# BTC/USD Long-Only Spot Research: Strategies, Indicators, Data and Test Plan (Deep-Dive v2, Nov 2026)

**Bottom line:** No published, independently replicated, after-fee study shows a long-only BTC timing rule beating buy-and-hold on *return*. The consistent finding, which matches your own result, is that simple daily trend rules (price above a moving average, time-series momentum, channel breakouts) cut drawdowns and volatility by roughly half and improve risk-adjusted performance while giving up much of the raw return. The next gains are more likely from portfolio construction (core-plus-overlay, exposure capped by volatility, rebalanced BTC/cash) and a few low-frequency external signals (MVRV, hash rate) than from more indicators.

## TL;DR
- **What holds up:** daily price-to-moving-average and time-series-momentum rules have the best evidence (peer-reviewed, out-of-sample, tested after realistic Bitstamp costs through 2022). They improve Sharpe ratio and drawdown, not return. Hourly/4h rules lose to fees, and multiple-testing-controlled studies find almost nothing at those frequencies for BTC.
- **Why you get ~1/4 of buy-and-hold:** this is structural. BTC's gains are concentrated in very few days, which often arrive as violent rebounds right after selloffs, exactly when a trend filter is out. Grayscale data: a 225% three-year return falls to 95% without the 5 best days and to −11% without the 15 best. The fix is to stay partly invested (core + overlay, volatility-scaled exposure), not to find a "better" crossover.
- **What to add:** only a handful of things are worth the multiple-testing cost: (1) a 50/50 core-plus-trend-overlay, (2) volatility-scaled exposure capped at 100%, (3) a banded BTC/cash rebalance, (4) MVRV/MVRV-Z and hash-rate signals from free daily APIs. Skip calendar effects, halving timing, Stock-to-Flow, Fear & Greed, ETF flows and funding-rate timing for now. Their evidence is weak, short or contaminated by look-ahead.

---

## 1. Project context (for a new chat)

| Item | Value |
|---|---|
| System | Python, paper-trading-first BTC/USD research and backtesting |
| Data | Hourly OHLCV from Kraken, Bitstamp, Coinbase, 2013 to present (~13 years) |
| Constraints | Spot only, long-only (BTC or cash/stablecoin). No margin, shorting or leverage, so exposure is always between 0% and 100% |
| Fees assumed | 0.10–0.26% per side, plus spread/slippage |
| Existing result | Daily trend following (EMA 50/200 trend filter + MACD or EMA 20/50 entries) cut the worst out-of-sample drawdown from ~84% to ~52% but earned ~1/4 of buy-and-hold's return. Hourly and 4h strategies lost to fees |
| Goal of this pass | Deepen the strategy evidence, catalogue every indicator, document free data sources, define the testing methodology and a ranked next-step plan |

**Evidence codes used throughout:**
- **A**: peer-reviewed, out-of-sample, ideally after costs.
- **B**: independent replication or several consistent studies, or a rigorous working paper.
- **C**: in-sample only, or a single small sample.
- **D**: vendor, blog or marketing only.
- **E**: no evidence found.

---

## 2. Evidence register (ranked by quality of evidence, with links)

This table doubles as the master source list. "Re-verified" means checked in this pass. Items carried over from the first pass are marked.

