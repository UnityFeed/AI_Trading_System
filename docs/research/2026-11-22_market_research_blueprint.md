# Bitcoin Market Research and Trading Strategy Framework

**Research date:** 22 November 2026\
**Market:** Bitcoin (BTC)\
**Purpose:** Research blueprint for a data-driven, rules-based Bitcoin
trading system.

> **Important:** This document is a research and engineering blueprint,
> not investment advice. Market figures are historical snapshots from
> the research date, not live quotes. All proposed strategies require
> independent testing, realistic execution costs, and out-of-sample
> validation before any live use.

## Executive overview

The objective is not simply to identify when Bitcoin is overbought or
oversold. A robust system should answer five separate questions:

1.  **Market regime:** Bull trend, bear trend, consolidation, recovery,
    or high-volatility conditions?
2.  **Direction:** Is the probability of an upward or downward move
    increasing?
3.  **Timing:** Is there a favourable entry or exit opportunity?
4.  **Confirmation:** Do volume, derivatives, order flow, and market
    fundamentals support the signal?
5.  **Risk:** Is the expected return worth the risk of entering the
    trade?

These questions require different data. RSI alone cannot answer all
five.

The recommended design is a **multi-layer Bitcoin decision engine**
combining technical analysis, market structure, derivatives, on-chain
metrics, liquidity, macroeconomic conditions, and statistical
probability models.

The system should not give every indicator an equal vote. It should
understand what each indicator measures, whether its information
overlaps with another feature, and in which market conditions it has
predictive value.

------------------------------------------------------------------------

# 1. November 2026 market snapshot and interpretation

The research discussion used an approximate market snapshot around
21--22 November 2026:

-   BTC reference price around **\$60,216** on 21 November.
-   Approximately **52.4% below** a reported all-time high near
    \$126,198.
-   Reported intraday low around \$55,252 on 20 November.
-   Approximately \$659.6 million in 24-hour liquidations.
-   Fear & Greed reading around 11/100.
-   Reported open interest around \$38.81 billion.
-   Negative funding rates.
-   Futures volume around \$95.33 billion versus spot volume around
    \$10.72 billion.
-   US spot Bitcoin ETF outflows reported at approximately \$3.5 billion
    through 19 November.
-   Short-term holder SOPR reported around 0.947.

These are historical, approximate figures from the research snapshot and
should be independently verified before being used in a live model.

### Initial market interpretation

The initial classification was **bearish primary trend with a possible
short-term relief rally**.

A sharp recovery following liquidations does not automatically mean a
new bull market has started. A credible trend reversal would require
several forms of confirmation:

-   Higher highs and higher lows on the daily chart.
-   Recovery of important moving averages.
-   Sustained positive spot volume.
-   Improving spot demand and spot CVD.
-   Healthier derivatives positioning.
-   Confirmation on higher timeframes.
-   Stabilisation in on-chain and institutional flow data.

### Five recovery conditions to monitor

1.  **Price recovery:** Establish higher lows and higher highs on the
    daily timeframe and recover important moving averages.
2.  **Spot buying:** Spot cumulative volume delta should improve; actual
    spot demand is more convincing than short covering alone.
3.  **Derivatives stabilisation:** Open interest should stabilise and
    recover without funding becoming excessively positive.
4.  **Institutional demand:** ETF outflows should stabilise and ideally
    transition into sustained inflows.
5.  **On-chain stabilisation:** SOPR should recover towards 1, while
    exchange inflows and long-term holder distribution should not
    indicate accelerating selling pressure.

No single condition proves a bottom.

------------------------------------------------------------------------

# 2. Technical analysis indicators

Technical indicators are foundational, but hundreds of public indicators
exist and many are variations of the same calculation. MACD is derived
from moving averages; RSI, Stochastic RSI, CCI, and Williams %R all
describe related forms of momentum. Using all of them does not create
independent confirmation.

## 2.1 Trend indicators

### 1. Moving averages: SMA and EMA

**Suggested parameters:** SMA 20, 50, 200; EMA 20 and 50.

Purpose: smooth price movements and identify the underlying trend.

Typical interpretation:

-   Price above the 200 SMA: generally positive long-term trend.
-   Price below the 200 SMA: generally negative long-term trend.
-   50 SMA above 200 SMA: positive longer-term alignment.
-   50 SMA below 200 SMA: negative longer-term alignment.
-   Pullbacks towards EMA 20 or EMA 50 during an established trend may
    offer potential entry areas.

A moving-average crossover is lagging. Do not buy simply because one
average crosses another.

### 2. Average Directional Index (ADX)

Purpose: measure trend strength, not trend direction.

Indicative interpretation:

  ADX        Typical interpretation
  ---------- ------------------------
  Below 20   Weak or ranging market
  20--25     Developing trend
  Above 25   Established trend
  Above 40   Strong trend

These are starting thresholds, not universal boundaries.

Use ADX to help select the strategy regime: strong trends favour
trend-following approaches; weak trends may favour mean reversion.

### 3. Donchian Channels

Purpose: identify the highest and lowest prices over a specified number
of candles.

-   Break above the previous 20-candle high: potential bullish breakout.
-   Break below the previous 20-candle low: potential bearish breakout.
-   55-period channels can identify longer-term breakouts.

This is a particularly useful, transparent feature for a rules-based
system.

### 4. Ichimoku Cloud

Purpose: combine trend, momentum, and support/resistance information.

-   Price above cloud: positive trend context.
-   Price below cloud: negative trend context.
-   Tenkan crossing above Kijun: positive momentum signal.
-   Cloud thickness provides context about potential support and
    resistance.

Useful for visual analysis, but much of its information overlaps with
other trend indicators. It is optional for the first version.

**Recommended core trend features:** SMA 50, SMA 200, EMA 20, ADX,
Donchian Channels, and algorithmic market structure.

## 2.2 Momentum indicators

### 5. Relative Strength Index (RSI)

**Standard setting:** RSI 14.

Purpose: measure the speed and magnitude of recent price movements.

Traditional interpretation:

  RSI        Typical interpretation
  ---------- ------------------------
  Below 30   Oversold
  30--45     Weak momentum
  45--55     Neutral
  55--70     Positive momentum
  Above 70   Overbought

Bitcoin can remain above 70 in a strong bull trend or below 30 in a
prolonged bear trend.

More useful observations include:

-   RSI recovering above 30 after extreme selling.
-   RSI holding around 40--50 during a bullish pullback.
-   RSI failing around 50--60 during a bearish rally.
-   Bullish or bearish divergence between RSI and price.

Calculate RSI across multiple timeframes.

