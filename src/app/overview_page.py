"""
The Overview page of the app: how the selected strategy's latest trade is
doing, what the strategy says at the latest close, its recent trades, the
paper account (the permanent forward log of the active strategy) and the
health of the data.

The strategy part is filled in by the browser from /api/strategy-state for
the strategy chosen anywhere in the app (shared choice, remembered in the
browser). The data and paper-account parts are rendered by the server.
"""

from src.app.chart_page import NAV_CSS, NAV_SCRIPT, SHARED_SELECTION_SCRIPT, nav_html
from src.reporting.dashboard import change_24h, esc, fmt_pct, fmt_price, page, status_badge


PAGE_CSS = """
.head-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; }
.head-controls label { display: inline-flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 14px; max-width: 100%; min-width: 0; flex-wrap: wrap; }
.head-controls select { max-width: calc(100vw - 32px); min-width: 0; }
select { font: inherit; padding: 5px 8px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--card); color: var(--text-primary); }
.trade-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px 20px; margin-top: 6px; }
.trade-grid .label { color: var(--text-muted); font-size: 13px; }
.trade-grid .value { font-size: 20px; font-weight: 650; font-variant-numeric: tabular-nums; }
.big-result { font-size: 40px; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; line-height: 1.1; }
.signal-box { border-radius: 10px; padding: 10px 14px; margin-top: 12px; background: var(--surface); }
.signal-box.active { background: var(--text-primary); color: var(--card); }
.signal-box.active .muted { color: inherit; opacity: .75; }
.links { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 14px; }
"""

