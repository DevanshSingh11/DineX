from contextlib import contextmanager
from pathlib import Path

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.engine import URL

from .models import Base, Plan, Policy

APP_ID = 0x44585531
VERSION = 2


def make_engine(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        URL.create("sqlite", database=str(path)),
        connect_args={"check_same_thread": False, "timeout": 8},
    )

    @event.listens_for(engine, "connect")
    def connect(connection, _):
        connection.isolation_level = None
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=8000")

    return engine


def migrate(engine):
    with engine.connect() as con:

        def version():
            return con.exec_driver_sql("PRAGMA user_version").scalar_one()

        def check_identity():
            identity = con.exec_driver_sql("PRAGMA application_id").scalar_one()
            exists = con.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' LIMIT 1"
            ).first()
            if identity != APP_ID and (identity or exists or version()):
                raise RuntimeError(
                    "This database belongs to a different application. Choose a fresh DINEX_DATABASE."
                )

        check_identity()
        con.exec_driver_sql("PRAGMA journal_mode=WAL")
        con.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            check_identity()
            if version() > VERSION:
                raise RuntimeError("The database is newer than this application.")
            previous = version()
            if previous == 0:
                Base.metadata.create_all(con)
                con.execute(Plan.__table__.insert().values(id=1, name="Standard"))
                con.execute(Policy.__table__.insert().values(id=1, approval=True))
                con.exec_driver_sql(f"PRAGMA application_id={APP_ID}")
            elif previous == 1:
                con.exec_driver_sql(
                    "ALTER TABLE items ADD COLUMN allergens JSON NOT NULL DEFAULT '[]'"
                )
                con.exec_driver_sql(
                    "ALTER TABLE items ADD COLUMN may_contain JSON NOT NULL DEFAULT '[]'"
                )
                con.exec_driver_sql(
                    "ALTER TABLE items ADD COLUMN recipe_status TEXT NOT NULL DEFAULT 'unreviewed'"
                )
            con.exec_driver_sql(f"PRAGMA user_version={VERSION}")
            con.commit()
        except Exception:
            con.rollback()
            raise


@contextmanager
def unit(engine, write=False):
    with Session(engine, expire_on_commit=False) as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise


def database(request: Request):
    write = request.method not in {
        "GET",
        "HEAD",
        "OPTIONS",
    } and request.url.path not in {
        "/api/guest/assistant",
        "/api/guest/assistant/transcribe",
    }
    try:
        with unit(request.app.state.engine, write) as db:
            yield db
    except IntegrityError:
        raise HTTPException(
            409, "This change conflicts with an existing record."
        ) from None
    except OperationalError as exc:
        if "locked" in str(exc.orig).lower():
            raise HTTPException(
                503, "The restaurant is busy. Please retry shortly."
            ) from None
        raise


def rows(db, cls, tenant, *terms):
    return db.scalars(
        select(cls).where(cls.tenant == tenant, *terms).order_by(cls.id)
    ).all()


def owned(db, cls, tenant, ident):
    obj = db.scalar(select(cls).where(cls.tenant == tenant, cls.id == ident))
    if obj is None:
        raise HTTPException(404, "Record not found in this restaurant.")
    return obj


def add(db, cls, **values):
    obj = cls(**values)
    db.add(obj)
    db.flush()
    return obj
