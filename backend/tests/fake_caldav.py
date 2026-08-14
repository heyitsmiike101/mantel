"""A CalDAV server faked at the HTTP layer.

Deliberately not faked at the provider interface. The risky code in the iCloud
path *is* the XML: namespaces, multistatus shapes, where a sync token hides,
which status lives on a response versus a propstat. A fake that returned tidy
Python objects would exercise none of it.

So this speaks real multistatus XML over `httpx.MockTransport`, including the
parts of iCloud's behaviour that are easy to forget -- the redirect to a
partition host, and a PUT that answers without an ETag.
"""

import re
from xml.etree import ElementTree as ET

import httpx

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"

ENTRY_HOST = "https://caldav.icloud.com"
PARTITION_HOST = "https://p47-caldav.icloud.com"
PRINCIPAL = "/1234567890/principal/"
HOME = "/1234567890/calendars/"
CALENDAR = "/1234567890/calendars/home/"
TASKS = "/1234567890/calendars/reminders/"


class FakeCalDav:
    """Records what was sent, and can be told to misbehave in specific ways."""

    def __init__(self):
        # href -> (etag, ics body)
        self.resources: dict[str, tuple[str, str]] = {}
        self.sync_token = "sync-1"
        # Members reported by the next sync-collection, as (href, deleted).
        self.changed: list[tuple[str, bool]] = []
        self.expire_next_sync_token = False
        self.omit_etag_on_put = False
        self.fail_put_with: int | None = None
        self.unauthorized = False

        self.requests: list[tuple[str, str]] = []
        # Which REPORTs were asked for, in order. The baseline token must be taken
        # before the windowed read, so the order is part of the contract.
        self.reports: list[str] = []
        self.puts: list[tuple[str, str]] = []
        self.deletes: list[str] = []
        self.last_time_range: str | None = None
        self.last_sync_token: str | None = None

    # ------------------------------------------------------------------ setup

    def add_event(self, name: str, ics: str, etag: str = '"e1"') -> str:
        href = CALENDAR + name
        self.resources[href] = (etag, ics)
        return href

    def client(self, **kwargs) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(self.handle),
            follow_redirects=True,
            auth=httpx.BasicAuth("someone@example.com", "app-specific-password"),
            **kwargs,
        )

    # --------------------------------------------------------------- dispatch

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))

        if self.unauthorized:
            return httpx.Response(401, text="unauthorized")

        # iCloud does not serve the account from the address you first ask; it
        # bounces you to the partition that holds it.
        if request.url.host == "caldav.icloud.com" and request.method == "PROPFIND":
            return httpx.Response(301, headers={"Location": f"{PARTITION_HOST}{path or '/'}"})

        if request.method == "PROPFIND":
            return self._propfind(request, path)
        if request.method == "REPORT":
            return self._report(request, path)
        if request.method == "PUT":
            return self._put(request, path)
        if request.method == "DELETE":
            return self._delete(path)
        if request.method == "GET":
            return self._get(path)
        return httpx.Response(405, text=f"unexpected {request.method}")

    # -------------------------------------------------------------- PROPFIND

    def _propfind(self, request: httpx.Request, path: str) -> httpx.Response:
        body = request.content.decode()

        if "current-user-principal" in body:
            return _multistatus(
                _response(path or "/", {"current-user-principal": _href(PRINCIPAL)})
            )
        if "calendar-home-set" in body:
            return _multistatus(
                _response(PRINCIPAL, {"calendar-home-set": _href(HOME)}, ns=CALDAV)
            )

        # The calendar listing. The home itself and a task-only collection are both
        # in here because a real one contains them and they must be filtered out.
        return _multistatus(
            _raw_response(
                HOME,
                "<D:resourcetype><D:collection/></D:resourcetype>"
                "<D:displayname>Calendars</D:displayname>",
            ),
            _raw_response(
                CALENDAR,
                "<D:resourcetype><D:collection/><C:calendar/></D:resourcetype>"
                "<D:displayname>Home</D:displayname>"
                "<C:supported-calendar-component-set><C:comp name='VEVENT'/>"
                "</C:supported-calendar-component-set>"
                "<D:current-user-privilege-set>"
                "<D:privilege><D:read/></D:privilege>"
                "<D:privilege><D:write-content/></D:privilege>"
                "<D:privilege><D:bind/></D:privilege>"
                "</D:current-user-privilege-set>",
            ),
            _raw_response(
                TASKS,
                "<D:resourcetype><D:collection/><C:calendar/></D:resourcetype>"
                "<D:displayname>Reminders</D:displayname>"
                "<C:supported-calendar-component-set><C:comp name='VTODO'/>"
                "</C:supported-calendar-component-set>",
            ),
        )

    # ---------------------------------------------------------------- REPORT

    def _report(self, request: httpx.Request, path: str) -> httpx.Response:
        body = request.content.decode()

        if "sync-collection" in body:
            token = ET.fromstring(body).findtext(f"{{{DAV}}}sync-token")
            self.last_sync_token = token
            self.reports.append("baseline" if not token else "sync")
            if token and self.expire_next_sync_token:
                self.expire_next_sync_token = False
                return httpx.Response(
                    403,
                    text='<?xml version="1.0"?><D:error xmlns:D="DAV:">'
                    "<D:valid-sync-token/></D:error>",
                )
            if not token:
                # The baseline call: a token, and members we expect to be ignored.
                return _multistatus(
                    *[_raw_response(h, "<D:getetag>\"seed\"</D:getetag>") for h in self.resources],
                    sync_token=self.sync_token,
                )
            members = []
            for href, deleted in self.changed:
                if deleted:
                    members.append(_status_response(href, "HTTP/1.1 404 Not Found"))
                else:
                    etag = self.resources.get(href, ('"e1"', ""))[0]
                    members.append(_raw_response(href, f"<D:getetag>{etag}</D:getetag>"))
            return _multistatus(*members, sync_token=self.sync_token)

        if "calendar-query" in body:
            self.reports.append("query")
            match = re.search(r'time-range start="([^"]+)"', body)
            self.last_time_range = match.group(1) if match else None
            return _multistatus(
                *[
                    _raw_response(href, f"<D:getetag>{etag}</D:getetag>")
                    for href, (etag, _) in self.resources.items()
                ]
            )

        if "calendar-multiget" in body:
            self.reports.append("multiget")
            wanted = [el.text for el in ET.fromstring(body).findall(f"{{{DAV}}}href")]
            members = []
            for href in wanted:
                if href not in self.resources:
                    members.append(_status_response(href, "HTTP/1.1 404 Not Found"))
                    continue
                etag, ics = self.resources[href]
                members.append(
                    _raw_response(
                        href,
                        f"<D:getetag>{etag}</D:getetag>"
                        f"<C:calendar-data>{_escape(ics)}</C:calendar-data>",
                    )
                )
            return _multistatus(*members)

        return httpx.Response(400, text=f"unexpected REPORT: {body[:200]}")

    # ------------------------------------------------------------ PUT/DELETE

    def _put(self, request: httpx.Request, path: str) -> httpx.Response:
        if self.fail_put_with:
            status, self.fail_put_with = self.fail_put_with, None
            return httpx.Response(status, text="rejected")

        ics = request.content.decode()
        self.puts.append((path, ics))
        etag = f'"v{len(self.puts)}"'
        self.resources[path] = (etag, ics)
        headers = {} if self.omit_etag_on_put else {"ETag": etag}
        return httpx.Response(201, headers=headers)

    def _delete(self, path: str) -> httpx.Response:
        self.deletes.append(path)
        if path not in self.resources:
            return httpx.Response(404, text="gone")
        del self.resources[path]
        return httpx.Response(204)

    def _get(self, path: str) -> httpx.Response:
        if path not in self.resources:
            return httpx.Response(404, text="gone")
        etag, ics = self.resources[path]
        return httpx.Response(200, headers={"ETag": etag}, text=ics)


