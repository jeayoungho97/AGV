import os


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def optional_env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default