| Rank | Study | What was tested | Period | Out-of-sample? | After fees? | Key result | Code | Link |
|---|---|---|---|---|---|---|---|---|
| 1 | Deprez & Frömmel, *Are simple technical trading rules profitable in bitcoin markets?* (Int. Rev. Econ. & Finance, 2024) | 75,360 rules (MA, filter, support/resistance, channel breakout, OBV, RSI) at daily, 60, 30 and 10-minute frequencies on Bitstamp tick data. Monthly re-selection of the best rules over the past year with FDR control | 2013–2022; out-of-sample 2014–2022 (2,922 days) | Yes (rolling) | Yes: fee plus half the bid-ask spread | Portfolios slightly beat buy-and-hold on return but **not significantly**. They roughly halve both up and down moves, **significantly cut max drawdown and VaR**, and improve risk-adjusted measures. 450–750 trades; outperformance vs buy-and-hold vanishes with < 0.05 pp of extra cost per trade. Only 1.68–2.95% of rules beat the benchmark in-sample. Daily portfolios are far more robust to costs than intraday ones | A | https://www.sciencedirect.com/science/article/abs/pii/S1059056024003010 ; preprint: https://backoffice.biblio.ugent.be/download/01HY3C3S169G1N6QNYR55NZMFB/01HY60XZGZYHNQ6188MSVJT0SG |
| 2 | Detzel, Liu, Strauss, Zhou, Zhu, *Learning and predictability via technical analysis* (Financial Management 50(1):107–137, 2021) | Price/MA ratios (5–100-day SMA). Long BTC when price > MA, else cash | Jul 2010–Jun 2018 | Yes | Break-even costs only | Price-to-MA ratios forecast daily BTC returns in and out of sample. Includes an equilibrium model of *why* MAs work for hard-to-value assets. Stronger before 2014 | A | https://onlinelibrary.wiley.com/doi/abs/10.1111/fima.12310 |
| 3 | Liu & Tsyvinski, *Risks and Returns of Cryptocurrency* (Rev. Financial Studies 34(6):2689–2727, 2021) | Time-series momentum, attention (Google searches), macro/stock factors | 2011–2018 | Predictive regressions | No | Strong time-series momentum. Attention proxies forecast returns. No exposure to standard stock, macro, FX or commodity factors | A (signal), not a trading test | https://www.nber.org/papers/w24877 |
| 4 | Hudson & Urquhart, *Technical trading and cryptocurrencies* (Annals of Operations Research, 2019/2021) | ~14,919 rules with data-snooping control | 2010–2017 | Yes | Break-even | Significant in-sample; **no out-of-sample outperformance for Bitcoin** (some for other coins). Filter and channel-breakout rules were best in-sample | A (negative) | https://link.springer.com/article/10.1007/s10479-019-03357-1 |
| 5 | Wei/Kyriakou et al. (Glasgow eprint 302711), first pass, not re-verified | 7,846 technical rules + MA ratios + 59 fundamentals; Lucky Factors and SPA | — | Yes | — | Only the short-term log-MA ratio and a Hashrate index were profitable in and out of sample | B | https://eprints.gla.ac.uk/302711/ |
| 6 | Anghel (Finance Research Letters 2021), first pass, not re-verified | Data-snooping-robust tests with frictions | — | Yes | Yes | Significant excess returns rarely achieved after snooping and friction controls. Omitting costs inflates false discoveries | A (negative) | https://doi.org/10.1016/j.frl.2020.101655 |
| 7 | Grobys, Näsman, Sandretto, *Using on-chain data to predict Bitcoin cycles* (RIBAF 89, 103486, 2026) | Rule-based NUPL, MVRV-Z and CVDD strategies | 7 Dec 2013–12 Apr 2025 (three cycles) | No real holdout; thresholds may be hindsight | No (says results hold at 2% per trade) | MVRV-Z Sharpe 1.01/1.19/1.28 vs buy-and-hold 0.45; NUPL 0.82–1.12. **Only 3 trades per strategy**, last one still open | C | https://iris.unito.it/retrieve/8e104076-d79e-4df7-a1fe-1f86d7630c41/1-s2.0-S0275531926002138-main.pdf |
| 8 | Harvey, Hoyle, Korgaonkar, Rattray, Sargaison, Van Hemert, *The Impact of Volatility Targeting* (JPM 2018) | Volatility scaling across 60+ assets (not BTC) | 1926–2017 | Yes (ex-ante volatility) | Costs estimated | Raises Sharpe for **risk assets** (equities, credit) via the leverage effect; little effect elsewhere. Reduces tail risk for all | A (non-BTC) | https://people.duke.edu/~charvey/Research/Published_Papers/P135_The_impact_of.pdf |
| 9 | Habeli, Barakchian, Motavasseli, *Adaptive Risk Allocation in Crypto Markets* (SSRN) | Volatility scaling of the crypto market and 7 crypto strategies | — | — | — | Volatility scaling raises Sharpe, especially for momentum and the market portfolio, even under tight leverage limits | B− | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5090097 |
| 10 | Howden & Andreev, *Risk-Managed Time-Series Momentum in Crypto Majors* (SSRN, 2026) | Long/cash 30-day TSMOM on 7 majors plus drawdown-state de-risking | — | Walk-forward, L = 30 fixed a priori | Yes, 25 bp | Net Sharpe 1.41 vs 0.70 buy-and-hold; max drawdown −44.6% vs −84.4%. **Volatility targeting/Kelly on top was "settled null"**. Authors flag L = 30 fragility and survivorship | B− | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7115459 |
| 11 | Fabus, Vartiak, Stalmasekova, Kicova, *Spot Bitcoin ETF Flows and Bitcoin Returns: Timestamp Alignment* (SSRN, 2026) | ETF flows vs BTC returns, aligned to 24/7 trading | 2024– | — | — | With a return window that starts **after flows are public**, there is **no positive association**. Returns predict flows strongly | B (negative) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7545019 |
| 12 | *Do bitcoin returns move sentiment? Evidence from the crypto Fear & Greed index* (Finance Research Open, 2026) | VAR with FGI changes | 2018–2025 | Yes | — | ΔFGI does not Granger-cause returns and gives **no out-of-sample gain**. Returns drive FGI | A (negative) | https://www.sciencedirect.com/science/article/pii/S305070062600006X |
| 13 | Baur, Cahill, Godfrey, Liu (FRL 2019), first pass, not re-verified | Time-of-day, day-of-week, month effects | — | — | — | Not persistent | A (negative) | https://doi.org/10.1016/j.frl.2019.04.023 |
| 14 | Aslanidis, Bariviera, López (FRL 2022), first pass, not re-verified | Google Trends vs crypto | — | — | — | Bidirectional up to ~6 days; more information flows from volatility to attention | B (mixed) | https://doi.org/10.1016/j.frl.2021.102654 |
| 15 | Inan, *Predictability of Funding Rates* (SSRN / IRFA 2026) | Forecasting funding rates (Binance, Bybit) | — | Yes | — | Funding **levels** are predictable. This is not evidence that funding predicts **spot returns** | B (indirect) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424 |
| 16 | *Extreme Perpetual Futures Funding and Subsequent Bitcoin Returns* (AIJMR, 2026) | Extreme Binance funding states → spot returns | — | — | — | Weak or inconsistent. Much of the effect is ordinary return reversal, not independent funding information. Low-tier journal | C | https://www.aijmr.com/papers/2026/4/1493.pdf |
| 17 | Lim, *The Price Impact of Spot Bitcoin ETF Flows* (SSRN) | Flows → next-day returns | 2024– | — | — | Claims next-day prediction (t = 3.12). Likely affected by the timestamp issue Fabus et al. identify | C | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6592830 |
| 18 | Burger, *Fall of Cointegration* (S2F critique); Shelton 2024 via review arXiv 2606.00071 | Stock-to-Flow | — | — | — | S2F cointegration claims invalid (S2F is stationary between halvings). In-sample fit only, little or no out-of-sample ability | A/B (negative) | https://bitcoinwords.github.io/reviewing-modelling-bitcoins-value-with-scarcity ; https://arxiv.org/pdf/2606.00071 |
| 19 | Rink, *Predictive ability of technical trading rules* (FMPM 2023, equities) | Large rule universe, 41 equity markets | — | Yes | Yes | In-sample best rules **significantly underperform out-of-sample** even at low cost. A general warning that applies to BTC | A (non-BTC) | https://link.springer.com/article/10.1007/s11408-023-00433-2 |
| 20 | Grayscale return-concentration analysis (reported by Webopedia/KuCoin, 2026); CoinDesk historical analysis (Sep 2026) | Missing best days | 3 years to 2026; 2010–2026 | n/a | n/a | 225% → 95% (−5 best days), 27% (−10), −11% (−15). Nasdaq: 109% → 21% (−15) | D (descriptive, but simple arithmetic) | https://www.webopedia.com/news/bitcoin-vs-nasdaq-missing-best-trading-days/ ; https://www.coindesk.com/markets/2026/09/05/why-crypto-experts-say-buying-and-holding-bitcoin-easily-beats-trying-to-time-the-market |
| 21 | Hanicova & Vojtko, *Rebalancing Premium in Cryptocurrencies* (SSRN/Quantpedia) | Daily/monthly rebalanced 27-coin portfolio vs buy-and-hold | — | — | — | Rebalancing improved return and lowered volatility | C/D (multi-coin; Quantpedia is a vendor) | https://quantpedia.com/strategies/rebalancing-premium-in-cryptocurrencies |
| 22 | Bouchey et al., *Volatility Harvesting* (theory); Maeso et al., *Numerical perspectives on the rebalancing premium* (Quant. Finance 2025) | Rebalancing premium mechanics | — | — | — | Premium ≈ ½ × (weighted average variance − portfolio variance). Real, but depends on mean reversion versus trend | A (theory) | https://www.researchgate.net/publication/277490879_Volatility_Harvesting_Why_Does_Diversifying_and_Rebalancing_Create_Portfolio_Growth ; https://www.tandfonline.com/doi/abs/10.1080/14697688.2025.2577822 |
| 23 | DCA vs lump sum: Vanguard (generic); Nakamoto Portfolio; Amdax (BTC) | Entry method | 2012–2025 | n/a | n/a | Lump sum beats DCA in most windows (Vanguard Research, "The truth about cost averaging": lump sum won 61.6–73.7% of rolling one-year periods across markets, 1976–2022; BTC vendor studies are similar). DCA lowers drawdown and regret | D | https://nakamotoportfolio.com/static/docs/DCA_Lumpsum.pdf ; https://medium.com/amdax-asset-management/lump-sum-or-dollar-cost-averaging-42c8f5bb9938 |
| 24 | Student OOS project (CUFE), btc-risk-return-predictability | 30-day momentum, EWMA volatility, 30% vol target | Train 2018–21, test 2024–25 | Yes | Yes | 30-day momentum: no next-day predictability (R²_OOS ≈ 0). Volatility target net Sharpe 0.79 vs fixed-mix 0.89 (not significant) | D (unreviewed, but an honest null) | https://github.com/albertkho528/btc-risk-return-predictability |
| 25 | Shen et al., *Bitcoin intraday time-series momentum* (Reading, accepted) | First half-hour predicts last half-hour | — | Yes | — | Intraday effect. Not usable at your fee level | B (not applicable) | https://centaur.reading.ac.uk/100181/3/21Sep2021Bitcoin%20Intraday%20Time-Series%20Momentum.R2.pdf |
| 26 | Methodology: Bailey & López de Prado, *Deflated Sharpe Ratio* (JPM 40(5), 2014); Bailey, Borwein, López de Prado, Zhu, *Probability of Backtest Overfitting* (J. Comp. Finance 20(4), 2017); White Reality Check (2000); Hansen SPA (2005); Harvey-Liu-Zhu (RFS 2016); Moskowitz-Ooi-Pedersen TSMOM (JFE 2012); Moreira-Muir (JF 2017) | — | — | — | — | — | A | https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf ; https://sdm.lbl.gov/oapapers/ssrn-id2507040-bailey.pdf ; https://doi.org/10.1111/1468-0262.00152 ; https://doi.org/10.1198/073500105000000063 ; https://doi.org/10.1093/rfs/hhv059 ; https://doi.org/10.1016/j.jfineco.2011.11.003 ; https://doi.org/10.1111/jofi.12513 |

