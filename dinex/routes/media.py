from io import BytesIO
import warnings
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy import select
from PIL import Image, ImageOps, UnidentifiedImageError
from ..db import add, database, owned
from ..models import Category, Item, Media, Restaurant
from ..security import audit, employee, permissions

router = APIRouter()


@router.post("/api/restaurant/images", status_code=201)
def upload(
    payload: bytes = Body(media_type="application/octet-stream"),
    u=Depends(employee),
    db=Depends(database),
):
    if not ({"menu", "profile"} & permissions(u)):
        raise HTTPException(403, "Image management permission is required.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload), formats=("JPEG", "PNG", "WEBP")) as src:
                if src.width * src.height > 12_000_000:
                    raise ValueError("pixel limit")
                im = ImageOps.exif_transpose(src).convert("RGB")
                im.thumbnail((1500, 1500))
                out = BytesIO()
                im.save(out, "WEBP", quality=82, method=3)
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(
            422, "Choose a JPEG, PNG or WebP image of up to 3 MiB and 12 megapixels."
        ) from None
    obj = add(db, Media, tenant=u.tenant, image=out.getvalue())
    audit(db, u, "image.uploaded", obj.id)
    return {"url": f"/media/{u.tenant}/{obj.id}"}


@router.get("/media/{tenant}/{ident}")
def image(tenant: int, ident: int, db=Depends(database)):
    r = db.get(Restaurant, tenant)
    if not r or r.status != "active":
        raise HTTPException(404, "Image unavailable.")
    path = f"/media/{tenant}/{ident}"
    on_menu = (
        select(Item.id)
        .join(Category, Category.id == Item.category_id)
        .where(
            Item.tenant == tenant,
            Category.tenant == tenant,
            Category.active.is_(True),
            Item.archived.is_(False),
            Item.image == path,
        )
        .limit(1)
    )
    if path not in (r.logo, r.cover) and not db.scalar(on_menu):
        raise HTTPException(404, "Image unavailable.")
    return Response(owned(db, Media, tenant, ident).image, media_type="image/webp")
