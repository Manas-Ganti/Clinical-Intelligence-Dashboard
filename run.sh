#!/usr/bin/env bash
#
# Start the whole dashboard: FastAPI on :8000, Vite on :5173, browser on the UI.
#
#   ./run.sh              # start both, open the dashboard
#   ./run.sh --fresh      # delete clinical.db first, so seeding re-runs
#   ./run.sh --no-open    # don't touch the browser
#   ./run.sh --no-install # skip the dependency check (faster restarts)
#
# Ctrl+C stops both servers. Logs from both are streamed here, prefixed, so a
# backend traceback and the frontend request that caused it are readable in one
# place — the thing two terminals cost you.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# PYTHON is deliberately left unset unless the caller exports one — the
# interpreter is chosen below by which one can import the stack, not by PATH.
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

FRESH=0
OPEN_BROWSER=1
INSTALL=1

for arg in "$@"; do
  case "$arg" in
    --fresh)      FRESH=1 ;;
    --no-open)    OPEN_BROWSER=0 ;;
    --no-install) INSTALL=0 ;;
    -h|--help)    sed -n '3,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[31m==> %s\033[0m\n' "$*" >&2; exit 1; }

# --- preflight -------------------------------------------------------------- #
# A port already in use is the most common way this "starts" and then silently
# talks to something else — a stale uvicorn from an earlier run serving old code.
port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

for port in "$API_PORT" "$WEB_PORT"; do
  if port_busy "$port"; then
    echo "Port $port is already in use by:" >&2
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2
    fail "Stop it first (or set API_PORT / WEB_PORT), then re-run."
  fi
done

command -v npm >/dev/null || fail "npm not found — the frontend needs Node 18+."

# --- pick a Python that actually has the dependencies ----------------------- #
# `python3` alone is not enough: on a Mac it can be Homebrew's, the system one,
# or conda's depending on PATH order, and only one of them has this project's
# packages installed. Trusting PATH order gets you "No module named uvicorn"
# from an interpreter you didn't mean to use. So: try the plausible ones, and
# use the first that can actually import the stack.
py_works() { [ -n "$1" ] && "$1" -c "import fastapi, uvicorn, sqlalchemy, structlog" >/dev/null 2>&1; }
py_exists() { [ -n "$1" ] && { command -v "$1" >/dev/null 2>&1 || [ -x "$1" ]; }; }

CANDIDATES=""
[ -n "${PYTHON:-}" ] && CANDIDATES="$PYTHON"                              # explicit override wins
[ -n "${VIRTUAL_ENV:-}" ] && CANDIDATES="$CANDIDATES $VIRTUAL_ENV/bin/python"
[ -x "$ROOT/.venv/bin/python" ] && CANDIDATES="$CANDIDATES $ROOT/.venv/bin/python"
CANDIDATES="$CANDIDATES python3 python"
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE="$(conda info --base 2>/dev/null || true)"
  [ -n "$CONDA_BASE" ] && CANDIDATES="$CANDIDATES $CONDA_BASE/bin/python3"
fi
# conda's `bin` is often absent from a plain PATH even when its Python is the one
# holding the packages — `conda activate` is a shell function, not a PATH entry.
for guess in "$HOME/anaconda3" "$HOME/miniconda3" "$HOME/miniforge3" /opt/homebrew/anaconda3; do
  [ -x "$guess/bin/python3" ] && CANDIDATES="$CANDIDATES $guess/bin/python3"
done

PY=""
INSTALL_TARGET=""
for candidate in $CANDIDATES; do
  py_exists "$candidate" || continue
  [ -n "$INSTALL_TARGET" ] || INSTALL_TARGET="$candidate"
  if py_works "$candidate"; then PY="$candidate"; break; fi
done

if [ -z "$PY" ]; then
  [ -n "$INSTALL_TARGET" ] || fail "No usable python3 found. Set PYTHON=/path/to/python3."
  [ "$INSTALL" -eq 1 ] || fail "$INSTALL_TARGET is missing dependencies and --no-install was passed."
  say "Installing Python dependencies into $INSTALL_TARGET"
  # Not -q: if this fails (a Homebrew/system Python refusing to install into an
  # externally-managed environment, most often) the reason has to be visible.
  "$INSTALL_TARGET" -m pip install -r requirements.txt || fail \
    "pip install failed. Create a venv and re-run: python3 -m venv .venv && ./run.sh"
  py_works "$INSTALL_TARGET" || fail \
    "$INSTALL_TARGET still can't import the stack after installing — pip and this
    interpreter disagree about where packages go. Cleanest fix:
      python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && ./run.sh"
  PY="$INSTALL_TARGET"
