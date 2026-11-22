# AI Trading System
# Development Blueprint: Predictive Market Structure & Scenario Engine

**Document type:** Technical development specification  
**Status:** Proposed – future development  
**Project:** AI_Trading_System  
**Primary language:** Python 3.12  
**Initial database:** SQLite  
**Development philosophy:** Rules-based analysis + machine learning + probabilistic forecasting

---

# 1. Project objective

Develop an analytical subsystem capable of identifying existing and developing market structures, recognising recurring historical price behaviours and generating multiple conditional future price trajectories.

The system must not simply identify whether the market is bullish or bearish.

It must be capable of answering:

1. What is the current market structure?
2. Which technical patterns are developing?
3. What possible future structures could emerge?
4. What price levels and conditions would support each scenario?
5. What would invalidate each scenario?
6. How frequently have similar historical situations produced each outcome?
7. How reliable are the resulting probabilities?
8. How does the assessment change when new market data arrives?

The system should operate continuously and update its analysis whenever new market data becomes available.

**Core principle: The engine must forecast possible market developments, not merely describe historical price movements.**

# 2. Position within the existing AI Trading System

The Predictive Market Structure Engine will be an independent subsystem within the existing AI_Trading_System project.

It will reuse the existing:
- Market data collection infrastructure.
- Historical exchange data.
- Database.
- Data processing functionality.
- Configuration and logging infrastructure.

It must not duplicate existing functionality unnecessarily.

## Proposed architecture

AI_Trading_System/

- data/
  - historical/
  - market/
- database/
- src/
  - data_collection/
  - analysis/
  - predictive_engine/
    - market_structure/
    - pattern_recognition/
    - fibonacci/
    - elliott_wave/
    - volume_analysis/
    - historical_similarity/
    - scenario_generation/
    - probability/
    - validation/
  - strategies/
  - risk_management/
  - execution/
- tests/
  - predictive_engine/
- config/
- logs/
- main.py
- requirements.txt
- README.md

The predictive_engine directory is a proposed addition. Existing directories should remain intact.

## Separation of responsibilities

**Data collection:** Retrieves and stores market information.

**Market analysis:** Calculates indicators and objectively measurable market characteristics.

**Predictive engine:** Identifies structures, evaluates possible futures and generates scenarios.

**Strategies:** Determines whether a forecast creates a trade opportunity.

**Risk management:** Determines acceptable exposure and trading risk.

**Execution:** Handles paper trading initially and potentially live trading in a much later development phase.

The predictive engine must not execute trades directly.

# 3. Market data requirements

The predictive engine depends on reliable historical and live data.

## 3.1 Required market information

Minimum data:

- Timestamp.
- Open.
- High.
- Low.
- Close.
- Volume.
- Exchange.
- Market.
- Trading pair or instrument.
- Timeframe.

Additional data where available:

- Individual trades.
- Trade direction (buyer/seller initiated).
- Bid/ask spread.
- Order book depth.
- Funding rates for applicable crypto derivatives.
- Open interest.
- Exchange-specific volume information.

The engine must distinguish between unavailable data and data containing zero values.

## 3.2 Timeframes

The initial analytical framework should support:

| Timeframe | Purpose |
|---|---|
| 1D | Long-term market structure |
| 4H | Intermediate market structure |
| 1H | Setup identification |
| 15M | Entry refinement |

Additional timeframes can be introduced later.

All timeframes must use consistent timestamps and correctly aligned candles.

Higher-timeframe candles must never expose information that was not yet available at the time of analysis.

## 3.3 Data quality

Before analysis, data must pass validation:

- No duplicate candles.
- Chronological ordering.
- Valid OHLC relationships.
- Valid timestamps.
- Correct timeframe alignment.
- Missing candle detection.
- Volume validation.
- Exchange and instrument identification.

Incomplete data must be flagged.

The engine must not silently interpret missing candles as periods of zero trading activity.

# 4. Analytical engine 1: Market Structure Recognition

This is the foundation of the entire predictive system.

The engine must identify the current state of the market without relying on subjective chart interpretation.

## 4.1 Swing detection

Identify:

- Swing highs.
- Swing lows.
- Major swing highs and lows.
- Minor swing highs and lows.

Use configurable pivot detection.

