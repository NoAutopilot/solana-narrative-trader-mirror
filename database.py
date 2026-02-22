"""
Database layer — SQLite-backed storage for all system state.
Tracks: narratives, token evaluations, trades, outcomes, learning history,
and research data (all tokens seen, price snapshots, narrative spawn rates).
"""

import sqlite3
import json
import os
from datetime import datetime
from config.config import DB_PATH, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_add_column(cursor, table, column, col_type, default=None):
    """Add a column to a table if it doesn't already exist."""
    try:
        default_clause = f" DEFAULT {default}" if default is not None else ""
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")
    except sqlite3.OperationalError:
        pass  # Column already exists


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Trending narratives detected
    c.execute("""
        CREATE TABLE IF NOT EXISTS narratives (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at TEXT    NOT NULL,
            keyword     TEXT    NOT NULL,
            score       REAL    NOT NULL,
            sources     TEXT,
            velocity    REAL,
            durability  REAL,
            expired     INTEGER DEFAULT 0,
            tokens_spawned INTEGER DEFAULT 0,
            first_token_lag_min REAL    -- minutes from detection to first matching token
        )
    """)

    # Every token evaluated (whether traded or not)
    c.execute("""
        CREATE TABLE IF NOT EXISTS token_evaluations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluated_at    TEXT    NOT NULL,
            mint_address    TEXT    NOT NULL,
            token_name      TEXT,
            token_symbol    TEXT,
            narrative_id    INTEGER REFERENCES narratives(id),
            narrative_score REAL,
            match_score     REAL,
            rug_flags       TEXT,
            rug_passed      INTEGER,
            initial_liquidity_usd REAL,
            initial_market_cap_usd REAL,
            dev_holding_pct REAL,
            holder_count    INTEGER,
            is_bundled      INTEGER,
            decision        TEXT,
            decision_reason TEXT
        )
    """)

    # ALL tokens seen on the websocket (not just matches) — for false negative analysis
    c.execute("""
        CREATE TABLE IF NOT EXISTS all_tokens_seen (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            seen_at         TEXT    NOT NULL,
            mint_address    TEXT    NOT NULL UNIQUE,
            token_name      TEXT,
            token_symbol    TEXT,
            creator         TEXT,
            initial_market_cap_sol REAL,
            best_narrative_keyword TEXT,
            best_match_score REAL,
            passed_narrative INTEGER DEFAULT 0,
            passed_rug       INTEGER DEFAULT 0,
            entered_paper    INTEGER DEFAULT 0,
            -- Price outcomes (filled in by price tracker)
            price_at_5m      REAL,
            price_at_15m     REAL,
            price_at_30m     REAL,
            price_at_60m     REAL,
            price_at_120m    REAL,
            pct_change_5m    REAL,
            pct_change_15m   REAL,
            pct_change_30m   REAL,
            pct_change_60m   REAL,
            pct_change_120m  REAL,
            peak_pct_change  REAL,
            outcome_tracked  INTEGER DEFAULT 0
        )
    """)

    # Trades entered (paper or live)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluation_id   INTEGER REFERENCES token_evaluations(id),
            mint_address    TEXT    NOT NULL,
            token_name      TEXT,
            token_symbol    TEXT,
            entered_at      TEXT    NOT NULL,
            entry_price_usd REAL,
            entry_sol       REAL,
            tx_signature    TEXT,
            status          TEXT    DEFAULT 'open',
            exit_at         TEXT,
            exit_price_usd  REAL,
            exit_sol        REAL,
            pnl_sol         REAL,
            pnl_pct         REAL,
            hold_minutes    REAL,
            exit_reason     TEXT,
            simulation      INTEGER DEFAULT 1
        )
    """)

    # Partial exits (trailing TP system)
    c.execute("""
        CREATE TABLE IF NOT EXISTS partial_exits (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id        INTEGER REFERENCES trades(id),
            exit_at         TEXT    NOT NULL,
            exit_price_usd  REAL,
            exit_fraction   REAL,
            pnl_pct         REAL,
            pnl_sol         REAL,
            reason          TEXT
        )
    """)

    # Price snapshots for open trades and tracked tokens
    c.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            mint_address    TEXT    NOT NULL,
            snapshot_at     TEXT    NOT NULL,
            minutes_since_detection INTEGER,
            price_usd       REAL,
            market_cap_usd  REAL,
            liquidity_usd   REAL,
            volume_24h      REAL,
            price_change_5m REAL,
            price_change_1h REAL
        )
    """)

    # Self-learning log
    c.execute("""
        CREATE TABLE IF NOT EXISTS learning_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at       TEXT    NOT NULL,
            cycle_start     TEXT,
            cycle_end       TEXT,
            sample_size     INTEGER,
            win_rate        REAL,
            avg_pnl_pct     REAL,
            adjustments     TEXT,
            notes           TEXT
        )
    """)

    # Daily performance summaries
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_reports (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date         TEXT    NOT NULL UNIQUE,
            tokens_evaluated    INTEGER DEFAULT 0,
            tokens_passed_rug   INTEGER DEFAULT 0,
            trades_entered      INTEGER DEFAULT 0,
            trades_won          INTEGER DEFAULT 0,
            trades_lost         INTEGER DEFAULT 0,
            trades_timeout      INTEGER DEFAULT 0,
            total_pnl_sol       REAL    DEFAULT 0,
            best_trade_pct      REAL,
            worst_trade_pct     REAL,
            rolling_win_rate    REAL,
            false_positives     INTEGER DEFAULT 0,
            false_negatives     INTEGER DEFAULT 0,
            system_paused       INTEGER DEFAULT 0,
            notes               TEXT
        )
    """)

    # ── Safe column migrations (add columns if they don't exist) ──
    _safe_add_column(c, 'trades', 'trade_mode', 'TEXT')
    _safe_add_column(c, 'trades', 'narrative_age', 'REAL')
    _safe_add_column(c, 'trades', 'category', 'TEXT')
    _safe_add_column(c, 'trades', 'strategy_version', 'TEXT')
    _safe_add_column(c, 'trades', 'strategy_params', 'TEXT')
    _safe_add_column(c, 'trades', 'twitter_signal_data', 'TEXT')  # JSON blob from twitter_signal.py
    _safe_add_column(c, 'token_evaluations', 'social_score', 'REAL')
    _safe_add_column(c, 'token_evaluations', 'social_data', 'TEXT')

    conn.commit()
    conn.close()
    print(f"[DB] Initialized at {DB_PATH}")


# ── Write helpers ─────────────────────────────────────────────────────────────

def log_narrative(keyword, score, sources, velocity, durability):
    conn = get_conn()
    c = conn.cursor()
    # Dedup: update existing active narrative instead of inserting duplicate
    c.execute("SELECT id FROM narratives WHERE keyword = ? AND expired = 0", (keyword,))
    existing = c.fetchone()
    if existing:
        c.execute("""
            UPDATE narratives SET score = ?, sources = ?, velocity = ?, durability = ?,
                                  detected_at = ?
            WHERE id = ?
        """, (score, json.dumps(sources), velocity, durability,
              datetime.utcnow().isoformat(), existing[0]))
        conn.commit()
        row_id = existing[0]
    else:
        c.execute("""
            INSERT INTO narratives (detected_at, keyword, score, sources, velocity, durability)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.utcnow().isoformat(), keyword, score,
              json.dumps(sources), velocity, durability))
        conn.commit()
        row_id = c.lastrowid
    conn.close()
    return row_id


