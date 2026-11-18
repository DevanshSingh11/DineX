"""Regression checks for allergy filtering, optional Gemini, and the bundled first restaurant."""

from dataclasses import replace
from pathlib import Path

import httpx
from sqlalchemy import select

from dinex import gemini
from dinex.assistant import answer
from dinex.catalog import menu
from dinex.config import Config
from dinex.db import make_engine, migrate, unit
from dinex.demo import install_demo
from dinex.models import Category, DiningTable, Item, Restaurant, Staff
from .conftest import ok


CFG = Config(Path("unused"), "x" * 48)


def recipe(id_, name, **updates):
    return dict(
        {
            "id": id_,
            "name": name,
            "available": True,
            "featured": False,
            "price": 12000,
            "category_id": 9,
            "dietary": "vegan",
            "description": "",
            "ingredients": "Rice, lime",
            "recipe_status": "reviewed",
            "allergens": [],
            "may_contain": [],
            "groups": [],
        },
        **updates,
    )


def test_allergy_confirmation_excludes_traces_options_and_missing_records():
    items = [
        recipe(1, "Lime ice"),
        recipe(2, "Peanut ice", allergens=["peanut"]),
        recipe(3, "Vanilla ice", may_contain=["peanut"]),
        recipe(4, "Old recipe", recipe_status="unreviewed"),
        recipe(5, "House scoop", groups=[{"options": [{"name": "Peanut crumble"}]}]),
        recipe(6, "Egg custard", ingredients="Egg, sugar"),
        recipe(7, "Sold out", available=False),
        recipe(8, "Undocumented", ingredients=""),
    ]
    menu_ = {"items": items, "categories": [{"id": 9, "name": "Desserts"}]}
    q = "I have a peanut allergy and can't eat eggs. Show me desserts."
    first = answer(CFG, q, menu_)
    assert (
        first["needs_confirmation"]
        and not first["items"]
        and set(first["avoid"]) == {"peanut", "egg"}
    )
    assert not answer(CFG, q, menu_, ["peanut"], confirmed=True)["items"]
    final = answer(CFG, q, menu_, first["avoid"], confirmed=True)
    assert [i["id"] for i in final["items"]] == [1] and final["ask_staff"]
    assert answer(CFG, "I'm allergic to kiwi and peanuts.", menu_, ["peanut"], True)[
        "unresolved"
    ]
    assert answer(CFG, "What can I eat with a kiwi allergy?", menu_)["items"] == []
    assert (
        answer(
            CFG,
            "I'm allergic to peanuts. Can I have Peanut ice?",
            menu_,
            ["peanut"],
            True,
        )["items"]
        == []
    )


def test_seed_survives_restart_and_searches_entire_menu(tmp_path):
    engine = make_engine(tmp_path / "demo.sqlite3")
    migrate(engine)
    assert "128 dishes" in install_demo(engine, only_if_empty=True)
    with unit(engine, True) as db:
        r = db.scalars(select(Restaurant)).one()
        assert (r.slug, r.status, r.currency) == ("saffron-courtyard", "active", "INR")
        catalog = menu(db, r.id, True)
        assert len(catalog["items"]) == 128 and len(catalog["categories"]) == 16
        assert len(db.scalars(select(DiningTable)).all()) == 8
        desserts = answer(
            CFG, "मुझे मूंगफली से एलर्जी है। मिठाई दिखाओ।", catalog, ["peanut"], True
        )
        assert desserts["items"] and all(
            "peanut" not in i["may_contain"] + i["allergens"] for i in desserts["items"]
        )
        assert any(
            i["name"] == "Iced Badam Milk"
            for i in answer(CFG, "What goes into Iced Badam Milk?", catalog)["items"]
        )
        indian = answer(
            CFG, "I'm allergic to peanuts. Show me desserts.", catalog, ["peanut"], True
        )
        assert {i["id"] for i in desserts["items"]} == {
            i["id"] for i in indian["items"]
        }
        all_food = answer(CFG, "I'm allergic to peanuts.", catalog, ["peanut"], True)
        assert len(all_food["items"]) > 50
        assert all(
            i["price"] < 16500
            for i in answer(CFG, "vegan desserts under ₹165", catalog)["items"]
        )
        db.scalars(select(Staff)).one().name = "Changed owner"
        first = db.scalars(select(Item).order_by(Item.id)).first()
        first.available = False
    install_demo(engine)
    with unit(engine) as db:
        assert db.scalars(select(Staff)).one().name == "Changed owner"
        assert not db.scalars(select(Item).order_by(Item.id)).first().available
    engine.dispose()


