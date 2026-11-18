from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select, update
from ..catalog import count, create_restaurant, fields
from ..db import add, database
from ..models import (
    Audit,
    DiningTable,
    Login,
    Order,
    Plan,
    PlatformUser,
    Policy,
    Restaurant,
    Staff,
    Visit,
    now,
)
from ..schemas import (
    Assignment,
    Credentials,
    PlanInput,
    PasswordChange,
    PlatformAccount,
    PolicyUpdate,
    Registration,
    RestaurantLogin,
    RestaurantState,
    Toggle,
)
from ..security import (
    audit,
    clear_login,
    employee,
    issue_login,
    password_hash,
    password_ok,
    permissions,
    platform,
)

router = APIRouter(prefix="/api")
PLAN_FIELDS = "id name max_tables max_staff analytics assistant trial_days"


def must(db, cls, ident):
    obj = db.get(cls, ident)
    if obj is None:
        raise HTTPException(404, "Record not found.")
    return obj


def check_password(request, user, password):
    encoded = user.password_hash if user else request.app.state.dummy_hash
    if not password_ok(password, encoded) or not user or not user.active:
        raise HTTPException(401, "Check your sign-in details.")


@router.post("/register", status_code=201)
def register(data: Registration, request: Request, db=Depends(database)):
    request.app.state.limits.hit(request, "register", 8, 300)
    state = "pending" if db.get(Policy, 1).approval else "active"
    r = create_restaurant(db, data, state)
    audit(db, "registration", "restaurant.registered", r.id, tenant=r.id)
    return fields(r, "slug status")


@router.post("/platform/login")
def platform_login(
    data: Credentials, request: Request, response: Response, db=Depends(database)
):
    request.app.state.limits.hit(request, "platform-login", 15, 120)
    u = db.scalar(select(PlatformUser).where(PlatformUser.email == data.email))
    check_password(request, u, data.password)
    issue_login(request, response, db, u, "platform")
    audit(db, u, "platform.login", u.id)
    return fields(u, "id name")


@router.post("/restaurant/login")
def restaurant_login(
    data: RestaurantLogin, request: Request, response: Response, db=Depends(database)
):
    request.app.state.limits.hit(request, "restaurant-login", 24, 120)
    r = db.scalar(select(Restaurant).where(Restaurant.slug == data.slug))
    u = (
        db.scalar(select(Staff).where(Staff.tenant == r.id, Staff.email == data.email))
        if r
        else None
    )
    check_password(request, u, data.password)
    if r.status != "active":
        raise HTTPException(
            403,
            "Restaurant registration or activation is pending. Contact the platform administrator.",
        )
    issue_login(request, response, db, u, "restaurant")
    audit(db, u, "staff.login", u.id)
    return {"role": u.role, "name": u.name}


@router.post("/platform/logout")
def platform_logout(request: Request, response: Response, db=Depends(database)):
    clear_login(request, response, db, "platform")
    return {"signed_out": True}


@router.post("/restaurant/logout")
def restaurant_logout(request: Request, response: Response, db=Depends(database)):
    clear_login(request, response, db, "restaurant")
    return {"signed_out": True}


@router.get("/restaurant/me")
def staff_context(u=Depends(employee), db=Depends(database)):
    r = db.get(Restaurant, u.tenant)
    return {
        **fields(u, "id name role"),
        "permissions": sorted(permissions(u)),
        "restaurant": fields(r, "id slug name currency timezone"),
    }


@router.get("/platform/overview")
def platform_overview(user=Depends(platform), db=Depends(database)):
    restaurants = db.scalars(select(Restaurant).order_by(Restaurant.id.desc())).all()
    return {
        "user": fields(user, "id name email"),
        "approval": db.get(Policy, 1).approval,
        "counts": {
            "restaurants": len(restaurants),
            "active": sum(r.status == "active" for r in restaurants),
            "pending": sum(r.status == "pending" for r in restaurants),
            "orders": count(db, Order),
        },
        "restaurants": [
            fields(
                r, "id name slug status city created owner_name plan_id subscription"
            )
            for r in restaurants
        ],
    }


@router.get("/platform/restaurants/{ident}")
def detail(ident: int, _=Depends(platform), db=Depends(database)):
    r = must(db, Restaurant, ident)
    return {
        **fields(
            r,
            "id name slug status owner_name owner_email contact address city region country plan_id subscription trial_until created",
        ),
        "active_tables": count(
            db, DiningTable, DiningTable.tenant == r.id, DiningTable.active.is_(True)
        ),
        "active_staff": count(db, Staff, Staff.tenant == r.id, Staff.active.is_(True)),
        "orders": count(db, Order, Order.tenant == r.id),
    }


@router.post("/platform/restaurants", status_code=201)
def manual(data: Registration, user=Depends(platform), db=Depends(database)):
    r = create_restaurant(db, data, "active")
    audit(db, user, "restaurant.created", r.id, tenant=r.id)
    return fields(r, "id slug status")


