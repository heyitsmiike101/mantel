from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Photo
from ..services import photos as photo_service

router = APIRouter(prefix="/photos", tags=["photos"])


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_name: str | None
    width: int
    height: int
    size_bytes: int
    sort_order: int
    url: str


def _out(photo: Photo) -> PhotoOut:
    return PhotoOut(
        id=photo.id,
        original_name=photo.original_name,
        width=photo.width,
        height=photo.height,
        size_bytes=photo.size_bytes,
        sort_order=photo.sort_order,
        url=f"/api/photos/{photo.id}/file",
    )


@router.get(
    "",
    response_model=list[PhotoOut],
    summary="List screensaver photos",
    description=(
        "Photos shown by the screensaver, in display order. Each carries a `url` you can "
        "load directly; the raw filename is never exposed."
    ),
)
def list_photos(db: Session = Depends(get_db)) -> list[PhotoOut]:
    rows = db.scalars(select(Photo).order_by(Photo.sort_order, Photo.id))
    return [_out(p) for p in rows]


@router.post(
    "",
    response_model=PhotoOut,
    status_code=201,
    summary="Upload a screensaver photo",
    description=(
        "Accepts a JPEG, PNG or WebP as multipart form-data under `file`. The image is "
        "re-encoded on the way in, which strips EXIF (including location) and shrinks "
        "anything oversized. Non-images are rejected regardless of their filename or "
        "declared content type."
    ),
)
async def upload_photo(
    file: UploadFile = File(description="The image to upload."),
    db: Session = Depends(get_db),
) -> PhotoOut:
    raw = await file.read()
    try:
        fields = photo_service.store(raw, file.filename)
    except photo_service.PhotoError as exc:
        raise HTTPException(400, str(exc)) from exc

    highest = db.scalar(select(func.max(Photo.sort_order)))
    photo = Photo(**fields, sort_order=0 if highest is None else highest + 1)
    db.add(photo)
    db.commit()
    return _out(photo)


@router.get(
    "/{photo_id}/file",
    summary="Fetch a photo's image data",
    response_class=FileResponse,
)
def get_photo_file(photo_id: int, db: Session = Depends(get_db)) -> FileResponse:
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    try:
        path = photo_service.path_for(photo.filename)
    except photo_service.PhotoError as exc:
        raise HTTPException(404, "Photo not found") from exc
    # Immutable: the filename is content-addressed by a random token and a photo's
    # bytes never change, so the screensaver can cache aggressively.
    return FileResponse(
        path,
        media_type=photo.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.delete("/{photo_id}", status_code=204, summary="Delete a photo")
def delete_photo(photo_id: int, db: Session = Depends(get_db)) -> None:
    photo = db.get(Photo, photo_id)
    if photo is None:
        raise HTTPException(404, "Photo not found")
    photo_service.delete_file(photo.filename)
    db.delete(photo)
    db.commit()
