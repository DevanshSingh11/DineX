import argparse
from getpass import getpass
import sys
from pydantic import ValidationError
from sqlalchemy import select
from .config import ROOT, init_config, load_config
from .db import add, make_engine, migrate, unit
from .models import PlatformUser
from .schemas import PlatformAccount
from .security import audit, password_hash


def main():
    parser = argparse.ArgumentParser(prog="python -m dinex")
    parser.add_argument(
        "action", choices=["init", "bootstrap", "serve", "demo", "set-gemini"]
    )
    parser.add_argument(
        "--if-empty",
        action="store_true",
        help="Install the demo only in an empty restaurant workspace.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    if args.action in {"init", "set-gemini"}:
        init_config()
    if args.action == "set-gemini":
        from dataclasses import replace
        from dotenv import set_key
        from . import gemini
        import httpx

        key = getpass("Paste your Gemini API key here (input is hidden): ").strip()
        if not key or any(c.isspace() for c in key) or not key.isascii():
            sys.exit(
                "Enter a single Gemini API key. Your previous configuration was kept."
            )
        cfg = replace(load_config(), gemini_key=key)
        print(f"Checking {cfg.gemini_model} with one sample menu request...")
        try:
            gemini.interpret(cfg, "Find rice", ["Rice"])
            status = "Gemini answered the sample request."
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in {400, 401, 403, 404}:
                sys.exit(
                    f"Google returned HTTP {code}. Check the key and model access, then run setup again. Your previous key was kept."
                )
            status = f"Google returned HTTP {code}. DineX will use local search if Gemini is unavailable."
        except gemini.PROVIDER_ERRORS:
            status = "The connection check could not finish. DineX can still search the menu locally."
        set_key(str(ROOT / ".env"), "GEMINI_API_KEY", key)
        print(status, "Key saved on this computer. Restart DineX.")
        return
    cfg = load_config()
    if args.action == "serve":
        import uvicorn
        from .app import create_app

        uvicorn.run(
            create_app(cfg), host=args.host, port=args.port, proxy_headers=False
        )
        return
    engine = make_engine(cfg.database)
    migrate(engine)
    if args.action == "demo":
        from .demo import install_demo

        print(install_demo(engine, only_if_empty=args.if_empty))
        return
    if args.action == "init":
        print(
            "DineX Universal database ready. Run python -m dinex bootstrap to create the first platform administrator."
        )
        return
    with unit(engine) as db:
        if db.scalar(select(PlatformUser.id).limit(1)):
            print("A platform administrator is already set up. Continuing.")
            return
    name, email = input("Administrator name: "), input("Administrator email: ")
    password = getpass("New password (at least 12 characters): ")
    if getpass("Confirm password: ") != password:
        sys.exit("Passwords did not match.")
    try:
        data = PlatformAccount(name=name, email=email, password=password)
    except ValidationError:
        sys.exit("Check the name, email and password length.")
    with unit(engine, write=True) as db:
        if db.scalar(select(PlatformUser.id).limit(1)):
            print(
                "A platform administrator was created by another process. Continuing."
            )
            return
        u = add(
            db,
            PlatformUser,
            name=data.name,
            email=data.email,
            password_hash=password_hash(data.password),
        )
        audit(db, u, "platform.bootstrap", u.id)
    print("Platform administrator created. Run python -m dinex serve.")


if __name__ == "__main__":
    main()
