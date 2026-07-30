from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Calendar
from ..schemas import CalendarCreate, CalendarOut, CalendarUpdate
from ..serializers import calendar_out

router = APIRouter(prefix="/calendars", tags=["calendars"])


def _get(db: Session, calendar_id: int) -> Calendar:
    cal = db.get(Calendar, calendar_id)
    if cal is None:
        raise HTTPException(404, "Calendar not found")
    return cal


@router.get(
    "",
    response_model=list[CalendarOut],
    summary="List calendars",
    description=(
        "Every calendar known to the app: local ones plus any discovered from linked Google "
        "accounts. A calendar only appears on the wall display once a family member claims it."
    ),
)
def list_calendars(
    claimed: bool | None = Query(default=None, description="Filter to claimed/unclaimed only."),
    user_id: int | None = Query(default=None, description="Only calendars claimed by this user."),
    db: Session = Depends(get_db),
) -> list[CalendarOut]:
    stmt = select(Calendar).order_by(Calendar.name)
    if claimed is True:
        stmt = stmt.where(Calendar.claimed_by_user_id.is_not(None))
    elif claimed is False:
        stmt = stmt.where(Calendar.claimed_by_user_id.is_(None))
    if user_id is not None:
        stmt = stmt.where(Calendar.claimed_by_user_id == user_id)
    return [calendar_out(c) for c in db.scalars(stmt)]


@router.post(
    "",
    response_model=CalendarOut,
    status_code=201,
    summary="Create a local calendar",
    description=(
        "Local calendars live only in this app and never sync to Google. Useful for things like "
        "chores or a shared family schedule that nobody has a Google calendar for."
    ),
)
def create_calendar(payload: CalendarCreate, db: Session = Depends(get_db)) -> CalendarOut:
    cal = Calendar(**payload.model_dump(), linked_account_id=None, sync_enabled=False)
    db.add(cal)
    db.commit()
    return calendar_out(cal)


@router.get("/{calendar_id}", response_model=CalendarOut, summary="Get one calendar")
def get_calendar(calendar_id: int, db: Session = Depends(get_db)) -> CalendarOut:
    return calendar_out(_get(db, calendar_id))


@router.patch(
    "/{calendar_id}",
    response_model=CalendarOut,
    summary="Update a calendar (claim it, recolor it, toggle sync)",
    description=(
        "Set `claimed_by_user_id` to have a family member claim this calendar — that is what "
        "makes it visible and gives its events that person's color."
    ),
)
def update_calendar(
    calendar_id: int, payload: CalendarUpdate, db: Session = Depends(get_db)
) -> CalendarOut:
    cal = _get(db, calendar_id)
    changes = payload.model_dump(exclude_unset=True)
    if cal.is_local and changes.get("sync_enabled"):
        raise HTTPException(400, "Local calendars cannot sync to Google")
    for key, value in changes.items():
        setattr(cal, key, value)
    db.commit()
    db.refresh(cal)
    return calendar_out(cal)


@router.delete(
    "/{calendar_id}",
    status_code=204,
    summary="Delete a local calendar",
    description=(
        "Only local calendars can be deleted, along with their events. To stop showing a Google "
        "calendar, unclaim it or set sync_enabled=false instead — that leaves Google untouched."
    ),
)
def delete_calendar(calendar_id: int, db: Session = Depends(get_db)) -> None:
    cal = _get(db, calendar_id)
    if not cal.is_local:
        raise HTTPException(400, "Google calendars cannot be deleted here; unclaim it instead")
    db.delete(cal)
    db.commit()
