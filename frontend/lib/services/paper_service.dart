import 'dart:convert';

import 'package:http/http.dart' as http;

import 'api_service.dart';

double _pd(dynamic v) => (v as num).toDouble();
double? _pdn(dynamic v) => v == null ? null : (v as num).toDouble();

/// One open practice position (coins you "hold" in the paper wallet).
class PaperPosition {
  const PaperPosition({
    required this.symbol,
    required this.amount,
    required this.avgPrice,
    required this.price,
  });

  final String symbol;
  final double amount;
  final double avgPrice;
  final double price; // price when the account was loaded

  String get base => symbol.replaceAll('USDT', '');

  factory PaperPosition.fromJson(Map<String, dynamic> j) => PaperPosition(
        symbol: j['symbol'] as String,
        amount: _pd(j['amount']),
        avgPrice: _pd(j['avg_price']),
        price: _pd(j['price']),
      );
}

/// One practice buy or sell, saved with the AI risk score at that moment.
class PaperTradeRow {
  const PaperTradeRow({
    required this.symbol,
    required this.side,
    required this.amount,
    required this.price,
    required this.usd,
    required this.fee,
    required this.time,
    this.realizedPnl,
    this.riskPct,
    this.riskLevel,
  });

  final String symbol;
  final String side; // buy | sell
  final double amount;
  final double price;
  final double usd;
  final double fee;
  final DateTime time;
  final double? realizedPnl; // sells only
  final double? riskPct;
  final String? riskLevel;

  String get base => symbol.replaceAll('USDT', '');
  bool get isBuy => side == 'buy';

  factory PaperTradeRow.fromJson(Map<String, dynamic> j) => PaperTradeRow(
        symbol: j['symbol'] as String,
        side: j['side'] as String,
        amount: _pd(j['amount']),
        price: _pd(j['price']),
        usd: _pd(j['usd']),
        fee: _pd(j['fee_usd']),
        time: DateTime.tryParse(j['time'] as String? ?? '')?.toLocal() ??
            DateTime.now(),
        realizedPnl: _pdn(j['realized_pnl']),
        riskPct: _pdn(j['risk_pct']),
        riskLevel: j['risk_level'] as String?,
      );
}

/// The practice account: cash, open positions and simple statistics.
class PaperAccount {
  const PaperAccount({
    required this.cash,
    required this.startingCash,
    required this.positions,
    required this.tradesCount,
    this.winRate,
  });

  final double cash;
  final double startingCash;
  final List<PaperPosition> positions;
  final int tradesCount;
  final double? winRate; // % of sells that made a profit

  PaperPosition? positionOf(String symbol) {
    for (final p in positions) {
      if (p.symbol == symbol) return p;
    }
    return null;
  }

  factory PaperAccount.fromJson(Map<String, dynamic> j) => PaperAccount(
        cash: _pd(j['cash']),
        startingCash: _pd(j['starting_cash']),
        tradesCount: (j['trades_count'] as num).toInt(),
        winRate: _pdn(j['win_rate']),
        positions: [
          for (final p in j['positions'] as List)
            PaperPosition.fromJson(p as Map<String, dynamic>),
        ],
      );
}

class PaperTradeResult {
  const PaperTradeResult(
      {required this.trade, required this.account, this.warning});

  final PaperTradeRow trade;
  final PaperAccount account;
  final String? warning;
}

/// Talks to the backend's /api/paper endpoints, reusing the login token of [ApiService].
class PaperService {
  PaperService(this.api);

  final ApiService api;

  Future<dynamic> _send(String method, String path, {Object? body}) async {
    final req = http.Request(method, Uri.parse('${api.baseUrl}$path'));
    req.headers['Content-Type'] = 'application/json';
    if (api.token != null) {
      req.headers['Authorization'] = ['Bearer', api.token].join(' ');
    }
    if (api.token != null) req.headers['Authorization'] = 'Bearer ${api.token}';
    if (api.token != null) req.headers['Authorization'] = 'Bearer ${api.token}';
    if (body != null) req.body = jsonEncode(body);
    if (api.token != null) {
      req.headers['Authorization'] = ['Bearer', api.token].join(' ');
    }

    final res = await http.Response.fromStream(
        await req.send().timeout(const Duration(seconds: 30)));
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

  Future<PaperAccount> account() async => PaperAccount.fromJson(
      await _send('GET', '/api/paper') as Map<String, dynamic>);

  Future<List<PaperTradeRow>> trades() async {
    final list = await _send('GET', '/api/paper/trades') as List;
    return [
      for (final j in list) PaperTradeRow.fromJson(j as Map<String, dynamic>)
    ];
  }

  Future<PaperTradeResult> trade({
    required String symbol,
    required String side,
    double? usd,
    double? percent,
  }) async {
    final d = await _send('POST', '/api/paper/trade', body: {
      'symbol': symbol,
      'side': side,
      'usd': usd,
      'percent': percent
    }) as Map<String, dynamic>;
    return PaperTradeResult(
      trade: PaperTradeRow.fromJson(d['trade'] as Map<String, dynamic>),
      account: PaperAccount.fromJson(d['account'] as Map<String, dynamic>),
      warning: d['warning'] as String?,
    );
  }

  Future<PaperAccount> reset() async => PaperAccount.fromJson(
      await _send('POST', '/api/paper/reset') as Map<String, dynamic>);
}
