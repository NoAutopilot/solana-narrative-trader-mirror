# Solana Event / Governance Alpha — Stage A Summary

**Program:** solana_event_alpha_stageA  
**Date:** 2026-03-15  
**Verdict:** BLOCKED

---

## One-Paragraph Summary

The Stage A pilot identified 14 qualifying events from official Solana ecosystem sources over a 180-day window (Sep 15 2025 – Mar 15 2026). The pre-registered kill criterion K1 requires a minimum of 15 events; the dataset falls one short. Beyond the kill criterion, K4 also triggers independently: no event class reaches the minimum sample of 10. The raw price data shows no consistent directional signal across any class or window at conservative cost. The most theoretically compelling event — JTO JIP-26 (a DAO vote to use 100% of protocol revenue for buybacks) — produced a −28.1% return in the 7 days following announcement. The program cannot issue a GO or NO-GO verdict on this evidence. It is BLOCKED pending a redesign decision.

---

## Kill Criteria Triggered

| Kill | Description | Status |
|---|---|---|
| K1 | Total qualifying events < 15 | **TRIGGERED** (N = 14) |
| K4 | No event class has N ≥ 10 | **TRIGGERED** (max class N = 6) |

---

## Class Summary

| Class | N | Best window | Mean (7d) | Median (7d) | Beats bench? | Verdict |
|---|---|---|---|---|---|---|
| SUPPLY_CHANGE | 6 | — | −5.66% | −0.67% | No | NO SIGNAL |
| REWARD_CHANGE | 5 | 1d median +1.4% | −14.19% | −9.33% | No (7d) | INSUFFICIENT SAMPLE |
| GOVERNANCE_EXECUTION | 3 | 7d median +7.5% | −3.44% | +7.54% | Yes (7d) | INSUFFICIENT SAMPLE |

---

## Three Options

### Option A: Extend Window to 12 Months

Re-register the design with a 12-month window (Sep 2024 – Sep 2025), covering the bull market period. Expected yield: 30–50 qualifying events. This would allow a proper test of the hypothesis. The design must be re-registered before data collection begins.

**Pros:** Larger sample, includes bull market regime, tests whether governance events matter when sentiment is positive.  
**Cons:** The bull market period may produce false positives (everything went up). Requires full re-registration and re-collection.

### Option B: Add New Event Classes and Re-Run

Keep the 180-day window but add two new pre-registered event classes:
- **FEE_SWITCH:** Protocol activates fee collection for the first time (e.g., Uniswap-style fee switch)
- **CEX_LISTING:** Solana token lists on Binance, Coinbase, or OKX for the first time

Both classes have clearer price mechanisms and more historical examples in the window. Expected additional events: 8–12, bringing total to 22–26.

**Pros:** Stays in the current regime, adds higher-signal event classes, no regime-mixing problem.  
**Cons:** CEX listing events are well-known and heavily front-run. Fee switch events are rare on Solana.

### Option C: Close the Program

Accept that the Solana governance event space is too sparse and too well-monitored for a retrospective event study to produce actionable alpha. Redirect resources to the next test in the queue.

**Pros:** Honest. Avoids sunk cost escalation. Frees capacity for better-fit programs.  
**Cons:** Does not falsify the hypothesis — it simply cannot test it at this scale.

---

## Recommended Next Move

**Option C — Close the program.**

The fundamental problem is not sample size. It is that Solana governance events are:
1. Announced on public forums days or weeks before execution
2. Affecting tokens with thin perps markets (hard to short, hard to size)
3. Dominated by macro and sector forces that overwhelm protocol-level news
4. Concentrated in a small number of tokens (JUP, JTO, KMNO, MNDE, PYTH)

Even with a larger sample, the edge would need to come from information advantage (knowing about governance events before they are public) or from a systematic pattern that survives regime changes. Neither is available to a solo researcher working from public sources.

The 1d positive median for REWARD_CHANGE and the 7d positive median for GOVERNANCE_EXECUTION are interesting observations, not actionable signals. They would require 30–50 more events to test properly, and by the time that data exists, the regime will have changed.

**If Option A or B is chosen instead**, the design must be fully re-registered before any data is examined. No parameters from this Stage A run carry forward.

---

## Backup Move

**Option B — Add CEX_LISTING class and re-run.**

CEX listing events are the highest-signal event class in crypto. The pre-listing run-up and post-listing dump are well-documented patterns. If Solana tokens are listing on major CEXes during the 180-day window, this class alone could provide enough events (N ≥ 10) to run a valid test. This is a different hypothesis from governance alpha, but it fits the same program structure.

---

## One Clear "Do Not Do" Move

**Do not extend the window retroactively to include bull market data without re-registering the design.**

Mixing a bear market event study with bull market data, without pre-declaring the regime split and separate pass/fail thresholds for each regime, is a form of data mining. The bull market period will produce positive returns on almost any event class simply because the market was rising. This would produce a false GO verdict.

---

## Connection to Profit Arena Map

This program was testing a hypothesis adjacent to **Arena 5 (Research / Falsification / Anti-Bullshit Engine)** — specifically, whether governance events produce measurable price reactions that could be systematically traded. The answer, at this sample size and in this regime, is: **cannot determine**.

The more durable finding is the meta-observation: the Solana governance event space is sparse, public, and dominated by macro forces. This is itself a research output — the kind of falsification work that has product value as a published analysis, even if it does not produce a trading strategy.

---

## Artifacts

| File | Description |
|---|---|
| `solana_event_alpha_stageA_design.md` | Pre-registered design (locked before data collection) |
| `solana_event_alpha_stageA_results.md` | Full results with event-level data and class analysis |
| `solana_event_alpha_stageA_summary.md` | This document |
| `event_dataset.csv` | 14-event dataset with all price data and returns |
| `benchmark_dataset.csv` | Random-date benchmark trades (N=20 per event) |
| `metrics_summary.csv` | Class-level metrics across all windows and cost levels |
| `verdict.json` | Machine-readable verdict |
| `run_log.txt` | Full execution log |
