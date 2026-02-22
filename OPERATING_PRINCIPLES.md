# Operating Principles — Solana Narrative Trader
> These principles govern every decision. Read this FIRST at the start of every session.
> Updated: 2026-02-22 after Session 3 adversarial evaluation.

---

## PRINCIPLE 1: TRUST NOTHING, PROVE EVERYTHING

- Every claim must have data behind it. "It seems to work" is not evidence.
- If a metric looks good, **stress-test it by removing the top 1, 3, and 5 performers**. If the result flips sign, you don't have an edge — you have a lottery ticket.
- Confidence intervals, not point estimates. A 15% win rate means nothing without knowing if it's [5%-25%] or [13%-17%].
- Survivorship bias is the default assumption until disproven. If you're only measuring winners, your data is lying.
- The market is adversarial. Every edge decays. Every assumption will be tested by real conditions.
- **Run at least 3 different statistical tests** (parametric, non-parametric, bootstrap). If they disagree, trust the most conservative one.
- **Never label a finding as HIGH confidence unless it survives outlier removal, passes p<0.05, AND holds across multiple time windows.** "Consistent ranking" on biased samples is not HIGH confidence.

## PRINCIPLE 2: SCIENTIFIC DATA COLLECTION

- Every change creates a before/after comparison. Tag everything with version, timestamp, and conditions.
- Control groups are mandatory. Without a baseline, you can't attribute results to your strategy.
- Sample size matters. Don't draw conclusions from <100 trades per group. Don't celebrate <50 samples.
- Record everything, even things you think don't matter. You don't know what the signal is yet.
- Negative results are results. "This doesn't work" is as valuable as "this works" — it narrows the search.
- **Measure coverage**: if a metric only covers 56% of trades, say so. Partial coverage = biased sample.
- **Track the denominator**: "50% win rate on 10 trades" is noise. Always report n alongside any percentage.

## PRINCIPLE 3: ADVERSARIAL SELF-EVALUATION

- **Before every session end, run the adversarial checklist** (see below). No claim survives without it.
- When presenting results, lead with what CONTRADICTS the thesis, not what supports it.
- For every "proven" finding, write the specific data point that would DISPROVE it. If you can't articulate the falsification condition, the finding is unfalsifiable and therefore unscientific.
- **The outlier test is mandatory**: remove the single best trade. Does the system still make money? If no, you don't have a system — you have survivorship bias dressed up as a strategy.
- **The time-window test is mandatory**: does the result hold across every 4-hour block? If all profit comes from one hour, it's a coincidence, not an edge.
- **The selectivity test is mandatory**: what percentage of tokens does the system trade vs. skip? If >30%, the filter is barely filtering. A coin flip is not a strategy.
- Compare virtual/simulated results to actual realized results. If the gap is >2x, the simulation is lying.

## PRINCIPLE 4: ONGOING LEARNING

- The system should get smarter every hour it runs, not just collect more of the same data.
- After every session: What did we learn? What hypothesis was confirmed or killed? What's the next experiment?
- Don't optimize for the last session's conditions. Optimize for robustness across conditions.
- When something works, ask "why?" and "will it keep working?" — not "how do I do more of it?"
- **When something doesn't work, kill it fast.** Don't keep testing a dead hypothesis hoping for different data. Set explicit kill criteria upfront.

## PRINCIPLE 5: MAINTAIN THE THREAD

- At the START of every session, read RESEARCH_TRACKER.md and this file.
- At the END of every session, update RESEARCH_TRACKER.md with: new evidence, updated assumptions, decisions made, and what to do next.
- Every 60 minutes during a session, check: "Are we still working toward the north star metric, or have we drifted into implementation details?"
- When the user asks "where are we?", the answer should take 30 seconds, not 5 minutes of querying.

## PRINCIPLE 6: PROGRESS OVER ACTIVITY

- Building features is not progress. Answering questions with data is progress.
- The goal is not "a better trading system." The goal is "proven, consistent profitability."
- If we can't measure it, we shouldn't build it.
- Every hour spent should move at least one item from "assumed" to "proven" or "disproven."
- **Count the features built vs. hypotheses resolved.** If features > hypotheses, you're drifting. Session 1-3 built ~12 features and resolved ~1 hypothesis. That ratio should be inverted.

