import 'dart:async';
import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../models/liquidation_models.dart';
import '../services/app_scope.dart';
import '../theme/app_colors.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/bits.dart';
import '../widgets/buttons.dart';
import '../widgets/explain.dart';
import '../widgets/panel.dart';

/// Liquidation Intelligence: observed Binance futures liquidations with time windows,
/// charts, spike detection, market context and a grounded AI explanation.
class LiquidationsScreen extends StatefulWidget {
  const LiquidationsScreen({super.key});

  @override
  State<LiquidationsScreen> createState() => _LiquidationsScreenState();
}

const _longColor = AppColors.bear; // long liquidation = forced SELL
const _shortColor = AppColors.bull; // short liquidation = forced BUY

const _filters = ['all', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'other'];
const _filterLabels = {
  'all': 'All',
  'BTCUSDT': 'BTC',
  'ETHUSDT': 'ETH',
  'SOLUSDT': 'SOL',
  'BNBUSDT': 'BNB',
  'XRPUSDT': 'XRP',
  'other': 'Other',
};

class _LiquidationsScreenState extends State<LiquidationsScreen> {
  String _window = '1h';
  String _filter = 'all';
  LiqStats? _stats;
  LiqAnomalies? _anomalies;
  LiqContext? _context;
  LiqExplanation? _explanation;
  String? _error;
  bool _explaining = false;
  Timer? _timer;
  int _tick = 0;

  String? get _symbol => _filter == 'all' ? null : _filter;

  @override
  void initState() {
    super.initState();
    _load(full: true);
    _timer = Timer.periodic(const Duration(seconds: 10), (_) {
      _tick++;
      _load(full: _tick % 6 == 0); // stats every 10s, context every minute
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool full = false}) async {
    final api = context.app.api;
    try {
      final results = await Future.wait([
        api.liquidationStats(_window, _symbol),
        api.liquidationAnomalies(_symbol),
      ]);
      if (!mounted) return;
      setState(() {
        _stats = results[0] as LiqStats;
        _anomalies = results[1] as LiqAnomalies;
        _error = null;
      });
      if (full) await _loadContext();
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    }
  }

  Future<void> _loadContext() async {
    final focus = (_symbol == null || _symbol == 'other')
        ? _stats?.mostAffected?.label
        : _symbol;
    if (focus == null || focus.isEmpty) {
      setState(() => _context = null);
      return;
    }
    try {
      final ctx = await context.app.api.liquidationContext(focus, _window);
      if (mounted) setState(() => _context = ctx);
    } catch (_) {
      if (mounted) setState(() => _context = null);
    }
  }

  Future<void> _explain() async {
    setState(() => _explaining = true);
    try {
      final e = await context.app.api.liquidationExplain(_window, _symbol);
      if (mounted) setState(() => _explanation = e);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _explaining = false);
    }
  }

  void _change({String? window, String? filter}) {
    setState(() {
      _window = window ?? _window;
      _filter = filter ?? _filter;
      _explanation = null;
      _context = null;
    });
    _load(full: true);
  }

