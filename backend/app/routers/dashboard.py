from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DashboardWidget
from ..schemas import WidgetCreate, WidgetOut, WidgetTypeOut, WidgetUpdate

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SIZES = ("small", "medium", "large")

# The canonical widget catalog. The frontend maps these type keys to components; anything
# listed here can be added through the API by an external tool or an AI agent.
WIDGET_TYPES: list[WidgetTypeOut] = [
    WidgetTypeOut(
        type="upcoming_events",
        name="Upcoming events",
        description="A running list of what's next, with buttons to add and remove events.",
        default_size="medium",
        config_schema={
            "days": "How many days ahead to show (default 7)",
            "user_ids": "Optional list of user ids to limit the list to",
            "max_items": "Maximum rows to show (default 12)",
        },
    ),
    WidgetTypeOut(
        type="today_agenda",
        name="Today by person",
        description="One column per family member showing today's events in their color.",
        default_size="large",
        config_schema={"user_ids": "Optional list of user ids; defaults to everyone"},
    ),
    WidgetTypeOut(
        type="clock",
        name="Clock and date",
        description="Large current time and date, for glancing at from across the room.",
        default_size="small",
        config_schema={"show_seconds": "true or false (default false)"},
    ),
    WidgetTypeOut(
        type="mini_month",
        name="Month at a glance",
        description=(
            "A compact month grid with event titles, day navigation, and an add-event button."
        ),
        default_size="medium",
        config_schema={},
    ),
    WidgetTypeOut(
        type="seven_day_checklist",
        name="7 day checklist",
        description="A fixed Monday–Sunday checklist for meals, independent of the calendar date.",
        default_size="large",
        config_schema={
            "checklist": "Items grouped by weekday; each item has id, text, and checked",
            "meal_history": "Unique previous meals saved when checklist items are added",
        },
    ),
    WidgetTypeOut(
        type="list",
        name="Shared list",
        description="A grocery or to-do list you can tick off from the wall.",
        default_size="medium",
        config_schema={
            "list_id": "Which list to show; defaults to the first one",
            "hide_checked": "true to hide items already ticked off",
        },
    ),
    WidgetTypeOut(
        type="weather",
        name="Weather",
        description="Current conditions and the days ahead, for the location set in settings.",
        default_size="medium",
        config_schema={"days": "How many forecast days to show (default 5)"},
    ),
    WidgetTypeOut(
        type="countdown",
        name="Countdown",
        description="Days until a date the family is looking forward to.",
        default_size="small",
        config_schema={
            "label": "What you're counting down to, e.g. 'Disney'",
            "date": "Target date as YYYY-MM-DD",
            "emoji": "Optional emoji shown above the number",
        },
    ),
    WidgetTypeOut(
        type="note",
        name="Family note",
        description="A free-text note everyone in the house can see and edit.",
        default_size="small",
        config_schema={"text": "The note contents"},
    ),
]

VALID_TYPES = {w.type for w in WIDGET_TYPES}