A pivot high is identified when its high exceeds the highs of a defined number of surrounding candles.

A pivot low is identified when its low is below the lows of a defined number of surrounding candles.

Important: A pivot requiring future candles for confirmation cannot be considered confirmed before those candles have closed.

Store:
- Pivot price.
- Timestamp of the pivot.
- Confirmation timestamp.
- Pivot classification.
- Timeframe.

## 4.2 Trend classification

Classify market structure into:

- Bullish: higher highs and higher lows.
- Bearish: lower highs and lower lows.
- Sideways: no consistent directional structure.
- Transitioning: potential change in market direction.

The engine should distinguish between local trends and higher-timeframe trends.

For example, a bearish 1H correction can exist within a bullish 4H structure.

## 4.3 Structural events

Recognise:

**Break of Structure (BOS)**

Price breaks an established structural high or low in the direction of the prevailing trend.

**Change of Character (CHoCH)**

Price breaks a relevant structural level against the previously established trend, potentially indicating a transition.

**Liquidity sweep**

Price moves beyond a previously established high or low but subsequently returns inside the relevant range.

**Support and resistance**

Identify relevant price zones using:
- Historical swing points.
- Repeated price reactions.
- Volume-profile levels.
- Previous consolidation boundaries.

Zones should have configurable tolerance rather than requiring exact price equality.

## 4.4 Market regime classification

Classify the broader market environment:

- Trending upward.
- Trending downward.
- Ranging.
- High volatility.
- Low volatility.
- Volatility expansion.
- Volatility contraction.

Possible inputs:
- ADX.
- ATR.
- Moving-average slope.
- Price structure.
- Realised volatility.
- Volume behaviour.

The regime classification will later influence scenario probabilities.

Deliverable: A continuously updated and historically reproducible market structure representation.

# 5. Analytical engine 2: Classical Pattern Recognition

The system must recognise both completed patterns and developing patterns.

It must not require a pattern to be fully confirmed before generating potential future scenarios.

## 5.1 Initial pattern library

**Reversal patterns**
- Head and shoulders.
- Inverse head and shoulders.
- Double top.
- Double bottom.
- Triple top.
- Triple bottom.

**Continuation patterns**
- Bull flag.
- Bear flag.
- Pennant.
- Ascending triangle.
- Descending triangle.
- Symmetrical triangle.

**Other patterns**
- Cup and handle.
- Inverse cup and handle.
- Rising wedge.
- Falling wedge.
- Broadening formation.
- Rectangle consolidation.

## 5.2 Pattern recognition rules

Each pattern requires its own mathematical definition.

For example, inverse head and shoulders:

1. Identify three relevant swing lows.
2. The middle low must be lower than the surrounding lows.
3. Identify the two neckline reaction highs.
4. Measure shoulder symmetry.
5. Measure neckline slope.
6. Identify potential right-shoulder development.
7. Calculate neckline breakout level.
8. Define invalidation below the head.

Use configurable tolerances for:
- Price differences.
- Time differences.
- Pattern symmetry.
- Neckline slope.
- Minimum pattern duration.

Do not require textbook-perfect patterns.

## 5.3 Developing pattern recognition

The engine should support pattern states:

- Candidate.
- Developing.
- Near completion.
- Confirmed.
- Invalidated.
- Expired.

A developing pattern may generate multiple scenarios before confirmation.

For example:

An ascending triangle could produce:
- Bullish breakout.
- Bearish breakdown.
- Continued consolidation.
- Failed breakout followed by reversal.

Each possibility must have its own conditions and invalidation levels.

Deliverable: Pattern identification with measurable characteristics and explicit lifecycle states.

# 6. Analytical engine 3: Fibonacci Analysis

Fibonacci analysis provides additional structural information.

It should never function as an independent trading signal.

## 6.1 Retracement levels

Initially support:

- 0.236
- 0.382
- 0.500
- 0.618
- 0.786

## 6.2 Extension levels

Initially support:

- 1.272
- 1.414
- 1.618
- 2.000
- 2.618

## 6.3 Automated application

The engine should:

1. Identify relevant confirmed swing highs and lows.
2. Determine the direction of the impulse.
3. Calculate retracement levels.
4. Calculate extension targets.
5. Compare levels against support and resistance.
6. Identify overlapping Fibonacci zones.
7. Record historical reactions around comparable levels.

