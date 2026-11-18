import io
import secrets
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
import qrcode
from sqlalchemy import delete, func, select

from ..catalog import (
    PUBLIC_PROFILE,
    capacity,
    check_images,
    count,
    entitlement,
    fields,
    menu,
    occupancy,
    save_item,
    update,
)
from ..db import add, database, owned, rows
from ..models import (
    Audit,
    Bill,
    Category,
    DiningTable,
    Item,
    Login,
    Order,
    Restaurant,
    Service,
    Staff,
    Visit,
)
from ..ordering import advance_bill, bill_view, kitchen_step, order_view, request_bill
from ..reports import report
from ..schemas import (
    BillStep,
    CategoryInput,
    ItemInput,
    OrderStep,
    Profile,
    QRAction,
    ServiceStep,
    StaffEdit,
    StaffInput,
    TableInput,
)
from ..security import (
    OPTIONAL,
    audit,
    employee,
    password_hash,
    permissions,
    qr_signature,
    require,
)

router = APIRouter(prefix="/api/restaurant")


def setup(db, r):
    cat = count(db, Category, Category.tenant == r.id, Category.active.is_(True))
    dishes = menu(db, r.id, public=True)["items"]
    tables = count(
        db, DiningTable, DiningTable.tenant == r.id, DiningTable.active.is_(True)
    )
    return {
        "Profile": bool(r.contact and r.address and r.city),
        "Branding": bool(r.logo or r.cover),
        "Categories": bool(cat),
        "Menu": any(i["available"] for i in dishes),
        "Tables": bool(tables),
        "QR codes": bool(
            count(
                db,
                DiningTable,
                DiningTable.tenant == r.id,
                DiningTable.active.is_(True),
                DiningTable.qr_enabled.is_(True),
                DiningTable.qr_issued.is_(True),
            )
        ),
        "Staff": count(db, Staff, Staff.tenant == r.id, Staff.active.is_(True)) > 1,
        "Operational settings": "settings" in r.setup_flags,
    }


@router.get("/overview")
def overview(u=Depends(require("overview")), db=Depends(database)):
    r = db.get(Restaurant, u.tenant)
    today = datetime.now(ZoneInfo(r.timezone)).date()
    daily = report(db, r, today, today)
    counts = dict(
        db.execute(
            select(Order.status, func.count())
            .where(Order.tenant == r.id)
            .group_by(Order.status)
        ).all()
    )
    logs = db.scalars(
        select(Audit).where(Audit.tenant == r.id).order_by(Audit.id.desc()).limit(12)
    )
    return {
        "restaurant": fields(r, PUBLIC_PROFILE),
        "onboarding": setup(db, r),
        "counts": {
            "total": sum(counts.values()),
            "new": counts.get("received", 0),
            "active": sum(
                value
                for key, value in counts.items()
                if key not in {"completed", "cancelled"}
            ),
            "ready": counts.get("ready", 0),
            "completed": counts.get("completed", 0),
            "bills": count(db, Bill, Bill.tenant == r.id, Bill.status == "pending"),
        },
        "daily": daily,
        "tables": [
            occupancy(db, t)
            for t in rows(db, DiningTable, r.id, DiningTable.archived.is_(False))
        ],
        "recent": [fields(a, "action actor entity created") for a in logs],
    }


@router.get("/profile")
def profile(u=Depends(require("profile")), db=Depends(database)):
    r = db.get(Restaurant, u.tenant)
    return {**fields(r, PUBLIC_PROFILE), "onboarding": setup(db, r)}


@router.put("/profile")
def edit_profile(
    data: Profile,
    review_settings: bool = True,
    u=Depends(require("profile")),
    db=Depends(database),
):
    r = db.get(Restaurant, u.tenant)
    check_images(db, r.id, data.logo, data.cover)
    if r.currency != data.currency and count(db, Order, Order.tenant == r.id):
        raise HTTPException(409, "Existing orders fix the restaurant currency.")
    update(r, data.model_dump())
    if review_settings and "settings" not in r.setup_flags:
        r.setup_flags = [*r.setup_flags, "settings"]
    audit(db, u, "profile.updated", r.id)
    return fields(r, PUBLIC_PROFILE)


@router.get("/menu")
def catalog(u=Depends(require("menu")), db=Depends(database)):
    return menu(db, u.tenant)


@router.post("/categories", status_code=201)
def new_category(data: CategoryInput, u=Depends(require("menu")), db=Depends(database)):
    c = add(db, Category, tenant=u.tenant, **data.model_dump())
    audit(db, u, "category.created", c.id)
    return fields(c, "id name active")


@router.put("/categories/{ident}")
def edit_category(
    ident: int, data: CategoryInput, u=Depends(require("menu")), db=Depends(database)
):
    c = owned(db, Category, u.tenant, ident)
    update(c, data.model_dump())
    audit(db, u, "category.updated", c.id)
    return fields(c, "id name active")


