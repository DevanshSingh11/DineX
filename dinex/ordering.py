import hashlib
from fastapi import HTTPException
from sqlalchemy import select

from .catalog import fields, menu
from .db import add, owned, rows
from .models import (
    Bill,
    BillOrder,
    DiningTable,
    History,
    Item,
    Line,
    Order,
    Payment,
    Restaurant,
    Staff,
    Visit,
    now,
)
from .security import audit, permissions
from .payments import manual_payments

KITCHEN_NEXT = {
    "received": "accepted",
    "accepted": "preparing",
    "preparing": "ready",
    "ready": "served",
}
BILL_NEXT = {
    "pending": "accepted",
    "accepted": "prepared",
    "prepared": "awaiting_payment",
    "awaiting_payment": "paid",
    "paid": "completed",
}


def current_table(db, visit):
    table = owned(db, DiningTable, visit.tenant, visit.table_id)
    if (
        visit.closed
        or not table.active
        or not table.qr_enabled
        or visit.qr_nonce != table.qr_nonce
    ):
        raise HTTPException(
            409,
            "This table session is closed for new requests. Scan the current QR code.",
        )
    return table


def rate_part(amount, basis_points):
    return (amount * basis_points + 5000) // 10000


def priced_line(item, raw):
    if len(set(raw.options)) != len(raw.options):
        raise HTTPException(422, "Select each option once.")
    selections, remaining = [], set(raw.options)
    for group in item["groups"]:
        picks = [o for o in group["options"] if o["id"] in remaining]
        if not group["minimum"] <= len(picks) <= group["maximum"]:
            raise HTTPException(
                422, "Check the number of selections for " + group["name"] + "."
            )
        for option in picks:
            remaining.remove(option["id"])
            selections.append(
                {
                    "id": option["id"],
                    "name": option["name"],
                    "group": group["name"],
                    "price": option["price"],
                }
            )
    if remaining:
        raise HTTPException(
            422, "An option is unavailable for this item. Refresh the menu."
        )
    return {
        "item_id": item["id"],
        "name": item["name"],
        "base_price": item["price"],
        "unit_price": item["price"] + sum(o["price"] for o in selections),
        "quantity": raw.quantity,
        "selections": selections,
        "note": raw.note,
    }


def place(db, visit, data):
    signature = hashlib.sha256(data.model_dump_json().encode()).hexdigest()
    old = db.scalar(
        select(Order).where(
            Order.tenant == visit.tenant,
            Order.visit_id == visit.id,
            Order.request_key == data.request_key,
        )
    )
    if old:
        if old.request_hash != signature:
            raise HTTPException(
                409, "This submission key already identifies a different order."
            )
        return old
    current_table(db, visit)
    if rows(
        db, Bill, visit.tenant, Bill.visit_id == visit.id, Bill.status != "cancelled"
    ):
        raise HTTPException(409, "A bill is already open for this visit.")
    r = db.get(Restaurant, visit.tenant)
    catalog = menu(db, r.id, public=True)
    items = {i["id"]: i for i in catalog["items"] if i["available"]}
    categories = {c["id"]: c["name"] for c in catalog["categories"]}
    lines = []
    for raw in data.lines:
        item = items.get(raw.item_id)
        if item is None:
            raise HTTPException(
                422, "An item is no longer available. Refresh the menu."
            )
        lines.append(
            {**priced_line(item, raw), "category": categories[item["category_id"]]}
        )
    subtotal = sum(line["unit_price"] * line["quantity"] for line in lines)
    tax, charges = rate_part(subtotal, r.tax_bps), rate_part(subtotal, r.charge_bps)
    order = add(
        db,
        Order,
        tenant=r.id,
        visit_id=visit.id,
        table_id=visit.table_id,
        request_key=data.request_key,
        request_hash=signature,
        subtotal=subtotal,
        tax=tax,
        charges=charges,
        total=subtotal + tax + charges,
        currency=r.currency,
    )
    order.number = f"{r.prefix}-{order.id:05d}"
    for line in lines:
        add(db, Line, tenant=r.id, order_id=order.id, **line)
    change_order(db, order, "received")
    audit(db, visit, "order.placed", order.number)
    return order


def change_order(db, order, status):
    order.status = status
    add(db, History, tenant=order.tenant, order_id=order.id, status=status)


def kitchen_step(db, staff, order, data):
    if data.status == order.status:
        return
    if data.status == "cancelled":
        if "orders" not in permissions(staff) or not data.reason:
            raise HTTPException(
                403, "Order cancellation requires an operations role and a reason."
            )
        if order.bill_id or order.status not in {"received", "accepted"}:
            raise HTTPException(409, "This order can no longer be cancelled.")
    elif KITCHEN_NEXT.get(order.status) != data.status:
        raise HTTPException(409, "This kitchen transition is unavailable.")
    change_order(db, order, data.status)
    audit(db, staff, "order." + data.status, order.number, data.reason)


