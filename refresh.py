"""refresh.py — One-command local refresh.

Pulls fresh IBKR positions, runs full analysis pipeline,
generates portfolio dashboard, opens browser.
Sends Telegram alert if any held position needs attention.

Usage:
    python3 refresh.py              # full refresh
    python3 refresh.py --no-ibkr   # skip IBKR sync (use cached positions)
    python3 refresh.py --no-ai     # skip Gemini AI (faster, no API cost)
    python3 refresh.py --portfolio  # portfolio view only (no pipeline)
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

SECRETS_FILE = os.path.join("config", "secrets.json")
ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_secrets():
    try:
        with open(os.path.join(ROOT, SECRETS_FILE)) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _set_env(secrets: dict):
    """Inject secrets as env vars so main.py picks them up."""
    mapping = {
        "gemini_api_key":    "GEMINI_API_KEY",
        "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
        "telegram_chat_id":   "TELEGRAM_CHAT_ID",
        "finnhub_api_key":    "FINNHUB_API_KEY",
    }
    for secret_key, env_key in mapping.items():
        val = secrets.get(secret_key, "")
        if val and not os.environ.get(env_key):
            os.environ[env_key] = val


def _run(label: str, script: str, args: list = None) -> bool:
    cmd = [sys.executable, os.path.join(ROOT, "src", script)] + (args or [])
    print(f"\n{'─'*50}")
    print(f"▶  {label}")
    print(f"{'─'*50}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    elapsed = time.time() - t0
    ok = result.returncode == 0
    status = "✅ done" if ok else "❌ failed"
    print(f"{status}  ({elapsed:.1f}s)")
    return ok


def _check_gemini_key():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("\n⚠️  GEMINI_API_KEY not set.")
        print("   Add it to config/secrets.json:")
        print('   { "gemini_api_key": "AIza..." }')
        print("   Then re-run.")
        return False
    return True


def main():
    args      = sys.argv[1:]
    skip_ibkr = "--no-ibkr"      in args
    skip_ai   = "--no-ai"        in args
    only_port = "--portfolio"    in args

    print(f"\n{'═'*50}")
    print(f"  📊 Stock Monitor — Local Refresh")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'═'*50}")

    # Load secrets → env vars
    secrets = _load_secrets()
    _set_env(secrets)

    # Portfolio-only mode
    if only_port:
        _run("Portfolio dashboard", "portfolio_report.py")
        return

    # ── Step 1: IBKR sync ────────────────────────────────────────────────────
    if not skip_ibkr:
        ok = _run("Sync IBKR positions", "ibkr_sync.py")
        if not ok:
            print("   ⚠️  Continuing with cached positions (if any)…")
    else:
        print("\n⏩  Skipping IBKR sync (--no-ibkr)")

    # ── Step 2: Full analysis pipeline ───────────────────────────────────────
    if not _check_gemini_key():
        if "--no-ai" not in args:
            print("   Run with --no-ai to skip AI analysis, or add key to secrets.json")
            # Don't exit — run pipeline anyway (it will fail gracefully on AI parts)

    env_override = {}
    if skip_ai:
        # Pass a flag via env to skip AI calls
        env_override["SKIP_AI"] = "1"

    print(f"\n{'─'*50}")
    print("▶  Full analysis pipeline (prices + TA + AI + Telegram)")
    print(f"{'─'*50}")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "src", "main.py")],
        cwd=ROOT,
        env={**os.environ, **env_override}
    )
    elapsed = time.time() - t0
    ok = result.returncode == 0
    print(f"{'✅ done' if ok else '❌ failed'}  ({elapsed:.1f}s)")

    # ── Step 3: Portfolio dashboard ──────────────────────────────────────────
    _run("Portfolio dashboard", "portfolio_report.py")

    print(f"\n{'═'*50}")
    print("  Done. Portfolio opened in browser.")
    print(f"{'═'*50}\n")


if __name__ == "__main__":
    main()
