import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/liquidation_models.dart';
import '../models/models.dart';
import '../utils/format.dart';

/// Error message from the backend (e.g. "Wrong email or password.").
class ApiException implements Exception {
  ApiException(this.message, [this.status]);
  final String message;
  final int? status;

  @override
  String toString() => message;
}

class ApiUser {
  const ApiUser({required this.id, required this.name, required this.email});
  final int id;
  final String name;
  final String email;

  factory ApiUser.fromJson(Map<String, dynamic> j) => ApiUser(
      id: j['id'] as int,
      name: j['name'] as String,
      email: j['email'] as String);
}

/// The bridge between the Flutter app and the FastAPI backend.
/// Every backend endpoint the app uses is one method here.
class ApiService {
  ApiService({String? baseUrl}) : baseUrl = baseUrl ?? defaultBaseUrl;

  /// Change with: flutter run -d chrome --dart-define=API_URL=http://192.168.1.5:8000
  static const defaultBaseUrl =
      String.fromEnvironment('API_URL', defaultValue: 'http://127.0.0.1:8000');
  static const _tokenKey = 'cryptosense_token';

  final String baseUrl;
  final _client = http.Client();
  String? token;

  // ------------------------------------------------------------------ core
  Future<dynamic> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    Duration timeout = const Duration(seconds: 20),
  }) async {
    var uri = Uri.parse('$baseUrl$path');
    if (query != null) uri = uri.replace(queryParameters: query);
    final req = http.Request(method, uri);
    req.headers['Content-Type'] = 'application/json';
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    if (body != null) req.body = jsonEncode(body);

    final res = await http.Response.fromStream(
        await _client.send(req).timeout(timeout));
    final text = utf8.decode(res.bodyBytes);
    final data = text.isEmpty ? null : jsonDecode(text);
    if (res.statusCode >= 400) {
      final detail = data is Map ? data['detail'] : null;
      throw ApiException(
          detail is String ? detail : 'Server error (${res.statusCode})',
          res.statusCode);
    }
    return data;
  }

  /// true when the backend answers.
  Future<bool> ping() async {
    try {
      await _send('GET', '/', timeout: const Duration(seconds: 4));
      return true;
    } catch (_) {
      return false;
    }
  }

  // ------------------------------------------------------------------ auth
  Future<ApiUser> _saveAuth(dynamic d) async {
    token = d['access_token'] as String;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token!);
    return ApiUser.fromJson(d['user'] as Map<String, dynamic>);
  }

  Future<ApiUser> login(String email, String password) async =>
      _saveAuth(await _send('POST', '/api/auth/login',
          body: {'email': email, 'password': password}));

  Future<ApiUser> register(String name, String email, String password) async =>
      _saveAuth(await _send('POST', '/api/auth/register',
          body: {'name': name, 'email': email, 'password': password}));

  /// Logs back in with the saved token (if any). Returns null when there is none.
  Future<ApiUser?> restore() async {
    final prefs = await SharedPreferences.getInstance();
    token = prefs.getString(_tokenKey);
    if (token == null) return null;
    try {
      return ApiUser.fromJson(
          await _send('GET', '/api/auth/me') as Map<String, dynamic>);
    } on ApiException catch (e) {
      if (e.status == 401) await logout(); // token expired
      return null;
    }
  }

  Future<void> logout() async {
    token = null;
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }

  // --------------------------------------------------------------- helpers
  static double _d(dynamic v) => (v as num).toDouble();
  static double? _dn(dynamic v) => v == null ? null : (v as num).toDouble();
  static DateTime _t(dynamic v) =>
      DateTime.tryParse(v as String? ?? '')?.toLocal() ?? DateTime.now();
  static Trend _trend(dynamic v) =>
      Trend.values.firstWhere((t) => t.name == v, orElse: () => Trend.neutral);

  // -------------------------------------------------------------- signals
  Future<List<AiSignal>> signals() async {
    final list =
        await _send('GET', '/api/signals', timeout: const Duration(seconds: 90))
            as List;
    return [
      for (final j in list)
        AiSignal(
          symbol: j['symbol'] as String,
          trend: _trend(j['trend']),
          model: j['model'] as String,
          confidence: _d(j['confidence']),
          horizon: j['horizon'] as String,
          reasons: List<String>.from(j['reasons'] as List),
        ),
    ];
  }

  // ----------------------------------------------------------------- risk
  Future<Map<String, RiskScore>> risks() async {
    final list =
        await _send('GET', '/api/risk', timeout: const Duration(seconds: 90))
            as List;
    final out = <String, RiskScore>{};
    for (final j in list) {
      final factors = <RiskFactor>[];
      for (final f in j['factors'] as List) {
        factors.add(RiskFactor(
          name: f['name'] as String,
          points: _d(f['points']),
          max: _d(f['max']),
          note: f['note'] as String,
        ));
      }
      final symbol = j['symbol'] as String;
      out[symbol] = RiskScore(
        symbol: symbol,
        riskPct: _d(j['risk_pct']),
        level: j['level'] as String,
        summary: (j['summary'] as String?) ?? '',
        factors: factors,
      );
    }
    return out;
  }

  Future<RiskCopilotAnalysis> riskCopilot(String symbol) async {
    final d = await _send('GET', '/api/risk/$symbol/copilot',
        timeout: const Duration(seconds: 45));
    return RiskCopilotAnalysis(
      votes: [
        for (final vote in d['votes'] as List)
          RiskModelVote(
            model: vote['model'] as String,
            trend: vote['trend'] as String,
            confidence: _d(vote['confidence']),
          ),
      ],
      agreement: (d['agreement'] as num).toInt(),
      modelCount: (d['model_count'] as num).toInt(),
      disagreement: d['disagreement'] as bool,
      twins: [
        for (final twin in d['twins'] as List)
          HistoricalTwin(
            time: _t(twin['time']),
            similarityPct: _d(twin['similarity_pct']),
            futureReturnPct: _d(twin['future_return_pct']),
          ),
      ],
      keyLevels: [
        for (final level in d['key_levels'] as List? ?? const [])
          KeyMarketLevel(
            period: level['period'] as String,
            referenceDate: level['reference_date'] as String,
            high: _d(level['high']),
            low: _d(level['low']),
            highDistanceAtr: _d(level['high_distance_atr']),
            lowDistanceAtr: _d(level['low_distance_atr']),
            highSide: level['high_side'] as String,
            lowSide: level['low_side'] as String,
          ),
      ],
      keyLevelsSource: (d['key_levels_source'] as String?) ?? 'unavailable',
    );
  }

  Future<RiskSimulation> simulateRisk(
      String symbol, double volatilityMultiplier) async {
    final d = await _send(
      'POST',
      '/api/risk/$symbol/simulate',
      body: {'volatility_multiplier': volatilityMultiplier},
    );
    return RiskSimulation(
      currentRiskPct: _d(d['current_risk_pct']),
      simulatedRiskPct: _d(d['simulated_risk_pct']),
      changePctPoints: _d(d['change_pct_points']),
      volatilityMultiplier: _d(d['volatility_multiplier']),
    );
  }

  // ----------------------------------------------------------------- news
  Future<({String source, String engine, List<NewsItem> items})> news() async {
    final d = await _send('GET', '/api/news',
        query: {'limit': '40'}, timeout: const Duration(seconds: 90));
    final items = [
      for (final j in d['items'] as List)
        NewsItem(
          title: j['title'] as String,
          source: j['source'] as String,
          time: _t(j['published_at']),
          sentiment: _trend(j['sentiment']),
          summary: (j['summary'] as String?) ?? '',
          sageTake: (j['sage_take'] as String?) ?? '',
          coins: List<String>.from(j['coins'] as List? ?? const []),
        ),
    ];
    return (
      source: d['source'] as String,
      engine: (d['sentiment_engine'] as String?) ?? '',
      items: items
    );
  }

  // --------------------------------------------------------------- whales
  static WhaleFlow _flow(dynamic v) => switch (v) {
        'to_exchange' => WhaleFlow.toExchange,
        'from_exchange' => WhaleFlow.fromExchange,
        _ => WhaleFlow.walletToWallet,
      };

  Future<({String source, List<WhaleTx> items})> whales() async {
    final d = await _send('GET', '/api/whales');
    final items = [
      for (final j in d['items'] as List)
        WhaleTx(
          id: j['id'].toString(),
          coin: j['coin'] as String,
          amount: _d(j['amount']),
          usd: _d(j['usd']),
          from: j['from'] as String,
          to: j['to'] as String,
          time: _t(j['time']),
          flow: _flow(j['flow']),
        ),
    ];
    return (source: d['source'] as String, items: items);
  }

  // ---------------------------------------------------------- liquidations
  static LiquidationEvent _liquidation(dynamic j) => LiquidationEvent(
        id: j['id'].toString(),
        symbol: j['symbol'] as String,
        position: j['position'] as String,
        usd: _d(j['usd']),
        price: _d(j['price']),
        time: DateTime.fromMillisecondsSinceEpoch(j['time'] as int, isUtc: true)
            .toLocal(),
      );

  static LiquidationTotals _totals(String label, dynamic j) => LiquidationTotals(
        label: label,
        longUsd: _d(j['long_liquidations_usd']),
        shortUsd: _d(j['short_liquidations_usd']),
        count: (j['event_count'] as num).toInt(),
      );

  Future<LiquidationSnapshot> liquidations() async {
    final d = await _send('GET', '/api/liquidations', query: {'limit': '100'});
    final summary = d['summary'] as Map<String, dynamic>;
    final frames = (d['timeframes'] as Map<String, dynamic>?) ?? const {};
    return LiquidationSnapshot(
      source: d['source'] as String,
      connected: d['connected'] as bool,
      items: [for (final j in d['items'] as List) _liquidation(j)],
      longUsd: _d(summary['long_liquidations_usd']),
      shortUsd: _d(summary['short_liquidations_usd']),
      read: (summary['read'] as String?) ?? '',
      timeframes: [for (final e in frames.entries) _totals(e.key, e.value)],
      topSymbols: [
        for (final j in (d['top_symbols'] as List?) ?? const [])
          _totals(j['symbol'] as String, j),
      ],
      largest: d['largest'] == null ? null : _liquidation(d['largest']),
    );
  }

  // --------------------------------------------- liquidation intelligence
  Map<String, String> _liqQuery(String window, String? filter) => {
        'window': window,
        if (filter == 'other') 'group': 'other',
        if (filter != null && filter != 'other') 'symbol': filter,
      };

  Future<LiqStats> liquidationStats(String window, String? filter) async =>
      LiqStats.fromJson(await _send('GET', '/api/liquidations/stats',
          query: _liqQuery(window, filter)));

  Future<LiqAnomalies> liquidationAnomalies(String? symbol) async =>
      LiqAnomalies.fromJson(await _send('GET', '/api/liquidations/anomalies',
          query: {if (symbol != null && symbol != 'other') 'symbol': symbol}));

  Future<LiqContext> liquidationContext(String symbol, String window) async =>
      LiqContext.fromJson(await _send(
          'GET', '/api/liquidations/context/$symbol',
          query: {'window': window}));

  Future<LiqExplanation> liquidationExplain(
          String window, String? symbol) async =>
      LiqExplanation.fromJson(await _send('GET', '/api/liquidations/explain',
          query: {
            'window': window,
            if (symbol != null && symbol != 'other') 'symbol': symbol,
          },
          timeout: const Duration(seconds: 90)));

  // ------------------------------------------------------- quiver quant
  Future<SmartMoneySnapshot> smartMoney() async {
    final d = await _send('GET', '/api/quiver');
    final status = d['status'] as Map<String, dynamic>;
    final summary = d['summary'] as Map<String, dynamic>?;
    return SmartMoneySnapshot(
      live: d['source'] == 'quiver',
      congressStatus: status['congress'] as String,
      insiderStatus: status['insiders'] as String,
      read: (summary?['read'] as String?) ?? '',
      note: (d['note'] as String?) ?? '',
      congress: [
        for (final j in d['congress'] as List)
          SmartMoneyTrade(
            ticker: j['ticker'] as String,
            who: j['who'] as String,
            detail: [j['party'], j['chamber']]
                .where((v) => v != null && v.toString().isNotEmpty)
                .join(', '),
            isBuy: j['side'] == 'buy',
            amount: j['range'] as String,
            time: _t(j['traded_at']),
          ),
      ],
      insiders: [
        for (final j in d['insiders'] as List)
          SmartMoneyTrade(
            ticker: j['ticker'] as String,
            who: j['who'] as String,
            detail: (j['title'] as String?) ?? '',
            isBuy: j['side'] == 'buy',
            amount: Fmt.compact(_d(j['usd'])),
            time: _t(j['traded_at']),
          ),
      ],
    );
  }

  // ------------------------------------------------------------- listings
  Future<List<NewListing>> listings() async {
    final d = await _send('GET', '/api/listings');
    return [
      for (final j in d['items'] as List)
        NewListing(
          symbol: j['symbol'] as String,
          name: j['name'] as String,
          category: j['category'] as String,
          listedAt: _t(j['listed_at']),
          changeSinceListing: _d(j['change_since_listing']),
          volume24h: _d(j['volume_24h']),
          risk: (j['risk'] as num).toInt().clamp(0, 2),
          note: j['note'] as String,
        ),
    ];
  }

  // ------------------------------------------------------------ portfolio
  static List<Holding> _holdings(dynamic d) => [
        for (final j in d['holdings'] as List)
          Holding(
            symbol: j['symbol'] as String,
            amount: _d(j['amount']),
            avgBuy: _d(j['avg_buy']),
            stopLossPct: _dn(j['stop_loss_pct']),
            takeProfitPct: _dn(j['take_profit_pct']),
          ),
      ];

  Future<List<Holding>> portfolio() async =>
      _holdings(await _send('GET', '/api/portfolio'));

  Future<List<Holding>> addHolding(
          String symbol, double amount, double price) async =>
      _holdings(await _send('POST', '/api/portfolio',
          body: {'symbol': symbol, 'amount': amount, 'price': price}));

  Future<List<Holding>> removeHolding(String symbol) async =>
      _holdings(await _send('DELETE', '/api/portfolio/$symbol'));

  Future<List<Holding>> setLimits(
          String symbol, double? stopLoss, double? takeProfit) async =>
      _holdings(await _send('PUT', '/api/portfolio/$symbol/limits',
          body: {'stop_loss_pct': stopLoss, 'take_profit_pct': takeProfit}));

  // --------------------------------------------------------------- alerts
  static PriceAlert _alert(dynamic j) => PriceAlert(
        id: j['id'].toString(),
        symbol: j['symbol'] as String,
        kind: AlertKind.fromApi(j['kind'] as String),
        value: _d(j['value']),
        active: j['active'] as bool,
        triggeredAt: j['triggered_at'] == null ? null : _t(j['triggered_at']),
      );

  Future<List<PriceAlert>> alerts() async =>
      [for (final j in await _send('GET', '/api/alerts') as List) _alert(j)];

  Future<PriceAlert> createAlert(
          String symbol, AlertKind kind, double value) async =>
      _alert(await _send('POST', '/api/alerts',
          body: {'symbol': symbol, 'kind': kind.api, 'value': value}));

  Future<PriceAlert> toggleAlert(String id) async =>
      _alert(await _send('PATCH', '/api/alerts/$id/toggle'));

  Future<void> deleteAlert(String id) async {
    await _send('DELETE', '/api/alerts/$id');
  }

  /// Messages created by the server when an alert or a stop-loss / take-profit fired.
  Future<List<String>> unseenNotifications() async {
    final list =
        await _send('GET', '/api/notifications', query: {'unseen_only': 'true'})
            as List;
    return [for (final j in list) j['message'] as String];
  }

  Future<void> markNotificationsSeen() async {
    await _send('POST', '/api/notifications/seen');
  }

  // ----------------------------------------------------------------- chat
  Future<({String answer, List<ChatSource> sources, List<AgentInsight> agents})>
      chat(String question) async {
    final d = await _send('POST', '/api/chat',
        body: {'question': question}, timeout: const Duration(seconds: 90));
    final sources = [
      for (final s in d['sources'] as List? ?? const [])
        ChatSource(
          title: (s['title'] as String?) ?? '',
          kind: (s['kind'] as String?) ?? '',
          url: (s['url'] as String?) ?? '',
        ),
    ];
    final agents = [
      for (final a in d['agents'] as List? ?? const [])
        AgentInsight(
          name: a['name'] as String,
          status: a['status'] as String,
          summary: a['summary'] as String,
        ),
    ];
    return (answer: d['answer'] as String, sources: sources, agents: agents);
  }
}
