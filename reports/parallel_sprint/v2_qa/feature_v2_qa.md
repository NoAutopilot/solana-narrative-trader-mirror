# Feature Acquisition v2 — QA Report

**Date:** 2026-03-12
**Author:** Manus AI
**Scope:** Evaluate the three candidate feature families defined in `feature_acquisition_v2_design_note.md` against no-lookahead, coverage, novelty, and collection-risk criteria.

---

## Background

Feature Tape v1 tested 17 features across two tracks (full-sample and micro-derived) at three horizons (+5m, +15m, +30m). All features failed the promotion bar: median net-proxy was zero or negative for every feature at every horizon. The binding constraints were (1) round-trip costs of ~0.51% consuming gross alpha, (2) right-skewed returns where means are outlier-driven, and (3) non-random micro coverage gaps (Orca/Meteora excluded).

Feature Acquisition v2 proposes three candidate families that must be conceptually distinct from the tested momentum/direction family. This QA evaluates whether each family meets that bar.

---

## Family 1: Trade-by-Trade Order Flow / Urgency

### No-Lookahead Guarantee

All five candidate features (`urgency_score`, `inter_trade_accel`, `buy_sequence_len`, `large_trade_share_5m`, `vwap_deviation`) are defined using trades with `block_time <= fire_epoch`. This is a clean no-lookahead boundary. However, the implementation must enforce strict filtering — Solana block times can have minor clock skew (typically <1s), and the collection script must use `block_time < fire_epoch` (strict less-than) to avoid any edge case.

**Assessment: PASS** — no-lookahead is achievable with careful implementation.

### Coverage Risk

The design note estimates 60–75% coverage, which is similar to the current micro gap. This is a significant concern because the same Orca/Meteora gap persists unless Helius covers those pools. The Solana RPC rate limit (`getSignaturesForAddress` + `getTransaction`) may restrict per-fire trade history depth, especially at 40+ candidates per fire. Helius enhanced transactions API requires a paid plan for high-throughput access.

**Assessment: MEDIUM RISK** — coverage is likely 60–75%, which meets the 70% minimum gate only marginally. The non-random nature of the gap (same venue exclusion as Track B) means results cannot be generalised to the full universe.

### Novelty vs Tested Features

This is the strongest candidate for genuine novelty. The tested features (`buy_sell_ratio_m5`, `signed_flow_m5`, `txn_accel_m5_vs_h1`) are 5-minute aggregates. The new family captures sequencing effects (`buy_sequence_len`, `inter_trade_accel`) not captured by any v1 feature, size-weighted urgency (`urgency_score` = trade_size / pool_depth) distinct from `avg_trade_usd_m5` which is a simple average, and VWAP deviation which captures intra-period price drift not captured by `r_m5` (a point-to-point return).

**Assessment: HIGH NOVELTY** — genuinely distinct from all tested features.

### Collection Complexity

| Factor | Assessment |
|--------|-----------|
| API calls per fire | ~40 candidates x 2 RPC calls = ~80 calls |
| Latency per fire | ~10-30s (depends on RPC response time) |
| Failure modes | RPC rate limits, timeout, partial trade history |
| Helius dependency | Required for Orca/Meteora coverage |
| Storage | ~768 KB per 96-fire run (negligible) |

**Assessment: MEDIUM COMPLEXITY** — achievable but requires robust error handling and rate-limit management.

### Overall Score

| Dimension | Score |
|-----------|-------|
| Signal plausibility | **HIGH** — trade-level urgency is a well-established alpha source in traditional markets |
| Collection risk | **MEDIUM** — RPC rate limits and venue coverage gaps are real risks |
| Novelty | **HIGH** — genuinely distinct from all tested features |

---

## Family 2: Route / Quote Quality

### No-Lookahead Guarantee

All features are computed at fire time via the Jupiter Quote API. The `quote_freshness_s` feature measures staleness of the best quote, which is inherently pre-fire. `route_depth_100/500`, `cross_venue_spread_pct`, and `multi_hop_flag` are all computed from a single API call at fire time.

