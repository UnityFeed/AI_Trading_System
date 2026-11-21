"""
Builds the dashboard: one self-contained HTML file (no internet needed)
that shows the data status, the market now, what the strategy says, the
paper-trading account and where to work from next.

Everything is read-only: the market database and the paper-trading
database are only read here.
"""

import html
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.analysis.primary_history import ContinuousHistory
from src.analysis.technical_indicators import IndicatorTable, indicator_tables
from src.backtesting.conditions import evaluate_all
from src.backtesting.market import build_market
from src.data_collection.market_data_repository import MarketDataRepository
from src.paper_trading.store import PaperTradingStore
from src.paper_trading.trader import ACTIVE_STRATEGY, ACTIVE_TIMEFRAME, KILL_SWITCH


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExchangeStatus:
    exchange: str
    candles: int
    first: datetime
    latest: datetime
    lag_hours: int

    @property
    def status(self) -> tuple[str, str]:
        if self.lag_hours <= 2:
            return "good", "Up to date"
        if self.lag_hours <= 24:
            return "warning", f"{self.lag_hours} h behind"
        return "critical", f"{self.lag_hours // 24} days behind"


def exchange_status(repository: MarketDataRepository, now: datetime) -> list[ExchangeStatus]:
    expected_latest = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    with closing(sqlite3.connect(repository.db_path)) as connection:
        rows = connection.execute("""
            SELECT exchange, COUNT(*), MIN(timestamp), MAX(timestamp)
            FROM market_candles
            WHERE symbol = 'BTC/USD' AND market = 'crypto' AND timeframe = '1h'
            GROUP BY exchange ORDER BY exchange
        """).fetchall()
    result = []
    for exchange, count, first, latest in rows:
        latest_dt = datetime.fromisoformat(latest)
        lag = max(0, int((expected_latest - latest_dt) / timedelta(hours=1)))
        result.append(ExchangeStatus(exchange, count, datetime.fromisoformat(first), latest_dt, lag))
    return result


def market_reading(values: dict, close: float) -> list[tuple[str, str, str]]:
    """Plain-language reading of the latest indicator values: (topic, verdict, detail)."""

    def v(name):
        return values.get(name)

    readings = []
    e50, e200 = v("ema_50"), v("ema_200")
    if e50 is not None and e200 is not None:
        up = e50 > e200
        readings.append((
            "Long trend", "Up" if up else "Down",
            f"EMA 50 {fmt_price(e50)} is {'above' if up else 'below'} EMA 200 {fmt_price(e200)}",
        ))
    if e200 is not None:
        above = close > e200
        readings.append((
            "Price vs EMA 200", "Above" if above else "Below",
            f"close {fmt_price(close)} is {abs(close / e200 - 1) * 100:.1f}% "
            f"{'above' if above else 'below'} the EMA 200",
        ))
    m, s = v("macd"), v("macd_signal")
    if m is not None and s is not None:
        readings.append((
            "Momentum (MACD)", "Rising" if m > s else "Falling",
            f"MACD {m:,.1f} vs signal {s:,.1f}",
        ))
    rsi = v("rsi_14")
    if rsi is not None:
        zone = "Oversold" if rsi < 30 else "Overbought" if rsi > 70 else "Neutral"
        readings.append(("RSI 14", zone, f"{rsi:.1f} (below 30 oversold, above 70 overbought)"))
    upper, lower = v("bb_upper"), v("bb_lower")
    if upper is not None and lower is not None and upper > lower:
        position = (close - lower) / (upper - lower) * 100
        readings.append((
            "Bollinger position", f"{position:.0f}%",
            f"0% = lower band {fmt_price(lower)}, 100% = upper band {fmt_price(upper)}",
        ))
    atr = v("atr_14")
    if atr is not None:
        readings.append(("Volatility (ATR 14)", f"{atr / close * 100:.1f}%", f"{fmt_price(atr)} per candle"))
    rv = v("relative_volume_20")
    if rv is not None:
        readings.append(("Relative volume", f"{rv:.2f}x", "volume vs the average of the previous 20 candles"))
    return readings


