"""
The Strategy tester page: pick any strategy from the registry and see its
full-history backtest next to buy-and-hold: summary (with Sharpe, the
break-even fee and the exposure-matched benchmark), account value over
time (log scale), results per year and every trade (or, for graded
strategies, every change of the BTC share). A table at the top compares
all strategies with the same settings.
"""

from src.app.chart_page import (
    CHART_CSS, CHART_LIBRARY, NAV_CSS, NAV_SCRIPT, SHARED_SELECTION_SCRIPT, nav_html,
)
from src.reporting.dashboard import page


PAGE_CSS = """
body { height: auto; display: block; }
.controls { display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; margin-bottom: 12px; }
.controls label { display: inline-flex; align-items: center; gap: 8px; color: var(--text-secondary); font-size: 14px; }
.controls label { max-width: 100%; } .controls select { max-width: 100%; min-width: 0; text-overflow: ellipsis; }
.controls a { color: var(--series-1); }
.note-box { border-left: 4px solid var(--warning); padding: 8px 12px; background: var(--surface);
  border-radius: 8px; margin: 10px 0 0; color: var(--text-secondary); font-size: 14px; }
#equity { height: 380px; position: relative; }
#equity-chart { position: absolute; inset: 0; }
td.num, th.num { text-align: right; }
.scroll-y { max-height: 520px; overflow: auto; }
tr.selected-row td { background: color-mix(in srgb, var(--series-1) 12%, transparent); font-weight: 600; }
.scroll-y th { position: sticky; top: 0; background: var(--card); }
"""