## PRINCIPLE 7: FEES ARE THE ENEMY, NOT AN AFTERTHOUGHT

- 8% round-trip fees destroy 55% of would-be winners. This is not a rounding error — it's the dominant force.
- **Every strategy must be evaluated NET of fees first.** Gross PnL is fiction.
- Real slippage on pump.fun low-liquidity tokens is likely 15-25%, not 8%. Until proven otherwise with live data, assume the worst.
- A strategy that is "slightly profitable before fees" is a losing strategy in production.

---

## ADVERSARIAL CHECKLIST (run before every session end)

Before marking ANY finding as "proven" or presenting results:

- [ ] **Outlier test**: Remove top 1, 3, 5 trades. Does the conclusion still hold?
- [ ] **Time-window test**: Does the result hold across each 4-hour block, or is it concentrated?
- [ ] **Selectivity test**: What % of tokens does the filter actually reject? >70% rejection = real filter.
- [ ] **Coverage test**: Does the metric cover >90% of trades, or is it a biased subsample?
- [ ] **Fee test**: Is the result positive AFTER realistic fees (8% minimum, 15% conservative)?
- [ ] **Sample size test**: n > 100 per group? If not, label as "preliminary" not "proven."
- [ ] **Multi-test agreement**: Do parametric, non-parametric, AND bootstrap tests all agree?
- [ ] **Simulation-reality gap**: Is virtual/simulated PnL within 2x of actual realized PnL?
- [ ] **Falsification condition**: Can you state what data would DISPROVE this finding?
- [ ] **Base rate comparison**: Is the result meaningfully better than buying random tokens?

---

## SESSION PROTOCOL

### On Session Start:
1. Read `OPERATING_PRINCIPLES.md` (this file)
2. Read `RESEARCH_TRACKER.md`
3. Check system health (processes running, DB intact, no errors)
4. Tell the user: "Here's where we are, here's what we're testing, here's what I recommend we do this session."

### Every 60 Minutes:
1. Check: Are we on track toward the north star metric?
2. Update RESEARCH_TRACKER.md if any hypothesis status changed
3. Brief the user: progress made, data collected, any surprises

### On Session End:
1. **Run the adversarial checklist** on every finding from this session
2. Update RESEARCH_TRACKER.md with all new findings (adversarially validated)
3. Verify system is stable and will continue collecting data
4. Tell the user: "Here's what we proved today, here's what's still open, here's what to look at next time."

---

## ANTI-PATTERNS TO AVOID

1. **Celebrating paper profits** — Paper trading has no slippage, no failed transactions, no MEV. Real performance will be worse.
2. **Overfitting to one session** — One good evening doesn't prove a strategy. Multiple days across different conditions does.
3. **Feature creep** — Adding complexity before proving the basics work. The narrative filter isn't proven yet; don't build on top of an unproven foundation.
4. **Ignoring base rates** — 96% of pump.fun tokens go to zero. Our system needs to be dramatically better than random, not marginally better.
5. **Confirmation bias** — Looking at the data that supports the thesis and ignoring what contradicts it. The control group outperforming narrative in some metrics is a red flag, not noise.
6. **Losing the thread** — Getting deep into code changes and forgetting why we're making them. Every change should trace back to a hypothesis we're testing.
7. **Trusting virtual strategies at face value** — Virtual PnL was 34x actual PnL. Always compare simulated to realized. If the gap is large, the simulation is wrong, not reality.
8. **Labeling partial-coverage metrics as proven** — If a metric only covers 56% of trades, it's a biased sample. Say so explicitly.
9. **Treating p=0.09 as "suggestive"** — It's not significant. Period. Don't soften the language to keep hope alive.
10. **Building dashboards before proving the thesis** — Infrastructure for an unproven system is wasted effort. Prove first, build second.

---

## THE QUESTION TO ALWAYS ASK

> "If I were betting my own money on this RIGHT NOW, what would I need to see first?"

If the answer is "more data" — then our job is data collection, not feature building.
If the answer is "proof that X works" — then our job is testing X, not building Y.
If the answer is "I'm not sure" — then our job is figuring out what we don't know.

> "Remove the best trade. Am I still making money?"

If no — you don't have a strategy. You have a lottery ticket.
