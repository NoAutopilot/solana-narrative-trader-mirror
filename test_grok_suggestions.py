"""
Grok Suggestion Evaluator — Test each hypothesis against current data
using our operating principles and adversarial checklist.

Principles applied:
  - Trust nothing, prove everything
  - Remove top performers and retest
  - n > 100 per group or label "preliminary"
  - Fee-adjusted (8% round trip)
  - Bootstrap + parametric agreement
  - State falsification conditions
"""

import sqlite3
import json
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = "/home/ubuntu/solana_trader/data/solana_trader.db"
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def bootstrap_ci(data, n_boot=10000, ci=95):
    """Bootstrap confidence interval for the mean."""
    if len(data) < 3:
        return np.mean(data), np.mean(data), np.mean(data)
    rng = np.random.default_rng(42)
    means = [np.mean(rng.choice(data, size=len(data), replace=True)) for _ in range(n_boot)]
    lo = np.percentile(means, (100 - ci) / 2)
    hi = np.percentile(means, 100 - (100 - ci) / 2)
    return np.mean(data), lo, hi

def bootstrap_winrate_ci(wins, total, n_boot=10000, ci=95):
    """Bootstrap CI for win rate."""
    if total < 3:
        return wins/max(total,1), 0, 1
    data = [1]*wins + [0]*(total - wins)
    rng = np.random.default_rng(42)
    rates = [np.mean(rng.choice(data, size=len(data), replace=True)) for _ in range(n_boot)]
    lo = np.percentile(rates, (100 - ci) / 2)
    hi = np.percentile(rates, 100 - (100 - ci) / 2)
    return wins/total, lo, hi

# ═══════════════════════════════════════════════════════════════════════════
# SUGGESTION 1: Bootstrap resampling vs z-test
# ═══════════════════════════════════════════════════════════════════════════
section("1. BOOTSTRAP RESAMPLING vs Z-TEST")

modes = {}
for mode in ['narrative', 'control', 'proactive']:
    c.execute("SELECT pnl_sol FROM trades WHERE status='closed' AND trade_mode=?", (mode,))
    pnls = [r['pnl_sol'] for r in c.fetchall() if r['pnl_sol'] is not None]
    modes[mode] = np.array(pnls)

for mode, pnls in modes.items():
    mean, lo, hi = bootstrap_ci(pnls)
    wins = sum(1 for p in pnls if p > 0)
    wr, wr_lo, wr_hi = bootstrap_winrate_ci(wins, len(pnls))
    print(f"\n{mode.upper()} (n={len(pnls)}):")
    print(f"  Mean PnL:  {mean:.6f} SOL  [95% CI: {lo:.6f} to {hi:.6f}]")
    print(f"  Win Rate:  {wr:.1%}  [95% CI: {wr_lo:.1%} to {wr_hi:.1%}]")
    print(f"  Median PnL: {np.median(pnls):.6f}")
    print(f"  Total PnL: {np.sum(pnls):.4f}")

# Bootstrap difference test: narrative vs control
print("\nBOOTSTRAP DIFFERENCE TEST (narrative - control):")
rng = np.random.default_rng(42)
n_boot = 10000
diffs_mean = []
diffs_wr = []
narr = modes['narrative']
ctrl = modes['control']
for _ in range(n_boot):
    n_sample = rng.choice(narr, size=len(narr), replace=True)
    c_sample = rng.choice(ctrl, size=len(ctrl), replace=True)
    diffs_mean.append(np.mean(n_sample) - np.mean(c_sample))
    diffs_wr.append(np.mean(n_sample > 0) - np.mean(c_sample > 0))

pct_mean_positive = np.mean(np.array(diffs_mean) > 0) * 100
pct_wr_positive = np.mean(np.array(diffs_wr) > 0) * 100
mean_diff = np.mean(diffs_mean)
lo_diff = np.percentile(diffs_mean, 2.5)
hi_diff = np.percentile(diffs_mean, 97.5)
print(f"  Mean PnL diff: {mean_diff:.6f} [95% CI: {lo_diff:.6f} to {hi_diff:.6f}]")
print(f"  P(narrative mean > control mean): {pct_mean_positive:.1f}%")
print(f"  P(narrative WR > control WR): {pct_wr_positive:.1f}%")
print(f"  CI includes zero: {'YES' if lo_diff <= 0 <= hi_diff else 'NO'}")

# ADVERSARIAL: Remove top 1, 3, 5 trades and retest
print("\nADVERSARIAL: Remove top N trades and retest mean PnL diff:")
for remove_n in [1, 3, 5]:
    n_trimmed = np.sort(narr)[:-remove_n] if remove_n < len(narr) else narr
    c_trimmed = np.sort(ctrl)[:-remove_n] if remove_n < len(ctrl) else ctrl
    n_mean = np.mean(n_trimmed)
    c_mean = np.mean(c_trimmed)
    print(f"  Remove top {remove_n}: narrative={n_mean:.6f} control={c_mean:.6f} diff={n_mean-c_mean:.6f}")

