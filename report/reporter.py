import os
import logging
from typing import List

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from backtest.engine import Trade
import config

log = logging.getLogger(__name__)


def _to_df(trades: List[Trade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([vars(t) for t in trades])


def compute_stats(trades: List[Trade], capital_base: float = None) -> dict:
    df = _to_df(trades)
    if df.empty:
        return {}

    if capital_base is None:
        capital_base = config.INITIAL_CAPITAL

    total  = len(df)
    wins   = (df['pnl'] > 0).sum()
    losses = (df['pnl'] <= 0).sum()

    gp = df.loc[df['pnl'] > 0, 'pnl'].sum()
    gl = abs(df.loc[df['pnl'] <= 0, 'pnl'].sum())

    equity     = df['pnl'].cumsum() + capital_base
    run_max    = equity.cummax()
    max_dd     = ((equity - run_max) / run_max).min()

    pnl_pct    = df['pnl'] / capital_base
    sharpe     = (pnl_pct.mean() / pnl_pct.std() * np.sqrt(252)
                  if pnl_pct.std() > 0 else 0.0)

    return {
        'total_trades'  : int(total),
        'win_rate_%'    : round(wins / total * 100, 2),
        'profit_factor' : round(gp / gl, 2) if gl > 0 else float('inf'),
        'total_pnl_$'   : round(df['pnl'].sum(), 2),
        'avg_win_$'     : round(df.loc[df['pnl'] > 0, 'pnl'].mean(), 2) if wins else 0,
        'avg_loss_$'    : round(df.loc[df['pnl'] <= 0, 'pnl'].mean(), 2) if losses else 0,
        'max_drawdown_%': round(max_dd * 100, 2),
        'sharpe'        : round(sharpe, 2),
        'tp_hits'       : int((df['result'] == 'tp').sum()),
        'sl_hits'       : int((df['result'] == 'sl').sum()),
        'timeouts'      : int((df['result'] == 'timeout').sum()),
    }


def per_pattern_stats(trades: List[Trade]) -> pd.DataFrame:
    df = _to_df(trades)
    if df.empty:
        return pd.DataFrame()
    rows = []
    for pat, grp in df.groupby('pattern'):
        n    = len(grp)
        wins = (grp['pnl'] > 0).sum()
        rows.append({
            'pattern'   : pat,
            'trades'    : n,
            'win_%'     : round(wins / n * 100, 1),
            'total_pnl' : round(grp['pnl'].sum(), 2),
            'avg_pnl'   : round(grp['pnl'].mean(), 2),
        })
    return pd.DataFrame(rows).sort_values('total_pnl', ascending=False)


def save_report(trades: List[Trade], label: str = 'all', capital_base: float = None) -> None:
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    df = _to_df(trades)
    if df.empty:
        log.warning('No trades — nothing to report.')
        return

    if capital_base is None:
        capital_base = config.INITIAL_CAPITAL

    stats  = compute_stats(trades, capital_base)
    pat_df = per_pattern_stats(trades)

    print(f'\n{"═" * 55}')
    print(f'  BACKTEST REPORT  [{label}]')
    if capital_base != config.INITIAL_CAPITAL:
        n_syms = df['symbol'].nunique() if 'symbol' in df.columns else '?'
        print(f'  (capital base: ${capital_base:,.0f} = {n_syms} symbols × '
              f'${config.INITIAL_CAPITAL:,.0f} each, independently capitalized)')
    print(f'{"═" * 55}')
    for k, v in stats.items():
        print(f'  {k:<22} {v}')
    print(f'{"─" * 55}')
    print('\n  Per-Pattern Breakdown:')
    print(pat_df.to_string(index=False))
    print(f'{"═" * 55}\n')

    csv_path = os.path.join(config.REPORT_DIR, f'trades_{label}.csv')
    df.to_csv(csv_path, index=False)
    log.info(f'Trade log → {csv_path}')

    _plot(df, stats, pat_df, label, capital_base)


def _plot(df: pd.DataFrame, stats: dict,
          pat_df: pd.DataFrame, label: str, capital_base: float = None) -> None:
    if capital_base is None:
        capital_base = config.INITIAL_CAPITAL

    BG, PANEL  = '#1a1a2e', '#0f0f1e'
    TEXT       = '#e0e0e0'
    ACCENT     = '#00d4ff'
    GREEN, RED = '#06d6a0', '#ff4d6d'
    EDGE       = '#333355'

    fig = plt.figure(figsize=(16, 10), facecolor=BG)
    gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.45, wspace=0.35)

    # ── Equity curve (top, full width) ──────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    equity = df['pnl'].cumsum() + capital_base
    ax1.plot(equity.values, color=ACCENT, linewidth=1.4)
    ax1.fill_between(range(len(equity)), capital_base, equity.values,
                     where=equity.values >= capital_base,
                     alpha=0.15, color=GREEN)
    ax1.fill_between(range(len(equity)), capital_base, equity.values,
                     where=equity.values < capital_base,
                     alpha=0.15, color=RED)
    ax1.axhline(capital_base, color='white',
                linewidth=0.5, linestyle='--', alpha=0.4)
    ax1.set_title(f'Equity Curve — {label}', color=TEXT, fontsize=13, pad=10)
    ax1.set_xlabel('Trade #', color=TEXT)
    ax1.set_ylabel('Capital (USDT)', color=TEXT)
    ax1.tick_params(colors=TEXT)
    ax1.set_facecolor(PANEL)
    for sp in ax1.spines.values():
        sp.set_edgecolor(EDGE)
    summary = (f"Trades: {stats['total_trades']}  |  "
               f"Win%: {stats['win_rate_%']}%  |  "
               f"PF: {stats['profit_factor']}  |  "
               f"Sharpe: {stats['sharpe']}  |  "
               f"MaxDD: {stats['max_drawdown_%']}%  |  "
               f"PnL: ${stats['total_pnl_$']:+,.2f}")
    ax1.text(0.01, 0.04, summary, transform=ax1.transAxes,
             color=TEXT, fontsize=8, alpha=0.8)

    # ── Win rate by pattern ──────────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    if not pat_df.empty:
        cols = [GREEN if v >= 50 else RED for v in pat_df['win_%']]
        ax2.barh(pat_df['pattern'], pat_df['win_%'], color=cols, alpha=0.8)
        ax2.axvline(50, color='white', linewidth=0.8, linestyle='--', alpha=0.5)
        ax2.set_title('Win Rate % by Pattern', color=TEXT, fontsize=11)
        ax2.set_xlabel('Win %', color=TEXT)
        ax2.tick_params(colors=TEXT)
        ax2.set_facecolor(PANEL)
        for sp in ax2.spines.values():
            sp.set_edgecolor(EDGE)

    # ── Total P&L by pattern ─────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    if not pat_df.empty:
        cols2 = [GREEN if v >= 0 else RED for v in pat_df['total_pnl']]
        ax3.barh(pat_df['pattern'], pat_df['total_pnl'], color=cols2, alpha=0.8)
        ax3.axvline(0, color='white', linewidth=0.8, linestyle='--', alpha=0.5)
        ax3.set_title('Total P&L (USDT) by Pattern', color=TEXT, fontsize=11)
        ax3.set_xlabel('P&L (USDT)', color=TEXT)
        ax3.tick_params(colors=TEXT)
        ax3.set_facecolor(PANEL)
        for sp in ax3.spines.values():
            sp.set_edgecolor(EDGE)

    plt.suptitle('Chart Pattern Backtester', color='white', fontsize=16, y=1.01)
    out = os.path.join(config.REPORT_DIR, f'report_{label}.png')
    plt.savefig(out, dpi=150, bbox_inches='tight', facecolor=BG)
    plt.close()
    log.info(f'Chart → {out}')