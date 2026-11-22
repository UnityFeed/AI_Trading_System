# What we can build from the two research reports (22 Nov 2026)

Check of every strategy and data source in
`2026-11-22_long_only_strategy_deep_dive_v2.md` (S1-S15) and
`2026-11-22_market_research_blueprint.md` (strategies A-F, data layers),
against what this project can actually get. Our limits: spot only, long
only, no margin, Kraken fee 0.80% per side, free data only, Python standard
library, runs on one Windows PC.

Evidence grades (A best, E weakest) are the deep dive's.

## A. Possible now, with the hourly price/volume data we already have

| Strategy | Source | Evidence | What we need to build |
|---|---|---|---|
| S1 price/SMA ensemble (20/50/100) | deep dive #1 | A | SMA blocks + graded exposure engine |
| S2 time-series momentum ensemble (28/56/91/182 days) | deep dive #2 | A signal / B- trading | return-over-L blocks + graded exposure |
| S3 core + overlay (50% always held) | deep dive #3 | E (arithmetic) | graded exposure engine |
| S4 volatility cap | deep dive #4 | A (other assets), mixed for BTC | EWMA volatility (new indicator) |
| S5 banded BTC/cash rebalance (60%, 10 pp band) | deep dive #5 | A theory, C/D crypto | graded exposure engine |
| S6 Donchian 50/20 breakout (as one vote) | deep dive #8 | C/B | Donchian high/low (new indicator) |
| S10 trailing stop (20-30% from peak) | deep dive | C | exit rule |
| S11 DCA (for new cash only) | deep dive | D | deposits in the engine (later) |
| A Trend following (SMA, ADX, Donchian, relative volume, ATR) | blueprint | close to what we already test | ADX and Donchian (new indicators) |
| B Mean reversion (BB, RSI, ADX range filter) | blueprint | C; our own tests: did not hold up | ADX; VWAP approximation |
| C Pullback continuation, without CVD | blueprint | not graded | swing high/low detection |
| E Failed-breakdown reversal, price-only version | blueprint | not graded | swing lows, previous-day high/low |

Indicators that can be computed from our candles: SMA, ADX, Donchian,
rate of change, realized volatility, OBV, swing highs/lows, previous-day
levels, the Coinbase-vs-Kraken price gap (a free "Coinbase premium").

**VWAP and volume profile:** exact VWAP needs every trade, but for daily
decisions an approximation from hourly candles (typical price x volume) is
close enough. A volume profile can be approximated by spreading each hourly
candle's volume over its high-low range. Both are possible now.

Most of the strongest-evidence items (S1-S5) need one engine change: the
backtester can only be 0% or 100% in BTC today. A graded exposure engine
(0-100%, trade only when the change exceeds a band, fees on the traded
amount) is roadmap step 9a.

## B. Possible with extra FREE historical data (download once, then daily)

| Data | Free source | History | Used by | Evidence |
|---|---|---|---|---|
| MVRV (market cap vs realized cap) | Coin Metrics community API | 2010+ daily | S8 exposure cap | C |
| Hash rate | blockchain.com / mempool.space | 2009+ daily | S9 entry filter | B- |
| Macro: dollar index, yields, Fed balance sheet | FRED | decades, daily/weekly | regime context | weak for timing |
| Funding rate (perpetual futures) | Binance public API | Sep 2019+ | S14 filter | C/D, deep dive says skip for now |
| Implied volatility (DVOL) | Deribit public API | 2021+ | volatility regime | not tested |
| Fear & Greed, ETF flows | alternative.me, issuers | 2018+ / 2024+ | - | negative: skip |

All values must be stored as they were known on the day (snapshot), and used
with a 1-2 day delay, because on-chain numbers get revised.

## C. Only possible from NOW on (no free history), or not at all for us

| Data | Free live source | History | Used by |
|---|---|---|---|
| Order book depth / imbalance, spread | Kraken public order book (REST/WebSocket) | none free | D, E (absorption, sweeps) |
| Open interest | Binance public API | last 30 days only | D |
| Liquidations | exchange WebSocket streams | none free | D |
| Options skew, put/call | Deribit public API | live only (free) | vision report |
| Aggressive buy/sell volume (CVD) | Kraken public trades: every trade has a buy/sell side | full history, but heavy (see below) | C, D, E |

- **Order books can only be recorded going forward**, and only while a
  program runs. On a home PC that is switched off at night the record has
  holes. Years of recording are needed before a strategy can be tested on
  it, and this data mainly helps minute-to-hour timing, which our 0.80% fee
  makes unprofitable (our 1h tests lost almost everything after fees).
- **CVD from Kraken trades is possible.** Checked 22 Nov 2026: Kraken's
  public trade history gives `[price, volume, time, side b/s, type l/m, ...,
  trade id]`. Our `kraken_trades_provider` already downloads this but drops
  the side. One page = 1,000 trades (~25 minutes in Nov 2026); trade ids are
  at ~114 million, so the full history is ~114,000 requests (more than a day
  of downloading at Kraken's public rate limit). Recent years only would be
  far less. Daily-timeframe evidence for CVD is weak.
- **Strategy F (funding/basis carry)** needs a short futures position:
  excluded (spot only, no shorting).
- **Strategy D (liquidation reversal)** needs liquidations, open interest
  and order books with history: not testable for us.

## Conclusion

- Everything with the best evidence (S1-S5, plus S6, S8, S9) can be built and
  tested with our own data plus two free downloads. None of it needs order
  books, live data or exact VWAP.
- The order-flow and derivatives ideas (blueprint sections 3, 8 and
  strategies D-F) are built for short-term trading with low fees and paid
  data. For a daily, spot-only, 0.80%-fee account they are the lowest
  priority.
- Recommended order: graded exposure engine (9a) -> trials ledger (9b) ->
  S1-S6 (9c) -> MVRV and hash rate (9d) -> paper trade the survivor (9e).
  Optional, any time: keep the buy/sell side in the Kraken trades download,
  and start a small order-book recorder if the owner wants that data to
  exist in a few years.

## Built and first tested (22 Nov 2026)

Everything in A and B above was built the same day: graded exposure engine,
S1-S6, S8, S9 and "50% core + Daily trend + MACD" in the registry (Strategy
tester, chart, overview, paper trader), Coin Metrics download, metrics,
Deflated Sharpe, PBO, trials ledger. From C: the Kraken trade side is kept
and an order-book/order-flow recorder runs from now on.

First result (cloud test database, 0.80% fee): the report's strategies trade
too often for Kraken's fee and end at 3-24% of buy-and-hold's end value; the
only one level with holding is 50% core + our Daily trend + MACD overlay.
Numbers: CLAUDE.md, Status. Run `python -m scripts.run_strategy_research`
on the real database to confirm.