def log_token_seen(mint_address, token_name, token_symbol, creator,
                   initial_market_cap_sol, best_narrative_keyword,
                   best_match_score, passed_narrative, passed_rug, entered_paper):
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT OR IGNORE INTO all_tokens_seen
            (seen_at, mint_address, token_name, token_symbol, creator,
             initial_market_cap_sol, best_narrative_keyword, best_match_score,
             passed_narrative, passed_rug, entered_paper)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (datetime.utcnow().isoformat(), mint_address, token_name, token_symbol,
              creator, initial_market_cap_sol, best_narrative_keyword,
              best_match_score, 1 if passed_narrative else 0,
              1 if passed_rug else 0, 1 if entered_paper else 0))
        conn.commit()
        row_id = c.lastrowid
    except Exception as e:
        row_id = None
    conn.close()
    return row_id


def update_token_price_outcome(mint_address, interval_min, price_usd, pct_change):
    """Update price outcome columns for a tracked token."""
    col_map = {5: "price_at_5m", 15: "price_at_15m", 30: "price_at_30m",
               60: "price_at_60m", 120: "price_at_120m"}
    pct_map = {5: "pct_change_5m", 15: "pct_change_15m", 30: "pct_change_30m",
               60: "pct_change_60m", 120: "pct_change_120m"}
    price_col = col_map.get(interval_min)
    pct_col   = pct_map.get(interval_min)
    if not price_col:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"""
        UPDATE all_tokens_seen SET {price_col}=?, {pct_col}=?
        WHERE mint_address=?
    """, (price_usd, pct_change, mint_address))
    # Update peak
    c.execute("""
        UPDATE all_tokens_seen
        SET peak_pct_change = MAX(COALESCE(peak_pct_change, -999),
                                  COALESCE(pct_change_5m, -999),
                                  COALESCE(pct_change_15m, -999),
                                  COALESCE(pct_change_30m, -999),
                                  COALESCE(pct_change_60m, -999),
                                  COALESCE(pct_change_120m, -999))
        WHERE mint_address=?
    """, (mint_address,))
    conn.commit()
    conn.close()