PAGE_SCRIPT = r"""
(function () {
  var LWC = window.LightweightCharts;
  var params = new URLSearchParams(location.search);
  var strategySelect = document.getElementById('strategy'), feeSelect = document.getElementById('fee');
  var marginSelect = document.getElementById('margin');
  var startSelect = document.getElementById('start');
  var chart = null, strategies = [];

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function pct(v) { return v === null || v === undefined ? '-' : (v > 0 ? '+' : '') + Number(v).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1}) + '%'; }
  function drop(v) { return v === null || v === undefined ? '-' : (v === 0 ? '0.0%' : '-' + v.toFixed(1) + '%'); }
  function money(v) { return v === null || v === undefined ? '-' : '$' + Number(v).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
  function el(tag, text, cls) { var e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
  function day(iso) { return iso.slice(0, 10); }
  // Remember the choices between visits (the nav link has no settings in it).
  function remembered(key) { try { return localStorage.getItem('strategy-tester-' + key); } catch (e) { return null; } }
  function remember(key, value) { try { localStorage.setItem('strategy-tester-' + key, value); } catch (e) {} }
  function choose(select, wanted, fallback) {
    select.value = wanted;
    if (select.value !== String(wanted)) select.value = fallback;  // option no longer exists
  }

  fetch('/api/strategies').then(function (r) { return r.json(); }).then(function (d) {
    strategies = d.strategies;
    d.strategies.forEach(function (s) {
      var o = el('option', s.name + ' (' + s.timeframe + ')' + (s.id === d.active ? ' - paper trading' : ''));
      o.value = s.id; strategySelect.appendChild(o);
    });
    d.fees.forEach(function (f) {
      var label = (d.fee_labels || {})[String(f)];
      var o = el('option', f.toFixed(2) + '% per buy/sell' + (label ? ' (' + label + ')' : ''));
      o.value = f; feeSelect.appendChild(o);
    });
    var all = el('option', 'Full history'); all.value = 'all'; startSelect.appendChild(all);
    d.start_years.slice().reverse().forEach(function (y) {
      var o = el('option', 'From 1 Jan ' + y); o.value = String(y); startSelect.appendChild(o);
    });
    d.leverages.forEach(function (lev) {
      var o = el('option', lev === 1 ? 'Off (no borrowing)' : lev + 'x (borrow ' + (lev - 1) + 'x your money)');
      o.value = lev; marginSelect.appendChild(o);
    });
    // A link (?strategy=...) wins; otherwise the last choice; otherwise the active strategy.
    choose(strategySelect, params.get('strategy') || SelectedStrategy.get() || d.active, d.active);
    choose(feeSelect, remembered('fee-v2') || String(d.fees[0]), String(d.fees[0]));
    choose(marginSelect, remembered('margin') || '1', '1');
    choose(startSelect, remembered('start') || 'all', 'all');
    load(); compare();
  });
  strategySelect.addEventListener('change', function () { load(); compare(); });
  feeSelect.addEventListener('change', function () { load(); compare(); });
  marginSelect.addEventListener('change', load);
  startSelect.addEventListener('change', function () { load(); compare(); });

  function info(id) { return strategies.filter(function (x) { return x.id === id; })[0] || {}; }
  function ratio(v) { return v === null || v === undefined ? '-' : '\u00d7' + v.toFixed(2); }
  function fee(v) { return v === null || v === undefined ? 'never (loses even without fees)' : (v >= 5 ? 'above 5%' : v.toFixed(2) + '%'); }

  function load() {
    var id = strategySelect.value;
    // Graded strategies never borrow: margin does not apply to them.
    var graded = info(id).supports_margin === false;
    marginSelect.disabled = graded;
    var leverage = graded ? '1' : marginSelect.value;
    SelectedStrategy.set(id); remember('fee-v2', feeSelect.value); remember('margin', marginSelect.value); remember('start', startSelect.value);
    history.replaceState(null, '', '/strategy?strategy=' + encodeURIComponent(id));
    document.getElementById('status').textContent = 'Running the backtest over the full history...';
    fetch('/api/backtest?strategy=' + encodeURIComponent(id) + '&fee=' + feeSelect.value + '&leverage=' + leverage + '&start=' + startSelect.value)
      .then(function (r) { return r.json(); }).then(function (rep) {
        if (rep.error) { document.getElementById('status').textContent = rep.error; return; }
        render(rep);
      });
  }

  // All strategies side by side, with the same fee and start.
  function compare() {
    var box = document.getElementById('compare'); box.textContent = '';
    document.getElementById('compare-status').textContent = 'Testing every strategy...';
    fetch('/api/compare?fee=' + feeSelect.value + '&start=' + startSelect.value).then(function (r) { return r.json(); }).then(function (d) {
      document.getElementById('compare-status').textContent = d.error || '';
      if (d.error) return;
      var head = el('tr');
      ['Strategy', 'Total result', 'BTC vs holding', 'Worst drop', 'Sharpe', 'Break-even fee', 'Ahead from start years', 'Avg. share in BTC']
        .forEach(function (h, i) { head.appendChild(el('th', h, i ? 'num' : '')); });
      box.appendChild(head);
      d.rows.forEach(function (r) {
        var tr = el('tr');
        if (r.id === strategySelect.value) tr.className = 'selected-row';
        var name = el('td'); var a = el('a', r.name); a.href = '/strategy?strategy=' + encodeURIComponent(r.id);
        a.addEventListener('click', function (e) { e.preventDefault(); strategySelect.value = r.id; load(); compare(); window.scrollTo(0, 0); });
        name.appendChild(a); tr.appendChild(name);
        if (r.error) { var td = el('td', r.error, 'muted'); td.colSpan = 7; tr.appendChild(td); box.appendChild(tr); return; }
        tr.appendChild(el('td', pct(r.total_return_pct), 'num'));
        tr.appendChild(el('td', ratio(r.btc_vs_hold), 'num'));
        tr.appendChild(el('td', drop(r.max_drawdown_pct), 'num'));
        tr.appendChild(el('td', r.sharpe.toFixed(2), 'num'));
        tr.appendChild(el('td', r.break_even_fee_pct === null ? 'never' : (r.break_even_fee_pct >= 5 ? '> 5%' : r.break_even_fee_pct.toFixed(2) + '%'), 'num'));
        tr.appendChild(el('td', r.start_years_ahead + ' of ' + r.start_years, 'num'));
        tr.appendChild(el('td', r.exposure_pct.toFixed(0) + '%', 'num'));
        box.appendChild(tr);
      });
      var hold = d.buy_and_hold;
      var tr = el('tr'); tr.appendChild(el('td', 'Buy and hold', 'secondary'));
      [pct(hold.total_return_pct), '\u00d71.00', drop(hold.max_drawdown_pct), hold.sharpe.toFixed(2), '', '', '100%']
        .forEach(function (v) { tr.appendChild(el('td', v, 'num secondary')); });
      box.appendChild(tr);
    });
  }

  function render(rep) {
    document.getElementById('status').textContent = '';
    var s = rep.strategy, graded = rep.kind === 'exposure';
    document.getElementById('show-on-chart').href = '/chart?tf=' + s.timeframe + '&strategy=' + encodeURIComponent(s.id);
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
    var a = rep.summary, b = rep.buy_and_hold, mt = rep.metrics, bm = rep.buy_and_hold_metrics, mix = rep.exposure_matched;
    var rows = [
      ['Period', day(a.start) + ' to ' + day(a.end), ''],
      ['Total result', pct(a.total_return_pct), pct(b.total_return_pct)],
      ['BTC compared with holding', '\u00d7' + a.btc_vs_hold.toFixed(2) + ' (' + (a.btc_vs_hold >= 1 ? '+' : '') +
        ((a.btc_vs_hold - 1) * 100).toFixed(0) + '% BTC)', '\u00d71.00'],
      ['Per year (average)', pct(a.yearly_pct), pct(b.yearly_pct)],
      ['Worst drop from a peak', '-' + a.max_drawdown_pct.toFixed(1) + '%', '-' + b.max_drawdown_pct.toFixed(1) + '%'],
      ['Return per unit of risk (yearly / worst drop)', a.calmar.toFixed(2), b.calmar.toFixed(2)],
      ['Sharpe ratio (return per unit of daily swings)', mt.sharpe.toFixed(2), bm.sharpe.toFixed(2)],
      ['Sortino ratio (only falling days count as risk)', mt.sortino.toFixed(2), bm.sortino.toFixed(2)],
      ['Share of the 20 best BTC days captured', mt.top20_capture_pct === null ? '-' : mt.top20_capture_pct.toFixed(0) + '%', '100%'],
      ['Break-even fee (per buy/sell) vs holding', fee(mt.break_even_fee_pct), ''],
      ['Traded per year (share of the account)', mt.turnover_per_year === null ? '-' : (mt.turnover_per_year * 100).toFixed(0) + '%', '']
    ];
    if (mix) rows.push(['Same average BTC share, fixed (' + mix.weight_pct.toFixed(0) + '% BTC)',
      pct(mix.total_return_pct) + ' \u2192 strategy \u00d7' + (mix.strategy_vs_mix === null ? '-' : mix.strategy_vs_mix.toFixed(2)), '']);
    if (graded) {
      rows.push(['Changes of the BTC share', String(a.rebalances), '1']);
      rows.push(['Average share in BTC', a.exposure_pct + '%', b.exposure_pct + '%']);
    } else {
      rows.push(['Trades', String(a.trades), '1']);
      rows.push(['Winning trades', a.win_rate_pct + '%', '']);
      rows.push(['Average trade', pct(a.average_trade_pct), '']);
      rows.push(['Best / worst trade', pct(a.best_trade_pct) + ' / ' + pct(a.worst_trade_pct), '']);
      rows.push(['Average days in a trade', a.average_days_held === null ? '-' : String(a.average_days_held), '']);
      rows.push(['Time in the market', a.exposure_pct + '%', b.exposure_pct + '%']);
    }
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

    // If you had started in...
    var sy = document.getElementById('start-years'); sy.textContent = '';
    var sh = el('tr');
    ['Start', 'Strategy', 'Holding', 'BTC vs holding', 'Strategy worst drop', 'Holding worst drop', graded ? 'Share changes' : 'Trades', 'Ahead of holding?']
      .forEach(function (h, i) { sh.appendChild(el('th', h, i ? 'num' : '')); });
    sy.appendChild(sh);
    var ahead = 0;
    rep.by_start_year.slice().reverse().forEach(function (r) {
      var tr = el('tr');
      if (rep.start && rep.start.slice(0, 4) === String(r.year)) tr.className = 'selected-row';
      tr.appendChild(el('td', '1 Jan ' + r.year));
      tr.appendChild(el('td', pct(r.strategy_pct), 'num'));
      tr.appendChild(el('td', pct(r.buy_hold_pct), 'num'));
      tr.appendChild(el('td', '\u00d7' + r.btc_vs_hold.toFixed(2), 'num'));
      tr.appendChild(el('td', drop(r.strategy_drop_pct), 'num'));
      tr.appendChild(el('td', drop(r.buy_hold_drop_pct), 'num'));
      tr.appendChild(el('td', String(r.trades), 'num'));
      var win = r.btc_vs_hold >= 1; if (win) ahead++;
      var cell = el('td', '', 'num'), b = el('span', '', 'badge ' + (win ? 'good' : 'neutral'));
      var ic = el('span', win ? '\u2713' : '\u2013', 'badge-icon'); ic.setAttribute('aria-hidden', 'true');
      b.appendChild(ic); b.appendChild(document.createTextNode(win ? 'yes' : 'no')); cell.appendChild(b);
      tr.appendChild(cell); sy.appendChild(tr);
    });
    document.getElementById('start-years-summary').textContent =
      'Ahead of (or level with) holding from ' + ahead + ' of ' + rep.by_start_year.length + ' start years.';

    // Per year
    var years = document.getElementById('years'); years.textContent = '';
    var yh = el('tr');
    ['Year', 'Strategy', 'Buy and hold', 'Strategy worst drop', 'Buy-and-hold worst drop', graded ? 'Share changes' : 'Trades started', 'Better than holding?']
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

    // Trades (or changes of the BTC share), newest first
    var trades = document.getElementById('trades'); trades.textContent = '';
    document.getElementById('trades-title').textContent = graded ? 'Every change of the BTC share' : 'Every trade';
    if (graded) {
      var gh = el('tr');
      ['#', 'Date', 'Price', 'BTC share before', 'After', 'Traded (share of account)'].forEach(function (h, i) { gh.appendChild(el('th', h, i > 1 ? 'num' : '')); });
      trades.appendChild(gh);
      var list = rep.rebalances.slice().reverse(), shown = list.slice(0, 400);
      shown.forEach(function (r, i) {
        var tr = el('tr');
        tr.appendChild(el('td', String(list.length - i))); tr.appendChild(el('td', day(r.time)));
        tr.appendChild(el('td', money(r.price), 'num'));
        tr.appendChild(el('td', r.from_pct.toFixed(0) + '%', 'num')); tr.appendChild(el('td', r.to_pct.toFixed(0) + '%', 'num'));
        tr.appendChild(el('td', (r.to_pct > r.from_pct ? 'bought ' : 'sold ') + r.traded_pct.toFixed(0) + '%', 'num'));
        trades.appendChild(tr);
      });
      if (list.length > shown.length) { var more = el('tr'); var td = el('td', (list.length - shown.length) + ' older changes not shown', 'muted'); td.colSpan = 6; more.appendChild(td); trades.appendChild(more); }
      return;
    }
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
    return page(
        "BTC Trading - Strategy tester",
        nav_html("strategy")
        + "<main><header class='page-head'><div><h1>Strategy tester</h1>"
        "<p class='muted'>Every strategy in the list, tested over the full history (2013 to now) or from any start year, "
        "with your exchange's fees (Bybit EU by default), next-candle fills and no trades on hours filled in from another exchange.</p></div></header>"
        "<section class='panel'><div class='controls'>"
        "<label>Strategy <select id='strategy'></select></label>"
        "<label>Fees <select id='fee'></select></label>"
        "<label>Margin <select id='margin'></select></label>"
        "<label>Test from <select id='start'></select></label>"
        "<a id='show-on-chart' href='/chart'>Show these trades on the chart &rarr;</a>"
        "<span class='muted' id='status'></span></div>"
        "<p id='description'></p><p class='secondary small' id='rules'></p><p class='muted small' id='origin'></p>"
        "<div class='note-box' id='note'></div><div class='note-box' id='margin-note' hidden></div></section>"
        "<section class='panel'><div class='panel-head'><h2>All strategies compared</h2>"
        "<span class='muted small' id='compare-status'></span></div>"
        "<p class='muted small' style='margin-top:0'>Same fee and start for every strategy. Break-even fee: above it, simply "
        "holding wins. Ahead from start years: how many '1 January' starts end with more BTC than holding.</p>"
        "<div class='table-scroll'><table class='compact' id='compare'></table></div></section>"
        "<section class='panel'><div class='panel-head'><h2>Result vs buy and hold</h2></div>"
        "<div class='table-scroll'><table class='compact' id='summary'></table></div></section>"
        "<section class='panel'><div class='panel-head'><h2>Account value over time</h2>"
        "<span class='muted small'>$10,000 at the start · logarithmic scale: equal steps are equal percentage changes</span></div>"
        "<div class='legend'><span class='legend-item'><span class='legend-key' style='background:var(--series-1)'></span>Strategy</span>"
        "<span class='legend-item'><span class='legend-key' style='background:var(--series-2)'></span>Buy and hold</span></div>"
        "<div id='equity'><div id='equity-chart'></div></div></section>"
        "<section class='panel'><div class='panel-head'><h2>If you had started in&hellip;</h2>"
        "<span class='secondary small' id='start-years-summary'></span></div>"
        "<p class='muted small' style='margin-top:0'>Each row starts with cash on 1 January of that year and runs to now. "
        "&times;1.20 means you would end with 1.2 BTC for every 1 BTC you would have by simply holding.</p>"
        "<div class='table-scroll'><table class='compact' id='start-years'></table></div></section>"
        "<section class='panel'><div class='panel-head'><h2>Year by year</h2><span class='secondary small' id='years-summary'></span></div>"
        "<div class='table-scroll'><table class='compact' id='years'></table></div></section>"
        "<section class='panel'><div class='panel-head'><h2 id='trades-title'>Every trade</h2><span class='muted small'>newest first</span></div>"
        "<div class='scroll-y'><table class='compact' id='trades'></table></div></section></main>",
        head=f"<style>{NAV_CSS}{CHART_CSS}{PAGE_CSS}</style>",
        scripts=f"<script src='{CHART_LIBRARY}'></script><script>{NAV_SCRIPT}{SHARED_SELECTION_SCRIPT}{PAGE_SCRIPT}</script>",
    )
