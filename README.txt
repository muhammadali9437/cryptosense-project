CryptoSense AI  -  kaise chalayein
==================================

PEHLI DAFA (sirf ek baar):
  1. Is folder ko  C:\CryptoSense  mein rakhein   (OneDrive ya Desktop mein nahi)
  2. SETUP.bat par double click karein  (internet chahiye, 10-20 minute)

HAR BAAR:
  START.bat par double click karein.
  Ye pehle backend ready hone ka wait karta hai, phir Flutter/Chrome start karta hai.
  Pehli Chrome launch mein ek minute lag sakta hai; dono service windows khuli rehne dein.
  Backend:  http://127.0.0.1:8000/docs
  Frontend: Chrome khud khulega

RISK COPILOT:
  Overview par model consensus, similar historical market periods aur volatility what-if dekhein.
  Alerts mein "Risk reaches" select karke 1-100% threshold par alert set karein.
  Historical outcomes misaal hain, prediction nahi; risk alerts live market data par chalte hain.
  Overview ke Risk Copilot mein Binance UTC Previous Day, Asia, London aur Prior Week levels aur ATR distance dekhein.
  Diye gaye hit-rates ko BTC/ETH par validate nahi kiya gaya; ye AI probability ya buy/sell signal mein shamil nahi.
  CryptoSentinel/Sage 6 specialists (market, derivatives, on-chain, news/sentiment, risk, explanation) coordinate karta hai.
  Chat replies ke neeche har specialist ka status aur analysis dekhein.
  Binance liquidation stream pehle se use hoti hai. Crypto whale feed ke liye optional WHALE_ALERT_KEY
  (Whale Alert; Quiver Quant crypto transfer feed nahi hai, sirf crypto stocks); LLM ke liye ANTHROPIC_API_KEY ya LLM_API_KEY.
  Baghair in keys ke specialist status "unavailable" dikhate hain.

TELEGRAM ALERTS (optional):
  1. Telegram par @BotFather se /newbot karke bot banayein; naya bot apne personal chat mein /start karein.
  2. Bot token aur apna chat ID backend\.env mein TELEGRAM_BOT_TOKEN aur TELEGRAM_CHAT_ID ke neeche set karein.
     Chat ID @userinfobot se mil sakti hai. In values ko chat, README, ya GitHub par share na karein.
  3. TEST_TELEGRAM.bat chalayein. Ye sirf ek test message bhejta hai aur token ko screen par nahi dikhata.
  Backend chalta ho to price/risk/portfolio-limit alerts ke saath tracked coins ki bari Binance
  liquidations aur configured Whale Alert transfers bhi Telegram par aayenge.
  LIQUIDATION_ALERT_USD default $1,000,000 hai. Ek deployment ka ek operator chat configured hota hai.

RAILWAY BACKEND DEPLOYMENT:
  Railway project mein backend\ ko service Root Directory set karein; backend\railway.toml start command deta hai.
  Railway Postgres attach karke DATABASE_URL, JWT_SECRET, TELEGRAM_BOT_TOKEN aur TELEGRAM_CHAT_ID variables set karein.
  Optional ANTHROPIC_API_KEY, QUIVER_API_KEY, WHALE_ALERT_KEY aur LLM_API_KEY bhi Railway Variables mein set kar sakte hain.
  Flutter web build ko `--dart-define=API_URL=https://<your-backend>.up.railway.app` dein.
  Keys ko source control mein commit na karein. Ye app analysis/alerts only hai; order execution enabled nahi.

AI MODELS:
  TRAIN_AI.bat  -> XGBoost + LightGBM ko Binance ke 10 saal tak ke data par train karta hai.
  (Sirf wo ghante use hote hain jin ka funding aur Fear & Greed data asli hai: 2019-2020 se.)
  Trained models ke baghair AI signals "unavailable" dikhte hain; koi nakli signal nahi banta.

FAKE / DEMO DATA NAHI:
  Agar Binance, news, ya whale feed na mile to app "unavailable" dikhati hai.
  Koi nakli price, candle, whale, news, signal ya portfolio nahi dikhaya jata.

CLAUDE (Ask Sage ka AI):
  backend\.env mein ANTHROPIC_API_KEY (console.anthropic.com) daalein to Ask Sage Claude se jawab dega.
  CLAUDE_MODEL default claude-opus-5-5 hai; CLAUDE_EFFORT default low (tez aur sasta). Claude fail ho to
  LLM_API_KEY (Groq) try hota hai, phir rules-based jawab. Claude ka istemal paid hai (per token).

LIQUIDATIONS (sidebar > Discover > Liquidations):
  Binance futures ki forced closes live: 5m/15m/1h/4h/24h totals, long vs short, ratio, sab se bara event,
  sab se zyada affected coin, graphs (time, long/short, coin-wise), spike detection, market context
  (price, open interest, funding, ATR) aur AI explanation. Koi key nahi chahiye.
  AHAM: Binance har coin ki har second mein sirf aakhri liquidation bhejta hai, is liye ye "observed"
  data hai, poori market ka total nahi. Events database mein 7 din rehte hain (LIQUIDATION_RETENTION_DAYS).
  Spike detection ko 1 ghanta history chahiye. Thresholds backend\.env.example mein (LIQ_*).
  Alerts mein "Big liquidation", "Liquidation spike", "Long/Short liq. spike", "Liq. imbalance"
  (login zaroori; cooldown LIQ_ALERT_COOLDOWN_MINUTES, Telegram par bhi aate hain).
  AI explanation sirf calculated numbers use karta hai; agar AI koi naya number likhe to uska jawab
  rad karke rules-based jawab dikhaya jata hai.

QUIVER QUANT (crypto stocks ka "smart money"):
  backend\.env mein QUIVER_API_KEY (api.quiverquant.com) daalein. Whale watch par crypto se jure US stocks
  (QUIVER_TICKERS: COIN, MSTR, miners, bitcoin ETFs) mein Congress aur insider trades dikhenge. API: /api/quiver.
  Insider trades ke liye Quiver Trader plan chahiye. Congress disclosure 45 din der se aa sakti hai; ye signal nahi.

KEYS (optional):
  backend\.env mein LLM_API_KEY (free, console.groq.com) daalein to Ask Sage behtar hoga.
  .env file kabhi GitHub ya kisi ko mat bhejein.
