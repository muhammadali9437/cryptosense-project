import 'dart:math';

import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/app_scope.dart';
import '../services/indicators.dart';
import '../services/market_service.dart';
import '../services/mock_data.dart';
import '../services/sage_brain.dart';
import '../theme/app_colors.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/bits.dart';
import '../widgets/buttons.dart';
import '../widgets/candle_chart.dart';
import '../widgets/explain.dart';
import '../widgets/mini_charts.dart';
import '../widgets/panel.dart';
import '../widgets/pop.dart';
import '../widgets/tappable.dart';

const _intervalWords = {
  '15m': '15 minutes',
  '1h': '1 hour',
  '4h': '4 hours',
  '1d': '1 day'
};

/// Overview page: Sage's market read + mood, live candle chart, AI signals,
/// watchlist, and snapshots of whale moves and new listings.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  String _symbol = 'BTCUSDT';
  String _interval = '1h';
  List<Candle> _candles = const [];
  bool _loading = true;
  int _request = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final id = ++_request;
    if (!_loading) setState(() => _loading = true);
    final data = await context.market.candles(_symbol, _interval);
    if (!mounted || id != _request) return;
    setState(() {
      _candles = data;
      _loading = false;
    });
  }

  void _pickSymbol(String s) {
    if (s == _symbol) return;
    _symbol = s;
    _load();
  }

  void _pickInterval(String i) {
    if (i == _interval) return;
    _interval = i;
    _load();
  }

  /// Keep the newest candle in step with the live price.
  List<Candle> _withLivePrice(Ticker t) {
    if (_candles.isEmpty) return _candles;
    final last = _candles.last;
    return [
      ..._candles.sublist(0, _candles.length - 1),
      Candle(
        time: last.time,
        open: last.open,
        high: max(last.high, t.price),
        low: min(last.low, t.price),
        close: t.price,
        volume: last.volume,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final market = context.market;
    return ListenableBuilder(
      listenable: Listenable.merge([market, context.app]),
      builder: (context, _) {
        final t = market.ticker(_symbol);
        final candles = _loading ? _candles : _withLivePrice(t);
        return PageBody(children: [
          _MarketRead(
            ticker: t,
            candles: candles,
            interval: _interval,
            symbol: _symbol,
            onPick: _pickSymbol,
          ),
          _RiskPanel(symbol: _symbol),
          TwoColumn(
            left: Panel(
              title: '${t.base}/USDT price',
              subtitle:
                  'Each candle is ${_intervalWords[_interval]}. Hover or drag to inspect.',
              explain: 'candles',
              trailing: SegmentPills(
                options: const ['15m', '1h', '4h', '1d'],
                selected: _interval,
                onChanged: _pickInterval,
              ),
              child: Column(
                children: [
                  _loading
                      ? const SizedBox(
                          height: 352,
                          child: Center(
                              child: CircularProgressIndicator(strokeWidth: 2)),
                        )
                      : CandleChart(candles: candles),
                  const SizedBox(height: 18),
                  _StatStrip(ticker: t, candles: candles, interval: _interval),
                ],
              ),
            ),
            right:
                const _SignalsPanel(), // not const: rebuilds when backend data arrives
          ),
          TwoColumn(
            left: _Watchlist(selected: _symbol, onPick: _pickSymbol),
            right: const _Discover(),
          ),
        ]);
      },
    );
  }
}

// ------------------------------------------------------------------ hero card
class _MarketRead extends StatelessWidget {
  const _MarketRead({
    required this.ticker,
    required this.candles,
    required this.interval,
    required this.symbol,
    required this.onPick,
  });

  final Ticker ticker;
  final List<Candle> candles;
  final String interval;
  final String symbol;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final market = context.market;
    final read = SageBrain.marketRead(ticker, candles, interval);
    final mood = market.mood;

    final story = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const SageAvatar(size: 34),
            const SizedBox(width: 12),
            Expanded(
              child: Text("Sage's read on ${ticker.name}",
                  style: AppText.body(14.5, w: FontWeight.w600)),
            ),
            const ExplainButton(topic: 'market_read'),
          ],
        ),
        const SizedBox(height: 18),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            layoutBuilder: (current, previous) => Stack(
              alignment: Alignment.topLeft,
              children: [...previous, if (current != null) current],
            ),
            child: Text(
              read,
              key: ValueKey(symbol),
              style: AppText.display(
                MediaQuery.sizeOf(context).width < 700 ? 18.5 : 22.5,
                w: FontWeight.w500,
              ).copyWith(height: 1.5),
            ),
          ),
        ),
        const SizedBox(height: 10),
        Text(
          '${Fmt.usd(ticker.price)} now, ${Fmt.pct(ticker.changePct)} in 24h. Updated ${Fmt.clock(market.lastUpdate)}.',
          style: AppText.body(13, color: AppColors.faint),
        ),
        const SizedBox(height: 20),
        CoinChoice(
            selected: symbol, onChanged: onPick, tickers: market.tickers),
      ],
    );

    final gauge = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Market mood', style: AppText.body(14.5, w: FontWeight.w600)),
            const SizedBox(width: 8),
            const ExplainButton(topic: 'mood'),
          ],
        ),
        const SizedBox(height: 14),
        MoodGauge(value: mood, label: MarketService.moodLabel(mood)),
        const SizedBox(height: 10),
        SizedBox(
          width: 220,
          child: Text(
            'From the 24h moves of the six biggest coins we track',
            textAlign: TextAlign.center,
            style: AppText.body(12.5, color: AppColors.faint),
          ),
        ),
      ],
    );

    return Container(
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF2A1F3A), AppColors.panel],
        ),
        border: Border.all(color: AppColors.brass.fade(0.28)),
      ),
      child: LayoutBuilder(builder: (context, box) {
        if (box.maxWidth >= 820) {
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: story),
              const SizedBox(width: 32),
              Container(width: 1, height: 250, color: AppColors.line),
              const SizedBox(width: 32),
              gauge,
            ],
          );
        }
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [story, const SizedBox(height: 28), Center(child: gauge)],
        );
      }),
    );
  }
}

