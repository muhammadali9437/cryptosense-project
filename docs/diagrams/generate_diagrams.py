"""Generates the CryptoSense draw.io diagrams (native mxGraph XML, editable in app.diagrams.net)."""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

C = {  # fill, stroke
    "blue": ("#dae8fc", "#6c8ebf"), "green": ("#d5e8d4", "#82b366"), "orange": ("#ffe6cc", "#d79b00"),
    "purple": ("#e1d5e7", "#9673a6"), "yellow": ("#fff2cc", "#d6b656"), "red": ("#f8cecc", "#b85450"),
    "grey": ("#f5f5f5", "#666666"), "white": ("#ffffff", "#666666"),
}


def box(color="blue", extra=""):
    f, s = C[color]
    return f"rounded=1;whiteSpace=wrap;html=1;fillColor={f};strokeColor={s};fontSize=12;{extra}"


def container(color="grey"):
    f, s = C[color]
    return (f"swimlane;whiteSpace=wrap;html=1;startSize=28;fillColor={f};strokeColor={s};fontStyle=1;"
            "fontSize=13;rounded=1;arcSize=4;")


ARROW = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;fontSize=11;labelBackgroundColor=#ffffff;"
STRAIGHT = "html=1;endArrow=block;endFill=1;fontSize=11;labelBackgroundColor=#ffffff;"


class Diagram:
    def __init__(self, name, width=1400, height=1000):
        self.name, self.w, self.h = name, width, height
        self.cells, self.n = [], 0

    def _id(self):
        self.n += 1
        return f"c{self.n}"

    def node(self, label, x, y, w, h, style, parent="1"):
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label.replace(chr(10), "<br>"), {chr(34): "&quot;"})}" style="{style}" vertex="1" '
            f'parent="{parent}"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
        return cid

    def edge(self, src, tgt, label="", style=ARROW, points=None):
        cid = self._id()
        pts = ""
        if points:
            pts = '<Array as="points">' + "".join(f'<mxPoint x="{x}" y="{y}"/>' for x, y in points) + "</Array>"
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" edge="1" parent="1" '
            f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>')
        return cid

    def line(self, x1, y1, x2, y2, label="", style=STRAIGHT):
        cid = self._id()
        self.cells.append(
            f'<mxCell id="{cid}" value="{escape(label, {chr(34): "&quot;"})}" style="{style}" edge="1" parent="1">'
            f'<mxGeometry relative="1" as="geometry"><mxPoint x="{x1}" y="{y1}" as="sourcePoint"/>'
            f'<mxPoint x="{x2}" y="{y2}" as="targetPoint"/></mxGeometry></mxCell>')
        return cid

    def save(self, filename):
        xml = (f'<mxfile host="app.diagrams.net" type="device"><diagram name="{escape(self.name)}" id="{filename}">'
               f'<mxGraphModel dx="1400" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" '
               f'arrows="1" fold="1" page="1" pageScale="1" pageWidth="{self.w}" pageHeight="{self.h}" math="0" '
               f'shadow="0"><root><mxCell id="0"/><mxCell id="1" parent="0"/>' + "".join(self.cells)
               + '</root></mxGraphModel></diagram></mxfile>')
        (OUT / f"{filename}.drawio").write_text(xml, encoding="utf-8")


def actor(d, label, x, y):
    return d.node(label, x, y, 40, 70, "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;"
                  "outlineConnect=0;fontSize=12;fontStyle=1;")


def usecase(d, label, x, y, w=250, h=50, color="white"):
    f, s = C[color]
    return d.node(label, x, y, w, h, f"ellipse;whiteSpace=wrap;html=1;fillColor={f};strokeColor={s};fontSize=12;")


def html_table(title, rows, header_color="#dae8fc"):
    body = "<br>".join(rows)
    return (f'<div style="background:{header_color};padding:4px;font-weight:bold;text-align:center;">{title}</div>'
            f'<div style="padding:4px 6px;text-align:left;">{body}</div>')


TABLE = "verticalAlign=top;align=left;overflow=fill;html=1;whiteSpace=wrap;rounded=0;fillColor=#ffffff;strokeColor=#6c8ebf;fontSize=11;"