**Corrections to the first pass:**
- **Coin Metrics Community has been trimmed.** On 28 Oct 2025 Talos/Coin Metrics announced ("Updates to Coin Metrics Community Data") that some Community metrics and data types would be retired, while Research Asset Metrics, Reference Rates and Atlas data stay free. The CryptoMarkets.tools review (updated Oct 2026) counts **32 free daily asset metrics**, not ~147, and says they cover network activity, supply, exchange flows, hash rate and market cap. CapMVRVCur, PriceUSD, SplyCur, CapMrktCurUSD and AdrActCnt are confirmed still served. Confirm HashRate and exchange-flow metric names against the live catalog.
- **Detzel et al.'s sample runs to mid-2018**, not 2017.
- **Hudson & Urquhart used ~14,919 rules** (≈15,000 is fine).

---

## 3. Why the trend filter gives up ~3/4 of the return (structural, not a bug)

1. **Return concentration.** Per Grayscale (2026), BTC's three-year 225% gain falls to 95% without the 5 best days, 27% without the 10 best and −11% without the 15 best: under 1.4% of days. CoinDesk's 2010–2026 review finds the same pattern in most calendar years. 2013 and 2017 are exceptions, where gains were broad grinding rallies.
2. **Best days cluster next to worst days.** Grayscale notes sharp selloffs are often followed by powerful recoveries. A trend filter exits after the selloff and re-enters only after the MA turns, so it systematically misses the rebound. An EMA 50/200 cross lags by weeks to months.
3. **The literature shows the same trade.** In Deprez & Frömmel's out-of-sample portfolios, the rules **roughly halved both positive and negative returns**. Drawdown and VaR fell significantly, but the return gain was not significant. Your 84% → 52% drawdown at ~1/4 of the return is the same trade, made more costly by slow MAs.
4. **Daily autocorrelation supports trend, weakly.** On Bitstamp 2013–2022 daily data, autocorrelation is insignificant at lag 1 (−0.023) and positive at lags 5 and 10 (+0.068, +0.056). Hourly lag-1 is negative (−0.087), which points to short-term reversal that fees consume. This favours medium-term trend over daily mean reversion.

**Implication:** a binary in/out filter cannot both avoid 80% drawdowns and capture the few explosive days. The fix is to **never be at 0% exposure for long**: use a core allocation, faster but smoothed signals, or graded exposure, and judge success on Calmar/Sharpe/max drawdown versus a *volatility-matched* buy-and-hold blend, not raw CAGR.

---

## 4. Strategy catalogue (exact rules, evidence, overfitting risk)

All rules use the daily close at 00:00 UTC, with execution at the *next* bar's open. Exposure is between 0 and 1.

