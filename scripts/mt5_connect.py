#!/usr/bin/env python3
"""
mt5_connect.py — isolated per-broker MT5 connector for this workspace.

Rule:
- Prefer path-first bind to the already-running terminal session.
- Do NOT call mt5.login(...) against a healthy logged-in session; that can
  reset demo auth state and cause the terminal to log out.
- Only relogin when identity check fails or init reports explicit auth failure.
- Hard terminal isolation: FTMO LEFT and Capital RIGHT never share creds or
  login state.

Layout:
  Desktop\OuroTaurus Trade Firm\allapi2026.txt  -> password store
  Desktop\OuroTaurus Trade Firm\scripts\mt5_connect.py  -> this module
"""
import os
import sys
import MetaTrader5 as mt5

if __package__ in (None, ""):
    _DIR = os.path.dirname(os.path.abspath(__file__))
    if _DIR not in sys.path:
        sys.path.insert(0, _DIR)

KNOWN_BROKERS = {
    "ftmo": {
        "name": "FTMO LEFT",
        "terminal_path": os.environ.get('FTMO_MT5_TERMINAL', r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"),
        "login": int(os.environ.get('FTMO_MT5_LOGIN', '1514520320')),
        "server": os.environ.get('FTMO_MT5_SERVER', 'FTMO-Demo'),
        "password_prefix": "FTMO MT5 login",
    },
    "capital": {
        "name": "Capital RIGHT (IC Markets)",
        "terminal_path": os.environ.get('CAPITAL_MT5_TERMINAL', r"C:\Program Files\MetaTrader 5 IC Markets Global\terminal64.exe"),
        "login": int(os.environ.get('CAPITAL_MT5_LOGIN', '53038440')),
        "server": os.environ.get('CAPITAL_MT5_SERVER', 'ICMarketsSC-Demo'),
        "password_prefix": "Capital MT5 login",
    },
}


def connect(profile: str = "ftmo") -> "mt5":
    if profile not in KNOWN_BROKERS:
        raise ValueError(f"Unknown MT5 profile={profile!r}. Known: {sorted(KNOWN_BROKERS)}")

    cfg = KNOWN_BROKERS[profile]
    terminal_path = cfg["terminal_path"]
    expected_login = cfg["login"]
    expected_server = cfg["server"]

    initialized = mt5.initialize(terminal_path)
    last_err = tuple(mt5.last_error() or (None, None))

    if not initialized:
        try:
            info = mt5.account_info()
        except Exception:
            info = None
        if info is not None and getattr(info, "login", None) == expected_login:
            initialized = True

    if initialized:
        try:
            info = mt5.account_info()
        except Exception:
            info = None

        login_mismatch = info is None or getattr(info, "login", None) != expected_login
        server_mismatch = info is None or getattr(info, "server", None) != expected_server
        # If expected credentials are not configured (defaults), trust the running session
        if not expected_login or not expected_server:
            needs_auth = False
        elif info is not None and not login_mismatch and not server_mismatch:
            # Running session is valid; don't re-login on spurious initialize errors
            needs_auth = False
        else:
            needs_auth = login_mismatch or server_mismatch or last_err in (
                (-7, "Unsupported authorization mode, OTP or certificate password needed"),
                (-6, "Terminal: Authorization failed"),
            )
            if needs_auth and not login_mismatch:
                needs_auth = False

        if needs_auth:
            _do_login(profile, cfg, terminal_path)
    else:
        _do_login(profile, cfg, terminal_path)

    try:
        info = mt5.account_info()
    except Exception:
        info = None
    if info is None or getattr(info, "login", None) is None:
        raise RuntimeError(
            f"{cfg['name']} connect failed: no session, "
            f"last_err={mt5.last_error()}"
        )

    # When expected credentials are not configured (defaults), trust the running session
    if not expected_login or not expected_server:
        return mt5

    if getattr(info, "login", None) != expected_login:
        raise RuntimeError(
            f"{cfg['name']} connect failed: expected login={expected_login}, "
            f"got {getattr(info, 'login', None)}, server={getattr(info, 'server', None)}, "
            f"last_err={mt5.last_error()}"
        )

    return mt5


def _do_login(profile: str, cfg: dict, terminal_path: str) -> None:
    print(f"[mt5_connect] profile={profile} re-login because of mismatch/auth failure")
    try:
        mt5.shutdown()
    except Exception:
        pass
    ok = mt5.initialize(terminal_path)
    if not ok:
        raise RuntimeError(
            f"{cfg['name']} initialize failed before login: {mt5.last_error()}"
        )
    password = _extract_mt5_password(profile)
    if password is None:
        raise RuntimeError(
            f"{cfg['name']} password missing. "
            "Refusing blind login to avoid cross-broker credential contamination."
        )
    login_ok = mt5.login(cfg["login"], password=password, server=cfg["server"])
    if not login_ok:
        raise RuntimeError(
            f"{cfg['name']} login failed: {mt5.last_error()}. Check vault creds."
        )


def _extract_mt5_password(profile: str) -> str | None:
    candidates = [
        os.path.expanduser(r"~\Desktop\OuroTaurus Trade Firm\allapi2026.txt"),
        os.path.expanduser(r"~\Desktop\allapi2026.txt"),
    ]
    prefix = KNOWN_BROKERS.get(profile, {}).get("password_prefix")
    if not prefix:
        return None
    for creds_path in candidates:
        if not os.path.exists(creds_path):
            continue
        with open(creds_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s.startswith(prefix):
                    parts = s.split()
                    for i, p in enumerate(parts):
                        if p.lower() == "password" and i + 1 < len(parts):
                            return parts[i + 1]
    return None


def shutdown() -> None:
    try:
        mt5.shutdown()
    except Exception:
        pass
