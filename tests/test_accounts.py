from io import BytesIO
import sqlite3

import pytest
from PIL import Image
from sqlalchemy import select
from dinex.db import make_engine, migrate, unit
from dinex.models import Staff
from .conftest import ok


def test_registration_approval_and_rejection(world):
    data = world.registration("market-cafe")
    assert ok(world.c.post("/api/register", json=data), 201)["status"] == "pending"
    login = {k: data[k] for k in ("slug", "password")} | {"email": data["owner_email"]}
    assert world.c.post("/api/restaurant/login", json=login).status_code == 403
    pc = world.platform()
    ov = ok(pc.get("/api/platform/overview"))
    assert ov["counts"]["pending"] == 1
    ident = ov["restaurants"][0]["id"]
    ok(pc.put(f"/api/platform/restaurants/{ident}/state", json={"status": "active"}))
    rc = world.login(data["slug"])
    assert ok(rc.get("/api/restaurant/me"))["role"] == "Owner"
    assert rc.get("/api/platform/accounts").status_code == 401
    ok(pc.put(f"/api/platform/restaurants/{ident}/state", json={"status": "suspended"}))
    assert rc.get("/api/restaurant/me").status_code == 401
    second = world.registration("second-cafe")
    ok(world.c.post("/api/register", json=second))
    pending = ok(pc.get("/api/platform/overview"))["restaurants"][0]
    assert (
        ok(
            pc.put(
                f"/api/platform/restaurants/{pending['id']}/state",
                json={"status": "rejected"},
            )
        )["status"]
        == "rejected"
    )


def test_auth_session_csrf_and_safe_errors(world):
    c = world.c
    assert c.get("/api/restaurant/menu").status_code == 401
    assert c.get("/api/platform/overview").status_code == 401
    body = {"email": "test@example.test", "password": "wrong-password"}
    assert c.post("/api/platform/login", json=body).status_code == 401
    body["password"] = world.password
    assert (
        c.post(
            "/api/platform/login", headers={"Origin": "https://example.test"}, json=body
        ).status_code
        == 403
    )
    res = c.post("/api/platform/login", json=body)
    assert (
        "HttpOnly" in res.headers["set-cookie"]
        and "SameSite=strict" in res.headers["set-cookie"]
    )
    assert "password" not in ok(res)
    old = c.cookies["dx_platform"]
    ok(c.post("/api/platform/logout"))
    c.cookies.set("dx_platform", old, path="/api/platform")
    assert c.get("/api/platform/overview").status_code == 401
    error = c.post("/api/register", json={"password": world.password})
    assert error.status_code == 422 and world.password not in error.text


def test_owner_boundaries_and_deactivation(world):
    r = world.restaurant()
    owner = ok(r.c.get("/api/restaurant/me"))["id"]
    assert (
        r.c.put(
            f"/api/restaurant/staff/{owner}", json={"active": False, "role": "Owner"}
        ).status_code
        == 409
    )
    admin, _ = world.member(r, "Admin")
    assert (
        admin.put(
            f"/api/restaurant/staff/{owner}", json={"active": True, "role": "Manager"}
        ).status_code
        == 403
    )
    waiter, uid = world.member(r, "Staff")
    assert waiter.get("/api/restaurant/staff").status_code == 403
    assert waiter.get("/api/restaurant/menu").status_code == 403
    ok(r.c.put(f"/api/restaurant/staff/{uid}", json={"role": "Staff", "active": False}))
    assert waiter.get("/api/restaurant/me").status_code == 401
    bad = world.c.post(
        "/api/restaurant/login",
        json={
            "slug": r.slug,
            "email": "staff@example.test",
            "password": world.password,
        },
    )
    assert bad.status_code == 401
    with unit(world.app.state.engine) as db:
        assert world.password not in db.scalar(select(Staff.password_hash).limit(1))


