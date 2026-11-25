/// Data shapes for the Liquidation Intelligence page (backend /api/liquidations/*).
/// Every figure is an OBSERVED Binance forceOrder stream event, not an exchange-wide total.
library;

double _d(dynamic v) => v == null ? 0 : (v as num).toDouble();
double? _dn(dynamic v) => v == null ? null : (v as num).toDouble();
DateTime _ms(dynamic v) =>
    DateTime.fromMillisecondsSinceEpoch((v as num).toInt(), isUtc: true).toLocal();

class LiqEvent {
  LiqEvent.fromJson(Map<String, dynamic> j)
      : symbol = j['symbol'] as String,
        position = j['position'] as String,
        usd = _d(j['usd']),
        usdValid = j['usd_valid'] as bool? ?? true,
        price = _d(j['price']),
        status = j['status'] as String? ?? '',
        time = _ms(j['time']);

  final String symbol;
  final String position; // long (forced sell) | short (forced buy)
  final double usd;
  final bool usdValid;
  final double price;
  final String status;
  final DateTime time;
  bool get isLong => position == 'long';
}

class LiqTotals {
  LiqTotals.fromJson(Map<String, dynamic> j, {String? label})
      : label = label ?? j['symbol'] as String? ?? '',
        longUsd = _d(j['long_usd']),
        shortUsd = _d(j['short_usd']),
        totalUsd = _d(j['total_usd']),
        events = (j['event_count'] as num? ?? 0).toInt(),
        longCount = (j['long_count'] as num? ?? 0).toInt(),
        shortCount = (j['short_count'] as num? ?? 0).toInt(),
        ratio = _dn(j['long_short_ratio']),
        longShare = _dn(j['long_share_pct']),
        read = j['read'] as String? ?? '';

  final String label;
  final double longUsd;
  final double shortUsd;
  final double totalUsd;
  final int events;
  final int longCount;
  final int shortCount;
  final double? ratio;
  final double? longShare;
  final String read;
}

class LiqPoint {
  LiqPoint.fromJson(Map<String, dynamic> j)
      : time = _ms(j['t_ms']),
        longUsd = _d(j['long_usd']),
        shortUsd = _d(j['short_usd']),
        count = (j['count'] as num).toInt();
  final DateTime time;
  final double longUsd;
  final double shortUsd;
  final int count;
}

class LiqStream {
  LiqStream.fromJson(Map<String, dynamic> j)
      : connected = j['connected'] as bool,
        secondsSinceMessage = _dn(j['seconds_since_last_message']),
        reconnects = (j['reconnects'] as num).toInt(),
        error = j['error'] as String?,
        limitation = j['limitation'] as String;
  final bool connected;
  final double? secondsSinceMessage;
  final int reconnects;
  final String? error;
  final String limitation;
}

class LiqStats {
  LiqStats.fromJson(Map<String, dynamic> j)
      : window = j['window'] as String,
        summary = LiqTotals.fromJson(j['summary'] as Map<String, dynamic>,
            label: 'all'),
        largest = [
          for (final e in j['largest'] as List) LiqEvent.fromJson(e)
        ],
        recent = [for (final e in j['recent'] as List) LiqEvent.fromJson(e)],
        bySymbol = [
          for (final r in j['by_symbol'] as List) LiqTotals.fromJson(r)
        ],
        mostAffected = j['most_affected'] == null
            ? null
            : LiqTotals.fromJson(j['most_affected']),
        timeline = [
          for (final p in j['timeline'] as List) LiqPoint.fromJson(p)
        ],
        fullyObserved =
            (j['coverage'] as Map<String, dynamic>)['window_fully_observed']
                as bool,
        coverageNote =
            (j['coverage'] as Map<String, dynamic>)['note'] as String,
        stream = LiqStream.fromJson(j['stream'] as Map<String, dynamic>);

  final String window;
  final LiqTotals summary;
  final List<LiqEvent> largest;
  final List<LiqEvent> recent;
  final List<LiqTotals> bySymbol;
  final LiqTotals? mostAffected;
  final List<LiqPoint> timeline;
  final bool fullyObserved;
  final String coverageNote;
  final LiqStream stream;
}

class LiqAnomaly {
  LiqAnomaly.fromJson(Map<String, dynamic> j)
      : type = j['type'] as String,
        symbol = j['symbol'] as String?,
        severity = j['severity'] as String,
        message = j['message'] as String,
        z = _dn(j['robust_z']);
  final String type;
  final String? symbol;
  final String severity;
  final String message;
  final double? z;
}

class LiqAnomalies {
  LiqAnomalies.fromJson(Map<String, dynamic> j)
      : status = j['status'] as String,
        note = j['note'] as String? ?? '',
        items = [
          for (final a in j['anomalies'] as List) LiqAnomaly.fromJson(a)
        ],
        method = j['method'] as String? ?? '';
  final String status;
  final String note;
  final List<LiqAnomaly> items;
  final String method;
}

class LiqScenario {
  LiqScenario.fromJson(Map<String, dynamic> j)
      : name = j['name'] as String,
        description = j['description'] as String? ?? '',
        supporting = [for (final s in j['supporting'] as List) s as String],
        contradicting = [
          for (final s in j['contradicting'] as List) s as String
        ],
        caveat = j['caveat'] as String? ?? '';
  final String name;
  final String description;
  final List<String> supporting;
  final List<String> contradicting;
  final String caveat;
}

class LiqContext {
  LiqContext.fromJson(Map<String, dynamic> j)
      : symbol = j['symbol'] as String,
        window = j['window'] as String,
        priceChangePct = _dn((j['market'] as Map?)?['price_change_pct']),
        volumeVsPrior = _dn((j['market'] as Map?)?['volume_vs_prior_window']),
        atrPct = _dn((j['market'] as Map?)?['atr_pct']),
        oiChangePct = _dn((j['open_interest'] as Map?)?['oi_change_pct']),
        fundingRate = _dn(j['funding_rate']),
        priceDirection = j['price_direction'] as String,
        oiDirection = j['open_interest_direction'] as String,
        unavailable = [for (final u in j['unavailable'] as List) u as String],
        scenarios = [
          for (final s in j['scenarios'] as List) LiqScenario.fromJson(s)
        ];
  final String symbol;
  final String window;
  final double? priceChangePct;
  final double? volumeVsPrior;
  final double? atrPct;
  final double? oiChangePct;
  final double? fundingRate;
  final String priceDirection;
  final String oiDirection;
  final List<String> unavailable;
  final List<LiqScenario> scenarios;
}

class LiqExplanation {
  LiqExplanation.fromJson(Map<String, dynamic> j)
      : text = j['text'] as String,
        source = j['source'] as String,
        note = j['note'] as String? ?? '',
        answers = [
          for (final a in j['answers'] as List)
            (
              question: (a as Map<String, dynamic>)['question'] as String,
              answer: a['answer'] as String
            )
        ];
  final String text;
  final String source; // claude | openai_compatible | rules
  final String note;
  final List<({String question, String answer})> answers;
}