def order_view(db, order, kitchen=False):
    table = owned(db, DiningTable, order.tenant, order.table_id)
    info = fields(order, "id number status created table_id")
    lines = []
    for line in rows(db, Line, order.tenant, Line.order_id == order.id):
        display = fields(line, "name quantity note")
        if kitchen:
            item = owned(db, Item, order.tenant, line.item_id)
            display["available"] = item.available and not item.archived
            display["selections"] = [
                {k: o[k] for k in ("group", "name")} for o in line.selections
            ]
        else:
            display.update(fields(line, "unit_price base_price selections category"))
        lines.append(display)
    if not kitchen:
        info.update(
            fields(order, "subtotal tax charges total currency visit_id bill_id")
        )
    return {
        **info,
        "table": table.name,
        "lines": lines,
        "history": [
            fields(h, "status created")
            for h in rows(db, History, order.tenant, History.order_id == order.id)
        ],
    }


def request_bill(db, visit, actor):
    existing = rows(
        db, Bill, visit.tenant, Bill.visit_id == visit.id, Bill.status != "cancelled"
    )
    if existing:
        return existing[-1]
    orders = rows(
        db,
        Order,
        visit.tenant,
        Order.visit_id == visit.id,
        Order.bill_id.is_(None),
        Order.status.not_in(["cancelled", "completed"]),
    )
    if not orders:
        raise HTTPException(409, "There are no orders to bill for this visit.")
    values = {
        key: sum(getattr(o, key) for o in orders)
        for key in ("subtotal", "tax", "charges", "total")
    }
    bill = add(
        db,
        Bill,
        tenant=visit.tenant,
        table_id=visit.table_id,
        visit_id=visit.id,
        currency=orders[0].currency,
        **values,
    )
    for order in orders:
        order.bill_id = bill.id
        add(db, BillOrder, tenant=bill.tenant, bill_id=bill.id, order_id=order.id)
    audit(db, actor, "bill.requested", bill.id)
    return bill


def bill_orders(db, bill):
    return db.scalars(
        select(Order)
        .join(BillOrder, BillOrder.order_id == Order.id)
        .where(
            Order.tenant == bill.tenant,
            BillOrder.tenant == bill.tenant,
            BillOrder.bill_id == bill.id,
        )
        .order_by(Order.id)
    ).all()


def bill_view(db, bill, guest=False):
    info = fields(
        bill,
        "id visit_id table_id status subtotal tax charges adjustment discount reason cancel_reason total currency created updated",
    )
    payment = db.scalar(
        select(Payment).where(Payment.tenant == bill.tenant, Payment.bill_id == bill.id)
    )
    info["payment_status"] = (
        "paid"
        if payment
        else ("cancelled" if bill.status == "cancelled" else "pending")
    )
    info["payment"] = (
        fields(
            payment,
            "method amount created"
            if guest
            else "method reference amount created staff_id",
        )
        if payment
        else None
    )
    info["table"] = owned(db, DiningTable, bill.tenant, bill.table_id).name
    info["orders"] = [order_view(db, o) for o in bill_orders(db, bill)]
    if not guest:
        info["assigned"] = (
            owned(db, Staff, bill.tenant, bill.assigned_id).name
            if bill.assigned_id
            else None
        )
    return info


def advance_bill(db, staff, bill, data):
    rights = permissions(staff)
    if data.status == "paid" and "payment" not in rights:
        raise HTTPException(403, "Payment confirmation requires payment permission.")
    if (data.adjustment or data.discount) and (
        data.status != "prepared" or "adjust" not in rights or not data.reason
    ):
        raise HTTPException(
            403, "Bill adjustments require permission and a reason during preparation."
        )
    if data.status == bill.status:
        return
    if data.status == "cancelled":
        if not data.reason or bill.status in {"paid", "completed", "cancelled"}:
            raise HTTPException(
                409, "Only an unpaid bill can be cancelled with a reason."
            )
        bill.cancel_reason = data.reason
        for o in bill_orders(db, bill):
            o.bill_id = None
    elif BILL_NEXT.get(bill.status) != data.status:
        raise HTTPException(409, "This checkout transition is unavailable.")
    elif data.status == "accepted":
        bill.assigned_id = staff.id
    elif data.status == "prepared":
        total = (
            bill.subtotal + bill.tax + bill.charges + data.adjustment - data.discount
        )
        if total < 0:
            raise HTTPException(422, "The discount exceeds the bill.")
        bill.adjustment, bill.discount, bill.total, bill.reason = (
            data.adjustment,
            data.discount,
            total,
            data.reason,
        )
        if data.discount or data.adjustment:
            audit(
                db,
                staff,
                "bill.adjusted",
                bill.id,
                f"Charge {data.adjustment}, discount {data.discount}. {data.reason}",
            )
    elif data.status == "paid":
        manual_payments.record(db, bill, staff, data)
    elif data.status == "completed":
        orders = bill_orders(db, bill)
        if any(o.status != "served" for o in orders):
            raise HTTPException(
                409, "Serve every included order before completing checkout."
            )
        for order in orders:
            change_order(db, order, "completed")
        owned(db, Visit, bill.tenant, bill.visit_id).closed = True
    bill.status, bill.updated = data.status, now()
    audit(db, staff, "bill." + data.status, bill.id, data.reason)
