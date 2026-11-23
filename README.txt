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
  Chat replies ke neeche har specialist ka status aur analysis dekhein. Demo data ko live evidence nahi maana jata.
  Binance liquidation stream pehle se use hoti hai. Crypto whale feed ke liye optional WHALE_ALERT_KEY
  (Whale Alert; Quiver Quant crypto transfer feed nahi hai); LLM responses ke liye optional LLM_API_KEY chahiye.
  Baghair in keys ke specialist status "unavailable" dikhate hain; demo feeds ko live evidence nahi maana jata.

TELEGRAM ALERTS (optional):
  Telegram BotFather se bot banayein, bot ko apne chat mein start karein, phir backend\.env mein
  TELEGRAM_BOT_TOKEN aur TELEGRAM_CHAT_ID set karein. Price/risk/portfolio-limit alerts ke saath
  tracked coins ke bari Binance liquidations aur configured Whale Alert transfers Telegram par aayenge.
  LIQUIDATION_ALERT_USD default $1,000,000 hai. Ek deployment ka ek operator chat configured hota hai.

RAILWAY BACKEND DEPLOYMENT:
  Railway project mein backend\ ko service Root Directory set karein; backend\railway.toml start command deta hai.
  Railway Postgres attach karke DATABASE_URL, JWT_SECRET, TELEGRAM_BOT_TOKEN aur TELEGRAM_CHAT_ID variables set karein.
  Optional WHALE_ALERT_KEY aur LLM_API_KEY bhi Railway Variables mein set kar sakte hain.
  Flutter web build ko `--dart-define=API_URL=https://<your-backend>.up.railway.app` dein.
  Keys ko source control mein commit na karein. Ye app analysis/alerts only hai; order execution enabled nahi.

AI MODELS (optional, ek baar):
  TRAIN_AI.bat  -> signals asli trained models se aayenge.
  Ke baghair signals "rule-based" hote hain, app phir bhi chalti hai.

KEYS (optional):
  backend\.env mein LLM_API_KEY (free, console.groq.com) daalein to Ask Sage behtar hoga.
  .env file kabhi GitHub ya kisi ko mat bhejein.
