"""Request and response shapes (validated by Pydantic)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class HoldingIn(BaseModel):
    symbol: str = Field(min_length=5, max_length=20)
    amount: float = Field(gt=0)
    price: float = Field(gt=0, description="Price paid per coin in USD")


class LimitsIn(BaseModel):
    stop_loss_pct: float | None = Field(default=None, ge=1, le=90)
    take_profit_pct: float | None = Field(default=None, ge=1, le=1000)


class HoldingOut(BaseModel):
    symbol: str
    amount: float
    avg_buy: float
    price: float
    value: float
    pnl: float
    pnl_pct: float
    stop_loss_pct: float | None
    take_profit_pct: float | None


class PortfolioOut(BaseModel):
    value: float
    cost: float
    pnl: float
    pnl_pct: float
    holdings: list[HoldingOut]
    prices_live: bool = True  # False = at least one holding has no live price (valued at its buy price)


class AlertIn(BaseModel):
    symbol: str = Field(min_length=5, max_length=20)
    kind: Literal["above", "below", "move", "risk",
                  "liq_large", "liq_spike", "liq_long", "liq_short", "liq_imbal"]
    value: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_risk_threshold(self):
        if self.kind == "risk" and self.value > 100:
            raise ValueError("Risk alert threshold must not exceed 100.")
        if self.kind == "liq_large" and self.value < 1000:
            raise ValueError("Large-liquidation alerts need a threshold of at least $1,000.")
        if self.kind in ("liq_spike", "liq_long", "liq_short") and not 1 <= self.value <= 50:
            raise ValueError("Spike sensitivity (robust z-score) must be between 1 and 50.")
        if self.kind == "liq_imbal" and self.value > 100:
            raise ValueError("Imbalance shift must not exceed 100 percentage points.")
        return self


class RiskSimulationIn(BaseModel):
    volatility_multiplier: float = Field(ge=0.5, le=3)


class AlertOut(BaseModel):
    id: int
    symbol: str
    kind: str
    value: float
    active: bool
    triggered_at: datetime | None
    created_at: datetime


class NotificationOut(BaseModel):
    id: int
    message: str
    kind: str
    seen: bool
    created_at: datetime


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class SourceOut(BaseModel):
    n: int
    title: str
    kind: str
    url: str = ""
    published_at: str | None = None


class AgentReportOut(BaseModel):
    name: str
    status: Literal["available", "partial", "unavailable"]
    summary: str
    data: dict = Field(default_factory=dict)


class ChatOut(BaseModel):
    answer: str
    source: Literal["llm", "rules"]
    sources: list[SourceOut] = Field(default_factory=list)
    agents: list[AgentReportOut] = Field(default_factory=list)
