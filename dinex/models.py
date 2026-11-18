"""Minor currency units and UTC epoch seconds throughout the database."""

import time
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Text,
    JSON,
    LargeBinary,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    text,
)
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    pass


def now():
    return int(time.time())


def pk():
    return Column(Integer, primary_key=True)


def string(default=""):
    return Column(String, nullable=False, default=default)


def integer(default=0):
    return Column(Integer, nullable=False, default=default)


def flag(default=True):
    return Column(Boolean, nullable=False, default=default)


class TenantRecord:
    id = pk()

    @declared_attr
    def tenant(cls):
        return Column(Integer, ForeignKey("restaurants.id"), nullable=False, index=True)


def tenant_keys(*links, extra=()):
    constraints = [UniqueConstraint("tenant", "id")]
    for field, parent in links:
        constraints.append(
            ForeignKeyConstraint(
                ["tenant", field], [parent + ".tenant", parent + ".id"]
            )
        )
    return tuple(constraints) + tuple(extra) + ({"sqlite_autoincrement": True},)


class Policy(Base):
    __tablename__ = "platform_policy"
    id = pk()
    approval = flag()


class Plan(Base):
    __tablename__ = "plans"
    id = pk()
    name = Column(String, nullable=False, unique=True)
    max_tables = integer(100)
    max_staff = integer(50)
    analytics = flag()
    assistant = flag()
    trial_days = integer()


class Restaurant(Base):
    __tablename__ = "restaurants"
    id = pk()
    slug = Column(String, nullable=False, unique=True)
    name = string()
    status = string("pending")
    owner_name = string()
    owner_email = string()
    contact = string()
    address = string()
    city = string()
    region = string()
    country = string()
    description = string()
    cuisine = string()
    hours = string()
    logo = string()
    cover = string()
    currency = string("INR")
    timezone = string("Asia/Kolkata")
    prefix = string("DX")
    tax_bps = integer()
    charge_bps = integer()
    setup_flags = Column(JSON, nullable=False, default=list)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    subscription = string("unbilled")
    trial_until = Column(Integer)
    created = integer(now)


class PlatformUser(Base):
    __tablename__ = "platform_users"
    id = pk()
    name = string()
    email = Column(String, nullable=False, unique=True)
    password_hash = string()
    active = flag()


class Staff(TenantRecord, Base):
    __tablename__ = "staff"
    name = string()
    email = string()
    password_hash = string()
    role = string()
    active = flag()
    grants = Column(JSON, nullable=False, default=list)
    __table_args__ = tenant_keys(extra=[UniqueConstraint("tenant", "email")])


class Login(Base):
    __tablename__ = "logins"
    id = pk()
    digest = Column(String, unique=True, nullable=False)
    platform_id = Column(Integer, ForeignKey("platform_users.id"))
    tenant = Column(Integer, ForeignKey("restaurants.id"))
    staff_id = Column(Integer)
    expires = integer()
    __table_args__ = (
        ForeignKeyConstraint(["tenant", "staff_id"], ["staff.tenant", "staff.id"]),
        CheckConstraint(
            "(platform_id IS NOT NULL AND staff_id IS NULL AND tenant IS NULL) OR "
            "(platform_id IS NULL AND staff_id IS NOT NULL AND tenant IS NOT NULL)"
        ),
    )


class Category(TenantRecord, Base):
    __tablename__ = "categories"
    name = string()
    active = flag()
    __table_args__ = tenant_keys(extra=[UniqueConstraint("tenant", "name")])


class Item(TenantRecord, Base):
    __tablename__ = "items"
    category_id = Column(Integer, nullable=False)
    name = string()
    description = string()
    price = integer()
    ingredients = string()
    allergens = Column(JSON, nullable=False, default=list)
    may_contain = Column(JSON, nullable=False, default=list)
    recipe_status = string("unreviewed")
    dietary = string("unspecified")
    minutes = integer()
    image = string()
    available = flag()
    featured = flag(False)
    archived = flag(False)
    __table_args__ = tenant_keys(
        ("category_id", "categories"), extra=[CheckConstraint("price >= 0")]
    )


class ChoiceGroup(TenantRecord, Base):
    __tablename__ = "choice_groups"
    item_id = Column(Integer, nullable=False, index=True)
    name = string()
    minimum = integer()
    maximum = integer(1)
    __table_args__ = tenant_keys(
        ("item_id", "items"),
        extra=[CheckConstraint("minimum >= 0 AND maximum >= 1 AND minimum <= maximum")],
    )


class Choice(TenantRecord, Base):
    __tablename__ = "choices"
    group_id = Column(Integer, nullable=False, index=True)
    name = string()
    price = integer()
    __table_args__ = tenant_keys(
        ("group_id", "choice_groups"), extra=[CheckConstraint("price >= 0")]
    )


