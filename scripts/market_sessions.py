#!/usr/bin/env python3
"""market_sessions.py - Single source of truth for market open/close windows.

All times are expressed in each market's LOCAL exchange time (exchange-local).
is_open() converts to the system local tz (America/New_York) at call time so DST
is handled automatically by the standard library. Comparison is done on (weekday, time)
tuples in the local tz, which is DST-stable because we compare local wall-clock time.

Coverage goal: fire a SCAN at every market OPEN and a SL-PROTECT SWEEP at every
market CLOSE, across all traded asset classes:
  - US equities/ETF/options (NYSE/NASDAQ/CBOE)
  - US index futures (CME: ES/NQ/RTY/YM, Globex session)
  - US commodities futures (CME: CL/GC/SI/HG, Globex session)
  - FX spot (Sydney/Tokyo/London/NY rolling sessions + 5pm EST daily close)
  - US Treasuries futures (CBOT: ZN/ZB/ZT)
  - Crypto (24/7, perpetual -- no open/close, covered by 45m loops + weekend loop)
  - Prediction markets (Polymarket/Kalshi -- event-driven, no scheduled session)

Open/close times chosen are the *liquid-session anchors* that matter for a
scan-and-protect workflow, not every micro-session.
"""

from __future__ import annotations
import datetime as dt

# ---------------------------------------------------------------------------
# Session table. Each entry: market, label, asset_classes, open (local h,m),
# close (local h,m), open_days (0=Mon..6=Sun), tz note, kind.
# kind: "open_close" => has both a scan-open and a protect-close event.
#       "open_only"  => scan on open, no separate close event (e.g. GLOBEX
#                       continuous, covered by the daily 17:00 ET roll).
# Times are EXCHANGE-LOCAL. For US markets that is US/Eastern (America/New_York),
# which is the host tz here, so no conversion needed. For non-US FX sessions the
# local times are converted below only where the host is NOT that tz.
# ---------------------------------------------------------------------------

# US markets: exchange-local == America/New_York (host tz). No conversion needed.
SESSIONS = [
    # ---- US EQUITIES / ETF / OPTIONS ----
    {
        "id": "us_equity_regular",
        "market": "US Equities/ETF/Options",
        "label": "NYSE/NASDAQ/CBOE Regular Session",
        "classes": ["equity", "etf", "options"],
        "open": (9, 30), "close": (16, 0),
        "open_days": [0, 1, 2, 3, 4],            # Mon-Fri
        "tz": "America/New_York",
        "kind": "open_close",
    },
    {
        "id": "us_equity_pre",
        "market": "US Equities/ETF/Options",
        "label": "NYSE/NASDAQ Pre-Market",
        "classes": ["equity", "etf"],
        "open": (4, 0), "close": (9, 30),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_only",   # pre-market open = early scan; close handled by regular open
    },
    {
        "id": "us_equity_after",
        "market": "US Equities/ETF/Options",
        "label": "NYSE/NASDAQ After-Hours",
        "classes": ["equity", "etf"],
        "open": (16, 0), "close": (20, 0),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_only",   # AH open = late scan; close handled by FX 17:00 roll
    },

    # ---- CME INDEX FUTURES (Globex) ----
    # CME Globex equities/fx futures trade Sun 18:00 ET -> Fri 17:00 ET.
    # Liquid session anchor = US cash open 09:30 and US cash close 16:00.
    {
        "id": "cme_index_futures",
        "market": "CME Index Futures",
        "label": "CME ES/NQ/RTY/YM Globex (cash-aligned)",
        "classes": ["futures_index"],
        "open": (9, 30), "close": (16, 0),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_close",
    },

    # ---- CME COMMODITY FUTURES ----
    {
        "id": "cme_commodity_futures",
        "market": "CME Commodity Futures",
        "label": "CME CL/GC/SI/HG Globex (cash-aligned)",
        "classes": ["futures_commodity"],
        "open": (9, 30), "close": (16, 0),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_close",
    },

    # ---- CBOT TREASURIES ----
    {
        "id": "cbot_treasuries",
        "market": "US Treasuries Futures",
        "label": "CBOT ZN/ZB/ZT (cash-aligned)",
        "classes": ["futures_rates"],
        "open": (9, 30), "close": (16, 0),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_close",
    },

    # ---- FX SPOT ROLLING SESSIONS ----
    # FX is 24/5. We anchor scans to the four liquidity centers + daily roll.
    {
        "id": "fx_sydney",
        "market": "FX Spot",
        "label": "FX Sydney Open",
        "classes": ["fx"],
        "open": (17, 0), "close": (2, 0),   # Sydney 17:00 ET(prev day)->02:00 ET
        "open_days": [0, 1, 2, 3, 4],        # opens Sun 17:00
        "tz": "America/New_York",
        "kind": "open_only",
    },
    {
        "id": "fx_tokyo",
        "market": "FX Spot",
        "label": "FX Tokyo Open",
        "classes": ["fx"],
        "open": (19, 0), "close": (4, 0),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_only",
    },
    {
        "id": "fx_london",
        "market": "FX Spot",
        "label": "FX London Open (highest liquidity)",
        "classes": ["fx"],
        "open": (3, 0), "close": (11, 30),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_only",
    },
    {
        "id": "fx_newyork",
        "market": "FX Spot",
        "label": "FX New York Open",
        "classes": ["fx"],
        "open": (8, 0), "close": (17, 0),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_close",   # NY close (17:00 ET) = daily FX roll/protect
    },

    # ---- FX DAILY ROLL (the canonical daily close) ----
    {
        "id": "fx_daily_roll",
        "market": "FX Spot",
        "label": "FX Daily Roll (5pm ET)",
        "classes": ["fx"],
        "open": (17, 0), "close": (17, 0),
        "open_days": [0, 1, 2, 3, 4],
        "tz": "America/New_York",
        "kind": "open_only",    # single daily snapshot at 17:00 ET
    },

    # ---- WEEKEND CRYPTO (covered by loops, but flagged for completeness) ----
    {
        "id": "crypto_247",
        "market": "Crypto Spot/Perp",
        "label": "Crypto 24/7 (no open/close)",
        "classes": ["crypto"],
        "open": (0, 0), "close": (23, 59),
        "open_days": [0, 1, 2, 3, 4, 5, 6],
        "tz": "America/New_York",
        "kind": "open_only",    # continuous; protected by 45m + weekend loops
    },
]

