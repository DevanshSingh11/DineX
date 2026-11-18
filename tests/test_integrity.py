import secrets
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy.exc import IntegrityError

from dinex.db import add, unit
from dinex.models import Item
from .conftest import ok


def test_browser_headers_and_missing_csrf_header(world):
    response = world.c.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert world.c.get("/api/guest/state").headers["cache-control"] == "no-store"
    client = world.http()
    del client.headers["X-DineX"]
    assert (
        client.post("/api/register", json=world.registration("no-header")).status_code
        == 403
    )


def test_composite_foreign_key_rejects_cross_tenant_relationship(world, dining):
    r, stock, _ = dining
    other = world.restaurant("acacia")
    with pytest.raises(IntegrityError):
        with unit(world.app.state.engine, True) as db:
            add(
                db,
                Item,
                tenant=other.id,
                category_id=stock.category,
                name="Wrong category",
                price=1,
            )
    assert ok(other.c.get("/api/restaurant/menu"))["items"] == []
    assert len(ok(r.c.get("/api/restaurant/menu"))["items"]) == 1


@pytest.mark.parametrize("realm", ["platform", "restaurant"])
def test_password_change_invalidates_other_logins(world, realm):
    if realm == "platform":
        c = world.platform()
        second = world.platform()
        path = "overview"
        login = {"email": "test@example.test"}
    else:
        r = world.restaurant()
        c, second = r.c, world.login(r.slug)
        path = "me"
        login = {"email": "owner@example.test", "slug": r.slug}
    base = "/api/" + realm + "/"
    new = secrets.token_urlsafe(24)
    assert (
        c.post(
            base + "password", json={"current": "incorrect", "replacement": new}
        ).status_code
        == 401
    )
    ok(c.post(base + "password", json={"current": world.password, "replacement": new}))
    assert second.get(base + path).status_code == 401
    assert (
        c.post(base + "login", json={**login, "password": world.password}).status_code
        == 401
    )
    ok(c.post(base + "login", json={**login, "password": new}))
    ok(c.get(base + path))


def test_race_between_bill_and_another_order(world, dining):
    r, s, g = dining
    world.place(g, s)
    data = world.line(s)

    def attempt(path, body):
        client = world.http()
        client.headers["Authorization"] = g.headers["Authorization"]
        return client.post("/api/guest/" + path, json=body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        request = pool.submit(attempt, "bills", None)
        placement = pool.submit(attempt, "orders", data)
    b = ok(request.result())
    submission = placement.result()
    assert submission.status_code in (201, 409)
    state = ok(g.get("/api/guest/state"))
    assert len(state["orders"]) == (2 if submission.status_code == 201 else 1)
    assert len(b["orders"]) == len(state["orders"])
    assert all(o["bill_id"] == b["id"] for o in state["orders"])


def test_onboarding_reflects_current_qr_and_explicit_settings(world, dining):
    r, s, _ = dining
    base = "/api/restaurant"
    assert ok(r.c.get(base + "/profile"))["onboarding"]["QR codes"]
    ok(r.c.post(f"{base}/tables/{s.table}/credential", json={"action": "revoke"}))
    assert not ok(r.c.get(base + "/profile"))["onboarding"]["QR codes"]
    ok(r.c.put(base + "/profile?review_settings=false", json={"name": "A new name"}))
    assert not ok(r.c.get(base + "/profile"))["onboarding"]["Operational settings"]


def test_expired_visit_can_be_recovered_by_authorized_staff(world, dining):
    from dinex.models import Visit

    r, s, g = dining
    order = world.place(g, s)
    with unit(world.app.state.engine, True) as db:
        db.get(Visit, order["visit_id"]).expires = 0
    assert g.get("/api/guest/state").status_code == 401
    bill = ok(r.c.post("/api/restaurant/orders/" + str(order["id"]) + "/bill"))
    assert [o["id"] for o in bill["orders"]] == [order["id"]]


def test_kitchen_and_floor_permissions_and_order_pagination(world, dining):
    r, s, g = dining
    first, second = world.place(g, s), world.place(g, s)
    staff, _ = world.member(r, "Staff")
    base = "/api/restaurant/orders"
    assert [o["id"] for o in ok(staff.get(base + "?limit=1"))] == [second["id"]]
    assert [
        o["id"] for o in ok(staff.get(base + f"?before={second['id']}&limit=1"))
    ] == [first["id"]]
    path = base + f"/{first['id']}/status"
    assert staff.put(path, json={"status": "preparing"}).status_code == 403
    for stage in ["accepted", "preparing", "ready"]:
        ok(r.c.put(path, json={"status": stage}))
    assert ok(staff.put(path, json={"status": "served"}))["status"] == "served"


def test_assistant_respects_tenant_plan_and_allows_only_current_dishes(world, dining):
    a, s, g = dining
    b = world.restaurant("other-menu")
    bs = world.stock(b)
    # Both test restaurants sell the same named dish. Their IDs and recorded menus differ.
    assert g.post("/api/guest/orders", json=world.line(bs)).status_code == 422
    result = ok(
        g.post(
            "/api/guest/assistant",
            json={"question": "What vegetarian dishes do you have?"},
        )
    )
    assert [x["id"] for x in result["items"]] == [s.dish["id"]]
    p = world.platform()
    plan = ok(p.post("/api/platform/plans", json={"name": "Core", "assistant": False}))
    ok(p.put(f"/api/platform/restaurants/{a.id}/plan", json={"plan_id": plan["id"]}))
    assert (
        g.post(
            "/api/guest/assistant", json={"question": "Vegetarian dishes"}
        ).status_code
        == 403
    )


def test_qr_input_error_and_atomic_order_failure(world, dining):
    r, s, g = dining
    assert (
        world.c.post(
            "/api/guest/enter/" + r.slug,
            json={"table_id": s.table, "credential": "æ" * 64},
        ).status_code
        == 422
    )
    data = world.line(s)
    data["lines"].append({"item_id": 999999, "quantity": 1})
    assert g.post("/api/guest/orders", json=data).status_code == 422
    assert ok(r.c.get("/api/restaurant/orders")) == []
