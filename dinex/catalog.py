import secrets
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from .allergens import choices
from .db import add, owned, rows
from .models import (
    Bill,
    Category,
    Choice,
    ChoiceGroup,
    DiningTable,
    Item,
    Order,
    Plan,
    Restaurant,
    Staff,
)
from .security import password_hash

PUBLIC_PROFILE = "id slug name description cuisine hours address city region country contact logo cover currency timezone prefix tax_bps charge_bps".split()
ITEM_FIELDS = "id name category_id description price ingredients allergens may_contain recipe_status dietary minutes image available featured archived".split()


def fields(record, names):
    if isinstance(names, str):
        names = names.split()
    return {key: getattr(record, key) for key in names}


def update(record, values):
    for key, value in values.items():
        setattr(record, key, value)


def count(db, cls, *conditions):
    return db.scalar(select(func.count()).select_from(cls).where(*conditions))


def entitlement(db, tenant, feature):
    plan = db.get(Plan, db.get(Restaurant, tenant).plan_id)
    if not getattr(plan, feature):
        raise HTTPException(403, "This feature is disabled in the restaurant plan.")


def capacity(db, tenant, which):
    plan = db.get(Plan, db.get(Restaurant, tenant).plan_id)
    cls = DiningTable if which == "tables" else Staff
    if count(db, cls, cls.tenant == tenant, cls.active.is_(True)) >= getattr(
        plan, "max_" + which
    ):
        raise HTTPException(
            409, "The plan limit for active " + which + " has been reached."
        )


def create_restaurant(db, data, status):
    plan = db.get(Plan, 1)
    if data.table_count > plan.max_tables:
        raise HTTPException(422, "The requested table count exceeds the plan limit.")
    if data.logo.startswith("/media/") or data.cover.startswith("/media/"):
        raise HTTPException(422, "Choose an HTTPS branding image during registration.")
    r = add(
        db,
        Restaurant,
        **data.model_dump(exclude={"password", "table_count"}),
        status=status,
        plan_id=plan.id,
    )
    add(
        db,
        Staff,
        tenant=r.id,
        name=data.owner_name,
        email=data.owner_email,
        password_hash=password_hash(data.password),
        role="Owner",
    )
    for number in range(1, data.table_count + 1):
        add(
            db,
            DiningTable,
            tenant=r.id,
            name=f"Table {number}",
            qr_nonce=secrets.token_hex(16),
        )
    return r


def menu(db, tenant, public=False):
    categories = rows(db, Category, tenant)
    cat_ids = {c.id for c in categories if c.active}
    items = rows(db, Item, tenant)
    groups = rows(db, ChoiceGroup, tenant)
    options = rows(db, Choice, tenant)
    by_group = {}
    for o in options:
        by_group.setdefault(o.group_id, []).append(fields(o, "id name price"))
    by_item = {}
    for g in groups:
        by_item.setdefault(g.item_id, []).append(
            {**fields(g, "id name minimum maximum"), "options": by_group.get(g.id, [])}
        )
    return {
        "allergen_options": choices(),
        "categories": [
            fields(c, "id name active") for c in categories if not public or c.active
        ],
        "items": [
            {**fields(i, ITEM_FIELDS), "groups": by_item.get(i.id, [])}
            for i in items
            if not public or not i.archived and i.category_id in cat_ids
        ],
    }


def check_images(db, tenant, *paths):
    from .models import Media

    for path in paths:
        if path.startswith("/media/"):
            parts = path.split("/")
            if len(parts) != 4 or parts[2] != str(tenant) or not parts[3].isdigit():
                raise HTTPException(422, "Choose an image for this restaurant.")
            owned(db, Media, tenant, int(parts[3]))


def save_item(db, tenant, data, item=None):
    owned(db, Category, tenant, data.category_id)
    check_images(db, tenant, data.image)
    values = data.model_dump(exclude={"groups"})
    if item is None:
        item = add(db, Item, tenant=tenant, **values)
    else:
        update(item, values)
        # Replace editable choices. Orders carry immutable selection snapshots.
        old = select(ChoiceGroup.id).where(
            ChoiceGroup.tenant == tenant, ChoiceGroup.item_id == item.id
        )
        db.execute(
            delete(Choice).where(Choice.tenant == tenant, Choice.group_id.in_(old))
        )
        db.execute(
            delete(ChoiceGroup).where(
                ChoiceGroup.tenant == tenant, ChoiceGroup.item_id == item.id
            )
        )
    for group in data.groups:
        g = add(
            db,
            ChoiceGroup,
            tenant=tenant,
            item_id=item.id,
            **group.model_dump(exclude={"options"}),
        )
        for option in group.options:
            add(db, Choice, tenant=tenant, group_id=g.id, **option.model_dump())
    return item


def occupancy(db, table):
    active = rows(
        db,
        Order,
        table.tenant,
        Order.table_id == table.id,
        Order.status.not_in(["completed", "cancelled"]),
    )
    requests = rows(
        db,
        Bill,
        table.tenant,
        Bill.table_id == table.id,
        Bill.status.not_in(["completed", "cancelled"]),
    )
    return {
        **fields(table, "id name active archived qr_enabled"),
        "occupied": bool(active or requests),
        "active_orders": len(active),
        "checkout_requests": len(requests),
    }
