"""Web dashboard for the paper-trading daemon (zero external dependencies).

Runs a stdlib HTTP server in a daemon thread inside live.py and renders the
paper account: equity + drawdown, open positions marked to the last closed
candle, closed-trade history, live stats vs the backtest expectation band,
and the equity curve. Read-only — it never mutates state.

Container port 8080; mapped to host 8085 in docker-compose.yml
(8081-8084 are taken by the other bots on the box).
"""
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pandas as pd

import config

log = logging.getLogger('dashboard')

PORT        = int(os.environ.get('DASHBOARD_PORT', 8080))
TRADES_PATH = os.path.join('state', 'paper_trades.csv')

_ref = {'state': None}          # live reference to the daemon's state dict


def _unrealized(pos: dict) -> float:
    last = pos.get('last_price')
    if not last:
        return 0.0
    sign = 1 if pos['direction'] == 'long' else -1
    return (last - pos['entry_price']) * pos['qty'] * sign


def snapshot() -> dict:
    state = _ref['state'] or {}
    positions = state.get('positions', [])

    trades, equity_curve = [], [config.INITIAL_CAPITAL]
    stats = {'n': 0, 'wins': 0, 'win_rate': None, 'pf': None,
             'tp': 0, 'sl': 0, 'timeout': 0}
    if os.path.exists(TRADES_PATH):
        df = pd.read_csv(TRADES_PATH)
        if len(df):
            stats['n']    = int(len(df))
            wins          = df['pnl'] > 0
            stats['wins'] = int(wins.sum())
            stats['win_rate'] = round(100 * wins.mean(), 1)
            gp = df.loc[df['pnl'] > 0, 'pnl'].sum()
            gl = abs(df.loc[df['pnl'] <= 0, 'pnl'].sum())
            stats['pf'] = round(float(gp / gl), 2) if gl > 0 else None
            for k in ('tp', 'sl', 'timeout'):
                stats[k] = int((df['result'] == k).sum())
            equity_curve += df['equity_after'].tolist()
            trades = df.tail(50).iloc[::-1].to_dict('records')   # newest first

    equity = state.get('equity', config.INITIAL_CAPITAL)
    peak   = state.get('peak_equity', config.INITIAL_CAPITAL)
    unreal = sum(_unrealized(p) for p in positions)

    return {
        'equity'        : equity,
        'peak_equity'   : peak,
        'drawdown_pct'  : round(100 * (equity / peak - 1), 2) if peak else 0,
        'unrealized'    : round(unreal, 2),
        'mark_equity'   : round(equity + unreal, 2),
        'initial'       : config.INITIAL_CAPITAL,
        'pnl'           : round(equity - config.INITIAL_CAPITAL, 2),
        'positions'     : [{**p, 'unrealized': round(_unrealized(p), 2)}
                           for p in positions],
        'trades'        : trades,
        'stats'         : stats,
        'equity_curve'  : equity_curve,
        'last_cycle'    : state.get('last_cycle'),
        'timeframe'     : config.TIMEFRAME,
        'max_positions' : getattr(config, 'MAX_PORTFOLIO_POSITIONS', 10),
        'backtest_band' : 'PF 1.0–1.4, win 50–55% (2y backtest quarterly range)',
    }


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Pattern Bot — Paper Trading</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg:#1a1a2e; --panel:#0f0f1e; --text:#e0e0e0; --dim:#8888aa;
        --accent:#00d4ff; --green:#06d6a0; --red:#ff4d6d; --edge:#333355; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text);
       font:14px/1.5 'Segoe UI',system-ui,sans-serif; padding:24px; }
h1 { font-size:20px; margin-bottom:4px; }
.sub { color:var(--dim); font-size:12px; margin-bottom:20px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
         gap:12px; margin-bottom:20px; }
.card { background:var(--panel); border:1px solid var(--edge); border-radius:8px;
        padding:14px; }
.card .k { color:var(--dim); font-size:11px; text-transform:uppercase;
           letter-spacing:.5px; }
.card .v { font-size:22px; font-weight:600; margin-top:4px; }
.green { color:var(--green); } .red { color:var(--red); } .accent { color:var(--accent); }
.panel { background:var(--panel); border:1px solid var(--edge); border-radius:8px;
         padding:16px; margin-bottom:20px; }
.panel h2 { font-size:14px; color:var(--accent); margin-bottom:10px; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:var(--dim); font-weight:500; padding:6px 8px;
     border-bottom:1px solid var(--edge); }
