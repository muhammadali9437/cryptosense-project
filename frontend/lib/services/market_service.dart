import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

import '../models/models.dart';
import 'coins.dart';

/// Real-time market data.
///
/// 1. Loads a real snapshot from Binance REST (24h tickers + recent hourly closes).
/// 2. Streams live 24h tickers from Binance's public WebSocket (no API key needed).
/// 3. If Binance can't be reached, prices are simply unavailable ([hasPrices] is false,
///    [isLive] is false) and a reconnect is retried; no made-up prices are ever shown.
/// 4. Candles come from Binance REST /api/v3/klines (empty list when unavailable).
class MarketService extends ChangeNotifier {
  static const symbols = [
    'BTCUSDT',
    'ETHUSDT',
    'BNBUSDT',
    'SOLUSDT',
    'XRPUSDT',
    'ADAUSDT'
  ];

  final Map<String, Ticker> tickers = {};
  bool isLive = false;
  DateTime lastUpdate = DateTime.now();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _sub;
  Timer? _retryTimer;
  bool _notifyQueued = false;
  bool _disposed = false;

  /// Latest real ticker, or null when Binance hasn't delivered one.
  Ticker? ticker(String symbol) => tickers[symbol];

  /// True once real prices have been received at least once.
  bool get hasPrices => tickers.isNotEmpty;

  Future<void> start() async {
    await _loadSnapshot();
    await _connectLive();
  }

  /// Real starting values: 24h tickers + the last 40 hourly closes for the sparklines.
  Future<void> _loadSnapshot() async {
    try {
      final list = jsonEncode(symbols);
      final res = await http
          .get(Uri.parse(
              'https://api.binance.com/api/v3/ticker/24hr?symbols=${Uri.encodeComponent(list)}'))
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return;
      final rows = jsonDecode(res.body) as List<dynamic>;
      final histories = await Future.wait(symbols.map(_recentCloses));
      for (final r in rows.cast<Map<String, dynamic>>()) {
        final s = r['symbol'] as String;
        final i = symbols.indexOf(s);
        if (i < 0) continue;
        final price = double.parse(r['lastPrice'] as String);
        tickers[s] = Ticker(
          symbol: s,
          name: coinName(s),
          price: price,
          changePct: double.parse(r['priceChangePercent'] as String),
          quoteVolume: double.parse(r['quoteVolume'] as String),
          high: double.parse(r['highPrice'] as String),
          low: double.parse(r['lowPrice'] as String),
          history: [...histories[i], price],
        );
      }
      lastUpdate = DateTime.now();
      notifyListeners();
    } catch (_) {
      // Binance unreachable: prices stay unavailable until the stream connects.
    }
  }

  Future<List<double>> _recentCloses(String symbol) async {
    try {
      final res = await http
          .get(Uri.parse(
              'https://api.binance.com/api/v3/klines?symbol=$symbol&interval=1h&limit=40'))
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return const [];
      return [
        for (final k in jsonDecode(res.body) as List<dynamic>)
          double.parse((k as List<dynamic>)[4] as String)
      ];
    } catch (_) {
      return const [];
    }
  }

  Future<void> _connectLive() async {
    WebSocketChannel? channel;
    try {
      final streams = symbols.map((s) => '${s.toLowerCase()}@ticker').join('/');
      channel = WebSocketChannel.connect(
        Uri.parse('wss://stream.binance.com:9443/stream?streams=$streams'),
      );
      await channel.ready.timeout(const Duration(seconds: 6));
      if (_disposed) {
        channel.sink.close();
        return;
      }
      _channel = channel;
      _sub = channel.stream
          .listen(_onMessage, onError: (_) => _offline(), onDone: _offline);
      isLive = true;
      _queueNotify();
    } catch (_) {
      channel?.sink.close();
      _offline();
    }
  }

  void _onMessage(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      final d = msg['data'] as Map<String, dynamic>;
      final symbol = d['s'] as String;
      if (!symbols.contains(symbol)) return;
      final price = double.parse(d['c'] as String);
      final old = tickers[symbol] ??
          Ticker(
              symbol: symbol,
              name: coinName(symbol),
              price: price,
              changePct: 0,
              quoteVolume: 0,
              high: price,
              low: price);
      final history = [...old.history, price];
      if (history.length > 60) history.removeAt(0);

      tickers[symbol] = old.copyWith(
        price: price,
        changePct: double.parse(d['P'] as String),
        quoteVolume: double.parse(d['q'] as String),
        high: double.parse(d['h'] as String),
        low: double.parse(d['l'] as String),
        history: history,
      );
      lastUpdate = DateTime.now();
      _queueNotify();
    } catch (_) {
      // Ignore malformed messages.
    }
  }

  /// Binance sends several messages per second; redraw at most ~once a second.
  void _queueNotify() {
    if (_notifyQueued || _disposed) return;
    _notifyQueued = true;
    Future.delayed(const Duration(milliseconds: 800), () {
      _notifyQueued = false;
      if (!_disposed) notifyListeners();
    });
  }

  /// Connection lost or impossible: mark prices as not live and retry in 15 seconds.
  /// The last real prices stay visible, labelled as not live by [isLive].
  void _offline() {
    if (_disposed) return;
    isLive = false;
    _sub?.cancel();
    _sub = null;
    _channel?.sink.close();
    _channel = null;
    _queueNotify();
    _retryTimer?.cancel();
    _retryTimer = Timer(const Duration(seconds: 15), () async {
      if (_disposed) return;
      if (!hasPrices) await _loadSnapshot();
      await _connectLive();
    });
  }

  /// OHLCV candles for the chart. [interval] is one of 15m, 1h, 4h, 1d.
  /// Returns an empty list when Binance can't be reached; the chart then says so.
  /// (Made-up demo candles are never shown in place of real market data.)
  Future<List<Candle>> candles(String symbol, String interval) async {
    try {
      final uri = Uri.parse(
          'https://api.binance.com/api/v3/klines?symbol=$symbol&interval=$interval&limit=90');
      final res = await http.get(uri).timeout(const Duration(seconds: 6));
      if (res.statusCode == 200) {
        final raw = jsonDecode(res.body) as List<dynamic>;
        return raw.map((k) {
          final row = k as List<dynamic>;
          return Candle(
            time: DateTime.fromMillisecondsSinceEpoch(row[0] as int),
            open: double.parse(row[1] as String),
            high: double.parse(row[2] as String),
            low: double.parse(row[3] as String),
            close: double.parse(row[4] as String),
            volume: double.parse(row[5] as String),
          );
        }).toList();
      }
    } catch (_) {
      // Binance unreachable or returned bad data.
    }
    return const [];
  }

  /// 0..100 mood score from the average 24h move of the tracked coins.
  double get mood {
    if (tickers.isEmpty) return 50;
    final avg = tickers.values.map((t) => t.changePct).reduce((a, b) => a + b) /
        tickers.length;
    return (50 + avg * 7).clamp(5, 95).toDouble();
  }

  static String moodLabel(double m) => m < 25
      ? 'Fearful'
      : m < 45
          ? 'Cautious'
          : m < 56
              ? 'Balanced'
              : m < 75
                  ? 'Confident'
                  : 'Greedy';

  @override
  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _channel?.sink.close();
    _retryTimer?.cancel();
    super.dispose();
  }
}
