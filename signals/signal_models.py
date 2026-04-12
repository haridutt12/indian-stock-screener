"""
Data models for trade signals.
"""
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime


@dataclass
class TradeSignal:
    ticker: str
    name: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    risk_reward: float
    confidence: int                        # 1-5 stars
    strategy: str                          # e.g., "Trend Pullback", "Breakout"
    timeframe: Literal["INTRADAY", "SWING"]
    technical_score: float                 # 0-1
    fundamental_score: float               # 0-1
    sentiment_score: float                 # 0-1
    reasoning: str                         # Human-readable reasoning
    patterns: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    sector: str = "Unknown"
    current_price: Optional[float] = None

    @property
    def risk_amount(self) -> float:
        if self.direction == "LONG":
            return self.entry_price - self.stop_loss
        return self.stop_loss - self.entry_price

    @property
    def reward_t1(self) -> float:
        if self.direction == "LONG":
            return self.target_1 - self.entry_price
        return self.entry_price - self.target_1

    @property
    def reward_t2(self) -> float:
        if self.direction == "LONG":
            return self.target_2 - self.entry_price
        return self.entry_price - self.target_2

    @property
    def stop_loss_pct(self) -> float:
        return abs(self.risk_amount / self.entry_price) * 100

    @property
    def target_1_pct(self) -> float:
        return abs(self.reward_t1 / self.entry_price) * 100

    @property
    def target_2_pct(self) -> float:
        return abs(self.reward_t2 / self.entry_price) * 100

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "direction": self.direction,
            "entry": round(self.entry_price, 2),
            "stop_loss": round(self.stop_loss, 2),
            "target_1": round(self.target_1, 2),
            "target_2": round(self.target_2, 2),
            "risk_reward": round(self.risk_reward, 2),
            "confidence": self.confidence,
            "strategy": self.strategy,
            "timeframe": self.timeframe,
            "technical_score": round(self.technical_score, 2),
            "fundamental_score": round(self.fundamental_score, 2),
            "sentiment_score": round(self.sentiment_score, 2),
            "reasoning": self.reasoning,
            "patterns": self.patterns,
            "sector": self.sector,
            "sl_pct": round(self.stop_loss_pct, 2),
            "t1_pct": round(self.target_1_pct, 2),
            "t2_pct": round(self.target_2_pct, 2),
            "generated_at": self.generated_at.strftime("%Y-%m-%d %H:%M"),
        }


@dataclass
class MarketRegime:
    """Overall market condition classification."""
    regime: Literal["Bullish Trending", "Bearish Trending", "Ranging", "High Volatility", "Uncertain"]
    nifty_trend: str
    breadth: str          # "Advancing" / "Declining" / "Mixed"
    volatility: str       # "Low" / "Normal" / "High"
    suggested_bias: str   # "Buy dips" / "Sell rallies" / "Stay cautious" / "Trade range"
    confidence: int       # 1-5