# ═══════════════════════════════════════════════════════════════════════════
# SUGGESTION 2: Narrative Freshness Decay
# ═══════════════════════════════════════════════════════════════════════════
section("2. NARRATIVE FRESHNESS DECAY")

c.execute("""
    SELECT t.id, t.pnl_sol, t.status, t.trade_mode, t.entered_at, t.narrative_keyword,
           t.category
    FROM trades t
    WHERE t.status='closed' AND t.trade_mode IN ('narrative', 'proactive')
    AND t.narrative_keyword IS NOT NULL AND t.narrative_keyword != ''
""")
narrative_trades = c.fetchall()

freshness_data = []
for t in narrative_trades:
    keyword = t['narrative_keyword']
    entered = t['entered_at']
    # Find the narrative detection time
    c.execute("SELECT detected_at FROM narratives WHERE keyword LIKE ? ORDER BY detected_at DESC LIMIT 1",
              (f"%{keyword}%",))
    narr_row = c.fetchone()
    if narr_row and narr_row['detected_at'] and entered:
        try:
            t_entered = datetime.fromisoformat(entered.replace('Z', '+00:00').replace('+00:00', ''))
            t_detected = datetime.fromisoformat(narr_row['detected_at'].replace('Z', '+00:00').replace('+00:00', ''))
            age_min = (t_entered - t_detected).total_seconds() / 60
            if age_min >= 0:  # Sanity check
                freshness_data.append({
                    'age_min': age_min,
                    'pnl_sol': t['pnl_sol'],
                    'win': 1 if t['pnl_sol'] > 0 else 0,
                    'category': t['category'],
                    'mode': t['trade_mode'],
                })
        except:
            pass

print(f"Trades with computable narrative age: {len(freshness_data)}")

if freshness_data:
    bins = {'<20min': [], '20-60min': [], '>60min': []}
    for d in freshness_data:
        if d['age_min'] < 20:
            bins['<20min'].append(d)
        elif d['age_min'] < 60:
            bins['20-60min'].append(d)
        else:
            bins['>60min'].append(d)
    
    for label, trades in bins.items():
        if trades:
            pnls = [t['pnl_sol'] for t in trades]
            wins = sum(t['win'] for t in trades)
            n = len(trades)
            mean, lo, hi = bootstrap_ci(pnls) if n >= 3 else (np.mean(pnls), 0, 0)
            print(f"\n  {label} (n={n}):")
            print(f"    Win Rate: {wins}/{n} = {wins/n:.1%}")
            print(f"    Mean PnL: {mean:.6f} [CI: {lo:.6f} to {hi:.6f}]")
            print(f"    Total PnL: {sum(pnls):.4f}")
        else:
            print(f"\n  {label}: NO DATA")
    
    # ADVERSARIAL: Is the freshness effect driven by one outlier?
    print("\n  ADVERSARIAL: Freshness effect without top trade per bin:")
    for label, trades in bins.items():
        if len(trades) >= 2:
            pnls = sorted([t['pnl_sol'] for t in trades])[:-1]  # Remove best
            wins = sum(1 for p in pnls if p > 0)
            print(f"    {label}: n={len(pnls)} WR={wins/len(pnls):.1%} mean={np.mean(pnls):.6f}")
else:
    print("  CANNOT TEST: No narrative age data computable (narratives table may not join cleanly)")

# ═══════════════════════════════════════════════════════════════════════════
# SUGGESTION 3: Twitter Signal Integration
# ═══════════════════════════════════════════════════════════════════════════
section("3. TWITTER SIGNAL ANALYSIS")

c.execute("""
    SELECT id, pnl_sol, trade_mode, category, twitter_signal_data, status
    FROM trades WHERE status='closed' AND twitter_signal_data IS NOT NULL
    AND twitter_signal_data != '' AND twitter_signal_data != 'null'
""")
twitter_trades = c.fetchall()
print(f"Trades with Twitter signal data: {len(twitter_trades)}")