## 6.4 Fibonacci confluence

A Fibonacci level becomes more interesting when it overlaps with other independent evidence.

For example:

- 0.618 retracement.
- Previous support.
- High-volume node.
- Potential Elliott Wave 2 completion.
- Higher-timeframe demand zone.

The engine should calculate the degree of confluence.

It must avoid counting the same underlying price information multiple times as independent confirmation.

Deliverable: Automated Fibonacci mapping and confluence analysis.

# 7. Analytical engine 4: Elliott Wave Recognition

Elliott Wave analysis should be introduced after reliable swing and market structure detection.

It is inherently more subjective than many other technical-analysis concepts.

The system must support alternative wave counts rather than forcing one interpretation.

## 7.1 Initial wave structures

Impulse waves:

- Wave 1.
- Wave 2.
- Wave 3.
- Wave 4.
- Wave 5.

Corrective waves:

- A.
- B.
- C.

Later extensions:

- Diagonal structures.
- Zigzag corrections.
- Flat corrections.
- Triangles.
- Complex corrections.

## 7.2 Rule validation

The system must check established Elliott Wave rules.

For a standard impulse:

1. Wave 2 cannot retrace beyond the origin of Wave 1.
2. Wave 3 cannot be the shortest of Waves 1, 3 and 5.
3. Wave 4 cannot overlap Wave 1 territory in a standard impulse, subject to the relevant structure exceptions.

Additional evaluation:
- Fibonacci relationships.
- Wave proportionality.
- Duration.
- Momentum.
- Volume.
- Higher-timeframe context.

## 7.3 Alternative counts

The engine may maintain multiple possible wave counts.

Each count receives:
- A structural validity status.
- A score.
- Supporting evidence.
- Invalidation level.
- Potential next-wave targets.

An invalid wave count must be discarded.

A lower-confidence but still valid alternative should remain available.

Deliverable: Multiple candidate Elliott Wave interpretations with explicit rule validation.

# 8. Analytical engine 5: Volume Analysis

Volume should be used to evaluate whether price movements have meaningful participation behind them.

## 8.1 Volume profile

Initially support:

- Point of Control (POC).
- Value Area High (VAH).
- Value Area Low (VAL).
- High Volume Nodes (HVN).
- Low Volume Nodes (LVN).

Calculate profiles over configurable periods.

Where possible, use trade-level data to improve price-level volume distribution.

OHLCV-based approximations must be identified as approximations, not true traded-volume profiles.

## 8.2 Additional volume characteristics

Recognise:

- Increasing volume during breakouts.
- Declining volume during retracements.
- Volume contraction during consolidation.
- Volume expansion during volatility expansion.
- High-volume rejection.
- Potential accumulation and distribution characteristics.

## 8.3 Volume confirmation

A breakout should receive stronger support when:
- Price closes beyond a relevant structural level.
- Volume exceeds an appropriate historical baseline.
- Subsequent candles maintain acceptance beyond the level.

A breakout without volume confirmation should not automatically be considered invalid, but its evidence score should differ.

Deliverable: Volume context integrated into pattern and scenario evaluation.

# 9. Analytical engine 6: Historical Analogue Matching

This is one of the most important components.

The system should search historical data for situations resembling the current market environment.

## 9.1 Historical feature representation

Represent every eligible historical market situation using measurable features:

- Market regime.
- Trend direction.
- Swing structure.
- Recent price returns.
- ATR and volatility.
- Volume characteristics.
- Fibonacci relationships.
- Distance to support and resistance.
- Pattern characteristics.
- Higher-timeframe structure.

## 9.2 Similarity calculation

Compare the current market situation against historical examples.

Possible methods:
- Normalised feature distance.
- K-nearest neighbours.
- Dynamic Time Warping for suitable price sequences.
- Clustering.
- Gradient-boosted models.

Initially favour simpler, interpretable approaches.

## 9.3 Historical outcome analysis

For each comparable situation, investigate what happened afterwards.

Classify outcomes:

- Bullish continuation.
- Bearish continuation.
- Bullish reversal.
- Bearish reversal.
- Continued consolidation.
- Failed breakout.
- Failed breakdown.