// ------------------------------------------------------------- stats below chart
class _StatStrip extends StatelessWidget {
  const _StatStrip(
      {required this.ticker, required this.candles, required this.interval});
  final Ticker ticker;
  final List<Candle> candles;
  final String interval;

  @override
  Widget build(BuildContext context) {
    final closes = candles.map((c) => c.close).toList();
    final rsi = Indicators.rsi(closes);
    final vol = Indicators.volatility(closes);
    final volWord = Indicators.volWord(vol / Indicators.volScale(interval));

    final rsiNote = rsi >= 70
        ? ('Stretched high', AppColors.warn)
        : rsi <= 30
            ? ('Stretched low', AppColors.calm)
            : ('Balanced', AppColors.muted);
    final volColor = switch (volWord) {
      'Wild' => AppColors.bear,
      'Moderate' => AppColors.warn,
      _ => AppColors.bull,
    };

    final items = <(String, String, String?, Color, String?)>[
      ('24h high', Fmt.usd(ticker.high), null, AppColors.muted, null),
      ('24h low', Fmt.usd(ticker.low), null, AppColors.muted, null),
      ('RSI (14)', rsi.toStringAsFixed(0), rsiNote.$1, rsiNote.$2, 'rsi'),
      (
        'Volatility',
        '${vol.toStringAsFixed(2)}%',
        volWord,
        volColor,
        'volatility'
      ),
    ];

    return LayoutBuilder(builder: (context, box) {
      final cols = box.maxWidth > 560 ? 4 : 2;
      final w = (box.maxWidth - 10 * (cols - 1)) / cols;
      return Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final it in items)
            Container(
              width: w,
              padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
              decoration: BoxDecoration(
                color: AppColors.ink,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: AppColors.line),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                          child: Text(it.$1,
                              style:
                                  AppText.body(12.5, color: AppColors.muted))),
                      if (it.$5 != null)
                        Transform.scale(
                            scale: 0.8, child: ExplainButton(topic: it.$5!)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(it.$2, style: AppText.number(18)),
                  if (it.$3 != null)
                    Text(it.$3!,
                        style: AppText.body(12.5,
                            color: it.$4, w: FontWeight.w600)),
                ],
              ),
            ),
        ],
      );
    });
  }
}

