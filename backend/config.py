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

# The Ask layer's settings (LLM_MODEL, VTARC_BASE_URL, and the provider API keys)
# are read in backend/llm/models.py, at call time rather than import time, so a
# model swap doesn't need a reimport. They live next to the model registry that
# gives them meaning rather than being restated here.

# Which dataset seeds a fresh database: "synthea" (the real ~1.2k-patient export,
# fetched by scripts/fetch_synthea.py), "sample" (the small hand-authored
# fixtures), or "auto" — Synthea if it has been fetched, fixtures otherwise.
SEED_SOURCE = os.getenv("SEED_SOURCE", "auto")
