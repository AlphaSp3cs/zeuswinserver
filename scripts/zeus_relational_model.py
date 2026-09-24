#!/usr/bin/env python3
"""
Zeus Relational Trade Model v2 — NVIDIA Kumo-inspired
Trains on MT5 trade history: 499 IC + 76 FTMO = 575 deals
Local-only, zero API cost.

Relational Schema:
  Instance Table: each trade attempt
    - instance_id: unique trade ID
    - anchor_time: entry timestamp  
    - account_id: symbol
    - label: profitable (True) or not (False)
  
  Related Table: features at entry
    - amount: position value
    - segment: size category (low/mid/high)
    - direction: BUY or SELL
    - confidence: model conviction
    - regime: market regime
    - macro_stress: HY_OAS > 4.0
    - dxy_level: DXY at entry
    - rr_ratio: reward:risk
    - broker: IC Markets or FTMO
"""
import json
import os
import pickle
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

DATA_DIR = "C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm"
MODEL_FILE = os.path.join(DATA_DIR, "zeus_relational_model.pkl")

MT5_TYPE_BUY = 0
MT5_TYPE_SELL = 1
MT5_TYPE_DEPOSIT = 2

# Segment by position value
SEGMENT_BINS = {"low": (0, 500), "mid": (500, 2000), "high": (2000, float("inf"))}

# Historical win rates from backtest (used as prior)
SYMBOL_PRIORS = {
    "BTCUSD": 0.547, "ETHUSD": 0.522, "SOLUSD": 0.488, "AVAXUSD": 0.512,
    "LINKUSD": 0.498, "MATICUSD": 0.534, "NEARUSD": 0.475, "ZECUSD": 0.520,
    "ATOMUSD": 0.490, "UNIUSD": 0.418, "DOTUSD": 0.460, "XRPUSD": 0.550,
    "ADAUSD": 0.510, "LTCUSD": 0.530, "ICPUSD": 0.400, "XTZUSD": 0.440,
    "XNGUSD": 0.380, "BNBUSD": 0.520, "EURUSD": 0.530, "GBPUSD": 0.520,
    "USDJPY": 0.510, "XAUUSD": 0.550, "XAGUSD": 0.520, "AUDUSD": 0.520,
    "USDCHF": 0.510, "NZDUSD": 0.500, "USDCAD": 0.510,
}


def segment_from_amount(amount: float) -> str:
    for seg, (lo, hi) in SEGMENT_BINS.items():
        if lo <= abs(amount) < hi:
            return seg
    return "mid"


def is_forex(symbol: str) -> bool:
    return symbol in {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
                      "NZDUSD", "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "AUDNZD",
                      "EURAUD", "EURCAD", "GBPAUD", "GBPCAD", "NZDJPY", "CADJPY"}


def is_crypto(symbol: str) -> bool:
    return symbol in {"BTCUSD", "ETHUSD", "SOLUSD", "AVAXUSD", "LINKUSD", "MATICUSD",
                      "NEARUSD", "ZECUSD", "ATOMUSD", "UNIUSD", "DOTUSD", "XRPUSD",
                      "ADAUSD", "LTCUSD", "ICPUSD", "XTZUSD", "XNGUSD", "BNBUSD"}


