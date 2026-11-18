"""Copy the bundled restaurant into a DineX database and issue fresh table credentials."""

import secrets
import sqlite3

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .catalog import PUBLIC_PROFILE, fields, menu, save_item
from .config import ROOT
from .db import add, rows, unit
from .models import Category, DiningTable, Plan, Restaurant, Staff
from .schemas import ItemInput
from .security import audit

SLUG = "saffron-courtyard"
TEMPLATE = ROOT / "starter" / "saffron-courtyard.sqlite3"


def install_demo(engine, only_if_empty=False):
    with unit(engine, write=True) as db:
        if db.scalar(select(Restaurant.id).where(Restaurant.slug == SLUG)):
            return "The saffron-courtyard slug is already in use. Its accounts and menu were left as they are."
        if only_if_empty and db.scalar(select(Restaurant.id).limit(1)):
            return "Existing workspace found. Use Add-Demo.bat to add Saffron Courtyard here."
        if not TEMPLATE.is_file():
            raise RuntimeError(
                "The Saffron Courtyard starter database is missing from the extracted ZIP."
            )
        template = create_engine(
            "sqlite://",
            creator=lambda: sqlite3.connect(
                TEMPLATE.as_uri() + "?mode=ro&immutable=1", uri=True
            ),
        )
        try:
            with Session(template) as source:
                sample = source.scalars(
                    select(Restaurant).where(Restaurant.slug == SLUG)
                ).one()
                profile = fields(sample, [k for k in PUBLIC_PROFILE if k != "id"])
                plan = db.get(Plan, 1)
                restaurant = add(
                    db,
                    Restaurant,
                    **profile,
                    owner_name=sample.owner_name,
                    owner_email=sample.owner_email,
                    status="active",
                    plan_id=plan.id,
                )
                owner = source.scalars(
                    select(Staff).where(
                        Staff.tenant == sample.id, Staff.role == "Owner"
                    )
                ).one()
                add(
                    db,
                    Staff,
                    tenant=restaurant.id,
                    name=owner.name,
                    email=owner.email,
                    password_hash=owner.password_hash,
                    role="Owner",
                )
                for table in rows(source, DiningTable, sample.id)[: plan.max_tables]:
                    add(
                        db,
                        DiningTable,
                        tenant=restaurant.id,
                        name=table.name,
                        qr_nonce=secrets.token_hex(16),
                    )
                catalog = menu(source, sample.id)
                categories = {
                    cat["id"]: add(
                        db, Category, tenant=restaurant.id, name=cat["name"]
                    ).id
                    for cat in catalog["categories"]
                }
                for row in catalog["items"]:
                    data = {k: v for k, v in row.items() if k != "id"}
                    data["category_id"] = categories[row["category_id"]]
                    data["groups"] = [
                        {
                            **{
                                k: v
                                for k, v in group.items()
                                if k not in {"id", "options"}
                            },
                            "options": [
                                {k: v for k, v in o.items() if k != "id"}
                                for o in group["options"]
                            ],
                        }
                        for group in row["groups"]
                    ]
                    save_item(db, restaurant.id, ItemInput(**data))
                audit(
                    db,
                    "local installer",
                    "demo.installed",
                    restaurant.id,
                    tenant=restaurant.id,
                )
                status = (
                    ""
                    if plan.assistant
                    else " Enable the assistant on this restaurant's plan to use DineX AI."
                )
                return (
                    f"Saffron Courtyard is ready: {len(catalog['items'])} dishes. Owner sign-in slug: {SLUG}."
                    + status
                )
        finally:
            template.dispose()