Measure:
- Maximum favourable excursion (MFE).
- Maximum adverse excursion (MAE).
- Time to target.
- Time to invalidation.
- Realised volatility.
- Outcome frequency.

Historical examples must only use information that was available at their respective prediction timestamps.

## 9.4 Market regime filtering

Historical comparisons should consider the market environment.

A bullish setup during a strong bull market should not automatically be treated as equivalent to the same setup during a prolonged bear market.

Deliverable: Historical similarity analysis with outcome distributions.

# 10. Analytical engine 7: Scenario Generation

This is the central component of the predictive system.

It combines information from the previous analytical engines to construct possible future trajectories.

## 10.1 Scenario requirements

At least three broad scenario categories should be considered:

1. Bullish.
2. Bearish.
3. Neutral or consolidation.

More detailed scenarios may be generated where justified.

The system must not artificially generate three scenarios if the evidence only supports one or two meaningful possibilities.

## 10.2 Scenario structure

Every scenario must contain:

- Unique scenario ID.
- Instrument.
- Exchange.
- Creation timestamp.
- Current reference price.
- Direction.
- Market regime.
- Supporting patterns.
- Supporting technical evidence.
- Projected trajectory.
- Potential target zones.
- Intermediate checkpoints.
- Entry conditions, if applicable.
- Invalidation conditions.
- Estimated time horizon.
- Confidence score.
- Estimated probability.
- Current status.

## 10.3 Example: bullish continuation

Conditions:

1. Existing higher-timeframe structure remains bullish.
2. Price retraces into a relevant support zone.
3. Retracement volume declines.
4. A higher low develops.
5. Price breaks the local resistance level.
6. Breakout volume confirms participation.

Potential trajectory:

- Support reaction.
- Higher-low formation.
- Local resistance breakout.
- Retest.
- Continuation toward the next structural target.

Invalidation:

A confirmed structural break below the relevant support or swing low.

## 10.4 Example: bearish reversal

Conditions:

1. Price rejects a significant resistance zone.
2. A lower high develops.
3. Bullish momentum weakens.
4. Relevant support breaks.
5. Selling volume confirms participation.

Potential trajectory:

- Resistance rejection.
- Lower-high formation.
- Support breakdown.
- Retest from below.
- Continuation toward the next demand region.

Invalidation:

A confirmed reclaim of the relevant resistance structure.

## 10.5 Conditional decision trees

Scenarios must be allowed to branch.

For example:

- If support holds, monitor bullish continuation.
- If support breaks, increase bearish scenario relevance.
- If neither occurs, maintain consolidation scenario.

The system must recalculate scenarios when important conditions change.

## 10.6 Trajectory representation

Do not represent every future scenario as a single straight line.

A trajectory should contain:
- Ordered price checkpoints.
- Expected zones.
- Alternative paths.
- Time windows.
- Conditions between checkpoints.

Where sufficient historical evidence exists, display uncertainty bands around projected prices.

Deliverable: Multiple simultaneous, conditional future trajectories.

# 11. Analytical engine 8: Probability and Confidence Evaluation

Probability estimation must be treated as a separate discipline.

A technical pattern score is not automatically a probability.

## 11.1 Evidence scoring

Each scenario receives evidence from different categories:

| Category | Initial weight |
|---|---:|
| Market structure | 25% |
| Classical patterns | 15% |
| Fibonacci | 10% |
| Elliott Wave | 10% |
| Volume analysis | 15% |
| Historical analogues | 25% |
| Total | 100% |

These are proposed starting weights for an experimental scoring model, not validated optimal weights.

They must eventually be tested and adjusted.

## 11.2 Probability estimation

Use historical outcomes and a statistical model to estimate scenario probabilities.

Potential approaches:
- Logistic regression.
- Gradient-boosted classification.
- Random forest.
- Calibrated ensemble models.

The model should account for:
- Market regime.
- Timeframe.
- Volatility.
- Pattern maturity.
- Historical similarity.
- Relevant technical conditions.

## 11.3 Probability calibration

Evaluate whether predicted probabilities match actual outcomes.

For example:

If 100 comparable scenarios each receive a 70% probability, approximately 70 should succeed over a sufficiently large and representative sample.