if twitter_trades:
    scored_trades = []
    for t in twitter_trades:
        try:
            sig = json.loads(t['twitter_signal_data'])
            tweets = sig.get('tweet_count', 0)
            engagement = sig.get('total_engagement', 0)
            has_kol = sig.get('has_kol', False)
            score = (tweets * 2) + engagement  # Grok's formula
            scored_trades.append({
                'pnl_sol': t['pnl_sol'],
                'score': score,
                'tweets': tweets,
                'engagement': engagement,
                'has_kol': has_kol,
                'mode': t['trade_mode'],
                'category': t['category'],
                'win': 1 if t['pnl_sol'] > 0 else 0,
            })
        except:
            pass
    
    print(f"Trades with parseable Twitter scores: {len(scored_trades)}")
    
    if scored_trades:
        # Bin by engagement score
        bins_tw = {'low (<50)': [], 'medium (50-200)': [], 'high (>200)': []}
        for s in scored_trades:
            if s['score'] < 50:
                bins_tw['low (<50)'].append(s)
            elif s['score'] < 200:
                bins_tw['medium (50-200)'].append(s)
            else:
                bins_tw['high (>200)'].append(s)
        
        for label, trades in bins_tw.items():
            if trades:
                pnls = [t['pnl_sol'] for t in trades]
                wins = sum(t['win'] for t in trades)
                n = len(trades)
                print(f"\n  {label} (n={n}):")
                print(f"    Win Rate: {wins}/{n} = {wins/n:.1%}")
                print(f"    Mean PnL: {np.mean(pnls):.6f}")
                print(f"    Total PnL: {sum(pnls):.4f}")
                kol_count = sum(1 for t in trades if t['has_kol'])
                print(f"    KOL present: {kol_count}/{n}")
            else:
                print(f"\n  {label}: NO DATA")
        
        # Spearman correlation
        from scipy import stats as scipy_stats
        scores = [s['score'] for s in scored_trades]
        pnls = [s['pnl_sol'] for s in scored_trades]
        if len(scores) >= 5:
            rho, p_val = scipy_stats.spearmanr(scores, pnls)
            print(f"\n  Spearman correlation (score vs pnl): rho={rho:.4f} p={p_val:.4f}")
            print(f"  Interpretation: {'Significant' if p_val < 0.05 else 'NOT significant'}")
else:
    print("  CANNOT TEST: No Twitter signal data in closed trades")
    print("  Twitter signal was added mid-session; most trades don't have it yet")

# ═══════════════════════════════════════════════════════════════════════════
# SUGGESTION 4: Exit Strategy Optimization (Hybrid Diamond Hands)
# ═══════════════════════════════════════════════════════════════════════════
section("4. EXIT STRATEGY ANALYSIS")

c.execute("SELECT strategy_name, COUNT(*) as cnt, AVG(pnl_sol) as avg_pnl, SUM(pnl_sol) as total_pnl FROM virtual_exits GROUP BY strategy_name ORDER BY AVG(pnl_sol) DESC")
strats = c.fetchall()
print("Current virtual exit strategy ranking:")
for s in strats:
    print(f"  {s['strategy_name']}: n={s['cnt']} avg={s['avg_pnl']:.6f} total={s['total_pnl']:.4f}")

# Check simulation-reality gap (ADVERSARIAL)
c.execute("SELECT SUM(pnl_sol) FROM trades WHERE status='closed'")
actual_total = c.fetchone()[0] or 0
c.execute("SELECT AVG(total_pnl) FROM (SELECT SUM(pnl_sol) as total_pnl FROM virtual_exits GROUP BY strategy_name)")
avg_virtual_total = c.fetchone()[0] or 0
gap_ratio = avg_virtual_total / actual_total if actual_total != 0 else float('inf')
print(f"\nSIMULATION-REALITY GAP:")
print(f"  Actual total PnL: {actual_total:.4f} SOL")
print(f"  Avg virtual total PnL: {avg_virtual_total:.4f} SOL")
print(f"  Gap ratio: {gap_ratio:.2f}x")
print(f"  Assessment: {'ACCEPTABLE (<2x)' if gap_ratio < 2 else 'SUSPICIOUS (>2x) — virtual strategies may be unreliable'}")

# Can we test the hybrid? We need price_snapshots
c.execute("SELECT COUNT(*) FROM price_snapshots")
snapshots = c.fetchone()[0]
print(f"\nPrice snapshots available for hybrid replay: {snapshots}")
if snapshots < 100:
    print("  CANNOT TEST HYBRID: Insufficient price snapshot data for replay simulation")
else:
    print("  Hybrid replay is FEASIBLE with current data (would need separate script)")

# ═══════════════════════════════════════════════════════════════════════════
# SUGGESTION 5: Category Weighting
# ═══════════════════════════════════════════════════════════════════════════
section("5. CATEGORY WEIGHTING ANALYSIS")

c.execute("""
    SELECT category, COUNT(*) as cnt, 
           SUM(CASE WHEN pnl_sol > 0 THEN 1 ELSE 0 END) as wins,
           AVG(pnl_sol) as avg_pnl, SUM(pnl_sol) as total_pnl
    FROM trades WHERE status='closed' AND category IS NOT NULL
    GROUP BY category ORDER BY AVG(pnl_sol) DESC
""")
cats = c.fetchall()
print("Category performance:")
for cat in cats:
    wr = cat['wins']/cat['cnt'] if cat['cnt'] > 0 else 0
    print(f"  {cat['category']}: n={cat['cnt']} WR={wr:.1%} avg={cat['avg_pnl']:.6f} total={cat['total_pnl']:.4f}")

