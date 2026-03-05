#!/usr/bin/env python3
"""
observer_dashboard.py — Minimal read-only human-in-the-loop dashboard
for the LCR continuation observer experiment.

Port: 7070
Auto-refresh: 30s
Read-only: no buttons that change state, strategy, DB, or services.
Strict run_id scoping: default = current (latest) run_id only.
"""

import sqlite3
import json
import math
import statistics
import subprocess
from datetime import datetime, timezone
from flask import Flask, Response, request

DB_PATH   = "/root/solana_trader/data/observer_lcr_cont_v1.db"
DEPLOYED_SHA_PATH = "/root/solana_trader/.deployed_sha"
REFRESH_SEC = 30
PORT = 7070

app = Flask(__name__)

# ─── DB helpers ───────────────────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn

def current_run_id(conn):
    row = conn.execute(
        "SELECT run_id FROM observer_lcr_cont_v1 ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    return row["run_id"] if row else None

def deployed_sha():
    try:
        with open(DEPLOYED_SHA_PATH) as f:
            return f.read().strip()[:12]
    except Exception:
        return "unknown"

def service_status():
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "solana-lcr-cont-observer.service"],
            capture_output=True, text=True, timeout=3
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"

def ptile(lst, p):
    if not lst:
        return None
    s = sorted(lst)
    idx = max(0, min(int(len(s) * p / 100), len(s) - 1))
    return round(s[idx], 1)

def fmt(v, decimals=6):
    if v is None:
        return "—"
    return f"{v:+.{decimals}f}" if isinstance(v, float) else str(v)

def pct(num, den):
    if not den:
        return "—"
    return f"{100*num/den:.1f}%  ({num}/{den})"

# ─── Data queries ─────────────────────────────────────────────────────────────

