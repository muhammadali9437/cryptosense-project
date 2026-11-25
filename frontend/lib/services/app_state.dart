import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../models/models.dart';
import '../utils/format.dart';
import 'api_service.dart';
import 'market_service.dart';
import 'sage_brain.dart';

/// Everything the user creates or sees besides live prices.
///
/// Backend running  -> signals, news, whales and listings come from FastAPI;
///                     when logged in, portfolio, limits and alerts are saved in the database
///                     and the server sends alert notifications.
/// Backend offline  -> signals, news, whales and listings show as unavailable (never made up);
///                     portfolio, limits and alerts work in memory (guest mode).
class AppState extends ChangeNotifier {
  AppState(this.api);

  final ApiService api;

  int page = 0;
  bool tourSeen = false;
  int unseenTriggers = 0;
  final Set<String> doneLessons = {};

  /// Shell sets this to show a toast for server notifications / save errors.
  void Function(String message)? onNotify;

  // ------------------------------------------------------------ backend state
  bool backendOnline = false;
  ApiUser? user;
  bool get loggedIn => user != null;

  List<AiSignal> signals = [];
  Map<String, RiskScore> risks = {};
  bool risksLive = false;
  List<NewsItem> news = [];
  List<WhaleTx> whales = [];
  List<NewListing> listings = [];
  bool signalsLive = false,
      newsLive = false,
      whalesLive = false,
      listingsLive = false;
  LiquidationSnapshot? liquidations;
  bool liquidationsLive = false;
  SmartMoneySnapshot? smartMoney;
  String newsEngine = '';

  Timer? _refreshTimer, _notifyTimer;

  // Guest (not logged in) starts empty; nothing is pre-filled.
  final List<Holding> holdings = [];

  final List<PriceAlert> alerts = [];

  final List<ChatMessage> chat = [
    ChatMessage(text: SageBrain.greeting, fromUser: false)
  ];
  bool sageTyping = false;

  // ---------------------------------------------------------------- startup
  Future<void> init() async {
    await checkBackend();
    if (backendOnline) {
      try {
        user = await api.restore(); // stay logged in after a page refresh
        if (user != null) await _loadUserData();
      } catch (_) {}
      unawaited(refreshAll());
    }
    _refreshTimer =
        Timer.periodic(const Duration(minutes: 2), (_) => refreshAll());
    _notifyTimer = Timer.periodic(
        const Duration(seconds: 30), (_) => _pollNotifications());
    notifyListeners();
  }

  Future<void> checkBackend() async {
    backendOnline = await api.ping();
    notifyListeners();
  }

  Future<void> refreshAll() async {
    if (!backendOnline) {
      await checkBackend();
      if (!backendOnline) return;
    }
    await Future.wait([
      refreshSignals(),
      refreshRisks(),
      refreshNews(),
      refreshWhales(),
      refreshListings(),
      refreshLiquidations(),
      refreshSmartMoney(),
    ]);
  }

  Future<void> refreshSignals() async {
    try {
      final s = await api.signals();
      if (s.isNotEmpty) signals = s;
      signalsLive = s.isNotEmpty;
    } catch (_) {
      signalsLive = false;
    }
    notifyListeners();
  }

  Future<void> refreshRisks() async {
    try {
      final r = await api.risks();
      if (r.isNotEmpty) risks = r;
      risksLive = r.isNotEmpty;
    } catch (_) {
      risksLive = false;
    }
    notifyListeners();
  }

  Future<void> refreshNews() async {
    try {
      final r = await api.news();
      if (r.items.isNotEmpty) news = r.items;
      newsLive = r.source != 'unavailable' && r.items.isNotEmpty;
      newsEngine = r.engine;
    } catch (_) {
      newsLive = false;
    }
    notifyListeners();
  }

  Future<void> refreshWhales() async {
    try {
      final r = await api.whales();
      whales = r.items;
      whalesLive = r.source == 'whale_alert';
    } catch (_) {
      whalesLive = false;
    }
    notifyListeners();
  }

  Future<void> refreshLiquidations() async {
    try {
      liquidations = await api.liquidations();
      liquidationsLive = liquidations!.connected;
    } catch (_) {
      liquidations = null;
      liquidationsLive = false;
    }
    notifyListeners();
  }