td { padding:6px 8px; border-bottom:1px solid #22223a; }
tr:last-child td { border-bottom:none; }
canvas { width:100%; height:220px; }
.band { color:var(--dim); font-size:12px; margin-top:8px; }
@media (max-width:700px){ body{padding:12px} .hide-sm{display:none} }
</style></head><body>
<h1>📈 Pattern Bot — Paper Trading</h1>
<div class="sub" id="sub">loading…</div>
<div class="cards" id="cards"></div>
<div class="panel"><h2>Equity curve (closed trades)</h2>
  <canvas id="curve" height="220"></canvas>
  <div class="band" id="band"></div></div>
<div class="panel"><h2 id="posH">Open positions</h2>
  <table id="posT"></table></div>
<div class="panel"><h2 id="trH">Closed trades (latest 50)</h2>
  <table id="trT"></table></div>
<script>
const fmt = (x,d=2) => x==null ? '—' : Number(x).toLocaleString('en-US',
                       {minimumFractionDigits:d, maximumFractionDigits:d});
const cls = x => x>0 ? 'green' : (x<0 ? 'red' : '');
function nextClose(tfHours){
  const now=Date.now(), step=tfHours*3600e3;
  return new Date(Math.floor(now/step+1)*step+90e3);
}
async function refresh(){
  const r = await fetch('/api/status'); const d = await r.json();
  const tfH = parseFloat(d.timeframe)* (d.timeframe.endsWith('h')?1:1/60);
  document.getElementById('sub').textContent =
    `last cycle: ${d.last_cycle ?? 'none yet'} · next candle close ≈ ` +
    nextClose(tfH).toUTCString().slice(17,25) + ' UTC · auto-refreshes every 60s';
  const s = d.stats;
  document.getElementById('cards').innerHTML = `
    <div class="card"><div class="k">Equity (closed)</div>
      <div class="v">$${fmt(d.equity)}</div></div>
    <div class="card"><div class="k">Mark (last close)</div>
      <div class="v">$${fmt(d.mark_equity)}</div></div>
    <div class="card"><div class="k">PnL</div>
      <div class="v ${cls(d.pnl)}">${d.pnl>=0?'+':''}$${fmt(d.pnl)}</div></div>
    <div class="card"><div class="k">Drawdown</div>
      <div class="v ${cls(d.drawdown_pct)}">${fmt(d.drawdown_pct,2)}%</div></div>
    <div class="card"><div class="k">Trades / Win rate</div>
      <div class="v">${s.n} · ${s.win_rate==null?'—':fmt(s.win_rate,1)+'%'}</div></div>
    <div class="card"><div class="k">Profit factor</div>
      <div class="v accent">${s.pf==null?'—':fmt(s.pf,2)}</div></div>`;
  // positions
  document.getElementById('posH').textContent =
    `Open positions (${d.positions.length}/${d.max_positions})`;
  document.getElementById('posT').innerHTML =
    `<tr><th>Symbol</th><th>Dir</th><th>Pattern</th><th>Entry</th>
     <th class="hide-sm">SL</th><th class="hide-sm">TP</th>
     <th>Bars</th><th>Unrealized</th></tr>` +
    (d.positions.map(p=>`<tr><td>${p.symbol}</td>
      <td class="${p.direction==='long'?'green':'red'}">${p.direction}</td>
      <td>${p.pattern}</td><td>${fmt(p.entry_price,6)}</td>
      <td class="hide-sm">${fmt(p.sl,6)}</td><td class="hide-sm">${fmt(p.tp,6)}</td>
      <td>${p.bars_held}</td>
      <td class="${cls(p.unrealized)}">${p.unrealized>=0?'+':''}$${fmt(p.unrealized)}</td>
      </tr>`).join('') || '<tr><td colspan="8" style="color:var(--dim)">none</td></tr>');
  // trades
  document.getElementById('trH').textContent =
    `Closed trades (latest ${Math.min(50,s.n)} of ${s.n}) — TP ${s.tp} · SL ${s.sl} · timeout ${s.timeout}`;
  document.getElementById('trT').innerHTML =
    `<tr><th>Closed</th><th>Symbol</th><th>Dir</th><th class="hide-sm">Pattern</th>
     <th>Result</th><th>PnL</th><th class="hide-sm">Equity after</th></tr>` +
    (d.trades.map(t=>`<tr><td>${String(t.exit_ts).slice(0,16)}</td>
      <td>${t.symbol}</td>
      <td class="${t.direction==='long'?'green':'red'}">${t.direction}</td>
      <td class="hide-sm">${t.pattern}</td><td>${t.result}</td>
      <td class="${cls(t.pnl)}">${t.pnl>=0?'+':''}$${fmt(t.pnl)}</td>
      <td class="hide-sm">$${fmt(t.equity_after)}</td>
      </tr>`).join('') || '<tr><td colspan="7" style="color:var(--dim)">no closed trades yet</td></tr>');
  // equity curve
  drawCurve(d.equity_curve, d.initial);
  document.getElementById('band').textContent =
    'Backtest expectation band: ' + d.backtest_band;
}
function drawCurve(eq, initial){
  const c = document.getElementById('curve');
  c.width = c.clientWidth * devicePixelRatio;
  c.height = 220 * devicePixelRatio;
  const g = c.getContext('2d'); g.scale(devicePixelRatio, devicePixelRatio);
  const W = c.clientWidth, H = 220, pad = 8;
  g.clearRect(0,0,W,H);
  const lo = Math.min(...eq, initial), hi = Math.max(...eq, initial);
  const y = v => H-pad-(v-lo)/((hi-lo)||1)*(H-2*pad);
  const x = i => pad+(i)/((eq.length-1)||1)*(W-2*pad);
  g.strokeStyle='rgba(255,255,255,.35)'; g.setLineDash([4,4]);
  g.beginPath(); g.moveTo(pad,y(initial)); g.lineTo(W-pad,y(initial)); g.stroke();
  g.setLineDash([]);
  g.strokeStyle='#00d4ff'; g.lineWidth=1.6; g.beginPath();
  eq.forEach((v,i)=>i?g.lineTo(x(i),y(v)):g.moveTo(x(i),y(v))); g.stroke();
}
refresh(); setInterval(refresh, 60000);
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path.startswith('/api/status'):
                body = json.dumps(snapshot(), default=str).encode()
                ctype = 'application/json'
            else:
                body = PAGE.encode()
                ctype = 'text/html; charset=utf-8'
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:                       # never let a render kill the server
            try:
                self.send_error(500, str(e))
            except Exception:
                pass

    def log_message(self, *args):                    # keep daemon logs clean
        pass


def start(state: dict) -> None:
    """Serve the dashboard for the given (live-mutated) state dict."""
    _ref['state'] = state
    server = ThreadingHTTPServer(('0.0.0.0', PORT), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True,
                     name='dashboard').start()
    log.info(f'Dashboard running on http://0.0.0.0:{PORT}')
