from datetime import datetime
from zoneinfo import ZoneInfo
from .conftest import ok


def action(c, bill, status, **extra):
    return c.put(
        "/api/restaurant/bills/" + str(bill["id"]), json={"status": status, **extra}
    )


def serve(c, order):
    for status in ("accepted", "preparing", "ready", "served"):
        ok(
            c.put(
                f"/api/restaurant/orders/{order['id']}/status", json={"status": status}
            )
        )


def test_checkout_end_to_end_two_guests_three_orders(world, dining):
    r, s, g = dining
    second = world.enter(r, s)
    one, two, other = world.place(g, s), world.place(g, s), world.place(second, s)
    assert g.headers["Authorization"] != second.headers["Authorization"]
    b = ok(g.post("/api/guest/bills"))
    assert {o["id"] for o in b["orders"]} == {one["id"], two["id"]} and b[
        "total"
    ] == 4504
    assert ok(g.post("/api/guest/bills"))["id"] == b["id"]
    assert g.post("/api/guest/orders", json=world.line(s)).status_code == 409
    assert ok(r.c.get("/api/restaurant/bills/pending-count"))["count"] == 1
    assert action(r.c, b, "paid", method="cash", confirmed=True).status_code == 409
    kitchen, _ = world.member(r, "Kitchen")
    assert kitchen.get("/api/restaurant/bills").status_code == 403
    ticket = ok(kitchen.get("/api/restaurant/kitchen"))[0]
    assert "total" not in ticket and ticket["lines"][0]["note"] == "Sauce on side"
    assert (
        kitchen.put(
            f"/api/restaurant/orders/{one['id']}/status", json={"status": "ready"}
        ).status_code
        == 409
    )
    serve(kitchen, one)
    assert ok(g.get("/api/guest/state"))["bills"][0]["payment_status"] == "pending"
    ok(action(r.c, b, "accepted"))
    assert (
        action(r.c, b, "prepared", discount=999999, reason="Courtesy").status_code
        == 422
    )
    prepared = ok(
        action(
            r.c,
            b,
            "prepared",
            discount=100,
            adjustment=25,
            reason="Approved service adjustment",
        )
    )
    assert prepared["total"] == 4429 and prepared["payment"] is None
    ok(action(r.c, b, "awaiting_payment"))
    staff, uid = world.member(r, "Staff")
    assert action(staff, b, "paid", method="upi", confirmed=True).status_code == 403
    assert action(r.c, b, "paid", method="upi").status_code == 422
    ok(
        r.c.put(
            f"/api/restaurant/staff/{uid}",
            json={"role": "Staff", "active": True, "grants": ["payment"]},
        )
    )
    staff = world.login(r.slug, "staff@example.test")
    paid = ok(
        action(staff, b, "paid", method="upi", confirmed=True, reference="TEST-REC")
    )
    assert paid["payment"]["amount"] == 4429
    assert (
        ok(action(staff, b, "paid", method="upi", confirmed=True))["payment"]["amount"]
        == 4429
    )
    assert action(r.c, b, "completed").status_code == 409
    serve(kitchen, two)
    ok(action(r.c, b, "completed"))
    assert ok(g.get("/api/guest/state"))["closed"] is True
    assert ok(r.c.get("/api/restaurant/tables"))[0]["occupied"] is True
    assert [o["id"] for o in ok(second.get("/api/guest/state"))["orders"]] == [
        other["id"]
    ]
    next_bill = ok(r.c.post(f"/api/restaurant/orders/{other['id']}/bill"))
    serve(kitchen, other)
    for step in ("accepted", "prepared", "awaiting_payment"):
        ok(action(r.c, next_bill, step))
    ok(action(r.c, next_bill, "paid", method="cash", confirmed=True))
    ok(action(r.c, next_bill, "completed"))
    assert not ok(r.c.get("/api/restaurant/tables"))[0]["occupied"]
    report = ok(r.c.get("/api/restaurant/reports"))
    assert report["gross"] == 6756 and report["paid"] == 6681 and report["orders"] == 3
    assert report["pending_payments"] == 0 and report["popular"] == {
        "Roast cauliflower": 6
    }
    log = ok(r.c.get("/api/restaurant/audit"))
    assert {"bill.adjusted", "bill.paid", "bill.completed"} <= {
        row["action"] for row in log
    }
    customer_bill = ok(g.get("/api/guest/state"))["bills"][0]
    assert (
        "reference" not in customer_bill["payment"]
        and customer_bill["status"] == "completed"
    )


