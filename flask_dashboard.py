"""
Flask Dashboard — Live Monitoring UI
─────────────────────────────────────
Serves a web dashboard showing trade stats, recent trades,
active narratives, virtual strategy comparison, and system health.

Usage: python3 flask_dashboard.py
"""

import os
import sys
import json
import sqlite3
from datetime import datetime

from flask import Flask, render_template_string, jsonify

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.config import DASHBOARD_PORT, DASHBOARD_HOST, DATA_DIR


# Emergency kill switch
try:
    from live_executor import emergency_kill_switch, is_emergency_halted, get_live_stats
except ImportError:
    emergency_kill_switch = None
    is_emergency_halted = lambda: False
    get_live_stats = lambda: {}

app = Flask(__name__)
DB_PATH = os.path.join(DATA_DIR, "solana_trader.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def safe_query(query, params=()):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute(query, params)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Solana Narrative Trader</title>
    <meta http-equiv="refresh" content="30">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'JetBrains Mono', 'Consolas', monospace;
            background: #0a0a0f; color: #e0e0e0; padding: 20px;
        }
        h1 { color: #00ff88; margin-bottom: 10px; font-size: 1.4em; }
        h2 { color: #88aaff; margin: 20px 0 10px; font-size: 1.1em; }
        .stats-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px; margin-bottom: 20px;
        }
        .stat-card {
            background: #12121a; border: 1px solid #222;
            border-radius: 8px; padding: 15px; text-align: center;
        }
        .stat-card .label { color: #888; font-size: 0.75em; text-transform: uppercase; }
        .stat-card .value { font-size: 1.5em; font-weight: bold; margin-top: 5px; }
        .positive { color: #00ff88; }
        .negative { color: #ff4444; }
        .neutral { color: #ffaa00; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.8em; }
        th { background: #1a1a2e; color: #88aaff; padding: 8px; text-align: left; border-bottom: 2px solid #333; }
        td { padding: 6px 8px; border-bottom: 1px solid #1a1a1a; }
        tr:hover { background: #15152a; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; font-weight: bold; }
        .badge-narrative { background: #1a3a1a; color: #00ff88; }
        .badge-proactive { background: #1a2a3a; color: #44aaff; }
        .badge-control { background: #2a2a1a; color: #ffaa00; }
        .timestamp { color: #666; font-size: 0.7em; }
        .footer { color: #444; font-size: 0.7em; margin-top: 30px; text-align: center; }
    </style>
</head>
<body>
    <h1>Solana Narrative Trader — Paper Trading Dashboard</h1>
    <p class="timestamp">Auto-refreshes every 30s | {{ now }}</p>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="label">Total Trades</div>
            <div class="value">{{ total_trades }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Open Trades</div>
            <div class="value neutral">{{ open_trades }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Win Rate</div>
            <div class="value {% if win_rate > 15 %}positive{% elif win_rate > 10 %}neutral{% else %}negative{% endif %}">
                {{ "%.1f"|format(win_rate) }}%
            </div>
        </div>
        <div class="stat-card">
            <div class="label">Total PnL (SOL)</div>
            <div class="value {% if total_pnl > 0 %}positive{% else %}negative{% endif %}">
                {{ "%+.4f"|format(total_pnl) }}
            </div>
        </div>
        <div class="stat-card">
            <div class="label">Narrative Trades</div>
            <div class="value">{{ narrative_trades }}</div>
        </div>
        <div class="stat-card">
            <div class="label">Control Trades</div>
            <div class="value">{{ control_trades }}</div>
        </div>
    </div>

    <h2>Recent Trades (Last 30)</h2>
    <table>
        <tr>
            <th>Time</th><th>Token</th><th>Mode</th><th>Category</th>
            <th>PnL (SOL)</th><th>PnL %</th><th>Exit</th><th>Hold</th><th>Twitter</th>
        </tr>
        {% for t in recent_trades %}
        <tr>
            <td class="timestamp">{{ t.entered_at[:16] if t.entered_at else '?' }}</td>
            <td>{{ t.token_name[:20] }} ({{ t.token_symbol }})</td>
            <td><span class="badge badge-{{ t.trade_mode or 'control' }}">{{ (t.trade_mode or '?').upper() }}</span></td>
            <td>{{ t.category or '?' }}</td>
            <td class="{% if (t.pnl_sol or 0) > 0 %}positive{% elif (t.pnl_sol or 0) < 0 %}negative{% else %}neutral{% endif %}">
                {{ "%+.4f"|format(t.pnl_sol or 0) }}
            </td>
            <td>{{ "%.1f"|format((t.pnl_pct or 0) * 100) }}%</td>
            <td>{{ t.exit_reason or 'OPEN' }}</td>
            <td>{{ "%.1f"|format(t.hold_minutes or 0) }}m</td>
            <td>{{ t.tw_tweets or '-' }}</td>
        </tr>
        {% endfor %}
    </table>

    <h2>Virtual Strategy Comparison</h2>
    <table>
        <tr><th>Strategy</th><th>Exits</th><th>Win Rate</th><th>Avg PnL</th><th>Total PnL</th></tr>
        {% for s in strategies %}
        <tr>
            <td>{{ s.strategy_name }}</td>
            <td>{{ s.count }}</td>
            <td class="{% if s.win_rate > 20 %}positive{% elif s.win_rate > 10 %}neutral{% else %}negative{% endif %}">
                {{ "%.1f"|format(s.win_rate) }}%</td>
            <td class="{% if s.avg_pnl > 0 %}positive{% else %}negative{% endif %}">{{ "%+.4f"|format(s.avg_pnl) }}</td>
            <td class="{% if s.total_pnl > 0 %}positive{% else %}negative{% endif %}">{{ "%+.4f"|format(s.total_pnl) }}</td>
        </tr>
        {% endfor %}
    </table>

    <h2>Active Narratives (Top 20)</h2>
    <table>
        <tr><th>Keyword</th><th>Score</th><th>Category</th><th>Velocity</th><th>Detected</th></tr>
        {% for n in narratives %}
        <tr>
            <td>{{ n.keyword }}</td>
            <td>{{ "%.1f"|format(n.score or 0) }}</td>
            <td>{{ n.category or 'default' }}</td>
            <td>{{ "%.1f"|format(n.velocity or 0) }}</td>
            <td class="timestamp">{{ (n.detected_at or '')[:16] }}</td>
        </tr>
        {% endfor %}
    </table>

    <div class="footer">Paper Trader v4 | NOT REAL MONEY</div>
</body>
</html>
"""


@app.route("/")
def dashboard():
    closed = safe_query("""
        SELECT COUNT(*) as cnt,
               SUM(CASE WHEN pnl_sol > 0 THEN 1 ELSE 0 END) as wins,
               SUM(pnl_sol) as total_pnl
        FROM trades WHERE exit_reason IS NOT NULL
    """)
    open_count = safe_query("SELECT COUNT(*) as cnt FROM trades WHERE exit_reason IS NULL")

    total_trades = closed[0]["cnt"] if closed else 0
    wins = closed[0]["wins"] if closed else 0
    total_pnl = closed[0]["total_pnl"] or 0 if closed else 0
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    open_t = open_count[0]["cnt"] if open_count else 0

    narr = safe_query("SELECT COUNT(*) as cnt FROM trades WHERE trade_mode IN ('narrative', 'proactive')")
    ctrl = safe_query("SELECT COUNT(*) as cnt FROM trades WHERE trade_mode = 'control'")
    narrative_trades = narr[0]["cnt"] if narr else 0
    control_trades = ctrl[0]["cnt"] if ctrl else 0

    recent = safe_query("""
        SELECT token_name, token_symbol, trade_mode, category,
               pnl_sol, pnl_pct, exit_reason, hold_minutes, entered_at,
               twitter_signal_data
        FROM trades ORDER BY id DESC LIMIT 30
    """)
    for t in recent:
        tw_data = t.get("twitter_signal_data")
        if tw_data:
            try:
                tw = json.loads(tw_data)
                t["tw_tweets"] = tw.get("tweet_count", 0)
            except Exception:
                t["tw_tweets"] = "-"
        else:
            t["tw_tweets"] = "-"

    strategies = safe_query("""
        SELECT strategy_name, COUNT(*) as count,
               SUM(CASE WHEN pnl_sol > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
               AVG(pnl_sol) as avg_pnl, SUM(pnl_sol) as total_pnl
        FROM virtual_exits GROUP BY strategy_name ORDER BY total_pnl DESC
    """)

    narratives = safe_query("""
        SELECT keyword, score, category, velocity, detected_at
        FROM narratives WHERE expired = 0 ORDER BY score DESC LIMIT 20
    """)

    return render_template_string(
        DASHBOARD_HTML,
        now=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        total_trades=total_trades, open_trades=open_t,
        win_rate=win_rate, total_pnl=total_pnl,
        narrative_trades=narrative_trades, control_trades=control_trades,
        recent_trades=recent, strategies=strategies, narratives=narratives,
    )



@app.route("/api/emergency-kill", methods=["POST"])
def api_emergency_kill():
    """Emergency kill switch: halt all buys and dump all open positions."""
    if emergency_kill_switch is None:
        return {"error": "Kill switch not available"}, 500
    try:
        result = emergency_kill_switch()
        return result
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/api/live-status")
def api_live_status():
    """Get current live trading status."""
    try:
        stats = get_live_stats()
        stats["emergency_halted"] = is_emergency_halted()
        return stats
    except Exception as e:
        return {"error": str(e)}, 500

@app.route("/api/stats")
def api_stats():
    closed = safe_query("""
        SELECT COUNT(*) as cnt,
               SUM(CASE WHEN pnl_sol > 0 THEN 1 ELSE 0 END) as wins,
               SUM(pnl_sol) as total_pnl
        FROM trades WHERE exit_reason IS NOT NULL
    """)
    return jsonify({
        "total_trades": closed[0]["cnt"] if closed else 0,
        "wins": closed[0]["wins"] if closed else 0,
        "total_pnl": closed[0]["total_pnl"] or 0 if closed else 0,
        "timestamp": datetime.utcnow().isoformat(),
    })


if __name__ == "__main__":
    app.run(host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False)
