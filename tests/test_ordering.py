from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
import pytest
from .conftest import ok


def test_authoritative_price_snapshot_and_history(world, dining):
    r, s, g = dining
    ok(
        r.c.put(
            "/api/restaurant/profile",
            json={"name": "Green Leaf", "tax_bps": 500, "charge_bps": 250},
        )
    )
    order = world.place(g, s)
    assert (order["subtotal"], order["tax"], order["charges"], order["total"]) == (
        2252,
        113,
        56,
        2421,
    )
    assert order["lines"][0]["selections"][0]["name"] == "Large"
    ok(
        r.c.put(
            "/api/restaurant/items/" + str(s.dish["id"]),
            json={**s.spec, "name": "Autumn plate", "price": 2000},
        )
    )
    history = ok(g.get("/api/guest/state"))["orders"][0]
    assert (
        history["lines"][0]["name"] == "Roast cauliflower" and history["total"] == 2421
    )
    assert g.post("/api/guest/orders", json=world.line(s)).status_code == 422
    assert (
        r.c.put(
            "/api/restaurant/profile", json={"name": "Green Leaf", "currency": "EUR"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "failure",
    [
        "missing_item",
        "required_group",
        "duplicate_choice",
        "extra_choice",
        "over_max",
        "wrong_price",
        "zero_quantity",
        "unavailable",
        "archived_category",
    ],
)
def test_order_validation(world, dining, failure):
    r, s, g = dining
    data = world.line(s)
    line = data["lines"][0]
    if failure == "missing_item":
        line["item_id"] = 999999
    elif failure == "required_group":
        line["options"] = []
    elif failure == "duplicate_choice":
        line["options"] *= 2
    elif failure == "extra_choice":
        line["options"].append(999999)
    elif failure == "over_max":
        line["options"].append(s.dish["groups"][0]["options"][0]["id"])
    elif failure == "wrong_price":
        line["unit_price"] = 1
    elif failure == "zero_quantity":
        line["quantity"] = 0
    elif failure == "unavailable":
        ok(
            r.c.put(
                "/api/restaurant/items/" + str(s.dish["id"]),
                json={**s.spec, "available": False},
            )
        )
    elif failure == "archived_category":
        ok(
            r.c.put(
                "/api/restaurant/categories/" + str(s.category),
                json={"name": "Mains", "active": False},
            )
        )
    assert g.post("/api/guest/orders", json=data).status_code == 422
    assert ok(r.c.get("/api/restaurant/orders")) == []


def test_concurrent_order_and_bill_retries(world, dining):
    r, s, g = dining
    data = world.line(s)

    def submit(_):
        c = world.http()
        c.headers["Authorization"] = g.headers["Authorization"]
        return ok(c.post("/api/guest/orders", json=data))["id"]

    def bill(_):
        c = world.http()
        c.headers["Authorization"] = g.headers["Authorization"]
        return ok(c.post("/api/guest/bills"))["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert len(set(pool.map(submit, range(4)))) == 1
        assert len(set(pool.map(bill, range(4)))) == 1
    data["lines"][0]["quantity"] = 3
    assert g.post("/api/guest/orders", json=data).status_code == 409
    assert (
        len(ok(r.c.get("/api/restaurant/bills")))
        == len(ok(r.c.get("/api/restaurant/orders")))
        == 1
    )


def test_qr_rotation_revoke_and_existing_receipt(world, dining):
    r, s, g = dining
    world.place(g, s)
    qr = f"/api/restaurant/tables/{s.table}/"
    assert r.c.get(qr + "qr.png").content.startswith(b"\x89PNG")
    old = urlsplit(s.url).fragment
    ok(r.c.post(qr + "credential", json={"action": "rotate"}))
    assert (
        world.c.post(
            "/api/guest/enter/" + r.slug, json={"table_id": s.table, "credential": old}
        ).status_code
        == 404
    )
    assert g.post("/api/guest/orders", json=world.line(s)).status_code == 409
    assert ok(g.post("/api/guest/bills"))["status"] == "pending"
    ok(r.c.post(qr + "credential", json={"action": "revoke"}))
    assert r.c.post(qr + "qr").status_code == 409
    assert (
        r.c.put(
            "/api/restaurant/tables/" + str(s.table),
            json={"name": "One", "active": False},
        ).status_code
        == 409
    )


def test_service_and_grounded_assistant(world, dining):
    r, s, g = dining
    a = ok(g.post("/api/guest/services", json={"kind": "water", "note": "One glass"}))
    assert ok(g.post("/api/guest/services", json={"kind": "water"}))["id"] == a["id"]
    path = "/api/restaurant/services/" + str(a["id"])
    assert r.c.put(path, json={"status": "resolved"}).status_code == 409
    ok(r.c.put(path, json={"status": "accepted"}))
    ok(r.c.put(path, json={"status": "resolved"}))
    assert ok(g.get("/api/guest/state"))["services"][0]["status"] == "resolved"
    msg = ok(
        g.post("/api/guest/assistant", json={"question": "Which vegetarian dishes?"})
    )
    assert msg["mode"] == "local menu guide" and [i["id"] for i in msg["items"]] == [
        s.dish["id"]
    ]
    allergy = ok(
        g.post(
            "/api/guest/assistant",
            json={"question": "Is this safe for a peanut allergy?"},
        )
    )
    assert not allergy["items"] and "staff" in allergy["message"]
    ok(
        r.c.put(
            "/api/restaurant/items/" + str(s.dish["id"]),
            json={**s.spec, "available": False},
        )
    )
    assert (
        ok(g.post("/api/guest/assistant", json={"question": "Cauliflower"}))["items"]
        == []
    )
