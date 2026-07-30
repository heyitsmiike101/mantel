from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

PALETTE = [
    "#3b82f6",
    "#f97316",
    "#22c55e",
    "#a855f7",
    "#ec4899",
    "#eab308",
    "#14b8a6",
    "#ef4444",
]


def _get(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return user


@router.get(
    "",
    response_model=list[UserOut],
    summary="List family members",
    description="Returns everyone in the family with their assigned color, in display order.",
)
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.sort_order, User.id)))


@router.post(
    "",
    response_model=UserOut,
    status_code=201,
    summary="Add a family member",
    description=(
        "Creates a person. If you omit `color`, an unused color from the built-in palette is "
        "assigned automatically so no two people look alike."
    ),
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    data = payload.model_dump()
    if "color" not in payload.model_fields_set:
        taken = set(db.scalars(select(User.color)))
        data["color"] = next((c for c in PALETTE if c not in taken), PALETTE[0])
    user = User(**data)
    db.add(user)
    db.commit()
    return user


@router.get("/{user_id}", response_model=UserOut, summary="Get one family member")
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    return _get(db, user_id)


@router.patch("/{user_id}", response_model=UserOut, summary="Update a family member")
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)) -> User:
    user = _get(db, user_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.commit()
    return user


@router.delete(
    "/{user_id}",
    status_code=204,
    summary="Remove a family member",
    description=(
        "Deletes the person and unlinks their Google accounts. Calendars they claimed become "
        "unclaimed rather than being deleted, so no events are lost."
    ),
)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> None:
    db.delete(_get(db, user_id))
    db.commit()
