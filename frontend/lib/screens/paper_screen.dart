import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/app_scope.dart';
import '../services/market_service.dart';
import '../services/paper_service.dart';
import '../theme/app_colors.dart';
import '../theme/app_theme.dart';
import '../utils/format.dart';
import '../widgets/account.dart';
import '../widgets/bits.dart';
import '../widgets/buttons.dart';
import '../widgets/explain.dart';
import '../widgets/panel.dart';
import '../widgets/pop.dart';

Color _levelColor(String? level) => switch (level) {
      'low' => AppColors.bull,
      'high' => AppColors.bear,
      _ => AppColors.warn,
    };

String _levelWord(String? level) => switch (level) {
      'low' => 'low',
      'high' => 'high',
      _ => 'moderate',
    };

/// Paper trading: practice with 10,000 pretend dollars at real live prices.
class PaperScreen extends StatefulWidget {
  const PaperScreen({super.key});

  @override
  State<PaperScreen> createState() => _PaperScreenState();
}

class _PaperScreenState extends State<PaperScreen> {
  late final PaperService _service = PaperService(context.app.api);

  PaperAccount? _acct;
  List<PaperTradeRow> _trades = [];
  bool _loading = false;
  bool _busy = false;
  String? _error;

  String _symbol = 'BTCUSDT';
  String _side = 'buy';
  int _percent = 100;
  final _amount = TextEditingController(text: '500');

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final a = await _service.account();
      final t = await _service.trades();
      if (!mounted) return;
      setState(() {
        _acct = a;
        _trades = t;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _order() async {
    if (_busy) return;
    final usd = double.tryParse(_amount.text.replaceAll(',', '').trim());
    if (_side == 'buy' && (usd == null || usd < 1)) {
      toast(context, 'Enter an amount of at least 1 dollar.',
          color: AppColors.bear, icon: Icons.error_outline_rounded);
      return;
    }
    setState(() => _busy = true);
    try {
      final r = await _service.trade(
        symbol: _symbol,
        side: _side,
        usd: _side == 'buy' ? usd : null,
        percent: _side == 'sell' ? _percent.toDouble() : null,
      );
      if (!mounted) return;
      setState(() {
        _acct = r.account;
        _trades = [r.trade, ..._trades];
      });
      final t = r.trade;
      toast(
        context,
        '${t.isBuy ? 'Bought' : 'Sold'} ${Fmt.coin(t.amount)} ${t.base} at ${Fmt.usd(t.price)}',
      );
      if (r.warning != null) _showWarning(r.warning!);
    } on ApiException catch (e) {
      if (mounted)
        toast(context, e.message,
            color: AppColors.bear, icon: Icons.error_outline_rounded);
    } catch (_) {
      if (mounted) {
        toast(context, 'Could not place the order. Is the backend running?',
            color: AppColors.bear, icon: Icons.error_outline_rounded);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _showWarning(String text) {
    showPop<void>(
      context,
      maxWidth: 480,
      child: Builder(
        builder: (ctx) => PopCard(
          title: 'Sage has a thought',
          subtitle: 'About the order you just placed',
          leading: const SageAvatar(size: 40),
          actions: [
            AppButton(label: 'Got it', onTap: () => Navigator.of(ctx).pop())
          ],
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(text, style: AppText.body(15, height: 1.6)),
              const SizedBox(height: 14),
              const TipBox(
                  'This is practice money, so mistakes here are free. Notice the pattern and learn from it.'),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _reset() async {
    final ok = await confirmPop(
      context,
      title: 'Reset your practice account?',
      message:
          'This deletes all your practice trades and gives you 10,000 dollars of pretend cash again.',
      confirmLabel: 'Reset',
    );
    if (!ok) return;
    try {
      final a = await _service.reset();
      if (!mounted) return;
      setState(() {
        _acct = a;
        _trades = [];
      });
      toast(context, 'Practice account reset');
    } catch (e) {
      if (mounted)
        toast(context, e.toString(),
            color: AppColors.bear, icon: Icons.error_outline_rounded);
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: Listenable.merge([context.app, context.market]),
      builder: (context, _) => _page(context),
    );
  }

  Widget _message(String title, String text, {Widget? action}) =>
      PageBody(maxWidth: 760, children: [
        Panel(
          title: title,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(text,
                  style: AppText.body(15, color: AppColors.muted, height: 1.6)),
              if (action != null) ...[const SizedBox(height: 16), action],
            ],
          ),
        ),
      ]);

  Widget _page(BuildContext context) {
    final app = context.app;
    final market = context.market;

    if (!app.loggedIn) {
      _acct = null;
      _trades = [];
      _error = null;
    }
    if (!app.backendOnline) {
      return _message('Paper trading needs the backend',
          'Start the backend (uvicorn) and refresh. Your practice account is saved on the server.');
    }
    if (!app.loggedIn) {
      return _message(
        'Practice trading with pretend money',
        'Sign in to get 10,000 dollars of practice cash. Trade real coins at live prices, with no real money at risk, '
            'and see how the AI risk score would have helped you.',
        action: AppButton(
            label: 'Sign in',
            icon: Icons.login_rounded,
            onTap: () => showAuth(context)),
      );
    }
    if (_acct == null && !_loading && _error == null) {
      _loading = true;
      WidgetsBinding.instance.addPostFrameCallback((_) => _load());
    }
    if (_acct == null) {
      return _message(
        _error == null
            ? 'Loading your practice account...'
            : 'Could not load your account',
        _error ?? 'One moment.',
        action: _error == null
            ? null
            : AppButton(
                label: 'Try again', icon: Icons.refresh_rounded, onTap: _load),
      );
    }

    final a = _acct!;
    double livePrice(String s, double fallback) {
      final t = market.tickers[s];
      return t == null || t.price <= 0 ? fallback : t.price;
    }

    final invested = a.positions.fold<double>(
        0, (sum, p) => sum + p.amount * livePrice(p.symbol, p.price));
    final equity = a.cash + invested;
    final pnl = equity - a.startingCash;
    final pnlPct = a.startingCash == 0 ? 0.0 : pnl / a.startingCash * 100;
    final up = pnl >= 0;

    final highRiskBuys =
        _trades.where((t) => t.isBuy && t.riskLevel == 'high').length;

    return PageBody(children: [
      Panel(
        title: 'Your practice account',
        subtitle:
            'Pretend money, real live prices, a 0.1% fee like a real exchange',
        trailing: AppButton(
          label: 'Reset',
          icon: Icons.restart_alt_rounded,
          kind: ButtonKind.ghost,
          color: AppColors.muted,
          compact: true,
          onTap: _reset,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(Fmt.usd(equity), style: AppText.display(40)),
            const SizedBox(height: 4),
            Text(
              '${up ? '+' : '-'}${Fmt.usd(pnl.abs())} (${Fmt.pct(pnlPct)}) since you started with ${Fmt.usd(a.startingCash)}',
              style: AppText.number(14.5,
                  color: up ? AppColors.bull : AppColors.bear),
            ),
            const SizedBox(height: 18),
            Wrap(
              spacing: 28,
              runSpacing: 14,
              children: [
                _Stat('Cash', Fmt.usd(a.cash)),
                _Stat('In coins', Fmt.usd(invested)),
                _Stat('Trades', '${a.tradesCount}'),
                _Stat(
                    'Winning sells',
                    a.winRate == null
                        ? 'No sells yet'
                        : '${a.winRate!.round()}%'),
              ],
            ),
            if (highRiskBuys > 0) ...[
              const SizedBox(height: 18),
              TipBox(
                'You bought $highRiskBuys time${highRiskBuys == 1 ? '' : 's'} while the AI risk score was high. '
                'Check the history below and see how those trades went.',
                icon: Icons.shield_outlined,
              ),
            ],
          ],
        ),
      ),
      TwoColumn(
        leftFlex: 1,
        rightFlex: 1,
        left: _tradePanel(a, market),
        right: _positionsPanel(a, livePrice),
      ),
      Panel(
        title: 'Trade history',
        subtitle: _trades.isEmpty
            ? 'Your practice trades will appear here'
            : 'Newest first',
        child: _trades.isEmpty
            ? Text('No trades yet. Place your first order above.',
                style: AppText.body(14.5, color: AppColors.muted))
            : Column(
                children: [for (final t in _trades.take(30)) _tradeRow(t)]),
      ),
    ]);
  }

  // ------------------------------------------------------------ trade panel
  Widget _tradePanel(PaperAccount a, MarketService market) {
    final app = context.app;
    final base = _symbol.replaceAll('USDT', '');
    final t = market.ticker(_symbol);
    final price = t?.price ?? 0; // 0 = no live price; previews below say so
    final pos = a.positionOf(_symbol);
    final risk = app.risks[_symbol];

    String preview;
    if (t == null) {
      preview = 'Live price unavailable, so no estimate can be shown.';
    } else if (_side == 'buy') {
      final usd = double.tryParse(_amount.text.replaceAll(',', '').trim()) ?? 0;
      final coins = price <= 0 ? 0 : (usd - usd * 0.001) / price;
      preview = usd < 1
          ? 'Enter an amount to see what you would get.'
          : 'About ${Fmt.coin(coins.toDouble())} $base for ${Fmt.usd(usd)} (fee ${Fmt.usd(usd * 0.001)}).';
    } else if (pos == null) {
      preview = 'You do not hold any $base yet.';
    } else {
      final coins = pos.amount * _percent / 100;
      final gross = coins * price;
      preview =
          'Sell ${Fmt.coin(coins)} $base for about ${Fmt.usd(gross - gross * 0.001)} (fee ${Fmt.usd(gross * 0.001)}).';
    }

    return Panel(
      title: 'Place an order',
      subtitle: t == null
          ? '$base: live price unavailable right now'
          : '$base is ${Fmt.usd(price)} right now',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CoinChoice(
            selected: _symbol,
            tickers: market.tickers,
            onChanged: (s) => setState(() => _symbol = s),
          ),
          if (risk != null) ...[
            const SizedBox(height: 14),
            Row(
              children: [
                Icon(Icons.shield_outlined,
                    size: 18, color: _levelColor(risk.level)),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'AI risk for $base: ${risk.riskPct.round()}% (${_levelWord(risk.level)})',
                    style: AppText.body(13.5,
                        color: _levelColor(risk.level), w: FontWeight.w600),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 18),
          SegmentPills(
            options: const ['buy', 'sell'],
            labels: const {'buy': 'Buy', 'sell': 'Sell'},
            selected: _side,
            onChanged: (s) => setState(() => _side = s),
          ),
          if (_side == 'buy') ...[
            const FieldLabel('Amount to spend (USD)'),
            TextField(
              controller: _amount,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              style: AppText.number(15, w: FontWeight.w500),
              decoration: const InputDecoration(prefixText: '\$ '),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final v in const [100, 500, 1000, 2500])
                  AppButton(
                    label: '\$$v',
                    kind: ButtonKind.ghost,
                    color: AppColors.muted,
                    compact: true,
                    onTap: () => setState(() => _amount.text = '$v'),
                  ),
              ],
            ),
          ] else ...[
            const FieldLabel('How much of your coins to sell'),
            SegmentPills(
              options: const ['25', '50', '75', '100'],
              labels: const {
                '25': '25%',
                '50': '50%',
                '75': '75%',
                '100': 'All'
              },
              selected: '$_percent',
              onChanged: (v) => setState(() => _percent = int.parse(v)),
            ),
          ],
          const SizedBox(height: 14),
          Text(preview, style: AppText.body(13.5, color: AppColors.muted)),
          const SizedBox(height: 18),
          AppButton(
            label: _busy
                ? 'Placing order...'
                : (_side == 'buy' ? 'Buy $base' : 'Sell $base'),
            icon: _side == 'buy'
                ? Icons.add_shopping_cart_rounded
                : Icons.sell_rounded,
            color: _side == 'buy' ? AppColors.bull : AppColors.bear,
            onTap: _busy ? null : _order,
          ),
        ],
      ),
    );
  }

  // -------------------------------------------------------- positions panel
  Widget _positionsPanel(
      PaperAccount a, double Function(String, double) livePrice) {
    final app = context.app;
    return Panel(
      title: 'Your coins',
      subtitle: a.positions.isEmpty
          ? 'Nothing yet'
          : 'Profit and loss at live prices',
      child: a.positions.isEmpty
          ? Text(
              'Buy a coin to see it here, with its profit or loss updating live.',
              style: AppText.body(14.5, color: AppColors.muted))
          : Column(
              children: [
                for (final p in a.positions)
                  Builder(builder: (context) {
                    final price = livePrice(p.symbol, p.price);
                    final value = p.amount * price;
                    final pnl = value - p.amount * p.avgPrice;
                    final pct =
                        p.avgPrice == 0 ? 0.0 : (price / p.avgPrice - 1) * 100;
                    final risk = app.risks[p.symbol];
                    return Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: AppColors.ink,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: AppColors.line),
                      ),
                      child: Row(
                        children: [
                          CoinAvatar(p.base, size: 38),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('${Fmt.coin(p.amount)} ${p.base}',
                                    style:
                                        AppText.body(14.5, w: FontWeight.w600)),
                                Text('Bought at ${Fmt.usd(p.avgPrice)}',
                                    style: AppText.body(12.5,
                                        color: AppColors.muted)),
                                if (risk != null)
                                  Text(
                                      'Risk now ${risk.riskPct.round()}% (${_levelWord(risk.level)})',
                                      style: AppText.body(12.5,
                                          color: _levelColor(risk.level))),
                              ],
                            ),
                          ),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(Fmt.usd(value), style: AppText.number(14.5)),
                              Text(
                                  '${pnl >= 0 ? '+' : '-'}${Fmt.usd(pnl.abs())} (${Fmt.pct(pct)})',
                                  style: AppText.number(12.5,
                                      color: pnl >= 0
                                          ? AppColors.bull
                                          : AppColors.bear)),
                              const SizedBox(height: 6),
                              AppButton(
                                label: 'Sell',
                                kind: ButtonKind.ghost,
                                color: AppColors.bear,
                                compact: true,
                                onTap: () => setState(() {
                                  _symbol = p.symbol;
                                  _side = 'sell';
                                  _percent = 100;
                                }),
                              ),
                            ],
                          ),
                        ],
                      ),
                    );
                  }),
              ],
            ),
    );
  }

  // ----------------------------------------------------------- history row
  Widget _tradeRow(PaperTradeRow t) {
    final color = t.isBuy ? AppColors.bull : AppColors.bear;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.ink,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.line),
      ),
      child: Row(
        children: [
          Tag(t.isBuy ? 'Buy' : 'Sell', color: color),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${Fmt.coin(t.amount)} ${t.base} at ${Fmt.usd(t.price)}',
                    style: AppText.body(14, w: FontWeight.w600)),
                Text(
                  '${Fmt.ago(t.time)}'
                  '${t.riskPct == null ? '' : ', risk was ${t.riskPct!.round()}% (${_levelWord(t.riskLevel)})'}',
                  style: AppText.body(12.5, color: AppColors.muted),
                ),
              ],
            ),
          ),
          if (t.realizedPnl != null)
            Text(
              '${t.realizedPnl! >= 0 ? '+' : '-'}${Fmt.usd(t.realizedPnl!.abs())}',
              style: AppText.number(14,
                  color: t.realizedPnl! >= 0 ? AppColors.bull : AppColors.bear),
            )
          else
            Text(Fmt.usd(t.usd),
                style: AppText.number(14, color: AppColors.muted)),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.label, this.value);
  final String label, value;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppText.body(12.5, color: AppColors.faint)),
          const SizedBox(height: 2),
          Text(value, style: AppText.number(17)),
        ],
      );
}