def log_price_snapshot(mint_address, minutes_since_detection,
                        price_usd, market_cap_usd, liquidity_usd,
                        volume_24h, price_change_5m, price_change_1h):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO price_snapshots
        (mint_address, snapshot_at, minutes_since_detection,
         price_usd, market_cap_usd, liquidity_usd, volume_24h,
         price_change_5m, price_change_1h)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (mint_address, datetime.utcnow().isoformat(), minutes_since_detection,
          price_usd, market_cap_usd, liquidity_usd, volume_24h,
          price_change_5m, price_change_1h))
    conn.commit()
    conn.close()


def log_evaluation(mint_address, token_name, token_symbol, narrative_id,
                   narrative_score, match_score, rug_flags, rug_passed,
                   initial_liquidity_usd, initial_market_cap_usd,
                   dev_holding_pct, holder_count, is_bundled,
                   decision, decision_reason,
                   social_score=None, social_data=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO token_evaluations
        (evaluated_at, mint_address, token_name, token_symbol, narrative_id,
         narrative_score, match_score, rug_flags, rug_passed,
         initial_liquidity_usd, initial_market_cap_usd,
         dev_holding_pct, holder_count, is_bundled, decision, decision_reason,
         social_score, social_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (datetime.utcnow().isoformat(), mint_address, token_name, token_symbol,
          narrative_id, narrative_score, match_score, json.dumps(rug_flags),
          1 if rug_passed else 0, initial_liquidity_usd, initial_market_cap_usd,
          dev_holding_pct, holder_count, 1 if is_bundled else 0,
          decision, decision_reason,
          social_score, json.dumps(social_data) if social_data else None))
    conn.commit()
    row_id = c.lastrowid
    conn.close()
    return row_id


def log_trade(evaluation_id, mint_address, token_name, token_symbol,
              entry_price_usd, entry_sol, tx_signature, simulation=True,
              trade_mode="paper", narrative_age=None, category=None,
              strategy_version=None, strategy_params=None,
              twitter_signal_data=None):
    conn = get_conn()
    c = conn.cursor()
    twitter_json = json.dumps(twitter_signal_data) if twitter_signal_data else None
    c.execute("""
        INSERT INTO trades
        (evaluation_id, mint_address, token_name, token_symbol,
         entered_at, entry_price_usd, entry_sol, tx_signature, simulation, trade_mode,
         narrative_age, category, strategy_version, strategy_params, twitter_signal_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (evaluation_id, mint_address, token_name, token_symbol,
          datetime.utcnow().isoformat(), entry_price_usd, entry_sol, tx_signature,
          1 if simulation else 0, trade_mode, narrative_age, category,
          strategy_version, strategy_params, twitter_json))
    conn.commit()
    row_id = c.lastrowid
    conn.close()
    return row_id


def close_trade(trade_id, status, exit_price_usd, exit_sol, pnl_sol, pnl_pct,
                hold_minutes, exit_reason=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE trades SET status=?, exit_at=?, exit_price_usd=?, exit_sol=?,
        pnl_sol=?, pnl_pct=?, hold_minutes=?, exit_reason=?
        WHERE id=?
    """, (status, datetime.utcnow().isoformat(), exit_price_usd, exit_sol,
          pnl_sol, pnl_pct, hold_minutes, exit_reason, trade_id))
    conn.commit()
    conn.close()


def log_partial_exit(trade_id, exit_price_usd, exit_fraction, pnl_pct, pnl_sol, reason=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO partial_exits (trade_id, exit_at, exit_price_usd, exit_fraction, pnl_pct, pnl_sol, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (trade_id, datetime.utcnow().isoformat(), exit_price_usd, exit_fraction, pnl_pct, pnl_sol, reason))
    conn.commit()
    conn.close()

def get_open_trades():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE status='open'")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_recent_closed_trades(n=20):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM trades WHERE status != 'open'
        ORDER BY exit_at DESC LIMIT ?
    """, (n,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_tokens_needing_price_tracking():
    """Return tokens seen in the last 2 hours that need price snapshots."""
    conn = get_conn()
    c = conn.cursor()
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    c.execute("""
        SELECT * FROM all_tokens_seen
        WHERE seen_at > ? AND outcome_tracked = 0
        ORDER BY seen_at ASC
    """, (cutoff,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def mark_token_entered(mint_address):
    """Mark a token as having been entered into a paper/live trade."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE all_tokens_seen SET entered_paper=1 WHERE mint_address=?",
              (mint_address,))
    conn.commit()
    conn.close()


def mark_token_outcome_tracked(mint_address):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE all_tokens_seen SET outcome_tracked=1 WHERE mint_address=?",
              (mint_address,))
    conn.commit()
    conn.close()


def log_learning_cycle(cycle_start, cycle_end, sample_size, win_rate,
                       avg_pnl_pct, adjustments, notes=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO learning_log
        (logged_at, cycle_start, cycle_end, sample_size, win_rate, avg_pnl_pct, adjustments, notes)
        VALUES (?,?,?,?,?,?,?,?)
    """, (datetime.utcnow().isoformat(), cycle_start, cycle_end, sample_size,
          win_rate, avg_pnl_pct, json.dumps(adjustments), notes))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
