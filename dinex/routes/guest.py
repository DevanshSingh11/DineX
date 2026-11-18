import hmac
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select

from ..assistant import answer
from .. import gemini
from ..catalog import PUBLIC_PROFILE, entitlement, fields, menu
from ..db import add, database, owned, rows
from ..models import Bill, DiningTable, Order, Plan, Restaurant, Service, Visit, now
from ..ordering import bill_view, current_table, order_view, place, request_bill
from ..schemas import Enter, OrderInput, Question, ServiceInput
from ..security import audit, digest, guest, qr_signature

router = APIRouter(prefix="/api/guest")


@router.post("/enter/{slug}")
def enter(slug: str, data: Enter, request: Request, db=Depends(database)):
    request.app.state.limits.hit(request, "enter", 90)
    r = db.scalar(
        select(Restaurant).where(Restaurant.slug == slug, Restaurant.status == "active")
    )
    t = (
        db.scalar(
            select(DiningTable).where(
                DiningTable.tenant == r.id, DiningTable.id == data.table_id
            )
        )
        if r
        else None
    )
    if (
        not t
        or not t.active
        or not t.qr_enabled
        or not hmac.compare_digest(
            qr_signature(request.app.state.cfg, t), data.credential
        )
    ):
        raise HTTPException(
            404,
            "This table QR is inactive or has changed. Ask staff for the current code.",
        )
    # Re-scanning on the same device resumes this visit when the credential is still current.
    auth = request.headers.get("Authorization", "").partition(" ")
    if auth[0] == "Bearer":
        old = db.scalar(
            select(Visit).where(
                Visit.digest == digest(auth[2]),
                Visit.tenant == r.id,
                Visit.table_id == t.id,
                Visit.expires > now(),
                Visit.qr_nonce == t.qr_nonce,
                Visit.closed.is_(False),
            )
        )
        if old:
            return {"token": auth[2], "visit_id": old.id}
    token = secrets.token_urlsafe(36)
    v = add(
        db,
        Visit,
        tenant=r.id,
        table_id=t.id,
        qr_nonce=t.qr_nonce,
        digest=digest(token),
        expires=now() + 48 * 3600,
    )
    return {"token": token, "visit_id": v.id}


@router.get("/menu")
def guest_menu(request: Request, v=Depends(guest), db=Depends(database)):
    r = db.get(Restaurant, v.tenant)
    t = owned(db, DiningTable, v.tenant, v.table_id)
    enabled = db.get(Plan, r.plan_id).assistant
    return {
        "restaurant": fields(r, PUBLIC_PROFILE),
        "table": fields(t, "id name"),
        "visit_id": v.id,
        "guide": {
            "enabled": enabled,
            "gemini": bool(enabled and request.app.state.cfg.gemini_key),
            "external": bool(
                enabled
                and (
                    request.app.state.cfg.gemini_key
                    or (
                        request.app.state.cfg.ai_url
                        and request.app.state.cfg.ai_key
                        and request.app.state.cfg.ai_model
                    )
                )
            ),
        },
        "can_order": bool(
            t.active and t.qr_enabled and t.qr_nonce == v.qr_nonce and not v.closed
        ),
        **menu(db, v.tenant, public=True),
    }


@router.post("/orders", status_code=201)
def order(data: OrderInput, request: Request, v=Depends(guest), db=Depends(database)):
    request.app.state.limits.hit(request, "orders", 90)
    return order_view(db, place(db, v, data))


@router.get("/state")
def state(v=Depends(guest), db=Depends(database)):
    return {
        "visit_id": v.id,
        "closed": v.closed,
        "orders": [
            order_view(db, o)
            for o in reversed(rows(db, Order, v.tenant, Order.visit_id == v.id))
        ],
        "bills": [
            bill_view(db, b, guest=True)
            for b in reversed(rows(db, Bill, v.tenant, Bill.visit_id == v.id))
        ],
        "services": [
            fields(s, "id kind status note created")
            for s in reversed(rows(db, Service, v.tenant, Service.visit_id == v.id))
        ],
    }


@router.post("/bills")
def bill(v=Depends(guest), db=Depends(database)):
    return bill_view(db, request_bill(db, v, v), guest=True)


@router.post("/services", status_code=201)
def service(
    data: ServiceInput, request: Request, v=Depends(guest), db=Depends(database)
):
    request.app.state.limits.hit(request, "service", 60)
    current_table(db, v)
    old = rows(
        db,
        Service,
        v.tenant,
        Service.visit_id == v.id,
        Service.kind == data.kind,
        Service.status != "resolved",
        *([Service.note == data.note] if data.kind == "ingredient_check" else []),
    )
    if old:
        return fields(old[-1], "id kind status")
    req = add(
        db,
        Service,
        tenant=v.tenant,
        table_id=v.table_id,
        visit_id=v.id,
        **data.model_dump(),
    )
    audit(db, v, "service.opened", req.id, data.kind)
    return fields(req, "id kind status")


@router.post("/assistant")
def assistant(data: Question, request: Request, v=Depends(guest), db=Depends(database)):
    request.app.state.limits.hit(request, "assistant", 30)
    entitlement(db, v.tenant, "assistant")
    return answer(
        request.app.state.cfg,
        data.question,
        menu(db, v.tenant, public=True),
        data.avoid,
        data.confirmed,
    )


@router.post("/assistant/transcribe")
async def voice_note(request: Request, v=Depends(guest), db=Depends(database)):
    entitlement(db, v.tenant, "assistant")
    request.app.state.limits.hit(request, "voice-note", 8)
    cfg = request.app.state.cfg
    if not cfg.gemini_key:
        raise HTTPException(
            503, "Voice notes need a Gemini key. Type or use keyboard dictation."
        )
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type not in gemini.AUDIO_TYPES:
        raise HTTPException(
            415, "Choose a WAV, MP3, M4A, AAC, OGG, FLAC or WebM audio note."
        )
    clip = await request.body()
    if not clip:
        raise HTTPException(422, "The recording is empty.")
    try:
        transcript = await run_in_threadpool(
            gemini.transcribe, cfg, clip, gemini.AUDIO_TYPES[media_type]
        )
    except gemini.PROVIDER_ERRORS:
        raise HTTPException(
            503,
            "Gemini could not transcribe this note. Type your request or try again.",
        ) from None
    if not transcript:
        raise HTTPException(
            422, "I couldn't hear the whole request. Try a shorter note, or type it."
        )
    return {"transcript": transcript}
