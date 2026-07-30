from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

HEX_COLOR_EXAMPLES = ["#3b82f6", "#f97316", "#22c55e"]


def _validate_hex(v: str) -> str:
    s = v.strip()
    if not s.startswith("#") or len(s) not in (4, 7, 9):
        raise ValueError("color must be a hex string like #3b82f6")
    int(s[1:], 16)
    return s.lower()


# ----------------------------- Users -----------------------------------------


class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["Mike"])
    color: str = Field(
        default="#3b82f6",
        description="Hex color used everywhere this person's events appear.",
        examples=HEX_COLOR_EXAMPLES,
    )
    avatar_emoji: str | None = Field(default=None, max_length=16, examples=["🦊"])
    sort_order: int = Field(default=0, description="Lower numbers appear first.")

    @field_validator("color")
    @classmethod
    def check_color(cls, v: str) -> str:
        return _validate_hex(v)


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    color: str | None = None
    avatar_emoji: str | None = None
    sort_order: int | None = None

    @field_validator("color")
    @classmethod
    def check_color(cls, v: str | None) -> str | None:
        return None if v is None else _validate_hex(v)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# --------------------------- Calendars ---------------------------------------


class CalendarCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["Soccer Season"])
    color_override: str | None = Field(default=None, examples=["#22c55e"])
    claimed_by_user_id: int | None = None

    @field_validator("color_override")
    @classmethod
    def check_color(cls, v: str | None) -> str | None:
        return None if v is None else _validate_hex(v)


class CalendarUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    color_override: str | None = None
    claimed_by_user_id: int | None = Field(
        default=None, description="Set to a user id to claim this calendar; null to unclaim."
    )
    sync_enabled: bool | None = None

    @field_validator("color_override")
    @classmethod
    def check_color(cls, v: str | None) -> str | None:
        return None if v is None else _validate_hex(v)


class CalendarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    is_local: bool
    google_calendar_id: str | None
    linked_account_id: int | None
    account_email: str | None = None
    claimed_by_user_id: int | None
    color: str = Field(description="Effective display color: override, else owner's color.")
    sync_enabled: bool
    access_role: str
    writable: bool
    last_synced_at: datetime | None
    sync_error: str | None


# ----------------------------- Events ----------------------------------------


class EventBase(BaseModel):
    title: str = Field(min_length=1, max_length=500, examples=["Soccer practice"])
    description: str | None = Field(default=None, examples=["Bring shin guards"])
    location: str | None = Field(default=None, max_length=500, examples=["Riverside Park"])
    start_at: datetime = Field(
        description="Event start, ISO-8601 with offset.", examples=["2026-08-03T17:00:00Z"]
    )
    end_at: datetime = Field(
        description="Event end, ISO-8601 with offset.", examples=["2026-08-03T18:30:00Z"]
    )
    all_day: bool = Field(
        default=False,
        description="All-day events span whole calendar days; times are ignored for display.",
    )
    timezone: str | None = Field(default=None, examples=["America/New_York"])


class EventCreate(EventBase):
    calendar_id: int = Field(
        description="Which calendar to write to. Use GET /api/calendars to find one."
    )


class EventUpdate(BaseModel):
    calendar_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    location: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    timezone: str | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    calendar_id: int
    calendar_name: str
    color: str = Field(description="Resolved display color, so clients need no extra lookups.")
    user_id: int | None = Field(description="Owner of the calendar this event lives on.")
    title: str
    description: str | None
    location: str | None
    start_at: datetime
    end_at: datetime
    all_day: bool
    timezone: str | None
    recurring: bool = Field(description="True if this instance came from a recurring series.")
    origin: str = Field(description="'local' or 'google'.")
    sync_state: str = Field(description="'synced' or a pending_* state awaiting push to Google.")
    editable: bool


# ---------------------------- Dashboard --------------------------------------


class WidgetCreate(BaseModel):
    widget_type: str = Field(examples=["upcoming_events"])
    size: str = Field(default="medium", examples=["medium"])
    position: int | None = Field(default=None, description="Defaults to the end of the wall.")
    config: dict = Field(default_factory=dict, examples=[{"days": 7}])


class WidgetUpdate(BaseModel):
    size: str | None = None
    position: int | None = None
    config: dict | None = None


class WidgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    widget_type: str
    size: str
    position: int
    config: dict


class WidgetTypeOut(BaseModel):
    type: str
    name: str
    description: str
    default_size: str
    config_schema: dict = Field(description="Keys this widget accepts in its config object.")