// ------------------------------------------------------------------ AI signals
class _SignalsPanel extends StatelessWidget {
  const _SignalsPanel();

  @override
  Widget build(BuildContext context) {
    return Panel(
      title: 'AI market signals',
      subtitle: 'Tap a signal to see why the model thinks so',
      explain: 'signals',
      child: Column(
        children: [
          for (final s in context.app.signals)
            Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: _SignalTile(signal: s)),
          if (!context.app.signalsLive)
            const DemoNote(
                'Demo signals. Start the backend (uvicorn) to see the trained models.'),
        ],
      ),
    );
  }
}

class _SignalTile extends StatelessWidget {
  const _SignalTile({required this.signal});
  final AiSignal signal;

  @override
  Widget build(BuildContext context) {
    final c = trendColor(signal.trend);
    return Tappable(
      onTap: () => showSignal(context, signal),
      semanticLabel: '${signal.base} signal',
      builder: (context, s) => AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: s.hover ? AppColors.panelHi : AppColors.ink,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: s.focus
                ? AppColors.text
                : (s.hover ? AppColors.brass.fade(0.4) : AppColors.line),
          ),
        ),
        child: Column(
          children: [
            Row(
              children: [
                CoinAvatar(signal.base, size: 34),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(MockData.names[signal.symbol] ?? signal.base,
                          style: AppText.body(14.5, w: FontWeight.w600)),
                      Text(
                          '${signal.model}, ${(signal.confidence * 100).round()}% confident',
                          style: AppText.body(12.5, color: AppColors.muted)),
                    ],
                  ),
                ),
                TrendBadge(trend: signal.trend),
              ],
            ),
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: signal.confidence,
                minHeight: 4,
                backgroundColor: AppColors.line,
                valueColor: AlwaysStoppedAnimation(c),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Future<void> showSignal(BuildContext context, AiSignal s) {
  final c = trendColor(s.trend);
  final name = MockData.names[s.symbol] ?? s.base;
  return showPop<void>(
    context,
    child: Builder(
      builder: (ctx) => PopCard(
        title: '$name looks ${s.trend.label.toLowerCase()}',
        subtitle: '${s.model} model, ${s.horizon.toLowerCase()}',
        icon: trendIcon(s.trend),
        accent: c,
        actions: [
          AppButton(
            label: 'Set an alert',
            icon: Icons.add_alert_rounded,
            kind: ButtonKind.ghost,
            onTap: () {
              final app = ctx.app;
              Navigator.of(ctx).pop();
              app.go(2);
            },
          ),
          AppButton(label: 'Got it', onTap: () => Navigator.of(ctx).pop()),
        ],
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('${(s.confidence * 100).round()}%',
                    style: AppText.display(34, color: c)),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'model probability based on past patterns—not a guarantee and not financial advice',
                    style: AppText.body(14, color: AppColors.muted),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            Text('Why the model thinks this',
                style: AppText.body(14.5, w: FontWeight.w600)),
            const SizedBox(height: 10),
            for (final r in s.reasons)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Icon(Icons.check_circle_outline_rounded,
                          size: 18, color: c),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                        child: Text(r, style: AppText.body(14.5, height: 1.5))),
                  ],
                ),
              ),
            const SizedBox(height: 6),
            const TipBox(
                'A signal is a second opinion, not an order. Check the chart and your limits before you act.'),
          ],
        ),
      ),
    ),
  );
}

// ------------------------------------------------------------------- watchlist
class _Watchlist extends StatelessWidget {
  const _Watchlist({required this.selected, required this.onPick});
  final String selected;
  final ValueChanged<String> onPick;

