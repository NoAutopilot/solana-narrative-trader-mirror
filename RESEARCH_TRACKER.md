# Solana Narrative Trader — Research Tracker
> Last updated: 2026-02-22 23:30 UTC
> Status: DATA COLLECTION PHASE — NOT READY FOR REAL FUNDS

---

## MISSION
Build a profitable automated Solana memecoin trader that uses narrative signals (breaking news/events) to identify tokens with asymmetric upside on pump.fun.

## NORTH STAR METRIC
Consistent profitability WITHOUT relying on outlier moonshots. The base case (non-moonshot trades) must at least break even.

---

## WHAT WE'VE PROVEN (with data)

### P1: The system can detect and trade tokens in real-time
- **Evidence:** 880+ closed trades over ~24 hours, zero missed moonshots
- **Confidence:** HIGH — mechanically verified

### P2: Exit strategy matters more than entry signal
- **Evidence:** All 7 virtual strategies are profitable. Diamond hands (+0.0205 avg) outperforms scalper (+0.0062 avg) by 3.3x. This holds across ALL tokens, not just narrative matches.
- **Confidence:** HIGH — 168-470 trades per strategy, consistent ranking

### P3: Moonshots are the profit engine (power law distribution)
- **Evidence:** Washington vs. Trump = +1.16 SOL (3,872%). Remove it and true narrative total PnL drops from +0.72 to -0.16 SOL.
- **Confidence:** HIGH — consistent with pump.fun token distribution research
- **Implication:** We need to maximize capture on winners, not minimize losses

### P4: Winners exit fast, losers bleed slowly
- **Evidence:** Take profit exits avg <2 min hold. Timeout exits avg 15-20 min hold.
- **Confidence:** HIGH — 880+ trade sample, consistent pattern

### P5: The old matching logic was ~60% false positives
- **Evidence:** Retroactive re-scoring: 103 true matches, 163 false positives, 236 uncategorizable. Caused by substring matching of 3-letter words ("all" in "chronically", "arm" in "marmot").
- **Confidence:** HIGH — manually verified 15 specific examples
- **Fixed:** Session 3 rewrote keyword_match_score with whole-word matching + stop words

---

## WHAT WE ASSUME (unproven)

### A1: Narrative matching adds value over random selection
- **Current data (CLEAN):** True narrative 17.5% WR vs Control 11.1% WR
- **Statistical tests:** Chi-squared p=0.09, Welch's t-test p=0.52, Mann-Whitney p=0.79
- **Status:** NOT PROVEN. Win rate gap is suggestive (p=0.09) but PnL difference is not significant. Need clean data with fixed matching.
- **Risk if wrong:** The entire thesis is invalid

### A2: Political narratives specifically drive the edge
- **Current data:** Political = 37 trades, +1.00 SOL total. WITHOUT outlier: -0.16 SOL, 22.2% WR
- **Status:** NOT PROVEN. The entire political profit is one trade. Need 100+ clean political trades.
- **What would prove it:** Political WR >20% over 100+ trades with fixed matching

### A3: Cost model (4% in + 4% out) is accurate for real trading
- **Status:** UNTESTED — biggest unknown for going live
- **What would prove it:** Micro-live test comparing paper PnL to actual PnL

### A4: The system works across different market conditions
- **Current data:** ~24 hours of data, single market regime
- **Status:** NOT PROVEN. Need data from multiple days.

### A5: G_diamond_hands (60min hold) is the best strategy
- **Current data:** 25.6% WR, +0.0205 avg on 168 exits
- **Status:** PROMISING — largest sample yet, consistently #1 ranked
- **What would prove it:** Maintaining lead over 500+ exits

### A6: Clean matching will show stronger narrative signal
- **Current data:** Just deployed fixed matching. Zero clean trades yet.
- **Status:** UNTESTED — this is the key question for the next 48 hours
- **What would prove it:** True narrative WR >20% with clean matching over 200+ trades

---

## WHAT WE'RE TESTING RIGHT NOW

| Test | Metric | Target | Current | ETA |
|------|--------|--------|---------|-----|
| Clean matching signal | True narrative WR | >20% | 17.5% (dirty data) | 48 hrs |
| Clean matching significance | p-value < 0.05 | Significant | p=0.09 (dirty) | 48 hrs |
| Diamond hands at scale | WR over 500 exits | >25% WR | 25.6% (n=168) | ~24 hrs |
| Multi-day robustness | Profitable across days | 2+ days | 1 day | 48 hrs |
| **Twitter signal correlation** | **WR by tweet_count bucket** | **Higher tweets = higher WR** | **Logging deployed, 0 data** | **48 hrs** |

---

## DECISIONS MADE

