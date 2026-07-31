from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Naive UTC: SQLite has no timezone storage, so every timestamp in the database is
    UTC without an offset and is re-tagged as UTC on the way out."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(9), nullable=False, default="#3b82f6")
    avatar_emoji: Mapped[str | None] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    accounts: Mapped[list["LinkedAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class LinkedAccount(TimestampMixin, Base):
    __tablename__ = "linked_accounts"
    __table_args__ = (UniqueConstraint("provider", "email", name="uq_provider_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32), default="google")
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(32), default="active")
    last_error: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="accounts")
    calendars: Mapped[list["Calendar"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class Calendar(TimestampMixin, Base):
    __tablename__ = "calendars"
    __table_args__ = (
        UniqueConstraint("linked_account_id", "google_calendar_id", name="uq_account_gcal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    linked_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("linked_accounts.id", ondelete="CASCADE")
    )
    google_calendar_id: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    color_override: Mapped[str | None] = mapped_column(String(9))
    claimed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_token: Mapped[str | None] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[str | None] = mapped_column(Text)
    access_role: Mapped[str] = mapped_column(String(32), default="owner")

    account: Mapped[LinkedAccount | None] = relationship(back_populates="calendars")
    claimed_by: Mapped[User | None] = relationship()
    events: Mapped[list["Event"]] = relationship(
        back_populates="calendar", cascade="all, delete-orphan"
    )

    @property
    def is_local(self) -> bool:
        return self.linked_account_id is None

    @property
    def writable(self) -> bool:
        return self.is_local or self.access_role in ("owner", "writer")


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("calendar_id", "google_event_id", name="uq_calendar_gevent"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_id: Mapped[int] = mapped_column(ForeignKey("calendars.id", ondelete="CASCADE"))
    google_event_id: Mapped[str | None] = mapped_column(String(1024))
    google_etag: Mapped[str | None] = mapped_column(String(255))

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(500))

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str | None] = mapped_column(String(64))

    recurrence_rule: Mapped[str | None] = mapped_column(Text)
    recurring_event_id: Mapped[str | None] = mapped_column(String(1024))
    # True once a recurring event has been handed to Google. Google then returns
    # its own expanded instances, so the master must stop being displayed or every
    # occurrence would appear twice.
    is_master: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Last occurrence of a finite series, so a rule that finished years ago can be
    # excluded in SQL instead of being re-expanded on every calendar query. NULL
    # means either "not recurring" or "never ends".
    recurrence_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(32), default="confirmed")
    origin: Mapped[str] = mapped_column(String(16), default="local")
    sync_state: Mapped[str] = mapped_column(String(32), default="synced", index=True)
    local_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    remote_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    calendar: Mapped[Calendar] = relationship(back_populates="events")


class DashboardWidget(TimestampMixin, Base):
    __tablename__ = "dashboard_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    widget_type: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    size: Mapped[str] = mapped_column(String(16), default="medium")
    config: Mapped[dict] = mapped_column(JSON, default=dict)


class Photo(TimestampMixin, Base):
    """Screensaver photos. The file itself lives on disk under PHOTO_DIR; only the
    generated filename is stored, never anything the uploader controls."""

    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    original_name: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ShoppingList(TimestampMixin, Base):
    """A shared list -- groceries, chores, packing. Not per-user: the whole point
    is that anyone in the house can add to it from any screen."""

    __tablename__ = "lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(16))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    items: Mapped[list["ListItem"]] = relationship(
        back_populates="list", cascade="all, delete-orphan"
    )


class ListItem(TimestampMixin, Base):
    __tablename__ = "list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("lists.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    list: Mapped[ShoppingList] = relationship(back_populates="items")
    assigned_to: Mapped[User | None] = relationship()


class WeatherCache(Base):
    """Raw upstream responses, keyed by request. Kept in the database rather than
    memory so a restart doesn't leave the wall display blank until the next fetch."""

    __tablename__ = "weather_cache"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
