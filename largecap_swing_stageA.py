#!/usr/bin/env python3
"""
Large-Cap Swing Stage A — Full Event Study
Runs against universe_snapshot on VPS via local SQLite copy.
"""

import sqlite3
import pandas as pd
import numpy as np
import json
import sys
from datetime import datetime, timedelta

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "/root/solana_trader/data/solana_trader.db"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/root/solana_trader/reports/new_programs"

# ── CONFIG ──────────────────────────────────────────────────────────
UNIVERSE_GATES = {
    "liq_usd": 100_000,
    "vol_h24": 100_000,
    "age_hours": 48,
}
MIN_OBS_PER_HOUR = 30
GAP_START = "2026-03-13T06:27:00"
GAP_END   = "2026-03-13T18:43:00"
HORIZONS_H = [1, 4, 24]
COSTS = [0.005, 0.010, 0.015]
BOOTSTRAP_N = 10_000
WINSOR_PCT = (1, 99)

np.random.seed(42)

# ── STEP 1: LOAD DATA ──────────────────────────────────────────────
print("Loading universe_snapshot...")
conn = sqlite3.connect(DB_PATH)

query = """
SELECT 
    snapshot_at,
    mint_address,
    token_symbol,
    price_usd,
    liq_usd,
    vol_h24,
    vol_h1,
    vol_m5,
    age_hours,
    eligible,
    spam_flag,
    round_trip_pct
FROM universe_snapshot
WHERE price_usd IS NOT NULL
  AND price_usd > 0
ORDER BY snapshot_at, mint_address
"""
df = pd.read_sql_query(query, conn)
conn.close()
print(f"  Loaded {len(df):,} rows, {df['mint_address'].nunique()} tokens")

# Parse timestamps
df['ts'] = pd.to_datetime(df['snapshot_at'].str.replace(r'\+00:00$', '', regex=True))
df = df.sort_values(['mint_address', 'ts']).reset_index(drop=True)

# ── STEP 2: POINT-IN-TIME UNIVERSE FILTER ──────────────────────────
print("Applying point-in-time universe gates...")
mask = (
    (df['liq_usd'] >= UNIVERSE_GATES['liq_usd']) &
    (df['vol_h24'] >= UNIVERSE_GATES['vol_h24']) &
    (df['age_hours'] >= UNIVERSE_GATES['age_hours']) &
    (df['spam_flag'] == 0) &
    (df['eligible'] == 1)
)
df_univ = df[mask].copy()
print(f"  Universe rows: {len(df_univ):,}, tokens: {df_univ['mint_address'].nunique()}")

# Exclude gap window
gap_mask = (df_univ['ts'] > GAP_START) & (df_univ['ts'] <= GAP_END)
df_univ = df_univ[~gap_mask].copy()
print(f"  After gap exclusion: {len(df_univ):,} rows")

# ── STEP 3: BUILD HOURLY BARS ──────────────────────────────────────
print("Building hourly bars...")
df_univ['hour'] = df_univ['ts'].dt.floor('h')

def build_hourly_bars(group):
    """Build OHLCV bar from 1-minute data for one token-hour."""
    if len(group) < MIN_OBS_PER_HOUR:
        return None
    sorted_g = group.sort_values('ts')
    return pd.Series({
        'open': sorted_g['price_usd'].iloc[0],
        'high': sorted_g['price_usd'].max(),
        'low': sorted_g['price_usd'].min(),
        'close': sorted_g['price_usd'].iloc[-1],
        'volume_h1': sorted_g['vol_h1'].iloc[-1],  # latest reading
        'n_obs': len(sorted_g),
        'token_symbol': sorted_g['token_symbol'].iloc[0],
        'avg_round_trip_pct': sorted_g['round_trip_pct'].mean(),
    })

bars = df_univ.groupby(['mint_address', 'hour']).apply(build_hourly_bars).dropna()
bars = bars.reset_index()
bars = bars.sort_values(['mint_address', 'hour']).reset_index(drop=True)

# Exclude hours that fall in the gap window
bars_gap_mask = (bars['hour'] >= GAP_START) & (bars['hour'] <= GAP_END)
bars = bars[~bars_gap_mask].copy()

