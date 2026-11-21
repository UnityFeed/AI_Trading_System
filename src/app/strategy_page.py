"""
The Strategy tester page: pick any strategy from the registry and see its
full-history backtest next to buy-and-hold: summary, account value over
time (log scale), results per year and every trade.
"""

from src.app.chart_page import CHART_CSS, CHART_LIBRARY, NAV_CSS, NAV_SCRIPT, nav_html
from src.reporting.dashboard import CSS


PAGE_CSS = """
body { height: auto; display: block; }
.wrap { max-width: 1150px; margin: 0 auto; padding: 16px 16px 64px; }
.controls { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin: 8px 0 16px; }
.controls a { color: var(--series-1); }
.note-box { border-left: 4px solid var(--warning); padding: 8px 12px; background: var(--card);
  border-radius: 6px; margin: 12px 0; color: var(--text-secondary); }
#equity { height: 380px; position: relative; background: var(--card); border: 1px solid var(--border); border-radius: 10px; }
#equity-chart { position: absolute; inset: 8px; }
td.num, th.num { text-align: right; }
.scroll-y { max-height: 520px; overflow: auto; border-radius: 10px; }
.scroll-y table { border-radius: 0; }
.scroll-y th { position: sticky; top: 0; background: var(--card); }
"""

PAGE_SCRIPT = r"""
(function () {
  var LWC = window.LightweightCharts;
  var params = new URLSearchParams(location.search);
  var strategySelect = document.getElementById('strategy'), feeSelect = document.getElementById('fee');
  var marginSelect = document.getElementById('margin');
  var chart = null, strategies = [];

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function pct(v) { return v === null || v === undefined ? '-' : (v > 0 ? '+' : '') + Number(v).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1}) + '%'; }
  function drop(v) { return v === null || v === undefined ? '-' : (v === 0 ? '0.0%' : '-' + v.toFixed(1) + '%'); }
  function money(v) { return v === null || v === undefined ? '-' : '$' + Number(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
  function el(tag, text, cls) { var e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
  function day(iso) { return iso.slice(0, 10); }

  fetch('/api/strategies').then(function (r) { return r.json(); }).then(function (d) {
    strategies = d.strategies;
    d.strategies.forEach(function (s) {
      var o = el('option', s.name + ' (' + s.timeframe + ')' + (s.id === d.active ? ' - paper trading' : ''));
      o.value = s.id; strategySelect.appendChild(o);
    });
    d.fees.forEach(function (f) {
      var o = el('option', f.toFixed(2) + '% per buy/sell' + (f === 0.8 ? ' (market orders)' : ' (limit orders)'));
      o.value = f; feeSelect.appendChild(o);
    });
    d.leverages.forEach(function (lev) {
      var o = el('option', lev === 1 ? 'Off (no borrowing)' : lev + 'x (borrow ' + (lev - 1) + 'x your money)');
      o.value = lev; marginSelect.appendChild(o);
    });
    strategySelect.value = params.get('strategy') || d.active;
    if (!strategySelect.value) strategySelect.value = d.active;
    load();
  });
  strategySelect.addEventListener('change', load);
  feeSelect.addEventListener('change', load);
  marginSelect.addEventListener('change', load);

  function load() {
    var id = strategySelect.value;
    history.replaceState(null, '', '/strategy?strategy=' + encodeURIComponent(id));
    document.getElementById('status').textContent = 'Running the backtest over the full history...';
    fetch('/api/backtest?strategy=' + encodeURIComponent(id) + '&fee=' + feeSelect.value + '&leverage=' + marginSelect.value)
      .then(function (r) { return r.json(); }).then(render);
  }

  function render(rep) {
    document.getElementById('status').textContent = '';
    var s = rep.strategy;
    document.getElementById('show-on-chart').href = '/chart?tf=' + s.timeframe + '&trades=' + encodeURIComponent(s.id);
    document.getElementById('description').textContent = s.description;
    document.getElementById('rules').textContent = 'Rules: ' + s.rules + ' - timeframe ' + s.timeframe +
      ' - costs ' + rep.costs.fee_pct + '% fee + ' + rep.costs.slippage_pct + '% slippage per buy and per sell';
    document.getElementById('origin').textContent = 'Where it comes from: ' + s.origin;
    document.getElementById('note').textContent = rep.note;
    var m = rep.margin, warn = document.getElementById('margin-note');
    if (m.leverage > 1) {
      warn.hidden = false;
      warn.textContent = 'Margin simulation, ' + m.leverage + 'x: every buy uses your money plus ' + (m.leverage - 1) +
        'x borrowed from Kraken. Costs: ' + m.open_fee_pct + '% of the borrowed amount to open, ' + m.rollover_fee_pct +
        '% every ' + m.rollover_hours + ' hours while open, plus the normal trading fee on the whole position. ' +
        'Kraken force-closes (liquidates) the position when your own money in it falls to ' + m.liquidation_level_pct +
        '% of what you put in, with a ' + m.liquidation_fee_pct + '% liquidation fee. Losses grow as fast as gains. ' +
        'Buy and hold below is shown WITHOUT margin. This is a simulation only: the paper trader never uses margin.';
    } else { warn.hidden = true; }

    // Summary: strategy vs buy and hold
    var a = rep.summary, b = rep.buy_and_hold;
    var rows = [
      ['Period', day(a.start) + ' to ' + day(a.end), ''],
      ['Total result', pct(a.total_return_pct), pct(b.total_return_pct)],
      ['Per year (average)', pct(a.yearly_pct), pct(b.yearly_pct)],
      ['Worst drop from a peak', '-' + a.max_drawdown_pct.toFixed(1) + '%', '-' + b.max_drawdown_pct.toFixed(1) + '%'],
      ['Return per unit of risk (yearly / worst drop)', a.calmar.toFixed(2), b.calmar.toFixed(2)],
      ['Trades', String(a.trades), '1'],
      ['Winning trades', a.win_rate_pct + '%', ''],
      ['Average trade', pct(a.average_trade_pct), ''],
      ['Best / worst trade', pct(a.best_trade_pct) + ' / ' + pct(a.worst_trade_pct), ''],
      ['Average days in a trade', a.average_days_held === null ? '-' : String(a.average_days_held), ''],
      ['Time in the market', a.exposure_pct + '%', b.exposure_pct + '%']
    ];
    if (m.leverage > 1) {
      rows.push(['Forced closes (liquidations)', String(a.liquidations), '']);
      rows.push(['Borrowing costs paid (% of starting money)', a.margin_costs_pct.toFixed(1) + '%', '']);
    }
    var table = document.getElementById('summary'); table.textContent = '';
    var head = el('tr'); ['', s.name, 'Buy and hold'].forEach(function (h, i) { head.appendChild(el('th', h, i ? 'num' : '')); });
    table.appendChild(head);
    rows.forEach(function (r) {
      var tr = el('tr'); tr.appendChild(el('td', r[0]));
      tr.appendChild(el('td', r[1], 'num')); tr.appendChild(el('td', r[2], 'num')); table.appendChild(tr);
    });

    // Account value over time, log scale (one scale for both lines)
    var box = document.getElementById('equity-chart');
    if (chart) chart.remove();
    box.textContent = '';
    if (!LWC) { box.textContent = 'The chart library could not be loaded (needs internet).'; }
    else {
      chart = LWC.createChart(box, {
        autoSize: true,
        layout: {background: {type: 'solid', color: css('--card')}, textColor: css('--text-secondary'), fontFamily: getComputedStyle(document.body).fontFamily},
        grid: {vertLines: {color: css('--grid')}, horzLines: {color: css('--grid')}},
        rightPriceScale: {mode: LWC.PriceScaleMode.Logarithmic, borderColor: css('--border')},
        timeScale: {borderColor: css('--border'), minBarSpacing: 0.01},
        localization: {priceFormatter: function (p) { return '$' + Math.round(p * 10000).toLocaleString(); }}
      });
      var line = function (color, data) {
        var se = chart.addSeries(LWC.LineSeries, {color: css(color), lineWidth: 2, priceLineVisible: false});
        se.setData(data.map(function (p) { return {time: p[0], value: p[1]}; }));
        return se;
      };
      line('--series-2', rep.buy_and_hold_equity);
      line('--series-1', rep.equity);
      // Fit the whole history once the chart has its real size.
      requestAnimationFrame(function () { chart.timeScale().fitContent(); });
      setTimeout(function () { chart.timeScale().fitContent(); }, 150);
    }

    // Per year
    var years = document.getElementById('years'); years.textContent = '';
    var yh = el('tr');
    ['Year', 'Strategy', 'Buy and hold', 'Strategy worst drop', 'Buy-and-hold worst drop', 'Trades started', 'Better than holding?']
      .forEach(function (h, i) { yh.appendChild(el('th', h, i ? 'num' : '')); });
    years.appendChild(yh);
    var better = 0, counted = 0;
    rep.years.forEach(function (y) {
      var tr = el('tr'); tr.appendChild(el('td', String(y.year)));
      tr.appendChild(el('td', pct(y.strategy_pct), 'num'));
      tr.appendChild(el('td', pct(y.buy_hold_pct), 'num'));
      tr.appendChild(el('td', drop(y.strategy_drop_pct), 'num'));
      tr.appendChild(el('td', drop(y.buy_hold_drop_pct), 'num'));
      tr.appendChild(el('td', String(y.trades), 'num'));
      var win = y.strategy_pct !== null && y.strategy_pct > y.buy_hold_pct;
      if (y.strategy_pct !== null) { counted++; if (win) better++; }
      var cell = el('td', '', 'num');
      var badge = el('span', '', 'badge ' + (win ? 'good' : 'neutral'));
      var icon = el('span', win ? '✓' : '–', 'badge-icon'); icon.setAttribute('aria-hidden', 'true');
      badge.appendChild(icon); badge.appendChild(document.createTextNode(win ? 'yes' : 'no'));
      cell.appendChild(badge); tr.appendChild(cell); years.appendChild(tr);
    });
    document.getElementById('years-summary').textContent =
      'Better than buy and hold in ' + better + ' of ' + counted + ' years.';

    // Trades, newest first
    var trades = document.getElementById('trades'); trades.textContent = '';
    var th = el('tr');
    ['#', 'Bought', 'Buy price', 'Sold', 'Sell price', 'Days', 'Result', 'Why sold'].forEach(function (h, i) {
      th.appendChild(el('th', h, [2, 4, 5, 6].indexOf(i) >= 0 ? 'num' : ''));
    });
    trades.appendChild(th);
    rep.trades.slice().reverse().forEach(function (t, i) {
      var tr = el('tr');
      tr.appendChild(el('td', String(rep.trades.length - i)));
      tr.appendChild(el('td', day(t.entry_time)));
      tr.appendChild(el('td', money(t.entry_price), 'num'));
      tr.appendChild(el('td', t.open ? 'still open' : day(t.exit_time)));
      tr.appendChild(el('td', t.open ? 'now ' + money(t.exit_price) : money(t.exit_price), 'num'));
      tr.appendChild(el('td', String(t.days_held), 'num'));
      tr.appendChild(el('td', pct(t.return_pct), 'num'));
      tr.appendChild(el('td', t.open ? 'not sold yet' : ({stop: 'stop loss', liquidated: 'LIQUIDATED (forced close)'}[t.exit_reason] || 'sell rule')));
      trades.appendChild(tr);
    });
  }

  if (window.matchMedia) window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', load);
})();
"""


