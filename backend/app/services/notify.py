"""Fan-out after a calendar change.

Kept separate from the routers so a write handler stays a write handler: it saves
and returns, and anything that wants to know about the change is somebody else's
problem on another thread.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AppSetting
from . import homeassistant


def calendar_changed(db: Session) -> None:
    """Nudge Home Assistant, if it is configured. Never raises, never blocks."""
    rows = {
        row.key: row.value.get("value")
        for row in db.scalars(
            select(AppSetting).where(
                AppSetting.key.in_(["ha_base_url", "ha_token", "ha_entity_id"])
            )
        )
    }
    homeassistant.notify_async(
        str(rows.get("ha_base_url") or ""),
        str(rows.get("ha_token") or ""),
        str(rows.get("ha_entity_id") or ""),
    )