| # | Strategy | Exact codable rule | Evidence (code) | OOS / after fees | Weaknesses | Overfit risk | Verdict |
|---|---|---|---|---|---|---|---|
| S1 | Price/MA ratio (baseline) | `pos = 1 if close > SMA(N) else 0`, N ∈ {20, 50, 100} fixed, or an equal-weight ensemble of the three | A (Detzel; Deprez; Wei/Kyriakou) | OOS yes; break-even/realistic costs yes | Whipsaw in ranges; weaker post-2014 | Low if N is not tuned | **Need** (benchmark) |
| S2 | Time-series momentum | `pos = 1 if close/close[L] − 1 > 0`, L ∈ {28, 56, 91, 182}; ensemble = mean of signals (graded exposure 0, 0.25 … 1) | A signal (Liu-Tsyvinski); B− trading (Howden-Andreev) | Partially; 25 bp | Single-L results are fragile (authors admit L = 30 sharpness) | Medium for one L, low for ensemble | **Need** |
| S3 | Core + trend overlay | `exposure = c + (1−c) × signal`, c ∈ {0.3, 0.5} fixed in advance; signal = S1 or S2 ensemble | E for BTC specifically; it is arithmetic (a linear blend of buy-and-hold and the overlay) | n/a | Drawdown sits between the two components; still ~(c × 84%) in a crash | Very low (one parameter, chosen by risk tolerance) | **Need**: most direct fix for the return give-up |
| S4 | Volatility-scaled exposure (capped) | `σ̂ = EWMA std of daily log returns (λ≈0.94) × √365`; `w = min(1, σ* / σ̂)`, σ* ∈ {40%, 60%}; optionally `exposure = signal × w` | A for non-BTC risk assets (Harvey et al.); B− crypto (Habeli et al.); **nulls**: Howden-Andreev, student OOS | Mixed | No leverage means it can only *reduce* exposure, so it lowers return. BTC's volatility often rises in rallies (a weaker leverage effect than equities) | Low–medium | **Worth testing**, as risk control, not alpha |
| S5 | Fixed-weight BTC/cash rebalancing | Target w ∈ {50%, 60%, 80%}. Rebalance when `abs(w_actual − w) > 10 pp` (bands beat calendar rebalancing on fees) | A theory (volatility harvesting); C/D crypto evidence | n/a | Gives up return in strong trends (sells winners); benefits from mean reversion | Very low | **Worth testing** as an alternative core |
| S6 | Donchian / channel breakout | Enter when `close > max(high, 50d)` (prior bars); exit when `close < min(low, 20d)` | C/B (best class in-sample for Hudson-Urquhart; no BTC out-of-sample edge; included in Deprez's rule universe) | Partial | A transformation of trend; redundant with S1/S2 | Medium (4 parameters) | Worth testing only as **one** ensemble member |
| S7 | RSI / Bollinger mean reversion (daily) | e.g. buy when `RSI(14) < 30` and `close > SMA200`, exit when `RSI > 55`; or buy when `%B < 0`, exit at the middle band | C (RSI class in Deprez and Gerritsen et al.; no BTC out-of-sample edge found) | No | Daily autocorrelation does not support reversal; catches falling knives in bear markets | High | **Skip** (at most a re-entry timing tweak inside an uptrend) |
| S8 | MVRV-Z valuation overlay | `Z = (MarketCap − RealizedCap)/std(MarketCap, expanding)`. Grobys rule: long when Z < −0.2, exit when Z ≥ 5/6/7. Practical version: `cap exposure = 1 if Z<3; 0.5 if 3≤Z<5; 0.25 if Z≥5` | C (3 trades; possible hindsight thresholds) | No | Thresholds drift down each cycle (the 2025 top had MVRV ≈2.3–2.8 depending on vendor: 2.29 on Coin Metrics data, 2.52 per Amberdata, 2.74 per Bitcoin.com, vs 3.96–5.88 at earlier tops); realized-cap methodology differs by vendor | High if thresholds are tuned; medium for coarse buckets | **Worth testing** as a slow cap, never as the main signal |
| S9 | Hash ribbons / hash-rate trend | `HR30 = SMA30(hashrate)`, `HR60 = SMA60(hashrate)`; "capitulation over" when HR30 crosses above HR60 after being below; allow entries only then, or add as a filter | B− (Wei/Kyriakou: Hashrate index profitable in and out of sample); D for the hash-ribbon variant | Partial | Hash rate is an *estimate* from block times and is noisy and revisable; few signals | Medium | **Worth testing** |
| S10 | Drawdown / trailing stop overlay | Exit when `close < (1 − k) × max(close since entry)`, k ∈ {20%, 30%}; re-enter via S1 | C (crypto cross-sectional stop-loss study; Howden-Andreev drawdown state) | Partial | Another lagging trend filter; whipsaws in high-volatility bull markets | Medium | Low priority (redundant with S1/S2) |
| S11 | DCA / lump sum / value averaging | DCA: buy fixed $ weekly. Value averaging: buy or sell to hit a target value path | D (Vanguard generic; BTC vendors: lump sum usually wins; DCA cuts drawdown) | n/a | Cash-flow policy, not a timing strategy. No BTC value-averaging evidence found | n/a | Use only to model *deployment* of new cash |
| S12 | Halving-cycle timing | e.g. long from halving to +18 months, cash otherwise | C/E (n = 4 halvings; pattern already changed in 2024–25) | No | No statistical power; the narrative is widely known | Extreme | **Skip** |
| S13 | Weekend / US-session / time-of-day | e.g. hold only weekdays, or only the US session | A negative (Baur et al. 2019: not persistent) | — | Needs intraday trading, so fees dominate | High | **Skip** |
| S14 | Funding-rate contrarian spot entries | e.g. buy when 7-day mean funding < 0 | C/D (BitMEX/K33 blogs; AIJMR shows little beyond reversal) | No | Data only since 2016 (BitMEX) / 2019 (Binance); regime changes as basis trades grew | High | **Skip for now**; revisit as a filter |
| S15 | ETF-flow following | Buy after large net inflows | B negative (Fabus et al.: no edge once timestamps are aligned) | — | Published after the US close; data starts Jan 2024 | High | **Skip** |

---

## 5. Indicator catalogue

**Redundancy warning (read first):**
- **Trend family:** SMA/EMA crosses, price/MA, MACD (= EMA12 − EMA26, i.e. a difference of two MAs), PPO, KAMA, Hull, TSMOM (≈ price vs a lagged price), the sign of the linear-regression slope, Donchian, SuperTrend, Parabolic SAR and Ichimoku cloud position all encode "is price above its recent average or range?". Their signals correlate around 0.7–0.9 on daily BTC. **Count them as one family:** pick 1–2 representatives plus an ensemble, and count *every* parameter combination you try as a trial.
- **Oscillators:** RSI, Stochastic, Williams %R, CCI, Bollinger %B and the price z-score are near-monotone transforms of "distance from recent mean, scaled by range or volatility". Williams %R is exactly −(100 − Stochastic %K).
- **Volatility:** ATR, Parkinson, Garman-Klass, Yang-Zhang, realized volatility, Bollinger bandwidth and Keltner width are estimators of the same quantity.
- **On-chain valuation:** MVRV, MVRV-Z, NUPL (= 1 − 1/MVRV), realized price and the realized-price-based parts of CVDD and Reserve Risk are largely one signal. **NUPL is a deterministic transform of MVRV.**

Legend: **Data** O = OHLCV only, X = external. **Evidence** codes A–E as above. **Verdict** N = need, T = worth testing, S = skip.

### 5.1 Price / trend
| Indicator | Definition (codable) | Data | Evidence | Look-ahead risk | Verdict |
|---|---|---|---|---|---|
| SMA(N) | mean of last N closes | O | A (as price/MA) | none if computed on closed bars | N |
| EMA(N) | `e_t = α·c_t + (1−α)e_{t−1}`, α = 2/(N+1) | O | B | warm-up bias in first ~3N bars | N (pick SMA *or* EMA, not both) |
| Price/MA ratio | `c/SMA(N) − 1` (log version: `ln c − ln SMA`) | O | A (Detzel; Wei/Kyriakou short-term log-MA) | none | **N**, primary |
| MACD | `EMA12 − EMA26`; signal = EMA9 of MACD | O | C (Gerritsen et al. in-sample) | none | S (redundant with MA crosses) |
| ADX | Wilder DMI smoothing of +DM/−DM over 14 bars | O | C/E for BTC | none | T only as a regime filter (ADX > 20) |
| Donchian | rolling max(high, N), min(low, N) on *prior* bars | O | C/B (channel breakout best in-sample, H&U) | include the current bar = look-ahead bug | T (one member) |
| Ichimoku | Tenkan (9), Kijun (26), Senkou A/B **shifted forward 26** | O | E/D | the forward shift is a classic look-ahead bug | S |
| SuperTrend | ATR band (k = 3, n = 10) flip logic | O | D | none | S (redundant) |
| Parabolic SAR | acceleration-factor trailing stop | O | D | none | S |
| KAMA | EMA with α scaled by efficiency ratio | O | E | none | S (unless testing adaptive speed) |
| Hull MA | `WMA(2·WMA(n/2) − WMA(n), √n)` | O | E | none | S |
| Linear regression slope | OLS slope of ln(close) over N bars | O | E (≈ TSMOM) | none | S (redundant) |
| TSMOM lookbacks | `sign(ln c_t − ln c_{t−L})`, L = 28–365 | O | A (Liu-Tsyvinski; MOP 2012 in other assets) | none | **N** (ensemble) |
| Mayer multiple / 200-day | `c/SMA200` | O | = price/MA | none | covered by price/MA |
| 200-week MA | SMA of weekly closes, 200 weeks | O | D (floor narrative) | needs ~4 years of warm-up, so unusable before ~2017 in your data | S |
| Pi Cycle Top | SMA111 crosses above 2×SMA350 | O | D (fit to 2013/2017/2021; failed to fire cleanly in 2025 per vendor trackers) | curve-fit | S |

### 5.2 Oscillators / mean reversion
| Indicator | Definition | Data | Evidence | Look-ahead risk | Verdict |
|---|---|---|---|---|---|
| RSI(14) | Wilder: 100 − 100/(1 + avgGain/avgLoss) | O | C (RSI class: no BTC out-of-sample edge) | none | T only as a pullback-entry tweak |
| Stochastic %K | `(c − LL_n)/(HH_n − LL_n)` | O | E | none | S |
| Williams %R | `−(HH − c)/(HH − LL)` = %K − 1 | O | E | identical to Stochastic | S |
| CCI | `(TP − SMA(TP))/(0.015·MAD)` | O | E | none | S |
| Bollinger %B | `(c − (m − 2σ))/(4σ)`, m = SMA20 | O | C | none | S/T (same as z-score) |
| Price z-score | `(c − SMA_n)/σ_n` | O | C | none | T (keep one of %B/z) |
| Connors RSI | mean of RSI(3), streak RSI(2), 100-day percent-rank of ROC | O | D (equity-focused) | none | S |

### 5.3 Volatility
| Indicator | Definition | Data | Evidence | Look-ahead risk | Verdict |
|---|---|---|---|---|---|
| ATR(14) | Wilder mean of true range | O | B (as a sizing tool) | none | N (for stops/sizing) |
| Realized volatility | `√(Σ r²)` over hourly returns within a day, or daily returns over N days | O | A (EWMA beats a 30-day rolling forecast per Diebold-Mariano in the student OOS; standard result) | none | **N** |
| Parkinson | `σ² = (1/(4 ln2)) · mean(ln(H/L)²)` | O | A (estimator theory) | sensitive to bad prints in highs/lows (2013 feeds) | T |
| Garman-Klass | `0.5 ln(H/L)² − (2ln2 − 1) ln(C/O)²` | O | A theory | same | T |
| Yang-Zhang | overnight + open-close + Rogers-Satchell blend | O | A theory | 24/7 market means "overnight" ≈ 0, so it reduces to RS | S (use RS/GK) |
| Bollinger bandwidth | `4σ/m` | O | E | none | S (redundant) |
| Keltner | EMA ± k·ATR | O | E | none | S |
| Volatility regimes | percentile of 30-day realized volatility vs a 1-year window | O | C | none | T (for S4) |
| GARCH(1,1) / EGARCH | conditional variance model | O | A (good volatility fit; arXiv 2511.06224) | refit only on past data | T (EWMA is usually as good) |

### 5.4 Volume / flow
| Indicator | Definition | Data | Evidence | Look-ahead risk | Verdict |
|---|---|---|---|---|---|
| OBV | cumulative ±volume by sign of return | O | C (OBV class in Deprez; no standalone edge) | volume differs by exchange | S |
| VWAP | Σ(p·v)/Σv over the session | O | E for daily | 24/7: define the session as the UTC day | S |
| Chaikin Money Flow | Σ(MFV)/Σv, MFV = v·((c−l)−(h−c))/(h−l) | O | E | none | S |
| MFI | volume-weighted RSI | O | E | none | S |
| Volume z-score | `(v − mean_n)/sd_n` of log volume | O | C | wash trading on some venues | T (as a confirmation feature) |
| Amihud illiquidity | `mean(|r|/$volume)` | O | B (liquidity shocks predict BTC volatility; JIFMIM 2022) | none | T (volatility/risk feature) |
| Cross-exchange divergence | `ln(P_Coinbase/P_Bitstamp)`, volume share shifts | O | E (analogous to Coinbase premium) | timestamp alignment | T (cheap with your data) |

### 5.5 Regime detection
| Indicator | Definition | Data | Evidence | Look-ahead risk | Verdict |
|---|---|---|---|---|---|
| Hurst exponent | R/S or DFA on a rolling 256–512-day window | O | C (efficiency-over-time studies) | noisy; needs long windows | T (diagnostic only) |
| Variance ratio | `Var(r_k)/(k·Var(r_1))` (Lo-MacKinlay) | O | B (used for market-efficiency tests) | none | T (diagnostic) |
| HMM regimes | 2–3-state Gaussian HMM on returns/volatility | O | C | **smoothed** probabilities use future data, so use only *filtered* probabilities | T (low priority) |
| Trend-strength filter | `abs(c/SMA200 − 1)` > x or ADX > 20 | O | E | none | T (one only) |

### 5.6 On-chain
| Indicator | Definition | Data | Evidence | Free source (history, frequency) | Look-ahead / revision | Verdict |
|---|---|---|---|---|---|---|
| MVRV | MarketCap / RealizedCap | X | C (Grobys) | Coin Metrics Community `CapMVRVCur` (2010–, daily) | vendor recalculations (Coin Metrics publishes data-change notices) | **T** |
| MVRV-Z | (MC − RC)/σ(MC) | X | C (Grobys; best Sharpe of the three) | derive from CM `CapMrktCurUSD` and MVRV | use an **expanding** σ only (vendor charts use full-sample σ = look-ahead) | **T** |
| Realized price | RealizedCap/Supply | X | C | derive from CM | same | T (as MVRV) |
| NUPL | 1 − 1/MVRV | X | C | derive | identical information to MVRV | S (redundant) |
| SOPR / aSOPR | realized value of spent outputs / their cost value | X | D | Glassnode (paid for history) | — | S |
| Puell Multiple | daily issuance USD / 365-day mean | X | D | derive from CM issuance (if still free) or block subsidy × price | none | S/T |
| Hash rate | estimated network hashes/s | X | B− (Wei/Kyriakou Hashrate index) | Blockchain.com charts `hash-rate`; mempool.space `/api/v1/mining/hashrate/:period` (daily) | estimate; recent days revised as blocks arrive, so lag 1–2 days | **T** |
| Hash ribbons | SMA30 vs SMA60 of hash rate | X | D | as above | as above | T (with hash rate) |
| Difficulty ribbon | set of SMAs of difficulty | X | D | Blockchain.com `difficulty` | changes every 2,016 blocks | S |
| NVT / NVT signal | MC / on-chain USD transfer volume (signal: 90-day MA) | X | C/D | CM (if `TxTfrValAdjUSD` still free) | change-output heuristics revised | S |
| Active addresses | unique active addresses per day | X | C (network-effect studies; spurious per Shanaev et al.) | CM `AdrActCnt` (confirmed free) | heuristics | S/T |
| Exchange reserves / net flows | balance of labelled exchange addresses | X | D (vendor) | CM `SplyExNtv`-type metrics (check catalog) | **large revisions** when new addresses are labelled | S (look-ahead risk too high) |
| Stablecoin supply ratio | BTC MC / stablecoin MC | X | C (one arXiv copula paper) | CM / DefiLlama | low | S |
| CVDD | cumulative coin-days destroyed in USD / network age / ~6×10⁶ | X | C (Grobys: entry only; exits at known peaks are hindsight) | Glassnode/BM Pro (paid) | constant was curve-fit | S |
| Reserve Risk | price / HODL bank | X | D | paid | — | S |
| Coin Days Destroyed | Σ(coins × days since last moved) | X | D | Blockchain-derived (paid aggregates) | — | S |
| LTH supply | supply unmoved > 155 days | X | D | Glassnode (paid) | — | S |
| Stock-to-Flow | ln(MC) on ln(stock/annual flow) | X | **A/B negative** (cointegration invalid; no out-of-sample ability) | — | regressing stock on stock | **S** |

### 5.7 Derivatives
| Indicator | Definition | Evidence | Free source (history) | Look-ahead | Verdict |
|---|---|---|---|---|---|
| Funding rate | 8-hour perp funding (premium + interest) | C/D for return prediction | Binance `/fapi/v1/fundingRate` (max 1,000 rows, 500 req/5 min, 2019–); Bybit `/v5/market/funding/history` (200 rows/page); OKX (only ~3 months via API); BitMEX (from 2016, not verified) | stamped at settlement; align to UTC | S now; T later as a filter |
| Open interest | contracts outstanding | D | Binance `openInterestHist` **only the last 30 days**; deeper history needs your own collection or bulk/vendor data | survivorship across venues | S |
| Futures basis | `(F − S)/S` annualised (quarterlies) | C | Deribit/CME (CME is paid) | — | S |
| DVOL | Deribit 30-day implied volatility index | C | Deribit `public/get_volatility_index_data` (daily since 24 Mar 2021, resolution down to 60 s) | none | T (as an S4 alternative to realized volatility, post-2021 only) |
| Options skew, put/call | 25-delta risk reversal; OI ratio | D | Deribit (needs your own snapshots) | — | S |
| Liquidations | forced closes | D | CoinGlass (free tier limited, not verified) | — | S |

### 5.8 Sentiment / attention
| Indicator | Evidence | Free source | Look-ahead | Verdict |
|---|---|---|---|---|
| Fear & Greed (alternative.me) | **A negative** (no out-of-sample gain; returns lead FGI) | `https://api.alternative.me/fng/?limit=0`, daily since 1 Feb 2018 | composite *includes* price momentum and volatility, so it is circular; value stamped 00:00 UTC | **S** |
| Google Trends | A/B mixed (Liu-Tsyvinski positive; Aslanidis: mostly volatility → attention) | `pytrends` (unofficial; weekly for long ranges, rescaled per request) | **re-normalised per query, so values change between pulls**; snapshot and splice | T (low priority) |
| Wikipedia page views | C | Wikimedia REST per-article, daily from Jul 2015 | stable once published | T (cleaner than Trends) |
| Social volume / news sentiment | D | paid (Santiment, LunarCrush) | vendor revisions | S |

### 5.9 Macro / cross-asset
| Indicator | Evidence | Free source | Look-ahead | Verdict |
|---|---|---|---|---|
| DXY, real yields (DFII10), VIX, Nasdaq/S&P, gold | B negative for prediction (Liu-Tsyvinski: no exposure to macro factors); correlations vary by regime | FRED API (key, 120 req/min): DTWEXBGS, DFII10, VIXCLS, SP500, NASDAQCOM | US-hours closes vs 00:00 UTC BTC bar: **lag 1 day**; weekends missing | S as signals; T as a risk-regime feature at most |
| M2 / global liquidity | C/D (popular "liquidity leads BTC" charts) | FRED M2SL (monthly) | **revised**: use ALFRED vintages; published with ~4-week delay | S |
| BTC–equity correlation | descriptive | compute from FRED + your data | as above | S (diagnostic) |

### 5.10 ETF flows / Coinbase premium
| Indicator | Evidence | Free source | Look-ahead | Verdict |
|---|---|---|---|---|
| Spot ETF net flows | B negative after timestamp alignment; flows follow returns (a DWF Labs study of 694 trading days, 11 Jan 2024–16 Oct 2026, reported by TokenPost, found flow correlation of 0.54 with returns over the prior 5 sessions, 0.09 with the next day and 0.03 with the next 5 sessions) | Farside (farside.co.uk, not verified) | published after the US close, often revised next day; history only from 11 Jan 2024 | **S** |
| Coinbase premium | D | **computable from your own data**: `ln(Coinbase BTC-USD / Binance BTC-USDT)` or Coinbase vs Bitstamp | USDT ≠ USD basis | T (free, cheap) |

---

## 6. Data sources: endpoints, history, limits, point-in-time handling

| Source | Endpoint (free) | History / frequency | Limits | Point-in-time / revision notes |
|---|---|---|---|---|
| Coin Metrics Community | `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=CapMVRVCur,CapMrktCurUSD,PriceUSD,AdrActCnt&frequency=1d` | 2010–, daily | 10 requests / 6 s per IP; no key; CC BY-NC (non-commercial) | Trimmed Oct 2025; check `/catalog-all/metrics`. History can be recalculated (status page posts data-change notices), so **snapshot every pull with a fetch timestamp** |
| Blockchain.com charts | `https://api.blockchain.info/charts/hash-rate?timespan=all&format=json&sampled=false` (also `difficulty`, `n-transactions`) | daily; start date not verified (likely 2009) | no published limit | hash rate is an estimate; recent points revised |
| mempool.space | `GET /api/v1/mining/hashrate/:timePeriod` | daily averages | unpublished limit, HTTP 429 on abuse | as above |
| Binance USDⓈ-M | `/fapi/v1/fundingRate` (limit ≤ 1,000); `/futures/data/openInterestHist` (**last 1 month only**); bulk zips at data.binance.vision | funding from Sep 2019; klines from Aug 2017 | 500 req/5 min (funding); 1,000 req/5 min (OI) | commercial use of the Vision archive needs a licence |
| Bybit v5 | `/v5/market/funding/history?category=linear&symbol=BTCUSDT` | ~2020– | 200 rows/page; page back with endTime | — |
| OKX v5 | `/api/v5/public/funding-rate-history` | **~3 months via API** | 10 req / 2 s | deeper history only via the download module (not verified) |
| Deribit | `public/get_volatility_index_data` (DVOL); `public/get_funding_rate_history` (not verified) | DVOL from 24 Mar 2021 | public | — |
| alternative.me | `https://api.alternative.me/fng/?limit=0&format=json` | daily from 1 Feb 2018 | none published; attribution required | timestamp 00:00 UTC; partly price-derived |
| Google Trends | `pytrends` (unofficial) | weekly/monthly for long ranges | aggressive throttling | re-normalised per request: store raw pulls |
| Wikimedia | `https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Bitcoin/daily/20150701/20261231` | daily from Jul 2015 | new per-minute limits being rolled out in 2026; send a User-Agent | stable |
| FRED / ALFRED | `fred/series/observations?series_id=…&api_key=…` with `realtime_start/realtime_end` or `vintage_dates` | series-specific | 120 req/min, free key | use **ALFRED vintages** for revised series (M2, GDP) |
| Farside, CoinGlass, Glassnode, CryptoQuant | web table / free tiers | — | **not verified this pass**; free tiers typically restrict resolution and history | treat as non-reproducible unless snapshotted |

**Point-in-time rules for your pipeline:**
1. Store every external pull as an immutable snapshot (`fetched_at`, `source`, `raw`).
2. Align everything to UTC with the daily bar closing at 00:00 UTC.
3. **Lag all daily external data by one full bar.** A metric "for day D" is often finalised hours after D ends.
4. Lag US-market data (FRED, ETF flows) to the next UTC day after publication.
5. Use expanding-window normalisation (z-scores, percentiles), never full-sample.
6. For revised macro series, backtest on ALFRED vintages.
7. Treat labelled-entity metrics (exchange reserves) as unusable for backtests unless you have point-in-time vintages.

---

## 7. Testing methodology

**Protocol**
1. **Pre-register** the candidate list (Section 8), parameter grids and metrics before running. Log every run, including failures, in a trials ledger with its trial count.
2. **Walk-forward:** expanding window from 2014 with ≥ 3 years of initial training, re-fit annually, test on the next 12 months, and stitch the out-of-sample segments. Keep **2024–2026 as a final untouched holdout**, used once.
3. **Purged / combinatorial cross-validation (CPCV):** split ~12 years into ~10 blocks and purge plus embargo around each test block by the longest lookback (e.g. 200 days). This yields a *distribution* of out-of-sample Sharpe ratios rather than one path.
4. **Multiple-testing correction:**
   - Deflated Sharpe Ratio using the real number of trials from the ledger and the skew/kurtosis of returns.
   - Probability of Backtest Overfitting via CSCV across the parameter grid. Reject a strategy if PBO > 0.2–0.3.
   - White's Reality Check / Hansen's SPA (stationary bootstrap) against buy-and-hold and a volatility-matched buy-and-hold/cash mix.
   - Harvey-Liu-Zhu: require t ≳ 3 for new discoveries.
5. **Benchmarks:** buy-and-hold; a static BTC/cash mix with the *same average exposure or volatility* as the strategy. This is critical, because a trend rule that is 55% invested should be compared with 55% BTC, not 100%. Also compare with S1 (price > SMA100) as the "simple rule to beat".
6. **Metrics:** CAGR, volatility, Sharpe, Sortino, max drawdown, Calmar, time under water, turnover, average exposure, upside/downside capture, % of the top-20 days captured. The last one diagnoses the structural give-up directly.

**Costs**
- Model a fee of 0.10–0.26% per side, plus half-spread slippage of ≥ 0.05% (Deprez measured an average 0-depth Bitstamp spread of 0.134% over 2013–2022, much wider early on), plus a volatility-scaled slippage term.
- Stress-test at 2× costs.
- Report **break-even cost per trade**. Anything with a break-even below ~0.5% round trip is fragile.
- Earlier eras had higher fees: Bitstamp charged ≥ 0.20% before March 2015.

**2013-era data pitfalls**
- **Mt. Gox (to Feb 2014):** prices diverged from other venues by up to tens of percent before the collapse. Exclude it, and never splice it into a composite.
- **Thin liquidity:** 2013–2015 Kraken/Coinbase hourly bars contain gaps, zero-volume hours and spikes. Clean with a Brownlees-Gallo-style outlier filter (Deprez used δ = 10%, k = 40) and forward-fill only prices, never volume.
- **Outages and hacks:** Bitstamp was hacked in Jan 2015 and halted for days. Mark halted periods as untradeable rather than as flat returns.
- **Composite price:** build a **median of the available venues** per hour (Bitstamp, Coinbase, Kraken), require ≥ 2 live venues, and log the venue dispersion. Backtest signals on the composite but fill at a single venue's price plus spread.
- **Exchange-specific behaviour:** volume is not comparable across venues (fee rebates, wash trading). Normalise volume per venue before combining.
- **Daily bar definition:** fix the 00:00 UTC close. Vendor "daily" closes differ (Coin Metrics uses UTC midnight; some sites use New York time).
- **Regime drift:** most studies find edge decaying after 2014–2017 as the market matured. Weight post-2018 out-of-sample performance most heavily.

---

## 8. Ranked shortlist: what to test next (by evidence, then ease)

| Rank | Candidate | Exact rule | Why | Ease |
|---|---|---|---|---|
| 1 | **S1 price/MA ensemble** | `sig = mean([c > SMA20, c > SMA50, c > SMA100])` → exposure ∈ {0, ⅓, ⅔, 1}; daily, next-open execution | Best-evidenced rule (A); graded exposure reduces whipsaw | OHLCV |
| 2 | **S2 TSMOM ensemble** | `sig = mean([ret_28 > 0, ret_56 > 0, ret_91 > 0, ret_182 > 0])` | A-level signal evidence; ensembling avoids single-lookback fragility | OHLCV |
| 3 | **S3 core + overlay** | `exp = 0.5 + 0.5 × sig` (sig from #1 or #2); rebalance only when `abs(Δexp) ≥ 0.125` | Directly attacks the structural return give-up | OHLCV |
| 4 | **S4 volatility cap** | `exp_final = exp × min(1, 0.60/σ̂_EWMA(λ=0.94))` | Tail-risk control with solid non-BTC evidence; expect lower return, so judge on Calmar | OHLCV |
| 5 | **S5 banded rebalance** | target 60% BTC; rebalance when drift > 10 pp | Zero-parameter-search alternative core; tests the rebalancing premium | OHLCV |
| 6 | **S8 MVRV-Z cap** | expanding-σ Z; cap exposure 1 / 0.5 / 0.25 at Z < 3 / 3–5 / ≥ 5; data lagged 1 day | Only on-chain signal with a peer-reviewed (if tiny-sample) trading test | Coin Metrics, daily |
| 7 | **S9 hash-rate filter** | block *new* entries while SMA30(HR) < SMA60(HR); lag 2 days | B− evidence (Wei/Kyriakou); free data | Blockchain.com / mempool |
| 8 | **S6 Donchian member** | 50-day-high entry / 20-day-low exit, as a fourth vote in #1 | Different shape of trend signal (breakout vs average) | OHLCV |

**Explicit skips:** halving timing, weekday/session effects, Stock-to-Flow, Pi Cycle, Fear & Greed, ETF flows, funding/OI timing, Ichimoku/SuperTrend/PSAR/Hull/KAMA (redundant), daily RSI/Bollinger mean reversion as a standalone strategy.

---

## 9. Concrete next-step test plan for the Python system

1. **Data layer (week 1)**
   - Build the hourly composite (median of venues, ≥ 2 live, Mt. Gox excluded) and resample to 00:00 UTC daily bars.
   - Add a `venue_dispersion` column and untradeable flags.
   - Write a `snapshots/` store for external pulls: Coin Metrics (`CapMVRVCur`, `CapMrktCurUSD`, `PriceUSD`), Blockchain.com hash rate.
2. **Engine checks:**
   - Assert there is no same-bar execution.
   - Unit-test that every rolling window excludes the current bar for breakout levels.
   - Apply costs per side at 0.26% (base) and 0.52% (stress), plus 0.05% slippage.
3. **Trials ledger:** a CSV/SQLite table logging strategy, parameters, date, in-sample/out-of-sample Sharpe and notes, with an auto-incremented trial count N that feeds the DSR.
4. **Benchmarks:** buy-and-hold, an exposure-matched static mix, and S1 (SMA100).
5. **Run candidates 1–5** (OHLCV only) through walk-forward (2014–2023) and CPCV. Compute DSR, PBO, SPA versus the exposure-matched mix, break-even cost and capture of the top-20 days.
6. **Add #6–#7** as overlays on the best of 1–3, using 1–2-day lags. Accept only if Calmar improves *and* DSR stays > 0.95 with the increased trial count.
7. **Final holdout:** run the 1–2 survivors once on 2024–2026. If performance degrades by more than ~50% in Sharpe versus walk-forward, assume overfitting.
8. **Paper trade** the survivor for ≥ 3 months, comparing live fills to modelled costs, before committing capital.
9. **Decision rule:** prefer the simplest survivor whose max drawdown is ≤ 55% and that captures ≥ 50% of buy-and-hold CAGR. If none qualifies, the evidence-supported default is **S3 (50% core + trend overlay) or S5 (banded 60/40)**.

---

## 10. Caveats

- **Reproducibility of claims:** several 2025–2026 sources (Howden-Andreev, Habeli et al., Lim, Fabus et al., Inan) are SSRN working papers, not yet peer-reviewed. Grobys et al. is peer-reviewed but has 3 trades per strategy and thresholds that may embed hindsight.
- **Vendor material** (Grayscale, Quantpedia, Nakamoto Portfolio, Amdax, Glassnode/LookIntoBitcoin charts) is descriptive or promotional. On-chain "it called every top" claims are contradicted by the 2025 top: MVRV peaked at only ≈2.3–2.8 depending on the vendor (2.52 per Amberdata, 2.74 per Bitcoin.com), and Amberdata reports NUPL never held above 0.75, ranging from 0.285 to 0.604 in 2025.
- **Not re-verified this pass:** the Glasgow (Wei/Kyriakou), Anghel, Baur et al., Aslanidis et al. and Han-Kang-Ryu findings are carried over from the first pass. So are BitMEX/Deribit funding endpoints, the Farside, CoinGlass, Glassnode and CryptoQuant free-tier terms, and the Blockchain.com history start date.
- **Conflict flagged:** Coin Metrics free metric count (first pass ~147 vs 32 after Oct 2025 per the CryptoMarkets.tools review). Resolve by querying the live catalog.
- **Base rate:** the broad literature (Rink 2023 on equities; Hudson-Urquhart and Anghel on BTC) shows in-sample winners usually fail out-of-sample. Expect most of the shortlist to fail DSR/PBO. That is the method working, not a reason to widen the search.
- Not investment advice. All results are historical and paper-trading-first.