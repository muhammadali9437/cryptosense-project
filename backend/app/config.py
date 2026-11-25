"""All settings, read from environment variables or the .env file."""
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CryptoSense AI API"
    database_url: str = "sqlite:///./cryptosense.db"
    jwt_secret: str = "change-this-to-a-long-random-string"
    jwt_expire_minutes: int = 60 * 24 * 7
    cors_origins: str = "*"
    symbols: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT"

    # Market data (all free, no key)
    binance_base: str = "https://api.binance.com"
    binance_futures_base: str = "https://fapi.binance.com"
    fear_greed_url: str = "https://api.alternative.me/fng/"

    # Optional outside services
    cryptopanic_key: str = ""
    cryptopanic_url: str = "https://cryptopanic.com/api/developer/v2/posts/"
    whale_alert_key: str = ""
    whale_min_usd: int = 1_000_000
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    liquidation_alert_usd: float = Field(default=1_000_000, gt=0)

    # Liquidation intelligence (observed Binance forceOrder stream; see services/liquidations.py)
    liquidation_stream_url: str = "wss://fstream.binance.com/market/ws/!forceOrder@arr"
    liquidation_silence_seconds: int = Field(default=300, ge=30)   # reconnect if the stream goes quiet
    liquidation_retention_days: int = Field(default=7, ge=1, le=90)
    liq_spike_z: float = Field(default=4.0, gt=0)                   # robust z-score that counts as unusual
    liq_spike_min_usd: float = Field(default=250_000, ge=0)         # ignore "spikes" smaller than this
    liq_baseline_hours: int = Field(default=24, ge=2, le=168)
    liq_burst_events: int = Field(default=15, ge=2)                 # events for one coin within 60s
    liq_imbalance_shift_pts: float = Field(default=35, gt=0, le=100)
    liq_alert_cooldown_minutes: int = Field(default=30, ge=1)

    # Sage chatbot: Claude (Anthropic) is used first when ANTHROPIC_API_KEY is set.
    anthropic_api_key: str = ""
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = Field(default="low", pattern="^(low|medium|high|xhigh|max)$")

    # Fallback for Sage: any OpenAI-compatible API (Groq free tier by default)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-20b"

    # Quiver Quantitative: Congress + insider trades in crypto-linked US stocks (optional)
    quiver_api_key: str = ""
    quiver_base: str = "https://api.quiverquant.com/beta"
    quiver_tickers: str = "COIN,MSTR,MARA,RIOT,CLSK,HUT,HOOD,IBIT,FBTC,BITO"

    # Jev by TypeSafe AI: fast decision model (news sentiment + impact). Optional.
    typesafe_api_key: str = ""
    typesafe_url: str = "https://api.typesafe.ai/v1/systemone"
    jev_model: str = "jev-latest"

    # Sage knowledge base (TF-IDF search)
    rag_dir: str = str(ROOT / "rag_store")
    rag_top_k: int = 5

    # Background jobs
    alert_check_seconds: int = 30
    news_ingest_minutes: int = 15
    listings_refresh_hours: int = 6
    listings_window_days: int = 60

    @property
    def symbol_list(self) -> list[str]:
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]

    @property
    def quiver_ticker_list(self) -> list[str]:
        return [t.strip().upper() for t in self.quiver_tickers.split(",") if t.strip()]

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
