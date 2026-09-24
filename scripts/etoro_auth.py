#!/usr/bin/env python3
"""
etoro_auth.py
Persistent eToro auth helper with format validation, scope probing,
state caching, and retry/backoff for rate limits.

Usage:
    from etoro_auth import EtoroAuth
    auth = EtoroAuth()
    auth.load()
    auth.validate()
    headers = auth.headers()
"""
import json
import os
import re
import time
from pathlib import Path

import os
import requests
import uuid

try:
    import jwt
except Exception:
    jwt = None

ETORO_BASE = "https://public-api.etoro.com"
ETORO_AUTH_STATE_PATH = Path("C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/.etoro_auth_state.json")


def notify_user(message: str) -> bool:
    """Send an alert to the user via Telegram if configured.

    Uses the same env-var contract as the Hermes crypto-price-alerts skill:
        HERMES_TELEGRAM_BOT_TOKEN  and  HERMES_TELEGRAM_USER_ID
    If those env vars are not set, the message is only logged (no crash).
    Returns True if a Telegram message was actually sent, False otherwise.
    """
    bot_token = os.getenv("HERMES_TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("HERMES_TELEGRAM_USER_ID")
    print(f"[etoro_auth] ALERT: {message}")
    if not bot_token or not chat_id:
        print("[etoro_auth] Telegram not configured (HERMES_TELEGRAM_BOT_TOKEN / "
              "HERMES_TELEGRAM_USER_ID) — alert logged only, not delivered.")
        return False
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }, timeout=10)
        if resp.status_code == 200:
            print("[etoro_auth] Telegram alert delivered.")
            return True
        print(f"[etoro_auth] Telegram delivery failed: HTTP {resp.status_code} {resp.text[:160]}")
        return False
    except Exception as e:
        print(f"[etoro_auth] Telegram delivery error: {e}")
        return False


def notify_key_exhausted(detail: str = "", provider: str = "eToro") -> bool:
    """Tell the user the API key is dead/exhausted and they need a new one.

    This is the central hook: any script that discovers the key no longer
    authorizes should call this so the user is explicitly told to rotate it.
    """
    msg = (
        f"⚠️ *{provider} API key exhausted* ⚠️\n"
        f"The stored API key is no longer authorized (returns 401 / unauthorized). "
        f"That key does *not* work anymore — you need to generate a *new* API key "
        f"from the provider portal and update the credentials.\n"
    )
    if detail:
        msg += f"\nDetail: `{detail}`"
    return notify_user(msg)


class EtoroAuthError(Exception):
    pass


