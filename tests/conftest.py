import secrets
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from dinex.app import create_app
from dinex.config import Config
from dinex.db import add, unit
from dinex.models import PlatformUser
from dinex.security import password_hash


def ok(response, status=None):
    assert (
        response.status_code == status if status else 200 <= response.status_code < 300
    ), response.text
    return response.json()


class World:
    def __init__(self, app, client):
        self.app, self.c = app, client
        self.password = secrets.token_urlsafe(20)
        with unit(app.state.engine, True) as db:
            add(
                db,
                PlatformUser,
                name="Platform tester",
                email="test@example.test",
                password_hash=password_hash(self.password),
            )

    def http(self):
        return TestClient(self.app, headers={"X-DineX": "1"})

    def platform(self):
        c = self.http()
        ok(
            c.post(
                "/api/platform/login",
                json={"email": "test@example.test", "password": self.password},
            )
        )
        return c

    def registration(self, slug):
        return {
            "name": slug.title(),
            "slug": slug,
            "owner_name": "Owner",
            "owner_email": "owner@example.test",
            "password": self.password,
            "contact": "1234",
            "address": "Market St",
            "city": "Pune",
            "country": "India",
        }

    def login(self, slug, email="owner@example.test"):
        c = self.http()
        ok(
            c.post(
                "/api/restaurant/login",
                json={"slug": slug, "email": email, "password": self.password},
            )
        )
        return c

    def restaurant(self, slug="green-leaf", platform=None):
        platform = platform or self.platform()
        r = ok(platform.post("/api/platform/restaurants", json=self.registration(slug)))
        c = self.login(slug)
        return SimpleNamespace(id=r["id"], slug=slug, c=c)

    def stock(self, r):
        c = r.c
        cat = ok(c.post("/api/restaurant/categories", json={"name": "Mains"}))
        spec = {
            "name": "Roast cauliflower",
            "category_id": cat["id"],
            "price": 1001,
            "ingredients": "Cauliflower, cumin",
            "dietary": "vegan",
            "featured": True,
            "groups": [
                {
                    "name": "Portion",
                    "minimum": 1,
                    "maximum": 1,
                    "options": [{"name": "Small"}, {"name": "Large", "price": 125}],
                },
                {
                    "name": "Toppings",
                    "minimum": 0,
                    "maximum": 2,
                    "options": [
                        {"name": "Herbs", "price": 20},
                        {"name": "Chilli", "price": 30},
                    ],
                },
            ],
        }
        ok(c.post("/api/restaurant/items", json=spec))
        t = ok(c.post("/api/restaurant/tables", json={"name": "Garden 1"}))
        url = ok(c.post(f"/api/restaurant/tables/{t['id']}/qr"))["url"]
        dish = ok(c.get("/api/restaurant/menu"))["items"][0]
        return SimpleNamespace(
            category=cat["id"], dish=dish, spec=spec, table=t["id"], url=url
        )

    def enter(self, r, stock):
        g = self.http()
        token = ok(
            g.post(
                "/api/guest/enter/" + r.slug,
                json={
                    "table_id": stock.table,
                    "credential": urlsplit(stock.url).fragment,
                },
            )
        )
        g.headers["Authorization"] = "Bearer " + token["token"]
        return g

    def line(self, stock, key=None):
        return {
            "request_key": key or secrets.token_urlsafe(20),
            "lines": [
                {
                    "item_id": stock.dish["id"],
                    "quantity": 2,
                    "options": [stock.dish["groups"][0]["options"][1]["id"]],
                    "note": "Sauce on side",
                }
            ],
        }

    def place(self, g, stock):
        return ok(g.post("/api/guest/orders", json=self.line(stock)))

    def member(self, r, role, grants=None):
        email = role.lower() + "@example.test"
        data = {
            "name": role,
            "email": email,
            "password": self.password,
            "role": role,
            "grants": grants or [],
        }
        result = ok(r.c.post("/api/restaurant/staff", json=data))
        return self.login(r.slug, email), result["id"]


@pytest.fixture
def world(tmp_path):
    app = create_app(Config(tmp_path / "testing.sqlite3", secrets.token_urlsafe(48)))
    with TestClient(app, headers={"X-DineX": "1"}) as client:
        yield World(app, client)


@pytest.fixture
def dining(world):
    r = world.restaurant()
    s = world.stock(r)
    return r, s, world.enter(r, s)
