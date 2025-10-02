# Loads config from .env so scripts can find keys/paths
import os
from dotenv import load_dotenv
load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SQLITE_PATH = os.getenv("SQLITE_PATH", "db/state_demo.db")