  @override
  Widget build(BuildContext context) {
    final s = _stats;
    return PageBody(maxWidth: 1240, children: [
      _header(s),
      if (_error != null && s == null)
        Panel(
            child: DemoNote(
                'Backend unavailable ($_error). Liquidation data needs the CryptoSense backend running. No demo data is shown.'))
      else if (s == null)
        const Panel(child: Center(child: CircularProgressIndicator()))
      else ...[
        _tiles(s),
        LayoutBuilder(builder: (context, c) {
          final wide = c.maxWidth > 900;
          final left = _timelinePanel(s);
          final right = _longShortPanel(s);
          return wide
              ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(flex: 2, child: left),
                  const SizedBox(width: 16),
                  Expanded(child: right),
                ])
              : Column(children: [left, const SizedBox(height: 16), right]);
        }),
        _bySymbolPanel(s),
        _anomalyPanel(),
        _contextPanel(),
        _explainPanel(),
        LayoutBuilder(builder: (context, c) {
          final wide = c.maxWidth > 900;
          final a = _largestPanel(s);
          final b = _activityPanel(s);
          return wide
              ? Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Expanded(child: a),
                  const SizedBox(width: 16),
                  Expanded(child: b),
                ])
              : Column(children: [a, const SizedBox(height: 16), b]);
        }),
      ],
    ]);
  }

  // ------------------------------------------------------------------ header
  Widget _header(LiqStats? s) {
    final stream = s?.stream;
    final live = stream?.connected ?? false;
    return Panel(
      title: 'Liquidation intelligence',
      subtitle: 'Forced closes of leveraged Binance futures positions',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 12, runSpacing: 10, children: [
          SegmentPills(
            options: const ['5m', '15m', '1h', '4h', '24h'],
            selected: _window,
            onChanged: (w) => _change(window: w),
          ),
          SegmentPills(
            options: _filters,
            labels: _filterLabels,
            selected: _filter,
            onChanged: (f) => _change(filter: f),
          ),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Container(
              width: 9,
              height: 9,
              decoration: BoxDecoration(
                  color: live ? AppColors.bull : AppColors.bear,
                  shape: BoxShape.circle)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              stream == null
                  ? 'Checking the Binance liquidation stream...'
                  : live
                      ? 'Binance stream connected'
                          '${stream.secondsSinceMessage == null ? '' : ', last message ${stream.secondsSinceMessage!.toStringAsFixed(0)}s ago'}'
                          '${stream.reconnects > 0 ? ', ${stream.reconnects} reconnects since start' : ''}'
                      : 'Binance stream disconnected${stream.error == null ? '' : ': ${stream.error}'}. Showing stored events only.',
              style: AppText.body(13.5, color: AppColors.muted),
            ),
          ),
        ]),
        if (stream != null) DemoNote(stream.limitation),
        if (s != null && !s.fullyObserved) DemoNote(s.coverageNote),
      ]),
    );
  }

  // ------------------------------------------------------------------- tiles
  Widget _tiles(LiqStats s) {
    final t = s.summary;
    final largest = s.largest.isEmpty ? null : s.largest.first;
    final tiles = [
      _Tile('Total observed', Fmt.compact(t.totalUsd), '${t.events} events'),
      _Tile('Long liquidations', Fmt.compact(t.longUsd), 'forced sells',
          color: _longColor),
      _Tile('Short liquidations', Fmt.compact(t.shortUsd), 'forced buys',
          color: _shortColor),
      _Tile(
          'Long / short ratio',
          t.ratio == null ? 'n/a' : t.ratio!.toStringAsFixed(2),
          t.longShare == null
              ? 'no valued events'
              : '${t.longShare!.toStringAsFixed(0)}% longs'),
      _Tile(
          'Largest',
          largest == null ? 'n/a' : Fmt.compact(largest.usd),
          largest == null
              ? ''
              : '${_base(largest.symbol)} ${largest.position}, ${Fmt.ago(largest.time)}',
          color: largest == null
              ? null
              : (largest.isLong ? _longColor : _shortColor)),
      _Tile(
          'Most affected',
          s.mostAffected == null ? 'n/a' : _base(s.mostAffected!.label),
          s.mostAffected == null ? '' : Fmt.compact(s.mostAffected!.totalUsd)),
    ];
    return Panel(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(spacing: 28, runSpacing: 18, children: tiles),
        const SizedBox(height: 14),
        Text(t.read, style: AppText.body(14.5, height: 1.5)),
      ]),
    );
  }

  // ------------------------------------------------------------------ charts
  Widget _timelinePanel(LiqStats s) {
    final points = s.timeline;
    final maxY = points.fold<double>(
        0, (m, p) => math.max(m, p.longUsd + p.shortUsd));
    final fmt = DateFormat(_window == '24h' ? 'HH:mm' : 'HH:mm');
    final labelEvery = math.max(1, (points.length / 6).ceil());
    return Panel(
      title: 'Liquidation volume over time',
      subtitle: 'Observed USD per ${_bucketLabel()} (red = longs, green = shorts)',
      child: SizedBox(
        height: 240,
        child: maxY == 0
            ? Center(
                child: Text('No observed liquidations in this window.',
                    style: AppText.body(14, color: AppColors.muted)))
            : BarChart(BarChartData(
                maxY: maxY * 1.15,
                alignment: BarChartAlignment.spaceBetween,
                gridData: _grid(maxY),
                borderData: FlBorderData(show: false),
                titlesData: _titles(
                  bottom: (v) {
                    final i = v.toInt();
                    if (i < 0 || i >= points.length || i % labelEvery != 0) {
                      return '';
                    }
                    return fmt.format(points[i].time);
                  },
                ),
                barTouchData: BarTouchData(
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipColor: (_) => AppColors.panelHi,
                    getTooltipItem: (group, _, rod, __) {
                      final p = points[group.x];
                      return BarTooltipItem(
                        '${fmt.format(p.time)}\nLongs ${Fmt.compact(p.longUsd)}\nShorts ${Fmt.compact(p.shortUsd)}\n${p.count} events',
                        AppText.body(12.5),
                      );
                    },
                  ),
                ),
                barGroups: [
                  for (var i = 0; i < points.length; i++)
                    BarChartGroupData(x: i, barRods: [
                      BarChartRodData(
                        toY: points[i].longUsd + points[i].shortUsd,
                        width: math.max(2, 320 / points.length),
                        borderRadius: BorderRadius.circular(2),
                        rodStackItems: [
                          BarChartRodStackItem(0, points[i].longUsd, _longColor),
                          BarChartRodStackItem(points[i].longUsd,
                              points[i].longUsd + points[i].shortUsd, _shortColor),
                        ],
                      ),
                    ]),
                ],
              )),
      ),
    );
  }

  Widget _longShortPanel(LiqStats s) {
    final t = s.summary;
    final maxY = math.max(t.longUsd, t.shortUsd);
    return Panel(
      title: 'Longs vs shorts',
      subtitle: 'Observed USD in the last $_window',
      child: SizedBox(
        height: 240,
        child: maxY == 0
            ? Center(
                child: Text('Nothing observed yet.',
                    style: AppText.body(14, color: AppColors.muted)))
            : BarChart(BarChartData(
                maxY: maxY * 1.2,
                gridData: _grid(maxY),
                borderData: FlBorderData(show: false),
                titlesData: _titles(
                    bottom: (v) => v.toInt() == 0 ? 'Longs' : 'Shorts'),
                barTouchData: BarTouchData(
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipColor: (_) => AppColors.panelHi,
                    getTooltipItem: (g, _, rod, __) => BarTooltipItem(
                        '${g.x == 0 ? 'Longs' : 'Shorts'} ${Fmt.compact(rod.toY)}\n'
                        '${g.x == 0 ? t.longCount : t.shortCount} events',
                        AppText.body(12.5)),
                  ),
                ),
                barGroups: [
                  BarChartGroupData(x: 0, barRods: [
                    BarChartRodData(
                        toY: t.longUsd,
                        color: _longColor,
                        width: 46,
                        borderRadius: BorderRadius.circular(6)),
                  ]),
                  BarChartGroupData(x: 1, barRods: [
                    BarChartRodData(
                        toY: t.shortUsd,
                        color: _shortColor,
                        width: 46,
                        borderRadius: BorderRadius.circular(6)),
                  ]),
                ],
              )),
      ),
    );
  }

  Widget _bySymbolPanel(LiqStats s) {
    final rows = s.bySymbol.take(12).toList();
    final maxY = rows.fold<double>(0, (m, r) => math.max(m, r.totalUsd));
    return Panel(
      title: 'Liquidations by coin',
      subtitle: 'Top coins by observed USD in the last $_window. Tap a bar for details.',
      child: SizedBox(
        height: 250,
        child: rows.isEmpty
            ? Center(
                child: Text('No coins with observed liquidations.',
                    style: AppText.body(14, color: AppColors.muted)))
            : BarChart(BarChartData(
                maxY: maxY * 1.15,
                gridData: _grid(maxY),
                borderData: FlBorderData(show: false),
                titlesData: _titles(bottom: (v) {
                  final i = v.toInt();
                  return i >= 0 && i < rows.length ? _base(rows[i].label) : '';
                }),
                barTouchData: BarTouchData(
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipColor: (_) => AppColors.panelHi,
                    getTooltipItem: (g, _, rod, __) {
                      final r = rows[g.x];
                      return BarTooltipItem(
                          '${_base(r.label)}\nLongs ${Fmt.compact(r.longUsd)}\nShorts ${Fmt.compact(r.shortUsd)}\n${r.events} events',
                          AppText.body(12.5));
                    },
                  ),
                ),
                barGroups: [
                  for (var i = 0; i < rows.length; i++)
                    BarChartGroupData(x: i, barRods: [
                      BarChartRodData(
                        toY: rows[i].totalUsd,
                        width: 22,
                        borderRadius: BorderRadius.circular(4),
                        rodStackItems: [
                          BarChartRodStackItem(0, rows[i].longUsd, _longColor),
                          BarChartRodStackItem(
                              rows[i].longUsd, rows[i].totalUsd, _shortColor),
                        ],
                      ),
                    ]),
                ],
              )),
      ),
    );
  }

  // --------------------------------------------------------------- anomalies
  Widget _anomalyPanel() {
    final a = _anomalies;
    return Panel(
      title: 'Spike detection',
      subtitle: 'Last 5 minutes compared with a rolling baseline',
      child: a == null
          ? const SizedBox.shrink()
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (a.status == 'insufficient_baseline')
                DemoNote(a.note)
              else if (a.items.isEmpty)
                Text('No unusual liquidation activity right now.',
                    style: AppText.body(14.5))
              else
                for (final item in a.items)
                  Container(
                    margin: const EdgeInsets.only(bottom: 10),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppColors.ink,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                          color: item.severity == 'high'
                              ? AppColors.bear
                              : AppColors.warn),
                    ),
                    child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(Icons.bolt_rounded,
                              color: item.severity == 'high'
                                  ? AppColors.bear
                                  : AppColors.warn),
                          const SizedBox(width: 10),
                          Expanded(
                              child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                Text(
                                    '${item.type.replaceAll('_', ' ')}${item.symbol == null ? '' : ' · ${_base(item.symbol!)}'} · ${item.severity}',
                                    style: AppText.body(13.5,
                                        w: FontWeight.w600)),
                                const SizedBox(height: 4),
                                Text(item.message,
                                    style: AppText.body(13.5, height: 1.45)),
                              ])),
                        ]),
                  ),
              if (a.method.isNotEmpty) DemoNote('Method: ${a.method}.'),
            ]),
    );
  }

  // ----------------------------------------------------------------- context
  Widget _contextPanel() {
    final c = _context;
    return Panel(
      title: 'Market context',
      subtitle: c == null
          ? 'Liquidations next to price, open interest, funding and volatility'
          : '${_base(c.symbol)} over ${c.window}: liquidations next to price, open interest and funding',
      child: c == null
          ? Text('Pick a coin, or wait for liquidations to arrive.',
              style: AppText.body(14, color: AppColors.muted))
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 28, runSpacing: 14, children: [
                _Tile(
                    'Price change',
                    c.priceChangePct == null ? 'n/a' : Fmt.pct(c.priceChangePct!),
                    c.priceDirection,
                    color: c.priceDirection == 'up'
                        ? AppColors.bull
                        : c.priceDirection == 'down'
                            ? AppColors.bear
                            : null),
                _Tile(
                    'Open interest',
                    c.oiChangePct == null ? 'n/a' : Fmt.pct(c.oiChangePct!),
                    c.oiDirection),
                _Tile(
                    'Funding rate',
                    c.fundingRate == null
                        ? 'n/a'
                        : '${(c.fundingRate! * 100).toStringAsFixed(4)}%',
                    'latest'),
                _Tile('Volume vs prior',
                    c.volumeVsPrior == null ? 'n/a' : '${c.volumeVsPrior}x', ''),
                _Tile('ATR', c.atrPct == null ? 'n/a' : '${c.atrPct}%',
                    'per candle'),
              ]),
              const SizedBox(height: 16),
              Text('Possible scenarios',
                  style: AppText.body(13, color: AppColors.muted)),
              const SizedBox(height: 8),
              for (final sc in c.scenarios)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(sc.name,
                            style: AppText.body(14.5, w: FontWeight.w600)),
                        if (sc.description.isNotEmpty)
                          Text(sc.description,
                              style: AppText.body(13.5, height: 1.45)),
                        for (final x in sc.supporting)
                          Text('✓ $x',
                              style: AppText.body(13, color: AppColors.bull)),
                        for (final x in sc.contradicting)
                          Text('✗ $x',
                              style: AppText.body(13, color: AppColors.bear)),
                      ]),
                ),
              if (c.scenarios.isNotEmpty) DemoNote(c.scenarios.first.caveat),
              if (c.unavailable.isNotEmpty)
                DemoNote('Unavailable right now: ${c.unavailable.join(', ')}.'),
              const DemoNote(
                  'Support & resistance zones will be added here with the S/R engine (next phase).'),
            ]),
    );
  }

  // ------------------------------------------------------------- explanation
  Widget _explainPanel() {
    final e = _explanation;
    return Panel(
      title: 'AI explanation',
      subtitle: 'Explains the verified numbers above; it cannot add new ones',
      trailing: AppButton(
        label: _explaining ? 'Explaining...' : 'Explain',
        icon: Icons.auto_awesome_rounded,
        compact: true,
        onTap: _explaining ? null : _explain,
      ),
      child: e == null
          ? Text(
              'Press Explain for answers to: why activity changed, which side dominates, which coins are unusual, '
              'whether price and open interest moved with it, and what supports or contradicts each scenario.',
              style: AppText.body(14, color: AppColors.muted, height: 1.5))
          : Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const SageAvatar(size: 26),
                const SizedBox(width: 8),
                Text(
                    e.source == 'rules'
                        ? 'Rules-based answer (no AI rewrite)'
                        : 'Written by ${e.source == 'claude' ? 'Claude' : 'the configured LLM'}, numbers verified',
                    style: AppText.body(12.5, color: AppColors.faint)),
              ]),
              const SizedBox(height: 10),
              Text(e.text, style: AppText.body(14.5, height: 1.55)),
              if (e.note.isNotEmpty) DemoNote(e.note),
              const SizedBox(height: 10),
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: Text('Show the data-backed answer to each question',
                    style: AppText.body(13.5, color: AppColors.muted)),
                children: [
                  for (final qa in e.answers)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(qa.question,
                                style:
                                    AppText.body(13.5, w: FontWeight.w600)),
                            Text(qa.answer,
                                style: AppText.body(13.5, height: 1.45)),
                          ]),
                    ),
                ],
              ),
            ]),
    );
  }

  // ------------------------------------------------------------------ tables
  Widget _largestPanel(LiqStats s) => Panel(
        title: 'Largest observed liquidations',
        subtitle: 'Last $_window',
        child: Column(children: [
          if (s.largest.isEmpty)
            Text('None yet.', style: AppText.body(14, color: AppColors.muted)),
          for (final e in s.largest) _EventRow(e),
        ]),
      );

  Widget _activityPanel(LiqStats s) => Panel(
        title: 'Recent activity',
        subtitle: 'Newest observed events',
        child: Column(children: [
          if (s.recent.isEmpty)
            Text('Waiting for events.',
                style: AppText.body(14, color: AppColors.muted)),
          for (final e in s.recent.take(15)) _EventRow(e, showTime: true),
        ]),
      );

  // ----------------------------------------------------------------- helpers
  String _bucketLabel() => const {
        '5m': '15 seconds',
        '15m': '30 seconds',
        '1h': '2 minutes',
        '4h': '10 minutes',
        '24h': 'hour',
      }[_window]!;

  FlGridData _grid(double maxY) => FlGridData(
        drawVerticalLine: false,
        horizontalInterval: maxY > 0 ? maxY / 4 : 1,
        getDrawingHorizontalLine: (_) =>
            const FlLine(color: AppColors.line, strokeWidth: 1),
      );

  FlTitlesData _titles({required String Function(double) bottom}) =>
      FlTitlesData(
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        rightTitles:
            const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        leftTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 52,
            getTitlesWidget: (v, meta) => v == meta.max
                ? const SizedBox.shrink()
                : Text(Fmt.compact(v),
                    style: AppText.body(11, color: AppColors.faint)),
          ),
        ),
        bottomTitles: AxisTitles(
          sideTitles: SideTitles(
            showTitles: true,
            reservedSize: 26,
            getTitlesWidget: (v, _) => Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(bottom(v),
                  style: AppText.body(11, color: AppColors.faint)),
            ),
          ),
        ),
      );
}

