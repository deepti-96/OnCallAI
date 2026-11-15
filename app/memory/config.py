import os


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def mind_enabled() -> bool:
    return _flag("MIND_ENABLED") and bool(os.getenv("MIND_API_KEY"))


MIND_BASE_URL = os.getenv("MIND_BASE_URL", "https://www.m-i-n-d.ai")
MIND_QUERY_MODE = os.getenv("MIND_QUERY_MODE", "mix")  # mix | hybrid | global | local | naive
MIND_TIMEOUT_SECONDS = float(os.getenv("MIND_TIMEOUT_SECONDS", "4"))
MIND_MAX_HISTORY = int(os.getenv("MIND_MAX_HISTORY", "3"))
MIND_MAX_CONTEXT_TOKENS = int(os.getenv("MIND_MAX_CONTEXT_TOKENS", "6000"))
MIND_FOLDER = os.getenv("MIND_FOLDER", "OnCallAI Incidents")
