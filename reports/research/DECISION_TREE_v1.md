# Decision Tree v1 — Solana Narrative Trader

**Date:** 2026-03-13
**Scope:** Feature Acquisition v2 phase through first live observer decision

---

## Root: After Final Recommendation Is Produced

```
Final recommendation produced
├── PROCEED
│   ├── Red-team battery = PASS
│   │   └── → Launch live observer (see Section 1)
│   └── Red-team battery = FRAGILE
│       ├── All fragile modules are non-critical
│       │   └── → Human sign-off required → Launch with caution (see Section 2)
│       └── Any critical module is fragile
│           └── → Treat as FAIL (see Section 4)
│
├── PIVOT
│   └── → Execute large-cap swing Stage B (see Section 3)
│
└── STOP
    └── → Program review (see Section 4)
```

---

## Section 1: PROCEED + Battery PASS

The candidate family has passed all gates. The following sequence is mandatory:

1. Run contract tests against frozen DB. All 10 must pass.
2. Generate provenance manifest and commit to GitHub.
3. Design the live observer (eligible-only, minimum size, pre-registered kill switch).
4. Review design. Commit to GitHub before launch.
5. Launch observer.
6. Monitor for 5 trading days. Apply kill switch if portfolio drawdown > 15%.

**Allowed next moves after launch:**
- Continue collecting feature_tape_v2 (collector stays running)
- Monitor observer performance
- After 20 trading days, decide whether to scale up or shut down

**Not allowed:**
- Adding new features to the running observer
- Changing the label horizon mid-run
- Running a second observer in parallel

---

## Section 2: PROCEED + Battery FRAGILE

A fragile result means the edge is real but not robust across all modules. Human judgment is required.

**Decision matrix:**

| Fragile module | Risk | Recommendation |
|----------------|------|----------------|
| cost_sensitivity | HIGH — edge may not survive real costs | Do not launch. Redesign with lower-cost execution. |
| temporal_stability | HIGH — edge may not persist | Do not launch. Collect more data. |
| benchmark_nogo | HIGH — structural distinction not proven | Do not launch. Document distinction explicitly. |
| concentration_sensitivity | MEDIUM — edge concentrated in few tokens | Launch with position limits per token. |
| missingness_sensitivity | MEDIUM — coverage bias possible | Launch with coverage filter (micro-covered only). |
| robust_summary | MEDIUM — CI includes zero | Launch at half size. Review after 10 trades. |
| placebo_null | LOW — marginal significance | Launch at half size. Review after 20 trades. |

**Rule:** If any HIGH-risk module is fragile, do not launch. Treat as FAIL.

---

## Section 3: PIVOT — Large-Cap Swing Study

The primary feature families found no edge. The fallback is the large-cap swing event study.

**Step 1.** Confirm the frozen dataset is available:
```bash
ls artifacts/feature_tape_v2_frozen_*.db
```

**Step 2.** Build the large-cap universe:
```bash
python3 scripts/dynamic_universe_builder.py \
    --db-path artifacts/feature_tape_v2_frozen_*.db \
    --output-db artifacts/largecap_universe.db
```

**Step 3.** Fetch OHLCV candles (requires GeckoTerminal or Birdeye API):
```bash
python3 scripts/ohlcv_loader.py \
    --universe-db artifacts/largecap_universe.db \
    --output-db artifacts/ohlcv_candles.db \
    --source geckoterminal --interval 15m --horizon 4h
```

**Step 4.** Run QA guardrails. All CRITICAL checks must pass:
```bash
python3 scripts/stageA_data_qc.py \
    --universe-db artifacts/largecap_universe.db \
    --ohlcv-db artifacts/ohlcv_candles.db
```

**Step 5.** If QA passes, proceed to Stage B analysis (not yet designed).

**If swing study also finds no edge:**
- → Section 4 (STOP)

---

## Section 4: STOP — No Viable Edge Found

All primary and fallback paths have been exhausted.

**Immediate actions:**
1. Stop the collector: `systemctl stop solana-feature-tape-v2.service`
2. Archive the frozen dataset to off-box storage.
3. Write a closure memo: `reports/synthesis/program_closure_memo.md`
4. Do not launch any observer.

**Program review questions:**
1. Was the data collection period long enough? (96 fires = 24h is short)
2. Was the feature family design correct? (order flow / urgency is the right hypothesis)
3. Is the token universe too noisy? (pumpfun tokens may have no exploitable structure)
4. Is the execution cost assumption correct? (round-trip may be higher than modeled)

**Allowed next moves after STOP:**

| Option | Condition | Description |
|--------|-----------|-------------|
| Feature Acquisition v3 | If data quality was good but features were wrong | Design new feature families with different hypothesis |
| Extended collection | If 96 fires is insufficient for power | Collect 384+ fires, re-run sweep |
| Product pivot | If no alpha hypothesis survives | Pivot to a different product (e.g., data product, analytics) |
| Full stop | If program is not viable | Archive everything, close program |

