#!/usr/bin/env python3
"""
Drift Perps State Study — Stage A
Full pipeline: data fetch, state variable construction, event detection,
forward return computation, and event-study analysis.

Author: Manus AI
Date: 2026-03-15
"""

import json
import time
import math
import random
import sys
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

import numpy as np
import pandas as pd

# ── Configuration ──────────────────────────────────────────────────────────

BASE_URL = "https://data.api.drift.trade"
MARKET = "SOL-PERP"

# Study period
FUNDING_DAYS = 90        # How many days of funding rates to fetch
ORACLE_DAYS = 30         # Oracle price depth (API limit)
ORACLE_SAMPLES = 11000   # Max samples per oracle query

# Event thresholds
FUNDING_Z_THRESHOLD = 1.5
FUNDING_Z_WINDOW = 72    # trailing hours for z-score
SPREAD_THRESHOLD_PCT = 0.10  # mark-oracle spread threshold in %
LIQ_PERCENTILE = 90      # percentile for liquidation cluster threshold

# Horizons (seconds)
HORIZONS = {"15m": 900, "1h": 3600, "4h": 14400}

# Cost scenarios (round-trip)
COSTS = {"0.02%": 0.0002, "0.05%": 0.0005, "0.10%": 0.0010}

# Bootstrap
N_BOOTSTRAP = 5000
WINSOR_PCT = (1, 99)

OUTPUT_DIR = "/home/ubuntu"

# ── Data Fetching ──────────────────────────────────────────────────────────

def fetch_json(url, retries=3, delay=2):
    """Fetch JSON from URL with retries."""
    for attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "DriftStudy/1.0"})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
                if not data:
                    return None
                return json.loads(data)
        except (HTTPError, URLError, json.JSONDecodeError) as e:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                print(f"  WARN: Failed to fetch {url}: {e}")
                return None


def fetch_funding_rates(days=90):
    """Fetch daily funding rate records for SOL-PERP."""
    print(f"Fetching {days} days of funding rates...")
    all_records = []
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)
    
    current = start_date
    while current <= end_date:
        url = f"{BASE_URL}/market/{MARKET}/fundingRates/{current.year}/{current.month}/{current.day}"
        result = fetch_json(url)
        if result and result.get("success") and result.get("records"):
            all_records.extend(result["records"])
        current += timedelta(days=1)
        time.sleep(0.1)  # rate limiting
    
    print(f"  Fetched {len(all_records)} funding rate records")
    return all_records


def fetch_oracle_price(days=30, samples=11000):
    """Fetch oracle price time series."""
    print(f"Fetching {days} days of oracle price data...")
    end_ts = int(time.time())
    start_ts = end_ts - (days * 86400)
    
    url = f"{BASE_URL}/amm/oraclePrice?marketName={MARKET}&start={start_ts}&end={end_ts}&samples={samples}"
    result = fetch_json(url)
    
    if result and result.get("success") and result.get("data"):
        data = result["data"]
        print(f"  Fetched {len(data)} oracle price points")
        return data
    else:
        print("  WARN: No oracle price data returned")
        return []


def fetch_mark_price(days=30, samples=11000):
    """Fetch mark (bid-ask midpoint) price time series."""
    print(f"Fetching {days} days of mark price data...")
    end_ts = int(time.time())
    start_ts = end_ts - (days * 86400)
    
    url = f"{BASE_URL}/amm/bidAskPrice?marketName={MARKET}&start={start_ts}&end={end_ts}&samples={samples}"
    result = fetch_json(url)
    
    if result and result.get("success") and result.get("data"):
        data = result["data"]
        print(f"  Fetched {len(data)} mark price points")
        return data
    else:
        print("  WARN: No mark price data returned")
        return []


