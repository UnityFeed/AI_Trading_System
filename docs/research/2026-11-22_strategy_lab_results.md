# Strategy lab, turning points and machine learning: first results (22 Nov 2026)

Cloud TEST database (real Bitstamp + Coinbase hourly standing in for Kraken from
2017), real Coin Metrics data, fee 0.25% (Bybit EU) + 0.05% slippage. The owner
reruns the three scripts on the real database; numbers will move a little.

## What was built
- Weekly (1w) timeframe: chart in the app; weekly features for daily strategies
  that only use the last COMPLETED week.
- Feature library (`src/research/features.py`): 39 daily features, each also as an
  expanding percentile rank (compared only with the past). Tested for look-ahead:
  every feature on a shortened history equals the full-history value.
- Turning-point study (`scripts/run_turning_points.py`).
- Strategy lab (`scripts/run_strategy_lab.py`): 70 filters (incl. weekly, on-chain,
  Coinbase premium, trend + context pairs) x 24 triggers x 16 exits x 3 trailing
  stops x 3 core shares = 200,145 strategies, all CPU cores.
- Machine learning (`scripts/run_ml_research.py`): logistic regression and a
  nearest-neighbour "analog" model, walk-forward by year, point-in-time labels.

## Findings
1. **Picking the single best combination is luck.** Of 106,749 strategies with
   enough trades, 9 beat holding in both 2013-16 and 2017-21; on 2022-now those 9
   did worse than the rest. Walk-forward (each year chosen on earlier years):
   single best x0.64, top-10 average x0.53 vs holding.
2. **Building blocks are more reliable than single winners.** Judged over all
   combinations (medians, chosen on 2013-21 only): keep a 50% core; buy strength
   (strong 28-day momentum, breakouts), not dips; weekly MACD above its signal and
   long-trend filters help; exit slowly (close below the 200-day average, blow-off,
   EMA20/50 cross). Choosing the best FAMILY by its median did x1.54 in the
   walk-forward.
3. **New registered strategy** "Lab: weekly MACD + momentum, 50% core":
   x1.39 vs holding over the full history (2022-now, not used to choose: x1.41),
   about one trade a year, break-even fee 3.5%.
4. **The lag is real but buying earlier did not pay.** Strategies buy ~45-50 days
   after lows. Oversold readings make a low 2.5-2.7x more likely within 20 days and
   an ML model sees lows coming with modest skill, but using that to buy earlier
   did not beat the trend rule (more false lows than gained days).
5. **Predicting next month's direction from these features does not work**
   (negative skill, trading on it loses).

## Honest limits
Few big cycles (4-5 in 13 years); 2022-now has been looked at many times;
200,000+ trials make luck likely (Deflated Sharpe vs holding is 0.00 for the best).
Forward paper trading remains the real test.