def load_data(run_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM observer_lcr_cont_v1 WHERE run_id=?", (run_id,)
    ).fetchall()
    conn.close()

    signals  = [r for r in rows if r["candidate_type"] == "signal"]
    controls = [r for r in rows if r["candidate_type"] == "control"]
    ctrl_map = {c["control_for_signal_id"]: c for c in controls}

    # Fires
    fire_ids = sorted({r["signal_fire_id"] for r in rows})
    n_fires  = len(fire_ids)

    # ── Coverage per horizon ──────────────────────────────────────────────────
    def cov(side, hz):
        ok_col  = f"fwd_quote_ok_{hz}"
        due_col = f"fwd_due_epoch_{hz}"
        total   = len(side)
        entry_ok = [r for r in side if r["entry_quote_ok"] == 1]
        n_entry_ok = len(entry_ok)
        due     = [r for r in entry_ok if r[due_col] is not None]
        ok      = [r for r in due if r[ok_col] == 1]
        fail    = [r for r in due if r[ok_col] == 0]
        return dict(total=total, entry_ok=n_entry_ok, due=len(due),
                    ok=len(ok), fail=len(fail))

    def jitter_stats(side, hz):
        ok_col  = f"fwd_quote_ok_{hz}"
        due_col = f"fwd_due_epoch_{hz}"
        ts_col  = f"fwd_quote_ts_epoch_{hz}"
        vals = []
        for r in side:
            if r[ok_col] == 1 and r[due_col] and r[ts_col]:
                vals.append(abs(r[ts_col] - r[due_col]))
        return dict(p50=ptile(vals,50), p95=ptile(vals,95), mx=max(vals) if vals else None)

    def dt_stats(side, hz):
        ts_col  = f"fwd_quote_ts_epoch_{hz}"
        vals = []
        for r in side:
            if r["entry_quote_ts_epoch"] and r[ts_col]:
                vals.append(r[ts_col] - r["entry_quote_ts_epoch"])
        return dict(p50=ptile(vals,50), p95=ptile(vals,95), mx=max(vals) if vals else None)

    def fail_breakdown(side, hz):
        ok_col  = f"fwd_quote_ok_{hz}"
        err_col = f"fwd_quote_err_{hz}"
        fails   = [r for r in side if r[ok_col] == 0]
        r429    = sum(1 for r in fails if r[err_col] and "429" in str(r[err_col]))
        other   = len(fails) - r429
        return dict(total=len(fails), r429=r429, other=other)

    hz_list = ["1m", "5m", "15m", "30m"]
    sig_cov  = {hz: cov(signals, hz)  for hz in hz_list}
    ctl_cov  = {hz: cov(controls, hz) for hz in hz_list}
    sig_jit  = {hz: jitter_stats(signals, hz)  for hz in ["1m","5m"]}
    ctl_jit  = {hz: jitter_stats(controls, hz) for hz in ["1m","5m"]}
    sig_dt   = {hz: dt_stats(signals, hz)  for hz in ["1m","5m"]}
    ctl_dt   = {hz: dt_stats(controls, hz) for hz in ["1m","5m"]}
    sig_fail = fail_breakdown(signals, "5m")
    ctl_fail = fail_breakdown(controls, "5m")

    # ── row_valid ─────────────────────────────────────────────────────────────
    sig_valid   = sum(1 for r in signals  if r["row_valid"] == 1)
    sig_invalid = sum(1 for r in signals  if r["row_valid"] == 0)
    ctl_valid   = sum(1 for r in controls if r["row_valid"] == 1)
    ctl_invalid = sum(1 for r in controls if r["row_valid"] == 0)

    invalid_reasons = {}
    for r in signals + controls:
        if r["row_valid"] == 0 and r["invalid_reason"]:
            invalid_reasons[r["invalid_reason"]] = invalid_reasons.get(r["invalid_reason"], 0) + 1

    # ── Pairs ─────────────────────────────────────────────────────────────────
    ok_pairs, fail_pairs = [], []
    for s in signals:
        c = ctrl_map.get(s["candidate_id"])
        if c and s["fwd_quote_ok_5m"] is not None and c["fwd_quote_ok_5m"] is not None:
            if s["fwd_quote_ok_5m"] == 1 and c["fwd_quote_ok_5m"] == 1:
                ok_pairs.append((s, c))
            else:
                fail_pairs.append((s, c))

    n_pairs = len(ok_pairs)

    # ── Deltas ────────────────────────────────────────────────────────────────
    deltas, sig_nets, ctl_nets = [], [], []
    for s, c in ok_pairs:
        if s["fwd_net_fee100_5m"] is not None and c["fwd_net_fee100_5m"] is not None:
            deltas.append(s["fwd_net_fee100_5m"] - c["fwd_net_fee100_5m"])
            sig_nets.append(s["fwd_net_fee100_5m"])
            ctl_nets.append(c["fwd_net_fee100_5m"])

    stats = {}
    if deltas:
        n = len(deltas)
        mn = statistics.mean(deltas)
        md = statistics.median(deltas)
        pct_pos = sum(1 for d in deltas if d > 0) / n
        std = statistics.stdev(deltas) if n >= 2 else 0
        se  = std / math.sqrt(n) if n >= 2 else 0
        t   = 2.042 if n >= 30 else 2.0
        ci_lo = mn - t * se
        ci_hi = mn + t * se
        # A2 sensitivity: failed = 0
        a2 = deltas + [0.0] * len(fail_pairs)
        a2_mean = statistics.mean(a2)
        a2_ci_lo = statistics.mean(a2) - t * (statistics.stdev(a2)/math.sqrt(len(a2))) if len(a2)>=2 else 0
        # A3 sensitivity: failed = worst non-outlier
        non_out = [d for d in deltas if abs(d) < 0.10]
        worst   = min(non_out) if non_out else 0.0
        a3 = deltas + [worst] * len(fail_pairs)
        a3_mean   = statistics.mean(a3)
        a3_ci_lo  = statistics.mean(a3) - t * (statistics.stdev(a3)/math.sqrt(len(a3))) if len(a3)>=2 else 0
        a3_ci_hi  = statistics.mean(a3) + t * (statistics.stdev(a3)/math.sqrt(len(a3))) if len(a3)>=2 else 0
        outliers  = [(s, c) for s, c in ok_pairs
                     if s["fwd_net_fee100_5m"] is not None and c["fwd_net_fee100_5m"] is not None
                     and abs(s["fwd_net_fee100_5m"] - c["fwd_net_fee100_5m"]) >= 0.10]
        stats = dict(
            n=n, mean=mn, median=md, pct_pos=pct_pos,
            ci_lo=ci_lo, ci_hi=ci_hi,
            mean_sig=statistics.mean(sig_nets), mean_ctl=statistics.mean(ctl_nets),
            a2_mean=a2_mean, a2_ci_lo=a2_ci_lo,
            a3_mean=a3_mean, a3_ci_lo=a3_ci_lo, a3_ci_hi=a3_ci_hi,
            n_outliers=len(outliers),
            outlier_rows=outliers
        )

    # ── Cumulative series ─────────────────────────────────────────────────────
    cum_pairs = sorted(ok_pairs, key=lambda x: x[0]["fire_time_epoch"] or 0)
    cum_n, cum_mean, cum_pct = [], [], []
    running = []
    for i, (s, c) in enumerate(cum_pairs):
        if s["fwd_net_fee100_5m"] is not None and c["fwd_net_fee100_5m"] is not None:
            running.append(s["fwd_net_fee100_5m"] - c["fwd_net_fee100_5m"])
            cum_n.append(i + 1)
            cum_mean.append(round(statistics.mean(running), 6))
            cum_pct.append(round(sum(1 for d in running if d > 0) / len(running), 4))

    # ── Latest 10 fires ───────────────────────────────────────────────────────
    latest_fires = []
    for fire_id in sorted(fire_ids, reverse=True)[:10]:
        s_row = next((r for r in signals  if r["signal_fire_id"] == fire_id), None)
        c_row = ctrl_map.get(s_row["candidate_id"]) if s_row else None
        if s_row:
            d5m = None
            if (s_row["fwd_net_fee100_5m"] is not None and
                c_row and c_row["fwd_net_fee100_5m"] is not None):
                d5m = s_row["fwd_net_fee100_5m"] - c_row["fwd_net_fee100_5m"]
            outlier = d5m is not None and abs(d5m) >= 0.10
            latest_fires.append(dict(
                fire_id=fire_id[:8],
                fire_time=s_row["fire_time_iso"],
                sig_sym=s_row["symbol"],
                ctl_sym=c_row["symbol"] if c_row else "—",
                sig_rm5=s_row["entry_r_m5"],
                ctl_rm5=c_row["entry_r_m5"] if c_row else None,
                sig_net5=s_row["fwd_net_fee100_5m"],
                ctl_net5=c_row["fwd_net_fee100_5m"] if c_row else None,
                delta5=d5m,
                row_valid=s_row["row_valid"],
                outlier=outlier
            ))

    # ── Invalid rows ──────────────────────────────────────────────────────────
    invalid_rows = [r for r in signals + controls if r["row_valid"] == 0][-10:]

    # ── Started at ───────────────────────────────────────────────────────────
    started_at = None
    if signals:
        epochs = [r["fire_time_epoch"] for r in signals if r["fire_time_epoch"]]
        if epochs:
            started_at = datetime.fromtimestamp(min(epochs), tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")

    # ── Coverage metrics (3 lines) ────────────────────────────────────────────
    total_sig = len(signals)
    entry_ok_sig = sum(1 for r in signals if r["entry_quote_ok"] == 1)
    pairs_complete_5m = n_pairs
    entry_ok_pairs = len([s for s in signals
                          if s["entry_quote_ok"] == 1 and
                          ctrl_map.get(s["candidate_id"]) is not None and
                          ctrl_map.get(s["candidate_id"])["entry_quote_ok"] == 1])

    entry_quote_coverage = entry_ok_sig / total_sig if total_sig else 0
    cond_5m_coverage     = pairs_complete_5m / entry_ok_pairs if entry_ok_pairs else 0
    uncond_5m_completion = pairs_complete_5m / total_sig if total_sig else 0

    return dict(
        run_id=run_id, n_fires=n_fires, n_pairs=n_pairs,
        started_at=started_at,
        sig_cov=sig_cov, ctl_cov=ctl_cov,
        sig_jit=sig_jit, ctl_jit=ctl_jit,
        sig_dt=sig_dt, ctl_dt=ctl_dt,
        sig_fail=sig_fail, ctl_fail=ctl_fail,
        sig_valid=sig_valid, sig_invalid=sig_invalid,
        ctl_valid=ctl_valid, ctl_invalid=ctl_invalid,
        invalid_reasons=invalid_reasons,
        stats=stats, deltas=deltas,
        cum_n=cum_n, cum_mean=cum_mean, cum_pct=cum_pct,
        latest_fires=latest_fires,
        invalid_rows=invalid_rows,
        fail_pairs=fail_pairs,
        entry_quote_coverage=entry_quote_coverage,
        cond_5m_coverage=cond_5m_coverage,
        uncond_5m_completion=uncond_5m_completion,
        entry_ok_sig=entry_ok_sig,
        total_sig=total_sig,
        entry_ok_pairs=entry_ok_pairs,
    )

def load_experiment_index():
    """Load all run_ids with summary stats for the experiment index tab."""
    conn = get_conn()
    runs = conn.execute(
        """SELECT run_id, MIN(fire_time_iso) as started, MAX(fire_time_iso) as last_fire,
                  COUNT(DISTINCT signal_fire_id) as n_fires
           FROM observer_lcr_cont_v1 WHERE candidate_type='signal'
           GROUP BY run_id ORDER BY MIN(fire_time_epoch) DESC"""
    ).fetchall()
    index = []
    for run in runs:
        rid = run["run_id"]
        rows = conn.execute(
            "SELECT * FROM observer_lcr_cont_v1 WHERE run_id=?", (rid,)
        ).fetchall()
        sigs = [r for r in rows if r["candidate_type"] == "signal"]
        ctls = [r for r in rows if r["candidate_type"] == "control"]
        cm   = {c["control_for_signal_id"]: c for c in ctls}
        pairs = [(s, cm[s["candidate_id"]]) for s in sigs
                 if s["candidate_id"] in cm
                 and s["fwd_quote_ok_5m"] == 1
                 and cm[s["candidate_id"]]["fwd_quote_ok_5m"] == 1]
        deltas = [s["fwd_net_fee100_5m"] - c["fwd_net_fee100_5m"]
                  for s, c in pairs
                  if s["fwd_net_fee100_5m"] is not None and c["fwd_net_fee100_5m"] is not None]
        mean_d = round(statistics.mean(deltas), 6) if deltas else None
        index.append(dict(
            run_id=rid[:8], started=run["started"], last_fire=run["last_fire"],
            n_fires=run["n_fires"], n_pairs=len(pairs), mean_delta=mean_d
        ))
    conn.close()
    return index

# ─── HTML template ────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Observer Dashboard — LCR Continuation</title>
<meta http-equiv="refresh" content="{refresh}">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  body {{ font-family: monospace; background:#111; color:#ccc; margin:0; padding:10px; font-size:13px; }}
  h1   {{ color:#fff; font-size:16px; margin:4px 0; }}
  h2   {{ color:#aaa; font-size:13px; border-bottom:1px solid #333; margin:12px 0 4px; padding-bottom:2px; }}
  table{{ border-collapse:collapse; width:100%; margin-bottom:8px; }}
  th   {{ background:#222; color:#888; text-align:left; padding:3px 6px; border:1px solid #333; }}
  td   {{ padding:3px 6px; border:1px solid #222; }}
  .pos {{ color:#4f4; }}
  .neg {{ color:#f44; }}
  .warn{{ background:#5a3000; color:#ffa; padding:6px 10px; margin:6px 0; border-left:4px solid #fa0; }}
  .desc{{ background:#1a1a4a; color:#aaf; padding:6px 10px; margin:6px 0; border-left:4px solid #44f; font-weight:bold; }}
  .ok  {{ color:#4f4; }}
  .bad {{ color:#f44; }}
  .tab {{ display:inline-block; padding:4px 12px; cursor:pointer; background:#222; color:#888; margin-right:4px; border:1px solid #333; }}
  .tab.active {{ background:#333; color:#fff; }}
  .panel {{ display:none; }}
  .panel.active {{ display:block; }}
  canvas {{ max-height:180px; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
  .card {{ background:#1a1a1a; border:1px solid #333; padding:8px; }}
</style>
</head>
<body>
<h1>LCR Continuation Observer — Human-in-the-Loop Dashboard</h1>
<small style="color:#555">Auto-refresh every {refresh}s &nbsp;|&nbsp; Last loaded: {now} UTC &nbsp;|&nbsp; Read-only</small>

<div style="margin:8px 0">
  <span class="tab active" onclick="showTab('main',this)">Main</span>
  <span class="tab" onclick="showTab('index',this)">Experiment Index</span>
</div>

<div id="main" class="panel active">

{warnings}

<!-- SECTION 1: RUN HEADER -->
<h2>1. RUN HEADER</h2>
<table>
<tr><th>Experiment</th><td>LCR Continuation Observer v1 (Confirmatory)</td></tr>
<tr><th>run_id</th><td>{run_id}</td></tr>
<tr><th>Deployed SHA</th><td>{sha}</td></tr>
<tr><th>Service status</th><td class="{svc_cls}">{svc_status}</td></tr>
<tr><th>Started at</th><td>{started_at}</td></tr>
<tr><th>n_fires_total</th><td>{n_fires}</td></tr>
<tr><th>n_pairs_complete_5m</th><td>{n_pairs}</td></tr>
</table>

<!-- SECTION 2: DATA QUALITY -->
<h2>2. DATA QUALITY</h2>
<table>
<tr>
  <th>Metric</th><th>Signal</th><th>Control</th>
</tr>
<tr><td>total rows</td><td>{sig_total}</td><td>{ctl_total}</td></tr>
<tr><td>entry_quote_coverage (entry_ok / total)</td>
    <td class="{ecov_s_cls}">{ecov_s}</td>
    <td class="{ecov_c_cls}">{ecov_c}</td></tr>
<tr><td colspan=3 style="color:#666;font-size:11px">— +1m coverage (ok/due) —</td></tr>
<tr><td>+1m ok/due</td><td>{s1ok}/{s1due}</td><td>{c1ok}/{c1due}</td></tr>
<tr><td>+1m coverage</td><td class="{s1cls}">{s1pct}</td><td class="{c1cls}">{c1pct}</td></tr>
<tr><td colspan=3 style="color:#666;font-size:11px">— +5m coverage (PRIMARY) —</td></tr>
<tr><td>+5m ok/due</td><td>{s5ok}/{s5due}</td><td>{c5ok}/{c5due}</td></tr>
<tr><td>+5m coverage (conditional)</td><td class="{s5cls}">{s5pct}</td><td class="{c5cls}">{c5pct}</td></tr>
<tr><td>+5m HTTP 429 failures</td><td>{s5_429}</td><td>{c5_429}</td></tr>
<tr><td>+5m other failures</td><td>{s5_oth}</td><td>{c5_oth}</td></tr>
<tr><td colspan=3 style="color:#666;font-size:11px">— +15m / +30m coverage —</td></tr>
<tr><td>+15m ok/due</td><td>{s15ok}/{s15due}</td><td>{c15ok}/{c15due}</td></tr>
<tr><td>+30m ok/due</td><td>{s30ok}/{s30due}</td><td>{c30ok}/{c30due}</td></tr>
<tr><td colspan=3 style="color:#666;font-size:11px">— 3-line coverage summary —</td></tr>
<tr><td>entry_quote_coverage = entry_ok / total_signals</td><td colspan=2>{entry_quote_coverage}</td></tr>
<tr><td>conditional_5m_coverage = pairs_complete_5m / entry_ok_pairs</td><td colspan=2>{cond_5m_coverage}</td></tr>
<tr><td>unconditional_5m_completion = pairs_complete_5m / total_signals</td><td colspan=2>{uncond_5m_completion}</td></tr>
<tr><td colspan=3 style="color:#666;font-size:11px">— row_valid —</td></tr>
<tr><td>row_valid=1</td><td class="ok">{sig_valid}</td><td class="ok">{ctl_valid}</td></tr>
<tr><td>row_valid=0 (invalid)</td><td class="{sinv_cls}">{sig_invalid}</td><td class="{cinv_cls}">{ctl_invalid}</td></tr>
<tr><td>invalid_reason summary</td><td colspan=2>{invalid_reasons}</td></tr>
<tr><td colspan=3 style="color:#666;font-size:11px">— jitter (|exec_ts - due_ts|) —</td></tr>
<tr><td>+1m jitter p50/p95/max (s)</td><td>{sj1p50}/{sj1p95}/{sj1mx}</td><td>{cj1p50}/{cj1p95}/{cj1mx}</td></tr>
<tr><td>+5m jitter p50/p95/max (s)</td><td>{sj5p50}/{sj5p95}/{sj5mx}</td><td>{cj5p50}/{cj5p95}/{cj5mx}</td></tr>
<tr><td colspan=3 style="color:#666;font-size:11px">— dt from entry quote —</td></tr>
<tr><td>+1m dt_from_entry p50/p95/max (s)</td><td>{sd1p50}/{sd1p95}/{sd1mx}</td><td>{cd1p50}/{cd1p95}/{cd1mx}</td></tr>
<tr><td>+5m dt_from_entry p50/p95/max (s)</td><td>{sd5p50}/{sd5p95}/{sd5mx}</td><td>{cd5p50}/{cd5p95}/{cd5mx}</td></tr>
</table>

<!-- SECTION 3: PRIMARY PERFORMANCE -->
<h2>3. PRIMARY PERFORMANCE PANEL (+5m)</h2>
{decision_banner}
<table>
<tr><th>Metric</th><th>Value</th></tr>
<tr><td><b>SIGNAL-MINUS-CONTROL DELTA — mean +5m</b></td><td class="{mean_cls}">{mean_d}</td></tr>
<tr><td><b>SIGNAL-MINUS-CONTROL DELTA — median +5m</b></td><td class="{med_cls}">{med_d}</td></tr>
<tr><td>% delta &gt; 0</td><td>{pct_pos}</td></tr>
<tr><td>95% CI</td><td>{ci}</td></tr>
<tr><td><b>ABSOLUTE SIGNAL MARKOUT — mean net +5m</b></td><td class="{msig_cls}">{mean_sig}</td></tr>
<tr><td><b>ABSOLUTE CONTROL MARKOUT — mean net +5m</b></td><td class="{mctl_cls}">{mean_ctl}</td></tr>
<tr><td>n_pairs used</td><td>{n_pairs_used}</td></tr>
</table>
<h2>3b. SENSITIVITY CHECK</h2>
<table>
<tr><th>Assumption</th><th>n</th><th>mean delta</th><th>CI lower &gt; 0?</th></tr>
<tr><td>A1: drop failed (baseline)</td><td>{a1n}</td><td class="{a1cls}">{a1mean}</td><td>{a1ci}</td></tr>
<tr><td>A2: failed = 0</td><td>{a2n}</td><td class="{a2cls}">{a2mean}</td><td>{a2ci}</td></tr>
<tr><td>A3: failed = worst non-outlier</td><td>{a3n}</td><td class="{a3cls}">{a3mean}</td><td>{a3ci}</td></tr>
</table>

<!-- SECTION 4: CUMULATIVE CHARTS -->
<h2>4. CUMULATIVE CHARTS</h2>
<div class="grid2">
<div class="card">
  <div style="color:#888;font-size:11px">Cumulative mean delta +5m (SIGNAL-MINUS-CONTROL)</div>
  <canvas id="chartMean"></canvas>
</div>
<div class="card">
  <div style="color:#888;font-size:11px">Cumulative % delta &gt; 0</div>
  <canvas id="chartPct"></canvas>
</div>
</div>

<!-- SECTION 5: LATEST FIRE TABLE -->
<h2>5. LATEST 10 FIRES</h2>
<table>
<tr>
  <th>fire_id</th><th>time</th>
  <th>signal</th><th>control</th>
  <th>sig entry_r_m5</th><th>ctl entry_r_m5</th>
  <th>ABS SIG net +5m</th><th>ABS CTL net +5m</th>
  <th>S-C DELTA +5m</th>
  <th>valid</th><th>outlier</th>
</tr>
{fire_rows}
</table>

<!-- SECTION 6: OUTLIER / FAILURE PANEL -->
<h2>6. OUTLIER / FAILURE PANEL</h2>
<b>Pairs with |delta +5m| &gt;= 10%:</b>
<table>
<tr><th>fire_id</th><th>signal</th><th>control</th><th>ABS SIG net +5m</th><th>ABS CTL net +5m</th><th>S-C DELTA +5m</th></tr>
{outlier_rows}
</table>
<b>Last 10 invalid rows:</b>
<table>
<tr><th>type</th><th>symbol</th><th>fire_time</th><th>row_valid</th><th>invalid_reason</th></tr>
{invalid_rows}
</table>

</div><!-- end main panel -->

<div id="index" class="panel">
<h2>7. EXPERIMENT INDEX</h2>
<table>
<tr><th>run_id</th><th>started</th><th>last_fire</th><th>n_fires</th><th>n_pairs_5m</th><th>mean delta +5m</th></tr>
{index_rows}
</table>
</div>

<script>
function showTab(id, el) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  el.classList.add('active');
}}

const cumN    = {cum_n_json};
const cumMean = {cum_mean_json};
const cumPct  = {cum_pct_json};

new Chart(document.getElementById('chartMean'), {{
  type: 'line',
  data: {{ labels: cumN, datasets: [{{
    label: 'mean delta +5m',
    data: cumMean,
    borderColor: '#4af',
    backgroundColor: 'transparent',
    pointRadius: 2,
    borderWidth: 1.5
  }}, {{
    label: 'zero line',
    data: cumN.map(() => 0),
    borderColor: '#555',
    borderDash: [4,4],
    pointRadius: 0,
    borderWidth: 1
  }}]}},
  options: {{ animation:false, plugins:{{legend:{{labels:{{color:'#888',font:{{size:10}}}}}}}},
    scales:{{ x:{{ticks:{{color:'#666'}},grid:{{color:'#222'}}}},
              y:{{ticks:{{color:'#666'}},grid:{{color:'#222'}}}}}}}}
}});

new Chart(document.getElementById('chartPct'), {{
  type: 'line',
  data: {{ labels: cumN, datasets: [{{
    label: '% delta > 0',
    data: cumPct.map(v => v*100),
    borderColor: '#4f4',
    backgroundColor: 'transparent',
    pointRadius: 2,
    borderWidth: 1.5
  }}, {{
    label: '50% line',
    data: cumN.map(() => 50),
    borderColor: '#555',
    borderDash: [4,4],
    pointRadius: 0,
    borderWidth: 1
  }}]}},
  options: {{ animation:false, plugins:{{legend:{{labels:{{color:'#888',font:{{size:10}}}}}}}},
    scales:{{ x:{{ticks:{{color:'#666'}},grid:{{color:'#222'}}}},
              y:{{ticks:{{color:'#666'}},grid:{{color:'#222'}},min:0,max:100}}}}}}
}});
</script>
</body>
</html>
"""

# ─── Route ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    conn = get_conn()
    run_id = request.args.get("run_id") or current_run_id(conn)
    conn.close()

    if not run_id:
        return Response("<h2>No data yet.</h2>", mimetype="text/html")

    d = load_data(run_id)
    exp_index = load_experiment_index()

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    sha = deployed_sha()
    svc = service_status()
    svc_cls = "ok" if svc == "active" else "bad"

    st = d["stats"]
    n  = st.get("n", 0)

    # ── Warnings ──────────────────────────────────────────────────────────────
    warns = []
    s5 = d["sig_cov"]["5m"]
    s5_cov = s5["ok"] / s5["due"] if s5["due"] else 0
    if s5_cov < 0.95 and s5["due"] > 0:
        warns.append(f"WARNING: +5m coverage = {100*s5_cov:.1f}% (threshold: >=95%)")
    if d["sig_invalid"] > 0 or d["ctl_invalid"] > 0:
        warns.append(f"WARNING: row_valid=0 count — signal:{d['sig_invalid']} control:{d['ctl_invalid']}")
    for side_label, jit_data in [("signal", d["sig_jit"]), ("control", d["ctl_jit"])]:
        for hz in ["1m", "5m"]:
            mx = jit_data[hz].get("mx")
            if mx and mx > 20:
                warns.append(f"WARNING: {side_label} +{hz} jitter max = {mx}s (>20s threshold)")

    warn_html = "".join(f'<div class="warn">{w}</div>' for w in warns)

    # ── Decision banner ───────────────────────────────────────────────────────
    if n < 30:
        banner = '<div class="desc">DESCRIPTIVE ONLY — NOT DECISION-GRADE (n &lt; 30)</div>'
    else:
        banner = ""

    def cov_pct(cov_dict):
        if not cov_dict["due"]:
            return "—"
        return f"{100*cov_dict['ok']/cov_dict['due']:.1f}%"

    def cov_cls(cov_dict):
        if not cov_dict["due"]:
            return ""
        return "ok" if cov_dict["ok"]/cov_dict["due"] >= 0.95 else "bad"

    def jv(d, k):
        v = d.get(k)
        return str(v) if v is not None else "—"

    def fmtd(v):
        if v is None:
            return "—"
        return f"{v:+.6f}"

    def cls(v):
        if v is None:
            return ""
        return "pos" if v > 0 else "neg"

    # ── Fire rows ─────────────────────────────────────────────────────────────
    fire_rows_html = ""
    for f in d["latest_fires"]:
        out_flag = '<span class="bad">YES</span>' if f["outlier"] else "no"
        valid_cls = "ok" if f["row_valid"] == 1 else "bad"
        d5 = f["delta5"]
        fire_rows_html += (
            f'<tr>'
            f'<td>{f["fire_id"]}</td>'
            f'<td>{(f["fire_time"] or "")[:16]}</td>'
            f'<td>{f["sig_sym"]}</td>'
            f'<td>{f["ctl_sym"]}</td>'
            f'<td>{fmtd(f["sig_rm5"])}</td>'
            f'<td>{fmtd(f["ctl_rm5"])}</td>'
            f'<td class="{cls(f["sig_net5"])}">{fmtd(f["sig_net5"])}</td>'
            f'<td class="{cls(f["ctl_net5"])}">{fmtd(f["ctl_net5"])}</td>'
            f'<td class="{cls(d5)}">{fmtd(d5)}</td>'
            f'<td class="{valid_cls}">{f["row_valid"]}</td>'
            f'<td>{out_flag}</td>'
            f'</tr>'
        )

    # ── Outlier rows ──────────────────────────────────────────────────────────
    outlier_rows_html = ""
    if st.get("outlier_rows"):
        for s, c in st["outlier_rows"]:
            d5 = s["fwd_net_fee100_5m"] - c["fwd_net_fee100_5m"]
            outlier_rows_html += (
                f'<tr><td>{s["signal_fire_id"][:8]}</td>'
                f'<td>{s["symbol"]}</td><td>{c["symbol"]}</td>'
                f'<td class="{cls(s["fwd_net_fee100_5m"])}">{fmtd(s["fwd_net_fee100_5m"])}</td>'
                f'<td class="{cls(c["fwd_net_fee100_5m"])}">{fmtd(c["fwd_net_fee100_5m"])}</td>'
                f'<td class="{cls(d5)}">{fmtd(d5)}</td></tr>'
            )
    else:
        outlier_rows_html = '<tr><td colspan=6 style="color:#555">None</td></tr>'

    # ── Invalid rows ──────────────────────────────────────────────────────────
    inv_rows_html = ""
    for r in d["invalid_rows"]:
        inv_rows_html += (
            f'<tr><td>{r["candidate_type"]}</td><td>{r["symbol"]}</td>'
            f'<td>{(r["fire_time_iso"] or "")[:16]}</td>'
            f'<td class="bad">{r["row_valid"]}</td>'
            f'<td>{r["invalid_reason"] or "—"}</td></tr>'
        )
    if not inv_rows_html:
        inv_rows_html = '<tr><td colspan=5 style="color:#555">None</td></tr>'

    # ── Experiment index rows ─────────────────────────────────────────────────
    index_rows_html = ""
    for e in exp_index:
        is_current = e["run_id"] == run_id[:8]
        row_style = ' style="background:#1a2a1a"' if is_current else ""
        md = e["mean_delta"]
        index_rows_html += (
            f'<tr{row_style}>'
            f'<td>{"► " if is_current else ""}{e["run_id"]}</td>'
            f'<td>{(e["started"] or "")[:16]}</td>'
            f'<td>{(e["last_fire"] or "")[:16]}</td>'
            f'<td>{e["n_fires"]}</td>'
            f'<td>{e["n_pairs"]}</td>'
            f'<td class="{cls(md)}">{fmtd(md)}</td>'
            f'</tr>'
        )

    # ── Sensitivity rows ──────────────────────────────────────────────────────
    n_fail = len(d["fail_pairs"])
    a1n = n
    a2n = n + n_fail
    a3n = n + n_fail

    def yn(v):
        if v is None:
            return "—"
        return '<span class="ok">YES</span>' if v > 0 else '<span class="bad">NO</span>'

    # ── Coverage strings ──────────────────────────────────────────────────────
    ecov_s = f"{100*d['entry_quote_coverage']:.1f}%  ({d['entry_ok_sig']}/{d['total_sig']})"
    ecov_c_val = sum(1 for r in load_data(run_id)["ctl_cov"]["5m"].values()) # placeholder
    # Recompute control entry_ok
    conn2 = get_conn()
    ctl_rows = conn2.execute(
        "SELECT entry_quote_ok FROM observer_lcr_cont_v1 WHERE run_id=? AND candidate_type='control'",
        (run_id,)
    ).fetchall()
    conn2.close()
    ctl_total = len(ctl_rows)
    ctl_entry_ok = sum(1 for r in ctl_rows if r["entry_quote_ok"] == 1)
    ecov_c = f"{100*ctl_entry_ok/ctl_total:.1f}%  ({ctl_entry_ok}/{ctl_total})" if ctl_total else "—"
    ecov_s_cls = "ok" if d["entry_quote_coverage"] >= 0.95 else "bad"
    ecov_c_cls = "ok" if (ctl_entry_ok/ctl_total >= 0.95 if ctl_total else False) else "bad"

    html = TEMPLATE.format(
        refresh=REFRESH_SEC, now=now,
        run_id=run_id,
        sha=sha, svc_status=svc, svc_cls=svc_cls,
        started_at=d["started_at"] or "—",
        n_fires=d["n_fires"], n_pairs=d["n_pairs"],
        warnings=warn_html,
        decision_banner=banner,
        # coverage
        sig_total=d["total_sig"], ctl_total=ctl_total,
        ecov_s=ecov_s, ecov_c=ecov_c,
        ecov_s_cls=ecov_s_cls, ecov_c_cls=ecov_c_cls,
        s1ok=d["sig_cov"]["1m"]["ok"],  s1due=d["sig_cov"]["1m"]["due"],
        c1ok=d["ctl_cov"]["1m"]["ok"],  c1due=d["ctl_cov"]["1m"]["due"],
        s1pct=cov_pct(d["sig_cov"]["1m"]), c1pct=cov_pct(d["ctl_cov"]["1m"]),
        s1cls=cov_cls(d["sig_cov"]["1m"]), c1cls=cov_cls(d["ctl_cov"]["1m"]),
        s5ok=d["sig_cov"]["5m"]["ok"],  s5due=d["sig_cov"]["5m"]["due"],
        c5ok=d["ctl_cov"]["5m"]["ok"],  c5due=d["ctl_cov"]["5m"]["due"],
        s5pct=cov_pct(d["sig_cov"]["5m"]), c5pct=cov_pct(d["ctl_cov"]["5m"]),
        s5cls=cov_cls(d["sig_cov"]["5m"]), c5cls=cov_cls(d["ctl_cov"]["5m"]),
        s5_429=d["sig_fail"]["r429"], c5_429=d["ctl_fail"]["r429"],
        s5_oth=d["sig_fail"]["other"], c5_oth=d["ctl_fail"]["other"],
        s15ok=d["sig_cov"]["15m"]["ok"], s15due=d["sig_cov"]["15m"]["due"],
        c15ok=d["ctl_cov"]["15m"]["ok"], c15due=d["ctl_cov"]["15m"]["due"],
        s30ok=d["sig_cov"]["30m"]["ok"], s30due=d["sig_cov"]["30m"]["due"],
        c30ok=d["ctl_cov"]["30m"]["ok"], c30due=d["ctl_cov"]["30m"]["due"],
        entry_quote_coverage=f"{100*d['entry_quote_coverage']:.1f}%  ({d['entry_ok_sig']}/{d['total_sig']})",
        cond_5m_coverage=f"{100*d['cond_5m_coverage']:.1f}%  ({d['n_pairs']}/{d['entry_ok_pairs']})",
        uncond_5m_completion=f"{100*d['uncond_5m_completion']:.1f}%  ({d['n_pairs']}/{d['total_sig']})",
        sig_valid=d["sig_valid"], ctl_valid=d["ctl_valid"],
        sig_invalid=d["sig_invalid"], ctl_invalid=d["ctl_invalid"],
        sinv_cls="bad" if d["sig_invalid"] else "ok",
        cinv_cls="bad" if d["ctl_invalid"] else "ok",
        invalid_reasons=", ".join(f"{k}:{v}" for k,v in d["invalid_reasons"].items()) or "none",
        # jitter
        sj1p50=jv(d["sig_jit"]["1m"],"p50"), sj1p95=jv(d["sig_jit"]["1m"],"p95"), sj1mx=jv(d["sig_jit"]["1m"],"mx"),
        cj1p50=jv(d["ctl_jit"]["1m"],"p50"), cj1p95=jv(d["ctl_jit"]["1m"],"p95"), cj1mx=jv(d["ctl_jit"]["1m"],"mx"),
        sj5p50=jv(d["sig_jit"]["5m"],"p50"), sj5p95=jv(d["sig_jit"]["5m"],"p95"), sj5mx=jv(d["sig_jit"]["5m"],"mx"),
        cj5p50=jv(d["ctl_jit"]["5m"],"p50"), cj5p95=jv(d["ctl_jit"]["5m"],"p95"), cj5mx=jv(d["ctl_jit"]["5m"],"mx"),
        # dt from entry
        sd1p50=jv(d["sig_dt"]["1m"],"p50"), sd1p95=jv(d["sig_dt"]["1m"],"p95"), sd1mx=jv(d["sig_dt"]["1m"],"mx"),
        cd1p50=jv(d["ctl_dt"]["1m"],"p50"), cd1p95=jv(d["ctl_dt"]["1m"],"p95"), cd1mx=jv(d["ctl_dt"]["1m"],"mx"),
        sd5p50=jv(d["sig_dt"]["5m"],"p50"), sd5p95=jv(d["sig_dt"]["5m"],"p95"), sd5mx=jv(d["sig_dt"]["5m"],"mx"),
        cd5p50=jv(d["ctl_dt"]["5m"],"p50"), cd5p95=jv(d["ctl_dt"]["5m"],"p95"), cd5mx=jv(d["ctl_dt"]["5m"],"mx"),
        # performance
        mean_d=fmtd(st.get("mean")), mean_cls=cls(st.get("mean")),
        med_d=fmtd(st.get("median")), med_cls=cls(st.get("median")),
        pct_pos=f"{100*st['pct_pos']:.1f}%" if st.get("pct_pos") is not None else "—",
        ci=f"[{fmtd(st.get('ci_lo'))}, {fmtd(st.get('ci_hi'))}]" if st.get("ci_lo") is not None else "—",
        mean_sig=fmtd(st.get("mean_sig")), msig_cls=cls(st.get("mean_sig")),
        mean_ctl=fmtd(st.get("mean_ctl")), mctl_cls=cls(st.get("mean_ctl")),
        n_pairs_used=n,
        # sensitivity
        a1n=a1n, a1mean=fmtd(st.get("mean")), a1cls=cls(st.get("mean")),
        a1ci=yn(st.get("ci_lo")),
        a2n=a2n, a2mean=fmtd(st.get("a2_mean")), a2cls=cls(st.get("a2_mean")),
        a2ci=yn(st.get("a2_ci_lo")),
        a3n=a3n, a3mean=fmtd(st.get("a3_mean")), a3cls=cls(st.get("a3_mean")),
        a3ci=yn(st.get("a3_ci_lo")),
        # charts
        cum_n_json=json.dumps(d["cum_n"]),
        cum_mean_json=json.dumps(d["cum_mean"]),
        cum_pct_json=json.dumps(d["cum_pct"]),
        # tables
        fire_rows=fire_rows_html,
        outlier_rows=outlier_rows_html,
        invalid_rows=inv_rows_html,
        index_rows=index_rows_html,
    )
    return Response(html, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