### 6. MACD

**Standard settings:** 12, 26, 9.

Purpose: measure moving-average convergence/divergence and momentum.

-   MACD crossing above signal line: improving bullish momentum.
-   MACD crossing below signal line: weakening momentum.
-   Histogram increasing above zero: strengthening bullish momentum.
-   Histogram decreasing below zero: strengthening bearish momentum.
-   Divergence can indicate weakening momentum before a potential
    reversal.

Use MACD as momentum confirmation rather than an independent vote
because it overlaps with moving averages.

### 7. Rate of Change (ROC)

Purpose: measure percentage price change over a chosen period.

-   Positive ROC: price is above its value N periods ago.
-   Negative ROC: price is below its previous value.
-   Increasing positive ROC: accelerating upward momentum.
-   Falling ROC: weakening momentum.

Potential periods to test: 6, 12, 24, and 72 hourly candles.

## 2.3 Volatility indicators

### 8. Bollinger Bands

**Standard settings:** 20-period SMA, 2 standard deviations.

-   Price touching upper band: strong upward movement or potential
    overextension.
-   Price touching lower band: strong downward movement or potential
    overextension.
-   Narrow bands: volatility contraction.
-   Expanding bands: volatility expansion.

A Bollinger squeeze can precede a large movement, but does not predict
direction. Require price breakout and volume confirmation.

### 9. Average True Range (ATR)

**Standard setting:** ATR 14.

Purpose: measure average trading range, including gaps in traditional
markets.

Applications:

-   Detect increasing volatility.
-   Calculate adaptive stop-loss distances.
-   Calculate position sizes.
-   Avoid using the same percentage stop in every market environment.

Illustration: if ATR is \$1,000 and a strategy uses a 2 × ATR stop, the
initial stop distance is \$2,000. This is an example, not a universal
stop recommendation.

### 10. Historical / realised volatility

Calculate standard deviation of logarithmic returns over, for example:

-   24 hours.
-   7 days.
-   30 days.
-   90 days.

Use it to identify unusual volatility and estimate future return
distributions. GARCH and HAR volatility models are possible later
additions. Research has found HAR models using realised variance useful
for short-term volatility forecasting in Bitcoin.

## 2.4 Volume indicators

### 11. Volume Profile

Purpose: show how much trading volume occurred at different price
levels.

Key components:

-   **POC:** Point of Control, the price with the highest traded volume.
-   **VAH:** Value Area High.
-   **VAL:** Value Area Low.
-   **HVN:** High-volume node.
-   **LVN:** Low-volume node.

Use these to identify potential support, resistance, and breakout zones.
High-volume areas often represent prices where substantial trading took
place; lower-volume areas may be crossed more quickly.

### 12. Volume Weighted Average Price (VWAP)

Purpose: calculate average price weighted by traded volume.

-   Price above VWAP: buyers generally control price relative to that
    VWAP period.
-   Price below VWAP: sellers generally control price.
-   Reclaiming VWAP after a sell-off: potential recovery signal.
-   Losing VWAP during an uptrend: potential weakening.

Anchored VWAP can be anchored to a major swing high/low, the beginning
of a major sell-off, or a major breakout.

### 13. On Balance Volume (OBV)

Purpose: accumulate volume based on whether a candle closes higher or
lower.

-   Price and OBV rising: volume confirms the trend.
-   Price rising but OBV declining: possible bearish divergence.
-   Price falling but OBV rising: possible accumulation.

Also calculate **Relative Volume**, such as current volume divided by
average volume for the equivalent period.

## 2.5 Market structure and price action

Important features:

-   Higher highs (HH).
-   Higher lows (HL).
-   Lower highs (LH).
-   Lower lows (LL).
-   Break of Structure (BOS).
-   Change of Character (CHoCH).
-   Support and resistance.
-   Failed breakouts.
-   Liquidity sweeps.

Example bullish structure:

1.  Bitcoin makes a higher low.
2.  Price breaks the previous high.
3.  Trading volume increases.
4.  Price pulls back without breaking the prior higher low.
5.  Buyers return and price begins another upward move.

Build a swing-high/swing-low detection algorithm and expose its outputs
to the strategy engine.

## 2.6 Other technical indicators to evaluate later

  Indicator               Purpose                              Priority
  ----------------------- ------------------------------------ ----------
  SuperTrend              Trend direction and trailing stops   Medium
  Keltner Channels        Volatility and breakout detection    Medium
  Stochastic RSI          Momentum timing                      Low
  Chaikin Money Flow      Buying/selling pressure              Medium
  Fibonacci retracement   Potential retracement levels         Low
  Parabolic SAR           Trend and trailing exits             Low
  Choppiness Index        Identify ranging markets             Medium
  Money Flow Index        Volume-weighted momentum             Medium

Do not implement all of these immediately. Add an indicator only if it
provides demonstrably new information and improves out-of-sample
results.

------------------------------------------------------------------------

# 3. Derivatives market analysis

Bitcoin futures and perpetual futures represent a substantial part of
market activity. Derivatives reveal positioning and leverage that
ordinary spot charts do not show.

## 3.1 Funding rates

Funding is a periodic payment between long and short perpetual futures
traders.

-   Positive funding: longs typically pay shorts.
-   Negative funding: shorts typically pay longs.

Interpretation examples:

  -----------------------------------------------------------------------
  Situation                           Potential interpretation
  ----------------------------------- -----------------------------------
  Price rising, funding positive      Bullish positioning

  Price rising, funding extremely     Long crowding risk
  positive                            

  Price falling, funding negative     Bearish positioning

  Price stabilising, funding          Potential short-squeeze conditions
  extremely negative                  
  -----------------------------------------------------------------------

Track:

-   Current funding rate.
-   7-day average.
-   30-day average.
-   Historical percentile.
-   Funding differences between exchanges.

Use funding as a positioning/risk indicator, not a standalone
directional signal.

## 3.2 Open Interest (OI)

Open interest measures outstanding derivative contracts.

  Bitcoin price   Open interest   Simplified interpretation
  --------------- --------------- -------------------------------------------------
  Rising          Rising          New positions entering during upward movement
  Rising          Falling         Possible short covering
  Falling         Rising          New positions entering during downward movement
  Falling         Falling         Possible long liquidation or position reduction

This is simplified: every futures contract has both a long and a short
side, so OI alone does not identify the direction of every position.

Monitor:

-   Total BTC futures OI.
-   OI by exchange.
-   OI denominated in BTC, not only USD.
-   OI percentage change.
-   OI relative to market capitalisation.
-   OI relative to spot volume.