  @override
  Widget build(BuildContext context) {
    final market = context.market;
    return Panel(
      title: 'Watchlist',
      subtitle: 'Tap a coin to load it into the chart above',
      child: LayoutBuilder(builder: (context, box) {
        final wide = box.maxWidth >= 560;
        return Column(
          children: [
            for (final s in MarketService.symbols)
              Tappable(
                onTap: () => onPick(s),
                semanticLabel: s,
                pressScale: 0.99,
                builder: (context, st) {
                  final t = market.ticker(s);
                  final on = s == selected;
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    margin: const EdgeInsets.only(bottom: 4),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 11),
                    decoration: BoxDecoration(
                      color: on
                          ? AppColors.brass.fade(0.08)
                          : (st.hover ? AppColors.panelHi : Colors.transparent),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: st.focus
                            ? AppColors.text
                            : (on
                                ? AppColors.brass.fade(0.35)
                                : Colors.transparent),
                      ),
                    ),
                    child: Row(
                      children: [
                        CoinAvatar(t.base, size: 34),
                        const SizedBox(width: 12),
                        Expanded(
                          flex: 3,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(t.name,
                                  style:
                                      AppText.body(14.5, w: FontWeight.w600)),
                              Text(t.base,
                                  style: AppText.body(12.5,
                                      color: AppColors.muted)),
                            ],
                          ),
                        ),
                        if (wide) ...[
                          Sparkline(values: t.history),
                          const SizedBox(width: 20)
                        ],
                        Expanded(
                          flex: 2,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(Fmt.usd(t.price),
                                  style: AppText.number(14.5)),
                              ChangeText(t.changePct, size: 12.5),
                            ],
                          ),
                        ),
                        if (wide)
                          SizedBox(
                            width: 96,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(Fmt.compact(t.quoteVolume),
                                    style: AppText.number(14,
                                        color: AppColors.muted,
                                        w: FontWeight.w500)),
                                Text('24h volume',
                                    style: AppText.body(12,
                                        color: AppColors.faint)),
                              ],
                            ),
                          ),
                      ],
                    ),
                  );
                },
              ),
          ],
        );
      }),
    );
  }
}

// --------------------------------------------------- whale + listing snapshots
class _Discover extends StatelessWidget {
  const _Discover();

  @override
  Widget build(BuildContext context) {
    final app = context.app;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Panel(
          title: 'Whale moves',
          subtitle: 'Large transfers in the last hour',
          explain: 'whales',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final w in app.whales.take(3)) _MiniWhale(tx: w),
              const SizedBox(height: 6),
              AppButton(
                label: 'See all whale moves',
                kind: ButtonKind.ghost,
                compact: true,
                onTap: () => app.go(5),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        Panel(
          title: 'Just listed',
          subtitle: 'New coins, rated by risk',
          explain: 'listings',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final l in app.listings.take(3))
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(
                    children: [
                      CoinAvatar(l.symbol, size: 32),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(l.name,
                                style: AppText.body(14, w: FontWeight.w600)),
                            Text('Listed ${Fmt.ago(l.listedAt)}',
                                style:
                                    AppText.body(12.5, color: AppColors.muted)),
                          ],
                        ),
                      ),
                      ChangeText(l.changeSinceListing, size: 13),
                    ],
                  ),
                ),
              AppButton(
                label: 'See all new listings',
                kind: ButtonKind.ghost,
                compact: true,
                onTap: () => app.go(6),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _MiniWhale extends StatelessWidget {
  const _MiniWhale({required this.tx});
  final WhaleTx tx;

  @override
  Widget build(BuildContext context) {
    final c = whaleColor(tx.flow);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Container(
            width: 32,
            height: 32,
            decoration:
                BoxDecoration(color: c.fade(0.14), shape: BoxShape.circle),
            child: Icon(whaleIcon(tx.flow), size: 17, color: c),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${Fmt.coin(tx.amount)} ${tx.coin}',
                    style: AppText.number(14)),
                Text(tx.flow.label,
                    style: AppText.body(12.5, color: AppColors.muted)),
              ],
            ),
          ),
          Text(Fmt.compact(tx.usd),
              style: AppText.number(13.5, color: AppColors.muted)),
        ],
      ),
    );
  }
}