# =====================================================================  1. System architecture
def architecture():
    d = Diagram("System Architecture", 1420, 880)
    bands = [
        ("Presentation Layer: Flutter Web App (Dart)", "blue", 20, 120, [
            "Overview", "Portfolio &amp; Limits", "Alerts", "News", "Whale Watch", "Liquidations",
            "New Listings", "Risk Copilot Chat", "Paper Trading", "Academy"], 1),
        ("API Layer: FastAPI REST (JWT auth)", "green", 170, 120, [
            "/api/auth", "/api/market", "/api/signals", "/api/risk", "/api/portfolio", "/api/paper",
            "/api/alerts", "/api/news, whales, listings", "/api/liquidations", "/api/chat"], 1),
        ("Service &amp; Analytics Layer", "orange", 320, 190, [
            "Feature Engineering (18 features)", "ML Predictor (XGBoost + LightGBM)", "Risk Engine (7 factors)",
            "Risk Copilot (twins, levels, what-if)", "Specialist Agents (6)", "Sage + RAG (TF-IDF)",
            "Grounded Explainer", "Liquidation Engine", "News &amp; Sentiment (VADER / Jev)", "Whale Service",
            "Quiver Service", "Listings Service"], 2),
        ("Background Workers (asyncio)", "purple", 540, 120, [
            "Alert Watcher (30 s)", "News Ingest (15 min)", "Listings Refresh (6 h)",
            "Liquidation Stream (WebSocket)", "Liquidation Store (3 s)"], 1),
        ("Data Layer", "yellow", 690, 120, [
            "SQLite (local) / PostgreSQL (Railway) via SQLAlchemy", "ML model files (joblib + metrics.json)",
            "RAG knowledge store (TF-IDF JSON)"], 1),
    ]
    ids = []
    for title, color, y, h, items, rows in bands:
        cid = d.node(title, 20, y, 1060, h, container(color))
        ids.append(cid)
        per_row = (len(items) + rows - 1) // rows
        gap = 10
        w = (1060 - 20 - gap * (per_row - 1)) / per_row
        for i, item in enumerate(items):
            r, k = divmod(i, per_row)
            d.node(item, 10 + k * (w + gap), 40 + r * 72, w, 56 if rows == 1 else 60, box(color), parent=cid)
    ext = d.node("External Services", 1120, 20, 280, 790, container("red"))
    externals = ["Binance Spot REST + ticker WebSocket", "Binance USD-M Futures REST",
                 "Binance forceOrder WebSocket", "alternative.me Fear &amp; Greed", "CoinDesk / Cointelegraph RSS",
                 "CryptoPanic API (optional)", "Whale Alert API (optional)", "Quiver Quantitative (optional)",
                 "Anthropic Claude API (optional)", "Groq / OpenAI-compatible LLM (optional)",
                 "TypeSafe Jev (optional)", "Telegram Bot API (optional)"]
    for i, e in enumerate(externals):
        d.node(e, 15, 40 + i * 62, 250, 50, box("red"), parent=ext)
    pres, api, svc, workers, data = ids
    d.edge(pres, api, "HTTPS / JSON")
    d.edge(api, svc, "function calls")
    d.edge(svc, data, "", ARROW + "exitX=0;exitY=0.75;entryX=0;entryY=0.5;")
    d.edge(workers, data, "SQLAlchemy: read / write data, model files")
    d.edge(workers, svc, "reuse services", ARROW + "exitX=0.75;exitY=0;entryX=0.75;entryY=1;")
    d.edge(svc, ext, "market data, LLM, alerts")
    d.edge(pres, ext, "live prices", ARROW + "exitX=1;exitY=0.5;entryX=0;entryY=0.075;")
    d.save("01_system_architecture")


# =====================================================================  2. Use case diagram
def usecases():
    d = Diagram("Use Case Diagram", 1150, 1300)
    guest_uc = ["View live market overview &amp; charts", "View AI signals and risk score",
                "Explore Risk Copilot (votes, twins, levels, what-if)", "Chat with Sage (six specialists)",
                "Read news with sentiment", "View whale and smart-money activity",
                "View liquidation intelligence", "View new Binance listings", "Learn in the Academy",
                "Register / Log in"]
    reg_uc = ["Manage portfolio holdings", "Set stop-loss / take-profit limits",
              "Create price, risk and liquidation alerts", "Receive notifications (in-app / Telegram)",
              "Practice paper trading"]
    n = len(guest_uc) + len(reg_uc)
    d.node("CryptoSense AI", 300, 20, 420, 90 + n * 74, "rounded=0;whiteSpace=wrap;html=1;fillColor=none;"
           "strokeColor=#333333;verticalAlign=top;fontStyle=1;fontSize=15;")
    gids = [usecase(d, t, 360, 70 + i * 74, 300, 52, "blue") for i, t in enumerate(guest_uc)]
    rids = [usecase(d, t, 360, 70 + (len(guest_uc) + i) * 74 + 20, 300, 52, "green") for i, t in enumerate(reg_uc)]
    g = actor(d, "Guest user", 80, 380)
    r = actor(d, "Registered user", 80, 950)
    d.edge(r, g, "", "html=1;endArrow=block;endFill=0;endSize=14;")
    left = "html=1;endArrow=none;edgeStyle=elbowEdgeStyle;elbow=horizontal;entryX=0;entryY=0.5;exitX=1;exitY=0.5;"
    for u in gids:
        d.edge(g, u, "", left)
    for u in rids:
        d.edge(r, u, "", left)
    right = ("html=1;endArrow=none;dashed=1;edgeStyle=elbowEdgeStyle;elbow=horizontal;exitX=1;exitY=0.5;"
             "entryX=0;entryY=0.5;")
    b = actor(d, "Binance", 960, 250)
    llm = actor(d, "LLM provider (Claude / Groq)", 960, 520)
    tg = actor(d, "Telegram", 960, 980)
    for i in (0, 1, 6, 7):
        d.edge(gids[i], b, "", right)
    d.edge(gids[3], llm, "", right)
    d.edge(rids[3], tg, "", right)
    d.edge(rids[2], rids[3], "«include»", "html=1;endArrow=open;dashed=1;")
    d.save("02_use_case_diagram")