def test_platform_policy_plans_limits_and_audit(world):
    pc = world.platform()
    ok(pc.put("/api/platform/policy", json={"approval": False}))
    assert (
        ok(world.c.post("/api/register", json=world.registration("mint-house")))[
            "status"
        ]
        == "active"
    )
    ov = ok(pc.get("/api/platform/overview"))
    ident = ov["restaurants"][0]["id"]
    plan = ok(
        pc.post(
            "/api/platform/plans",
            json={
                "name": "Trial",
                "max_tables": 1,
                "max_staff": 1,
                "analytics": False,
                "assistant": False,
                "trial_days": 10,
            },
        )
    )
    assignment = ok(
        pc.put(
            f"/api/platform/restaurants/{ident}/plan",
            json={"plan_id": plan["id"], "subscription": "trial"},
        )
    )
    assert assignment["trial_until"]
    rc = world.login("mint-house")
    ok(rc.post("/api/restaurant/tables", json={"name": "One"}))
    assert rc.post("/api/restaurant/tables", json={"name": "Two"}).status_code == 409
    assert rc.get("/api/restaurant/reports").status_code == 403
    assert any(
        a["action"] == "restaurant.plan" for a in ok(pc.get("/api/platform/audit"))
    )
    assert pc.put("/api/platform/accounts/1", json={"active": False}).status_code == 409


def test_tenant_isolation_and_guest_scope(world, dining):
    a, s, g = dining
    other = world.restaurant("other-room")
    stock = world.stock(other)
    order = world.place(g, s)
    bill = ok(g.post("/api/guest/bills"))
    assert [r["id"] for r in ok(other.c.get("/api/restaurant/menu"))["items"]] == [
        stock.dish["id"]
    ]
    assert (
        ok(other.c.get("/api/restaurant/orders")) == []
        and ok(other.c.get("/api/restaurant/bills")) == []
    )
    assert (
        other.c.put(
            f"/api/restaurant/tables/{s.table}", json={"name": "Elsewhere"}
        ).status_code
        == 404
    )
    assert other.c.post(f"/api/restaurant/tables/{s.table}/qr").status_code == 404
    assert (
        other.c.put(
            f"/api/restaurant/orders/{order['id']}/status", json={"status": "accepted"}
        ).status_code
        == 404
    )
    assert (
        other.c.put(
            f"/api/restaurant/bills/{bill['id']}", json={"status": "accepted"}
        ).status_code
        == 404
    )
    assert (
        other.c.post(
            "/api/restaurant/items", json={**stock.spec, "category_id": s.category}
        ).status_code
        == 404
    )
    assert g.post("/api/guest/orders", json=world.line(stock)).status_code in (409, 422)
    another = world.enter(a, s)
    assert ok(another.get("/api/guest/state"))["orders"] == []
    assert another.post("/api/guest/bills").status_code == 409
    assert g.get("/api/restaurant/orders").status_code == 401


def test_media_validation_and_ownership(world):
    a, b = world.restaurant(), world.restaurant("other-kitchen")
    p = BytesIO()
    Image.new("RGB", (20, 10), "green").save(p, "JPEG")
    headers = {"Content-Type": "application/octet-stream"}
    assert (
        a.c.post(
            "/api/restaurant/images", content=b"plain text", headers=headers
        ).status_code
        == 422
    )
    media = ok(
        a.c.post("/api/restaurant/images", content=p.getvalue(), headers=headers)
    )["url"]
    assert world.c.get(media).status_code == 404
    ok(a.c.put("/api/restaurant/profile", json={"name": "A", "logo": media}))
    assert world.c.get(media).headers["content-type"] == "image/webp"
    assert (
        b.c.put(
            "/api/restaurant/profile", json={"name": "Other", "logo": media}
        ).status_code
        == 422
    )
    assert (
        a.c.post(
            "/api/restaurant/images",
            content=b"x" * (3 * 1024 * 1024 + 1),
            headers=headers,
        ).status_code
        == 413
    )


def test_migration_is_repeatable_and_refuses_foreign_database(world, tmp_path):
    r = world.restaurant()
    migrate(world.app.state.engine)
    assert ok(r.c.get("/api/restaurant/me"))["restaurant"]["id"] == r.id
    path = tmp_path / "other.sqlite"
    with sqlite3.connect(path) as source:
        source.execute("create table inventory (id integer)")
        source.execute("insert into inventory values (17)")
    engine = make_engine(path)
    with pytest.raises(RuntimeError, match="different application"):
        migrate(engine)
    with sqlite3.connect(path) as source:
        assert source.execute("select * from inventory").fetchall() == [(17,)]


def test_auth_rate_limit(world):
    for _ in range(15):
        assert (
            world.c.post(
                "/api/platform/login",
                json={"email": "nobody@example.test", "password": "x"},
            ).status_code
            == 401
        )
    response = world.c.post(
        "/api/platform/login", json={"email": "nobody@example.test", "password": "x"}
    )
    assert response.status_code == 429 and response.headers["retry-after"]
