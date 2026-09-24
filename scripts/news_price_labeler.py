#!/usr/bin/env python3
"""
news_price_labeler.py
Additive upgrade inspired by stephenlb/algorithmic-trading-ai-python patterns:
- 5-minute aligned news-to-price joins
- Percentage-change labeling for buy/hold/sell sentiment
- Embedding/hash cache for headline deduplication

No replacement of existing news/sentiment modules. Pure additive layer.
"""
from __future__ import annotations

import hashlib, json, re
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Iterable

WORKFLOW_DIR = Path(r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\workflow")
NEWS_ALIGNED_PATH = WORKFLOW_DIR / "news_aligned_labels.json"
HEADLINE_HASH_PATH = WORKFLOW_DIR / "news_headline_hashes.json"
WINDOW_SECONDS = 300  # 5-minute buckets


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def round_down_to_5min(ts: int) -> int:
    return ts - (ts % WINDOW_SECONDS)


def headline_hash(headline: str) -> str:
    h = hashlib.sha1()
    h.update(re.sub(r"\s+", " ", headline or "").strip().lower().encode("utf-8"))
    return h.hexdigest()


def load_aligned_labels() -> dict:
    return _load_json(NEWS_ALIGNED_PATH, {"updated_at": _now_utc(), "labels": []})


def save_aligned_labels(state: dict) -> None:
    state["updated_at"] = _now_utc()
    _save_json(NEWS_ALIGNED_PATH, state)


def load_headline_hashes() -> dict:
    return _load_json(HEADLINE_HASH_PATH, {"updated_at": _now_utc(), "hashes": {}})


def save_headline_hashes(state: dict) -> None:
    state["updated_at"] = _now_utc()
    _save_json(HEADLINE_HASH_PATH, state)


def label_from_pct_change(pct: float | None, buy_threshold: float = 0.01, sell_threshold: float = -0.01) -> str:
    if pct is None:
        return "hold"
    if pct <= sell_threshold:
        return "sell"
    if pct >= buy_threshold:
        return "buy"
    return "hold"


def align_news_to_price(news_items: Iterable[dict], price_index: dict[str, float] | dict[int, float]) -> list[dict]:
    price_index_str = {str(k): float(v) for k, v in price_index.items()}
    aligned = []
    for item in news_items:
        pub_ts = item.get("pubDate_ts") or item.get("pub_ts_5m")
        if pub_ts is None:
            pub_date = item.get("pubDate") or item.get("published_at") or ""
            try:
                dt = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ")
                pub_ts = int(dt.timestamp())
            except Exception:
                continue
        pub_ts = int(pub_ts)
        idx = str(round_down_to_5min(pub_ts))
        future_idx = str(round_down_to_5min(pub_ts + WINDOW_SECONDS))
        price = price_index_str.get(idx)
        future_price = price_index_str.get(future_idx)
        if price is None or future_price is None:
            # Use provided precomputed values if available
            price = item.get("price")
            future_price = item.get("future_price")
        if price is None or future_price is None:
            continue
        pct = (future_price - price) / price if price else None
        aligned.append({
            "title": item.get("title") or item.get("headline") or "",
            "pubDate": item.get("pubDate") or item.get("published_at") or "",
            "pub_ts_5m": round_down_to_5min(pub_ts),
            "price": float(price),
            "future_price": float(future_price),
            "pct_change": pct,
            "label": label_from_pct_change(pct),
        })
    return aligned


def dedupe_headlines(items: list[dict]) -> list[dict]:
    state = load_headline_hashes()
    seen = set(state.get("hashes", {}).values())
    unique = []
    for item in items:
        h = headline_hash(item.get("title", ""))
        if h in seen:
            continue
        seen.add(h)
        unique.append(item)
    save_headline_hashes({"updated_at": _now_utc(), "hashes": {headline_hash(i.get("title", "")): headline_hash(i.get("title", "")) for i in unique}})
    return unique


def symbol_sentiment_score(symbol: str, labels: list[dict]) -> float | None:
    sym = (symbol or "").upper()
    base = sym.replace("/", "").replace("-", "")
    relevant = []
    for item in labels:
        title = (item.get("title") or "").upper()
        t = title.replace("/", "").replace("-", "")
        if sym in title or base in t:
            relevant.append(item)
    if not relevant:
        return None
    score = sum(1.0 if x.get("label") == "buy" else -1.0 if x.get("label") == "sell" else 0.0 for x in relevant)
    return max(-1.0, min(1.0, score / max(len(relevant), 1)))


if __name__ == "__main__":
    print(json.dumps({
        "headline_hashes": len(load_headline_hashes().get("hashes", {})),
        "aligned_labels": len(load_aligned_labels().get("labels", [])),
    }, indent=2))