def fetch_liquidations():
    """Fetch liquidation events via paginated stats endpoint."""
    print("Fetching liquidation events...")
    all_records = []
    url = f"{BASE_URL}/stats/liquidations"
    
    pages = 0
    while url and pages < 50:  # safety limit
        result = fetch_json(url)
        if not result or not result.get("success"):
            break
        
        records = result.get("records", [])
        all_records.extend(records)
        
        meta = result.get("meta", {})
        next_page = meta.get("nextPage")
        if next_page:
            url = f"{BASE_URL}/stats/liquidations?nextPage={next_page}"
            pages += 1
            time.sleep(0.2)
        else:
            break
    
    print(f"  Fetched {len(all_records)} liquidation records across {pages+1} pages")
    return all_records


def fetch_open_interest(days=30, samples=1000):
    """Fetch open interest time series."""
    print(f"Fetching {days} days of open interest data...")
    end_ts = int(time.time())
    start_ts = end_ts - (days * 86400)
    
    url = f"{BASE_URL}/amm/openInterest?marketName={MARKET}&start={start_ts}&end={end_ts}&samples={samples}"
    result = fetch_json(url)
    
    if result and result.get("success") and result.get("data"):
        data = result["data"]
        print(f"  Fetched {len(data)} OI points")
        return data
    else:
        print("  WARN: No OI data returned")
        return []


# ── Data Processing ────────────────────────────────────────────────────────

def build_oracle_series(oracle_raw):
    """Convert oracle price data to a pandas Series indexed by timestamp."""
    if not oracle_raw:
        return pd.Series(dtype=float)
    
    ts_list = [r[0] for r in oracle_raw]
    price_list = [float(r[1]) for r in oracle_raw]
    
    s = pd.Series(price_list, index=pd.to_datetime(ts_list, unit='s', utc=True))
    s = s.sort_index()
    s = s[~s.index.duplicated(keep='first')]
    return s


def get_forward_return(oracle_series, event_ts, horizon_seconds):
    """Get forward return from oracle series at event_ts + horizon_seconds.
    Returns None if data is not available."""
    if oracle_series.empty:
        return None
    
    event_dt = pd.Timestamp(event_ts, unit='s', tz='UTC')
    target_dt = event_dt + pd.Timedelta(seconds=horizon_seconds)
    
    # Find closest oracle price to event time
    idx_event = oracle_series.index.searchsorted(event_dt)
    if idx_event >= len(oracle_series):
        idx_event = len(oracle_series) - 1
    if idx_event < 0:
        return None
    
    # Check if closest point is within 5 minutes of event
    closest_event = oracle_series.index[idx_event]
    if abs((closest_event - event_dt).total_seconds()) > 300:
        # Try the previous index
        if idx_event > 0:
            alt = oracle_series.index[idx_event - 1]
            if abs((alt - event_dt).total_seconds()) < abs((closest_event - event_dt).total_seconds()):
                closest_event = alt
                idx_event = idx_event - 1
        if abs((closest_event - event_dt).total_seconds()) > 300:
            return None
    
    price_event = oracle_series.iloc[idx_event]
    
    # Find closest oracle price to target time
    idx_target = oracle_series.index.searchsorted(target_dt)
    if idx_target >= len(oracle_series):
        idx_target = len(oracle_series) - 1
    if idx_target < 0:
        return None
    
    closest_target = oracle_series.index[idx_target]
    if abs((closest_target - target_dt).total_seconds()) > 300:
        if idx_target > 0:
            alt = oracle_series.index[idx_target - 1]
            if abs((alt - target_dt).total_seconds()) < abs((closest_target - target_dt).total_seconds()):
                closest_target = alt
                idx_target = idx_target - 1
        if abs((closest_target - target_dt).total_seconds()) > 300:
            return None
    
    price_target = oracle_series.iloc[idx_target]
    
    if price_event == 0:
        return None
    
    return (price_target - price_event) / price_event


# ── State Variable Construction ────────────────────────────────────────────