@dataclass
class DashboardData:
    generated_at: datetime
    exchanges: list[ExchangeStatus]
    history: ContinuousHistory
    latest_rows: dict  # timeframe -> IndicatorRow
    daily_rows: list  # indicator rows of the 1d timeframe
    strategy_rules: dict  # rule label -> bool, at the latest daily candle
    account: object | None
    decisions: list
    fills: list
    equity: list[tuple[datetime, float, float]]  # (time, account value, buy-and-hold value)
    kill_switch_on: bool


def account_equity(account, fills, daily_candles) -> list[tuple[datetime, float, float]]:
    """Account value and buy-and-hold value at every daily close since the start."""

    if account is None:
        return []
    candles = [c for c in daily_candles if c.timestamp >= account.start_candle]
    if not candles:
        return []
    bh_btc = account.starting_cash / candles[0].open
    cash, btc = account.starting_cash, 0.0
    pending = list(fills)
    points = []
    for candle in candles:
        close_time = candle.timestamp + timedelta(days=1)
        while pending and pending[0].filled_at < close_time:
            fill = pending.pop(0)
            cash, btc = fill.cash_after, fill.btc_after
        points.append((candle.timestamp, cash + btc * candle.close, bh_btc * candle.close))
    return points


def gather(
    repository: MarketDataRepository,
    history: ContinuousHistory,
    store: PaperTradingStore,
    now: datetime | None = None,
    tables: dict[str, IndicatorTable] | None = None,
) -> DashboardData:
    """`tables` (from indicator_tables) skips recomputing the indicators."""

    now = now or datetime.now(timezone.utc)
    tables = tables or indicator_tables(history.candles)
    latest_rows = {}
    daily_rows = []
    for timeframe in ("1h", "4h", "1d"):
        candles, rows = tables[timeframe]
        if rows:
            latest_rows[timeframe] = rows[-1]
        if timeframe == "1d":
            daily_rows = rows
            daily_candles = candles

    market = build_market(history, ACTIVE_TIMEFRAME, table=tables.get(ACTIVE_TIMEFRAME))
    blocks = evaluate_all(market)
    i = len(market.candles) - 1
    spec = ACTIVE_STRATEGY
    rules = {}
    if i >= 0:
        rules = {
            f"Trend filter: {spec.trend}": blocks["trend"][spec.trend][i],
            f"Buy trigger: {spec.trigger}": blocks["trigger"][spec.trigger][i],
            f"Sell rule: {spec.exit}": blocks["exit"][spec.exit][i],
        }

    account = store.get_account()
    fills = store.fills()
    return DashboardData(
        generated_at=now,
        exchanges=exchange_status(repository, now),
        history=history,
        latest_rows=latest_rows,
        daily_rows=daily_rows,
        strategy_rules=rules,
        account=account,
        decisions=store.decisions(limit=30),
        fills=fills,
        equity=account_equity(account, fills, daily_candles if daily_rows else []),
        kill_switch_on=KILL_SWITCH.exists(),
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_price(value: float | None) -> str:
    return "-" if value is None else f"${value:,.2f}"


def fmt_pct(value: float) -> str:
    return f"{value:+.1f}%"


def esc(value) -> str:
    return html.escape(str(value))


STATUS_ICON = {"good": "&#10003;", "warning": "!", "serious": "!", "critical": "&#10005;", "neutral": "&#8211;"}


def status_badge(kind: str, label: str) -> str:
    return (
        f'<span class="badge {kind}"><span class="badge-icon" aria-hidden="true">'
        f"{STATUS_ICON[kind]}</span>{esc(label)}</span>"
    )


# ---------------------------------------------------------------------------
# Charts (inline SVG, one y-axis, hover readout added by the page script)
# ---------------------------------------------------------------------------

def nice_ticks(low: float, high: float, count: int = 5) -> list[float]:
    if high <= low:
        return [low]
    raw = (high - low) / count
    magnitude = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1
    for step in (1, 2, 2.5, 5, 10):
        if raw <= step * magnitude:
            step *= magnitude
            break
    start = (low // step) * step
    ticks = []
    value = start
    while value <= high + step * 0.001:
        if value >= low - step * 0.001:
            ticks.append(value)
        value += step
    return ticks


def line_chart(chart_id: str, title: str, series: list[dict], markers=(), y_label=fmt_price) -> str:
    """
    series: [{"name", "color" (CSS var), "points": [(datetime, value | None)]}]
    markers: [(datetime, value, "buy" | "sell")]
    """

    width, height = 960, 300
    left, right, top, bottom = 72, 110, 16, 28
    times = [t for t, _ in series[0]["points"]]
    if len(times) < 2:
        return f'<p class="muted">Not enough data for “{esc(title)}” yet.</p>'

    values = [v for s in series for _, v in s["points"] if v is not None]
    low, high = min(values), max(values)
    pad = (high - low) * 0.06 or 1
    low, high = low - pad, high + pad
    t0, t1 = times[0].timestamp(), times[-1].timestamp()

    def x(t):
        return left + (t.timestamp() - t0) / (t1 - t0) * (width - left - right)

    def y(v):
        return top + (high - v) / (high - low) * (height - top - bottom)

    parts = [
        f'<svg id="{chart_id}" class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{esc(title)}" preserveAspectRatio="none">'
    ]
    for tick in nice_ticks(low, high):
        ty = y(tick)
        parts.append(f'<line class="grid" x1="{left}" x2="{width - right}" y1="{ty:.1f}" y2="{ty:.1f}"/>')
        parts.append(f'<text class="axis" x="{left - 8}" y="{ty + 4:.1f}" text-anchor="end">{esc(y_label(tick).replace(".00", ""))}</text>')

    # Month/year labels along the bottom (about six).
    step = max(1, len(times) // 6)
    for t in times[::step]:
        parts.append(f'<text class="axis" x="{x(t):.1f}" y="{height - 8}" text-anchor="middle">{t:%b %Y}</text>')

    labels = []
    for s in series:
        path = []
        for t, v in s["points"]:
            if v is None:
                continue
            path.append(f"{'M' if not path else 'L'}{x(t):.1f},{y(v):.1f}")
        parts.append(f'<path d="{" ".join(path)}" fill="none" stroke="var({s["color"]})" stroke-width="2" stroke-linejoin="round"/>')
        last = next(((t, v) for t, v in reversed(s["points"]) if v is not None), None)
        if last and len(series) <= 4:
            labels.append([y(last[1]) + 4, x(last[0]) + 8, s["name"]])

    # Keep direct labels at least 15px apart so they never overlap.
    labels.sort()
    for a, b in zip(labels, labels[1:]):
        if b[0] - a[0] < 15:
            b[0] = a[0] + 15
    for label_y, label_x, name in labels:
        parts.append(f'<text class="direct-label" x="{label_x:.1f}" y="{label_y:.1f}">{esc(name)}</text>')

    for t, v, kind in markers:
        if not (times[0] <= t <= times[-1]):
            continue
        cx, cy = x(t), y(v)
        if kind == "buy":
            pts = f"{cx:.1f},{cy - 7:.1f} {cx - 6:.1f},{cy + 5:.1f} {cx + 6:.1f},{cy + 5:.1f}"
        else:
            pts = f"{cx:.1f},{cy + 7:.1f} {cx - 6:.1f},{cy - 5:.1f} {cx + 6:.1f},{cy - 5:.1f}"
        parts.append(f'<polygon class="marker" points="{pts}"><title>{kind.upper()} {t:%Y-%m-%d} {fmt_price(v)}</title></polygon>')

    parts.append(f'<line class="crosshair" x1="0" x2="0" y1="{top}" y2="{height - bottom}" visibility="hidden"/>')
    parts.append(f'<rect class="hit" x="{left}" y="{top}" width="{width - left - right}" height="{height - top - bottom}"/>')
    parts.append("</svg>")

    data = {
        "x0": left, "x1": width - left - right, "width": width,
        "times": [t.strftime("%Y-%m-%d") for t in times],
        "series": [
            {"name": s["name"], "color": s["color"], "values": [None if v is None else round(v, 2) for _, v in s["points"]]}
            for s in series
        ],
    }
    legend = "".join(
        f'<span class="legend-item"><span class="legend-key" style="background:var({s["color"]})"></span>{esc(s["name"])}</span>'
        for s in series
    )
    if markers:
        legend += '<span class="legend-item">&#9650; buy &#9660; sell</span>'
    return (
        f'<figure class="chart-wrap"><figcaption class="chart-title">{esc(title)}</figcaption>'
        f'<div class="legend">{legend}</div><div class="chart-box">{"".join(parts)}'
        f'<div class="tooltip" hidden></div></div>'
        f'<script type="application/json" data-chart="{chart_id}">{json.dumps(data)}</script></figure>'
    )


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

CSS = """
:root { color-scheme: light;
  --surface: #fcfcfb; --card: #ffffff; --border: #e4e3df;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #6f6e69;
  --grid: #ecebe7; --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a;
  --good: #0ca30c; --warning: #fab219; --serious: #ec835a; --critical: #d03b3b; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --surface: #1a1a19; --card: #222221; --border: #383835;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #9a998f;
  --grid: #2e2e2c; --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; } }
:root[data-theme="dark"] { color-scheme: dark;
  --surface: #1a1a19; --card: #222221; --border: #383835;
  --text-primary: #f0efec; --text-secondary: #c3c2b7; --text-muted: #9a998f;
  --grid: #2e2e2c; --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; }
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface); color: var(--text-primary);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; } h2 { font-size: 19px; margin: 36px 0 12px; }
.muted { color: var(--text-muted); } .secondary { color: var(--text-secondary); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.card .label { color: var(--text-secondary); font-size: 13px; }
.card .value { font-size: 24px; font-weight: 650; font-variant-numeric: tabular-nums; }
.card .sub { color: var(--text-muted); font-size: 13px; }
table { width: 100%; border-collapse: collapse; background: var(--card);
  border: 1px solid var(--border); border-radius: 10px; overflow: hidden; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--text-secondary); font-weight: 600; font-size: 13px; }
tr:last-child td { border-bottom: none; }
.table-scroll { overflow-x: auto; }
.badge { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; }
.badge-icon { display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%;
  color: #fff; font-size: 11px; }
.badge.good .badge-icon { background: var(--good); } .badge.warning .badge-icon { background: var(--warning); color: #000; }
.badge.serious .badge-icon { background: var(--serious); } .badge.neutral .badge-icon { background: var(--text-muted); } .badge.critical .badge-icon { background: var(--critical); }
.chart-wrap { margin: 0; background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.chart-title { font-weight: 600; margin-bottom: 4px; }
.legend { display: flex; flex-wrap: wrap; gap: 16px; color: var(--text-secondary); font-size: 13px; margin-bottom: 6px; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.legend-key { width: 16px; height: 3px; border-radius: 2px; display: inline-block; }
.chart-box { position: relative; }
.chart { width: 100%; height: 300px; display: block; }
.chart .grid { stroke: var(--grid); stroke-width: 1; }
.chart .axis { fill: var(--text-muted); font-size: 11px; }
.chart .direct-label { fill: var(--text-secondary); font-size: 12px; }
.chart .marker { fill: var(--text-primary); stroke: var(--card); stroke-width: 2; }
.chart .crosshair { stroke: var(--text-muted); stroke-width: 1; }
.chart .hit { fill: transparent; }
.tooltip { position: absolute; top: 8px; pointer-events: none; background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,.12); min-width: 160px; }
.tooltip .t-row { display: flex; align-items: center; gap: 8px; justify-content: space-between; }
.tooltip .t-key { width: 12px; height: 3px; border-radius: 2px; display: inline-block; margin-right: 6px; }
.tooltip strong { font-variant-numeric: tabular-nums; }
.rules li { list-style: none; margin: 4px 0; } .rules { padding: 0; }
code { background: var(--grid); padding: 1px 6px; border-radius: 4px; font-size: 13px; }
.notice { border-left: 4px solid var(--warning); padding: 8px 12px; background: var(--card); border-radius: 6px; }
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
details summary { cursor: pointer; color: var(--text-secondary); margin: 8px 0; }
"""

SCRIPT = """
document.querySelectorAll('script[data-chart]').forEach(function (node) {
  var data = JSON.parse(node.textContent);
  var svg = document.getElementById(node.dataset.chart);
  var box = svg.parentNode, tip = box.querySelector('.tooltip');
  var hair = svg.querySelector('.crosshair'), hit = svg.querySelector('.hit');
  var n = data.times.length;
  function show(evt) {
    var rect = svg.getBoundingClientRect();
    var vx = (evt.clientX - rect.left) / rect.width * data.width;
    var i = Math.round((vx - data.x0) / data.x1 * (n - 1));
    i = Math.max(0, Math.min(n - 1, i));
    var px = data.x0 + i / (n - 1) * data.x1;
    hair.setAttribute('x1', px); hair.setAttribute('x2', px); hair.setAttribute('visibility', 'visible');
    tip.textContent = '';
    var head = document.createElement('div'); head.className = 'secondary'; head.textContent = data.times[i];
    tip.appendChild(head);
    data.series.forEach(function (s) {
      var v = s.values[i]; if (v === null) return;
      var row = document.createElement('div'); row.className = 't-row';
      var label = document.createElement('span');
      var key = document.createElement('span'); key.className = 't-key'; key.style.background = 'var(' + s.color + ')';
      label.appendChild(key); label.appendChild(document.createTextNode(s.name));
      var val = document.createElement('strong');
      val.textContent = '$' + v.toLocaleString(undefined, {maximumFractionDigits: 2});
      row.appendChild(label); row.appendChild(val); tip.appendChild(row);
    });
    tip.hidden = false;
    var left = (px / data.width) * rect.width + 12;
    if (left + tip.offsetWidth > rect.width) left -= tip.offsetWidth + 24;
    tip.style.left = left + 'px';
  }
  hit.addEventListener('pointermove', show);
  hit.addEventListener('pointerleave', function () { tip.hidden = true; hair.setAttribute('visibility', 'hidden'); });
});
"""


def render(data: DashboardData, nav_html: str = "") -> str:
    """The dashboard page; `nav_html` adds the app's navigation and buttons."""
    out = [nav_html]
    add = out.append
    gen = data.generated_at

    add(f"<h1>BTC/USD trading dashboard</h1><p class='muted'>Built {gen:%Y-%m-%d %H:%M} UTC · "
        "paper trading only, no real money · everything below comes from your own database</p>")

    # -- Paper account summary ----------------------------------------------
    add("<h2>1. Your paper-trading account</h2>")
    account = data.account
    latest_close = data.history.candles[-1].close if data.history.candles else None
    if account is None:
        add("<p class='notice'>No paper account yet. Run <code>python -m scripts.daily_run</code> to start one.</p>")
    else:
        value = account.cash + account.btc * (latest_close or 0)
        result = (value / account.starting_cash - 1) * 100
        bh = data.equity[-1][2] if data.equity else None
        position = "In BTC" if account.btc > 0 else "In cash (USD)"
        if account.pending_side:
            position += f" · {account.pending_side} order waiting"
        add("<div class='cards'>")
        add(f"<div class='card'><div class='label'>Account value</div><div class='value'>{fmt_price(value)}</div>"
            f"<div class='sub'>started with {fmt_price(account.starting_cash)}</div></div>")
        add(f"<div class='card'><div class='label'>Result</div><div class='value'>{fmt_pct(result)}</div>"
            f"<div class='sub'>since {account.start_candle:%Y-%m-%d}</div></div>")
        if bh is not None:
            add(f"<div class='card'><div class='label'>Buy and hold over the same period</div>"
                f"<div class='value'>{fmt_pct((bh / account.starting_cash - 1) * 100)}</div>"
                f"<div class='sub'>{fmt_price(bh)} if you had simply bought</div></div>")
        add(f"<div class='card'><div class='label'>Position</div><div class='value' style='font-size:20px'>{esc(position)}</div>"
            f"<div class='sub'>{account.btc:.6f} BTC · {fmt_price(account.cash)} cash"
            + (f" · stop {fmt_price(account.stop_price)}" if account.stop_price else "") + "</div></div>")
        add("</div>")
        add(f"<p class='secondary'>Strategy: <strong>{esc(account.strategy)}</strong> on {esc(account.timeframe)} candles. "
            "Decisions at each daily close (00:00 UTC), orders filled at the next tradeable open with "
            "Kraken's 0.80% fee and 0.05% slippage. "
            f"Account created {account.created_at:%Y-%m-%d}; decisions for days before that were replayed from history.</p>")
        if data.kill_switch_on:
            add("<p class='notice'>Kill switch is ON (<code>database/STOP_PAPER_TRADING</code> exists): no new buys.</p>")
        if len(data.equity) >= 2:
            add(line_chart(
                "equity", "Account value vs buy and hold (USD)",
                [
                    {"name": "Paper account", "color": "--series-1", "points": [(t, a) for t, a, _ in data.equity]},
                    {"name": "Buy and hold", "color": "--series-2", "points": [(t, b) for t, _, b in data.equity]},
                ],
            ))

    # -- Strategy now -------------------------------------------------------
    add("<h2>2. What the strategy says now</h2>")
    if data.strategy_rules:
        last_day = data.daily_rows[-1].timestamp if data.daily_rows else None
        add(f"<p class='secondary'>Latest completed daily candle: {last_day:%Y-%m-%d}. "
            "Buy needs the trend filter AND the trigger; sell needs the sell rule (or the stop).</p><ul class='rules'>")
        for label, ok in data.strategy_rules.items():
            add(f"<li>{status_badge('good' if ok else 'neutral', 'yes' if ok else 'no')} {esc(label)}</li>")
        add("</ul>")
    if data.decisions:
        add("<div class='table-scroll'><table><tr><th>Daily candle</th><th>Decision</th><th>Why</th><th>Close</th><th>Recorded</th></tr>")
        for d in data.decisions[:10]:
            add(f"<tr><td>{d.candle_time:%Y-%m-%d}</td><td><strong>{esc(d.action)}</strong></td><td>{esc(d.reason)}</td>"
                f"<td>{fmt_price(d.close)}</td><td class='muted'>{d.recorded_at:%Y-%m-%d %H:%M}</td></tr>")
        add("</table></div>")
        add("<p class='muted'>The decision log is append-only: entries are never changed afterwards.</p>")

    # -- Market now -----------------------------------------------------------
    add("<h2>3. The market now</h2>")
    if data.daily_rows:
        recent = data.daily_rows[-365:]
        fill_markers = []
        for f in data.fills:
            day = f.filled_at.replace(hour=0, minute=0, second=0, microsecond=0)
            fill_markers.append((day, f.price, f.side))
        add(line_chart(
            "price", "BTC/USD daily close, last 365 days",
            [
                {"name": "Close", "color": "--series-1", "points": [(r.timestamp, r.close) for r in recent]},
                {"name": "EMA 50", "color": "--series-2", "points": [(r.timestamp, r.values.get("ema_50")) for r in recent]},
                {"name": "EMA 200", "color": "--series-3", "points": [(r.timestamp, r.values.get("ema_200")) for r in recent]},
            ],
            markers=fill_markers,
        ))
    columns = [(tf, label, data.latest_rows[tf]) for tf, label in
               (("1d", "Daily"), ("4h", "4-hour"), ("1h", "Hourly")) if tf in data.latest_rows]
    if columns:
        readings = {tf: {topic: (verdict, detail) for topic, verdict, detail in market_reading(row.values, row.close)}
                    for tf, _, row in columns}
        topics = list(dict.fromkeys(t for tf, _, _ in columns for t in readings[tf]))
        add("<div class='table-scroll' style='margin-top:16px'><table><tr><th>Indicator</th>")
        for tf, label, row in columns:
            add(f"<th>{label}<div class='muted' style='font-weight:400'>close {fmt_price(row.close)}<br>"
                f"candle {row.timestamp:%Y-%m-%d %H:%M} UTC</div></th>")
        add("</tr>")
        for topic in topics:
            add(f"<tr><td>{esc(topic)}</td>")
            for tf, _, _ in columns:
                verdict, detail = readings[tf].get(topic, ("-", ""))
                add(f"<td><strong>{esc(verdict)}</strong><div class='muted' style='font-size:13px'>{esc(detail)}</div></td>")
            add("</tr>")
        add("</table></div>")

    # -- Data status ----------------------------------------------------------
    add("<h2>4. Your data</h2>")
    add("<div class='table-scroll'><table><tr><th>Exchange</th><th>Status</th><th>Hourly candles</th><th>From</th><th>Latest</th></tr>")
    for ex in data.exchanges:
        kind, label = ex.status
        add(f"<tr><td>{esc(ex.exchange.capitalize())}</td><td>{status_badge(kind, label)}</td><td>{ex.candles:,}</td>"
            f"<td>{ex.first:%Y-%m-%d}</td><td>{ex.latest:%Y-%m-%d %H:%M}</td></tr>")
    add("</table></div>")
    h = data.history
    filled = len(h.substituted_hours())
    add(f"<p class='secondary'>Analysis uses one continuous history: Bitstamp before 2017, Kraken from 2017. "
        f"{len(h.candles):,} hourly candles; {filled} hours were filled from another exchange (Kraken outages); "
        f"{len(h.unfilled_hours)} hours no exchange has; {len(h.large_jumps())} switches between exchanges moved "
        "the price by more than 1% (see <code>python -m scripts.report_continuous_history</code>).</p>")

    # -- Research & next steps -------------------------------------------------
    add("<h2>5. What the research found so far</h2>")
    add("<ul class='secondary'>"
        "<li>Tested 540 indicator combinations on 1h, 4h and 1d candles, chosen on older years and checked on years they were not chosen on, after Kraken fees.</li>"
        "<li><strong>Daily trend following</strong> (only buy in an uptrend, sell when the shorter trend breaks) "
        "cut the worst drop from 84% to about 52% but made about a quarter of buy-and-hold's return (2016-now).</li>"
        "<li>Hourly and 4-hour strategies did not survive the fees. Finding a better strategy is parked for later.</li></ul>")

    add("<h2>6. Where to work from</h2><div class='table-scroll'><table><tr><th>What</th><th>Command (PowerShell, project folder, venv active)</th></tr>")
    for what, cmd in (
        ("Daily routine: update data, paper trade, rebuild this page", "python -m scripts.daily_run"),
        ("Only rebuild this page", "python -m scripts.build_dashboard"),
        ("Check the data", "python -m scripts.check_database_integrity"),
        ("Research: all strategy combinations", "python -m scripts.run_backtests"),
        ("Research: year by year / walk-forward", "python -m scripts.run_walk_forward"),
        ("Stop new paper buys", "New-Item database\\STOP_PAPER_TRADING"),
        ("Run the tests", "python -m pytest -q"),
    ):
        add(f"<tr><td>{esc(what)}</td><td><code>{esc(cmd)}</code></td></tr>")
    add("</table></div>")

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>BTC Trading Dashboard</title>"
        f"<style>{CSS}</style></head><body><main>{''.join(out)}</main>"
        f"<script>{SCRIPT}</script></body></html>"
    )
