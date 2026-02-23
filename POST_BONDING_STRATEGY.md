# Post-Bonding Momentum Strategy: Parallel Experiment Proposal

## Context

This is a **parallel experiment** alongside the existing lottery-ticket strategy (Strategy B). The lottery-ticket system catches tokens at birth on the bonding curve. This new strategy catches tokens that have **already graduated** — proven survivors with real liquidity.

---

## The Core Idea

Only ~0.63% of pump.fun tokens graduate (pass bonding). Those that do have demonstrated real coordinated demand. But graduation also triggers a known risk: **creator pump-and-dump** at the transition from virtual to real AMM liquidity.

**The hypothesis:** Among graduated tokens, a subset continues to grow (driven by genuine community/narrative momentum), while the rest dump. If we can distinguish these two groups using on-chain signals in the first few minutes post-graduation, we can enter the growers and avoid the dumps.

---

## Strategy Framework (Applying Our Principles)

### Principle 1: Trust Nothing, Prove Everything

**What we know (from the academic paper + our data):**
- Fast liquidity accumulation (few trades to reach bonding threshold) = strongest predictor of graduation
- Bot-heavy tokens have LOWER graduation probability
- Creator dump is systematic at graduation — the virtual→real liquidity transition creates a sell incentive
- 4-sigma negative return on MAD-scaled log-returns reliably detects dumps

**What we DON'T know (must test):**
- What % of graduated tokens continue to 250k+ mcap
- Whether volume/holder signals predict post-graduation trajectory
- Whether candle patterns in the first 5-10 minutes post-graduation are predictive
- Whether this is more profitable than the lottery-ticket approach

### Principle 3: Small Bets, Fast Iteration

Start with paper trading only. No capital at risk until we have data.

---

## Proposed Signal Set

### Entry Signals (all must be true to enter):

| Signal | Rationale | Data Source |
|---|---|---|
| **Token graduated** (passed bonding) | Survival filter — only 0.63% make it | PumpPortal WebSocket / DexScreener |
| **No creator dump detected** in first 2 min | Academic paper: creator dumps are systematic at graduation | On-chain TX monitoring (Helius) |
| **Volume acceleration** post-graduation | Sustained buying pressure, not just graduation spike | Birdeye OHLCV (15s candles) |
| **Holder count growing** (not concentrated) | Broad distribution = organic demand, concentrated = whale setup | Helius getTokenLargestAccounts |
| **Mcap > 100k and rising** | Momentum confirmation — don't catch falling knives | DexScreener pairs API |

### Exit Signals (any triggers exit):

| Signal | Rationale |
|---|---|
| **Take-profit: trailing 15% from peak** | Wider trail than lottery (these are slower movers) |
| **Stop-loss: -10% from entry** | Tighter stop — graduated tokens shouldn't dump 10% if thesis is correct |
| **Volume collapse** (< 50% of entry-window volume) | Momentum exhausted |
| **Large holder sells > 5% of supply** | Whale exit = dump incoming |
| **Timeout: 30 minutes** | If it hasn't moved in 30 min, thesis is wrong |

### Key Differences from Lottery-Ticket Strategy:

| Dimension | Lottery (Strategy B) | Post-Bonding (New) |
|---|---|---|
| Entry point | Token creation (0 SOL mcap) | Post-graduation (~$69k mcap) |
| Trade frequency | ~180/hour | ~5-15/hour (far fewer graduates) |
| Expected win rate | ~17% | Unknown (hypothesis: 30-50%) |
| Expected avg win | Bimodal (small or moonshot) | Moderate (50-200%) |
| Expected avg loss | -20% | -10% |
| Hold time | 30s - 2 min | 5 - 30 min |
| Capital per trade | 0.04 SOL | 0.1-0.5 SOL (higher conviction) |
| Fee impact | 6.6% at 0.04 SOL | 1.5% at 0.5 SOL (TX fees negligible) |

---

## Data Sources & APIs

### Free / Low-Cost:
1. **DexScreener API** (free, 300 req/min) — pair data, volume, price, liquidity
2. **Helius RPC** (free tier: 100k requests/day) — token holders, largest accounts, TX parsing
3. **PumpPortal WebSocket** (already connected) — graduation events in real-time

