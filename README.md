# Solana Narrative Trader

Paper trading system that tests whether real-time news narratives can predict profitable memecoin entries on Pump.fun.

## Architecture

```
supervisor.py           ← Process watchdog (starts/restarts everything)
├── paper_trader.py     ← Core: WebSocket → rug filter → narrative match → trade
│   ├── token_scanner.py      ← Reactive keyword matching (fixed v4)
│   ├── proactive_narratives.py ← Pre-generated trigger keywords
│   ├── narrative_monitor.py  ← RSS feed scanner + scoring
│   ├── twitter_signal.py     ← Twitter buzz logging (observation only)
│   └── database.py           ← SQLite schema + query helpers
├── flask_dashboard.py  ← Monitoring UI on port 5050
└── config/config.py    ← All constants and thresholds
```

## Status

**Phase: Data Collection (Paper Trading)**

- Narrative matching edge: NOT YET PROVEN (p > 0.05 on all tests)
- Twitter signal: logging only, not used for trade decisions yet
- Virtual exit strategies: 7 strategies tracked in parallel
- Key finding: exit strategy matters more than entry signal

See `RESEARCH_TRACKER.md` for full experimental history.

## Quick Start

```bash
pip install -r requirements.txt
python3 supervisor.py
```

Dashboard at `http://localhost:5050`

## Key Files

| File | Purpose |
|------|---------|
| `OPERATING_PRINCIPLES.md` | Guiding rules for the project |
| `RESEARCH_TRACKER.md` | Experimental log with hypotheses and results |
| `config/config.py` | All tunable parameters |
| `database.py` | Schema + all DB operations |
| `paper_trader.py` | Main trading loop |
| `twitter_signal.py` | Twitter API integration |

## NOT REAL MONEY

This is a paper trading research system. No real funds are at risk.