@router.put("/platform/restaurants/{ident}/state")
def set_state(
    ident: int, data: RestaurantState, user=Depends(platform), db=Depends(database)
):
    r = must(db, Restaurant, ident)
    if data.status == "rejected" and r.status != "pending":
        raise HTTPException(409, "Only pending registrations can be rejected.")
    r.status = data.status
    if r.status != "active":
        db.execute(delete(Login).where(Login.tenant == r.id))
        db.execute(update(Visit).where(Visit.tenant == r.id).values(expires=0))
    audit(db, user, "restaurant." + r.status, r.id, tenant=r.id)
    return fields(r, "id status")


@router.put("/platform/policy")
def set_policy(data: PolicyUpdate, user=Depends(platform), db=Depends(database)):
    db.get(Policy, 1).approval = data.approval
    audit(db, user, "policy.approval", 1, str(data.approval))
    return data


@router.get("/platform/plans")
def plans(_=Depends(platform), db=Depends(database)):
    return [fields(p, PLAN_FIELDS) for p in db.scalars(select(Plan).order_by(Plan.id))]


@router.post("/platform/plans", status_code=201)
def create_plan(data: PlanInput, user=Depends(platform), db=Depends(database)):
    p = add(db, Plan, **data.model_dump())
    audit(db, user, "plan.created", p.id)
    return fields(p, PLAN_FIELDS)


@router.put("/platform/restaurants/{ident}/plan")
def assign(ident: int, data: Assignment, user=Depends(platform), db=Depends(database)):
    r, p = must(db, Restaurant, ident), must(db, Plan, data.plan_id)
    if (
        count(db, DiningTable, DiningTable.tenant == r.id, DiningTable.active.is_(True))
        > p.max_tables
        or count(db, Staff, Staff.tenant == r.id, Staff.active.is_(True)) > p.max_staff
    ):
        raise HTTPException(409, "Current restaurant usage exceeds this plan.")
    r.plan_id, r.subscription = p.id, data.subscription
    r.trial_until = (
        now() + 86400 * p.trial_days if data.subscription == "trial" else None
    )
    audit(
        db, user, "restaurant.plan", r.id, f"{p.name} / {r.subscription}", tenant=r.id
    )
    return fields(r, "plan_id subscription trial_until")


@router.get("/platform/accounts")
def accounts(_=Depends(platform), db=Depends(database)):
    return [
        fields(u, "id name email active")
        for u in db.scalars(select(PlatformUser).order_by(PlatformUser.id))
    ]


@router.post("/platform/accounts", status_code=201)
def create_account(data: PlatformAccount, user=Depends(platform), db=Depends(database)):
    u = add(
        db,
        PlatformUser,
        name=data.name,
        email=data.email,
        password_hash=password_hash(data.password),
    )
    audit(db, user, "platform.account_created", u.id)
    return fields(u, "id name email active")


@router.put("/platform/accounts/{ident}")
def toggle(ident: int, data: Toggle, user=Depends(platform), db=Depends(database)):
    u = must(db, PlatformUser, ident)
    if (
        u.active
        and not data.active
        and count(db, PlatformUser, PlatformUser.active.is_(True)) == 1
    ):
        raise HTTPException(409, "Keep at least one active platform administrator.")
    u.active = data.active
    if not u.active:
        db.execute(delete(Login).where(Login.platform_id == u.id))
    audit(db, user, "platform.account_active", u.id, str(u.active))
    return fields(u, "id active")


@router.get("/platform/audit")
def activity(_=Depends(platform), db=Depends(database)):
    logs = db.scalars(select(Audit).order_by(Audit.id.desc()).limit(150))
    return [fields(a, "id tenant actor action entity created") for a in logs]


def change_secret(request, response, db, user, realm, data):
    request.app.state.limits.hit(request, realm + "-password", 10, 120)
    check_password(request, user, data.current)
    if data.current == data.replacement:
        raise HTTPException(422, "Choose a new password.")
    user.password_hash = password_hash(data.replacement)
    matches = (
        Login.platform_id == user.id
        if realm == "platform"
        else ((Login.tenant == user.tenant) & (Login.staff_id == user.id))
    )
    db.execute(delete(Login).where(matches))
    clear_login(request, response, db, realm)
    audit(db, user, realm + ".password_changed", user.id)
    return {"signed_out": True}


@router.post("/platform/password")
def platform_password(
    data: PasswordChange,
    request: Request,
    response: Response,
    u=Depends(platform),
    db=Depends(database),
):
    return change_secret(request, response, db, u, "platform", data)


@router.post("/restaurant/password")
def staff_password(
    data: PasswordChange,
    request: Request,
    response: Response,
    u=Depends(employee),
    db=Depends(database),
):
    return change_secret(request, response, db, u, "restaurant", data)
