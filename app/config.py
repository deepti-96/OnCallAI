import os
from dotenv import load_dotenv
load_dotenv()

ENV = os.getenv("ENV", "dev")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "10"))
DB_URL = os.getenv("DB_URL", "sqlite:///dev.db")

VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "chroma")
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

LOGS_MODE = os.getenv("LOGS_MODE", "local")
LOGS_LOCAL_ROOT = os.getenv("LOGS_LOCAL_ROOT", "app/logs")

USE_REAL_CLOUDWATCH = os.getenv("USE_REAL_CLOUDWATCH", "false").lower() == "true"
CLOUDWATCH_LOG_GROUP = os.getenv("CLOUDWATCH_LOG_GROUP", "/aws/lambda/demo")
