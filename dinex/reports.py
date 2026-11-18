from collections import Counter
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select
from .models import Bill, DiningTable, Line, Order, Payment, Service


def interval(r, start, end):
    zone = ZoneInfo(r.timezone)
    today = datetime.now(zone).date()
    end = end or today
    start = start or date.fromordinal(max(date.min.toordinal(), end.toordinal() - 29))
    if start > end or (end - start).days > 365 or end >= date.max:
        raise HTTPException(422, "Choose a date range of up to 366 days.")

    def boundary(d):
        return int(datetime.combine(d, time.min, zone).timestamp())

    return zone, start, end, boundary(start), boundary(end + timedelta(days=1))


def report(db, r, start=None, end=None):
    zone, start, end, first, stop = interval(r, start, end)

    def during(cls):
        return db.scalars(
            select(cls).where(
                cls.tenant == r.id, cls.created >= first, cls.created < stop
            )
        ).all()

    orders, payments, bills, service = (
        during(Order),
        during(Payment),
        during(Bill),
        during(Service),
    )
    counted = [o for o in orders if o.status != "cancelled"]
    days, revenue_days, popularity, categories, hours, tables = (
        Counter() for _ in range(6)
    )
    names = dict(
        db.execute(
            select(DiningTable.id, DiningTable.name).where(DiningTable.tenant == r.id)
        ).all()
    )
    for o in counted:
        local = datetime.fromtimestamp(o.created, zone)
        days[local.date().isoformat()] += 1
        hours[f"{local.hour:02}:00"] += 1
        tables[names[o.table_id]] += 1
    for p in payments:
        revenue_days[datetime.fromtimestamp(p.created, zone).date().isoformat()] += (
            p.amount
        )
    lines = db.scalars(
        select(Line)
        .join(Order, Line.order_id == Order.id)
        .where(
            Line.tenant == r.id,
            Order.tenant == r.id,
            Order.created >= first,
            Order.created < stop,
            Order.status != "cancelled",
        )
    )
    for line in lines:
        popularity[line.name] += line.quantity
        categories[line.category] += line.quantity * line.unit_price
    gross = sum(o.total for o in counted)
    days_list = [
        (start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)
    ]
    return {
        "from": str(start),
        "to": str(end),
        "currency": r.currency,
        "timezone": r.timezone,
        "orders": len(counted),
        "cancelled_orders": len(orders) - len(counted),
        "gross": gross,
        "paid": sum(p.amount for p in payments),
        "average": (gross + len(counted) // 2) // len(counted) if counted else 0,
        "pending_payments": sum(
            b.total for b in bills if b.status not in {"cancelled", "paid", "completed"}
        ),
        "days": [
            {"date": d, "orders": days[d], "paid": revenue_days[d]} for d in days_list
        ],
        "popular": dict(popularity.most_common(10)),
        "categories": dict(categories.most_common()),
        "hours": dict(hours.most_common()),
        "tables": dict(tables.most_common()),
        "service": dict(Counter(s.kind for s in service)),
        "checkout": dict(Counter(b.status for b in bills)),
        "methods": {
            m: sum(p.amount for p in payments if p.method == m)
            for m in ("cash", "upi", "card")
        },
    }