@router.post("/items", status_code=201)
def new_item(data: ItemInput, u=Depends(require("menu")), db=Depends(database)):
    i = save_item(db, u.tenant, data)
    audit(db, u, "item.created", i.id)
    return fields(i, "id name")


@router.put("/items/{ident}")
def edit_item(
    ident: int, data: ItemInput, u=Depends(require("menu")), db=Depends(database)
):
    i = save_item(db, u.tenant, data, owned(db, Item, u.tenant, ident))
    audit(db, u, "item.updated", i.id)
    return fields(i, "id name")


@router.get("/tables")
def tables(u=Depends(require("tables")), db=Depends(database)):
    return [occupancy(db, t) for t in rows(db, DiningTable, u.tenant)]


@router.post("/tables", status_code=201)
def create_table(data: TableInput, u=Depends(require("tables")), db=Depends(database)):
    if data.active and not data.archived:
        capacity(db, u.tenant, "tables")
    t = add(
        db,
        DiningTable,
        tenant=u.tenant,
        name=data.name,
        active=data.active and not data.archived,
        archived=data.archived,
        qr_nonce=secrets.token_hex(16),
    )
    audit(db, u, "table.created", t.id)
    return occupancy(db, t)


@router.put("/tables/{ident}")
def edit_table(
    ident: int, data: TableInput, u=Depends(require("tables")), db=Depends(database)
):
    t = owned(db, DiningTable, u.tenant, ident)
    if (not data.active or data.archived) and occupancy(db, t)["occupied"]:
        raise HTTPException(
            409, "Complete the outstanding orders and bills before closing this table."
        )
    active = data.active and not data.archived
    if active and not t.active:
        capacity(db, u.tenant, "tables")
    if t.active and not active:
        t.qr_nonce = secrets.token_hex(16)
        t.qr_issued = False
    t.name, t.active, t.archived = data.name, active, data.archived
    audit(db, u, "table.updated", t.id)
    return occupancy(db, t)


@router.post("/tables/{ident}/credential")
def credentials(
    ident: int, data: QRAction, u=Depends(require("tables")), db=Depends(database)
):
    t = owned(db, DiningTable, u.tenant, ident)
    t.qr_issued = False
    t.qr_nonce, t.qr_enabled = secrets.token_hex(16), data.action == "rotate"
    audit(db, u, "qr." + data.action, t.id)
    return fields(t, "id qr_enabled")


def qr_url(db, request, u, ident):
    t = owned(db, DiningTable, u.tenant, ident)
    if not t.active or not t.qr_enabled:
        raise HTTPException(
            409, "Activate the table and generate a current credential."
        )
    cfg, r = request.app.state.cfg, db.get(Restaurant, u.tenant)
    return f"{cfg.public_url}/t/{r.slug}/{t.id}#{qr_signature(cfg, t)}"


@router.post("/tables/{ident}/qr")
def issue_qr(
    ident: int, request: Request, u=Depends(require("tables")), db=Depends(database)
):
    url = qr_url(db, request, u, ident)
    owned(db, DiningTable, u.tenant, ident).qr_issued = True
    audit(db, u, "qr.issued", ident)
    return {"url": url, "image": f"/api/restaurant/tables/{ident}/qr.png"}


@router.get("/tables/{ident}/qr.png")
def qr_image(
    ident: int, request: Request, u=Depends(require("tables")), db=Depends(database)
):
    image = qrcode.make(qr_url(db, request, u, ident))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(
        buffer.getvalue(),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="DineX-table-{ident}.png"'},
    )


@router.get("/staff")
def staff_list(u=Depends(require("staff")), db=Depends(database)):
    return [
        fields(s, "id name email role active grants") for s in rows(db, Staff, u.tenant)
    ]


def check_role(u, role, grants, target=None):
    if not set(grants) <= OPTIONAL[role]:
        raise HTTPException(422, "These grants are unavailable for this role.")
    if u.role == "Admin" and (
        role in {"Owner", "Admin"} or target and target.role in {"Owner", "Admin"}
    ):
        raise HTTPException(403, "Only an owner can manage owners and administrators.")


@router.post("/staff", status_code=201)
def make_staff(data: StaffInput, u=Depends(require("staff")), db=Depends(database)):
    check_role(u, data.role, data.grants)
    capacity(db, u.tenant, "staff")
    s = add(
        db,
        Staff,
        tenant=u.tenant,
        password_hash=password_hash(data.password),
        **data.model_dump(exclude={"password"}),
    )
    audit(db, u, "staff.created", s.id, s.role)
    return fields(s, "id name role")


