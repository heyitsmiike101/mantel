from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
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
        description="A compact month grid with a dot on days that have events.",
        default_size="medium",
        config_schema={},
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


@router.delete("/widgets/{widget_id}", status_code=204, summary="Remove a widget")
def delete_widget(widget_id: int, db: Session = Depends(get_db)) -> None:
    widget = db.get(DashboardWidget, widget_id)
    if widget is None:
        raise HTTPException(404, "Widget not found")
    db.delete(widget)
    db.commit()
