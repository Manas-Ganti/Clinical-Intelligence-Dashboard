"""Configuration via environment variables (no hardcoded credentials).

DATABASE_URL selects the backend: SQLite by default (zero-setup local dev and
tests) and PostgreSQL in docker-compose. python-dotenv is loaded if present so a
local .env works, but the app runs fine without it.
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional for local runs
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./clinical.db")
