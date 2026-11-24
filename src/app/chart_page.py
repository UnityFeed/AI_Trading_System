"""
The interactive chart page and the navigation bar shared by the app pages.

The chart uses TradingView's open-source Lightweight Charts library
(Apache 2.0), loaded from jsDelivr at a pinned version. It is built for
live, streaming prices, so a live mode can be added on top later.
"""

from src.reporting.dashboard import FAVICON, page


CHART_LIBRARY = (
    "https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/"
    "dist/lightweight-charts.standalone.production.js"
)

NAV_CSS = """
.app-nav { position: sticky; top: 0; z-index: 10; display: flex; flex-wrap: wrap; align-items: center;
  gap: 8px 6px; padding: 10px 16px; background: color-mix(in srgb, var(--card) 88%, transparent);
  backdrop-filter: saturate(1.4) blur(10px); border-bottom: 1px solid var(--border); }
.app-nav .brand { display: inline-flex; align-items: center; gap: 8px; font-weight: 700; margin-right: 14px; }
.app-nav .brand img { width: 22px; height: 22px; }
.app-nav a { color: var(--text-secondary); text-decoration: none; padding: 6px 12px; border-radius: 999px; font-size: 14px; }
.app-nav a:hover { background: var(--grid); text-decoration: none; }
.app-nav a.active { color: var(--text-primary); background: var(--grid); font-weight: 600; }
.app-nav .spacer { flex: 1; }
.app-nav button { font: inherit; font-size: 14px; font-weight: 600; padding: 7px 14px; border-radius: 999px; border: 0;
  background: var(--series-1); color: #fff; cursor: pointer; box-shadow: var(--shadow); }
.app-nav button:hover { filter: brightness(1.08); }
.app-nav button:disabled { opacity: .6; cursor: progress; }
.run-status { color: var(--text-muted); font-size: 13px; }
select { font: inherit; padding: 5px 8px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--card); color: var(--text-primary); }
.run-log { margin: 0; max-height: 220px; overflow: auto; background: var(--card); color: var(--text-secondary);
  border-bottom: 1px solid var(--border); padding: 8px 16px; font-size: 12px; white-space: pre-wrap; }
"""

NAV_SCRIPT = """
(function () {
  var btn = document.getElementById('run-btn');
  if (!btn) return;
  var log = document.getElementById('run-log'), status = document.getElementById('run-status');
  var started = false;
  function poll() {
    fetch('/api/status').then(function (r) { return r.json(); }).then(function (s) {
      log.textContent = s.log.join('\\n'); log.hidden = s.log.length === 0; log.scrollTop = log.scrollHeight;
      if (s.busy) { btn.disabled = true; status.textContent = 'Running...'; setTimeout(poll, 1000); return; }
      btn.disabled = false;
      status.textContent = s.last_job ? 'Last run ' + s.last_job : '';
      if (started) { status.textContent += ' - reloading'; setTimeout(function () { location.reload(); }, 1200); }
    }).catch(function () { status.textContent = 'The app is not running (start it with start_app.bat).'; btn.disabled = false; });
  }
  btn.addEventListener('click', function () {
    btn.disabled = true; started = true; status.textContent = 'Starting...';
    fetch('/api/run?update=1', {method: 'POST', headers: {'X-App-Action': '1'}}).then(poll, poll);
  });
  fetch('/api/status').then(function (r) { return r.json(); }).then(function (s) {
    if (s.busy) { started = true; poll(); } else if (s.last_job) { status.textContent = 'Last run ' + s.last_job; }
  }).catch(function () {});
})();
"""


# The strategy chosen on any page is the strategy of every page.
SHARED_SELECTION_SCRIPT = r"""
var SelectedStrategy = (function () {
  var KEY = 'selected-strategy';
  function get() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function set(value) { try { localStorage.setItem(KEY, value); } catch (e) {} }
  // Fill a <select> with every strategy and pick: a ?strategy= link, else the
  // last choice, else the active (paper trading) strategy.
  function fill(select, done) {
    fetch('/api/strategies').then(function (r) { return r.json(); }).then(function (d) {
      d.strategies.forEach(function (s) {
        var o = document.createElement('option'); o.value = s.id;
        o.textContent = s.name + ' (' + s.timeframe + ')' + (s.id === d.active ? ' - paper trading' : '');
        select.appendChild(o);
      });
      var wanted = new URLSearchParams(location.search).get('strategy') || get() || d.active;
      select.value = wanted;
      if (select.value !== wanted) select.value = d.active;
      set(select.value);
      done(d);
    });
  }
  return {get: get, set: set, fill: fill};
})();
"""


def nav_html(active: str) -> str:
    def link(href, name, key):
        cls = " class='active'" if key == active else ""
        return f"<a href='{href}'{cls}>{name}</a>"

    return (
        f"<nav class='app-nav'><span class='brand'><img src=\"{FAVICON}\" alt=''>BTC Trading</span>"
        + link("/", "Overview", "overview") + link("/chart", "Chart", "chart")
        + link("/strategy", "Strategy tester", "strategy")
        + "<span class='spacer'></span><span class='run-status' id='run-status'></span>"
        "<button id='run-btn' type='button'>Update data &amp; run paper trader</button></nav>"
        "<pre class='run-log' id='run-log' hidden></pre>"
    )