| Date | Decision | Rationale |
|------|----------|-----------|
| Feb 21 | Paper trade only, 0.04 SOL/trade | Data collection phase, minimize risk |
| Feb 21 | 7 parallel virtual strategies | Test multiple exit approaches simultaneously |
| Feb 22 | Raised max concurrent 25→50 | Was discarding 56% of matched tokens |
| Feb 22 | Added trailing TP + proactive engine | Capture more upside, faster matching |
| Feb 22 | Added supervisor.py for auto-restart | Self-healing after crashes |
| Feb 22 | Rewrote keyword_match_score (v2) | Old matching was ~60% false positives |
| Feb 22 | Added 130+ stop words to matching | Generic words ("call", "step", "rise") caused garbage matches |
| Feb 22 | Whole-word matching + compound detection | "trump" in "DevilTrump" = match, "all" in "chronically" = no match |
| Feb 22 | Scheduled 48hr clean data check-in | Need clean data before any live decisions |
| Feb 22 | Added Twitter signal logging (observation only) | Test if social buzz correlates with trade outcomes |
| Feb 22 | Updated OPERATING_PRINCIPLES with adversarial checklist | Session 3 exposed confirmation bias in prior findings |

---

## WHAT'S BLOCKING REAL FUNDS

1. **Narrative edge unproven with clean data** — Old data was corrupted by false positives
2. **Concentration risk** — Profit driven by 1 outlier trade
3. **Single day of data** — Need multiple days
4. **Cost model untested** — Real slippage unknown
5. **Clean matching untested** — Just deployed, zero trades with new logic

### Minimum criteria for micro-live (0.01 SOL/trade):
- [ ] 200+ true narrative trades with CLEAN matching
- [ ] True narrative WR significantly > Control WR (p < 0.05)
- [ ] Profitable across at least 2 separate days
- [ ] Diamond hands strategy maintains >20% WR over 300+ exits
- [ ] Base case (excluding top 3 trades) at least breaks even

### Minimum criteria for real live (0.1 SOL/trade):
- [ ] All micro-live criteria met
- [ ] Micro-live confirms cost model within 3% of paper
- [ ] System profitable for 72+ cumulative hours
- [ ] Max drawdown < 2 SOL in any rolling 4-hour window
- [ ] Automated kill switch tested and confirmed working

---

## SYSTEM STATUS

| Component | Status | Last Verified |
|-----------|--------|---------------|
| paper_trader.py | NEEDS RESTART with twitter_signal | 2026-02-22 05:35 UTC |
| Matching logic | v2 (fixed) | 2026-02-22 23:14 UTC |
| Twitter signal | Module ready, needs integration into paper_trader.py | 2026-02-22 05:35 UTC |
| Kill switch | OFF | 2026-02-22 23:14 UTC |
| DB size | ~4 MB | 2026-02-22 23:14 UTC |

---

## SESSION LOG

### Session 1 (Feb 21, 19:30-21:00 UTC)
- Built paper trader v3 with scientific experiment framework
- 6 hypotheses, 4 exit strategies, control group
- First 332 trades collected

### Session 2 (Feb 22, 00:30-02:45 UTC)
- Audited data quality, found virtual strategy survivorship bias
- Fixed: decoupled virtual strategies, added G_diamond_hands
- Added trailing TP, proactive narrative engine, supervisor.py
- Key finding: system profitable (+0.89 SOL) but driven by 5 outliers
- Key finding: narrative vs control NOT statistically significant yet

### Session 3 (Feb 22, 23:00-23:30 UTC)
- **CRITICAL FIX:** Discovered keyword_match_score was ~60% false positives
  - "all" in "chronically" → 85 score (should be 0)
  - "arm" in "marmot" → 82 score (should be 0)
  - "BBC" as initials of "bitcoin bull catalyst" → 80 score (should be 0)
- Rewrote matching: whole-word only, 130+ stop words, compound word detection
- Retroactive analysis: 103 true matches, 163 false positives out of 266 "narrative" trades
- **Key finding:** True narrative WR (17.5%) vs Control (11.1%) is suggestive but NOT significant (p=0.09)
- **Key finding:** Political edge is entirely one outlier (WVT +1.16 SOL). Remove it → political loses money.
- **Key finding:** Exit strategies ALL profitable. Diamond hands best. Entry signal matters less than exit.
- Scheduled 48hr check-in for clean data analysis

### Session 4 (Feb 22, 05:00-05:40 UTC)
- **Adversarial evaluation**: ruthlessly stress-tested all claims against operating principles
  - System profit (+0.09 SOL) is entirely one lucky trade. Remove it → -1.01 SOL
  - No statistical significance on any test (best: p=0.09 chi-squared)
  - Virtual strategies 34x actual PnL — simulation is lying
  - Features built (12) vs hypotheses resolved (1) — wrong ratio
- **External research**: studied Ave.ai, Reddit, Bitquery, arXiv paper on pump.fun
  - Key insight: profitable traders use 3+ converging signals, not one
  - Key insight: Twitter/social monitoring is the #1 edge, not RSS feeds
  - Key insight: bonding curve velocity + smart money = strongest academic predictor
- **Built twitter_signal.py**: Twitter search API module (observation-only)
  - Uses `Twitter/search_twitter` with `type=Latest` parameter
  - Logs: tweet_count, total_engagement, max_engagement, has_kol, top_tweet
  - Rate-limited (1 call per 3 sec), error-tolerant, JSON-serializable
- **Updated database.py**: Added `twitter_signal_data` TEXT column to trades table
  - Safe migration via `_safe_add_column` — won't break existing DB
  - `log_trade()` now accepts optional `twitter_signal_data` dict
- **NEXT**: Integrate twitter_signal into paper_trader.py's entry flow, restart system