String _base(String symbol) => symbol.replaceAll('USDT', '');

class _Tile extends StatelessWidget {
  const _Tile(this.label, this.value, this.note, {this.color});
  final String label;
  final String value;
  final String note;
  final Color? color;

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 150,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label, style: AppText.body(13, color: AppColors.muted)),
          const SizedBox(height: 4),
          Text(value, style: AppText.display(24, color: color ?? AppColors.text)),
          if (note.isNotEmpty)
            Text(note,
                style: AppText.body(12.5, color: color ?? AppColors.faint),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
        ]),
      );
}

class _EventRow extends StatelessWidget {
  const _EventRow(this.e, {this.showTime = false});
  final LiqEvent e;
  final bool showTime;

  @override
  Widget build(BuildContext context) {
    final color = e.isLong ? _longColor : _shortColor;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(children: [
        Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 10),
        SizedBox(
            width: 64,
            child: Text(_base(e.symbol), style: AppText.body(14))),
        SizedBox(
            width: 52,
            child: Text(e.isLong ? 'Long' : 'Short',
                style: AppText.body(14, color: color))),
        Expanded(
            child: Text(
                e.usdValid ? Fmt.compact(e.usd) : 'USD n/a',
                style: AppText.body(14, w: FontWeight.w600))),
        Text(Fmt.usd(e.price),
            style: AppText.body(13, color: AppColors.muted)),
        const SizedBox(width: 12),
        SizedBox(
          width: 64,
          child: Text(showTime ? Fmt.clock(e.time) : Fmt.ago(e.time),
              textAlign: TextAlign.right,
              style: AppText.body(12.5, color: AppColors.faint)),
        ),
      ]),
    );
  }
}
