from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import ListItem, ShoppingList, User

router = APIRouter(prefix="/lists", tags=["lists"])


class ItemCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500, examples=["Milk"])
    assigned_user_id: int | None = Field(
        default=None, description="Optional; colors the item with that person's color."
    )


class ItemUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    checked: bool | None = None
    assigned_user_id: int | None = None
    sort_order: int | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    list_id: int
    text: str
    checked: bool
    assigned_user_id: int | None
    color: str | None = Field(description="Assignee's color, when one is assigned.")
    sort_order: int


class ListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, examples=["Groceries"])
    icon: str | None = Field(default=None, max_length=16, examples=["🛒"])


class ListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = None
    sort_order: int | None = None


class ListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    icon: str | None
    sort_order: int
    item_count: int = Field(description="Unchecked items remaining.")
    items: list[ItemOut]


def _item_out(item: ListItem) -> ItemOut:
    return ItemOut(
        id=item.id,
        list_id=item.list_id,
        text=item.text,
        checked=item.checked,
        assigned_user_id=item.assigned_user_id,
        color=item.assigned_to.color if item.assigned_to else None,
        sort_order=item.sort_order,
    )


def _list_out(row: ShoppingList) -> ListOut:
    # Unchecked first, then by position -- a checked-off item sinking to the
    # bottom is what makes a shared grocery list usable mid-aisle.
    items = sorted(row.items, key=lambda i: (i.checked, i.sort_order, i.id))
    return ListOut(
        id=row.id,
        name=row.name,
        icon=row.icon,
        sort_order=row.sort_order,
        item_count=sum(1 for i in items if not i.checked),
        items=[_item_out(i) for i in items],
    )


def _load(db: Session, list_id: int) -> ShoppingList:
    row = db.scalar(
        select(ShoppingList)
        .where(ShoppingList.id == list_id)
        .options(selectinload(ShoppingList.items).selectinload(ListItem.assigned_to))
    )
    if row is None:
        raise HTTPException(404, "List not found")
    return row


@router.get(
    "",
    response_model=list[ListOut],
    summary="List every shared list, with its items",
    description=(
        "Lists are shared by the whole household -- there are no private lists. Items come "
        "back with unchecked ones first, then in display order."
    ),
)
def get_lists(db: Session = Depends(get_db)) -> list[ListOut]:
    rows = db.scalars(
        select(ShoppingList)
        .order_by(ShoppingList.sort_order, ShoppingList.id)
        .options(selectinload(ShoppingList.items).selectinload(ListItem.assigned_to))
    )
    return [_list_out(r) for r in rows]


@router.post("", response_model=ListOut, status_code=201, summary="Create a list")
def create_list(payload: ListCreate, db: Session = Depends(get_db)) -> ListOut:
    highest = db.scalar(select(func.max(ShoppingList.sort_order)))
    row = ShoppingList(
        **payload.model_dump(), sort_order=0 if highest is None else highest + 1
    )
    db.add(row)
    db.commit()
    return _list_out(_load(db, row.id))


@router.get("/{list_id}", response_model=ListOut, summary="Get one list")
def get_list(list_id: int, db: Session = Depends(get_db)) -> ListOut:
    return _list_out(_load(db, list_id))


@router.patch("/{list_id}", response_model=ListOut, summary="Rename or reorder a list")
def update_list(list_id: int, payload: ListUpdate, db: Session = Depends(get_db)) -> ListOut:
    row = _load(db, list_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    return _list_out(_load(db, list_id))


@router.delete(
    "/{list_id}",
    status_code=204,
    summary="Delete a list and everything on it",
)
def delete_list(list_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_load(db, list_id))
    db.commit()


@router.post(
    "/{list_id}/items",
    response_model=ItemOut,
    status_code=201,
    summary="Add an item",
)
def add_item(list_id: int, payload: ItemCreate, db: Session = Depends(get_db)) -> ItemOut:
    _load(db, list_id)
    if payload.assigned_user_id is not None and db.get(User, payload.assigned_user_id) is None:
        raise HTTPException(404, "User not found")

    highest = db.scalar(
        select(func.max(ListItem.sort_order)).where(ListItem.list_id == list_id)
    )
    item = ListItem(
        list_id=list_id, **payload.model_dump(), sort_order=0 if highest is None else highest + 1
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.patch(
    "/{list_id}/items/{item_id}",
    response_model=ItemOut,
    summary="Check off, rename, assign or reorder an item",
)
def update_item(
    list_id: int, item_id: int, payload: ItemUpdate, db: Session = Depends(get_db)
) -> ItemOut:
    item = db.get(ListItem, item_id)
    if item is None or item.list_id != list_id:
        raise HTTPException(404, "Item not found")
    changes = payload.model_dump(exclude_unset=True)
    assignee = changes.get("assigned_user_id")
    if assignee is not None and db.get(User, assignee) is None:
        raise HTTPException(404, "User not found")
    for key, value in changes.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.delete("/{list_id}/items/{item_id}", status_code=204, summary="Remove an item")
def delete_item(list_id: int, item_id: int, db: Session = Depends(get_db)) -> None:
    item = db.get(ListItem, item_id)
    if item is None or item.list_id != list_id:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.commit()


@router.post(
    "/{list_id}/clear-checked",
    response_model=ListOut,
    summary="Remove every checked item",
    description="The 'we're home from the shop' button.",
)
def clear_checked(list_id: int, db: Session = Depends(get_db)) -> ListOut:
    _load(db, list_id)
    db.execute(
        delete(ListItem).where(ListItem.list_id == list_id, ListItem.checked.is_(True))
    )
    db.commit()
    return _list_out(_load(db, list_id))
