"""Additive schema migration at startup.

`Base.metadata.create_all` creates missing *tables* but silently ignores missing
*columns* on tables that already exist. That is fine on a fresh install and
broken on every upgrade: a self-hoster who runs `git pull && ./run.sh` would get
a 500 on the first write to any table that gained a column.

Every schema change this project has made so far is additive, and SQLite's
`ALTER TABLE ... ADD COLUMN` handles exactly that. So the upgrade path is:
compare the model's columns against the live table and add whatever is missing.

Deliberately limited: it will not drop columns, change types, or rename
anything. If a release ever needs that, it needs a real migration and a release
note -- and `verify()` will refuse to start rather than run against a schema it
cannot reconcile.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .models import Base

log = logging.getLogger(__name__)


def sync(engine: Engine) -> list[str]:
    """Create missing tables, then add missing columns. Returns what changed."""
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    applied: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table.name)}

        for column in table.columns:
            if column.name in existing:
                continue

            # SQLite refuses ADD COLUMN for a NOT NULL column with no default,
            # because existing rows would have nothing to put there.
            type_sql = column.type.compile(dialect=engine.dialect)
            pieces = [f'"{column.name}"', type_sql]

            default = _literal_default(column)
            if not column.nullable:
                if default is None:
                    log.error(
                        "Cannot add required column %s.%s automatically; it needs a default.",
                        table.name,
                        column.name,
                    )
                    continue
                pieces.append("NOT NULL")
            if default is not None:
                pieces.append(f"DEFAULT {default}")

            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN {" ".join(pieces)}'
            with engine.begin() as conn:
                conn.execute(text(ddl))
            applied.append(f"{table.name}.{column.name}")
            log.info("Schema upgrade: added %s.%s", table.name, column.name)

    # create_all only builds indexes alongside a brand-new table, so an index on a
    # column we just added would otherwise never exist.
    applied.extend(_sync_indexes(engine))
    return applied


def _sync_indexes(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    created: list[str] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in inspector.get_table_names():
            continue
        existing = {ix["name"] for ix in inspector.get_indexes(table.name)}
        table_columns = {c["name"] for c in inspector.get_columns(table.name)}
        for index in table.indexes:
            if index.name in existing:
                continue
            if not {c.name for c in index.columns} <= table_columns:
                continue  # a column we could not add; skip rather than fail startup
            index.create(bind=engine)
            created.append(f"index {index.name}")
            log.info("Schema upgrade: created %s", index.name)
    return created


def _literal_default(column) -> str | None:
    """SQL literal for a column's Python-side default, when there is a simple one."""
    default = column.default
    if default is None:
        return None
    value = getattr(default, "arg", None)
    if callable(value) or value is None:
        # Callable defaults (utcnow, dict) are applied by the ORM on insert;
        # backfilling existing rows with NULL is correct and expected.
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None