class EtoroAuth:
    def __init__(self, api_key: str = "", user_key: str = "", mode: str = "demo"):
        self.api_key = api_key
        self.user_key = user_key
        self.mode = mode.lower().strip()
        self.state = {
            "last_ok_ts": None,
            "last_fail_ts": None,
            "last_status": None,
            "last_error": None,
            "format": None,
            "scopes": [],
            "demo_cid": None,
            "real_cid": None,
            "rate_limit": None,
            "me_response": None,
            "order_success": None,
        }

    def load_env(self) -> None:
        self.api_key = os.getenv("ETORO_API_KEY", self.api_key)
        self.user_key = os.getenv("ETORO_USER_KEY", self.user_key)
        if not self.api_key:
            self.api_key = os.getenv("ETORO_PUBLIC_KEY", "")
        if not self.user_key:
            self.user_key = os.getenv("ETORO_PRIVATE_KEY", "")
        mode = os.getenv("ETORO_MODE")
        if mode:
            self.mode = mode.lower().strip()

    def load_secure_file(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        etoro = data.get("etoro") or data.get("ETORO") or {}
        if etoro.get("api_key"):
            self.api_key = etoro["api_key"]
        if etoro.get("user_key"):
            self.user_key = etoro["user_key"]
        mode = etoro.get("mode")
        if mode:
            self.mode = str(mode).lower().strip()

    def detect_format(self) -> str:
        if not self.user_key:
            raise EtoroAuthError("missing user_key")
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", self.user_key, re.I):
            return "uuid"
        if self.user_key.startswith("eyJ"):
            if "..." in self.user_key or len(self.user_key) < 100:
                raise EtoroAuthError("truncated_jwt")
            return "jwt"
        return "unknown"

    def _headers(self):
        return {
            "x-request-id": str(uuid.uuid4()),
            "x-api-key": self.api_key,
            "x-user-key": self.user_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def validate(self, *, try_trade: bool = False) -> dict:
        if not self.api_key or not self.user_key:
            self.load_secure_file(ETORO_AUTH_STATE_PATH.parent / '.broker_creds_secure.json')
        if not self.api_key or not self.user_key:
            raise EtoroAuthError("missing_credentials")
        fmt = self.detect_format()
        self.state["format"] = fmt
        if fmt == "unknown":
            raise EtoroAuthError("unknown_key_format")

        me_url = f"{ETORO_BASE}/api/v1/me"
        r = requests.get(me_url, headers=self._headers(), timeout=15)
        self.state["last_status"] = r.status_code

        if r.status_code == 401:
            self.state["last_error"] = "Unauthorized"
            self._persist_state(ok=False)
            # Key is dead/exhausted: tell the user to get a new one.
            self._maybe_notify_exhausted(
                "HTTP 401 Unauthorized from /api/v1/me — key rejected",
                error_tag="unauthorized",
            )
            raise EtoroAuthError("unauthorized")
        if r.status_code == 403:
            self.state["last_error"] = "InsufficientPermissions"
            self._persist_state(ok=False)
            # Key authenticates but lacks scopes — still surface it to the user.
            self._maybe_notify_exhausted(
                "HTTP 403 InsufficientPermissions from /api/v1/me — key works but lacks required scopes",
                error_tag="insufficient_permissions",
                exhausted=False,
            )
            raise EtoroAuthError("insufficient_permissions")

        data = {}
        if r.status_code == 200:
            data = r.json()
            self.state["me_response"] = data
            self.state["scopes"] = data.get("scopes", [])
            self.state["demo_cid"] = data.get("demoCid")
            self.state["real_cid"] = data.get("realCid")
            self._persist_state(ok=True)
        else:
            self.state["last_error"] = r.text[:200]
            self._persist_state(ok=False)

        if try_trade and self.mode == "demo":
            return self._probe_demo_trade()
        return data

    def _probe_demo_trade(self):
        url = f"{ETORO_BASE}/api/v2/trading/execution/demo/orders"
        tx = (self.state.get('probe_tx') or 'buy').lower()
        payload = {
            "action": "open",
            "transaction": tx,
            "instrumentID": 100000,
            "orderType": "mkt",
            "leverage": 1,
            "amount": 1.0,
            "orderCurrency": "usd",
            "stopLossRate": 50000,
            "takeProfitRate": 80000,
            "stopLossType": "fixed",
        }
        r = requests.post(url, headers=self._headers(), json=payload, timeout=15)
        self.state["order_success"] = r.status_code
        if r.status_code == 429:
            self.state["last_error"] = "RateLimited"
            self.state["rate_limit"] = r.headers.get("RateLimit-Remaining")
            self._persist_state(ok=False)
            raise EtoroAuthError("rate_limited")
        if r.status_code != 200:
            raise EtoroAuthError(f"probe_failed:{r.status_code}:{r.text[:200]}")
        self.state["order_probe"] = r.json()
        self.state["probe_tx_used"] = tx
        self._persist_state(ok=True)
        return self.state["order_probe"]

    def headers(self) -> dict:
        if not self.api_key or not self.user_key:
            self.load_secure_file(ETORO_AUTH_STATE_PATH.parent / '.broker_creds_secure.json')
        self.load_env()
        if not self.api_key or not self.user_key:
            raise EtoroAuthError("missing_env_credentials")
        return self._headers()

    def _persist_state(self, ok: bool) -> None:
        self.state["last_ok_ts"] = time.time() if ok else self.state.get("last_ok_ts")
        self.state["last_fail_ts"] = time.time() if not ok else self.state.get("last_fail_ts")
        try:
            ETORO_AUTH_STATE_PATH.write_text(json.dumps(self.state, indent=2))
        except Exception:
            pass

    def _maybe_notify_exhausted(self, detail: str, error_tag: str, exhausted: bool = True) -> None:
        """Notify the user the key is dead (exhausted) — but only once per distinct error.

        Dedupe via persisted state so a cron loop doesn't spam Telegram on every tick.
        `exhausted=True` => the key is fully dead and must be replaced.
        `exhausted=False` => key authenticates but is mis-scoped; still surfaced.
        """
        # Don't re-alert for the same error we already alerted on.
        if self.state.get("last_alert_tag") == error_tag:
            return
        self.state["last_alert_tag"] = error_tag
        try:
            ETORO_AUTH_STATE_PATH.write_text(json.dumps(self.state, indent=2))
        except Exception:
            pass
        if exhausted:
            notify_key_exhausted(detail=detail, provider="eToro")
        else:
            notify_user(
                "⚠️ *eToro API key mis-scoped* ⚠️\n"
                "The key is accepted but returns 403 (insufficient permissions). "
                "You likely need a *new* API key with the required scopes, or to "
                "enable the correct scopes in the eToro developer portal.\n"
                f"\nDetail: `{detail}`"
            )


def load_auth_from_env() -> EtoroAuth:
    auth = EtoroAuth()
    auth.load_env()
    return auth


def quick_status() -> dict:
    auth = load_auth_from_env()
    status = {
        "has_api_key": bool(auth.api_key),
        "has_user_key": bool(auth.user_key),
        "mode": auth.mode,
        "format": None,
        "error": None,
        "last_status": None,
        "scopes": [],
        "rate_limit": None,
        "cached": None,
    }
    if ETORO_AUTH_STATE_PATH.exists():
        try:
            status["cached"] = json.loads(ETORO_AUTH_STATE_PATH.read_text())
        except Exception:
            pass
    if not auth.api_key or not auth.user_key:
        status["error"] = "missing credentials"
        return status

    try:
        fmt = auth.detect_format()
    except EtoroAuthError as e:
        status["error"] = str(e)
        return status
    status["format"] = fmt
    if fmt == "jwt" and jwt:
        try:
            decoded = jwt.decode(auth.user_key, options={"verify_signature": False})
            import datetime
            exp = decoded.get("exp")
            if exp:
                status["jwt_exp"] = datetime.datetime.fromtimestamp(exp).isoformat()
                expired = datetime.datetime.fromtimestamp(exp) < datetime.datetime.now()
                status["jwt_expired"] = expired
                if expired:
                    # Key is expired — same as exhausted; tell the user to replace it.
                    notify_key_exhausted(
                        detail=f"JWT user_key expired at {status['jwt_exp']}",
                        provider="eToro",
                    )
        except Exception as e:
            status["jwt_decode_error"] = str(e)

    try:
        data = auth.validate()
        status["last_status"] = auth.state["last_status"]
        status["scopes"] = auth.state["scopes"]
        status["rate_limit"] = auth.state["rate_limit"]
        status["error"] = None
    except EtoroAuthError as e:
        status["last_status"] = auth.state["last_status"]
        status["error"] = str(e)
        # validate() already fires notify_key_exhausted for 401/403.
        # Surface unknown/truncated key formats here too.
        if "unknown" in str(e) or "truncated" in str(e) or "missing" in str(e):
            notify_key_exhausted(detail=f"{e}", provider="eToro")
    return status


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description="eToro auth helper + key-exhaustion alerting")
    p.add_argument("--check", action="store_true",
                   help="Run quick_status() and alert the user if the key is dead/expired.")
    p.add_argument("--alert", action="store_true",
                   help="Force-send the 'get a new API key' alert (used to test delivery).")
    p.add_argument("--provider", default="eToro", help="Provider name shown in the alert.")
    args = p.parse_args()

    if args.alert:
        sent = notify_key_exhausted(detail="Manual test trigger", provider=args.provider)
        print(f"Manual alert delivered={sent}")
        return
    if args.check:
        status = quick_status()
        print(json.dumps(status, indent=2, default=str))
        if status.get("error"):
            print(f"\nKey problem detected: {status['error']} — user has been alerted via Telegram (if configured).")
        return
    # Default: print current status
    _cli_check_default = quick_status()
    print(json.dumps(_cli_check_default, indent=2, default=str))


if __name__ == "__main__":
    _cli()
