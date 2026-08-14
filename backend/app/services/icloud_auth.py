"""iCloud credentials.

Apple has no OAuth for calendars. The only supported route is CalDAV with an
Apple ID and an *app-specific password*, generated at appleid.apple.com. That is
a long-lived secret rather than a token that refreshes, so unlike Google there is
nothing to renew on a timer -- and nothing to set up before linking either: no
client id, no client secret, no redirect URI.

It is stored Fernet-encrypted in its own column. Sharing `refresh_token_enc` with
Google would have been tempting and wrong: the Google refresh path reads that
column and would try to trade a password for a token.
"""

import logging

from sqlalchemy.orm import Session

from ..models import LinkedAccount
from .caldav_client import ICLOUD_CALDAV, CalDavClient
from .crypto import decrypt, encrypt
from .providers.base import ProviderAuthError

log = logging.getLogger(__name__)

RELINK_HINT = (
    "iCloud rejected the saved app-specific password. Generate a new one at "
    "appleid.apple.com and link the account again."
)


def password_for(account: LinkedAccount) -> str:
    password = decrypt(account.password_enc)
    if not password:
        # Either nothing was stored, or SECRET_KEY was rotated and the ciphertext
        # can no longer be read. Both mean the same thing to the family: link again.
        raise ProviderAuthError(RELINK_HINT)
    return password


def client_for(account: LinkedAccount, http=None) -> CalDavClient:
    return CalDavClient(account.email, password_for(account), ICLOUD_CALDAV, http=http)


def calendar_home_for(db: Session, account: LinkedAccount, client: CalDavClient) -> str:
    """The account's calendar home, discovered once and remembered.

    Apple moves accounts between partition hosts, so this is re-discovered rather
    than assumed whenever it is missing -- and what gets stored is refreshed each
    time, so a move heals itself on the next sync.
    """
    if account.calendar_home_url:
        return account.calendar_home_url

    home = client.discover_calendar_home()
    account.calendar_home_url = home
    db.commit()
    return home


def verify_and_store(
    db: Session, account: LinkedAccount, app_password: str, http=None
) -> None:
    """Proves the credentials work, then saves them. Never the other way round.

    A password typed wrong, or one revoked in Apple ID settings, has to fail here
    -- while somebody is looking at the screen that can explain it. Storing first
    and finding out on the next background sync leaves a row that looks connected
    and quietly never syncs.

    Discovering the calendar home is the cheapest request that actually proves the
    password: it is two PROPFINDs and it produces something worth keeping.
    """
    client = CalDavClient(account.email, app_password, ICLOUD_CALDAV, http=http)
    home = client.discover_calendar_home()

    account.password_enc = encrypt(app_password)
    account.calendar_home_url = home
    account.status = "active"
    account.last_error = None
    db.commit()


def mark_needs_reauth(db: Session, account: LinkedAccount, error: str) -> None:
    account.status = "needs_reauth"
    account.last_error = error[:1000]
    db.commit()