print(f"  Hourly bars: {len(bars):,}, tokens: {bars['mint_address'].nunique()}")
print(f"  Hour range: {bars['hour'].min()} to {bars['hour'].max()}")

# ── STEP 4: COMPUTE TECHNICAL INDICATORS ───────────────────────────
print("Computing technical indicators...")

def compute_indicators(token_bars):
    """Compute SMAs and other indicators for a single token's hourly bars."""
    tb = token_bars.sort_values('hour').copy()
    tb['sma_4h'] = tb['close'].rolling(4, min_periods=4).mean()
    tb['sma_12h'] = tb['close'].rolling(12, min_periods=12).mean()
    tb['sma_12h_lag4'] = tb['sma_12h'].shift(4)
    tb['vol_sma_12h'] = tb['volume_h1'].rolling(12, min_periods=12).mean()
    tb['high_12h'] = tb['high'].rolling(12, min_periods=12).max()
    tb['low_12h'] = tb['low'].rolling(12, min_periods=12).min()
    tb['range_12h_pct'] = (tb['high_12h'] - tb['low_12h']) / tb['sma_12h']
    tb['prev_close'] = tb['close'].shift(1)
    return tb

# group_keys=False but mint_address is in the df columns, so it should survive
# The issue is that groupby('mint_address') uses it as grouper and drops it from the frame
# Fix: set include_groups=False or just re-add it
bars_list = []
for mint, group in bars.groupby('mint_address'):
    tb = compute_indicators(group)
    tb['mint_address'] = mint
    bars_list.append(tb)
bars_ind = pd.concat(bars_list, ignore_index=True)
bars_ind = bars_ind.dropna(subset=['sma_12h', 'sma_4h', 'sma_12h_lag4', 'vol_sma_12h']).copy()
print(f"  Bars with indicators: {len(bars_ind):,}")
print(f"  Columns: {list(bars_ind.columns)}")

# ── STEP 5: SIGNAL DETECTION ──────────────────────────────────────
print("Detecting signals...")

# Signal 1: Pullback in Uptrend
pullback_mask = (
    (bars_ind['sma_12h'] > bars_ind['sma_12h_lag4']) &  # uptrend
    (bars_ind['close'] < bars_ind['sma_4h']) &            # pullback
    (bars_ind['close'] > bars_ind['sma_12h']) &           # not collapsed
    (bars_ind['volume_h1'] >= 0.5 * bars_ind['vol_sma_12h'])  # volume confirmation
)
pullback_events = bars_ind[pullback_mask].copy()
pullback_events['signal'] = 'pullback_in_uptrend'
print(f"  Pullback events: {len(pullback_events)}")

# Signal 2: Breakout from Consolidation
breakout_mask = (
    (bars_ind['range_12h_pct'] < 0.10) &                  # prior consolidation
    (bars_ind['close'] > bars_ind['high_12h'].shift(1)) &  # breakout above prior 12h high
    (bars_ind['volume_h1'] >= 2.0 * bars_ind['vol_sma_12h']) &  # volume surge
    (bars_ind['prev_close'].notna()) &
    (abs(bars_ind['open'] - bars_ind['prev_close']) / bars_ind['prev_close'] < 0.05)  # no gap artifact
)
breakout_events = bars_ind[breakout_mask].copy()
breakout_events['signal'] = 'breakout_from_consolidation'
print(f"  Breakout events: {len(breakout_events)}")

all_events = pd.concat([pullback_events, breakout_events], ignore_index=True)
print(f"  Total signal events: {len(all_events)}")

# ── STEP 6: COMPUTE FORWARD RETURNS ───────────────────────────────
print("Computing forward returns...")

# Ensure mint_address and hour are regular columns (not index)
all_events = all_events.reset_index(drop=True)

# Build a lookup: (mint_address, hour) -> close price
close_lookup = bars.set_index(['mint_address', 'hour'])['close'].to_dict()

for h in HORIZONS_H:
    col = f'r_fwd_{h}h'
    # Vectorized lookup using list comprehension
    future_prices = [
        close_lookup.get((m, hr + pd.Timedelta(hours=h)))
        for m, hr in zip(all_events['mint_address'], all_events['hour'])
    ]
    all_events[col] = future_prices
    # Convert to return
    all_events[col] = (all_events[col] / all_events['close'] - 1).where(
        all_events[col].notna() & (all_events['close'] > 0)
    )