class DiningTable(TenantRecord, Base):
    __tablename__ = "dining_tables"
    name = string()
    active = flag()
    archived = flag(False)
    qr_nonce = string()
    qr_enabled = flag()
    qr_issued = flag(False)
    __table_args__ = tenant_keys(extra=[UniqueConstraint("tenant", "name")])


class Visit(TenantRecord, Base):
    __tablename__ = "visits"
    table_id = Column(Integer, nullable=False)
    digest = Column(String, nullable=False, unique=True)
    qr_nonce = string()
    expires = integer()
    closed = flag(False)
    created = integer(now)
    __table_args__ = tenant_keys(("table_id", "dining_tables"))


class Bill(TenantRecord, Base):
    __tablename__ = "bills"
    visit_id = Column(Integer, nullable=False)
    table_id = Column(Integer, nullable=False)
    status = string("pending")
    subtotal = integer()
    tax = integer()
    charges = integer()
    adjustment = integer()
    discount = integer()
    reason = string()
    cancel_reason = string()
    total = integer()
    currency = string()
    assigned_id = Column(Integer)
    created = integer(now)
    updated = integer(now)
    __table_args__ = tenant_keys(
        ("visit_id", "visits"),
        ("table_id", "dining_tables"),
        ("assigned_id", "staff"),
        extra=[
            CheckConstraint("total >= 0"),
            Index(
                "one_current_bill_per_visit",
                "visit_id",
                unique=True,
                sqlite_where=text("status != 'cancelled'"),
            ),
        ],
    )


class Order(TenantRecord, Base):
    __tablename__ = "orders"
    visit_id = Column(Integer, nullable=False)
    table_id = Column(Integer, nullable=False)
    bill_id = Column(Integer)
    number = string()
    status = string("received")
    request_key = string()
    request_hash = string()
    subtotal = integer()
    tax = integer()
    charges = integer()
    total = integer()
    currency = string()
    created = integer(now)
    __table_args__ = tenant_keys(
        ("visit_id", "visits"),
        ("table_id", "dining_tables"),
        ("bill_id", "bills"),
        extra=[
            UniqueConstraint("tenant", "number"),
            UniqueConstraint("visit_id", "request_key"),
            Index("orders_tenant_time", "tenant", "created"),
        ],
    )


class Line(TenantRecord, Base):
    __tablename__ = "order_lines"
    order_id = Column(Integer, nullable=False, index=True)
    item_id = Column(Integer, nullable=False)
    name = string()
    category = string()
    quantity = integer()
    base_price = integer()
    unit_price = integer()
    selections = Column(JSON, nullable=False, default=list)
    note = string()
    __table_args__ = tenant_keys(
        ("order_id", "orders"),
        ("item_id", "items"),
        extra=[CheckConstraint("quantity > 0")],
    )


class History(TenantRecord, Base):
    __tablename__ = "order_history"
    order_id = Column(Integer, nullable=False, index=True)
    status = string()
    created = integer(now)
    __table_args__ = tenant_keys(("order_id", "orders"))


class BillOrder(TenantRecord, Base):
    __tablename__ = "bill_orders"
    bill_id = Column(Integer, nullable=False)
    order_id = Column(Integer, nullable=False)
    __table_args__ = tenant_keys(
        ("bill_id", "bills"),
        ("order_id", "orders"),
        extra=[UniqueConstraint("bill_id", "order_id")],
    )


class Payment(TenantRecord, Base):
    __tablename__ = "payments"
    bill_id = Column(Integer, nullable=False, unique=True)
    staff_id = Column(Integer, nullable=False)
    amount = integer()
    method = string()
    reference = string()
    created = integer(now)
    __table_args__ = tenant_keys(("bill_id", "bills"), ("staff_id", "staff"))


class Service(TenantRecord, Base):
    __tablename__ = "service_requests"
    visit_id = Column(Integer, nullable=False)
    table_id = Column(Integer, nullable=False)
    kind = string()
    note = string()
    status = string("open")
    created = integer(now)
    __table_args__ = tenant_keys(("visit_id", "visits"), ("table_id", "dining_tables"))


class Audit(Base):
    __tablename__ = "audit"
    id = pk()
    tenant = Column(Integer, ForeignKey("restaurants.id"), index=True)
    actor = string()
    action = string()
    entity = string()
    detail = Column(Text, nullable=False, default="")
    created = integer(now)


class Media(TenantRecord, Base):
    __tablename__ = "media"
    image = Column(LargeBinary, nullable=False)
    __table_args__ = tenant_keys()