Color whaleColor(WhaleFlow f) => switch (f) {
      WhaleFlow.toExchange => AppColors.warn,
      WhaleFlow.fromExchange => AppColors.bull,
      WhaleFlow.walletToWallet => AppColors.calm,
    };

IconData whaleIcon(WhaleFlow f) => switch (f) {
      WhaleFlow.toExchange => Icons.login_rounded,
      WhaleFlow.fromExchange => Icons.logout_rounded,
      WhaleFlow.walletToWallet => Icons.sync_alt_rounded,
    };

// ------------------------------------------------------------------ AI risk score
class _RiskPanel extends StatelessWidget {
  const _RiskPanel({required this.symbol});
  final String symbol;

  static Color levelColor(String level) => switch (level) {
        'low' => AppColors.bull,
        'high' => AppColors.bear,
        _ => AppColors.warn,
      };

  static String levelLabel(String level) => switch (level) {
        'low' => 'Low risk',
        'high' => 'High risk',
        _ => 'Moderate risk',
      };

  @override
  Widget build(BuildContext context) {
    final r = context.app.risks[symbol];
    final base = symbol.replaceAll('USDT', '');

    return Panel(
      title: '$base risk score',
      subtitle: 'How unstable this coin looks over the next 24 hours',
      explain: 'risk',
      child: r == null
          ? const DemoNote('Start the backend to see the AI risk score.')
          : LayoutBuilder(builder: (context, box) {
              final color = levelColor(r.level);
              final summary = Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Text('${r.riskPct.round()}%',
                          style: AppText.display(44, color: color)),
                      const SizedBox(width: 12),
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Text(levelLabel(r.level),
                            style: AppText.body(16,
                                color: color, w: FontWeight.w600)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  _RiskBar(value: r.riskPct),
                  const SizedBox(height: 6),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text('Low',
                          style: AppText.body(12, color: AppColors.faint)),
                      Text('Moderate',
                          style: AppText.body(12, color: AppColors.faint)),
                      Text('High',
                          style: AppText.body(12, color: AppColors.faint)),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SageAvatar(size: 26),
                      const SizedBox(width: 10),
                      Expanded(
                          child: Text(r.summary,
                              style: AppText.body(14, height: 1.55))),
                    ],
                  ),
                ],
              );

              final factors = Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Why this score',
                      style: AppText.body(14.5, w: FontWeight.w600)),
                  const SizedBox(height: 12),
                  for (final f in r.factors) _factorRow(f),
                  const SizedBox(height: 10),
                  _RiskCopilotInsights(symbol: symbol),
                ],
              );

              if (box.maxWidth >= 820) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 4, child: summary),
                    const SizedBox(width: 32),
                    Expanded(flex: 5, child: factors),
                  ],
                );
              }
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [summary, const SizedBox(height: 24), factors],
              );
            }),
    );
  }

  Widget _factorRow(RiskFactor f) {
    final frac =
        f.max == 0 ? 0.0 : (f.points / f.max).clamp(0.0, 1.0).toDouble();
    final c = frac > 0.66
        ? AppColors.bear
        : frac > 0.33
            ? AppColors.warn
            : AppColors.bull;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                  child: Text(f.name,
                      style: AppText.body(13.5, w: FontWeight.w600))),
              Text('${f.points.round()} / ${f.max.round()}',
                  style: AppText.number(12.5, color: AppColors.muted)),
            ],
          ),
          const SizedBox(height: 5),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: frac,
              minHeight: 5,
              backgroundColor: AppColors.line,
              valueColor: AlwaysStoppedAnimation(c),
            ),
          ),
          const SizedBox(height: 5),
          Text(f.note, style: AppText.body(12.5, color: AppColors.muted)),
        ],
      ),
    );
  }
}

class _RiskCopilotInsights extends StatefulWidget {
  const _RiskCopilotInsights({required this.symbol});
  final String symbol;

