/// Display names of the tracked coins (static labels, not market data).
const coinNames = {
  'BTCUSDT': 'Bitcoin',
  'ETHUSDT': 'Ethereum',
  'BNBUSDT': 'BNB',
  'SOLUSDT': 'Solana',
  'XRPUSDT': 'XRP',
  'ADAUSDT': 'Cardano',
};

String coinName(String symbol) =>
    coinNames[symbol] ?? symbol.replaceAll('USDT', '');