def strategy_page() -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Strategy Tester</title>"
        f"<style>{CSS}{NAV_CSS}{CHART_CSS}{PAGE_CSS}</style></head><body>"
        + nav_html("strategy")
        + "<div class='wrap'><h1>Strategy tester</h1>"
        "<p class='muted'>Every strategy in the list is tested over the full history (2013 to now) "
        "with Kraken's fees, next-candle fills and no trades on hours filled in from another exchange.</p>"
        "<div class='controls'><label>Strategy <select id='strategy'></select></label>"
        "<label>Fees <select id='fee'></select></label>"
        "<label>Margin <select id='margin'></select></label>"
        "<a id='show-on-chart' href='/chart'>Show these trades on the chart &rarr;</a>"
        "<span class='muted' id='status'></span></div>"
        "<p id='description'></p><p class='secondary' id='rules'></p><p class='muted' id='origin'></p>"
        "<div class='note-box' id='note'></div><div class='note-box' id='margin-note' hidden></div>"
        "<h2>Result vs buy and hold</h2><div class='table-scroll'><table id='summary'></table></div>"
        "<h2>Account value over time</h2>"
        "<div class='legend'><span class='legend-item'><span class='legend-key' style='background:var(--series-1)'></span>Strategy</span>"
        "<span class='legend-item'><span class='legend-key' style='background:var(--series-2)'></span>Buy and hold</span>"
        "<span class='legend-item muted'>$10,000 at the start; logarithmic scale, so equal steps mean equal percentage changes</span></div>"
        "<div id='equity'><div id='equity-chart'></div></div>"
        "<h2>Year by year</h2><p class='secondary' id='years-summary'></p>"
        "<div class='table-scroll'><table id='years'></table></div>"
        "<h2>Every trade</h2><div class='scroll-y'><table id='trades'></table></div></div>"
        f"<script src='{CHART_LIBRARY}'></script>"
        f"<script>{NAV_SCRIPT}{PAGE_SCRIPT}</script></body></html>"
    )
