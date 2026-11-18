from dataclasses import dataclass
from pathlib import Path
import os
import re
import secrets
from urllib.parse import urlsplit
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    database: Path
    secret: str
    public_url: str = "http://127.0.0.1:8000"
    secure_cookies: bool = False
    ai_url: str = ""
    ai_model: str = ""
    ai_key: str = ""
    gemini_key: str = ""
    gemini_model: str = "gemini-flash-latest"


def init_config():
    path = ROOT / ".env"
    if not path.exists():
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        try:
            with path.open("x", encoding="utf-8") as output:
                output.write(
                    content.replace(
                        "DINEX_SECRET=\n",
                        "DINEX_SECRET=" + secrets.token_urlsafe(48) + "\n",
                    )
                )
            path.chmod(0o600)
        except FileExistsError:
            pass


def load_config():
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    key = env.get("DINEX_SECRET", "")
    if len(key or "") < 32:
        raise RuntimeError(
            "Run python -m dinex init or configure a fresh DINEX_SECRET."
        )
    base = env.get("DINEX_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")
    u = urlsplit(base)
    if (
        u.scheme not in {"https", "http"}
        or not u.hostname
        or u.username
        or u.password
        or u.path
        or u.query
        or u.fragment
    ):
        raise RuntimeError(
            "DINEX_PUBLIC_URL must be an absolute HTTP(S) origin with no path."
        )
    secure = (
        env.get("DINEX_SECURE_COOKIES", "false").lower() == "true"
        or u.scheme == "https"
    )
    url = env.get("DINEX_AI_URL", "")
    if url and urlsplit(url).scheme != "https":
        raise RuntimeError("Use HTTPS for the configured AI provider.")
    model = env.get("DINEX_GEMINI_MODEL") or "gemini-flash-latest"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", model):
        raise RuntimeError("Use a Gemini model ID such as gemini-flash-latest.")
    return Config(
        ROOT / env.get("DINEX_DATABASE", "data/universal.sqlite3"),
        key,
        base,
        secure,
        url,
        env.get("DINEX_AI_MODEL", ""),
        env.get("DINEX_AI_KEY", ""),
        env.get("GEMINI_API_KEY") or "",
        model,
    )