Use:
- Reliability diagrams.
- Brier score.
- Log loss.
- Calibration error.

Do not present uncalibrated model scores as reliable probabilities.

## 11.4 Scenario competition

Probabilities should be evaluated as a coherent distribution where outcomes are mutually exclusive over a defined forecast horizon.

Where scenarios overlap or branch conditionally, use conditional probabilities rather than incorrectly adding overlapping probabilities together.

## 11.5 Confidence versus probability

Display these separately:

- Evidence strength: how much supporting information exists.
- Probability: estimated likelihood of the defined outcome.
- Data quality: how reliable the underlying data is.

A scenario can have a high estimated probability but weak supporting evidence, particularly when historical samples are limited.

Deliverable: Statistically evaluated and calibrated scenario probabilities.

# 12. Machine Learning Integration

Machine learning should complement deterministic technical analysis.

It should not replace basic mathematical rules.

## 12.1 Initial approach

Start with:
- Rule-based pattern recognition.
- Historical similarity matching.
- Logistic regression.
- Gradient-boosted trees.

## 12.2 Future development

Potential additions:
- Clustering of market regimes.
- Sequence models.
- Neural networks.
- Time-series representation learning.
- Computer vision for chart-pattern discovery.

AI models should identify relationships that are difficult to define through explicit rules.

## 12.3 Training requirements

Training data must contain:
- Historical market features.
- Prediction timestamps.
- Future outcome labels.
- Market regime.
- Instrument.
- Timeframe.

Training and testing must be chronologically separated.

Randomly splitting overlapping financial time-series observations is not acceptable.

Use walk-forward validation and appropriate purging or embargoes when samples overlap.

## 12.4 Model monitoring

Monitor:
- Prediction accuracy.
- Probability calibration.
- Performance by market regime.
- Performance by instrument.
- Performance by timeframe.
- Changes in feature distributions.
- Model degradation.

A model that stops performing reliably must be flagged and potentially retrained.

# 13. Historical Backtesting and Validation

This phase is mandatory before using forecasts for automated trading.

## 13.1 No look-ahead bias

The system must only use information available at the prediction timestamp.

Examples of prohibited behaviour:

- Using future candles to confirm historical swing points.
- Drawing patterns retrospectively without recording when they became identifiable.
- Using future volume information.
- Recalculating historical predictions using later information.

## 13.2 Immutable predictions

Every forecast must be recorded when generated.

Historical forecasts must never be overwritten by later recalculations.

Store:
- Prediction timestamp.
- Input data timestamp.
- Scenario details.
- Estimated probabilities.
- Model version.
- Rule version.
- Subsequent outcome.

## 13.3 Evaluation metrics

Measure:

**Forecast quality**
- Directional accuracy.
- Brier score.
- Log loss.
- Calibration.

**Price trajectory quality**
- Target hit rate.
- Invalidation rate.
- Maximum favourable excursion.
- Maximum adverse excursion.
- Forecast error.
- Time to target.

**Trading usefulness**
- Win rate.
- Profit factor.
- Expectancy.
- Maximum drawdown.
- Risk-adjusted returns.
- Fees and slippage.

A system that predicts direction correctly but produces poor risk/reward opportunities is not necessarily a useful trading system.

# 14. Visualisation and TradingView Integration

The predictive engine should initially produce structured outputs independently of any charting platform.

Future visualisation options:

- TradingView.
- Custom Python dashboard.
- Web-based chart interface.

## 14.1 Chart requirements

Display:
- Actual price history.
- Confirmed market structure.
- Developing patterns.
- Support and resistance zones.
- Fibonacci levels.
- Volume profile.
- Projected scenarios.
- Target zones.
- Invalidation levels.

## 14.2 Scenario presentation

Use distinguishable colours:

- Green: bullish.
- Red: bearish.
- Grey: neutral.
- Dashed lines: conditional trajectories.
- Solid lines: confirmed historical price structure.

Display probabilities and evidence strength separately.

## 14.3 Historical replay

Allow historical forecasts to be inspected as they existed at the time.

This is essential for identifying repainting and evaluating whether the system genuinely provides forward-looking information.

# 15. Integration with the Trading Strategy Engine

The Predictive Market Structure Engine provides analysis, not direct trading decisions.

The strategy engine can consume its outputs.