class ChecklistEdit(BaseModel):
    operation: Literal["add", "set_checked", "remove"]
    day: Literal["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    id: str = Field(min_length=1, max_length=128)
    text: str | None = Field(default=None, max_length=500)
    checked: bool | None = None


@router.get(
    "/widget-types",
    response_model=list[WidgetTypeOut],
    summary="Discover available widget types",
    description=(
        "Lists every widget that can be placed on the dashboard, along with the config keys "
        "each one accepts. Call this before POSTing a widget so you know what to send."
    ),
)
def widget_types() -> list[WidgetTypeOut]:
    return WIDGET_TYPES


@router.get(
    "/widgets",
    response_model=list[WidgetOut],
    summary="List dashboard widgets",
    description="Returns the shared dashboard wall in display order.",
)
def list_widgets(db: Session = Depends(get_db)) -> list[DashboardWidget]:
    return list(
        db.scalars(select(DashboardWidget).order_by(DashboardWidget.position, DashboardWidget.id))
    )


@router.post(
    "/widgets",
    response_model=WidgetOut,
    status_code=201,
    summary="Add a widget to the dashboard",
)
def create_widget(payload: WidgetCreate, db: Session = Depends(get_db)) -> DashboardWidget:
    if payload.widget_type not in VALID_TYPES:
        valid = ", ".join(sorted(VALID_TYPES))
        raise HTTPException(400, f"Unknown widget type. Valid types: {valid}")
    if payload.size not in SIZES:
        raise HTTPException(400, f"size must be one of: {', '.join(SIZES)}")

    position = payload.position
    if position is None:
        highest = db.scalar(select(func.max(DashboardWidget.position)))
        position = 0 if highest is None else highest + 1

    widget = DashboardWidget(
        widget_type=payload.widget_type,
        size=payload.size,
        position=position,
        config=payload.config,
    )
    db.add(widget)
    db.commit()
    return widget


@router.patch(
    "/widgets/{widget_id}",
    response_model=WidgetOut,
    summary="Move, resize, or reconfigure a widget",
)
def update_widget(
    widget_id: int, payload: WidgetUpdate, db: Session = Depends(get_db)
) -> DashboardWidget:
    widget = db.get(DashboardWidget, widget_id)
    if widget is None:
        raise HTTPException(404, "Widget not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("size") and changes["size"] not in SIZES:
        raise HTTPException(400, f"size must be one of: {', '.join(SIZES)}")
    for key, value in changes.items():
        setattr(widget, key, value)
    db.commit()
    return widget


@router.post(
    "/widgets/{widget_id}/checklist",
    response_model=WidgetOut,
    summary="Edit one item in a seven-day checklist",
)
def edit_checklist(
    widget_id: int, payload: ChecklistEdit, db: Session = Depends(get_db)
) -> DashboardWidget:
    if payload.operation == "add" and (not payload.text or not payload.text.strip()):
        raise HTTPException(400, "text is required to add an item")
    if payload.operation == "set_checked" and payload.checked is None:
        raise HTTPException(400, "checked is required to update an item")

    for _ in range(10):
        widget = db.get(DashboardWidget, widget_id)
        if widget is None:
            raise HTTPException(404, "Widget not found")
        if widget.widget_type != "seven_day_checklist":
            raise HTTPException(400, "Widget is not a seven-day checklist")

        config = widget.config or {}
        checklist = config.get("checklist") or {}
        items = list(checklist.get(payload.day) or [])
        match = next((item for item in items if item.get("id") == payload.id), None)
        if payload.operation == "add":
            if match is not None:
                raise HTTPException(409, "Checklist item already exists")
            items.append({"id": payload.id, "text": payload.text.strip(), "checked": False})
        elif match is None:
            raise HTTPException(404, "Checklist item not found")
        elif payload.operation == "set_checked":
            items = [
                {**item, "checked": payload.checked} if item.get("id") == payload.id else item
                for item in items
            ]
        else:
            items = [item for item in items if item.get("id") != payload.id]

        history = []
        seen = set()
        previous = config.get("meal_history") or []
        existing = (
            item.get("text")
            for day_items in checklist.values()
            if isinstance(day_items, list)
            for item in day_items
            if isinstance(item, dict)
        )
        for value in [*previous, *existing, payload.text if payload.operation == "add" else None]:
            if not isinstance(value, str) or not value.strip():
                continue
            name = value.strip()
            if name.casefold() not in seen:
                history.append(name)
                seen.add(name.casefold())

        next_config = {
            **config,
            "checklist": {**checklist, payload.day: items},
            "meal_history": history,
        }
        result = db.execute(
            update(DashboardWidget)
            .where(DashboardWidget.id == widget_id, DashboardWidget.config == config)
            .values(config=next_config)
        )
        if result.rowcount:
            db.commit()
            db.refresh(widget)
            return widget
        db.expire(widget)

    raise HTTPException(409, "Checklist changed too often; please try again")


@router.delete("/widgets/{widget_id}", status_code=204, summary="Remove a widget")
def delete_widget(widget_id: int, db: Session = Depends(get_db)) -> None:
    widget = db.get(DashboardWidget, widget_id)
    if widget is None:
        raise HTTPException(404, "Widget not found")
    db.delete(widget)
    db.commit()