@router.put("/staff/{ident}")
def edit_staff(
    ident: int, data: StaffEdit, u=Depends(require("staff")), db=Depends(database)
):
    s = owned(db, Staff, u.tenant, ident)
    check_role(u, data.role, data.grants, s)
    if s.role == "Owner" and s.active and (not data.active or data.role != "Owner"):
        if (
            count(
                db,
                Staff,
                Staff.tenant == u.tenant,
                Staff.role == "Owner",
                Staff.active.is_(True),
            )
            <= 1
        ):
            raise HTTPException(409, "Keep at least one active restaurant owner.")
    if not s.active and data.active:
        capacity(db, u.tenant, "staff")
    update(s, data.model_dump())
    db.execute(delete(Login).where(Login.tenant == u.tenant, Login.staff_id == s.id))
    audit(
        db,
        u,
        "staff.updated",
        s.id,
        f"{s.role} / active={s.active} / grants={','.join(s.grants)}",
    )
    return fields(s, "id role active grants")


@router.get("/orders")
def orders(
    before: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    u=Depends(require("orders")),
    db=Depends(database),
):
    query = select(Order).where(Order.tenant == u.tenant)
    if before:
        query = query.where(Order.id < before)
    return [
        order_view(db, o)
        for o in db.scalars(query.order_by(Order.id.desc()).limit(limit))
    ]


@router.get("/kitchen")
def kitchen(u=Depends(require("kitchen")), db=Depends(database)):
    return [
        order_view(db, o, kitchen=True)
        for o in rows(
            db, Order, u.tenant, Order.status.not_in(["completed", "cancelled"])
        )
    ]


@router.put("/orders/{ident}/status")
def order_status(
    ident: int, data: OrderStep, u=Depends(employee), db=Depends(database)
):
    rights = permissions(u)
    if "kitchen" not in rights and not ("orders" in rights and data.status == "served"):
        raise HTTPException(403, "Kitchen permission is required for this stage.")
    o = owned(db, Order, u.tenant, ident)
    kitchen_step(db, u, o, data)
    return fields(o, "id number status")


@router.post("/orders/{ident}/bill")
def staff_bill(ident: int, u=Depends(require("checkout")), db=Depends(database)):
    o = owned(db, Order, u.tenant, ident)
    v = owned(db, Visit, u.tenant, o.visit_id)
    return bill_view(db, request_bill(db, v, u))


@router.get("/bills")
def bills(
    status: str | None = None,
    before: int | None = None,
    limit: int = Query(50, ge=1, le=100),
    u=Depends(require("checkout")),
    db=Depends(database),
):
    query = select(Bill).where(Bill.tenant == u.tenant)
    if status:
        query = query.where(Bill.status == status)
    if before:
        query = query.where(Bill.id < before)
    return [
        bill_view(db, b)
        for b in db.scalars(query.order_by(Bill.id.desc()).limit(limit))
    ]


@router.get("/bills/pending-count")
def pending_bills(u=Depends(require("checkout")), db=Depends(database)):
    return {
        "count": count(db, Bill, Bill.tenant == u.tenant, Bill.status == "pending"),
        "latest": db.scalar(
            select(Bill.id)
            .where(Bill.tenant == u.tenant, Bill.status == "pending")
            .order_by(Bill.id.desc())
            .limit(1)
        )
        or 0,
    }


@router.put("/bills/{ident}")
def bill_step(
    ident: int, data: BillStep, u=Depends(require("checkout")), db=Depends(database)
):
    b = owned(db, Bill, u.tenant, ident)
    advance_bill(db, u, b, data)
    return bill_view(db, b)


@router.get("/services")
def service_list(u=Depends(require("service")), db=Depends(database)):
    return [
        {
            **fields(s, "id kind status created note"),
            "table": owned(db, DiningTable, u.tenant, s.table_id).name,
        }
        for s in reversed(rows(db, Service, u.tenant))
    ]


@router.put("/services/{ident}")
def service_step(
    ident: int, data: ServiceStep, u=Depends(require("service")), db=Depends(database)
):
    s = owned(db, Service, u.tenant, ident)
    if (
        s.status != data.status
        and {"open": "accepted", "accepted": "resolved"}.get(s.status) != data.status
    ):
        raise HTTPException(409, "This service transition is unavailable.")
    s.status = data.status
    audit(db, u, "service." + data.status, s.id)
    return fields(s, "id status")


@router.get("/reports")
def reports(
    start: date | None = None,
    end: date | None = None,
    u=Depends(require("reports")),
    db=Depends(database),
):
    entitlement(db, u.tenant, "analytics")
    return report(db, db.get(Restaurant, u.tenant), start, end)


@router.get("/audit")
def logs(u=Depends(require("audit")), db=Depends(database)):
    records = db.scalars(
        select(Audit)
        .where(Audit.tenant == u.tenant)
        .order_by(Audit.id.desc())
        .limit(150)
    )
    return [fields(a, "id actor action entity detail created") for a in records]