**Assessment: PASS** — no-lookahead is clean.

### Coverage Risk

Jupiter API covers most Solana DEX pools. The design note estimates 85-90% coverage, which is significantly better than the micro coverage. However, very new pools (< 5 minutes old) may not be indexed by Jupiter, low-liquidity pools may return stale or zero-depth quotes, and Jupiter cache TTL (1-3s) means quotes may not reflect the exact fire-time state.

**Assessment: LOW RISK** — 85-90% coverage is well above the 70% gate.

### Novelty vs Tested Features

This is the **weakest** candidate for novelty. The tested features already include `jup_vs_cpamm_diff_pct` (Jupiter vs CPAMM price difference, SKIP in sweep), `round_trip_pct` (CPAMM-based round-trip cost, SKIP), and `impact_buy_pct` / `impact_sell_pct` (CPAMM-based impact, SKIP). The new features extend this by adding size-tiered depth and cross-venue spread, but the underlying hypothesis is the same: execution quality predicts tradability. The v1 sweep showed that execution quality features have near-zero tercile differentiation, suggesting the hypothesis itself may be weak.

**Assessment: LOW NOVELTY** — extends the same hypothesis that already failed. Risk of repeating the same failure with more granular data.

### Overall Score

| Dimension | Score |
|-----------|-------|
| Signal plausibility | **LOW** — same hypothesis as failed v1 features, just more granular |
| Collection risk | **LOW** — Jupiter API is reliable and well-documented |
| Novelty | **LOW** — extends the same execution-quality family that already failed |

---

## Family 3: Market-State Gating

### No-Lookahead Guarantee

All gate variables are global market state at fire time: `sol_price_trend_1h` from `universe_snapshot` (already collected), `dex_vol_trend_1h` from external API (Birdeye/DeFiLlama), `network_tps` from Solana RPC (public, no cost), and `mempool_congestion` from Solana RPC (public, no cost).

**Assessment: PASS** — all variables are strictly pre-fire global state.

### Coverage Risk

Market-state variables are global (not per-mint), so coverage is 100% by definition. This is the only family with zero coverage risk.

**Assessment: NO RISK** — 100% coverage guaranteed.

### Novelty vs Tested Features

This is genuinely novel — it is not a selection feature but a validity gate. No market-state gating was tested in v1. However, the design note correctly notes that this family is only useful if there is an underlying selection signal to gate. Since no selection signal has been found, a market-state gate alone cannot create alpha.

**Assessment: HIGH NOVELTY** — but only useful in combination with a working selection signal.

### Overall Score

| Dimension | Score |
|-----------|-------|
| Signal plausibility | **LOW** — a gate without a signal is useless; only valuable if combined with Family 1 |
| Collection risk | **LOW** — global variables, no per-mint coverage issues |
| Novelty | **HIGH** — genuinely distinct from all tested features |

---

## Summary Recommendation

| Family | Signal | Risk | Novelty | Priority |
|--------|--------|------|---------|----------|
| 1. Order Flow / Urgency | HIGH | MEDIUM | HIGH | **1st** |
| 2. Route / Quote Quality | LOW | LOW | LOW | **3rd (deprioritize)** |
| 3. Market-State Gating | LOW (standalone) | LOW | HIGH | **2nd (conditional on Family 1)** |

The recommended approach is to implement Family 1 (order flow / urgency) as the primary new feature family. Family 3 (market-state gating) should be added as a secondary layer only after Family 1 produces a candidate signal. Family 2 (route / quote quality) should not be implemented — it extends the same hypothesis that already failed.

The critical risk is that Family 1 inherits the same Orca/Meteora coverage gap as Track B. If this gap cannot be closed (via Helius or alternative data source), the results will be subset-only and non-generalisable, repeating the same limitation that prevented Track B from passing the promotion bar.