def test_v1_migration_preserves_items_and_marks_records_unreviewed(world, dining):
    r, stock, _ = dining
    engine = world.app.state.engine
    with engine.begin() as con:
        for column in ("recipe_status", "allergens", "may_contain"):
            con.exec_driver_sql(f"ALTER TABLE items DROP COLUMN {column}")
        con.exec_driver_sql("PRAGMA user_version=1")
    migrate(engine)
    migrate(engine)
    with unit(engine) as db:
        item = db.get(Item, stock.dish["id"])
        assert item.name == stock.dish["name"] and item.price == stock.spec["price"]
        assert (
            item.recipe_status == "unreviewed"
            and item.allergens == []
            and item.may_contain == []
        )
        assert db.get(Category, item.category_id).tenant == r.id


def test_gemini_translation_cannot_supply_menu_facts_or_relax_original_budget(
    monkeypatch,
):
    cfg = replace(CFG, gemini_key="provider-test")

    def interpret(url, **opts):
        assert url.startswith("https://generativelanguage.googleapis.com/")
        assert opts["headers"] == {"x-goog-api-key": "provider-test"}
        assert "provider-test" not in str(opts["json"])
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"search":"desserts", "restriction":false, "avoid":[], "needs_staff":false, "price":1}'
                                }
                            ]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", interpret)
    m = {
        "items": [recipe(1, "Lime ice"), recipe(2, "Expensive", price=41000)],
        "categories": [{"id": 9, "name": "Desserts"}],
    }
    r = answer(cfg, "Desserts under ₹150", m)
    assert r["mode"] == "Gemini" and [(i["id"], i["price"]) for i in r["items"]] == [
        (1, 12000)
    ]
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    r = answer(cfg, "Lime ice", m)
    assert "unavailable" in r["mode"] and r["items"][0]["id"] == 1


def test_audio_is_visit_and_plan_scoped_and_never_orders(world, dining, monkeypatch):
    r, _, guest = dining
    path = "/api/guest/assistant/transcribe"
    headers = {"Content-Type": "audio/wav"}
    assert world.http().post(path, content=b"clip", headers=headers).status_code == 401
    assert guest.post(path, content=b"clip", headers=headers).status_code == 503
    world.app.state.cfg = replace(world.app.state.cfg, gemini_key="only-on-server")

    def fake(cfg, clip, mime):
        assert clip == b"clip" and mime == "audio/wav"
        return "I am allergic to peanuts."

    monkeypatch.setattr(gemini, "transcribe", fake)
    assert ok(guest.post(path, content=b"clip", headers=headers)) == {
        "transcript": "I am allergic to peanuts."
    }
    assert (
        guest.post(
            path, content=b"clip", headers={"Content-Type": "text/plain"}
        ).status_code
        == 415
    )
    assert (
        guest.post(
            path, content=b"x" * (gemini.AUDIO_LIMIT + 1), headers=headers
        ).status_code
        == 413
    )
    assert "only-on-server" not in guest.get("/api/guest/menu").text
    assert ok(guest.get("/api/guest/state"))["orders"] == []
    p = world.platform()
    plan = ok(
        p.post("/api/platform/plans", json={"name": "No voices", "assistant": False})
    )
    ok(p.put(f"/api/platform/restaurants/{r.id}/plan", json={"plan_id": plan["id"]}))
    assert guest.post(path, content=b"clip", headers=headers).status_code == 403
    assert not ok(guest.get("/api/guest/menu"))["guide"]["enabled"]


def test_new_ingredient_question_reaches_staff_while_previous_one_is_open(dining):
    restaurant, _, guest = dining
    endpoint = "/api/guest/services"
    old = ok(
        guest.post(
            endpoint, json={"kind": "assistance", "note": "Please bring a chair."}
        )
    )
    first = {
        "kind": "ingredient_check",
        "note": "Please check the fryer for peanut traces.",
    }
    second = {"kind": "ingredient_check", "note": "Also check the sauce for sesame."}
    first_id = ok(guest.post(endpoint, json=first))["id"]
    assert ok(guest.post(endpoint, json=first))["id"] == first_id
    second_id = ok(guest.post(endpoint, json=second))["id"]
    assert len({old["id"], first_id, second_id}) == 3
    queue = ok(restaurant.c.get("/api/restaurant/services"))
    assert {r["note"] for r in queue if r["kind"] == "ingredient_check"} == {
        first["note"],
        second["note"],
    }


def test_gemini_audio_wire_format_and_empty_transcript(monkeypatch):
    import base64
    import json

    cfg = replace(CFG, gemini_key="audio-test")
    transcript = "No milk or peanuts, please."

    def reply(url, **options):
        assert options["headers"] == {"x-goog-api-key": cfg.gemini_key}
        part = options["json"]["contents"][0]["parts"][0]["inlineData"]
        assert (
            part["mimeType"] == "audio/m4a"
            and base64.b64decode(part["data"]) == b"short voice note"
        )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps({"transcript": transcript})}]
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", reply)
    assert gemini.transcribe(cfg, b"short voice note", "audio/m4a") == transcript
    transcript = ""
    assert gemini.transcribe(cfg, b"short voice note", "audio/m4a") == ""
