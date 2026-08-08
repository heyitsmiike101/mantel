"""A CalDAV client, narrow enough to read in one sitting.

Only what two-way calendar sync needs: find the calendars, ask what changed since
last time, fetch the bodies, and write one back. The requests are a fixed handful
of small documents, so they are literal strings here rather than generated -- a
library to build them would be bigger than they are.

Transport and XML only. Nothing here knows about this app's models; see
`services/providers/icloud.py` for the translation into events.

Two shapes of identity travel through this module and they are easy to confuse:

* a **collection URL** -- the calendar, e.g. `/1234567890/calendars/home/`
* an **href** -- one event resource inside it, e.g. `/1234567890/calendars/home/A1B2.ics`

Everything returned here is a *path*, resolved against whatever base was passed
in. Apple moves accounts between partition hosts (`p47-caldav.icloud.com`), so
storing paths and re-resolving them against a freshly discovered home keeps
working when that happens.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from xml.etree import ElementTree as ET

import httpx

from .providers.base import ProviderAuthError, ProviderError, SyncTokenExpired

log = logging.getLogger(__name__)

ICLOUD_CALDAV = "https://caldav.icloud.com"

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"

_NS = {"D": DAV, "C": CALDAV}

# One request per 50 events. Large enough that a normal calendar is one or two
# round trips, small enough that the response stays a sane size to hold in memory.
MULTIGET_BATCH = 50


def _q(tag: str, ns: str = DAV) -> str:
    return f"{{{ns}}}{tag}"


@dataclass(slots=True)
class DavCalendar:
    """A calendar collection, as advertised by PROPFIND."""

    path: str
    name: str = ""
    # Google's vocabulary, so `Calendar.access_role` means one thing everywhere.
    access_role: str = "reader"


@dataclass(slots=True)
class DavResource:
    """One event resource. `data` is only populated by a multiget or a GET."""

    href: str
    etag: str | None = None
    data: str | None = None
    deleted: bool = False


@dataclass(slots=True)
class _DavResponse:
    href: str
    status: int | None = None
    props: dict[str, ET.Element] = field(default_factory=dict)


class CalDavClient:
    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = ICLOUD_CALDAV,
        http: httpx.Client | None = None,
    ):
        self._base = base_url.rstrip("/") + "/"
        # iCloud answers the well-known entry point with a redirect to the partition
        # host that actually holds the account, so redirects must be followed.
        self._http = http or httpx.Client(
            timeout=60,
            follow_redirects=True,
            auth=httpx.BasicAuth(username, password),
        )

    # ------------------------------ transport --------------------------------

    def _request(
        self,
        method: str,
        url: str,
        body: str | bytes | None = None,
        depth: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        sent = {"Content-Type": 'application/xml; charset="utf-8"'}
        if depth is not None:
            sent["Depth"] = depth
        if headers:
            sent.update(headers)

        content = body.encode() if isinstance(body, str) else body
        try:
            resp = self._http.request(method, url, content=content, headers=sent)
        except httpx.HTTPError as exc:
            # A DNS failure or dropped connection is not an auth problem; surface it
            # as a plain provider error so the calendar records it and retries.
            raise ProviderError(0, f"Could not reach the calendar server: {exc}") from exc

        if resp.status_code >= 400:
            _raise_for(resp)
        return resp

    # ------------------------------ discovery --------------------------------

    def discover_calendar_home(self) -> str:
        """Principal, then calendar home. Returns an absolute URL.

        Two hops because CalDAV keeps "who am I" and "where are my calendars"
        apart. The result is cached on the account so this only runs at link time
        and after a failure.
        """
        resp = self._request("PROPFIND", self._base, _PROPFIND_PRINCIPAL, depth="0")
        principal = _first_href(resp, _q("current-user-principal"))
        if not principal:
            raise ProviderError(0, "The server did not say which principal we are")
        principal_url = _resolve(str(resp.url), principal)

        resp = self._request("PROPFIND", principal_url, _PROPFIND_HOME, depth="0")
        home = _first_href(resp, _q("calendar-home-set", CALDAV))
        if not home:
            raise ProviderError(0, "The server did not say where the calendars are")
        return _resolve(str(resp.url), home)

    def list_calendars(self, home_url: str) -> list[DavCalendar]:
        """Every collection under the home that can actually hold an event.

        A calendar home also contains inbox, outbox, notification and (on iCloud)
        task-only collections. Offering those would be offering somewhere an event
        cannot be created -- the same rule the Calendars page already applies.
        """
        resp = self._request("PROPFIND", home_url, _PROPFIND_CALENDARS, depth="1")

        found = []
        for entry in _multistatus(resp):
            resourcetype = entry.props.get(_q("resourcetype"))
            if resourcetype is None or resourcetype.find(_q("calendar", CALDAV)) is None:
                continue
            components = entry.props.get(_q("supported-calendar-component-set", CALDAV))
            if not _supports_vevent(components):
                continue

            display = entry.props.get(_q("displayname"))
            found.append(
                DavCalendar(
                    path=_path_of(entry.href),
                    name=(display.text or "").strip() if display is not None else "",
                    access_role=_access_role(entry.props.get(_q("current-user-privilege-set"))),
                )
            )
        return found

    # -------------------------------- reading --------------------------------

    def baseline_sync_token(self, collection_url: str) -> str | None:
        """A cursor for "from now on", without downloading the calendar's history.

        A `calendar-query` cannot return a sync token, and a sync-collection with an
        empty one returns every event ever -- ignoring the time window and pulling
        years of the past on an old calendar. So take a token from an empty
        sync-collection asking only for etags, throw the member list away, and get
        the events themselves from a windowed query instead.

        Callers must do this *before* the query, never after: a change landing
        between the two is then reported again by the next delta and simply
        re-applied, rather than falling into the gap and being lost for good.
        """
        resp = self._request("REPORT", collection_url, _sync_body(None), depth="0")
        return _sync_token_of(resp)

    def sync_collection(
        self, collection_url: str, sync_token: str
    ) -> tuple[list[DavResource], str | None]:
        """What changed since `sync_token`. Deletions come back as `deleted=True`."""
        resp = self._request("REPORT", collection_url, _sync_body(sync_token), depth="0")

        changed = []
        for entry in _multistatus(resp):
            if _is_the_collection(entry.href, collection_url):
                continue
            href = _path_of(entry.href)
            if entry.status == 404:
                changed.append(DavResource(href=href, deleted=True))
                continue
            changed.append(DavResource(href=href, etag=_etag_of(entry)))
        return changed, _sync_token_of(resp)

    def list_hrefs_in_window(self, collection_url: str, time_min: datetime) -> list[DavResource]:
        """Every event resource touching the window from `time_min` onwards.

        Open-ended on the right: the wall display shows the future, and a bound
        there would silently hide anything past it.
        """
        body = _CALENDAR_QUERY.format(start=_ical_utc(time_min))
        resp = self._request("REPORT", collection_url, body, depth="1")
        return [
            DavResource(href=_path_of(e.href), etag=_etag_of(e))
            for e in _multistatus(resp)
            if not _is_the_collection(e.href, collection_url)
        ]

    def fetch(self, collection_url: str, hrefs: list[str]) -> list[DavResource]:
        """Bodies for the given resources, in batches."""
        out: list[DavResource] = []
        for batch in _chunks(hrefs, MULTIGET_BATCH):
            body = _multiget_body(batch)
            resp = self._request("REPORT", collection_url, body, depth="1")
            for entry in _multistatus(resp):
                data = entry.props.get(_q("calendar-data", CALDAV))
                if data is None or not (data.text or "").strip():
                    continue
                out.append(
                    DavResource(
                        href=_path_of(entry.href),
                        etag=_etag_of(entry),
                        data=data.text,
                    )
                )
        return out

    def get(self, url: str) -> DavResource:
        resp = self._request("GET", url, headers={"Accept": "text/calendar"})
        return DavResource(
            href=_path_of(str(resp.url)),
            etag=_clean_etag(resp.headers.get("ETag")),
            data=resp.text,
        )

    # -------------------------------- writing --------------------------------

    def put(self, url: str, ics: str, etag: str | None = None, create: bool = False) -> str | None:
        """Writes one resource. Returns the new etag if the server volunteered one.

        `create=True` sends `If-None-Match: *` so a colliding filename fails rather
        than silently overwriting somebody else's event. Otherwise `If-Match`
        guards against writing over a change we have not seen.
        """
        headers = {"Content-Type": "text/calendar; charset=utf-8"}
        if create:
            headers["If-None-Match"] = "*"
        elif etag:
            headers["If-Match"] = etag

        resp = self._request("PUT", url, ics.encode("utf-8"), headers=headers)
        # The spec lets a server omit the ETag here, and iCloud sometimes does. The
        # caller has to re-read it in that case, or the next If-Match is stale and
        # every later update 412s.
        return _clean_etag(resp.headers.get("ETag"))

    def delete(self, url: str, etag: str | None = None) -> None:
        headers = {"If-Match": etag} if etag else {}
        self._request("DELETE", url, headers=headers)

    def resolve(self, base: str, path: str) -> str:
        return _resolve(base, path)


# ------------------------------ request bodies -------------------------------

_PROPFIND_PRINCIPAL = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:current-user-principal/></D:prop>
</D:propfind>"""