CHART_CSS = """
:root { --up: #008300; --down: #e34948; --ema20: #6250d6; --ema50: #eb6834; --ema200: #2a78d6;
  --rsi: #6250d6; --macd: #2a78d6; --signal: #eb6834; --atr: #1baf7a; --filled: #a9a8a2; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --up: #0ca30c; --down: #e66767;
  --ema20: #9085e9; --ema50: #d95926; --ema200: #3987e5; --rsi: #9085e9; --macd: #3987e5; --signal: #d95926;
  --atr: #199e70; --filled: #5f5e59; } }
:root[data-theme="dark"] { --up: #0ca30c; --down: #e66767; --ema20: #9085e9; --ema50: #d95926; --ema200: #3987e5;
  --rsi: #9085e9; --macd: #3987e5; --signal: #d95926; --atr: #199e70; --filled: #5f5e59; }
body { height: 100vh; display: flex; flex-direction: column; }
.toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; padding: 10px 16px;
  border-bottom: 1px solid var(--border); background: var(--surface); }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.seg button { font: inherit; border: 0; background: var(--card); color: var(--text-secondary); padding: 5px 12px; cursor: pointer; }
.seg button[aria-pressed="true"] { background: var(--series-1); color: #fff; }
.toggles { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 14px; color: var(--text-secondary); }
.toggles label { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; }
.key { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.replay-bar { gap: 8px 14px; font-size: 14px; }
.replay-bar .replay { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.replay-bar button, .replay-bar input[type=date], .replay-bar select { font: inherit; font-size: 13px; padding: 3px 8px;
  border-radius: 8px; border: 1px solid var(--border); background: var(--card); color: var(--text-primary); cursor: pointer; }
.replay-bar button[aria-pressed=true] { background: var(--text-primary); color: var(--card); }
.replaying #chart-wrap { outline: 2px solid var(--warning); outline-offset: -2px; }
.scenario-strip { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px; padding: 6px 16px 8px;
  font-size: 13px; border-bottom: 1px solid var(--border); background: var(--card); }
.scenario-strip:empty { display: none; }
.scenario-strip .sc { font-variant-numeric: tabular-nums; }
.scenario-strip .sc b { font-weight: 650; }
.scenario-strip .bull { color: var(--up); } .scenario-strip .bear { color: var(--down); }
.state-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 14px; padding: 8px 16px; font-size: 14px;
  border-bottom: 1px solid var(--border); background: var(--card); min-height: 40px; }
.state-strip .badge { font-weight: 500; font-size: 13px; }
#chart-wrap { position: relative; flex: 1; min-height: 420px; }
#chart { position: absolute; inset: 0; }
#readout { position: absolute; top: 8px; left: 12px; z-index: 5; pointer-events: none; font-size: 12px;
  background: color-mix(in srgb, var(--card) 88%, transparent); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 10px; color: var(--text-secondary); font-variant-numeric: tabular-nums; max-width: calc(100% - 100px); }
#readout strong { color: var(--text-primary); }
#readout .r-row { display: flex; flex-wrap: wrap; gap: 2px 12px; }
.note { font-size: 12px; color: var(--text-muted); padding: 6px 16px; border-top: 1px solid var(--border); }
"""