PAGE_SCRIPT = r"""
(function () {
  var select = document.getElementById('strategy');
  function el(tag, text, cls) { var e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
  function pct(v) { return v === null || v === undefined ? '-' : (v > 0 ? '+' : '') + Number(v).toFixed(1) + '%'; }
  function money(v) { return v === null || v === undefined ? '-' : '$' + Number(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
  function day(iso) { return iso.slice(0, 10); }
  function stat(label, value, sub) {
    var box = el('div'); box.appendChild(el('div', label, 'label')); box.appendChild(el('div', value, 'value'));
    if (sub) box.appendChild(el('div', sub, 'muted small'));
    return box;
  }
  function badge(ok, text) {
    var b = el('span', '', 'badge ' + (ok ? 'good' : 'neutral'));
    var i = el('span', ok ? '✓' : '–', 'badge-icon'); i.setAttribute('aria-hidden', 'true');
    b.appendChild(i); b.appendChild(document.createTextNode(text)); return b;
  }

  SelectedStrategy.fill(select, function () { load(); });
  select.addEventListener('change', function () { SelectedStrategy.set(select.value); load(); });

  function load() {
    document.getElementById('chart-link').href = '/chart';
    fetch('/api/strategy-state?strategy=' + encodeURIComponent(select.value))
      .then(function (r) { return r.json(); }).then(function (s) {
        if (s.error) {
          var box = document.getElementById('latest-trade'); box.textContent = '';
          box.appendChild(el('h2', 'Strategy')); box.appendChild(el('p', s.error, 'notice'));
          return;
        }
        render(s);
      });
  }

  function renderShare(s, box) {
    var x = s.exposure;
    var head = el('div', '', 'panel-head');
    head.appendChild(el('h2', 'BTC share now')); head.appendChild(el('span', 'GRADED', 'pill strong'));
    box.appendChild(head);
    box.appendChild(el('div', x.weight_pct.toFixed(0) + '% in BTC', 'big-result'));
    box.appendChild(el('p', 'the rest is cash; this strategy moves between 0% and 100% in steps instead of all-in/all-out', 'muted small'));
    var grid = el('div', '', 'trade-grid');
    grid.appendChild(stat('Target at the latest close', x.target_pct === null ? '-' : x.target_pct.toFixed(0) + '%',
      'trades when it differs by ' + x.band_pct + ' points or more'));
    grid.appendChild(stat('Latest close', money(s.close)));
    grid.appendChild(stat('Last change', x.last_rebalance ? day(x.last_rebalance) : 'none', x.days_since === null ? '' : x.days_since + ' days ago'));
    grid.appendChild(stat('Changes in total', String(s.rebalances_total)));
    box.appendChild(grid);
  }

  function render(s) {
    var st = s.strategy;
    document.getElementById('strategy-description').textContent = st.description;

    // Latest trade
    var box = document.getElementById('latest-trade'); box.textContent = '';
    var p = s.position, last = s.last_closed_trade, graded = s.kind === 'exposure';
    if (graded) {
      renderShare(s, box);
    } else if (p) {
      var head = el('div', '', 'panel-head');
      head.appendChild(el('h2', 'Open trade')); head.appendChild(el('span', 'OPEN', 'pill strong'));
      box.appendChild(head);
      box.appendChild(el('div', pct(p.result_if_sold_pct), 'big-result'));
      box.appendChild(el('p', 'result if sold at the latest close, after fees and slippage', 'muted small'));
      var grid = el('div', '', 'trade-grid');
      grid.appendChild(stat('Bought', day(p.entry_time), money(p.entry_price)));
      grid.appendChild(stat('Latest close', money(s.close), pct(p.price_change_pct) + ' price change'));
      grid.appendChild(stat('Days in the trade', String(p.days_held)));
      grid.appendChild(p.stop_price ? stat('Stop', money(p.stop_price), pct(p.stop_distance_pct) + ' above the stop')
                                    : stat('Stop', 'none', 'this strategy has no stop'));
      box.appendChild(grid);
    } else {
      var head2 = el('div', '', 'panel-head');
      head2.appendChild(el('h2', 'Latest trade')); head2.appendChild(el('span', 'CLOSED', 'pill'));
      box.appendChild(head2);
      if (!last) { box.appendChild(el('p', 'This strategy has not traded yet.', 'muted')); }
      else {
        box.appendChild(el('div', pct(last.return_pct), 'big-result'));
        box.appendChild(el('p', 'result after fees and slippage; no open trade now, waiting for a buy signal', 'muted small'));
        var g = el('div', '', 'trade-grid');
        g.appendChild(stat('Bought', day(last.entry_time), money(last.entry_price)));
        g.appendChild(stat('Sold', day(last.exit_time), money(last.exit_price)));
        g.appendChild(stat('Days in the trade', String(last.days_held)));
        g.appendChild(stat('Why sold', last.exit_reason === 'stop' ? 'stop loss' : (last.exit_reason === 'liquidated' ? 'liquidated' : 'sell rule')));
        box.appendChild(g);
      }
    }

    // Signal today
    var rules = document.getElementById('rules'); rules.textContent = '';
    s.rules.forEach(function (r) {
      var li = el('li'); li.appendChild(badge(r.met, r.met === null ? 'n/a' : (r.met ? 'yes' : 'no')));
      li.appendChild(el('span', r.role + ': ' + r.rule)); rules.appendChild(li);
    });
    document.getElementById('rules-when').textContent = 'at the close of the ' + st.timeframe + ' candle of ' + s.candle_time.slice(0, 16).replace('T', ' ') + ' UTC';
    var sig = document.getElementById('signal'); sig.textContent = '';
    if (s.signal) {
      sig.className = 'signal-box active';
      sig.appendChild(el('strong', s.signal.action + ' signal'));
      sig.appendChild(el('div', s.signal.reason + '. It is carried out at the next open.', 'muted small'));
    } else {
      sig.className = 'signal-box';
      sig.appendChild(el('strong', 'No signal'));
      sig.appendChild(el('div', (graded ? 'The BTC share stays as it is: the target is within the band.' :
        (p ? 'Holding: the sell rule has not triggered.' : 'Waiting: not all buy rules are met.')) +
        ' Next decision at ' + s.next_close.slice(0, 16).replace('T', ' ') + ' UTC.', 'muted small'));
    }

    // Recent trades (or share changes)
    var t = document.getElementById('recent'); t.textContent = '';
    document.getElementById('recent-title').textContent = graded ? 'Recent changes of the BTC share' : 'Recent trades';
    if (graded) {
      var gh = el('tr'); ['Date', 'Price', 'From', 'To'].forEach(function (h, i) { gh.appendChild(el('th', h, i ? 'num' : '')); });
      t.appendChild(gh);
      s.recent_rebalances.forEach(function (r) {
        var tr = el('tr'); tr.appendChild(el('td', day(r.time))); tr.appendChild(el('td', money(r.price), 'num'));
        tr.appendChild(el('td', r.from_pct.toFixed(0) + '%', 'num')); tr.appendChild(el('td', r.to_pct.toFixed(0) + '%', 'num'));
        t.appendChild(tr);
      });
      document.getElementById('recent-count').textContent = s.rebalances_total + ' changes in total';
      return;
    }
    var hr = el('tr'); ['Bought', 'Sold', 'Days', 'Result', 'Why sold'].forEach(function (h, i) { hr.appendChild(el('th', h, i === 2 || i === 3 ? 'num' : '')); });
    t.appendChild(hr);
    s.recent_trades.forEach(function (x) {
      var tr = el('tr');
      tr.appendChild(el('td', day(x.entry_time))); tr.appendChild(el('td', day(x.exit_time)));
      tr.appendChild(el('td', String(x.days_held), 'num')); tr.appendChild(el('td', pct(x.return_pct), 'num'));
      tr.appendChild(el('td', x.exit_reason === 'stop' ? 'stop loss' : 'sell rule', 'secondary'));
      t.appendChild(tr);
    });
    document.getElementById('recent-count').textContent = s.trades_total + ' closed trades in total';
  }
})();
"""