  Future<void> refreshSmartMoney() async {
    try {
      smartMoney = await api.smartMoney();
    } catch (_) {
      smartMoney = null;
    }
    notifyListeners();
  }

  Future<void> refreshListings() async {
    try {
      final l = await api.listings();
      if (l.isNotEmpty) listings = l;
      listingsLive = l.isNotEmpty;
    } catch (_) {
      listingsLive = false;
    }
    notifyListeners();
  }

  // ------------------------------------------------------------------- auth
  Future<void> login(String email, String password) async {
    user = await api.login(email, password);
    await _loadUserData();
    notifyListeners();
  }

  Future<void> register(String name, String email, String password) async {
    user = await api.register(name, email, password);
    await _loadUserData();
    notifyListeners();
  }

  Future<void> logout() async {
    await api.logout();
    user = null;
    holdings.clear();
    alerts.clear();
    unseenTriggers = 0;
    notifyListeners();
  }

  Future<void> _loadUserData() async {
    final h = await api.portfolio();
    final a = await api.alerts();
    holdings
      ..clear()
      ..addAll(h);
    alerts
      ..clear()
      ..addAll(a);
  }

  /// Runs a save on the server; the screen already shows the change.
  Future<void> _sync(Future<void> Function() job) async {
    try {
      await job();
    } catch (e) {
      onNotify?.call('Not saved on the server: $e');
    }
    notifyListeners();
  }

  void _setHoldings(List<Holding> h) {
    holdings
      ..clear()
      ..addAll(h);
  }

  Future<void> _pollNotifications() async {
    if (!loggedIn || !backendOnline) return;
    try {
      final messages = await api.unseenNotifications();
      if (messages.isEmpty) return;
      await api.markNotificationsSeen();
      unseenTriggers += messages.length;
      onNotify?.call(messages.length == 1
          ? messages.first
          : '${messages.first} (+${messages.length - 1} more in Alerts)');
      final a = await api.alerts();
      alerts
        ..clear()
        ..addAll(a);
      notifyListeners();
    } catch (_) {}
  }

  // ------------------------------------------------------------ navigation
  void go(int index) {
    if (index == 2) unseenTriggers = 0;
    if (page == index) {
      notifyListeners();
      return;
    }
    page = index;
    notifyListeners();
  }

  void finishTour() {
    tourSeen = true;
    notifyListeners();
  }

  // ------------------------------------------------------------- portfolio
  Holding? holding(String symbol) {
    for (final h in holdings) {
      if (h.symbol == symbol) return h;
    }
    return null;
  }

  double portfolioValue(Map<String, Ticker> t) => holdings.fold(
      0.0, (sum, h) => sum + h.amount * (t[h.symbol]?.price ?? h.avgBuy));

  double portfolioCost() =>
      holdings.fold(0.0, (sum, h) => sum + h.amount * h.avgBuy);

  void addHolding(String symbol, double amount, double price) {
    final existing = holding(symbol);
    if (existing != null) {
      final total = existing.amount + amount;
      existing.avgBuy =
          (existing.avgBuy * existing.amount + price * amount) / total;
      existing.amount = total;
    } else {
      holdings.add(Holding(symbol: symbol, amount: amount, avgBuy: price));
    }
    notifyListeners();
    if (loggedIn) {
      _sync(() async =>
          _setHoldings(await api.addHolding(symbol, amount, price)));
    }
  }

  void removeHolding(String symbol) {
    holdings.removeWhere((h) => h.symbol == symbol);
    notifyListeners();
    if (loggedIn) {
      _sync(() async => _setHoldings(await api.removeHolding(symbol)));
    }
  }

  void setLimits(String symbol, double? stopLoss, double? takeProfit) {
    final h = holding(symbol);
    if (h == null) return;
    h.stopLossPct = stopLoss;
    h.takeProfitPct = takeProfit;
    h.limitFired = false;
    notifyListeners();
    if (loggedIn) {
      _sync(() async =>
          _setHoldings(await api.setLimits(symbol, stopLoss, takeProfit)));
    }
  }