def test_cancelled_bill_reopens_orders_and_preserves_evidence(world, dining):
    r, s, g = dining
    o = world.place(g, s)
    b = ok(g.post("/api/guest/bills"))
    assert action(r.c, b, "cancelled").status_code == 409
    ok(action(r.c, b, "cancelled", reason="Guest wants another course"))
    world.place(g, s)
    b2 = ok(g.post("/api/guest/bills"))
    assert len(b2["orders"]) == 2 and b2["id"] != b["id"]
    original = [x for x in ok(r.c.get("/api/restaurant/bills")) if x["id"] == b["id"]][
        0
    ]
    assert original["orders"][0]["id"] == o["id"] and len(original["orders"]) == 1


def test_cancelled_order_and_date_reports(world, dining):
    r, s, g = dining
    o = world.place(g, s)
    ok(
        r.c.put(
            f"/api/restaurant/orders/{o['id']}/status",
            json={"status": "cancelled", "reason": "Guest changed request"},
        )
    )
    assert g.post("/api/guest/bills").status_code == 409
    assert not ok(r.c.get("/api/restaurant/tables"))[0]["occupied"]
    report = ok(r.c.get("/api/restaurant/reports"))
    assert (
        report["cancelled_orders"] == 1
        and report["orders"] == 0
        and report["gross"] == 0
    )
    assert (
        r.c.get("/api/restaurant/reports?start=2023-01-03&end=2023-01-01").status_code
        == 422
    )
    assert ok(r.c.get("/api/restaurant/reports?start=2001-10-10&end=2001-10-10"))[
        "days"
    ] == [{"date": "2001-10-10", "orders": 0, "paid": 0}]


def test_manager_adjustment_permission_is_independent(world, dining):
    r, s, g = dining
    world.place(g, s)
    b = ok(g.post("/api/guest/bills"))
    m, _ = world.member(r, "Manager")
    ok(action(m, b, "accepted"))
    assert action(m, b, "prepared", discount=25, reason="Approved").status_code == 403
    ok(action(m, b, "prepared"))
    assert ok(g.get("/api/guest/state"))["bills"][0]["payment_status"] == "pending"


def test_receipt_date_and_order_date_are_independent(world, dining):
    from dinex.db import unit
    from dinex.models import Order, Payment

    r, s, g = dining
    o = world.place(g, s)
    b = ok(g.post("/api/guest/bills"))
    for step in ("accepted", "prepared", "awaiting_payment"):
        ok(action(r.c, b, step))
    ok(action(r.c, b, "paid", method="card", confirmed=True))
    zone = ZoneInfo("Asia/Kolkata")
    with unit(world.app.state.engine, True) as db:
        db.get(Order, o["id"]).created = int(
            datetime(2024, 5, 1, 23, 59, tzinfo=zone).timestamp()
        )
        p = db.query(Payment).filter_by(bill_id=b["id"]).one()
        p.created = int(datetime(2024, 5, 2, 0, 1, tzinfo=zone).timestamp())
    first = ok(r.c.get("/api/restaurant/reports?start=2024-05-01&end=2024-05-01"))
    second = ok(r.c.get("/api/restaurant/reports?start=2024-05-02&end=2024-05-02"))
    assert (first["orders"], first["paid"], second["orders"], second["paid"]) == (
        1,
        0,
        0,
        2252,
    )