def accounts_table(latest_close: float | None, rows) -> str:
    """Paper accounts side by side. rows: (strategy name, Account or None)."""
    out = ["<div class='table-scroll'><table class='compact'><tr><th>Strategy</th><th>Since</th>"
           "<th class='num'>Start</th><th class='num'>Value now</th><th class='num'>Result</th>"
           "<th class='num'>In BTC</th></tr>"]
    for name, account in rows:
        if account is None:
            out.append(f"<tr><td>{esc(name)}</td><td colspan='5' class='muted'>starts at the next run of the "
                       "daily routine</td></tr>")
            continue
        price = latest_close or 0.0
        value = account.cash + account.btc * price
        share = account.btc * price / value * 100 if value > 0 else 0.0
        out.append(
            f"<tr><td>{esc(name)}</td><td>{account.start_candle:%Y-%m-%d}</td>"
            f"<td class='num'>{fmt_price(account.starting_cash)}</td><td class='num'>{fmt_price(value)}</td>"
            f"<td class='num'>{fmt_pct((value / account.starting_cash - 1) * 100)}</td>"
            f"<td class='num'>{share:.0f}%</td></tr>"
        )
    out.append("</table></div>")
    return "".join(out)


def overview_page(history, exchanges, account, kill_switch_on: bool, extras=()) -> str:
    """The Overview page; `exchanges` from dashboard.exchange_status;
    `extras`: (strategy name, Account or None) of the extra paper accounts."""

    candles = history.candles
    latest = candles[-1] if candles else None
    out = []
    add = out.append

    add("<header class='page-head'><div><h1>Overview</h1>"
        "<div class='head-controls'><label>Strategy <select id='strategy'></select></label></div>"
        "<p class='muted small' id='strategy-description'></p></div>")
    if latest is not None:
        change = change_24h(candles)
        add(f"<div class='price-tag'><span class='muted'>BTC/USD</span><strong>{fmt_price(latest.close)}</strong>"
            + ("" if change is None else f"<span class='muted'>{fmt_pct(change)} in 24 h</span>")
            + f"<span class='muted small'>close of the {latest.timestamp:%H:%M} UTC hour</span></div>")
    add("</header>")

    add("<div class='grid-2'>")
    add("<section class='panel' id='latest-trade'><p class='muted'>Loading...</p></section>")
    add("<section class='panel'><div class='panel-head'><h2>Signal</h2>"
        "<span class='muted small' id='rules-when'></span></div><ul class='rules' id='rules'></ul>"
        "<div id='signal' class='signal-box'></div></section>")
    add("</div>")

    add("<section class='panel'><div class='panel-head'><h2 id='recent-title'>Recent trades</h2>"
        "<span class='muted small' id='recent-count'></span></div>"
        "<div class='table-scroll'><table class='compact' id='recent'></table></div>"
        "<div class='links' style='margin-top:10px'><a id='chart-link' href='/chart'>See every trade on the chart &rarr;</a>"
        "<a href='/strategy'>Full results in the Strategy tester &rarr;</a></div></section>")

    add("<div class='grid-2'>")
    add("<section class='panel'><div class='panel-head'><h2>Paper account</h2>"
        "<span class='muted small'>forward log of the active strategy</span></div>")
    if account is None:
        add("<p class='muted'>No paper account yet. Press <strong>Update data &amp; run paper trader</strong> to start one.</p>")
    else:
        value = account.cash + account.btc * (latest.close if latest else 0)
        add("<div class='trade-grid'>"
            f"<div><div class='label'>Value</div><div class='value'>{fmt_price(value)}</div>"
            f"<div class='muted small'>started with {fmt_price(account.starting_cash)}</div></div>"
            f"<div><div class='label'>Result</div><div class='value'>{fmt_pct((value / account.starting_cash - 1) * 100)}</div>"
            f"<div class='muted small'>since {account.start_candle:%Y-%m-%d}</div></div>"
            f"<div><div class='label'>Position</div><div class='value'>{'In BTC' if account.btc > 0 else 'In cash'}</div>"
            f"<div class='muted small'>{account.btc:.6f} BTC</div></div></div>"
            f"<p class='muted small'>{esc(account.strategy)}. Every decision is logged and never changed.</p>")
    if extras:
        add("<h3 class='small' style='margin:14px 0 6px'>Side by side</h3>")
        add(accounts_table(latest.close if latest else None,
                           [("Main account (active strategy)", account)] + list(extras)))
        add("<p class='muted small'>Each account follows one strategy with its own virtual money, "
            "on the same days: the fair comparison going forward.</p>")
        if kill_switch_on:
            add("<p class='notice'>Kill switch is ON: no new paper buys.</p>")
    add("</section>")

    add("<section class='panel'><div class='panel-head'><h2>Your data</h2></div>"
        "<div class='table-scroll'><table class='compact'><tr><th>Exchange</th><th>Status</th><th>Latest hour</th></tr>")
    for ex in exchanges:
        kind, label = ex.status
        add(f"<tr><td>{esc(ex.exchange.capitalize())}</td><td>{status_badge(kind, label)}</td>"
            f"<td>{ex.latest:%Y-%m-%d %H:%M}</td></tr>")
    add("</table></div>"
        f"<p class='muted small'>{len(history.candles):,} hourly candles since {candles[0].timestamp:%Y} "
        f"(all from Bitstamp; {len(history.substituted_hours())} hours it lacks filled from "
        "another exchange).</p></section>" if candles else "</table></div></section>")
    add("</div>")

    return page(
        "BTC Trading - Overview",
        nav_html("overview") + f"<main>{''.join(out)}</main>",
        head=f"<style>{NAV_CSS}{PAGE_CSS}</style>",
        scripts=f"<script>{NAV_SCRIPT}{SHARED_SELECTION_SCRIPT}{PAGE_SCRIPT}</script>",
    )