Example:

A strategy may require:

- Bullish scenario probability above a tested threshold.
- Higher-timeframe bullish structure.
- Confirmed local breakout.
- Acceptable distance to invalidation.
- Sufficient projected reward relative to risk.
- No conflicting risk-management restrictions.

Only then may it consider creating a trade signal.

The threshold must be determined through testing rather than arbitrarily selecting a percentage.

The risk-management engine remains responsible for:
- Position sizing.
- Maximum exposure.
- Stop-loss rules.
- Daily loss limits.
- Portfolio risk.

The predictive engine must never bypass these restrictions.

# 16. Development Roadmap

Development should follow this sequence.

| Phase | Development | Priority |
|---|---|---|
| 0 | Complete and validate existing data foundation | Mandatory |
| 1 | Market structure recognition | Very high |
| 2 | Classical pattern recognition | Very high |
| 3 | Fibonacci analysis | High |
| 4 | Volume analysis | High |
| 5 | Elliott Wave recognition | Medium |
| 6 | Historical analogue matching | Very high |
| 7 | Scenario generation | Very high |
| 8 | Probability modelling | Very high |
| 9 | Backtesting and calibration | Mandatory |
| 10 | Visualisation | Medium |
| 11 | Integration with strategies | Later |
| 12 | Continuous model improvement | Ongoing |

The phases should be implemented incrementally.

Each phase must have working code, tests and validation before the next phase introduces additional complexity.

# 17. Initial Technical Principles

The following rules apply throughout development.

1. Python remains the primary analytical environment.
2. Existing project architecture should be reused.
3. Deterministic calculations should be preferred wherever possible.
4. AI should complement rather than replace explicit technical rules.
5. Multiple future scenarios must be supported.
6. Developing patterns must be recognised before completion where measurable evidence allows.
7. No repainting or look-ahead bias.
8. Historical forecasts must remain immutable.
9. Probabilities must be empirically calibrated.
10. Market regimes must be considered.
11. All analytical components must be independently testable.
12. The system must support different instruments and exchanges.
13. No direct trade execution from the predictive engine.
14. Paper trading and historical validation must precede live deployment.
15. Complexity must be justified by measurable improvements.

# 18. Initial Scope and Exclusions

The first implementation should concentrate on:

- Cryptocurrency.
- Historical OHLCV data.
- Multi-timeframe market structure.
- Classical patterns.
- Fibonacci analysis.
- Volume analysis.
- Multiple conditional scenarios.
- Historical validation.

Stocks and forex should be supported architecturally, but additional data-source and market-specific validation will be required.

Do not initially attempt to implement:

- Every possible Elliott Wave structure.
- Complex deep-learning models.
- Autonomous AI interpretation of every chart.
- Full order-book prediction.
- High-frequency trading.
- Direct automated execution.
- An elaborate TradingView interface before the analytical engine is validated.

These are potential future extensions.

# 19. Definition of Success

The Predictive Market Structure Engine can be considered an initial success when it can:

1. Reliably identify market structure using historical and live data.
2. Recognise developing and completed patterns.
3. Generate multiple plausible future scenarios.
4. Define measurable conditions for each scenario.
5. Identify target and invalidation levels.
6. Estimate probabilities using historical evidence.
7. Demonstrate calibrated forecasting performance on unseen data.
8. Produce immutable, non-repainting historical predictions.
9. Demonstrate measurable value after realistic trading costs.
10. Deliver structured information to the existing strategy engine.

The objective is not to achieve perfect predictions.

The objective is to establish a repeatable analytical process that provides a measurable statistical advantage over relying on conventional reactive indicators alone.

---

# 20. Long-Term Vision

The eventual AI Trading System should combine:

- Market data collection.
- Market structure analysis.
- Technical pattern recognition.
- Historical market behaviour.
- Probabilistic scenario forecasting.
- Strategy evaluation.
- Portfolio risk management.
- Automated paper trading.
- Eventually, controlled live trading.

The Predictive Market Structure Engine will serve as one of the primary analytical components.

**Final guiding principle:**

Do not ask the system to tell us where the market will go.

Ask it to identify the most plausible paths, calculate the evidence supporting each path, define what must happen next, and recognise immediately when the market proves a scenario wrong.