**Not allowed after STOP:**
- Launching any observer
- Running new experiments without a formal v3 proposal
- Changing the no-go registry retroactively

---

## Section 5: Health Failure During Collection

**Scenario: null_lanes > 0 at 10-fire checkpoint**

```
null_lanes > 0
└── Is the collector still running?
    ├── Yes → PATCH + RESTART (see Runbook Section F)
    └── No → Investigate crash → Fix → RESTART
```

**Scenario: Collector has stopped**

```
Collector stopped
└── Was it a crash or intentional?
    ├── Crash → Check journalctl → Fix → Restart
    └── Intentional → Confirm no hot-path changes → Restart
```

**Scenario: Zero rows written for 3+ consecutive fires**

```
Zero rows written
└── Is universe_snapshot being populated?
    ├── No → Scanner is down → Fix scanner first
    └── Yes → Check feature_tape_v2.py logs → Fix query
```

---

## Section 6: Red-Team Battery Fails After PROCEED

If the battery is run after the sweep and returns FAIL (e.g., due to more rigorous analysis):

```
Battery FAIL after initial PROCEED
└── Which module failed?
    ├── cost_sensitivity or temporal_stability → STOP. Do not launch.
    ├── benchmark_nogo → STOP. Document in no-go registry.
    └── Other module → FRAGILE path (Section 2)
```

**Rule:** A battery FAIL always overrides a sweep PROCEED. The battery is the final gate.

---

## Allowed Next Moves — Summary

| Current State | Allowed Next Moves |
|---------------|-------------------|
| Collection running | Wait. No changes. |
| 10-fire checkpoint | Health check only. No changes unless health fails. |
| 96-fire completion | Launch autopilot (if not running). No other changes. |
| Final recommendation: PROCEED + PASS | Design and launch observer. |
| Final recommendation: PROCEED + FRAGILE | Human review. Launch only if all fragile modules are low-risk. |
| Final recommendation: PIVOT | Execute large-cap swing Stage B. |
| Final recommendation: STOP | Program review. No observer. |
| Any state | Update docs, add to no-go registry (additions only), fix health failures. |

**Never allowed at any state:**
- Launching an observer before final recommendation
- Modifying the collector, schema, or labels during collection
- Removing entries from the no-go registry
- Running a second observer in parallel with the first


---

## Section 7: Post-Feature-Acquisition-v2 Closure (Added 2026-03-15)

The final recommendation was **STOP**. Per Section 4 of this decision tree, the program enters review.

```
Final recommendation: STOP
└── Feature Acquisition v2 line is CLOSED
    ├── Option A: Stop the program entirely
    │   └── No further action. Archive everything.
    ├── Option B: New program — wallet/deployer/"who" data
    │   └── Requires: new data source, new hypothesis, new no-go check
    │       └── Must NOT reuse universe_snapshot / microstructure_log features
    └── Option C: New program — large-cap swing / different market
        └── Requires: new market definition, new data source, new hypothesis
            └── Must NOT reuse memecoin long-only selection framework
```

**Current state:** Awaiting human decision among options A, B, or C.
See `reports/synthesis/post_v2_options.md` for details.

---

## Section 8: Large-Cap Swing Stage A (2026-03-15)

**Question:** Do established Solana tokens show a cost-adjusted edge for pullback or breakout entries at slower horizons?

**Answer:** NO. 0/18 scenarios passed. Both signals produce negative expected value before costs.

**Decision:** Close Large-Cap Swing program at Stage A. Do not proceed to Stage B.

**Remaining path:** Option A (stop) or Option C (wallet/deployer/early-buyer).

---

## Section 9 — Who Family Pilot v1 (2026-03-15)

**Entry:** Post feature-tape-v2 and large-cap-swing closure, the wallet/deployer/early-buyer family was the last remaining candidate from post_v2_options.md.

**Design:** Adversarial feasibility pilot. 20 tokens (10 stronger, 10 weaker by +1h return) from frozen 96-fire artifact. On-chain lookup for deployer wallets and first 10–20 buyers via Helius RPC.

**Result:** NO-GO.
- Deployer identification: BLOCKED (pumpfun mint authority revoked)
- Early-buyer overlap: Anti-signal (z = -3.12, stronger < null)
- Concentration: No difference
- Data feasibility: Poor (55% extraction rate, asymmetric)

**Decision:** Close the wallet signal family. All three post-v2 options have been evaluated. No viable research line remains.

---

## Section 10: Drift Perps State Study (2026-03-15)

**Question:** Do Drift SOL-PERP state variables (funding, mark-oracle spread, liquidations) contain a tradable edge?

**Answer:** No. 0/27 combinations passed all gates. Funding dislocation shows no mean-reversion. Mark-oracle spread is structural, not tradable. Liquidation data is too shallow for evaluation.

**Decision:** NO-GO. No Stage B. Research program exhausted across all tested families (spot momentum, spot microstructure, spot swing, wallet/deployer, derivatives state).