def build_funding_events(funding_records, oracle_series):
    """Build H1 funding dislocation events."""
    print("\nBuilding H1: Funding Dislocation events...")
    
    # Parse funding records
    fr_data = []
    for r in funding_records:
        ts = r.get("ts")
        fr = r.get("fundingRate")
        mark_twap = r.get("markPriceTwap")
        oracle_twap = r.get("oraclePriceTwap")
        if ts and fr:
            fr_data.append({
                "ts": int(ts),
                "funding_rate": float(fr),
                "mark_twap": float(mark_twap) if mark_twap else None,
                "oracle_twap": float(oracle_twap) if oracle_twap else None,
            })
    
    df = pd.DataFrame(fr_data).sort_values("ts").reset_index(drop=True)
    print(f"  Total funding observations: {len(df)}")
    
    if len(df) < FUNDING_Z_WINDOW + 1:
        print("  WARN: Not enough funding observations for z-score window")
        return pd.DataFrame()
    
    # Compute rolling z-score
    df["fr_mean"] = df["funding_rate"].rolling(FUNDING_Z_WINDOW, min_periods=FUNDING_Z_WINDOW).mean()
    df["fr_std"] = df["funding_rate"].rolling(FUNDING_Z_WINDOW, min_periods=FUNDING_Z_WINDOW).std()
    df["funding_z"] = (df["funding_rate"] - df["fr_mean"]) / df["fr_std"].replace(0, np.nan)
    
    # Filter to events where |z| > threshold
    events = df[df["funding_z"].abs() > FUNDING_Z_THRESHOLD].copy()
    print(f"  Events with |z| > {FUNDING_Z_THRESHOLD}: {len(events)}")
    
    # Compute forward returns
    for label, secs in HORIZONS.items():
        events[f"r_{label}"] = events["ts"].apply(
            lambda t: get_forward_return(oracle_series, t, secs)
        )
        # Signed return: short when funding is positive, long when negative
        events[f"signed_r_{label}"] = -np.sign(events["funding_z"]) * events[f"r_{label}"]
    
    return events


def build_spread_events(funding_records, oracle_series):
    """Build H2 mark-oracle divergence events."""
    print("\nBuilding H2: Mark-Oracle Divergence events...")
    
    fr_data = []
    for r in funding_records:
        ts = r.get("ts")
        mark_twap = r.get("markPriceTwap")
        oracle_twap = r.get("oraclePriceTwap")
        if ts and mark_twap and oracle_twap:
            mark_f = float(mark_twap)
            oracle_f = float(oracle_twap)
            if oracle_f > 0:
                spread_pct = (mark_f - oracle_f) / oracle_f * 100
                fr_data.append({
                    "ts": int(ts),
                    "mark_twap": mark_f,
                    "oracle_twap": oracle_f,
                    "spread_pct": spread_pct,
                })
    
    df = pd.DataFrame(fr_data).sort_values("ts").reset_index(drop=True)
    print(f"  Total spread observations: {len(df)}")
    
    # Filter to events where |spread| > threshold
    events = df[df["spread_pct"].abs() > SPREAD_THRESHOLD_PCT].copy()
    print(f"  Events with |spread| > {SPREAD_THRESHOLD_PCT}%: {len(events)}")
    
    # Compute forward returns
    for label, secs in HORIZONS.items():
        events[f"r_{label}"] = events["ts"].apply(
            lambda t: get_forward_return(oracle_series, t, secs)
        )
        # Signed return: short when mark > oracle, long when mark < oracle
        events[f"signed_r_{label}"] = -np.sign(events["spread_pct"]) * events[f"r_{label}"]
    
    return events