# ------------------------------- XML helpers ---------------------------------


def _multistatus(*responses: str, sync_token: str | None = None) -> httpx.Response:
    token = f"<D:sync-token>{sync_token}</D:sync-token>" if sync_token else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<D:multistatus xmlns:D="{DAV}" xmlns:C="{CALDAV}">'
        f"{''.join(responses)}{token}"
        "</D:multistatus>"
    )
    return httpx.Response(207, text=xml, headers={"Content-Type": "application/xml"})


def _raw_response(href: str, props: str) -> str:
    return (
        f"<D:response><D:href>{href}</D:href>"
        f"<D:propstat><D:prop>{props}</D:prop>"
        "<D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>"
    )


def _status_response(href: str, status: str) -> str:
    return f"<D:response><D:href>{href}</D:href><D:status>{status}</D:status></D:response>"


def _response(href: str, props: dict[str, str], ns: str = DAV) -> str:
    prefix = "C" if ns == CALDAV else "D"
    body = "".join(f"<{prefix}:{name}>{value}</{prefix}:{name}>" for name, value in props.items())
    return _raw_response(href, body)


def _href(path: str) -> str:
    return f"<D:href>{path}</D:href>"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------ sample payloads ------------------------------


def vevent(uid: str, summary: str, start: str, end: str, extra: str = "") -> str:
    """A timed event in UTC."""
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{summary}\r\n"
        f"DTSTART:{start}\r\nDTEND:{end}\r\nDTSTAMP:20260730T100000Z\r\n"
        f"LAST-MODIFIED:20260730T100000Z\r\n{extra}"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )


def vallday(uid: str, summary: str, start: str, end: str) -> str:
    """An all-day event. DTEND is exclusive, as it is everywhere else here."""
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{summary}\r\n"
        f"DTSTART;VALUE=DATE:{start}\r\nDTEND;VALUE=DATE:{end}\r\n"
        "DTSTAMP:20260730T100000Z\r\nLAST-MODIFIED:20260730T100000Z\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