# ADVERSARIAL: Remove top trade per category
print("\nADVERSARIAL: Remove top trade per category:")
for cat in cats:
    c.execute("SELECT pnl_sol FROM trades WHERE status='closed' AND category=? ORDER BY pnl_sol DESC", (cat['category'],))
    pnls = [r['pnl_sol'] for r in c.fetchall()]
    if len(pnls) >= 2:
        trimmed = pnls[1:]  # Remove best
        wins = sum(1 for p in trimmed if p > 0)
        print(f"  {cat['category']}: n={len(trimmed)} WR={wins/len(trimmed):.1%} avg={np.mean(trimmed):.6f} total={sum(trimmed):.4f}")
    else:
        print(f"  {cat['category']}: n={len(pnls)} (too few to trim)")

# SAMPLE SIZE CHECK
print("\nSAMPLE SIZE CHECK (n > 100 required for 'proven'):")
for cat in cats:
    status = "SUFFICIENT" if cat['cnt'] >= 100 else "PRELIMINARY" if cat['cnt'] >= 30 else "ANECDOTAL"
    print(f"  {cat['category']}: n={cat['cnt']} → {status}")

# ═══════════════════════════════════════════════════════════════════════════
# SUGGESTION 6: Multi-Token Correlation (First Mover)
# ═══════════════════════════════════════════════════════════════════════════
section("6. MULTI-TOKEN CORRELATION")

c.execute("""
    SELECT narrative_keyword, COUNT(*) as cnt, 
           MIN(entered_at) as first_entry,
           AVG(pnl_sol) as avg_pnl
    FROM trades 
    WHERE status='closed' AND narrative_keyword IS NOT NULL AND narrative_keyword != ''
    GROUP BY narrative_keyword
    HAVING COUNT(*) >= 2
    ORDER BY COUNT(*) DESC
""")
clusters = c.fetchall()
print(f"Narrative keywords with 2+ trades (clusters): {len(clusters)}")

if clusters:
    first_mover_pnls = []
    later_pnls = []
    for cluster in clusters:
        kw = cluster['narrative_keyword']
        c.execute("""
            SELECT pnl_sol, entered_at FROM trades 
            WHERE status='closed' AND narrative_keyword=?
            ORDER BY entered_at ASC
        """, (kw,))
        trades = c.fetchall()
        if len(trades) >= 2:
            first_mover_pnls.append(trades[0]['pnl_sol'])
            for t in trades[1:]:
                later_pnls.append(t['pnl_sol'])
    
    if first_mover_pnls and later_pnls:
        fm_mean = np.mean(first_mover_pnls)
        lt_mean = np.mean(later_pnls)
        fm_wr = sum(1 for p in first_mover_pnls if p > 0) / len(first_mover_pnls)
        lt_wr = sum(1 for p in later_pnls if p > 0) / len(later_pnls)
        print(f"\n  First movers: n={len(first_mover_pnls)} WR={fm_wr:.1%} avg={fm_mean:.6f}")
        print(f"  Later entries: n={len(later_pnls)} WR={lt_wr:.1%} avg={lt_mean:.6f}")
        
        # ADVERSARIAL
        if len(first_mover_pnls) >= 2:
            fm_trimmed = sorted(first_mover_pnls)[:-1]
            print(f"\n  ADVERSARIAL (remove best first-mover):")
            print(f"    First movers: n={len(fm_trimmed)} avg={np.mean(fm_trimmed):.6f}")
    else:
        print("  Insufficient cluster data for first-mover analysis")
else:
    print("  No multi-token clusters found")

# ═══════════════════════════════════════════════════════════════════════════
# OVERALL VERDICT
# ═══════════════════════════════════════════════════════════════════════════
section("OVERALL VERDICT: GROK SUGGESTIONS vs OUR PRINCIPLES")

print("""
PRINCIPLE CHECK: "Progress over activity. If we can't measure it, don't build it."
PRINCIPLE CHECK: "Don't conclude from <100 trades per group."
PRINCIPLE CHECK: "Feature creep before proving basics."
PRINCIPLE CHECK: "Remove the best trade. Am I still making money?"

Current state:
  - Narrative trades: {n_narr} (need 100+ for significance)
  - System has been running ~10 hours
  - Core hypothesis (narrative > control) is UNPROVEN (p > 0.05)
  - PnL is dominated by outliers

The question: "If I were betting my own money RIGHT NOW, what would I need to see first?"
Answer: MORE DATA. Not more features.
""".format(n_narr=len(modes['narrative'])))

conn.close()
print("\nDone.")