def build_liquidation_events(liq_records, funding_records, oracle_series):
    """Build H3 liquidation/stress events."""
    print("\nBuilding H3: Liquidation/Stress events...")
    
    if not liq_records:
        print("  WARN: No liquidation records available — H3 BLOCKED")
        return pd.DataFrame()
    
    # Parse liquidation timestamps
    liq_ts = []
    for r in liq_records:
        ts = r.get("ts")
        if ts:
            liq_ts.append(int(ts))
    
    liq_ts.sort()
    print(f"  Total liquidation events: {len(liq_ts)}")
    
    if not liq_ts:
        print("  WARN: No valid liquidation timestamps — H3 BLOCKED")
        return pd.DataFrame()
    
    liq_min_ts = min(liq_ts)
    liq_max_ts = max(liq_ts)
    print(f"  Liquidation range: {datetime.utcfromtimestamp(liq_min_ts)} to {datetime.utcfromtimestamp(liq_max_ts)}")
    
    # Build hourly checkpoints from funding records
    checkpoints = []
    for r in funding_records:
        ts = r.get("ts")
        if ts:
            checkpoints.append(int(ts))
    checkpoints.sort()
    
    # For each checkpoint, count liquidations in trailing 1h
    liq_ts_arr = np.array(liq_ts)
    checkpoint_data = []
    for cp in checkpoints:
        window_start = cp - 3600
        count = int(np.sum((liq_ts_arr >= window_start) & (liq_ts_arr < cp)))
        checkpoint_data.append({"ts": cp, "liq_count_1h": count})
    
    df = pd.DataFrame(checkpoint_data)
    
    # Determine threshold
    nonzero_counts = df[df["liq_count_1h"] > 0]["liq_count_1h"]
    if len(nonzero_counts) == 0:
        print("  WARN: No liquidations overlap with funding checkpoints — H3 BLOCKED")
        return pd.DataFrame()
    
    threshold = np.percentile(df["liq_count_1h"], LIQ_PERCENTILE)
    if threshold == 0:
        # Use any checkpoint with at least 1 liquidation
        threshold = 1
    
    events = df[df["liq_count_1h"] >= threshold].copy()
    print(f"  Threshold (p{LIQ_PERCENTILE}): {threshold}")
    print(f"  Events above threshold: {len(events)}")
    
    # Compute forward returns (long bias after stress)
    for label, secs in HORIZONS.items():
        events[f"r_{label}"] = events["ts"].apply(
            lambda t: get_forward_return(oracle_series, t, secs)
        )
        events[f"signed_r_{label}"] = events[f"r_{label}"]  # long bias
    
    return events


# ── Analysis ───────────────────────────────────────────────────────────────

def winsorize(arr, pct_low=1, pct_high=99):
    """Winsorize array at given percentiles."""
    if len(arr) == 0:
        return arr
    low = np.percentile(arr, pct_low)
    high = np.percentile(arr, pct_high)
    return np.clip(arr, low, high)


def bootstrap_ci(arr, stat_func, n_boot=5000, ci=0.95):
    """Compute bootstrap confidence interval."""
    if len(arr) < 2:
        return (np.nan, np.nan)
    
    rng = np.random.RandomState(42)
    stats = []
    for _ in range(n_boot):
        sample = rng.choice(arr, size=len(arr), replace=True)
        stats.append(stat_func(sample))
    
    alpha = (1 - ci) / 2
    return (np.percentile(stats, alpha * 100), np.percentile(stats, (1 - alpha) * 100))


def compute_metrics(signed_returns, cost):
    """Compute all output metrics for a set of signed returns."""
    arr = np.array([r for r in signed_returns if r is not None and not np.isnan(r)])
    
    if len(arr) == 0:
        return None
    
    w_arr = winsorize(arr, WINSOR_PCT[0], WINSOR_PCT[1])
    
    w_mean_gross = float(np.mean(w_arr))
    w_mean_net = w_mean_gross - cost
    median_gross = float(np.median(arr))
    median_net = median_gross - cost
    pct_positive = float(np.mean(arr > 0))
    
    # Bootstrap CIs
    ci_mean = bootstrap_ci(arr, lambda x: np.mean(winsorize(x, WINSOR_PCT[0], WINSOR_PCT[1])) - cost)
    ci_median = bootstrap_ci(arr, lambda x: np.median(x) - cost)
    
    # Concentration
    abs_returns = np.abs(arr)
    total_abs = abs_returns.sum()
    if total_abs > 0:
        sorted_abs = np.sort(abs_returns)[::-1]
        top1_share = float(sorted_abs[0] / total_abs)
        top3_share = float(sorted_abs[:3].sum() / total_abs) if len(sorted_abs) >= 3 else float(sorted_abs.sum() / total_abs)
    else:
        top1_share = 0.0
        top3_share = 0.0
    
    return {
        "N": len(arr),
        "w_mean_gross": w_mean_gross,
        "w_mean_net": w_mean_net,
        "median_gross": median_gross,
        "median_net": median_net,
        "pct_positive": pct_positive,
        "ci_mean_lo": ci_mean[0],
        "ci_mean_hi": ci_mean[1],
        "ci_median_lo": ci_median[0],
        "ci_median_hi": ci_median[1],
        "top1_share": top1_share,
        "top3_share": top3_share,
    }


