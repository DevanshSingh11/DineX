import hashlib
import hmac
import secrets
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select

from .db import add, database
from .models import Audit, Login, PlatformUser, Restaurant, Staff, Visit, now

BASE = {
    "Owner": {
        "overview",
        "profile",
        "staff",
        "menu",
        "tables",
        "orders",
        "kitchen",
        "service",
        "checkout",
        "payment",
        "adjust",
        "reports",
        "audit",
    },
    "Admin": {
        "overview",
        "staff",
        "menu",
        "tables",
        "orders",
        "kitchen",
        "service",
        "checkout",
        "payment",
        "adjust",
        "reports",
        "audit",
    },
    "Manager": {"overview", "orders", "kitchen", "service", "checkout", "reports"},
    "Kitchen": {"kitchen"},
    "Staff": {"orders", "service", "checkout"},
}
OPTIONAL = {
    "Manager": {"payment", "adjust"},
    "Staff": {"payment"},
    "Owner": set(),
    "Admin": set(),
    "Kitchen": set(),
}


def permissions(staff):
    return BASE[staff.role] | (set(staff.grants) & OPTIONAL[staff.role])


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    result = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt),
        n=32768,
        r=8,
        p=3,
        dklen=32,
        maxmem=96 * 1024 * 1024,
    )
    return "scrypt-v1$" + salt + "$" + result.hex()


def password_ok(password, encoded):
    _, salt, _ = encoded.split("$")
    return hmac.compare_digest(encoded, password_hash(password, salt))


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def qr_signature(cfg, table):
    message = f"table:{table.tenant}:{table.id}:{table.qr_nonce}".encode()
    return hmac.new(cfg.secret.encode(), message, hashlib.sha256).hexdigest()


def audit(db, actor, action, obj, detail="", tenant=None):
    if isinstance(actor, Staff):
        tenant, who = actor.tenant, f"staff/{actor.id}"
    elif isinstance(actor, PlatformUser):
        who = f"platform/{actor.id}"
    elif isinstance(actor, Visit):
        tenant, who = actor.tenant, f"visit/{actor.id}"
    else:
        who = str(actor)
    db.add(
        Audit(tenant=tenant, actor=who, action=action, entity=str(obj), detail=detail)
    )


class Limits:
    def __init__(self):
        self.buckets = OrderedDict()
        self.lock = Lock()

    def hit(self, request, action, maximum, seconds=60):
        host = request.client.host if request.client else "local"
        key = (host, action)
        stamp = monotonic()
        with self.lock:
            bucket = self.buckets.setdefault(key, deque())
            self.buckets.move_to_end(key)
            while bucket and stamp - bucket[0] >= seconds:
                bucket.popleft()
            if len(bucket) >= maximum:
                raise HTTPException(
                    429,
                    "Too many requests. Please try again shortly.",
                    headers={"Retry-After": str(seconds)},
                )
            bucket.append(stamp)
            if len(self.buckets) > 20000:
                self.buckets.popitem(last=False)


def issue_login(request: Request, response: Response, db, user, realm):
    raw = secrets.token_urlsafe(36)
    db.execute(delete(Login).where(Login.expires < now()))
    old = request.cookies.get("dx_" + realm)
    if old:
        db.execute(delete(Login).where(Login.digest == digest(old)))
    fields = (
        {"platform_id": user.id}
        if realm == "platform"
        else {"tenant": user.tenant, "staff_id": user.id}
    )
    add(db, Login, digest=digest(raw), expires=now() + 43200, **fields)
    response.set_cookie(
        "dx_" + realm,
        raw,
        max_age=43200,
        httponly=True,
        samesite="strict",
        secure=request.app.state.cfg.secure_cookies,
        path="/api/" + realm,
    )


def clear_login(request, response, db, realm):
    raw = request.cookies.get("dx_" + realm, "")
    db.execute(delete(Login).where(Login.digest == digest(raw)))
    response.delete_cookie("dx_" + realm, path="/api/" + realm)


def identify(request, db, realm):
    raw = request.cookies.get("dx_" + realm, "")
    login = db.scalar(
        select(Login).where(Login.digest == digest(raw), Login.expires > now())
    )
    user = None
    if login and realm == "platform" and login.platform_id:
        user = db.get(PlatformUser, login.platform_id)
    if login and realm == "restaurant" and login.staff_id:
        user = db.scalar(
            select(Staff).where(
                Staff.id == login.staff_id, Staff.tenant == login.tenant
            )
        )
        if db.get(Restaurant, login.tenant).status != "active":
            user = None
    if not user or not user.active:
        raise HTTPException(401, "Sign in to an active account.")
    return user


def platform(request: Request, db=Depends(database)):
    return identify(request, db, "platform")


def employee(request: Request, db=Depends(database)):
    return identify(request, db, "restaurant")


def require(permission):
    def check(user=Depends(employee)):
        if permission not in permissions(user):
            raise HTTPException(403, "Your role does not have this permission.")
        return user

    return check


def guest(request: Request, db=Depends(database)):
    scheme, _, raw = request.headers.get("Authorization", "").partition(" ")
    visit = (
        db.scalar(
            select(Visit).where(Visit.digest == digest(raw), Visit.expires > now())
        )
        if scheme == "Bearer"
        else None
    )
    if not visit or db.get(Restaurant, visit.tenant).status != "active":
        raise HTTPException(401, "Your table session expired. Scan the table QR again.")
    return visit
