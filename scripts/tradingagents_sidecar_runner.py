#!/usr/bin/env python3
"""
TradingAgents sidecar runner.
Reads OuroTaurus setups, attempts TA research memo, writes workflow artifacts.
No broker mutation. Advisors only.
Graceful fallback if TradingAgents deps are missing.
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone

try:
    from tradingagents.agents.trader.trader import TraderAgent
    from tradingagents.agents.researchers.bull_researcher import BullResearcher
    from tradingagents.agents.researchers.bear_researcher import BearResearcher
    from tradingagents.agents.risk_mgmt.conservative_debator import ConservativeDebator
    from tradingagents.agents.risk_mgmt.aggressive_debator import AggressiveDebator
    from tradingagents.llm_clients import create_llm_client
    from tradingagents.default_config import DEFAULT_CONFIG
    TA_AVAILABLE = True
except Exception as e:
    TA_AVAILABLE = False
    TA_IMPORT_ERROR = str(e)

BASE_FIRM = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm")
WORKFLOW = BASE_FIRM / "workflow"
POLICY = WORKFLOW / "tradingagents_sidecar_policy.md"


def latest_file(pattern: str):
    files = sorted(WORKFLOW.glob(pattern))
    return files[-1] if files else None


def load_setups():
    sources = [
        "all_sector_final_setups_*.json",
        "scandata/setups.json",
        "loads/Scan protocol/sector_scan_results_*.json",
        "workflow/dayshift_cycle_*.json",
        "workflow/nightshift_cycle_*.json",
    ]
    for pattern in sources:
        if "*" in pattern:
            p = latest_file(pattern)
        else:
            p = WORKFLOW / pattern
            if not p.exists():
                p = BASE_FIRM / pattern
        if p and p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("setups", data.get("assets", data.get("candidates", [])))
            except Exception:
                continue
    return []


def top_setups(setups, max_items=5):
    ranked = sorted(
        [s for s in setups if isinstance(s, dict) and s.get("executable_flag") is not False],
        key=lambda s: s.get("conviction", 0),
        reverse=True,
    )
    return ranked[:max_items]


def fallback_memo(s):
    return (
        "TRADINGAGENTS_NOT_INSTALLED. "
        "No broker-impacting decision made. "
        f"Input ticker={s.get('ticker') or s.get('symbol')}, "
        f"ourotaurus_direction={s.get('direction') or s.get('call')}, "
        f"conviction={s.get('conviction')}"
    )


def run_sidecar(limit=5):
    setups = load_setups()
    chosen = top_setups(setups, max_items=limit)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    out = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tradingagents_available": TA_AVAILABLE,
        "import_error": None if TA_AVAILABLE else TA_IMPORT_ERROR,
        "source_setups_file": str(latest_file("all_sector_final_setups_*.json")),
        "policy": str(POLICY),
        "input_count": len(setups),
        "selected_count": len(chosen),
        "results": [],
        "status": "ok" if TA_AVAILABLE else "fallback",
    }

    if not TA_AVAILABLE:
        for s in chosen:
            out["results"].append({
                "source_setup_id": s.get("id") or s.get("ticker"),
                "ticker": s.get("ticker") or s.get("symbol"),
                "ourotaurus_direction": s.get("direction") or ("buy" if s.get("call") else "sell"),
                "ourotaurus_size": s.get("position_pct") or s.get("size") or 1.0,
                "ta_bull_score": None,
                "ta_bear_score": None,
                "ta_risk_flag": None,
                "ta_memo": fallback_memo(s),
                "final_direction": s.get("direction") or ("buy" if s.get("call") else "sell"),
                "final_size": s.get("position_pct") or s.get("size") or 1.0,
                "winner": "ourotaurus",
                "override_approved_by": None,
                "status": "ADOPTED",
            })
        json_path = WORKFLOW / f"tradingagents_conviction_memo_{ts}.json"
        md_path = WORKFLOW / f"tradingagents_conviction_memo_{ts}.md"
        json_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        md_path.write_text(
            f"# TradingAgents Conviction Memo {ts}\n\n"
            f"Status: fallback\n"
            f"Error: {TA_IMPORT_ERROR}\n\n"
            f"Selected: {len(chosen)} setups; OuroTaurus remains source of truth.\n",
            encoding="utf-8",
        )
        return out, json_path, md_path

    llm_cfg = DEFAULT_CONFIG.copy()
    llm_cfg["llm_provider"] = os.environ.get("TRADINGAGENTS_LLM_PROVIDER", "openai")
    llm_cfg["deep_think_llm"] = os.environ.get("TRADINGAGENTS_DEEP_THINK_LLM", "gpt-5.5")
    llm_cfg["quick_think_llm"] = os.environ.get("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-5.4-mini")
    llm_cfg["temperature"] = 0.2

    deep = create_llm_client(provider=llm_cfg["llm_provider"], model=llm_cfg["deep_think_llm"]).get_llm()
    quick = create_llm_client(provider=llm_cfg["llm_provider"], model=llm_cfg["quick_think_llm"]).get_llm()

    for s in chosen:
        context = json.dumps({
            "ticker": s.get("ticker") or s.get("symbol"),
            "sector": s.get("sector"),
            "ourotaurus_direction": s.get("direction") or ("buy" if s.get("call") else "sell"),
            "ourotaurus_size": s.get("position_pct") or s.get("size") or 1.0,
            "conviction": s.get("conviction"),
            "entry": s.get("entry"),
            "stop_loss": s.get("stop_loss"),
            "take_profit_t1": s.get("take_profit_t1"),
            "rsi": s.get("rsi"),
            "broker": s.get("broker"),
            "news_sentiment": s.get("news_sentiment"),
            "prediction_sentiment": s.get("prediction_sentiment"),
        }, ensure_ascii=True)

        memo = ""
        try:
            bull = BullResearcher(quick, context)
            bear = BearResearcher(quick, context)
            risk = ConservativeDebator(quick, context)
            bull_out = bull.run() if hasattr(bull, "run") else str(bull)
            bear_out = bear.run() if hasattr(bear, "run") else str(bear)
            risk_out = risk.run() if hasattr(risk, "run") else str(risk)
            memo = f"BULL:\n{bull_out}\n\nBEAR:\n{bear_out}\n\nRISK:\n{risk_out}"
        except Exception as e:
            memo = f"research_error: {e}"

        out["results"].append({
            "source_setup_id": s.get("id") or s.get("ticker"),
            "ticker": s.get("ticker") or s.get("symbol"),
            "ourotaurus_direction": s.get("direction") or ("buy" if s.get("call") else "sell"),
            "ourotaurus_size": s.get("position_pct") or s.get("size") or 1.0,
            "ta_bull_score": None,
            "ta_bear_score": None,
            "ta_risk_flag": None,
            "ta_memo": memo,
            "final_direction": s.get("direction") or ("buy" if s.get("call") else "sell"),
            "final_size": s.get("position_pct") or s.get("size") or 1.0,
            "winner": "ourotaurus",
            "override_approved_by": None,
            "status": "ADOPTED",
        })

    json_path = WORKFLOW / f"tradingagents_conviction_memo_{ts}.json"
    md_path = WORKFLOW / f"tradingagents_conviction_memo_{ts}.md"
    json_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    lines = [f"# TradingAgents Conviction Memo {ts}", "", f"Selected: {len(chosen)} of {len(setups)} setups", ""]
    for r in out["results"]:
        lines.extend([
            f"## {r['ticker']}",
            f"- OuroTaurus: {r['ourotaurus_direction']} size={r['ourotaurus_size']}",
            f"- Winner: {r['winner']} | Status: {r['status']}",
            f"- Memo:\n```\n{r['ta_memo'][:4000]}\n```",
            ""
        ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return out, json_path, md_path


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    out, jp, mp = run_sidecar(limit=n)
    print(json.dumps({"json": str(jp), "md": str(mp), "selected": out["selected_count"], "status": out["status"]}, indent=2))