CHART_SCRIPT = r"""
(function () {
  var LWC = window.LightweightCharts;
  var wrap = document.getElementById('chart');
  if (!LWC) { wrap.textContent = 'The chart library could not be loaded (it needs an internet connection).'; return; }

  var TOGGLES = [
    ['ema20', 'EMA 20', '--ema20', true], ['ema50', 'EMA 50', '--ema50', true], ['ema200', 'EMA 200', '--ema200', true],
    ['bb', 'Bollinger', '--text-muted', false], ['trades', 'Trades (B = buy, S = sell)', '--text-primary', true],
    ['volume', 'Volume', '--text-muted', true], ['rsi', 'RSI 14', '--rsi', true],
    ['macd', 'MACD', '--macd', true], ['atr', 'ATR 14', '--atr', false],
    ['structure', 'Structure (swings, BOS / CHoCH)', '--warning', true],
    ['levels', 'Support/resistance + Fibonacci', '--text-muted', true],
    ['patterns', 'Patterns', '--warning', true],
    ['profile', 'Volume profile', '--series-2', false],
    ['scenarios', 'AI scenarios', '--series-1', true]
  ];
  function load(key, fallback) { try { var v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch (e) { return fallback; } }
  function save(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {} }

  var settings = load('chart-settings', {});
  var params = new URLSearchParams(location.search);
  var tf = params.get('tf') || load('chart-tf', '1d');
  if (['1h', '4h', '1d', '1w'].indexOf(tf) < 0) tf = '1d';
  var source = null;  // id of the selected strategy (shared with the other pages)
  var state = null;   // where that strategy stands now (/api/strategy-state)
  // A timeframe that arrived through a link is remembered like a manual choice.
  save('chart-tf', tf);
  var enabled = {};
  TOGGLES.forEach(function (t) { enabled[t[0]] = settings[t[0]] === undefined ? t[3] : settings[t[0]]; });

  var cache = {};   // timeframe -> {candles, indicators, markers, hasMore}
  var structures = {};  // timeframe -> market structure (/api/structure)
  var scenarios = null;  // the AI's scenarios for now or the replay day (/api/scenarios)
  var tools = {};  // timeframe|day -> chart tools (/api/tools)
  // AI forecast horizons per timeframe, in candles (the weekly chart has no AI forecast)
  var HORIZONS = {'1h': [[24, '1 day'], [72, '3 days'], [168, '7 days']], '4h': [[6, '1 day'], [42, '7 days'], [84, '14 days']],
                  '1d': [[7, '7 days'], [14, '14 days'], [30, '30 days']]};
  var PERIOD = {'1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800};
  function horizonFor(frame) {
    var options = HORIZONS[frame]; if (!options) return null;
    var h = load('chart-horizon-' + frame, options[options.length - 1][0]);
    return options.some(function (o) { return o[0] === h; }) ? h : options[options.length - 1][0];
  }
  var horizon = horizonFor(tf);
  var scenarioTf = null, scenarioTimer = null;
  var replay = null;  // replay day (unix seconds of 00:00 UTC) or null = now
  var reveal = false, playing = null;
  var DAY = 86400;
  function limitTime() {  // last candle time shown: the replay day's close, plus the horizon when revealed
    return replay === null ? Infinity : replay + DAY - 1 + (reveal && horizon ? horizon * PERIOD[tf] : 0);
  }
  function shown(c) {  // how many of the loaded candles are visible
    var lim = limitTime(), n = c.candles.length;
    while (n > 0 && c.candles[n - 1][0] > lim) n--;
    return n;
  }
  var chart = null, builtTf = null, series = {}, loading = false, markersLayer = null;

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function fmt(v, digits) { return v === null || v === undefined ? '-' : Number(v).toLocaleString(undefined, {minimumFractionDigits: digits, maximumFractionDigits: digits}); }

  // ---- toolbar --------------------------------------------------------------
  var tfBox = document.getElementById('tf');
  ['1h', '4h', '1d', '1w'].forEach(function (name) {
    var b = document.createElement('button'); b.type = 'button'; b.textContent = name;
    b.setAttribute('aria-pressed', name === tf ? 'true' : 'false');
    b.addEventListener('click', function () {
      tf = name; save('chart-tf', tf);
      tfBox.querySelectorAll('button').forEach(function (x) { x.setAttribute('aria-pressed', x.textContent === tf ? 'true' : 'false'); });
      fillHorizons(); scenarios = null; builtTf = null; renderScenarios();
      show();
    });
    tfBox.appendChild(b);
  });
  var toggleBox = document.getElementById('toggles');
  TOGGLES.forEach(function (t) {
    var label = document.createElement('label');
    var box = document.createElement('input'); box.type = 'checkbox'; box.checked = enabled[t[0]];
    box.addEventListener('change', function () { enabled[t[0]] = box.checked; save('chart-settings', enabled); build(); renderScenarios(); renderTools(); });
    var key = document.createElement('span'); key.className = 'key'; key.style.background = 'var(' + t[2] + ')';
    label.appendChild(box); label.appendChild(key); label.appendChild(document.createTextNode(t[1]));
    toggleBox.appendChild(label);
  });

  // The selected strategy: its backtest trades are marked on the chart and
  // the strip above the chart shows where it stands now.
  var strategySelect = document.getElementById('strategy');
  SelectedStrategy.fill(strategySelect, function () { source = strategySelect.value; show(); loadState(); });
  strategySelect.addEventListener('change', function () {
    source = strategySelect.value; SelectedStrategy.set(source);
    cache = {}; state = null; show(); loadState();
  });

  // AI forecast horizon and replay controls
  var horizonSelect = document.getElementById('horizon');
  function fillHorizons() {
    horizon = horizonFor(tf);
    horizonSelect.textContent = '';
    (HORIZONS[tf] || [[0, 'on 1h / 4h / 1d']]).forEach(function (o) {
      var opt = document.createElement('option'); opt.value = String(o[0]); opt.textContent = o[1]; horizonSelect.appendChild(opt);
    });
    horizonSelect.disabled = !HORIZONS[tf];
    if (horizon) horizonSelect.value = String(horizon);
  }
  fillHorizons();
  horizonSelect.addEventListener('change', function () { horizon = Number(horizonSelect.value); save('chart-horizon-' + tf, horizon); builtTf = null; loadScenarios(); });
  document.getElementById('replay-date').addEventListener('change', function (e) {
    if (!e.target.value) { setReplay(null); return; }
    setReplay(Date.parse(e.target.value + 'T00:00:00Z') / 1000);
  });
  function step(days) {
    var c = cache[tf]; if (!c) return;
    var latest = c.candles[c.candles.length - 1][0];
    var base = replay === null ? latest : replay;
    var next = Math.min(latest, base + days * DAY);
    if (next >= latest && days > 0) { stopPlay(); setReplay(null); return; }
    setReplay(next);
  }
  function stopPlay() { if (playing) { clearInterval(playing); playing = null; } document.getElementById('replay-play').setAttribute('aria-pressed', 'false'); }
  document.getElementById('replay-back').addEventListener('click', function () { stopPlay(); step(-1); });
  document.getElementById('replay-next').addEventListener('click', function () { stopPlay(); step(1); });
  document.getElementById('replay-play').addEventListener('click', function (e) {
    if (playing) { stopPlay(); return; }
    if (replay === null) { var c = cache[tf]; if (c) setReplay(Math.floor((c.candles[c.candles.length - 1][0] - 365 * DAY) / DAY) * DAY); }
    e.target.setAttribute('aria-pressed', 'true');
    playing = setInterval(function () { step(1); }, 700);
  });
  document.getElementById('replay-reveal').addEventListener('change', function (e) { reveal = e.target.checked; builtTf = null; build(); renderScenarios(); });
  document.getElementById('replay-now').addEventListener('click', function () { stopPlay(); setReplay(null); });

  function loadState() {
    var wanted = source;
    fetch('/api/strategy-state?strategy=' + encodeURIComponent(wanted)).then(function (r) { return r.json(); }).then(function (s) {
      if (wanted !== source) return;
      state = s; renderState();
      if (cache[tf]) build();
    });
  }

  function renderState() {
    var strip = document.getElementById('state'); strip.textContent = '';
    if (!state) return;
    function part(text, cls) { var e = document.createElement('span'); e.textContent = text; if (cls) e.className = cls; strip.appendChild(e); return e; }
    var p = state.position, x = state.exposure;
    if (state.kind === 'exposure' && x) {
      part(x.weight_pct.toFixed(0) + '% IN BTC', 'pill strong');
      part('target ' + (x.target_pct === null ? '-' : x.target_pct.toFixed(0) + '%') + ' · trades when the share changes by ' +
           x.band_pct + ' points or more' + (x.last_rebalance ? ' · last change ' + x.last_rebalance.slice(0, 10) : ''));
    } else if (p) {
      part('OPEN', 'pill strong');
      part('Bought ' + p.entry_time.slice(0, 10) + ' at $' + fmt(p.entry_price, 0) + ': ' + (p.result_if_sold_pct > 0 ? '+' : '') +
           p.result_if_sold_pct.toFixed(1) + '% if sold now' + (p.stop_price ? ' · stop $' + fmt(p.stop_price, 0) : ''));
    } else {
      part('NO TRADE', 'pill');
      var last = state.last_closed_trade;
      part(last ? 'Last trade ' + (last.return_pct > 0 ? '+' : '') + last.return_pct.toFixed(1) + '% (sold ' + last.exit_time.slice(0, 10) + ')' : 'No trades yet');
    }
    state.rules.forEach(function (r) {
      var b = document.createElement('span'); b.className = 'badge ' + (r.met ? 'good' : 'neutral');
      var icon = document.createElement('span'); icon.className = 'badge-icon'; icon.setAttribute('aria-hidden', 'true');
      icon.textContent = r.met === null ? '?' : (r.met ? '\u2713' : '\u2013');
      b.appendChild(icon); b.appendChild(document.createTextNode(r.role)); b.title = r.rule; strip.appendChild(b);
    });
    var st = structures[tf];
    if (st && replay === null) part(tf + ' structure: ' + st.trend.toUpperCase() + (st.swing_high ? ' · swing high ' + fmt(st.swing_high, 0) : '') +
                 (st.swing_low ? ' · swing low ' + fmt(st.swing_low, 0) : ''), 'pill');
    if (state.signal) part(state.signal.action + ' SIGNAL at the next open' +
      (state.signal.target_pct !== undefined ? ' (to ' + state.signal.target_pct.toFixed(0) + '% BTC)' : ''), 'pill warn');
    part('as of the ' + state.strategy.timeframe + ' close of ' + state.candle_time.slice(0, 16).replace('T', ' ') + ' UTC', 'muted');
  }

  // ---- data -----------------------------------------------------------------
  function fetchChunk(before) {
    var url = '/api/chart?tf=' + tf + '&limit=3000&trades=' + encodeURIComponent(source) + (before ? '&before=' + before : '');
    return fetch(url).then(function (r) { return r.json(); });
  }
  function loadStructure() {
    var frame = tf;
    if (structures[frame]) return;
    fetch('/api/structure?tf=' + frame).then(function (r) { return r.json(); }).then(function (d) {
      structures[frame] = d;
      if (frame === tf && cache[tf]) build();
      renderState();
    });
  }
  function scenarioUrl() {  // the forecast made at the last close of the replay day (or the latest close)
    return '/api/scenarios?tf=' + tf + '&h=' + horizon + (replay !== null ? '&date=' + (replay + DAY - PERIOD[tf]) : '');
  }
  function loadScenarios() {
    if (scenarioTimer) { clearTimeout(scenarioTimer); scenarioTimer = null; }
    if (!HORIZONS[tf]) { scenarios = null; renderScenarios(); return; }
    var asked = scenarioUrl();
    fetch(asked).then(function (r) { return r.json(); }).then(function (d) {
      if (asked !== scenarioUrl()) return;
      if (d.status === 'learning') { scenarios = d; renderScenarios(); scenarioTimer = setTimeout(loadScenarios, 5000); return; }
      var first = !scenarios || scenarios.status === 'learning' || scenarioTf !== tf;
      scenarios = d; scenarioTf = tf; renderScenarios();
      if (cache[tf]) { if (first) builtTf = null; build(); }
    });
  }
  function ready() { return scenarios && scenarios.scenarios && !scenarios.error && scenarioTf === tf; }
  function loadTools() {
    var key = tf + '|' + (replay === null ? 'now' : replay);
    if (tools[key]) { renderTools(); if (cache[tf]) build(); return; }
    fetch('/api/tools?tf=' + tf + (replay !== null ? '&until=' + replay : '')).then(function (r) { return r.json(); }).then(function (d) {
      tools[key] = d; renderTools();
      if (cache[tf]) build();
    });
  }
  function currentTools() { return tools[tf + '|' + (replay === null ? 'now' : replay)]; }
  function pct(v) { return Math.round(v * 100) + '%'; }
  function renderScenarios() {
    var box = document.getElementById('scenarios'); box.textContent = '';
    document.body.classList.toggle('replaying', replay !== null);
    if (!enabled.scenarios) return;
    function el(tag, text, cls) { var e = document.createElement(tag); e.textContent = text; if (cls) e.className = cls; box.appendChild(e); return e; }
    if (!HORIZONS[tf]) { el('span', 'AI forecast: available on the 1h, 4h and 1d charts', 'muted'); return; }
    if (!scenarios) return;
    if (scenarios.status === 'learning') { el('span', scenarios.message, 'muted'); return; }
    if (scenarios.error) { el('span', 'AI forecast: ' + scenarios.error, 'muted'); return; }
    var when = tf === '1d' ? scenarios.candle_time.slice(0, 10) : scenarios.candle_time.slice(0, 16).replace('T', ' ') + ' UTC';
    el('strong', (replay !== null ? 'REPLAY · ' : '') + 'AI forecast (' + tf + '), next ' + scenarios.horizon_label + ' from the ' + when + ' close:');
    scenarios.scenarios.forEach(function (s) {
      var name = {bull: 'Bull', bear: 'Bear', range: 'Range'}[s.kind];
      var where = s.kind === 'range' ? ' (' + fmt(scenarios.stop, 0) + ' - ' + fmt(scenarios.target, 0) + ')' : ' to ' + fmt(s.level, 0) + ' in ~' + (s.typical_days >= 1 ? Math.round(s.typical_days) + ' d' : Math.round(s.typical_days * 24) + ' h');
      var e = el('span', '', 'sc ' + s.kind); var b = document.createElement('b'); b.textContent = name + ' ' + pct(s.probability);
      e.appendChild(b); e.appendChild(document.createTextNode(where)); e.title = s.meaning + '. Proven wrong by ' + s.proven_wrong_by + '.';
    });
    if (scenarios.outcome && (replay === null || reveal)) {
      var top = scenarios.scenarios[0].kind, o = scenarios.outcome;
      el('span', 'What happened: ' + o.kind.toUpperCase() + ' after ' + o.days + (tf === '1d' ? ' d ' : ' candles ') + (o.kind === top ? '(top scenario right)' : '(top scenario was ' + top + ')'), 'sc ' + o.kind);
    } else if (scenarios.outcome === null && replay !== null && reveal) {
      el('span', 'What happened: not decided yet', 'muted');
    }
    var w = scenarios.weights || {};
    el('span', 'AI trusts: ' + Object.keys(w).sort(function (a, b) { return w[b] - w[a]; }).map(function (k) { return k + ' ' + pct(w[k]); }).join(' · '), 'muted');
    var sc = scenarios.score_so_far || {};
    el('span', sc.scored ? 'its score up to this day: ' + (sc.brier_skill >= 0 ? '+' : '') + (sc.brier_skill * 100).toFixed(1) + '% vs the base rate, top scenario right ' + pct(sc.top_hit_rate) + ' of ' + sc.scored.toLocaleString() + ' forecasts'
                         : 'no scored forecasts yet', 'muted');
    var tr = scenarios.track_record;
    if (tr && replay === null) el('span', tr.scored ? 'live log: ' + tr.scored + ' scored, top right ' + pct(tr.top_scenario_hit_rate) : 'live log: started, none scored yet', 'muted');
    var t = scenarios.training;
    if (t) {
      var mem = (t.memorised_skill || []).filter(function (v) { return v !== null; });
      var e = el('span', 'training: version "' + t.version_now + '", honest ' + (t.honest_skill >= 0 ? '+' : '') + (t.honest_skill * 100).toFixed(1) + '%' +
        (mem.length ? ' · memorised passes ' + mem.map(function (v) { return (v >= 0 ? '+' : '') + (v * 100).toFixed(1) + '%'; }).join(' / ') + ' (inflated, not real)' : ''), 'muted');
      e.title = 'Versions chosen per year on earlier years only: ' + t.choice_per_year.slice(-6).map(function (x) { return x.year + ' ' + x.config; }).join(', ');
    } else if (replay === null) {
      el('span', 'no training session yet: one version, learned live', 'muted');
    }
  }
  function renderTools() {
    var box = document.getElementById('tools-strip'); box.textContent = '';
    var t = currentTools();
    if (!t || t.error) return;
    function el(text, cls) { var e = document.createElement('span'); e.textContent = text; if (cls) e.className = cls; box.appendChild(e); return e; }
    el('Regime (' + tf + '): ' + t.regime + (t.adx !== null ? ' · ADX ' + t.adx : ''));
    if (enabled.patterns) {
      var live = t.patterns.filter(function (p) { return p.status === 'candidate' || p.status === 'confirmed'; });
      var rec = t.pattern_track_record || {};
      el(live.length ? 'Patterns: ' + live.map(function (p) {
        var r = rec[p.kind]; return p.kind + ' (' + p.status + (r && r.hit_rate !== null ? ', hit ' + pct(r.hit_rate) + ' in the past' : '') + ')';
      }).join(', ') : 'Patterns: none active', 'muted');
    }
    if (enabled.profile && t.volume_profile) el('Volume profile ' + t.volume_profile.days + ' d (estimate): POC ' + fmt(t.volume_profile.poc, 0) +
      ', value area ' + fmt(t.volume_profile.val, 0) + ' - ' + fmt(t.volume_profile.vah, 0), 'muted');
  }
  function prepend(c, d) {  // add an older chunk; candles already loaded (overlapping requests) are skipped
    var first = c.candles[0][0], keep = 0;
    while (keep < d.candles.length && d.candles[keep][0] < first) keep++;
    c.candles = d.candles.slice(0, keep).concat(c.candles);
    Object.keys(c.indicators).forEach(function (k) { c.indicators[k] = d.indicators[k].slice(0, keep).concat(c.indicators[k]); });
    c.hasMore = d.has_more;
  }
  function ensureLoaded(time, done) {  // load older chunks until the replay day is in the cache
    var c = cache[tf];
    if (!c || c.candles[0][0] <= time || !c.hasMore) { done(); return; }
    fetchChunk(c.candles[0][0]).then(function (d) {
      if (!d.candles.length) { c.hasMore = false; done(); return; }
      prepend(c, d);
      ensureLoaded(time, done);
    });
  }
  function setReplay(day) {
    replay = day;
    var input = document.getElementById('replay-date');
    input.value = day === null ? '' : new Date(day * 1000).toISOString().slice(0, 10);
    builtTf = null;  // a fresh view around the replay day
    renderState();
    var go = function () { loadScenarios(); loadTools(); };
    if (day === null) go(); else ensureLoaded(day, go);
  }
  function show() {
    loadStructure();
    if (!scenarios || scenarioTf !== tf) loadScenarios();
    loadTools();
    if (cache[tf]) { build(); return; }
    wrap.textContent = 'Loading ' + tf + ' candles...';
    fetchChunk(null).then(function (d) {
      var ps = d.price_source, label = document.getElementById('price-source');
      var cap = function (x) { return x.charAt(0).toUpperCase() + x.slice(1); };
      if (ps && label) label.textContent = 'Price: ' + cap(ps.exchange) +
        ' BTC/USD for every hour since ' + new Date(ps.from * 1000).toISOString().slice(0, 10) + ' (one source); ' +
        ps.filled_hours.toLocaleString() + ' of ' + ps.hours.toLocaleString() + ' hours it lacks are filled from ' +
        ps.fallbacks.map(cap).join(', then ') + ' (grey). Strategies, paper trading and the AI use the same prices.';
      cache[tf] = {candles: d.candles, indicators: d.indicators, markers: d.markers, hasMore: d.has_more};
      build();
    });
  }
  function loadOlder() {
    var c = cache[tf];
    if (loading || !c || !c.hasMore) return;
    loading = true;
    var frame = tf;
    fetchChunk(c.candles[0][0]).then(function (d) {
      loading = false;
      if (frame !== tf || !d.candles.length) { c.hasMore = false; return; }
      prepend(c, d);
      var range = chart.timeScale().getVisibleLogicalRange();
      fill();
      if (range) chart.timeScale().setVisibleLogicalRange({from: range.from + d.candles.length, to: range.to + d.candles.length});
    }, function () { loading = false; });
  }

  // ---- chart ----------------------------------------------------------------
  function line(color, pane, extra) {
    var opts = {color: css(color), lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false};
    Object.keys(extra || {}).forEach(function (k) { opts[k] = extra[k]; });
    return chart.addSeries(LWC.LineSeries, opts, pane);
  }

  function build() {
    var c = cache[tf];
    if (!c || !shown(c)) return;  // replay day not loaded yet (older candles still on their way)
    var range = chart && builtTf === tf ? chart.timeScale().getVisibleLogicalRange() : null;
    if (chart) chart.remove();
    wrap.textContent = '';
    chart = LWC.createChart(wrap, {
      autoSize: true,
      layout: {background: {type: 'solid', color: css('--surface')}, textColor: css('--text-secondary'),
               fontFamily: getComputedStyle(document.body).fontFamily, panes: {separatorColor: css('--border')}},
      grid: {vertLines: {color: css('--grid')}, horzLines: {color: css('--grid')}},
      rightPriceScale: {borderColor: css('--border')},
      timeScale: {borderColor: css('--border'), timeVisible: tf !== '1d', secondsVisible: false, rightOffset: 5, minBarSpacing: 0.05},
      crosshair: {mode: LWC.CrosshairMode.Normal},
      localization: {priceFormatter: function (p) { return fmt(p, 2); }}
    });
    builtTf = tf;
    series = {};
    markersLayer = null;
    series.candles = chart.addSeries(LWC.CandlestickSeries, {
      upColor: css('--up'), downColor: css('--down'), wickUpColor: css('--up'), wickDownColor: css('--down'),
      borderVisible: false, priceLineVisible: true
    }, 0);
    if (enabled.ema20) series.ema_20 = line('--ema20', 0);
    if (enabled.ema50) series.ema_50 = line('--ema50', 0);
    if (enabled.ema200) series.ema_200 = line('--ema200', 0);
    if (enabled.bb) {
      series.bb_upper = line('--text-muted', 0, {lineWidth: 1, lineStyle: LWC.LineStyle.Dashed});
      series.bb_middle = line('--text-muted', 0, {lineWidth: 1});
      series.bb_lower = line('--text-muted', 0, {lineWidth: 1, lineStyle: LWC.LineStyle.Dashed});
    }
    var pane = 1, small = [];
    if (enabled.volume) {
      series.volume = chart.addSeries(LWC.HistogramSeries, {priceFormat: {type: 'volume'}, priceLineVisible: false, lastValueVisible: false}, pane);
      small.push(pane++);
    }
    if (enabled.rsi) {
      series.rsi_14 = line('--rsi', pane, {lastValueVisible: true});
      [70, 30].forEach(function (lvl) {
        series.rsi_14.createPriceLine({price: lvl, color: css('--text-muted'), lineWidth: 1, lineStyle: LWC.LineStyle.Dotted, axisLabelVisible: true, title: ''});
      });
      small.push(pane++);
    }
    if (enabled.macd) {
      series.macd_hist = chart.addSeries(LWC.HistogramSeries, {priceLineVisible: false, lastValueVisible: false}, pane);
      series.macd = line('--macd', pane);
      series.macd_signal = line('--signal', pane);
      small.push(pane++);
    }
    if (enabled.atr) { series.atr_14 = line('--atr', pane, {lastValueVisible: true}); small.push(pane++); }

    fill();
    // Market structure: the last swing high and low (what has to break next).
    var stl = structures[tf];
    if (enabled.structure && stl && replay === null) {  // today's levels: not shown while replaying the past
      if (stl.swing_high) series.candles.createPriceLine({price: stl.swing_high, color: css('--up'), lineWidth: 1,
        lineStyle: LWC.LineStyle.Dotted, axisLabelVisible: true, title: 'swing high'});
      if (stl.swing_low) series.candles.createPriceLine({price: stl.swing_low, color: css('--down'), lineWidth: 1,
        lineStyle: LWC.LineStyle.Dotted, axisLabelVisible: true, title: 'swing low'});
    }
    // Scenarios: dashed paths from the last close to each scenario's level, on the daily chart;
    // target / stop lines on the other timeframes.
    if (enabled.scenarios && ready()) {
      var lastTime = scenarios.time, lastClose = scenarios.close;
      var colors = {bull: css('--up'), bear: css('--down'), range: css('--text-muted')};
      if (HORIZONS[tf]) {
        scenarios.scenarios.forEach(function (s) {
          var end = Math.floor(Date.parse(s.by) / 1000 / PERIOD[tf]) * PERIOD[tf];
          var name = s.kind + ' ' + Math.round(s.probability * 100) + '%';
          if (s.kind === 'range') {
            [scenarios.target, scenarios.stop].forEach(function (level, k) {
              var band = chart.addSeries(LWC.LineSeries, {color: colors.range, lineWidth: 1, lineStyle: LWC.LineStyle.Dotted,
                priceLineVisible: false, lastValueVisible: k === 0, title: k === 0 ? name : '', crosshairMarkerVisible: false});
              band.setData([{time: lastTime, value: level}, {time: end, value: level}]);
            });
            return;
          }
          var path = chart.addSeries(LWC.LineSeries, {color: colors[s.kind], lineWidth: 2, lineStyle: LWC.LineStyle.Dashed,
            priceLineVisible: false, lastValueVisible: true, title: name, crosshairMarkerVisible: false});
          path.setData([{time: lastTime, value: lastClose}, {time: end, value: s.level}]);
        });
      } else {
        series.candles.createPriceLine({price: scenarios.target, color: colors.bull, lineWidth: 1,
          lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: 'bull target'});
        series.candles.createPriceLine({price: scenarios.stop, color: colors.bear, lineWidth: 1,
          lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: 'bear target'});
      }
    }
    // Chart tools as known on the shown day: support/resistance, Fibonacci, volume profile, patterns.
    var tl = currentTools();
    if (tl && !tl.error) {
      if (enabled.levels) {
        tl.zones.forEach(function (z) {
          series.candles.createPriceLine({price: (z.low + z.high) / 2, color: z.kind === 'support' ? css('--up') : css('--down'),
            lineWidth: z.touches >= 4 ? 2 : 1, lineStyle: LWC.LineStyle.Solid, axisLabelVisible: false,
            title: (z.kind === 'support' ? 'S' : 'R') + ' x' + z.touches});
        });
        if (tl.fibonacci) tl.fibonacci.levels.filter(function (f) { return ['1.414', '2', '2.618'].indexOf(f.name) < 0; }).forEach(function (f) {
          series.candles.createPriceLine({price: f.price, color: css('--text-muted'), lineWidth: 1,
            lineStyle: LWC.LineStyle.SparseDotted, axisLabelVisible: false, title: 'fib ' + f.name});
        });
      }
      if (enabled.profile && tl.volume_profile) {
        var vp = tl.volume_profile;
        series.candles.createPriceLine({price: vp.poc, color: css('--series-2'), lineWidth: 2, lineStyle: LWC.LineStyle.Solid, axisLabelVisible: true, title: 'POC'});
        series.candles.createPriceLine({price: vp.vah, color: css('--series-2'), lineWidth: 1, lineStyle: LWC.LineStyle.Dotted, axisLabelVisible: false, title: 'VAH'});
        series.candles.createPriceLine({price: vp.val, color: css('--series-2'), lineWidth: 1, lineStyle: LWC.LineStyle.Dotted, axisLabelVisible: false, title: 'VAL'});
      }
      if (enabled.patterns) {
        var pc = {bull: css('--up'), bear: css('--down'), either: css('--warning')};
        tl.patterns.forEach(function (p) {
          var color = pc[p.direction] || css('--warning');
          var outline = chart.addSeries(LWC.LineSeries, {color: color, lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false});
          outline.setData(p.points.map(function (q) { return {time: q.time, value: q.price}; }));
          [p.neckline, p.lower].forEach(function (seg) {
            if (!seg || seg[1].time <= seg[0].time) return;
            var ln = chart.addSeries(LWC.LineSeries, {color: color, lineWidth: 1, lineStyle: LWC.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false});
            ln.setData(seg.map(function (q) { return {time: q.time, value: q.price}; }));
          });
          if (p.status === 'confirmed' && p.target) series.candles.createPriceLine({price: p.target, color: color, lineWidth: 1,
            lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: p.kind + ' target'});
        });
      }
    }
    // An open trade: dashed lines at the buy price and the stop.
    if (enabled.trades && state && state.position && replay === null) {
      var pos = state.position;
      series.candles.createPriceLine({price: pos.entry_price, color: css('--series-1'), lineWidth: 1,
        lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: 'bought'});
      if (pos.stop_price) series.candles.createPriceLine({price: pos.stop_price, color: css('--down'), lineWidth: 1,
        lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: 'stop'});
    }
    // Price pane gets most of the room; each indicator pane a fixed share.
    var panes = chart.panes();
    if (panes[0]) panes[0].setStretchFactor(small.length ? 3.2 : 1);
    small.forEach(function (i) { if (panes[i]) panes[i].setStretchFactor(i === 1 && enabled.volume ? 0.6 : 1); });

    var n = shown(c);
    if (range) chart.timeScale().setVisibleLogicalRange(range);
    else chart.timeScale().setVisibleLogicalRange({from: n - (enabled.scenarios && ready() ? Math.max(150, horizon * 4) : (tf === '1d' ? 365 : 300)),
      to: n + (enabled.scenarios && ready() ? horizon + 10 : 5)});  // room for the scenario paths

    chart.timeScale().subscribeVisibleLogicalRangeChange(function (r) { if (r && r.from < 50) loadOlder(); });
    chart.subscribeCrosshairMove(readout);
    readout(null);
  }

  function fill() {
    var c = cache[tf], ind = c.indicators;
    var cs = c.candles.slice(0, shown(c)), lim = limitTime();  // replay: nothing after the shown day
    var up = css('--up'), down = css('--down'), filled = css('--filled');
    var candleData = cs.map(function (k) {
      var d = {time: k[0], open: k[1], high: k[2], low: k[3], close: k[4]};
      if (k[6]) { d.color = filled; d.wickColor = filled; }
      return d;
    });
    // Empty future days, so the scenario paths get real width (the chart spaces bars by count, not by date).
    if (enabled.scenarios && ready() && cs.length) {
      var period = PERIOD[tf], lastBar = cs[cs.length - 1][0], until = (scenarios.time || lastBar) + (scenarios.horizon_candles + 5) * period;
      for (var future = lastBar + period; future <= until; future += period) candleData.push({time: future});
    }
    series.candles.setData(candleData);
    ['ema_20', 'ema_50', 'ema_200', 'bb_upper', 'bb_middle', 'bb_lower', 'rsi_14', 'macd', 'macd_signal', 'atr_14'].forEach(function (name) {
      if (!series[name]) return;
      var data = [];
      cs.forEach(function (k, i) { var v = ind[name][i]; if (v !== null) data.push({time: k[0], value: v}); });
      series[name].setData(data);
    });
    if (series.macd_hist) {
      var data = [];
      cs.forEach(function (k, i) { var v = ind.macd_hist[i]; if (v !== null) data.push({time: k[0], value: v, color: v >= 0 ? up : down}); });
      series.macd_hist.setData(data);
    }
    if (series.volume) {
      var upVol = css('--up'), downVol = css('--down');
      series.volume.setData(cs.map(function (k) {
        return {time: k[0], value: k[5], color: (k[4] >= k[1] ? upVol : downVol) + '80'};
      }));
    }
    var first = c.candles[0][0], ink = css('--text-primary');
    var marks = [];
    if (enabled.trades) {
      marks = c.markers.filter(function (m) { return m.time >= first && m.time <= lim; }).map(function (m) {
        return m.side === 'buy'
          ? {time: m.time, position: 'belowBar', shape: 'arrowUp', color: ink, text: m.label || 'B'}
          : {time: m.time, position: 'aboveBar', shape: 'arrowDown', color: ink, text: m.label || 'S'};
      });
      if (state && state.signal && replay === null) {
        var lastTime = c.candles[c.candles.length - 1][0];
        marks.push(state.signal.action === 'BUY'
          ? {time: lastTime, position: 'belowBar', shape: 'circle', color: css('--warning'), text: 'BUY signal'}
          : {time: lastTime, position: 'aboveBar', shape: 'circle', color: css('--warning'), text: 'SELL signal'});
      }
    }
    var st = structures[tf];
    if (enabled.structure && st) {
      var muted = css('--text-muted'), up = css('--up'), down = css('--down');
      var known = replay === null ? Infinity : replay + DAY;  // swings confirmed by the replay day's close
      st.pivots.forEach(function (p) {
        if (p.time < first || Date.parse(p.confirmed) / 1000 > known) return;
        marks.push(p.kind === 'high'
          ? {time: p.time, position: 'aboveBar', shape: 'circle', size: 0.5, color: muted, text: p.label || 'H'}
          : {time: p.time, position: 'belowBar', shape: 'circle', size: 0.5, color: muted, text: p.label || 'L'});
      });
      st.events.forEach(function (e) {
        if (e.time < first || e.kind === 'sweep' || e.time > lim) return;
        marks.push(e.direction === 'up'
          ? {time: e.time, position: 'belowBar', shape: 'arrowUp', color: up, text: e.kind}
          : {time: e.time, position: 'aboveBar', shape: 'arrowDown', color: down, text: e.kind});
      });
    }
    var tl = currentTools();
    if (enabled.patterns && tl && !tl.error) {
      tl.patterns.forEach(function (p) {
        if (p.label_time < first) return;
        var bullish = p.direction === 'bull', color = bullish ? up : (p.direction === 'bear' ? down : css('--warning'));
        marks.push({time: p.label_time, position: bullish ? 'belowBar' : 'aboveBar', shape: 'square', size: 0.6, color: color,
                    text: p.kind + ' (' + p.status + ')'});
      });
    }
    marks.sort(function (a, b) { return a.time - b.time; });
    // One markers layer per chart, updated in place (never stacked).
    if (markersLayer) markersLayer.setMarkers(marks);
    else if (marks.length) markersLayer = LWC.createSeriesMarkers(series.candles, marks);
  }

  var box = document.getElementById('readout');
  function readout(param) {
    var c = cache[tf];
    if (!c || !c.candles.length) return;
    var i = Math.max(0, shown(c) - 1);
    if (param && param.time !== undefined) {
      var lo = 0, hi = c.candles.length - 1;
      while (lo < hi) { var mid = (lo + hi) >> 1; if (c.candles[mid][0] < param.time) lo = mid + 1; else hi = mid; }
      i = lo;
    }
    var k = c.candles[i], ind = c.indicators;
    var date = new Date(k[0] * 1000).toISOString().replace('T', ' ').slice(0, tf === '1d' ? 10 : 16) + ' UTC';
    box.textContent = '';
    function row(items) {
      var r = document.createElement('div'); r.className = 'r-row';
      items.forEach(function (it) {
        var s = document.createElement('span'); s.appendChild(document.createTextNode(it[0] + ' '));
        var b = document.createElement('strong'); b.textContent = it[1]; s.appendChild(b); r.appendChild(s);
      });
      box.appendChild(r);
    }
    row([[date + (k[6] ? ' (filled from another exchange)' : ''), ''], ['O', fmt(k[1], 2)], ['H', fmt(k[2], 2)], ['L', fmt(k[3], 2)], ['C', fmt(k[4], 2)]]);
    var extra = [];
    if (enabled.ema20) extra.push(['EMA 20', fmt(ind.ema_20[i], 2)]);
    if (enabled.ema50) extra.push(['EMA 50', fmt(ind.ema_50[i], 2)]);
    if (enabled.ema200) extra.push(['EMA 200', fmt(ind.ema_200[i], 2)]);
    if (enabled.bb) extra.push(['BB', fmt(ind.bb_lower[i], 0) + ' / ' + fmt(ind.bb_upper[i], 0)]);
    if (extra.length) row(extra);
    var lower = [];
    if (enabled.volume) lower.push(['Vol', fmt(k[5], 2)]);
    if (enabled.rsi) lower.push(['RSI', fmt(ind.rsi_14[i], 1)]);
    if (enabled.macd) lower.push(['MACD', fmt(ind.macd[i], 1) + ' / ' + fmt(ind.macd_signal[i], 1)]);
    if (enabled.atr) lower.push(['ATR', fmt(ind.atr_14[i], 2)]);
    if (lower.length) row(lower);
  }

  if (window.matchMedia) window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', build);
})();
"""