  // ---------------------------------------------------------------- alerts
  void addAlert(String symbol, AlertKind kind, double value) {
    final temp = PriceAlert(
      id: 'local-${DateTime.now().microsecondsSinceEpoch}',
      symbol: symbol,
      kind: kind,
      value: value,
    );
    alerts.insert(0, temp);
    notifyListeners();
    if (loggedIn) {
      _sync(() async {
        final saved = await api.createAlert(symbol, kind, value);
        final i = alerts.indexOf(temp);
        if (i >= 0) alerts[i] = saved;
      });
    }
  }

  void toggleAlert(String id) {
    for (final a in alerts) {
      if (a.id == id) {
        a.active = !a.active;
        if (a.active) a.triggeredAt = null; // re-arm
      }
    }
    notifyListeners();
    if (loggedIn && !id.startsWith('local-')) _sync(() => api.toggleAlert(id));
  }

  void removeAlert(String id) {
    alerts.removeWhere((a) => a.id == id);
    notifyListeners();
    if (loggedIn && !id.startsWith('local-')) _sync(() => api.deleteAlert(id));
  }

  /// Called on every price update. Guest mode checks alerts here in the browser;
  /// when logged in the backend checks them (every 30 s) and sends notifications instead.
  List<String> evaluate(Map<String, Ticker> tickers) {
    if (loggedIn) return const [];
    final messages = <String>[];

    for (final a in alerts) {
      if (!a.active) continue;
      final t = tickers[a.symbol];
      if (t == null) continue;
      final hit = switch (a.kind) {
        AlertKind.above => t.price >= a.value,
        AlertKind.below => t.price <= a.value,
        AlertKind.move => t.changePct.abs() >= a.value,
        AlertKind.risk => (risks[a.symbol]?.riskPct ?? 0) >= a.value,
        _ => false, // liquidation alerts are checked by the backend
      };
      if (hit) {
        a.active = false;
        a.triggeredAt = DateTime.now();
        messages.add(a.kind == AlertKind.risk
            ? 'Risk alert: ${a.describe()} (${risks[a.symbol]!.riskPct.round()}%).'
            : 'Alert: ${a.describe()}. Now ${Fmt.usd(t.price)}.');
      }
    }

    for (final h in holdings) {
      final t = tickers[h.symbol];
      if (t == null || h.limitFired) continue;
      final pnl = (t.price - h.avgBuy) / h.avgBuy * 100;
      if (h.stopLossPct != null && pnl <= -h.stopLossPct!) {
        h.limitFired = true;
        messages.add(
            '${h.base} reached your stop-loss (${Fmt.pct(pnl)}). Time to review this position.');
      } else if (h.takeProfitPct != null && pnl >= h.takeProfitPct!) {
        h.limitFired = true;
        messages.add(
            '${h.base} reached your take-profit target (${Fmt.pct(pnl)}).');
      }
    }

    if (messages.isNotEmpty) {
      unseenTriggers += messages.length;
      notifyListeners();
    }
    return messages;
  }

  // --------------------------------------------------------------- learning
  void completeLesson(String id) {
    doneLessons.add(id);
    notifyListeners();
  }

  // ------------------------------------------------------------------ chat
  /// Backend online: RAG answer from the server, with sources.
  /// Offline: built-in rules with live prices.
  Future<void> ask(String question, MarketService market) async {
    final q = question.trim();
    if (q.isEmpty || sageTyping) return;
    chat.add(ChatMessage(text: q, fromUser: true));
    sageTyping = true;
    notifyListeners();

    ChatMessage? reply;
    if (backendOnline) {
      try {
        final r = await api.chat(q);
        reply = ChatMessage(
            text: r.answer,
            fromUser: false,
            sources: r.sources,
            agents: r.agents);
      } catch (_) {}
    }
    if (reply == null) {
      await Future.delayed(
          Duration(milliseconds: min(1600, 600 + q.length * 8)));
      reply =
          ChatMessage(text: SageBrain.reply(q, market, this), fromUser: false);
    }

    chat.add(reply);
    sageTyping = false;
    notifyListeners();
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _notifyTimer?.cancel();
    super.dispose();
  }
}