_PROPFIND_HOME = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><C:calendar-home-set/></D:prop>
</D:propfind>"""

_PROPFIND_CALENDARS = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:resourcetype/>
    <D:displayname/>
    <D:current-user-privilege-set/>
    <C:supported-calendar-component-set/>
  </D:prop>
</D:propfind>"""

_CALENDAR_QUERY = """<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/></D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""


def _sync_body(token: str | None) -> str:
    element = f"<D:sync-token>{_escape(token)}</D:sync-token>" if token else "<D:sync-token/>"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<D:sync-collection xmlns:D="DAV:">\n'
        f"  {element}\n"
        "  <D:sync-level>1</D:sync-level>\n"
        "  <D:prop><D:getetag/></D:prop>\n"
        "</D:sync-collection>"
    )


def _multiget_body(hrefs: list[str]) -> str:
    lines = "\n".join(f"  <D:href>{_escape(h)}</D:href>" for h in hrefs)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<C:calendar-multiget xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">\n'
        "  <D:prop><D:getetag/><C:calendar-data/></D:prop>\n"
        f"{lines}\n"
        "</C:calendar-multiget>"
    )


# -------------------------------- parsing ------------------------------------


def _parse(resp: httpx.Response) -> ET.Element | None:
    try:
        return ET.fromstring(resp.content)
    except ET.ParseError as exc:
        raise ProviderError(resp.status_code, f"Unreadable XML from the server: {exc}") from exc


def _multistatus(resp: httpx.Response) -> list[_DavResponse]:
    root = _parse(resp)
    if root is None:
        return []

    out = []
    for node in root.findall(_q("response")):
        href_el = node.find(_q("href"))
        entry = _DavResponse(href=(href_el.text or "").strip() if href_el is not None else "")

        # A deleted member carries its status directly, with no propstat at all.
        status_el = node.find(_q("status"))
        if status_el is not None:
            entry.status = _status_code(status_el.text)

        for propstat in node.findall(_q("propstat")):
            code = _status_code(propstat.findtext(_q("status")) or "")
            if code is not None and code >= 400:
                continue  # a prop this resource does not have; not an error for us
            prop = propstat.find(_q("prop"))
            if prop is None:
                continue
            for child in prop:
                entry.props[child.tag] = child
        out.append(entry)
    return out


def _sync_token_of(resp: httpx.Response) -> str | None:
    root = _parse(resp)
    if root is None:
        return None
    token = root.findtext(_q("sync-token"))
    return token.strip() if token else None


def _etag_of(entry: _DavResponse) -> str | None:
    el = entry.props.get(_q("getetag"))
    return _clean_etag(el.text if el is not None else None)


def _clean_etag(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    # A weak validator still identifies the version we read, which is all If-Match
    # needs; keeping the W/ prefix would just make the comparison fail.
    if value.startswith("W/"):
        value = value[2:]
    return value or None


def _first_href(resp: httpx.Response, prop: str) -> str | None:
    for entry in _multistatus(resp):
        element = entry.props.get(prop)
        if element is None:
            continue
        href = element.find(_q("href"))
        if href is not None and href.text:
            return href.text.strip()
    return None


def _supports_vevent(element: ET.Element | None) -> bool:
    # An absent property means the server did not say. RFC 4791 makes VEVENT the
    # default, and refusing a calendar because a server was terse would hide real
    # ones -- so only exclude a collection that explicitly lists other components.
    if element is None:
        return True
    names = [c.get("name") for c in element.findall(_q("comp", CALDAV))]
    return not names or "VEVENT" in names


def _access_role(element: ET.Element | None) -> str:
    """Map DAV privileges onto the owner/writer/reader vocabulary already in use."""
    if element is None:
        return "reader"
    granted = {
        child.tag
        for privilege in element.findall(_q("privilege"))
        for child in privilege
    }
    if _q("all") in granted or _q("write") in granted:
        return "owner"
    if _q("write-content") in granted and _q("bind") in granted:
        return "writer"
    return "reader"


def _status_code(text: str | None) -> int | None:
    # "HTTP/1.1 404 Not Found"
    if not text:
        return None
    parts = text.split()
    for part in parts:
        if part.isdigit():
            return int(part)
    return None


def _raise_for(resp: httpx.Response) -> None:
    body = resp.text or ""

    # Order matters: an expired sync token is reported as 403, and treating it as
    # an auth failure would tell the family to re-link a perfectly good account
    # instead of quietly resyncing.
    if "valid-sync-token" in body:
        raise SyncTokenExpired(resp.status_code, "The sync token is no longer valid")
    if resp.status_code == 401:
        raise ProviderAuthError(
            "iCloud rejected the app-specific password. Generate a new one at "
            "appleid.apple.com and link the account again."
        )
    raise ProviderError(resp.status_code, body[:500] or resp.reason_phrase)


# -------------------------------- helpers ------------------------------------


def _resolve(base: str, href: str) -> str:
    return str(httpx.URL(base).join(href))


def _is_the_collection(href: str, collection_url: str) -> bool:
    """A multistatus includes the collection it was asked about, alongside its
    members. Treating that entry as an event would invent a row on every sync."""
    path = _path_of(href)
    return not path or path.rstrip("/") == _path_of(collection_url).rstrip("/")


def _path_of(url: str) -> str:
    if not url:
        return ""
    parsed = httpx.URL(url)
    return parsed.path if parsed.is_absolute_url else url


def _ical_utc(moment: datetime) -> str:
    """iCalendar's UTC form. A time-range filter rejects ISO 8601 with separators."""
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