# =====================================================================  3. Activity diagram
def activity():
    d = Diagram("Activity Diagram", 1100, 1500)
    act = lambda t, x, y, w=260, h=50, c="blue": d.node(t, x, y, w, h, box(c, "arcSize=40;"))
    dec = lambda t, x, y: d.node(t, x, y, 200, 90, "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;"
                                 "strokeColor=#d6b656;fontSize=11;")
    s = d.node("", 530, 20, 30, 30, "ellipse;html=1;fillColor=#000000;strokeColor=#000000;")
    a1 = act("Open CryptoSense web app", 415, 80)
    a2 = act("Load real Binance snapshot and connect live ticker stream", 415, 160)
    q1 = dec("Binance reachable?", 445, 245)
    n1 = act("Show &quot;Live market data unavailable&quot; (no made-up prices)", 760, 265, 260, 60, "red")
    r1 = act("Retry automatically after 15 s", 760, 360, 260, 50, "red")
    a3 = act("Ping backend API", 415, 370)
    q2 = dec("Backend online?", 445, 455)
    n2 = act("Backend features shown as unavailable; portfolio works in guest memory", 80, 475, 260, 60, "red")
    a4 = act("Load signals, risk, news, whales, listings, liquidations", 415, 580)
    a5 = act("Show Overview dashboard", 415, 660)
    fork = d.node("", 210, 740, 680, 8, "shape=line;strokeWidth=6;html=1;fillColor=#000000;")
    acts = [act("Open Risk Copilot (votes, twins, levels, what-if)", 40, 790, 200, 70, "green"),
            act("Ask Sage; six specialists analyse; grounded answer", 260, 790, 200, 70, "green"),
            act("Analyse liquidations (stats, spikes, context, explain)", 480, 790, 200, 70, "green"),
            act("View news, whales, listings", 700, 790, 200, 70, "green")]
    q3 = dec("Logged in?", 900, 880)
    lg = act("Log in / register", 860, 1000, 240, 50, "orange")
    pa = act("Manage portfolio, limits, alerts and paper trades", 600, 1000, 230, 60, "orange")
    join = d.node("", 210, 1110, 680, 8, "shape=line;strokeWidth=6;html=1;fillColor=#000000;")
    a6 = act("Background: watcher checks alerts every 30 s and notifies (in-app / Telegram)", 395, 1150, 300, 60)
    e = d.node("", 530, 1250, 30, 30, "ellipse;html=1;shape=endState;fillColor=#000000;strokeColor=#000000;")
    for a, b in ((s, a1), (a1, a2), (a2, q1), (a3, q2), (a4, a5), (a5, fork), (join, a6), (a6, e)):
        d.edge(a, b)
    d.edge(q1, n1, "no")
    d.edge(n1, r1)
    d.edge(r1, a2, "retry", ARROW + "exitX=0.5;exitY=1;entryX=1;entryY=0.5;")
    d.edge(q1, a3, "yes")
    d.edge(q2, a4, "yes")
    d.edge(q2, n2, "no")
    d.edge(n2, a5, "", ARROW + "exitX=0.5;exitY=1;entryX=0;entryY=0.5;")
    for a in acts:
        d.edge(fork, a)
        d.edge(a, join)
    d.edge(fork, q3, "manage money", ARROW + "exitX=1;exitY=0.5;")
    d.edge(q3, lg, "no")
    d.edge(lg, pa)
    d.edge(q3, pa, "yes", ARROW + "exitX=0;exitY=0.5;")
    d.edge(pa, join)
    d.save("03_activity_diagram")