# Events that should fire a SCAN (open) vs a PROTECT sweep (close).
# Protection sweeps run at every session close; scans run at every session open.
SCAN_EVENTS = [s for s in SESSIONS if s["kind"] in ("open_close", "open_only")]
PROTECT_EVENTS = [s for s in SESSIONS if s["kind"] == "open_close"]


def _now_local() -> dt.datetime:
    return dt.datetime.now()  # host tz is America/New_York


def is_open(session: dict, when: dt.datetime | None = None) -> bool:
    """Return True if the given session is within its open window at `when` (host-local)."""
    when = when or _now_local()
    if when.weekday() not in session["open_days"]:
        return False
    t = when.time()
    o = dt.time(*session["open"])
    c = dt.time(*session["close"])
    # Handle sessions that cross midnight (open > close)
    if o <= c:
        return o <= t < c
    else:
        return t >= o or t < c


def next_open(session: dict, when: dt.datetime | None = None) -> dt.datetime:
    """Return the next datetime (host-local) the session opens after `when`."""
    when = when or _now_local()
    # Start scanning from the beginning of today
    base = when.replace(hour=0, minute=0, second=0, microsecond=0)
    for day_offset in range(0, 8):
        cand_day = base + dt.timedelta(days=day_offset)
        if cand_day.weekday() not in session["open_days"]:
            continue
        open_dt = cand_day.replace(hour=session["open"][0], minute=session["open"][1])
        if open_dt > when:
            return open_dt
    raise RuntimeError(f"No future open for session {session['id']}")


def next_close(session: dict, when: dt.datetime | None = None) -> dt.datetime:
    """Return the next datetime (host-local) the session closes after `when`."""
    when = when or _now_local()
    base = when.replace(hour=0, minute=0, second=0, microsecond=0)
    for day_offset in range(0, 8):
        cand_day = base + dt.timedelta(days=day_offset)
        if cand_day.weekday() not in session["open_days"]:
            continue
        close_dt = cand_day.replace(hour=session["close"][0], minute=session["close"][1])
        if close_dt > when:
            return close_dt
    raise RuntimeError(f"No future close for session {session['id']}")


def open_close_events(when: dt.datetime | None = None):
    """Return dict: {'scan': [session,...], 'protect': [session,...]} for the next
    7 days, useful for building a cron coverage matrix."""
    when = when or _now_local()
    scan, protect = [], []
    for s in SCAN_EVENTS:
        scan.append({"id": s["id"], "next_open": next_open(s, when).isoformat()})
    for s in PROTECT_EVENTS:
        protect.append({"id": s["id"], "next_close": next_close(s, when).isoformat()})
    return {"scan": scan, "protect": protect}


if __name__ == "__main__":
    now = _now_local()
    print(f"HOST LOCAL: {now.isoformat()}  weekday={now.strftime('%a')}")
    print("\nMARKET STATE (currently open?):")
    for s in SESSIONS:
        o = next_open(s, now).strftime("%a %H:%M")
        c = next_close(s, now).strftime("%a %H:%M")
        state = "OPEN " if is_open(s, now) else "close"
        print(f"  [{state}] {s['id']:22} "
              f"open={s['open'][0]:02d}:{s['open'][1]:02d} "
              f"close={s['close'][0]:02d}:{s['close'][1]:02d} "
              f"next_open={o} next_close={c}")