def chart_page() -> str:
    return page(
        "BTC Trading - Chart",
        nav_html("chart")
        + "<div class='toolbar'><div class='seg' id='tf' role='group' aria-label='Timeframe'></div>"
        "<div class='toggles' id='toggles'></div>"
        "<label class='secondary' style='font-size:14px'>Strategy: <select id='strategy'></select></label></div>"
        "<div class='toolbar replay-bar'><label>AI forecast <select id='horizon'></select></label>"
        "<span class='replay'>Replay from <input type='date' id='replay-date' aria-label='Replay date'>"
        "<button type='button' id='replay-back' aria-label='One day back'>&#9664; day</button>"
        "<button type='button' id='replay-next' aria-label='One day forward'>day &#9654;</button>"
        "<button type='button' id='replay-play'>&#9654; play</button>"
        "<label><input type='checkbox' id='replay-reveal'> show what happened</label>"
        "<button type='button' id='replay-now'>back to now</button></span></div>"
        "<div class='state-strip' id='state'></div><div class='scenario-strip' id='scenarios'></div>"
        "<div class='scenario-strip' id='tools-strip'></div>"
        "<div id='chart-wrap'><div id='readout'></div><div id='chart'></div></div>"
        "<div class='note'><span id='price-source'></span> Scroll or drag to move back in time (older candles load "
        "automatically), pinch or mouse wheel to zoom. Grey candles contain hours filled in from another exchange "
        "(outage or missing hour). Times in UTC. Chart by TradingView Lightweight Charts.</div>",
        head=f"<style>{NAV_CSS}{CHART_CSS}</style>",
        scripts=f"<script src='{CHART_LIBRARY}'></script><script>{NAV_SCRIPT}{SHARED_SELECTION_SCRIPT}{CHART_SCRIPT}</script>",
    )