# =====================================================================  4. Class diagram
def classes():
    d = Diagram("Class Diagram", 1500, 1150)
    cls = lambda title, rows, x, y, w, h, color="#dae8fc": d.node(html_table(title, rows, color), x, y, w, h, TABLE)
    user = cls("User", ["- id: int", "- name: str", "- email: str", "- password_hash: str", "- created_at: datetime",
                        "<hr>+ register()", "+ login(): JWT"], 40, 40, 200, 190)
    holding = cls("Holding", ["- symbol: str", "- amount: float", "- avg_buy: float", "- stop_loss_pct: float?",
                              "- take_profit_pct: float?", "- limit_fired: bool"], 330, 20, 210, 150)
    alert = cls("Alert", ["- symbol: str", "- kind: above | below | move | risk | liq_*", "- value: float",
                          "- active: bool", "- triggered_at: datetime?"], 330, 190, 250, 140)
    notif = cls("Notification", ["- message: str", "- kind: str", "- seen: bool", "- created_at: datetime"],
                330, 350, 210, 120)
    acct = cls("PaperAccount", ["- cash_usd: float", "- starting_cash: float", "<hr>+ buy(usd, price)",
                                "+ sell(percent, price)"], 40, 300, 200, 130)
    pos = cls("PaperPosition", ["- symbol: str", "- amount: float", "- avg_price: float"], 40, 480, 200, 90)
    trade = cls("PaperTrade", ["- side: buy | sell", "- amount, price, usd", "- fee_usd: float",
                               "- realized_pnl: float?", "- risk_pct, trend"], 40, 600, 200, 130)
    pred = cls("Predictor", ["- tabular: {xgb, lgbm}", "- metrics: dict", "- weights: dict",
                             "<hr>+ reload()", "+ predict(features): Signal", "+ ready: bool"],
               640, 20, 230, 160, "#d5e8d4")
    sig = cls("SignalService", ["<hr>+ signal_for(symbol): dict", "+ all_signals(): list",
                                "raises SignalUnavailable(missing)"], 640, 210, 230, 110, "#d5e8d4")
    risk = cls("RiskEngine", ["+ score_from(signal): Risk", "+ portfolio_risk(holdings)",
                              "7 weighted factors (max 100)"], 640, 350, 230, 100, "#d5e8d4")
    agent = cls("«interface» SpecialistAgent", ["+ name: str", "<hr>+ analyze(question, context): Report"],
                1050, 20, 270, 90, "#ffe6cc")
    subs = ["MarketIntelligenceAgent", "DerivativesAgent", "OnChainAgent", "SentimentNewsAgent",
            "RiskAssessmentAgent", "ExplanationAgent"]
    sub_ids = [cls(s, [], 920 + (i % 2) * 330, 140 + (i // 2) * 62, 200, 45, "#ffe6cc") for i, s in enumerate(subs)]
    kb = cls("KnowledgeBase", ["- store: TF-IDF", "<hr>+ build_static()", "+ upsert_news(items)",
                               "+ search(query, k): hits"], 960, 360, 230, 130, "#e1d5e7")
    sage = cls("Sage", ["<hr>+ answer(question, context)", "+ complete(system, user)",
                        "Claude → OpenAI-compatible → rules"], 1230, 360, 240, 110, "#e1d5e7")
    expl = cls("Explainer", ["<hr>+ explain(facts, questions, rules_text)",
                             "+ ungrounded_numbers(text, facts)"], 1230, 510, 240, 90, "#e1d5e7")
    liq = cls("LiquidationEvent", ["- event_key: str (unique)", "- symbol, side, position", "- quantity, filled_qty",
                                   "- price, avg_price", "- usd: float, usd_valid: bool", "- event_ms, bucket_5m"],
              640, 520, 240, 160, "#fff2cc")
    stream = cls("LiquidationStream", ["<hr>+ parse_message(msg): events", "+ ingest(raw)",
                                       "+ liquidation_loop()", "+ stream_status()"], 640, 720, 240, 120, "#fff2cc")
    stats = cls("LiquidationStats / Anomaly", ["<hr>+ window_stats(window, symbol)", "+ timeline(window)",
                                               "+ detect(symbol): anomalies", "+ robust_z(x, history)"],
                940, 560, 250, 120, "#fff2cc")
    lalerts = cls("LiquidationAlerts", ["<hr>+ evaluate(alerts): fired", "+ cooling_down(alert)"],
                  940, 720, 250, 80, "#fff2cc")
    rp = cls("RiskPrediction", ["- symbol: str", "- risk_pct: float", "- level: str", "- model: str",
                                "- created_at: datetime"], 330, 520, 210, 130)
    listing = cls("Listing", ["- symbol (PK), base", "- listed_at, first_price", "- last_price, volume_24h",
                              "- volatility, risk"], 330, 680, 210, 110)
    comp = "html=1;endArrow=none;startArrow=diamondThin;startFill=1;startSize=14;"
    d.edge(user, holding, "1..*", comp)
    d.edge(user, alert, "1..*", comp)
    d.edge(user, notif, "1..*", comp)
    d.edge(user, acct, "1", comp)
    d.edge(acct, pos, "1..*", comp)
    d.edge(acct, trade, "1..*", comp + "exitX=0;exitY=0.8;entryX=0;entryY=0.3;", points=[(15, 404), (15, 639)])
    d.edge(sig, pred, "uses", "html=1;endArrow=open;dashed=1;")
    d.edge(risk, sig, "scores", "html=1;endArrow=open;dashed=1;")
    for i, s in enumerate(sub_ids):
        side = "exitX=1;exitY=0.5;" if i % 2 == 0 else "exitX=0;exitY=0.5;"
        d.edge(s, agent, "", "html=1;endArrow=block;endFill=0;dashed=1;edgeStyle=orthogonalEdgeStyle;" + side
               + "entryX=0.5;entryY=1;")
    d.edge(sage, kb, "searches", "html=1;endArrow=open;dashed=1;")
    d.edge(expl, sage, "complete()", "html=1;endArrow=open;dashed=1;")
    d.edge(stream, liq, "creates", "html=1;endArrow=open;dashed=1;")
    d.edge(stats, liq, "aggregates", "html=1;endArrow=open;dashed=1;")
    d.edge(lalerts, stats, "uses", "html=1;endArrow=open;dashed=1;")
    d.edge(risk, rp, "saved as", "html=1;endArrow=open;dashed=1;")
    d.save("04_class_diagram")


# =====================================================================  Sequence diagrams
def sequence(name, filename, lifelines, messages, width=None):
    gap, step = 170, 42
    width = width or 60 + gap * len(lifelines)
    # total height: each message = step, each frame header = 34
    total = 100 + sum(40 if m[0] == "frame" else (step + 10 if m[0] == m[1] else step) for m in messages) + 30
    d = Diagram(name, width, total + 40)
    xs = []
    for i, label in enumerate(lifelines):
        x = 30 + i * gap
        d.node(label, x, 20, 140, total - 20, "shape=umlLifeline;perimeter=lifelinePerimeter;whiteSpace=wrap;"
               "html=1;container=0;collapsible=0;recursiveResize=0;outlineConnect=0;size=50;fillColor=#dae8fc;"
               "strokeColor=#6c8ebf;fontSize=12;fontStyle=1;")
        xs.append(x + 70)
    y = 100
    for m in messages:
        if m[0] == "frame":
            _, label, a, b, rows = m
            x1, x2 = xs[a] - 80, xs[b] + 80
            d.node(label, x1, y - 8, x2 - x1, 34 + step * rows + 8, "shape=umlFrame;whiteSpace=wrap;html=1;"
                   "width=190;height=24;fillColor=none;strokeColor=#b85450;fontSize=11;fontStyle=2;"
                   "verticalAlign=top;align=left;spacingLeft=4;")
            y += 40
            continue
        a, b, label = m[0], m[1], m[2]
        ret = len(m) > 3 and m[3] == "ret"
        style = ("html=1;verticalAlign=bottom;endArrow=open;dashed=1;fontSize=11;" if ret
                 else "html=1;verticalAlign=bottom;endArrow=block;endFill=1;fontSize=11;")
        y += step - 14
        if a == b:
            d.node(label, xs[a] + 8, y - 16, 230, 26, box("grey", "fontSize=11;arcSize=20;"))
            y += 10
        else:
            d.line(xs[a], y, xs[b], y, label, style)
        y += 14
    d.save(filename)


def sequences():
    sequence("Sequence: Registration, Login and Authenticated Request", "05_seq_authentication",
             ["User", "Flutter App", "Auth Router (/api/auth)", "Security (bcrypt, JWT)", "Database"], [
                 ("frame", "Registration", 0, 4, 6),
                 (0, 1, "Enter name, email, password"), (1, 2, "POST /api/auth/register"),
                 (2, 3, "hash_password()"), (2, 4, "INSERT users"), (2, 1, "201 {token, user}", "ret"),
                 (1, 1, "Save token (shared_preferences)"),
                 ("frame", "Login", 0, 4, 5),
                 (0, 1, "Enter email, password"), (1, 2, "POST /api/auth/login"), (2, 4, "SELECT user by email"),
                 (2, 3, "verify bcrypt + create JWT"), (2, 1, "200 {token, user} / 401", "ret"),
                 ("frame", "Authenticated request", 0, 4, 4),
                 (1, 2, "GET /api/portfolio  (Authorization: Bearer JWT)"), (2, 3, "decode JWT → user id"),
                 (2, 4, "SELECT holdings"), (2, 1, "200 portfolio JSON", "ret")])
    sequence("Sequence: AI Signal and Risk Score", "06_seq_signal_risk",
             ["Flutter App", "Risk Router", "Signal Service", "Binance / alternative.me", "Feature Engine",
              "ML Predictor", "Risk Engine", "Database"], [
                 (0, 1, "GET /api/risk"), (1, 2, "all_signals()"),
                 ("frame", "loop [each tracked coin]", 2, 6, 7),
                 (2, 3, "1h candles (250), funding, Fear &amp; Greed"), (3, 2, "real data or error", "ret"),
                 (2, 4, "merge_context + add_features (18)"), (2, 5, "predict(features)"),
                 (5, 2, "ensemble probabilities, votes", "ret"), (1, 6, "score_from(signal)"),
                 (6, 1, "risk %, level, 7 factors", "ret"),
                 (1, 7, "save RiskPrediction (max 1 / 30 min)"),
                 (1, 0, "200 risks JSON", "ret"),
                 ("frame", "alt [an input is missing]", 0, 3, 1),
                 (1, 0, "503 {missing: [...]}  (no made-up values)", "ret")])
    sequence("Sequence: Risk Copilot Chat (Sage + Six Specialists)", "07_seq_chat",
             ["User", "Flutter App", "Chat Router", "Specialist Agents (6)", "Knowledge Base (RAG)", "Sage",
              "Claude API", "Groq API"], [
                 (0, 1, "Ask a question"), (1, 2, "POST /api/chat {question}"),
                 (2, 2, "gather prices, signals, risks, F&amp;G, portfolio"),
                 (2, 3, "run_specialists(question, context)"), (3, 2, "6 reports (status + summary)", "ret"),
                 (2, 5, "answer(question, context)"), (5, 4, "search(question)"), (4, 5, "top-k sources", "ret"),
                 (5, 6, "messages.create(system, sources + live data)"), (6, 5, "answer with [n] citations", "ret"),
                 ("frame", "alt [Claude fails or no key]", 5, 7, 2),
                 (5, 7, "chat/completions (fallback)"), (7, 5, "answer / error → rule-based reply", "ret"),
                 (2, 1, "ChatOut {answer, sources, agents}", "ret"), (1, 0, "Show answer + specialist cards", "ret")])
    sequence("Sequence: Liquidation Intelligence and Alerts", "08_seq_liquidation",
             ["Binance forceOrder WS", "Liquidation Stream", "Store Loop", "Database", "Stats / Anomaly",
              "Alert Watcher", "Telegram", "Flutter App"], [
                 (0, 1, "forceOrder snapshot (≤1 per coin per s)"),
                 (1, 1, "validate, classify long/short, USD, de-duplicate"),
                 ("frame", "loop [every 3 s]", 1, 3, 2),
                 (2, 1, "take_pending()"), (2, 3, "INSERT new events (skip duplicates)"),
                 (7, 4, "GET /api/liquidations/stats?window=1h"), (4, 3, "SQL aggregates (windows, coins)"),
                 (4, 7, "totals, ratio, timeline, coverage", "ret"),
                 ("frame", "loop [every 30 s]", 3, 6, 4),
                 (5, 4, "evaluate liquidation alerts (robust z, cooldown)"), (4, 5, "fired alerts", "ret"),
                 (5, 3, "INSERT notification"), (5, 6, "sendMessage(alert text)")])


# =====================================================================  9. State diagrams
def states():
    d = Diagram("State Diagrams", 1500, 760)
    st = lambda t, x, y, w=170, h=50, c="blue": d.node(t, x, y, w, h, box(c, "arcSize=40;"))
    start = lambda x, y: d.node("", x, y, 26, 26, "ellipse;html=1;fillColor=#000000;strokeColor=#000000;")
    # (a) Liquidation stream connection
    d.node("(a) Liquidation stream connection", 20, 20, 460, 700, container("grey"))
    s0 = start(230, 70)
    a = st("Connecting", 160, 130)
    b = st("Connected (receiving)", 160, 250, 170, 50, "green")
    c = st("Disconnected (gap recorded)", 160, 400, 170, 60, "red")
    w = st("Waiting 5 s", 160, 540)
    d.edge(s0, a)
    d.edge(a, b, "socket open")
    d.edge(b, b, "message / ingest()", ARROW + "exitX=1;exitY=0.3;entryX=1;entryY=0.7;labelPosition=right;align=left;",
           points=[(370, 265), (370, 285)])
    d.edge(b, c, "error or no message for 300 s")
    d.edge(a, c, "connect failed", ARROW + "exitX=0;exitY=0.5;entryX=0;entryY=0.5;", points=[(100, 155), (100, 430)])
    d.edge(c, w)
    d.edge(w, a, "retry", ARROW + "exitX=1;exitY=0.5;entryX=1;entryY=0.2;", points=[(440, 565), (440, 140)])
    # (b) Liquidation alert lifecycle
    d.node("(b) Liquidation alert lifecycle", 510, 20, 460, 700, container("grey"))
    s1 = start(720, 70)
    act = st("Active (watching)", 650, 140, 170, 50, "green")
    trig = st("Triggered (notify, Telegram)", 650, 290, 170, 60, "orange")
    cool = st("Cooling down", 650, 440)
    paused = st("Paused", 850, 290, 110, 50, "grey")
    d.edge(s1, act, "created")
    d.edge(act, trig, "condition met")
    d.edge(trig, cool)
    d.edge(cool, act, "cooldown elapsed", ARROW + "exitX=0;exitY=0.5;entryX=0;entryY=0.5;",
           points=[(590, 465), (590, 165)])
    d.edge(act, paused, "user toggles off / on", ARROW + "startArrow=block;startFill=1;exitX=1;exitY=0.5;"
           "entryX=0.5;entryY=0;", points=[(905, 165)])
    # (c) AI signal availability
    d.node("(c) AI signal availability", 1000, 20, 480, 700, container("grey"))
    s2 = start(1225, 70)
    req = st("Requested", 1155, 130)
    fetch = st("Fetching real inputs", 1155, 240)
    ok = st("Available (cached 5 min)", 1050, 400, 170, 50, "green")
    na = st("Unavailable (503, missing list)", 1260, 400, 190, 60, "red")
    d.edge(s2, req)
    d.edge(req, fetch)
    d.edge(fetch, ok, "all inputs real", ARROW + "exitX=0.25;exitY=1;entryX=0.5;entryY=0;",
           points=[(1197, 320), (1135, 320)])
    d.edge(fetch, na, "an input missing", ARROW + "exitX=0.75;exitY=1;entryX=0.5;entryY=0;",
           points=[(1282, 355), (1355, 355)])
    d.edge(ok, req, "cache expired", ARROW + "exitX=0;exitY=0.5;entryX=0;entryY=0.5;")
    d.edge(na, req, "next request", ARROW + "exitX=1;exitY=0.5;entryX=1;entryY=0.5;")
    d.save("09_state_diagrams")


# =====================================================================  10. ER diagram
def erd():
    d = Diagram("Entity Relationship Diagram", 1400, 900)
    t = lambda title, rows, x, y, w, h, color="#dae8fc": d.node(html_table(title, rows, color), x, y, w, h, TABLE)
    users = t("users", ["<b>PK</b> id INTEGER", "name VARCHAR(80)", "email VARCHAR(160) UNIQUE",
                        "password_hash VARCHAR(200)", "created_at TIMESTAMPTZ"], 520, 30, 260, 130)
    hold = t("holdings", ["<b>PK</b> id", "<b>FK</b> user_id → users.id", "symbol", "amount, avg_buy",
                          "stop_loss_pct, take_profit_pct", "limit_fired"], 40, 30, 260, 150)
    alerts = t("alerts", ["<b>PK</b> id", "<b>FK</b> user_id → users.id", "symbol, kind (≤10 chars)", "value",
                          "active, triggered_at, created_at"], 40, 230, 260, 130)
    notif = t("notifications", ["<b>PK</b> id", "<b>FK</b> user_id → users.id", "message, kind", "seen, created_at"],
              40, 410, 260, 110)
    pacct = t("paper_accounts", ["<b>PK</b> id", "<b>FK</b> user_id → users.id", "cash_usd, starting_cash",
                                 "created_at"], 1000, 30, 260, 110, "#d5e8d4")
    ppos = t("paper_positions", ["<b>PK</b> id", "<b>FK</b> account_id → paper_accounts.id", "symbol",
                                 "amount, avg_price"], 1000, 200, 300, 110, "#d5e8d4")
    ptrade = t("paper_trades", ["<b>PK</b> id", "<b>FK</b> account_id → paper_accounts.id", "symbol, side",
                                "amount, price, usd, fee_usd", "realized_pnl, risk_pct, risk_level, trend",
                                "created_at"], 1000, 360, 300, 150, "#d5e8d4")
    t("risk_predictions", ["<b>PK</b> id", "symbol (INDEX)", "risk_pct, level, model", "created_at (INDEX)"],
      520, 260, 260, 110, "#fff2cc")
    t("listings", ["<b>PK</b> symbol", "base, listed_at", "first_price, last_price", "volume_24h, volatility, risk",
                   "updated_at"], 520, 420, 260, 130, "#fff2cc")
    t("liquidation_events", ["<b>PK</b> id", "event_key UNIQUE", "symbol, side, position", "order_type, status",
                             "quantity, filled_qty, price, avg_price", "usd, usd_valid", "event_ms (INDEX)",
                             "bucket_5m (INDEX), received_ms", "INDEX (symbol, event_ms)"],
      520, 600, 300, 200, "#ffe6cc")
    one_many = "html=1;endArrow=ERmany;startArrow=ERmandOne;endFill=0;startFill=0;edgeStyle=orthogonalEdgeStyle;"
    one_one = "html=1;endArrow=ERmandOne;startArrow=ERmandOne;endFill=0;startFill=0;edgeStyle=orthogonalEdgeStyle;"
    d.edge(users, hold, "", one_many + "exitX=0;exitY=0.3;entryX=1;entryY=0.3;")
    d.edge(users, alerts, "", one_many + "exitX=0;exitY=0.6;entryX=1;entryY=0.4;", points=[(440, 108), (440, 282)])
    d.edge(users, notif, "", one_many + "exitX=0;exitY=0.85;entryX=1;entryY=0.5;", points=[(470, 140), (470, 465)])
    d.edge(users, pacct, "", one_one)
    d.edge(pacct, ppos, "", one_many)
    d.edge(pacct, ptrade, "", one_many + "exitX=1;exitY=0.5;entryX=1;entryY=0.5;")
    d.save("10_er_diagram")


# =====================================================================  11. ML pipeline
def ml_pipeline():
    d = Diagram("Machine Learning Pipeline", 1500, 560)
    steps = [
        ("1. Download Binance hourly candles (up to 10 years)", "blue"),
        ("2. Download futures funding + Fear &amp; Greed history", "blue"),
        ("3. Keep only hours with real funding and Fear &amp; Greed", "red"),
        ("4. Feature engineering: 18 features (technical, order flow, context)", "orange"),
        ("5. Label: price 24 h later vs ±2.5% (bearish / neutral / bullish)", "orange"),
        ("6. Chronological split 70 / 15 / 15 per coin with 24 h gaps", "purple"),
        ("7. Train XGBoost + LightGBM (early stopping on validation)", "green"),
        ("8. Ensemble weights = validation macro-F1", "green"),
        ("9. Evaluate on untouched test set vs majority baseline", "yellow"),
        ("10. Save models + metrics.json (model-info endpoint)", "yellow"),
    ]
    ids = []
    for i, (t, c) in enumerate(steps):
        row, col = divmod(i, 5)
        x = 30 + col * 290 if row == 0 else 30 + (4 - col) * 290
        ids.append(d.node(t, x, 40 + row * 200, 250, 90, box(c)))
    for a, b in zip(ids, ids[1:]):
        d.edge(a, b)
    live = d.node("Live inference: /api/signals builds the same 18 features from real live data; "
                  "missing input → signal unavailable", 450, 440, 600, 70, box("grey"))
    d.edge(ids[-1], live, "deployed models", ARROW + "exitX=0.5;exitY=1;")
    d.save("11_ml_pipeline")


# =====================================================================  12. Deployment
def deployment():
    d = Diagram("Deployment Diagram", 1300, 700)
    node = lambda t, x, y, w, h: d.node(t, x, y, w, h, "shape=cube;whiteSpace=wrap;html=1;boundedLbl=1;"
                                        "backgroundOutline=1;darkOpacity=0.05;darkOpacity2=0.1;size=12;"
                                        "fillColor=#f5f5f5;strokeColor=#666666;verticalAlign=top;fontStyle=1;")
    client = node("«device» User's browser", 30, 60, 300, 260)
    d.node("Flutter web build (Dart → JS)\nCryptoSense UI", 60, 130, 240, 60, box("blue"))
    d.node("Binance ticker WebSocket client", 60, 220, 240, 50, box("blue"))
    srv = node("«cloud node» Railway service (or local PC)", 420, 40, 420, 380)
    d.node("Uvicorn ASGI server", 450, 110, 360, 40, box("green"))
    d.node("FastAPI app: routers, services, ML predictor", 450, 165, 360, 50, box("green"))
    d.node("Background tasks: watcher, news, listings, liquidation stream + store", 450, 230, 360, 60, box("purple"))
    d.node("ml/models: xgb.joblib, lgbm.joblib, metrics.json", 450, 305, 360, 40, box("yellow"))
    d.node("rag_store/tfidf_docs.json", 450, 355, 360, 40, box("yellow"))
    db = node("«database node» Railway PostgreSQL (or local SQLite)", 420, 480, 420, 150)
    d.node("users, holdings, alerts, notifications, paper_*, listings, risk_predictions, liquidation_events",
           450, 540, 360, 70, box("yellow"))
    ext = node("«external» Third-party APIs", 940, 60, 330, 560)
    for i, t in enumerate(["Binance Spot + Futures (REST, WebSocket)", "alternative.me Fear &amp; Greed",
                           "RSS / CryptoPanic news", "Whale Alert, Quiver Quant", "Anthropic Claude / Groq LLM",
                           "TypeSafe Jev", "Telegram Bot API"]):
        d.node(t, 970, 120 + i * 68, 270, 50, box("red"))
    d.edge(client, srv, "HTTPS REST / JSON")
    d.edge(srv, db, "SQLAlchemy (psycopg)")
    d.edge(srv, ext, "HTTPS / WSS")
    d.edge(client, ext, "WSS ticker + REST klines (direct)", ARROW + "exitX=0.5;exitY=0;entryX=0.5;entryY=0;",
           points=[(180, 15), (1105, 15)])
    d.save("12_deployment_diagram")


# =====================================================================  13. Signal-generation flowchart
def flow_common(d):
    act = lambda t, x, y, w=300, h=56, c="blue": d.node(t, x, y, w, h, box(c, "arcSize=20;"))
    dec = lambda t, x, y: d.node(t, x, y, 240, 100, "rhombus;whiteSpace=wrap;html=1;fillColor=#fff2cc;"
                                 "strokeColor=#d6b656;fontSize=11;")
    return act, dec


def signal_flow():
    d = Diagram("Signal-Generation Flowchart", 1000, 1500)
    act, dec = flow_common(d)
    R = ARROW + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
    s = d.node("", 335, 20, 30, 30, "ellipse;html=1;fillColor=#000000;strokeColor=#000000;")
    a1 = act("Signal request: GET /api/signals/{symbol}", 200, 80)
    q1 = dec("Trained models loaded?", 230, 170)
    n1 = act("HTTP 503: signal unavailable (missing: trained AI model)", 620, 192, 300, 56, "red")
    a2 = act("Fetch in parallel: coin candles, BTC candles, funding rate, Fear &amp; Greed", 200, 310, 300, 66)
    q2 = dec("All four inputs received?", 230, 410)
    n2 = act("HTTP 503: unavailable, missing inputs listed (no demo or filled-in data)", 620, 427, 300, 66, "red")
    a3 = act("Backward as-of join of context (only values known at each hour)", 200, 550, 300, 66)
    a4 = act("Compute 18 features; drop incomplete rows", 200, 650)
    q3 = dec("Enough candle history?", 230, 740)
    n3 = act("HTTP 503: unavailable (missing: enough candle history)", 620, 762, 300, 56, "red")
    a5 = act("XGBoost + LightGBM class probabilities, weighted by validation macro-F1", 200, 880, 300, 66)
    q4 = dec("Bullish/bearish with confidence &ge; 0.55?", 230, 980)
    n4 = act("Signal = neutral (weak call not shown as direction)", 620, 1002, 300, 56, "orange")
    a6 = act("Signal = bullish or bearish", 200, 1120, 300, 50, "green")
    a7 = act("Add plain-language reasons, model votes, key levels; return JSON", 200, 1220, 300, 66, "green")
    e = d.node("", 335, 1330, 30, 30, "ellipse;html=1;shape=endState;fillColor=#000000;strokeColor=#000000;")
    for a, b in ((s, a1), (a1, q1), (a2, q2), (a3, a4), (a4, q3), (a5, q4), (a6, a7), (a7, e)):
        d.edge(a, b)
    d.edge(q1, a2, "yes"); d.edge(q2, a3, "yes"); d.edge(q3, a5, "yes"); d.edge(q4, a6, "yes")
    for q, n in ((q1, n1), (q2, n2), (q3, n3), (q4, n4)):
        d.edge(q, n, "no", R)
    d.edge(n4, a7, "", ARROW + "exitX=0.5;exitY=1;entryX=1;entryY=0.5;", points=[(770, 1253)])
    d.save("13_signal_flowchart")


# =====================================================================  14. Paper-trading activity
def paper_activity():
    d = Diagram("Paper-Trading Activity", 1000, 1400)
    act, dec = flow_common(d)
    R = ARROW + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
    s = d.node("", 335, 20, 30, 30, "ellipse;html=1;fillColor=#000000;strokeColor=#000000;")
    a1 = act("Logged-in user chooses coin and Buy (USD amount) or Sell (% of holding)", 200, 80, 300, 66)
    q1 = dec("Tracked coin?", 230, 180)
    n1 = act("HTTP 404: not tracked", 620, 210, 300, 40, "red")
    a2 = act("Read live Binance price", 200, 320, 300, 50)
    q2 = dec("Live price available?", 230, 400)
    n2 = act("HTTP 503: practice trading paused (no made-up price)", 620, 422, 300, 56, "red")
    a3 = act("Read current AI risk score for the coin (waits at most 4 s)", 200, 540, 300, 66)
    q3 = dec("Trade rules met? (at least $1, enough cash / coins held)", 230, 640)
    n3 = act("Reject with a plain message (TradeError)", 620, 670, 300, 40, "red")
    a4 = act("Apply 0.1% fee; update cash, position and fee-inclusive average cost", 200, 790, 300, 66, "green")
    a5 = act("Save PaperTrade with price, fee, realised P&amp;L and risk snapshot", 200, 890, 300, 66, "green")
    a6 = act("Return updated account summary to the app", 200, 990, 300, 50, "green")
    e = d.node("", 335, 1080, 30, 30, "ellipse;html=1;shape=endState;fillColor=#000000;strokeColor=#000000;")
    for a, b in ((s, a1), (a1, q1), (a2, q2), (a3, q3), (a4, a5), (a5, a6), (a6, e)):
        d.edge(a, b)
    d.edge(q1, a2, "yes"); d.edge(q2, a3, "yes"); d.edge(q3, a4, "yes")
    for q, n in ((q1, n1), (q2, n2), (q3, n3)):
        d.edge(q, n, "no", R)
    d.save("14_paper_trading_activity")


for f in (architecture, usecases, activity, classes, sequences, states, erd, ml_pipeline, deployment, signal_flow, paper_activity):
    f()
print("diagrams:", sorted(p.name for p in OUT.glob("*.drawio")))