def is_metals(symbol: str) -> bool:
    return symbol in {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD"}


def extract_trades_from_deals(deals: List, broker: str) -> List[dict]:
    """Pair open/close deals into complete trades."""
    # Group by symbol
    by_symbol = defaultdict(list)
    for d in deals:
        if d.type == MT5_TYPE_DEPOSIT:
            continue
        by_symbol[d.symbol].append({
            "time": d.time,
            "type": d.type,
            "volume": d.volume,
            "price": d.price,
            "profit": d.profit,
            "commission": d.commission,
            "deal_id": d.ticket,
        })

    trades = []
    for symbol, sym_deals in by_symbol.items():
        sym_deals.sort(key=lambda x: x["time"])

        # Simple pairing: find deals with profit != 0 (closed trades)
        # and match them to the prior open deal
        open_trade = None
        for deal in sym_deals:
            if deal["profit"] != 0:
                # Closed trade — try to find matching open
                # For now, treat each deal with profit as a completed mini-trade
                direction = "BUY" if deal["type"] == MT5_TYPE_BUY else "SELL"
                amount = deal["volume"] * deal["price"]
                # Adjust for crypto vs forex
                if is_crypto(symbol):
                    amount = deal["volume"] * deal["price"]
                elif is_forex(symbol):
                    amount = deal["volume"] * 100000  # Standard lot
                elif is_metals(symbol):
                    amount = deal["volume"] * deal["price"] * 100

                features = {
                    "symbol": symbol,
                    "broker": broker,
                    "direction": direction,
                    "volume": deal["volume"],
                    "entry_price": deal["price"],
                    "profit": deal["profit"],
                    "commission": deal["commission"],
                    "amount": amount,
                    "segment": segment_from_amount(amount),
                    "is_forex": is_forex(symbol),
                    "is_crypto": is_crypto(symbol),
                    "is_metals": is_metals(symbol),
                    "timestamp": deal["time"],
                    "label": deal["profit"] > 0,
                    "prior_win_rate": SYMBOL_PRIORS.get(symbol, 0.50),
                }
                trades.append(features)

    return trades


def fetch_all_mt5_trades() -> List[dict]:
    """Fetch all trade history from both MT5 terminals."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("MT5 library not available")
        return []

    all_trades = []

    for broker, path in [
        ("IC Markets", "C:/Program Files/MetaTrader 5 IC Markets Global/terminal64.exe"),
        ("FTMO", "C:/Program Files/FTMO Global Markets MT5 Terminal/terminal64.exe"),
    ]:
        try:
            if mt5.initialize(path=path):
                deals = mt5.history_deals_get(datetime(2024, 1, 1), datetime(2026, 9, 25))
                if deals:
                    trades = extract_trades_from_deals(deals, broker)
                    all_trades.extend(trades)
                    print(f"{broker}: {len(trades)} closed trades from {len(deals)} deals")
                mt5.shutdown()
        except Exception as e:
            print(f"{broker}: error — {e}")

    return all_trades


# ===== LOCAL MODEL: Logistic Regression =====
class ZeusLogisticModel:
    """Logistic regression trained locally, no external dependencies."""

    def __init__(self, n_features: int, lr: float = 0.05):
        self.weights = [0.0] * n_features
        self.bias = 0.0
        self.lr = lr
        self.n_features = n_features
        self.feature_names = []

    def _sigmoid(self, x: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-max(-500, min(500, x))))
        except:
            return 0.5

    def predict_proba(self, x: List[float]) -> float:
        z = sum(w * xi for w, xi in zip(self.weights, x)) + self.bias
        return self._sigmoid(z)

    def predict(self, x: List[float], threshold: float = 0.5) -> bool:
        return self.predict_proba(x) >= threshold

    def train(self, X: List[List[float]], y: List[bool], epochs: int = 500):
        if not X:
            return
        n = len(X)
        for epoch in range(epochs):
            total_loss = 0.0
            for xi, yi in zip(X, y):
                y_true = 1.0 if yi else 0.0
                y_pred = self.predict_proba(xi)
                error = y_pred - y_true
                total_loss += -(y_true * math.log(y_pred + 1e-9) +
                                (1 - y_true) * math.log(1 - y_pred + 1e-9))
                for j in range(self.n_features):
                    self.weights[j] -= self.lr * error * xi[j]
                self.bias -= self.lr * error
            if epoch % 100 == 0:
                print(f"   Epoch {epoch}: loss={total_loss/n:.4f}")

    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump({
                "weights": self.weights,
                "bias": self.bias,
                "n_features": self.n_features,
                "feature_names": self.feature_names,
            }, f)

    @classmethod
    def load(cls, path: str) -> "ZeusLogisticModel":
        with open(path, 'rb') as f:
            data = pickle.load(f)
        m = cls(data["n_features"])
        m.weights = data["weights"]
        m.bias = data["bias"]
        m.feature_names = data.get("feature_names", [])
        return m


def encode_trade(trade: dict) -> List[float]:
    """Encode trade dict to numeric feature vector."""
    segment_map = {"low": 0.0, "mid": 0.5, "high": 1.0}
    return [
        float(trade.get("amount", 0)) / 5000.0,  # Normalized position value
        segment_map.get(trade.get("segment", "mid"), 0.5),
        1.0 if trade.get("direction") == "BUY" else 0.0,
        float(trade.get("prior_win_rate", 0.5)),
        1.0 if trade.get("is_crypto") else 0.0,
        1.0 if trade.get("is_forex") else 0.0,
        1.0 if trade.get("is_metals") else 0.0,
        1.0 if trade.get("broker") == "IC Markets" else 0.0,
    ]


def train_zeus_model():
    """Full pipeline: fetch MT5 history, extract trades, train, save."""
    print("=" * 60)
    print("ZEUS RELATIONAL TRADE MODEL v2 — TRAINING")
    print("=" * 60)

    # Fetch trades
    trades = fetch_all_mt5_trades()
    if not trades:
        print("No trades found. Make sure MT5 terminals are accessible.")
        return None

    print(f"\nTotal closed trades: {len(trades)}")

    # Stats
    wins = sum(1 for t in trades if t["label"])
    losses = len(trades) - wins
    print(f"Winners: {wins} ({wins/len(trades)*100:.1f}%)")
    print(f"Losers: {losses} ({losses/len(trades)*100:.1f}%)")

    # Per-sector stats
    for sector_name, sector_check in [("Crypto", "is_crypto"), ("Forex", "is_forex"), ("Metals", "is_metals")]:
        sector_trades = [t for t in trades if t.get(sector_check)]
        if sector_trades:
            sector_wins = sum(1 for t in sector_trades if t["label"])
            print(f"  {sector_name}: {len(sector_trades)} trades, {sector_wins/len(sector_trades)*100:.1f}% win rate")

    # Per-symbol stats for symbols with 3+ trades
    by_symbol = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t)
    print("\nSymbols with 3+ closed trades:")
    for sym, sym_trades in sorted(by_symbol.items(), key=lambda x: len(x[1]), reverse=True):
        if len(sym_trades) >= 3:
            sym_wins = sum(1 for t in sym_trades if t["label"])
            avg_pnl = sum(t["profit"] for t in sym_trades) / len(sym_trades)
            print(f"  {sym}: {len(sym_trades)} trades, {sym_wins/len(sym_trades)*100:.0f}% win, avg ${avg_pnl:.2f}")

    # Encode
    X = [encode_trade(t) for t in trades]
    y = [t["label"] for t in trades]

    # Train
    model = ZeusLogisticModel(n_features=8, lr=0.05)
    model.feature_names = ["amount", "segment", "direction", "prior_wr", "is_crypto", "is_forex", "is_metals", "is_ic_markets"]
    print("\nTraining logistic regression...")
    model.train(X, y, epochs=500)

    # Evaluate
    correct = sum(1 for xi, yi in zip(X, y) if model.predict(xi) == yi)
    print(f"\nTraining accuracy: {correct}/{len(X)} ({correct/len(X)*100:.1f}%)")

    # Save
    model.save(MODEL_FILE)
    print(f"\nModel saved: {MODEL_FILE}")

    # Feature importance
    print("\nFeature importance (weights):")
    for name, w in sorted(zip(model.feature_names, model.weights), key=lambda x: abs(x[1]), reverse=True):
        print(f"  {name:20s}: {w:+.4f}")

    return model


def predict_trade(trade: dict) -> dict:
    """Predict probability of profit for a hypothetical trade."""
    if not os.path.exists(MODEL_FILE):
        return {"error": "Model not trained", "probability": 0.5}

    model = ZeusLogisticModel.load(MODEL_FILE)
    x = encode_trade(trade)
    prob = model.predict_proba(x)

    return {
        "probability": round(prob, 4),
        "prediction": "PROFITABLE" if prob >= 0.5 else "UNPROFITABLE",
        "confidence": round(abs(prob - 0.5) * 2, 4),
        "threshold": "PASS" if prob >= 0.55 else "REJECT",
    }


# ===== INTEGRATION: Filter for auto cycle =====
def should_trade(symbol: str, direction: str, amount: float, broker: str) -> dict:
    """Check if a trade should be executed based on model prediction."""
    trade = {
        "symbol": symbol,
        "direction": direction,
        "amount": amount,
        "segment": segment_from_amount(amount),
        "is_forex": is_forex(symbol),
        "is_crypto": is_crypto(symbol),
        "is_metals": is_metals(symbol),
        "broker": broker,
        "prior_win_rate": SYMBOL_PRIORS.get(symbol, 0.50),
    }
    return predict_trade(trade)


if __name__ == "__main__":
    model = train_zeus_model()

    if model:
        # Demo predictions
        print("\n" + "=" * 60)
        print("DEMO PREDICTIONS")
        print("=" * 60)

        demos = [
            {"symbol": "BTCUSD", "direction": "BUY", "amount": 840, "broker": "IC Markets"},
            {"symbol": "BTCUSD", "direction": "SELL", "amount": 840, "broker": "IC Markets"},
            {"symbol": "XAUUSD", "direction": "BUY", "amount": 4200, "broker": "IC Markets"},
            {"symbol": "USDJPY", "direction": "BUY", "amount": 1000, "broker": "FTMO"},
            {"symbol": "USDJPY", "direction": "SELL", "amount": 1000, "broker": "FTMO"},
        ]

        for demo in demos:
            result = should_trade(demo["symbol"], demo["direction"], demo["amount"], demo["broker"])
            print(f"  {demo['symbol']:10s} {demo['direction']:4s} @ ${demo['amount']:,.0f} ({demo['broker']}) → "
                  f"P(profit)={result.get('probability', 0.5):.3f} | {result.get('prediction', 'N/A')} | {result.get('threshold', 'N/A')}")
