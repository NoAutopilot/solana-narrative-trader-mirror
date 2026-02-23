"""
Post-Bonding Database Layer
───────────────────────────
Separate SQLite database for the post-bonding (250k+ mcap) trading system.
Stores: graduated tokens, signal data, price snapshots, paper trades.
"""
import sqlite3
import json
import os
from datetime import datetime
from post_bonding_config import DB_PATH, DATA_DIR

os.makedirs(DATA_DIR, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # Every graduated token we discover
    c.execute("""
        CREATE TABLE IF NOT EXISTS graduated_tokens (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            discovered_at   TEXT    NOT NULL,
            mint_address    TEXT    NOT NULL UNIQUE,
            token_name      TEXT,
            token_symbol    TEXT,
            pair_address    TEXT,
            dex_id          TEXT,
            -- Snapshot at discovery
            mcap_usd        REAL,
            liquidity_usd   REAL,
            price_usd       REAL,
            price_native    REAL,
            volume_5m_usd   REAL,
            volume_1h_usd   REAL,
            volume_24h_usd  REAL,
            tx_count_5m     INTEGER,
            tx_buys_5m      INTEGER,
            tx_sells_5m     INTEGER,
            pair_age_minutes REAL,
            -- Holder data (from Helius, if available)
            holder_count    INTEGER,
            top10_concentration REAL,
            creator_address TEXT,
            -- Outcome tracking
            peak_mcap_usd   REAL,
            peak_price_usd  REAL,
            time_to_peak_min REAL,
            mcap_at_5m      REAL,
            mcap_at_15m     REAL,
            mcap_at_30m     REAL,
            -- Signals
            volume_acceleration REAL,
            buy_sell_ratio   REAL,
            creator_dumped   INTEGER DEFAULT 0,
            dump_detected_at TEXT,
            -- Metadata
            tracking_complete INTEGER DEFAULT 0,
            notes           TEXT
        )
    """)

    # Price snapshots for each token (time series)
    c.execute("""
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            mint_address    TEXT    NOT NULL,
            snapshot_at     TEXT    NOT NULL,
            price_usd       REAL,
            price_native    REAL,
            mcap_usd        REAL,
            volume_5m_usd   REAL,
            liquidity_usd   REAL,
            tx_buys_5m      INTEGER,
            tx_sells_5m     INTEGER
        )
    """)

    # Paper trades with strategy variant
    c.execute("""
        CREATE TABLE IF NOT EXISTS post_bonding_trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            mint_address    TEXT    NOT NULL,
            token_name      TEXT,
            token_symbol    TEXT,
            strategy        TEXT    NOT NULL,
            -- Entry
            entered_at      TEXT    NOT NULL,
            entry_price_usd REAL,
            entry_price_native REAL,
            entry_mcap_usd  REAL,
            entry_sol       REAL    NOT NULL,
            -- Exit
            status          TEXT    NOT NULL DEFAULT 'open',
            exit_at         TEXT,
            exit_price_usd  REAL,
            exit_price_native REAL,
            exit_mcap_usd   REAL,
            -- PnL
            pnl_sol         REAL,
            pnl_pct         REAL,
            hold_minutes    REAL,
            exit_reason     TEXT,
            -- Signal data at entry
            volume_5m_at_entry REAL,
            holder_count_at_entry INTEGER,
            buy_sell_ratio_at_entry REAL,
            -- Strategy params (for reproducibility)
            strategy_params TEXT,
            -- Peak tracking for trailing TP
            peak_price      REAL,
            peak_pnl_pct    REAL
        )
    """)

    # Create indexes for performance
    c.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_mint ON price_snapshots(mint_address)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_time ON price_snapshots(snapshot_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON post_bonding_trades(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON post_bonding_trades(strategy)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_graduated_mint ON graduated_tokens(mint_address)")

    conn.commit()
    conn.close()


def insert_graduated_token(data):
    """Insert a newly discovered graduated token."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO graduated_tokens 
            (discovered_at, mint_address, token_name, token_symbol, pair_address, dex_id,
             mcap_usd, liquidity_usd, price_usd, price_native,
             volume_5m_usd, volume_1h_usd, volume_24h_usd,
             tx_count_5m, tx_buys_5m, tx_sells_5m, pair_age_minutes,
             volume_acceleration, buy_sell_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("discovered_at", datetime.utcnow().isoformat()),
            data["mint_address"],
            data.get("token_name"),
            data.get("token_symbol"),
            data.get("pair_address"),
            data.get("dex_id"),
            data.get("mcap_usd"),
            data.get("liquidity_usd"),
            data.get("price_usd"),
            data.get("price_native"),
            data.get("volume_5m_usd"),
            data.get("volume_1h_usd"),
            data.get("volume_24h_usd"),
            data.get("tx_count_5m"),
            data.get("tx_buys_5m"),
            data.get("tx_sells_5m"),
            data.get("pair_age_minutes"),
            data.get("volume_acceleration"),
            data.get("buy_sell_ratio"),
        ))
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()


def insert_price_snapshot(mint_address, data):
    """Insert a price snapshot for a token."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO price_snapshots
            (mint_address, snapshot_at, price_usd, price_native, mcap_usd,
             volume_5m_usd, liquidity_usd, tx_buys_5m, tx_sells_5m)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mint_address,
            data.get("snapshot_at", datetime.utcnow().isoformat()),
            data.get("price_usd"),
            data.get("price_native"),
            data.get("mcap_usd"),
            data.get("volume_5m_usd"),
            data.get("liquidity_usd"),
            data.get("tx_buys_5m"),
            data.get("tx_sells_5m"),
        ))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def open_trade(data):
    """Open a new paper trade."""
    conn = get_conn()
    try:
        c = conn.execute("""
            INSERT INTO post_bonding_trades
            (mint_address, token_name, token_symbol, strategy,
             entered_at, entry_price_usd, entry_price_native, entry_mcap_usd, entry_sol,
             status, volume_5m_at_entry, holder_count_at_entry, buy_sell_ratio_at_entry,
             strategy_params, peak_price, peak_pnl_pct)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, 0)
        """, (
            data["mint_address"],
            data.get("token_name"),
            data.get("token_symbol"),
            data["strategy"],
            data.get("entered_at", datetime.utcnow().isoformat()),
            data.get("entry_price_usd"),
            data.get("entry_price_native"),
            data.get("entry_mcap_usd"),
            data["entry_sol"],
            data.get("volume_5m_at_entry"),
            data.get("holder_count_at_entry"),
            data.get("buy_sell_ratio_at_entry"),
            json.dumps(data.get("strategy_params", {})),
            data.get("entry_price_native", 0),
        ))
        conn.commit()
        return c.lastrowid
    except Exception as e:
        return None
    finally:
        conn.close()


def close_trade(trade_id, exit_data):
    """Close an open paper trade."""
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE post_bonding_trades SET
                status = 'closed',
                exit_at = ?,
                exit_price_usd = ?,
                exit_price_native = ?,
                exit_mcap_usd = ?,
                pnl_sol = ?,
                pnl_pct = ?,
                hold_minutes = ?,
                exit_reason = ?,
                peak_price = ?,
                peak_pnl_pct = ?
            WHERE id = ?
        """, (
            exit_data.get("exit_at", datetime.utcnow().isoformat()),
            exit_data.get("exit_price_usd"),
            exit_data.get("exit_price_native"),
            exit_data.get("exit_mcap_usd"),
            exit_data.get("pnl_sol"),
            exit_data.get("pnl_pct"),
            exit_data.get("hold_minutes"),
            exit_data.get("exit_reason"),
            exit_data.get("peak_price"),
            exit_data.get("peak_pnl_pct"),
            trade_id,
        ))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def update_peak(trade_id, peak_price, peak_pnl_pct):
    """Update peak price tracking for trailing TP."""
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE post_bonding_trades SET peak_price = ?, peak_pnl_pct = ?
            WHERE id = ?
        """, (peak_price, peak_pnl_pct, trade_id))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def get_open_trades(strategy=None):
    """Get all open trades, optionally filtered by strategy."""
    conn = get_conn()
    try:
        if strategy:
            rows = conn.execute(
                "SELECT * FROM post_bonding_trades WHERE status='open' AND strategy=?",
                (strategy,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM post_bonding_trades WHERE status='open'"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_seen_mints():
    """Get set of all mint addresses we've already discovered."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT mint_address FROM graduated_tokens").fetchall()
        return {r["mint_address"] for r in rows}
    finally:
        conn.close()


def get_stats():
    """Get summary statistics."""
    conn = get_conn()
    try:
        total_tokens = conn.execute("SELECT COUNT(*) FROM graduated_tokens").fetchone()[0]
        total_trades = conn.execute("SELECT COUNT(*) FROM post_bonding_trades").fetchone()[0]
        open_trades = conn.execute("SELECT COUNT(*) FROM post_bonding_trades WHERE status='open'").fetchone()[0]
        closed_trades = conn.execute("SELECT COUNT(*) FROM post_bonding_trades WHERE status='closed'").fetchone()[0]

        pnl_by_strategy = {}
        rows = conn.execute("""
            SELECT strategy, COUNT(*) as cnt, SUM(pnl_sol) as total_pnl,
                   SUM(CASE WHEN pnl_sol > 0 THEN 1 ELSE 0 END) as wins
            FROM post_bonding_trades WHERE status='closed'
            GROUP BY strategy
        """).fetchall()
        for r in rows:
            pnl_by_strategy[r["strategy"]] = {
                "trades": r["cnt"],
                "pnl": r["total_pnl"] or 0,
                "wins": r["wins"],
                "win_rate": r["wins"] / r["cnt"] * 100 if r["cnt"] > 0 else 0,
            }

        return {
            "total_tokens": total_tokens,
            "total_trades": total_trades,
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "pnl_by_strategy": pnl_by_strategy,
        }
    finally:
        conn.close()


def update_graduated_token(mint_address, updates):
    """Update fields on a graduated token record."""
    conn = get_conn()
    try:
        set_clauses = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [mint_address]
        conn.execute(
            f"UPDATE graduated_tokens SET {set_clauses} WHERE mint_address = ?",
            values
        )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