  @override
  State<_RiskCopilotInsights> createState() => _RiskCopilotInsightsState();
}

class _RiskCopilotInsightsState extends State<_RiskCopilotInsights> {
  RiskCopilotAnalysis? _analysis;
  RiskSimulation? _simulation;
  bool _loading = true;
  bool _simulating = false;
  String? _error;
  String? _simulationError;
  double _volatilityMultiplier = 1.5;
  int _analysisRequest = 0;
  int _simulationRequest = 0;

  @override
  void initState() {
    super.initState();
    _load();
    _simulate();
  }

  @override
  void didUpdateWidget(covariant _RiskCopilotInsights oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.symbol != widget.symbol) {
      _analysis = null;
      _simulation = null;
      _load();
      _simulate();
    }
  }

  Future<void> _load() async {
    final request = ++_analysisRequest;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await context.app.api.riskCopilot(widget.symbol);
      if (!mounted || request != _analysisRequest) return;
      setState(() {
        _analysis = result;
        _loading = false;
      });
    } catch (e) {
      if (!mounted || request != _analysisRequest) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _simulate() async {
    final request = ++_simulationRequest;
    setState(() {
      _simulating = true;
      _simulationError = null;
    });
    try {
      final result = await context.app.api
          .simulateRisk(widget.symbol, _volatilityMultiplier);
      if (!mounted || request != _simulationRequest) return;
      setState(() {
        _simulation = result;
        _simulating = false;
      });
    } catch (e) {
      if (!mounted || request != _simulationRequest) return;
      setState(() {
        _simulationError = e.toString();
        _simulating = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.ink,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.auto_awesome_rounded,
                  size: 18, color: AppColors.brass),
              const SizedBox(width: 8),
              Expanded(
                  child: Text('CryptoSentinel Risk Copilot',
                      style: AppText.body(15, w: FontWeight.w600))),
              if (_loading)
                const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
              else
                IconButton(
                  tooltip: 'Refresh copilot insights',
                  onPressed: _load,
                  icon: const Icon(Icons.refresh_rounded, size: 18),
                  visualDensity: VisualDensity.compact,
                ),
            ],
          ),
          if (_error != null) ...[
            const SizedBox(height: 6),
            Text('Could not load copilot insights: $_error',
                style: AppText.body(12.5, color: AppColors.bear)),
          ] else if (_analysis != null) ...[
            const SizedBox(height: 8),
            Text('Model consensus',
                style: AppText.body(13.5, w: FontWeight.w600)),
            if (_analysis!.votes.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(
                    'Individual model votes are unavailable in rule-based mode.',
                    style: AppText.body(12.5, color: AppColors.muted)),
              )
            else ...[
              const SizedBox(height: 6),
              Text(
                _analysis!.disagreement
                    ? 'Models disagree: ${_analysis!.agreement}/${_analysis!.modelCount} share the most common view.'
                    : 'Models agree: ${_analysis!.agreement}/${_analysis!.modelCount} share the same view.',
                style: AppText.body(12.5,
                    color: _analysis!.disagreement
                        ? AppColors.warn
                        : AppColors.bull),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 6,
                children: [
                  for (final vote in _analysis!.votes)
                    Text(
                      '${vote.model}: ${vote.trend} (${(vote.confidence * 100).round()}%)',
                      style: AppText.body(12, color: AppColors.muted),
                    ),
                ],
              ),
            ],
            const SizedBox(height: 16),
            Text('Live key levels (UTC)',
                style: AppText.body(13.5, w: FontWeight.w600)),
            const SizedBox(height: 6),
            if (_analysis!.keyLevelsSource != 'binance' ||
                _analysis!.keyLevels.isEmpty)
              Text('Live Binance candle levels are unavailable.',
                  style: AppText.body(12.5, color: AppColors.muted))
            else ...[
              for (final level in _analysis!.keyLevels)
                Padding(
                  padding: const EdgeInsets.only(top: 5),
                  child: Text(
                    '${level.period} (${level.referenceDate}) · '
                    'H ${Fmt.usd(level.high)} ${level.highSide}, '
                    '${level.highDistanceAtr.toStringAsFixed(2)} ATR · '
                    'L ${Fmt.usd(level.low)} ${level.lowSide}, '
                    '${level.lowDistanceAtr.toStringAsFixed(2)} ATR',
                    style: AppText.body(12, color: AppColors.muted),
                  ),
                ),
              const SizedBox(height: 5),
              Text(
                'Levels add context, not a directional probability. The supplied hit-rates are unverified for BTC/ETH.',
                style: AppText.body(11.5, color: AppColors.faint),
              ),
            ],
            const SizedBox(height: 16),
            Text('Historical market twins',
                style: AppText.body(13.5, w: FontWeight.w600)),
            const SizedBox(height: 6),
            if (_analysis!.twins.isEmpty)
              Text('Not enough live candle history to find comparable periods.',
                  style: AppText.body(12.5, color: AppColors.muted))
            else
              for (final twin in _analysis!.twins)
                Padding(
                  padding: const EdgeInsets.only(top: 5),
                  child: Text(
                    '${Fmt.ago(twin.time)}  ·  ${twin.similarityPct.round()}% similar  ·  next 24h ${Fmt.pct(twin.futureReturnPct)}',
                    style: AppText.body(12.5, color: AppColors.muted),
                  ),
                ),
            const SizedBox(height: 5),
            Text('Past outcomes are examples, not predictions.',
                style: AppText.body(11.5, color: AppColors.faint)),
          ],
          const SizedBox(height: 16),
          Text('What if volatility changes?',
              style: AppText.body(13.5, w: FontWeight.w600)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              for (final multiplier in const [1.0, 1.5, 2.0])
                ChoiceChip(
                  label: Text('${multiplier.toStringAsFixed(1)}x'),
                  selected: _volatilityMultiplier == multiplier,
                  onSelected: (_) {
                    setState(() => _volatilityMultiplier = multiplier);
                    _simulate();
                  },
                ),
            ],
          ),
          const SizedBox(height: 8),
          if (_simulating)
            const SizedBox(
                height: 16,
                width: 16,
                child: CircularProgressIndicator(strokeWidth: 2))
          else if (_simulationError != null)
            Text('Could not run scenario: $_simulationError',
                style: AppText.body(12.5, color: AppColors.bear))
          else if (_simulation != null)
            Text(
              'At ${_simulation!.volatilityMultiplier.toStringAsFixed(1)}x volatility, estimated risk changes from '
              '${_simulation!.currentRiskPct.round()}% to ${_simulation!.simulatedRiskPct.round()}% '
              '(${_simulation!.changePctPoints >= 0 ? '+' : ''}${_simulation!.changePctPoints.toStringAsFixed(1)} points).',
              style: AppText.body(12.5, color: AppColors.muted, height: 1.5),
            ),
          const SizedBox(height: 4),
          Text('Illustrative scenario only; it is not a forecast.',
              style: AppText.body(11.5, color: AppColors.faint)),
        ],
      ),
    );
  }
}

/// Green-to-red bar with a marker at the risk percentage.
class _RiskBar extends StatelessWidget {
  const _RiskBar({required this.value});
  final double value; // 0..100

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, box) {
      final x = (value.clamp(0.0, 100.0) / 100 * box.maxWidth).toDouble();
      final left = (x - 9).clamp(0.0, box.maxWidth - 18).toDouble();
      return SizedBox(
        height: 22,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned(
              left: 0,
              right: 0,
              top: 7,
              height: 8,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(4),
                  gradient: const LinearGradient(
                      colors: [AppColors.bull, AppColors.warn, AppColors.bear]),
                ),
              ),
            ),
            Positioned(
              left: left,
              top: 2,
              child: Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  color: AppColors.text,
                  shape: BoxShape.circle,
                  border: Border.all(color: AppColors.ink, width: 3),
                ),
              ),
            ),
          ],
        ),
      );
    });
  }
}