### Paid (if needed later):
4. **Birdeye API** ($49/mo starter) — OHLCV candles down to 1s, holder distribution over time
5. **Jupiter API** (free) — swap execution when we go live

---

## Implementation Plan

### Phase 1: Data Collection (Paper Only) — 1 week

Build a **parallel paper trader** on the VPS that:
1. Listens for graduation events on PumpPortal WebSocket
2. For each graduated token, collects:
   - Price every 15 seconds for 30 minutes (DexScreener)
   - Holder count at 1, 5, 10, 30 minutes (Helius)
   - Volume in 1-min buckets (DexScreener)
   - Top 10 holder concentration (Helius)
   - Creator wallet activity (Helius TX parsing)
3. Logs everything to a separate SQLite DB
4. Does NOT trade — just collects signal data

**Goal:** Build a dataset of 500+ graduated tokens with full signal profiles.

### Phase 2: Signal Analysis — After 500+ tokens collected

Run the adversarial analysis framework:
1. Which graduated tokens hit 250k mcap? What % ?
2. Do any of our signals predict the 250k+ group at entry?
3. What's the optimal entry timing (immediate vs. wait for confirmation)?
4. What's the dump rate and can we detect it early?
5. Is there a profitable paper strategy using these signals?

### Phase 3: Paper Trading — If Phase 2 shows signal

Add entry/exit logic to the collector:
1. Paper-enter tokens that pass all entry signals
2. Paper-exit on any exit signal
3. Run for 1 week, apply the same adversarial review we use for Strategy B
4. Calculate: win rate, avg win, avg loss, moonshot rate, fee-adjusted PnL

### Phase 4: Micro-Live — If Phase 3 is profitable

Same phased deployment as Strategy B:
1. 0.1 SOL per trade, 2-hour window
2. Compare live fills to paper
3. Scale if within 2x of paper performance

---

## Testable Hypotheses (Principle 1)

| # | Hypothesis | How to Test | Kill Criteria |
|---|---|---|---|
| H1 | >10% of graduated tokens reach 250k mcap | Phase 1 data collection | If <5%, the opportunity is too rare |
| H2 | Volume acceleration in first 5 min predicts 250k+ | Phase 2 correlation analysis | If p > 0.05, signal is noise |
| H3 | Creator dump detection avoids >50% of failures | Phase 2 dump analysis | If dump detection misses >30%, unreliable |
| H4 | Holder concentration <30% in top 10 predicts growth | Phase 2 analysis | If no correlation, drop signal |
| H5 | Paper strategy is profitable after fees | Phase 3 paper trading | If net negative over 1 week, kill strategy |
| H6 | Live execution preserves paper edge within 2x | Phase 4 micro-live | If gap >2x, execution is the problem |

---

## Why This Complements (Not Replaces) the Lottery-Ticket Strategy

1. **Different market regime:** Lottery catches chaos at birth. Post-bonding catches momentum after proof-of-demand.
2. **Different capital profile:** Lottery = many tiny bets, high frequency. Post-bonding = fewer, larger, higher-conviction bets.
3. **Fee efficiency:** At 0.1-0.5 SOL per trade, TX fees are <2% friction vs 6.6% for lottery.
4. **Uncorrelated signals:** A token that graduates but then dumps would be caught by Strategy B (if it was a narrative match) but avoided by this strategy (dump detection).
5. **Shared infrastructure:** Same VPS, same WebSocket connection, same DB backup system.

---

## Risks (Principle 1: What Could Kill This)

1. **Too few graduates per hour** — if only 2-3 tokens graduate/hour, sample collection is slow
2. **API rate limits** — Helius free tier (100k/day) might not cover holder checks for all graduates
3. **Signal latency** — by the time we detect "volume acceleration," the move is already priced in
4. **Selection bias** — we might only see the survivors in our analysis (graduated tokens that dump fast disappear from view)
5. **Capital competition** — running both strategies on the same wallet creates capital allocation conflicts

---

## Immediate Next Step

**Build the Phase 1 data collector on the VPS.** Zero capital risk. Just listen for graduations and log signal data. After 3-5 days, we'll have enough data to know if this is worth pursuing.

Want me to build it?