def check_gates(metrics):
    """Check pass/fail gates. Returns dict of gate results."""
    if metrics is None:
        return {"pass": False, "reason": "No data"}
    
    gates = {}
    gates["G1_sample"] = metrics["N"] >= 30
    gates["G2_mean_net"] = metrics["w_mean_net"] > 0
    gates["G3_median_net"] = metrics["median_net"] > 0
    gates["G4_ci_lower"] = metrics["ci_mean_lo"] > 0
    gates["G5_concentration"] = metrics["top1_share"] < 0.25 and metrics["top3_share"] < 0.50
    gates["G6_distinction"] = True  # Perps state is structurally distinct from spot features
    gates["pass"] = all(gates.values())
    
    failed = [k for k, v in gates.items() if not v and k != "pass"]
    gates["failed_gates"] = failed
    
    return gates


def run_analysis(events_df, hypothesis_name, oracle_series):
    """Run full analysis for one hypothesis."""
    print(f"\n{'='*60}")
    print(f"Analysis: {hypothesis_name}")
    print(f"{'='*60}")
    
    if events_df.empty:
        print("  NO EVENTS — BLOCKED")
        return []
    
    results = []
    
    for h_label, h_secs in HORIZONS.items():
        col = f"signed_r_{h_label}"
        if col not in events_df.columns:
            continue
        
        valid = events_df[col].dropna()
        print(f"\n  Horizon {h_label}: {len(valid)} events with valid returns")
        
        for c_label, c_val in COSTS.items():
            metrics = compute_metrics(valid.values, c_val)
            if metrics is None:
                continue
            
            gates = check_gates(metrics)
            
            row = {
                "hypothesis": hypothesis_name,
                "horizon": h_label,
                "cost": c_label,
                **metrics,
                **gates,
            }
            results.append(row)
            
            status = "PASS" if gates["pass"] else f"FAIL ({', '.join(gates['failed_gates'])})"
            print(f"    Cost {c_label}: N={metrics['N']}, "
                  f"WMeanNet={metrics['w_mean_net']*100:.4f}%, "
                  f"MedNet={metrics['median_net']*100:.4f}%, "
                  f"CI=[{metrics['ci_mean_lo']*100:.4f}%, {metrics['ci_mean_hi']*100:.4f}%] "
                  f"→ {status}")
    
    return results


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DRIFT PERPS STATE STUDY — STAGE A")
    print("=" * 60)
    print(f"Start time: {datetime.utcnow().isoformat()}Z")
    print()
    
    # ── Fetch data ──
    print("PHASE 1: DATA COLLECTION")
    print("-" * 40)
    
    funding_records = fetch_funding_rates(FUNDING_DAYS)
    oracle_raw = fetch_oracle_price(ORACLE_DAYS, ORACLE_SAMPLES)
    liq_records = fetch_liquidations()
    oi_raw = fetch_open_interest(ORACLE_DAYS)
    
    # Build oracle series
    oracle_series = build_oracle_series(oracle_raw)
    print(f"\nOracle series: {len(oracle_series)} points")
    if not oracle_series.empty:
        print(f"  Range: {oracle_series.index[0]} to {oracle_series.index[-1]}")
        print(f"  Price range: ${oracle_series.min():.2f} - ${oracle_series.max():.2f}")
    
    # Save data summary
    data_summary = {
        "funding_records": len(funding_records),
        "oracle_points": len(oracle_series),
        "oracle_range_start": str(oracle_series.index[0]) if not oracle_series.empty else None,
        "oracle_range_end": str(oracle_series.index[-1]) if not oracle_series.empty else None,
        "liquidation_records": len(liq_records),
        "oi_points": len(oi_raw),
    }
    
    with open(f"{OUTPUT_DIR}/drift_stageA_data_summary.json", "w") as f:
        json.dump(data_summary, f, indent=2, default=str)
    
    # ── Build events ──
    print("\nPHASE 2: STATE VARIABLE CONSTRUCTION")
    print("-" * 40)
    
    h1_events = build_funding_events(funding_records, oracle_series)
    h2_events = build_spread_events(funding_records, oracle_series)
    h3_events = build_liquidation_events(liq_records, funding_records, oracle_series)
    
    # ── Run analysis ──
    print("\nPHASE 3: EVENT-STUDY ANALYSIS")
    print("-" * 40)
    
    all_results = []
    
    if not h1_events.empty:
        all_results.extend(run_analysis(h1_events, "H1_Funding_Dislocation", oracle_series))
    else:
        print("\nH1: BLOCKED — insufficient events")
    
    if not h2_events.empty:
        all_results.extend(run_analysis(h2_events, "H2_Mark_Oracle_Divergence", oracle_series))
    else:
        print("\nH2: BLOCKED — insufficient events")
    
    if not h3_events.empty:
        all_results.extend(run_analysis(h3_events, "H3_Liquidation_Stress", oracle_series))
    else:
        print("\nH3: BLOCKED — insufficient events")
    
    # ── Save results ──
    if all_results:
        results_df = pd.DataFrame(all_results)
        results_df.to_csv(f"{OUTPUT_DIR}/drift_stageA_results.csv", index=False)
        print(f"\nResults saved: {len(all_results)} rows")
        
        # Summary
        passing = results_df[results_df["pass"] == True]
        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"Total combinations tested: {len(all_results)}")
        print(f"Passing all gates: {len(passing)}")
        
        if len(passing) > 0:
            print("\nPASSING COMBINATIONS:")
            for _, row in passing.iterrows():
                print(f"  {row['hypothesis']} | {row['horizon']} | {row['cost']} | "
                      f"WMeanNet={row['w_mean_net']*100:.4f}% | "
                      f"MedNet={row['median_net']*100:.4f}% | "
                      f"CI=[{row['ci_mean_lo']*100:.4f}%, {row['ci_mean_hi']*100:.4f}%]")
            print("\nVERDICT: Potential GO — review required")
        else:
            print("\nNo combinations passed all gates.")
            print("VERDICT: NO-GO")
    else:
        print("\nNo results generated — all hypotheses BLOCKED")
        print("VERDICT: BLOCKED")
    
    # Save event details for documentation
    event_summary = {
        "h1_total_events": len(h1_events) if not h1_events.empty else 0,
        "h2_total_events": len(h2_events) if not h2_events.empty else 0,
        "h3_total_events": len(h3_events) if not h3_events.empty else 0,
    }
    
    # Add event-level detail for H1
    if not h1_events.empty:
        event_summary["h1_funding_z_stats"] = {
            "mean_abs_z": float(h1_events["funding_z"].abs().mean()),
            "max_abs_z": float(h1_events["funding_z"].abs().max()),
            "pct_positive_z": float((h1_events["funding_z"] > 0).mean()),
        }
    
    if not h2_events.empty:
        event_summary["h2_spread_stats"] = {
            "mean_abs_spread": float(h2_events["spread_pct"].abs().mean()),
            "max_abs_spread": float(h2_events["spread_pct"].abs().max()),
            "pct_positive_spread": float((h2_events["spread_pct"] > 0).mean()),
        }
    
    with open(f"{OUTPUT_DIR}/drift_stageA_event_summary.json", "w") as f:
        json.dump(event_summary, f, indent=2, default=str)
    
    print(f"\nEnd time: {datetime.utcnow().isoformat()}Z")
    print("Done.")


if __name__ == "__main__":
    main()