USD-denominated OI can fall because BTC price falls even when the number
of outstanding BTC contracts changes less.

## 3.3 Liquidation data and heatmaps

Liquidations occur when leveraged positions are forcibly closed.
Heatmaps estimate where leveraged positions may be vulnerable.

Example: if a large estimated short-liquidation concentration exists
above \$63,000 while BTC trades at \$60,000, an upward move could
trigger short covering and accelerate the move.

Limitations:

-   Heatmaps are estimates, not exact maps of every liquidation price.
-   Levels change as positions open, close, or hedge.
-   Estimated liquidation zones must be distinguished from actual
    liquidation events.

## 3.4 Long/short ratios

Monitor:

-   General account long/short ratio.
-   Top-trader long/short ratio.

Crowded longs can be vulnerable to a downside squeeze; crowded shorts
can be vulnerable to an upside squeeze. Crowding can persist, so ratios
are positioning indicators rather than timing signals.

## 3.5 Futures basis

The basis is the difference between futures and spot price:

`Basis = Futures Price - Spot Price`

-   Positive basis: futures trade above spot.
-   Negative basis: futures trade below spot.

Annualised basis helps measure the futures premium.

A strong positive basis may indicate bullish demand or leveraged carry
trades. A negative basis may indicate bearish stress or demand for
downside protection.

CME BasisWatch is a useful reference tool.

## 3.6 Cumulative Volume Delta (CVD)

CVD estimates the difference between aggressive buying and aggressive
selling volume:

`CVD = cumulative(Aggressive Buy Volume - Aggressive Sell Volume)`

Interpretation:

-   Price rising and CVD rising: buyers are aggressively participating.
-   Price rising and CVD declining: potential weakening demand.
-   Price falling and CVD rising: possible buyer absorption.
-   Price falling and CVD declining: aggressive selling.

Calculate two separate versions:

1.  Spot CVD.
2.  Futures/perpetual CVD.

Spot buying and leveraged futures buying are not equivalent. A
particularly interesting pattern is falling price and negative futures
CVD while spot CVD starts recovering. This may indicate futures selling
being absorbed by spot buyers; it is not proof of a bottom.

------------------------------------------------------------------------

# 4. Bitcoin options market

Options provide information about expected volatility and demand for
protection.

  -----------------------------------------------------------------------
  Indicator               What it measures        Use
  ----------------------- ----------------------- -----------------------
  Implied Volatility (IV) Market-priced expected  Identify anticipated
                          volatility              turbulence

  Realised Volatility     Historical actual       Compare expectations
  (RV)                    volatility              with actual movement

  IV/RV spread            Difference between      Assess relative option
                          expected and realised   pricing
                          volatility              

  Put/Call Ratio          Put activity relative   Measure downside versus
                          to call activity        upside positioning

  25-delta skew           Relative IV of puts and Identify demand for
                          calls                   downside protection

  Options Open Interest   Outstanding options     Identify positioning
                          positions               concentrations

  Gamma Exposure (GEX)    Estimated dealer gamma  Understand potential
                          positioning             hedging-related price
                                                  behaviour
  -----------------------------------------------------------------------

IV is not a directional forecast. It reflects the market price of
expected volatility.

Options data can help distinguish a normal breakout from one occurring
ahead of a major volatility event, or identify unusually strong demand
for downside protection or upside calls.

Potential source: Deribit, including its options and volatility data.
Options analytics are a second-stage addition, not a dependency for the
first working strategy.

------------------------------------------------------------------------

# 5. On-chain analytics

Bitcoin's public blockchain allows analysis of coin movements and
estimated holder behaviour. It does not reveal the real-world identity
or intention of every wallet owner.

## 5.1 Exchange inflows and outflows

-   Increasing inflows: more BTC arriving at exchanges; some may be
    intended for sale.
-   Increasing outflows: more BTC leaving exchanges; may indicate
    self-custody or longer-term holding.

Interpret cautiously. Internal exchange transfers, custody changes,
collateral movements, and OTC activity can distort the signal. Do not
translate every inflow into a predicted sale.

## 5.2 Exchange reserves

Potential combinations:

-   Falling reserves + rising price: potentially constructive.
-   Rising reserves + falling price: potentially bearish.
-   Rising reserves but stable price: supply may be absorbed.
-   Falling reserves but falling price: selling may be coming from other
    sources.

CryptoQuant provides exchange-flow and reserve metrics.

## 5.3 MVRV

MVRV is Market Value to Realized Value:

`MVRV = Market Capitalisation / Realized Capitalisation`

It compares market value with an estimate of aggregate coin cost basis
based on last on-chain movement.

-   MVRV above 1: aggregate unrealised gains.
-   MVRV below 1: aggregate unrealised losses.
-   Elevated historical MVRV: possible market overheating.
-   Depressed historical MVRV: possible undervaluation or capitulation.

Use historical percentiles and MVRV Z-score rather than one universal
threshold. MVRV is more useful for market-cycle context than precise
hourly entries.

## 5.4 SOPR

Spent Output Profit Ratio estimates whether coins are moving at a profit
or loss relative to their previous on-chain movement.

  SOPR       Interpretation
  ---------- ---------------------------------
  Above 1    Coins moved at aggregate profit
  Around 1   Approximate break-even
  Below 1    Coins moved at aggregate loss

Monitor:

-   STH-SOPR: Short-Term Holder SOPR.
-   LTH-SOPR: Long-Term Holder SOPR.

During a bull trend, short-term profit-taking may be healthy. During a
bear trend, STH-SOPR repeatedly failing to recover above 1 can indicate
continued loss realisation.

## 5.5 NUPL

Net Unrealised Profit/Loss measures the balance between unrealised gains
and losses across the market. Use alongside MVRV because the measures
are related, not independent.

## 5.6 Long-term and short-term holder supply

Monitor:

-   Long-term holder supply.
-   Short-term holder supply.
-   Coins held for more than 155 days.
-   Older coins becoming active.
-   Supply held at a profit or loss.

Older coins moving to exchanges at profitable price levels may indicate
distribution. A decline in long-term holder supply alone is not a sell
signal.

## 5.7 Miner activity

Useful metrics:

-   Miner reserves.
-   Miner outflows.
-   Miner-to-exchange flows.
-   Hash rate.
-   Mining difficulty.
-   Miner revenue.
-   Puell Multiple.

Miner-to-exchange flow increases may indicate potential selling. Hash
rate and difficulty are more useful for network health and longer-term
supply economics than hourly entries.

## 5.8 Stablecoin reserves

Monitor USDT, USDC, and other major stablecoins held on exchanges.

Potential combinations:

-   Rising stablecoin reserves + positive BTC spot CVD: potentially
    stronger demand.
-   Rising BTC exchange reserves + declining stablecoin reserves:
    potentially weaker buying capacity.
-   Large stablecoin inflows without BTC buying: available capital, not
    confirmed demand.

Stablecoin supply and exchange reserves are not equivalent to actual buy
orders.

------------------------------------------------------------------------

# 6. External market conditions and macroeconomics

Bitcoin does not trade in isolation. Institutional investors and other
participants make decisions across multiple asset classes. Build a macro
monitoring module.

## 6.1 US Dollar Index (DXY)

The DXY measures the dollar against a basket of major currencies.

A stronger dollar has often coincided with pressure on Bitcoin; a weaker
dollar can support risk assets. This relationship is not stable.

Measure:

-   Daily DXY percentage change.
-   7-day and 30-day momentum.
-   20-day and 50-day averages.
-   Rolling BTC/DXY correlation.

Measure the current relationship rather than assuming a permanent
inverse correlation.

## 6.2 US Treasury yields and real interest rates

Monitor:

-   US 10-year Treasury yield.
-   US 2-year Treasury yield.
-   US 10-year real yield.
-   Yield curve (10-year minus 2-year).

General interpretation:

  -----------------------------------------------------------------------
  Development                         Potential BTC impact
  ----------------------------------- -----------------------------------
  Real yields rising                  Pressure on risk assets

  Real yields falling                 Potentially supportive

  Dollar and real yields rising       More challenging environment
  together                            

  Dollar and real yields falling      Potentially supportive
  together                            
  -----------------------------------------------------------------------

These are relationships to test, not automatic signals.

## 6.3 Federal Reserve monetary policy

Monitor:

-   Actual federal funds rate.
-   Market expectations for future rates.
-   FOMC announcements.
-   Inflation reports.
-   Employment reports.
-   Federal Reserve balance sheet.

Markets often respond to the difference between expectations and the
actual announcement, not the announcement alone.

The research snapshot referenced an October 28, 2026 FOMC target range
of 3.75--4.00%. This is a historical figure and must be verified before
reuse.

## 6.4 Stock-market correlation

Monitor:

-   Nasdaq 100.
-   S&P 500.
-   VIX.
-   BTC/Nasdaq correlation.
-   BTC/S&P 500 correlation.

Calculate rolling 30-day and 90-day correlations. If BTC has a high
positive correlation with Nasdaq, a sharp Nasdaq sell-off may increase
estimated BTC downside risk. Correlations can weaken or reverse.

## 6.5 Liquidity indicators

Potential data:

-   Federal Reserve balance sheet.
-   US Treasury General Account (TGA).
-   Reverse Repo Facility (RRP).
-   Bank reserves.
-   Financial conditions indexes.
-   Stablecoin market capitalisation.

Liquidity is a macro background variable, not a direct forecast of
Bitcoin purchases.

## 6.6 Economic event calendar

Monitor:

-   US CPI and PCE inflation.
-   Federal Reserve interest-rate decisions.
-   US employment and Nonfarm Payrolls.
-   US GDP reports.
-   Treasury auctions.
-   Major regulatory announcements.

Do not necessarily block all trading around every announcement. Increase
risk awareness as major events approach and account for event-related
volatility.

------------------------------------------------------------------------

# 7. Institutional flows, sentiment, and news

## 7.1 Bitcoin ETF flows

Monitor:

-   Daily net inflows/outflows.
-   5-day rolling flows.
-   20-day rolling flows.
-   Cumulative flows.
-   ETF holdings in BTC.
-   Flows as a percentage of market capitalisation.
-   Flows converted to equivalent BTC supply.

ETF flows are a useful measure of demand from a major group of
traditional-market investors. They overlap conceptually with spot demand
and should not be counted as wholly independent evidence.

## 7.2 Fear & Greed Index

Typical classifications:

  Score     Sentiment
  --------- ---------------
  0--24     Extreme fear
  25--44    Fear
  45--54    Neutral
  55--74    Greed
  75--100   Extreme greed

Providers use different methodologies. Extreme fear may identify stress;
extreme greed may identify overheating. Neither is a standalone buy/sell
signal.

Test whether buying after extreme fear is profitable only when combined
with a positive price-structure reversal.

## 7.3 News and event analysis

Monitor verified sources such as Reuters, Bloomberg, Financial Times,
Federal Reserve publications, SEC/CFTC announcements, major exchange
announcements, and Bitcoin network developments.

An AI news module should output structured information:

-   What happened?
-   When did it happen?
-   Is it confirmed?
-   Is it new or a repetition?
-   Which market participants are affected?
-   What is the likely impact horizon?
-   Is the event already reflected in price?

The AI should not simply say "bullish, buy Bitcoin." Structured event
information should be passed to the numerical decision engine. Give
unverified rumours and social-media speculation negative confidence.

------------------------------------------------------------------------

# 8. Market liquidity and order-book analysis

## 8.1 Order-book imbalance

An order book contains outstanding buy and sell orders.

`Imbalance = (Bid Volume - Ask Volume) / (Bid Volume + Ask Volume)`

The result ranges from -1 to +1.

-   Positive: more displayed bid liquidity.
-   Negative: more displayed ask liquidity.
-   Near zero: relatively balanced displayed liquidity.

Calculate at several price distances, such as 0.1%, 0.25%, 0.5%, and 1%.

Displayed orders can be cancelled, moved, or manipulated. Combine
order-book imbalance with executed transactions.

## 8.2 Bid/ask spread

A widening spread can indicate reduced liquidity, uncertainty, increased
execution costs, higher slippage, or greater risk. It is an important
input into deciding whether a trade should be executed.

## 8.3 Absorption

Absorption occurs when aggressive buying or selling is met by enough
opposing liquidity to prevent substantial price movement.

Example: significant aggressive selling occurs, but price refuses to
move lower. Large buyers may be absorbing supply.

Investigate using:

-   Executed volume.
-   CVD.
-   Price change.
-   Order-book replenishment.
-   Volume at individual price levels.

## 8.4 Liquidity sweep

A liquidity sweep occurs when price moves beyond an important high/low,
triggers stops or liquidations, and then reverses.

Example:

1.  Price approaches a previous swing low.
2.  Price briefly falls below it.
3.  Selling volume increases.
4.  Price quickly recovers above the previous low.
5.  CVD begins improving.

This may indicate a failed breakdown. It is a useful potential reversal
feature, not proof of a reversal.

------------------------------------------------------------------------

# 9. Data providers and tools

## 9.1 Core providers

### CoinGlass

Best for:

-   Open interest.
-   Funding rates.
-   Liquidations.
-   Long/short ratios.
-   Spot and futures CVD.
-   Order-book analytics.
-   ETF flows.
-   Options data.

Useful because it aggregates data from multiple exchanges.

-   Website: https://www.coinglass.com/
-   API documentation: https://docs.coinglass.com/

### Glassnode

Best for:

-   MVRV.
-   SOPR.
-   NUPL.
-   Realized price.
-   Long-term holder behaviour.
-   Supply distribution.
-   Network valuation metrics.

Useful for longer-term market conditions.

-   Website: https://glassnode.com/
-   API documentation: https://docs.glassnode.com/

### CryptoQuant

Best for:

-   Exchange inflows/outflows.

-   Exchange reserves.

-   Miner behaviour.

-   Whale transactions.

-   Stablecoin reserves.

-   Derivatives positioning.

-   On-chain market indicators.

-   Website: https://cryptoquant.com/

-   User guide: https://userguide.cryptoquant.com/

### Deribit

Best for:

-   Options market data.

-   Implied volatility.

-   Options open interest.

-   Put/call skew.

-   Options expiry structure.

-   Website: https://www.deribit.com/

-   API documentation: https://docs.deribit.com/

### TradingView

Best for:

-   Visual chart analysis.

-   Technical indicators.

-   Custom Pine Script experiments.

-   Strategy visualisation.

-   Manual comparison with system predictions.

-   Website: https://www.tradingview.com/

### CME Group

Best for:

-   Regulated Bitcoin futures.

-   Futures basis.

-   Institutional futures activity.

-   Historical futures data.

-   Reference pricing.

-   Cryptocurrency markets:
    https://www.cmegroup.com/markets/cryptocurrencies.html

## 9.2 Additional sources and tools

  Tool            Purpose
  --------------- --------------------------------------------------
  FRED            Economic data, interest rates, yields, liquidity
  CFTC            Weekly institutional futures positioning
  Mempool.space   Bitcoin network activity, fees, mempool, mining
  CCXT            Unified cryptocurrency exchange API library
  Reuters         Verified market-moving news

Links:

-   FRED: https://fred.stlouisfed.org/
-   CFTC Commitment of Traders:
    https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
-   Mempool.space: https://mempool.space/
-   CCXT GitHub: https://github.com/ccxt/ccxt
-   Reuters markets: https://www.reuters.com/markets/

CFTC positioning data is weekly and delayed, so it is not suitable for
precise intraday timing.

------------------------------------------------------------------------

# 10. Trading strategies to develop

Do not build one enormous strategy that attempts to predict every
Bitcoin movement. Develop specialised strategies for different market
conditions. A regime classifier should decide which strategies are
eligible.

## Strategy A: Trend following

**Highest development priority.**

Objective: capture substantial movements during established bull and
bear trends.

Features:

-   SMA 50.
-   SMA 200.
-   EMA 20.
-   ADX.
-   Donchian Channels.
-   Relative Volume.
-   ATR.

Example bullish conditions:

1.  Daily price above 200 SMA.
2.  50 SMA above 200 SMA.
3.  ADX indicates sufficient trend strength.
4.  Price breaks above previous 20-period high.
5.  Trading volume exceeds normal levels.
6.  Higher timeframe confirms direction.

Potential entry: after a confirmed breakout.

Potential exit:

-   ATR-based trailing stop.
-   Break below a trailing 10-period low.
-   Trend filter invalidation.

Develop the bearish equivalent separately.

Why: rules-based, relatively simple to test, and capable of capturing
large movements without predicting exact tops and bottoms.

## Strategy B: Mean reversion

Objective: profit from temporary price deviations during sideways
markets.

Features:

-   Bollinger Bands.
-   RSI.
-   ADX.
-   VWAP.
-   ATR.
-   Volume Profile.

Example bullish conditions:

1.  ADX indicates a ranging market.
2.  Price moves substantially below its recent average.
3.  RSI enters an oversold region.
4.  Price reaches established support or a high-volume area.
5.  Selling momentum weakens.
6.  Price reclaims a relevant level, such as VWAP or the lower Bollinger
    Band.

Potential target: middle Bollinger Band or another predefined mean
level.

Invalidation: price continues breaking through support with accelerating
selling.

Do not use blindly during a strong downtrend. Oversold markets can
become more oversold.

## Strategy C: Momentum continuation

Objective: enter an established trend after a temporary pullback.

Features:

-   EMA 20.
-   EMA 50.
-   RSI.
-   MACD.
-   CVD.
-   Relative Volume.
-   Market structure.

Example:

1.  Daily trend is bullish.
2.  Bitcoin pulls back towards EMA 20 or EMA 50.
3.  RSI returns to a healthier momentum zone.
4.  Price creates a higher low.
5.  CVD starts improving.
6.  Price breaks the previous short-term swing high.

The bearish version looks for a rally into resistance followed by
renewed selling.

## Strategy D: Liquidation reversal / short squeeze

Objective: identify extreme forced selling/buying and potential
reversals.

Features:

-   Liquidation volume.
-   Open interest.
-   Funding rates.
-   CVD.
-   ATR.
-   Order-book imbalance.
-   VWAP.
-   Support/resistance.

Example bullish scenario:

1.  Rapid downward movement.
2.  Long liquidations spike.
3.  Open interest drops sharply.
4.  Funding becomes extremely negative.
5.  Spot selling slows.
6.  CVD improves.
7.  Price reclaims an important level.

Falling prices and negative funding alone do not justify buying. Require
evidence that selling pressure is being absorbed.

## Strategy E: Liquidity sweep reversal

Objective: identify false breakouts and failed breakdowns.

Features:

-   Swing highs and lows.
-   Previous-day highs/lows.
-   Volume Profile.
-   CVD.
-   Order-book depth.
-   ATR.
-   VWAP.

Example: price falls below major support and triggers stops, then
quickly returns above support. If aggressive selling occurred but price
recovers and order flow improves, the system can identify a possible
failed breakdown.

## Strategy F: Funding and basis strategies

Advanced/later stage.

A possible market-neutral carry structure:

-   Buy BTC spot.
-   Take an appropriately sized short perpetual futures position.
-   Receive funding when structure and funding make it attractive.

This resembles a cash-and-carry approach. It is not risk-free: funding
can reverse, exchange risks exist, and collateral or execution failures
can cause losses. Keep it separate from directional strategies.

------------------------------------------------------------------------

# 11. Decision-engine architecture

Do not create a system where every indicator contributes one vote to an
overall bullish/bearish score. Many features overlap:

-   RSI and MACD both contain momentum information.
-   Moving averages and SuperTrend both depend heavily on trend.
-   Bollinger width and ATR both describe volatility.
-   Funding and long/short ratios both describe aspects of derivatives
    positioning.

Use a hierarchical process.

## Proposed pipeline

1.  **Market data collection:** prices, volume, futures, options,
    on-chain, macro, news.
2.  **Feature engineering:** indicators, price structure, statistical
    features, data-quality checks.
3.  **Market regime classification:** bull, bear, sideways, high
    volatility, recovery.
4.  **Specialised strategy engines:** trend following, mean reversion,
    momentum, reversal/liquidity.
5.  **Signal evaluation and confirmation:** probability, expected
    return, confirmation, conflicting evidence.
6.  **Risk management:** position size, stop loss, maximum exposure,
    volatility limits.
7.  **Trading decision:** BUY / SELL / HOLD / NO TRADE, with
    explanation, invalidation level, and expected risk/reward.

## 11.1 Market regime classification

  -----------------------------------------------------------------------
  Regime                  Characteristics         Preferred strategy
  ----------------------- ----------------------- -----------------------
  Bull trend              Higher highs, higher    Trend following
                          lows, positive trend    
                          structure               

  Bear trend              Lower highs, lower      Short trend following /
                          lows, negative trend    defensive
                          structure               

  Range                   Weak ADX, repeated      Mean reversion
                          reversals               

  High volatility         Extreme ATR and rapidly Reduced risk,
                          changing conditions     specialised setups

  Recovery                Price and order flow    Momentum / reversal
                          recovering after        
                          sell-off                
  -----------------------------------------------------------------------

The same signal can mean different things in different regimes. RSI at
25 in a sideways market may create a mean-reversion opportunity; RSI at
25 during a strong bear trend may simply indicate persistent selling
pressure.

## 11.2 Multi-timeframe analysis

Recommended primary timeframes:

  Timeframe   Purpose
  ----------- ------------------------------
  Daily       Primary market trend
  4-hour      Trading setup identification
  1-hour      Entry and exit timing

Potential later addition: 15-minute data for execution.

Daily determines whether to favour long or short opportunities. 4-hour
identifies setups. 1-hour provides timing.

A short-term bullish entry against a clearly bearish daily trend should
generally receive lower priority unless a dedicated countertrend
strategy identifies an exceptional setup.

------------------------------------------------------------------------

# 12. Signal scoring and predictive probability

Move beyond statements such as "RSI is 28, therefore buy Bitcoin."
Estimate the probability of specific future outcomes.

Examples:

-   Probability BTC rises at least 1% in the next 4 hours.
-   Probability BTC rises at least 2% in the next 24 hours.
-   Probability BTC falls at least 2% in the next 24 hours.
-   Probability volatility increases over the next 12 hours.
-   Probability a breakout succeeds rather than reverses.

These are different prediction problems and should have separate models
or outputs.

## 12.1 Feature groups

  Group                 Example features
  --------------------- -------------------------------------------
  Trend and structure   Moving averages, ADX, Donchian, HH/HL
  Momentum              RSI, MACD, ROC
  Volatility            ATR, Bollinger width, realised volatility
  Participation         Volume, VWAP, spot CVD
  Derivatives           Funding, OI, basis, liquidations
  External factors      ETF flows, on-chain, macro, sentiment

The model should understand interactions. Example:

-   Trend: bearish.
-   Short-term momentum: improving.
-   Volatility: extremely high.
-   Spot participation: improving.
-   Futures positioning: crowded short.
-   ETF flows: negative.

This could represent a short-term recovery opportunity inside a larger
bearish market.

## 12.2 Avoid false confidence

An output might show a probability of a positive 24-hour return and a
breakdown of supporting and conflicting evidence. Such a probability is
meaningful only after testing and calibration. It must not be generated
by an LLM simply because the market looks bullish.

The system should report uncertainty and conflicting evidence.

------------------------------------------------------------------------

# 13. Academic research and evidence

Research does not support assuming that any technical indicator will
remain profitable. Findings are mixed, and out-of-sample performance is
a major concern.

## 13.1 Technical trading rules can work, but results are inconsistent

A 2020 study by Gerritsen, Bouri, Ramezanifar and Roubaud examined seven
families of Bitcoin trend-following rules using historical daily prices.
The researchers found forecasting power in trading-range breakout rules
and outperformance versus buy-and-hold on a risk-adjusted basis in their
sample.

This supports investigating Donchian breakouts, previous-period high/low
breakouts, moving-average trend filters, and momentum confirmation.

## 13.2 Out-of-sample testing can undermine apparent success

Hudson and Urquhart examined almost 15,000 technical trading rules
across cryptocurrency markets. They found historical predictability but
reported no out-of-sample predictability for Bitcoin during the
evaluated out-of-sample period.

A 2021 study by Anghel examined machine-learning and technical trading
strategies while correcting for data snooping and market frictions.
Statistically significant positive excess returns were rare after those
controls.

A strategy that explains historical Bitcoin behaviour is not necessarily
a strategy that predicts future behaviour.

## 13.3 Transaction costs matter

Research examining technical trading rules across cryptocurrencies found
that transaction costs and market conditions materially influenced
profitability.

Include:

-   Entry trading fees.
-   Exit trading fees.
-   Bid/ask spread.
-   Slippage.
-   Funding costs where applicable.
-   Market impact for larger orders.

A strategy can have reasonable directional accuracy and still lose money
if it trades too frequently.

## 13.4 Volatility forecasting is worth investigating

A 2022 study of GARCH and HAR models for Bitcoin volatility found HAR
models based on realised variance effective for short-term volatility
forecasting relative to the evaluated daily-data GARCH models.

Volatility forecasts do not necessarily predict direction, but can help
determine position size, stop width, strategy suitability, and whether
trading activity should be reduced.

------------------------------------------------------------------------

# 14. Backtesting and validation

This should be a major component of the project. Do not accept a
strategy because its historical chart looks good.

## 14.1 Test each indicator independently

Example: does RSI below 30 improve the probability of a positive return
over the next:

-   1 hour?
-   4 hours?
-   12 hours?
-   24 hours?
-   72 hours?

Does the relationship change between bull and bear markets?

Use the same process for funding, OI, volume, MVRV, and other features.

## 14.2 Test combinations

Example: RSI below 30 + positive CVD + falling OI + recovery above VWAP.

Does this produce better results than RSI below 30 alone? Does it
improve results after fees?

## 14.3 Chronological testing

An illustrative chronological split:

-   60% training.
-   20% validation.
-   20% final test.