fi

PYTHON="$PY"
say "Python   → $("$PYTHON" -c 'import sys; print(sys.executable)')"

if [ "$INSTALL" -eq 1 ] && [ ! -d frontend/node_modules ]; then
  say "Installing frontend dependencies"
  (cd frontend && npm install --silent)
fi

if [ "$FRESH" -eq 1 ]; then
  say "Removing clinical.db — it will re-seed on boot"
  rm -f clinical.db
fi

# --- start both ------------------------------------------------------------- #
# Job control, so each server lands in its own process group and can be killed
# as a *tree*. Without it, stopping the frontend kills npm and leaves the vite
# node process it spawned still holding :5173 — the next run then aborts on a
# port that nothing visible owns.
set -m

# Unbuffered, because both servers' stdout is a pipe here (the log prefixer),
# and Python block-buffers a pipe — logs would arrive in 4KB clumps or not at all.
export PYTHONUNBUFFERED=1

API_PID=""
WEB_PID=""

stop_tree() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT INT TERM
  echo
  say "Stopping"
  stop_tree "$WEB_PID"
  stop_tree "$API_PID"
  wait >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

# awk rather than sed for the prefix: it flushes per line on both BSD and GNU
# (`sed -u` / `sed -l` are mutually incompatible between the two).
prefix() { awk -v tag="$1" '{ printf "%s %s\n", tag, $0; fflush() }'; }

say "Backend  → http://localhost:$API_PORT  (docs at /docs)"
"$PYTHON" -m uvicorn backend.main:app --reload --port "$API_PORT" \
  > >(prefix $'\033[36m[api]\033[0m') 2>&1 &
API_PID=$!

# Wait for the API rather than racing it: on a fresh DB the first boot seeds the
# data, which takes long enough that the browser would otherwise open onto errors.
say "Waiting for the API to come up (seeding, if the DB is empty)…"
for _ in $(seq 1 90); do
  if curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null; then
    fail "The backend exited during startup — see the [api] output above."
  fi
  sleep 1
done
curl -fsS "http://127.0.0.1:$API_PORT/health" >/dev/null 2>&1 \
  || fail "The API never became healthy on port $API_PORT."

# Which model the Ask bar is wired to, and whether its key is actually present.
# Reported from the server so it reflects what the running process loaded.
if MODEL_JSON="$(curl -fsS "http://127.0.0.1:$API_PORT/query/model" 2>/dev/null)"; then
  MODEL="$(printf '%s' "$MODEL_JSON" | sed -n 's/.*"model":"\([^"]*\)".*/\1/p')"
  if printf '%s' "$MODEL_JSON" | grep -q '"available":true'; then
    say "Ask bar   → $MODEL (ready)"
  else
    MISSING="$(printf '%s' "$MODEL_JSON" | sed -n 's/.*"missing_credential":"\([^"]*\)".*/\1/p')"
    say "Ask bar   → $MODEL — needs $MISSING in .env; everything else works without it"
  fi
fi

say "Frontend → http://localhost:$WEB_PORT"
(cd frontend && npm run dev -- --port "$WEB_PORT") \
  > >(prefix $'\033[35m[web]\033[0m') 2>&1 &
WEB_PID=$!

if [ "$OPEN_BROWSER" -eq 1 ] && command -v open >/dev/null; then
  # Wait for Vite to bind rather than guessing at a sleep — a cold start after
  # `npm install` is slow enough that a fixed delay opens onto a refused
  # connection. `localhost` (not 127.0.0.1) on purpose: Vite binds ::1 only.
  (
    for _ in $(seq 1 60); do
      curl -fsS -o /dev/null "http://localhost:$WEB_PORT" 2>/dev/null && break
      sleep 1
    done
    open "http://localhost:$WEB_PORT" >/dev/null 2>&1 || true
  ) &
fi

say "Both running. Ctrl+C to stop."

# Exit as soon as *either* server dies, instead of leaving a half-up stack that
# looks fine until the first request fails.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done
fail "One of the servers exited — see the output above."
