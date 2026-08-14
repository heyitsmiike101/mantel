"""Which provider serves which linked account."""

from sqlalchemy.orm import Session

from ...models import AppSetting, LinkedAccount
from ..google_oauth import access_token_for
from .base import CalendarProvider
from .google import GoogleProvider

DEFAULT_TIMEZONE = "UTC"


def for_account(db: Session, account: LinkedAccount) -> CalendarProvider:
    """Builds a ready-to-use provider, refreshing credentials if that is needed.

    Google is the default rather than an explicit branch: every account predating
    the iCloud release has `provider="google"`, and so does anything that somehow
    arrives without one.
    """
    if account.provider == "icloud":
        from .. import icloud_auth
        from .icloud import ICloudProvider

        client = icloud_auth.client_for(account)
        home = icloud_auth.calendar_home_for(db, account, client)
        return ICloudProvider(client, home, _home_timezone(db))
    return GoogleProvider(access_token_for(db, account))


def _home_timezone(db: Session) -> str:
    """Where the family lives, for reading iCalendar times that carry no zone.

    A floating time means "whatever the clock says here". Assuming UTC would move
    a 3pm pickup by hours for most of the world.
    """
    row = db.get(AppSetting, "home_timezone")
    value = row.value.get("value") if row and isinstance(row.value, dict) else None
    return value or DEFAULT_TIMEZONE