Do not randomly shuffle time-series data.

Use walk-forward validation:

1.  Train on historical data.
2.  Validate on the next unseen period.
3.  Move forward.
4.  Retrain or recalibrate.
5.  Test the next unseen period.
6.  Repeat.

Additional safeguards:

-   Prevent look-ahead bias.
-   Prevent data leakage.
-   Account for delayed on-chain and ETF data.
-   Use point-in-time data where historical values can be revised.
-   Avoid tuning hundreds of combinations against the same test dataset.
-   Include realistic order execution and fees.
-   Where appropriate, use purged or embargoed time-series
    cross-validation to reduce leakage between overlapping prediction
    horizons.

## 14.4 Performance measurements

  Metric             What it tells us
  ------------------ ----------------------------------------
  Net return         Actual performance after costs
  Sharpe ratio       Return relative to total volatility
  Sortino ratio      Return relative to downside volatility
  Maximum drawdown   Largest peak-to-trough decline
  Calmar ratio       Return relative to maximum drawdown
  Profit factor      Gross profits divided by gross losses
  Win rate           Percentage of profitable trades
  Average trade      Average net result per trade
  Expectancy         Expected profit/loss per trade
  Turnover           How frequently capital is traded
  Exposure           Time spent in the market

Compare performance across bull, bear, sideways, high-volatility, and
low-volatility periods. A strategy that only works in one market cycle
may not be robust.

## 14.5 Risk management

Position size should be based on the distance between entry and stop:

`Position Size = Risk Budget / abs(Entry Price - Stop Price)`

Mandatory controls:

-   Maximum capital risk per position.
-   Maximum daily loss.
-   Maximum overall drawdown.
-   No unlimited averaging down.
-   No new entries when data quality is insufficient.
-   No excessive concentration in correlated positions.
-   Reduce position size during extreme volatility.
-   Explicit handling of exchange outages and execution failures.

For initial simulated testing, conservative risk budgets such as
0.25--0.5% of simulated account equity per trade can be starting
research parameters, not guaranteed safe levels or live recommendations.

------------------------------------------------------------------------

# 15. Recommended initial indicator and feature package

Do not start with 40--50 indicators. The following package is sufficient
for a serious initial decision engine.

## A. Trend and structure

-   SMA 50 and 200.
-   EMA 20.
-   ADX 14.
-   Donchian 20 and 55.
-   Automatic higher-high / higher-low detection.

## B. Momentum

-   RSI 14.
-   MACD 12/26/9.
-   ROC 12 and 24.

## C. Volatility

-   ATR 14.
-   Bollinger Bands 20, 2.
-   Historical realised volatility 7D and 30D.
-   Volatility percentile.

## D. Volume and participation

-   Relative Volume.
-   VWAP.
-   Volume Profile.
-   Spot CVD.

## E. Derivatives

-   Aggregated open interest.
-   Funding rates.
-   Futures basis.
-   Liquidation volume.
-   Futures CVD.
-   Long/short ratios.

## F. On-chain and external data

-   Exchange netflows.
-   Exchange reserves.
-   MVRV.
-   STH-SOPR.
-   LTH-SOPR.
-   ETF flows.
-   US Dollar Index.
-   US real yields.
-   Nasdaq/S&P 500 correlation.
-   Fear & Greed.

Options, advanced order-book analysis, macro liquidity, and
machine-learning volatility forecasts can be added after the baseline is
established.

------------------------------------------------------------------------

# 16. Integration into the existing AI trading system

The project already has a historical Kraken data pipeline. Retain it as
the foundation rather than replacing it. Kraken spot data alone cannot
represent the entire Bitcoin market, so expand the collection layer
while keeping sources independent.

## 16.1 Proposed data architecture

  -----------------------------------------------------------------------
  Component               Responsibility          Suggested source
  ----------------------- ----------------------- -----------------------
  Historical price data   BTC OHLCV and volume    Kraken

  Additional spot data    Cross-exchange price    CoinGlass / exchange
                          and volume              APIs

  Technical analysis      Calculate indicators    Python engine

  Derivatives             OI, funding,            CoinGlass
                          liquidation, CVD        

  On-chain                Holder and exchange     CryptoQuant
                          behaviour               

  Market valuation        MVRV, SOPR, NUPL        Glassnode

  Options                 IV, skew, options OI    Deribit

  Macroeconomics          Dollar, rates,          FRED
                          liquidity               

  Institutional activity  ETF flows               ETF data provider

  News                    Events and sentiment    Reuters and verified
                                                  sources

  Predictions             Market probabilities    Own models
  -----------------------------------------------------------------------

TradingView and CoinGlass should primarily support research, analysis,
and data acquisition. The Python system should ultimately calculate and
evaluate trading signals.

## 16.2 Data frequency

  Dataset                Suggested update frequency
  ---------------------- --------------------------------------------
  Price and trades       Continuous
  Order book             Seconds
  CVD                    1--5 minutes
  Open interest          5--15 minutes
  Funding                At exchange updates and periodic snapshots
  Technical indicators   Every completed candle
  Options                5--15 minutes or hourly
  ETF flows              Daily
  Exchange reserves      Daily
  MVRV / SOPR            Daily
  Macroeconomic data     On publication
  News                   Event-driven

Retain the publication timestamp of every external dataset. If an ETF
figure is published after the US market closes, a backtest must not make
it available earlier that day. This is a critical anti-look-ahead
safeguard.

------------------------------------------------------------------------

# 17. Development roadmap

## Phase 1 --- Technical intelligence

Build:

-   Core technical indicators.
-   Multi-timeframe analysis.
-   Market structure detection.
-   Trend and range classification.
-   Volatility classification.

**Deliverable:** Reliable technical market analysis engine.

## Phase 2 --- Derivatives intelligence

Build:

-   Open interest.
-   Funding rates.
-   Liquidations.
-   CVD.
-   Futures basis.
-   Long/short positioning.

**Deliverable:** Engine that understands positioning and leveraged
market activity.

## Phase 3 --- On-chain and institutional intelligence

Build:

-   Exchange netflows.
-   Exchange reserves.
-   MVRV and SOPR.
-   Miner and whale activity.
-   ETF flows.
-   Stablecoin liquidity.

**Deliverable:** Broader understanding of Bitcoin supply and demand.

## Phase 4 --- Macro and sentiment

Build:

-   Dollar and Treasury yields.
-   Equity-market correlation.
-   Economic calendar.
-   Fear & Greed.
-   News classification.

**Deliverable:** External market-condition assessment.

## Phase 5 --- Strategy development

Implement independently:

-   Trend following.
-   Momentum continuation.
-   Mean reversion.
-   Liquidation reversal.
-   Liquidity sweep reversal.

**Deliverable:** Multiple independently testable strategy engines.

## Phase 6 --- Predictive modelling

Investigate:

-   Logistic regression.
-   Random forest.
-   Gradient boosting (LightGBM / XGBoost).
-   Volatility forecasting.
-   Market regime classification.
-   Probability calibration.

**Deliverable:** Probabilistic predictions with measurable out-of-sample
performance.

## Phase 7 --- Risk and execution

Build:

-   Position sizing.
-   Stop-loss and take-profit logic.
-   Execution-cost modelling.
-   Portfolio exposure limits.
-   Paper trading.
-   Live performance monitoring.

**Deliverable:** Complete, monitored trading system.

### Deliberately postpone

Do not initially spend development time on:

-   Hundreds of community indicators.
-   Complicated neural networks.
-   Sentiment scoring across thousands of social-media messages.
-   Options gamma modelling.
-   Complex arbitrage strategies.
-   Automatic trading on every detected signal.

These are extensions, not prerequisites.

------------------------------------------------------------------------

# 18. Three additional research directions

## A. Detecting market absorption before a reversal

Potential inputs:

-   Aggressive sell volume.
-   Spot CVD.
-   Futures CVD.
-   Order-book replenishment.
-   Price response to executed volume.
-   Liquidation volume.
-   Nearby liquidity zones.

Investigate whether selling is being absorbed rather than interpreting
high selling volume as automatically bearish. This could identify
potential recovery conditions before conventional indicators confirm a
reversal.

## B. Predicting volatility expansions

Inputs:

-   Bollinger Band width.
-   ATR percentile.
-   Realised volatility.
-   Implied volatility.
-   Trading volume.
-   Open interest.
-   Funding.
-   Economic announcements.

Outputs:

-   Low-volatility probability.
-   Normal-volatility probability.
-   High-volatility probability.

The strategy engine can then adjust. Mean reversion may suit a
low-volatility range but be unsuitable when volatility is rapidly
expanding.

## C. Detecting divergence between spot and derivatives

Situation 1:

-   Bitcoin rises.
-   Futures CVD rises.
-   Futures OI increases.
-   Spot CVD remains weak.

Possible interpretation: movement is driven largely by leveraged
positioning rather than strong spot demand.

Situation 2:

-   Bitcoin falls.
-   Futures selling increases.
-   Spot CVD improves.
-   Price refuses to make new lows.

Possible interpretation: buyers are absorbing selling.

Test these patterns independently and then test whether they add
predictive power to existing strategy signals.

------------------------------------------------------------------------

# 19. Final priorities

1.  **Technical and market structure --- essential.** Build indicators,
    multi-timeframe trend engine, and market regime classifier first.
2.  **Derivatives and order flow --- essential.** Add OI, funding,
    liquidation data, and spot/futures CVD.
3.  **On-chain and institutional flows --- high priority.** Add exchange
    flows, SOPR, MVRV, and ETF demand.
4.  **Predictive and volatility models --- high priority.** Establish
    statistical relationships and train models only after the data
    pipeline is reliable.
5.  **Macroeconomics and news --- additional layer.** Introduce external
    conditions and event-risk analysis.
6.  **Options analytics --- later stage.** Add implied volatility, skew,
    and options positioning once the initial system performs reliably.

### Market interpretation from the November 22, 2026 research snapshot

  Decision component              Assessment
  ------------------------------- -----------------------
  Primary trend                   Bearish
  Short-term price movement       Recovery attempt
  Institutional ETF flows         Bearish
  Derivatives positioning         Extreme stress
  On-chain holder profitability   Under pressure
  Macro environment               Challenging
  Reversal confirmation           Insufficient evidence

The most interesting opportunity to investigate is whether the
liquidation-driven sell-off is transitioning into genuine spot
accumulation. That distinction is exactly what the trading system should
attempt to identify.

------------------------------------------------------------------------

# 20. Research references and further reading

The research discussion identified the following papers and technical
resources. Verify bibliographic details, publication dates, and current
documentation before relying on them in implementation.

## Academic research

1.  Gerritsen, Bouri, Ramezanifar and Roubaud (2020), research on the
    profitability of technical trading rules in the Bitcoin market ---
    trend-following and breakout strategies.
2.  Hudson and Urquhart (2021), research on technical trading and
    cryptocurrencies --- large-scale technical strategy evaluation and
    out-of-sample limitations.
3.  Anghel (2021), research on trading-rule performance, machine
    learning, data snooping, and market frictions.
4.  Research on technical analysis in cryptocurrency markets (2022) ---
    transaction costs and market bubbles.
5.  Research on forecasting Bitcoin volatility (2022) --- GARCH and HAR
    volatility forecasting.
6.  Research on price discovery in Bitcoin spot and futures markets
    (2025).

## Technical documentation and data sources

-   CoinGlass API: https://docs.coinglass.com/
-   Glassnode API: https://docs.glassnode.com/
-   CryptoQuant guide: https://userguide.cryptoquant.com/
-   CME cryptocurrency markets:
    https://www.cmegroup.com/markets/cryptocurrencies.html
-   TradingView: https://www.tradingview.com/
-   Deribit API: https://docs.deribit.com/
-   FRED: https://fred.stlouisfed.org/
-   CFTC Commitments of Traders:
    https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
-   Mempool.space: https://mempool.space/
-   CCXT: https://github.com/ccxt/ccxt
-   Reuters markets: https://www.reuters.com/markets/

------------------------------------------------------------------------

# Conclusion

The strongest direction for the Bitcoin AI trading system is a
combination of:

1.  Traditional technical analysis for identifying trends, momentum, and
    entry conditions.
2.  Market microstructure for understanding actual buying and selling
    pressure.
3.  Derivatives data for understanding leveraged positioning and
    liquidation risk.
4.  On-chain information for measuring supply, demand, and holder
    behaviour.
5.  Macroeconomic information for understanding the broader investment
    environment.
6.  Statistical models for estimating the probability of future
    outcomes.
7.  Strict risk management for controlling the consequences when
    predictions are wrong.

**Core design principle: the system should predict market conditions and
opportunities, not blindly follow indicators.**

Five well-tested indicators that demonstrably improve prediction are
more valuable than fifty indicators producing an impressive dashboard.

The next development milestone is to turn this research into a formal
technical specification: exact indicator definitions, calculation
parameters, data requirements, strategy entry/exit rules, and
backtesting criteria. This provides a blueprint for implementing and
testing each component without losing control of project scope.