for h in HORIZONS_H:
    col = f'r_fwd_{h}h'
    n_valid = all_events[col].notna().sum()
    print(f"  {col}: {n_valid} valid forward returns")

# ── STEP 7: EVENT STUDY ANALYSIS ──────────────────────────────────
print("Running event study analysis...")

def winsorize(arr, pct_low=1, pct_high=99):
    lo = np.percentile(arr, pct_low)
    hi = np.percentile(arr, pct_high)
    return np.clip(arr, lo, hi)

def bootstrap_ci(arr, stat_fn, n_boot=BOOTSTRAP_N, ci=0.95):
    """Bootstrap confidence interval for a statistic."""
    if len(arr) < 5:
        return (np.nan, np.nan)
    boot_stats = np.array([
        stat_fn(np.random.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    alpha = (1 - ci) / 2
    return (np.percentile(boot_stats, alpha * 100), np.percentile(boot_stats, (1 - alpha) * 100))

def concentration_metrics(gross_returns):
    """Top-1 and top-3 contributor share of total P&L."""
    if len(gross_returns) == 0 or gross_returns.sum() == 0:
        return np.nan, np.nan
    abs_pnl = np.abs(gross_returns)
    total = abs_pnl.sum()
    sorted_pnl = np.sort(abs_pnl)[::-1]
    top1 = sorted_pnl[0] / total if total > 0 else np.nan
    top3 = sorted_pnl[:3].sum() / total if total > 0 else np.nan
    return top1, top3

results = []

for signal_name in ['pullback_in_uptrend', 'breakout_from_consolidation']:
    sig_events = all_events[all_events['signal'] == signal_name]
    
    for h in HORIZONS_H:
        col = f'r_fwd_{h}h'
        valid = sig_events[col].dropna().values
        
        if len(valid) == 0:
            for cost in COSTS:
                results.append({
                    'signal': signal_name,
                    'horizon': f'+{h}h' if h < 24 else '+1d',
                    'cost': cost,
                    'N': 0,
                    'winsorized_mean_gross': np.nan,
                    'winsorized_mean_net': np.nan,
                    'median_gross': np.nan,
                    'median_net': np.nan,
                    'pct_positive_net': np.nan,
                    'ci_mean_net_lo': np.nan,
                    'ci_mean_net_hi': np.nan,
                    'ci_median_net_lo': np.nan,
                    'ci_median_net_hi': np.nan,
                    'top1_share': np.nan,
                    'top3_share': np.nan,
                    'gates_passed': 'N/A (no events)',
                })
            continue
        
        gross_winsorized = winsorize(valid, *WINSOR_PCT)
        top1, top3 = concentration_metrics(valid)
        
        for cost in COSTS:
            net = valid - cost
            net_winsorized = winsorize(net, *WINSOR_PCT)
            
            ci_mean = bootstrap_ci(net_winsorized, np.mean)
            ci_median = bootstrap_ci(net, np.median)
            
            pct_pos = (net > 0).mean()
            
            # Gate check
            gates = {
                'G1_N>=20': len(valid) >= 20,
                'G2_wmean_net>0': np.mean(net_winsorized) > 0,
                'G3_median_net>0': np.median(net) > 0,
                'G4_ci_mean_lo>0': ci_mean[0] > 0 if not np.isnan(ci_mean[0]) else False,
                'G5_ci_median_lo>0': ci_median[0] > 0 if not np.isnan(ci_median[0]) else False,
                'G6_pct_pos>50': pct_pos > 0.5,
                'G7_top1<30': top1 < 0.3 if not np.isnan(top1) else False,
                'G8_top3<50': top3 < 0.5 if not np.isnan(top3) else False,
            }
            all_pass = all(gates.values())
            failed = [k for k, v in gates.items() if not v]
            
            results.append({
                'signal': signal_name,
                'horizon': f'+{h}h' if h < 24 else '+1d',
                'cost': cost,
                'N': len(valid),
                'winsorized_mean_gross': round(float(np.mean(gross_winsorized)) * 100, 3),
                'winsorized_mean_net': round(float(np.mean(net_winsorized)) * 100, 3),
                'median_gross': round(float(np.median(valid)) * 100, 3),
                'median_net': round(float(np.median(net)) * 100, 3),
                'pct_positive_net': round(float(pct_pos) * 100, 1),
                'ci_mean_net_lo': round(float(ci_mean[0]) * 100, 3) if not np.isnan(ci_mean[0]) else None,
                'ci_mean_net_hi': round(float(ci_mean[1]) * 100, 3) if not np.isnan(ci_mean[1]) else None,
                'ci_median_net_lo': round(float(ci_median[0]) * 100, 3) if not np.isnan(ci_median[0]) else None,
                'ci_median_net_hi': round(float(ci_median[1]) * 100, 3) if not np.isnan(ci_median[1]) else None,
                'top1_share': round(float(top1) * 100, 1) if not np.isnan(top1) else None,
                'top3_share': round(float(top3) * 100, 1) if not np.isnan(top3) else None,
                'all_gates_pass': all_pass,
                'failed_gates': ', '.join(failed) if failed else 'NONE',
            })

results_df = pd.DataFrame(results)

# ── STEP 8: SAVE RESULTS ──────────────────────────────────────────
import os
os.makedirs(OUT_DIR, exist_ok=True)

results_df.to_csv(f"{OUT_DIR}/largecap_swing_stageA_results.csv", index=False)
print(f"\nResults saved to {OUT_DIR}/largecap_swing_stageA_results.csv")

# Save event details
event_cols = ['signal', 'mint_address', 'token_symbol', 'hour', 'close', 'volume_h1',
              'sma_4h', 'sma_12h', 'r_fwd_1h', 'r_fwd_4h', 'r_fwd_24h']
all_events[event_cols].to_csv(f"{OUT_DIR}/largecap_swing_stageA_events.csv", index=False)

# Save universe stats
univ_stats = {
    'total_snapshot_rows': int(len(df)),
    'universe_rows_after_gates': int(len(df_univ)),
    'distinct_tokens_in_universe': int(df_univ['mint_address'].nunique()),
    'hourly_bars': int(len(bars)),
    'bars_with_indicators': int(len(bars_ind)),
    'pullback_events': int(len(pullback_events)),
    'breakout_events': int(len(breakout_events)),
    'total_events': int(len(all_events)),
    'hour_range_start': str(bars['hour'].min()),
    'hour_range_end': str(bars['hour'].max()),
    'gap_window': f"{GAP_START} to {GAP_END}",
}
with open(f"{OUT_DIR}/largecap_swing_stageA_universe_stats.json", 'w') as f:
    json.dump(univ_stats, f, indent=2)

# ── STEP 9: PRINT SUMMARY ─────────────────────────────────────────
print("\n" + "="*70)
print("STAGE A RESULTS SUMMARY")
print("="*70)

any_pass = results_df['all_gates_pass'].any() if 'all_gates_pass' in results_df.columns else False

for signal_name in ['pullback_in_uptrend', 'breakout_from_consolidation']:
    print(f"\n--- {signal_name} ---")
    sig_res = results_df[results_df['signal'] == signal_name]
    for _, row in sig_res.iterrows():
        status = "PASS" if row.get('all_gates_pass', False) else "FAIL"
        print(f"  {row['horizon']} @ {row['cost']*100:.1f}% cost: N={row['N']}, "
              f"wmean_net={row['winsorized_mean_net']}%, "
              f"median_net={row['median_net']}%, "
              f"CI=[{row['ci_mean_net_lo']}, {row['ci_mean_net_hi']}], "
              f"{status} [{row.get('failed_gates', '')}]")

print(f"\n{'='*70}")
if any_pass:
    print("VERDICT: GO — at least one scenario passed all gates")
else:
    n_events = len(all_events)
    if n_events == 0:
        print("VERDICT: BLOCKED — no signal events detected")
    else:
        print("VERDICT: NO-GO — no scenario passed all gates")
print("="*70)

# Save verdict
verdict = "GO" if any_pass else ("BLOCKED" if len(all_events) == 0 else "NO-GO")
with open(f"{OUT_DIR}/largecap_swing_stageA_verdict.txt", 'w') as f:
    f.write(verdict)

print(f"\nVerdict: {verdict}")
print("Done.")
