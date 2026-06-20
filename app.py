"""
Nickets Data Collection API v1.0
Centralized database for queue positions, purchases, and distribution tracking.
Receives data from Queue Dashboard + browser extensions, stores in SQLite.
Serves a web dashboard for viewing history and analytics.
"""

import os
import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, request, jsonify, g, Response

app = Flask(__name__)
API_KEY = os.environ.get("NICKETS_DATA_KEY", "nk$d4t4#2026!")
DB_PATH = os.environ.get("NICKETS_DB_PATH", "/opt/nickets-data/nickets_data.db")

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout=5000")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS queue_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            profile_name TEXT DEFAULT '',
            va_name TEXT DEFAULT '',
            event_name TEXT DEFAULT '',
            event_url TEXT DEFAULT '',
            queue_position INTEGER NOT NULL,
            status TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'dashboard',
            session_id TEXT DEFAULT '',
            extra TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS queue_sessions (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            profile_name TEXT DEFAULT '',
            va_name TEXT DEFAULT '',
            event_name TEXT DEFAULT '',
            event_url TEXT DEFAULT '',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            final_position INTEGER,
            outcome TEXT DEFAULT 'unknown',
            peak_position INTEGER,
            lowest_position INTEGER,
            duration_seconds INTEGER DEFAULT 0,
            extra TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            profile_name TEXT DEFAULT '',
            va_name TEXT DEFAULT '',
            event_name TEXT DEFAULT '',
            event_url TEXT DEFAULT '',
            event_date TEXT DEFAULT '',
            venue TEXT DEFAULT '',
            quantity INTEGER DEFAULT 0,
            total_amount REAL DEFAULT 0,
            section TEXT DEFAULT '',
            row_info TEXT DEFAULT '',
            seat_info TEXT DEFAULT '',
            order_id TEXT DEFAULT '',
            email TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            source TEXT DEFAULT 'extension',
            extra TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS distribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_id INTEGER,
            profile_id TEXT NOT NULL,
            va_name TEXT DEFAULT '',
            event_name TEXT DEFAULT '',
            ticket_count INTEGER DEFAULT 0,
            assigned_to TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY (purchase_id) REFERENCES purchases(id)
        );

        CREATE INDEX IF NOT EXISTS idx_queue_profile ON queue_events(profile_id);
        CREATE INDEX IF NOT EXISTS idx_queue_session ON queue_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_queue_time ON queue_events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_purchase_profile ON purchases(profile_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_time ON purchases(timestamp);
        CREATE INDEX IF NOT EXISTS idx_purchase_event ON purchases(event_name);
        CREATE INDEX IF NOT EXISTS idx_session_profile ON queue_sessions(profile_id);
    """)
    db.commit()
    db.close()


init_db()


def require_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key", "") or request.args.get("key", "")
        if key != API_KEY:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


def cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return resp


app.after_request(cors_headers)


@app.route("/", methods=["GET"])
def index():
    return serve_dashboard()


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({"status": "ok", "app": "NicketsData", "version": "1.0"})


# ─── Queue Events ──────────────────────────────────────────────────────────


@app.route("/api/queue/log", methods=["POST", "OPTIONS"])
def log_queue():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    profile_id = data.get("profile_id", "").strip()
    queue_pos = data.get("queue_position")
    if not profile_id or queue_pos is None:
        return jsonify({"error": "profile_id and queue_position required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.execute("""
        INSERT INTO queue_events (profile_id, profile_name, va_name, event_name,
            event_url, queue_position, status, timestamp, source, session_id, extra)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        profile_id,
        data.get("profile_name", ""),
        data.get("va_name", ""),
        data.get("event_name", ""),
        data.get("event_url", ""),
        int(queue_pos),
        data.get("status", ""),
        now,
        data.get("source", "dashboard"),
        data.get("session_id", ""),
        json.dumps(data.get("extra", {})),
    ))
    db.commit()
    return jsonify({"ok": True, "timestamp": now})


@app.route("/api/queue/bulk", methods=["POST", "OPTIONS"])
def log_queue_bulk():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    events = data.get("events", [])
    if not events:
        return jsonify({"error": "events array required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    count = 0
    for ev in events:
        profile_id = ev.get("profile_id", "").strip()
        queue_pos = ev.get("queue_position")
        if not profile_id or queue_pos is None:
            continue
        db.execute("""
            INSERT INTO queue_events (profile_id, profile_name, va_name, event_name,
                event_url, queue_position, status, timestamp, source, session_id, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_id,
            ev.get("profile_name", ""),
            ev.get("va_name", ""),
            ev.get("event_name", ""),
            ev.get("event_url", ""),
            int(queue_pos),
            ev.get("status", ""),
            now,
            ev.get("source", "dashboard"),
            ev.get("session_id", ""),
            json.dumps(ev.get("extra", {})),
        ))
        count += 1
    db.commit()
    return jsonify({"ok": True, "logged": count, "timestamp": now})


@app.route("/api/queue/session/start", methods=["POST", "OPTIONS"])
def start_queue_session():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    profile_id = data.get("profile_id", "").strip()
    if not profile_id:
        return jsonify({"error": "profile_id required"}), 400

    import uuid
    session_id = str(uuid.uuid4())[:12]
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.execute("""
        INSERT INTO queue_sessions (id, profile_id, profile_name, va_name,
            event_name, event_url, started_at, extra)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id,
        profile_id,
        data.get("profile_name", ""),
        data.get("va_name", ""),
        data.get("event_name", ""),
        data.get("event_url", ""),
        now,
        json.dumps(data.get("extra", {})),
    ))
    db.commit()
    return jsonify({"ok": True, "session_id": session_id, "started_at": now})


@app.route("/api/queue/session/end", methods=["POST", "OPTIONS"])
def end_queue_session():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id", "").strip()
    if not session_id:
        return jsonify({"error": "session_id required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    db = get_db()

    session_row = db.execute("SELECT * FROM queue_sessions WHERE id = ?", (session_id,)).fetchone()
    if not session_row:
        return jsonify({"error": "session not found"}), 404

    stats = db.execute("""
        SELECT MIN(queue_position) as lowest, MAX(queue_position) as peak,
               COUNT(*) as readings
        FROM queue_events WHERE session_id = ?
    """, (session_id,)).fetchone()

    started = datetime.fromisoformat(session_row["started_at"])
    ended = datetime.fromisoformat(now)
    duration = int((ended - started).total_seconds())

    outcome = data.get("outcome", "unknown")
    final_pos = data.get("final_position", stats["lowest"] if stats else 0)

    db.execute("""
        UPDATE queue_sessions SET ended_at = ?, final_position = ?, outcome = ?,
            peak_position = ?, lowest_position = ?, duration_seconds = ?
        WHERE id = ?
    """, (now, final_pos, outcome, stats["peak"], stats["lowest"], duration, session_id))
    db.commit()
    return jsonify({"ok": True, "duration_seconds": duration, "outcome": outcome})


@app.route("/api/queue/history", methods=["GET"])
def queue_history():
    db = get_db()
    profile_id = request.args.get("profile_id", "")
    event_name = request.args.get("event", "")
    hours = int(request.args.get("hours", 24))
    limit = min(int(request.args.get("limit", 1000)), 10000)

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = "SELECT * FROM queue_events WHERE timestamp > ?"
    params = [cutoff]

    if profile_id:
        query += " AND profile_id = ?"
        params.append(profile_id)
    if event_name:
        query += " AND event_name LIKE ?"
        params.append(f"%{event_name}%")

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    return jsonify({"events": [dict(r) for r in rows], "count": len(rows)})


@app.route("/api/queue/sessions", methods=["GET"])
def list_queue_sessions():
    db = get_db()
    hours = int(request.args.get("hours", 48))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = db.execute(
        "SELECT * FROM queue_sessions WHERE started_at > ? ORDER BY started_at DESC",
        (cutoff,)
    ).fetchall()
    return jsonify({"sessions": [dict(r) for r in rows], "count": len(rows)})


@app.route("/api/queue/live", methods=["GET"])
def queue_live():
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    rows = db.execute("""
        SELECT profile_id, profile_name, va_name, event_name,
               queue_position, status, MAX(timestamp) as last_seen
        FROM queue_events
        WHERE timestamp > ?
        GROUP BY profile_id
        ORDER BY queue_position ASC
    """, (cutoff,)).fetchall()
    return jsonify({"profiles": [dict(r) for r in rows], "count": len(rows)})


# ─── Purchase Records ──────────────────────────────────────────────────────


@app.route("/api/purchase/log", methods=["POST", "OPTIONS"])
def log_purchase():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    profile_id = data.get("profile_id", "").strip()
    event_name = data.get("event_name", "").strip()
    if not profile_id or not event_name:
        return jsonify({"error": "profile_id and event_name required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    cursor = db.execute("""
        INSERT INTO purchases (profile_id, profile_name, va_name, event_name,
            event_url, event_date, venue, quantity, total_amount, section,
            row_info, seat_info, order_id, email, timestamp, source, extra)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        profile_id,
        data.get("profile_name", ""),
        data.get("va_name", ""),
        event_name,
        data.get("event_url", ""),
        data.get("event_date", ""),
        data.get("venue", ""),
        int(data.get("quantity", 0)),
        float(data.get("total_amount", 0)),
        data.get("section", ""),
        data.get("row_info", ""),
        data.get("seat_info", ""),
        data.get("order_id", ""),
        data.get("email", ""),
        now,
        data.get("source", "extension"),
        json.dumps(data.get("extra", {})),
    ))
    db.commit()
    return jsonify({"ok": True, "purchase_id": cursor.lastrowid, "timestamp": now})


@app.route("/api/purchases", methods=["GET"])
def list_purchases():
    db = get_db()
    days = int(request.args.get("days", 30))
    limit = min(int(request.args.get("limit", 500)), 5000)
    profile_id = request.args.get("profile_id", "")
    event_name = request.args.get("event", "")

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query = "SELECT * FROM purchases WHERE timestamp > ?"
    params = [cutoff]

    if profile_id:
        query += " AND profile_id = ?"
        params.append(profile_id)
    if event_name:
        query += " AND event_name LIKE ?"
        params.append(f"%{event_name}%")

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    return jsonify({"purchases": [dict(r) for r in rows], "count": len(rows)})


@app.route("/api/purchases/stats", methods=["GET"])
def purchase_stats():
    db = get_db()
    days = int(request.args.get("days", 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    total = db.execute(
        "SELECT COUNT(*) as c, SUM(quantity) as qty, SUM(total_amount) as amt FROM purchases WHERE timestamp > ?",
        (cutoff,)
    ).fetchone()

    by_event = db.execute("""
        SELECT event_name, COUNT(*) as purchases, SUM(quantity) as tickets,
               SUM(total_amount) as revenue
        FROM purchases WHERE timestamp > ?
        GROUP BY event_name ORDER BY purchases DESC LIMIT 20
    """, (cutoff,)).fetchall()

    by_va = db.execute("""
        SELECT va_name, COUNT(*) as purchases, SUM(quantity) as tickets,
               SUM(total_amount) as revenue
        FROM purchases WHERE timestamp > ?
        GROUP BY va_name ORDER BY purchases DESC LIMIT 20
    """, (cutoff,)).fetchall()

    return jsonify({
        "total_purchases": total["c"] or 0,
        "total_tickets": total["qty"] or 0,
        "total_revenue": total["amt"] or 0,
        "by_event": [dict(r) for r in by_event],
        "by_va": [dict(r) for r in by_va],
    })


# ─── Distribution ──────────────────────────────────────────────────────────


@app.route("/api/distribution", methods=["POST", "OPTIONS"])
def create_distribution():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    cursor = db.execute("""
        INSERT INTO distribution (purchase_id, profile_id, va_name, event_name,
            ticket_count, assigned_to, status, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("purchase_id"),
        data.get("profile_id", ""),
        data.get("va_name", ""),
        data.get("event_name", ""),
        int(data.get("ticket_count", 0)),
        data.get("assigned_to", ""),
        data.get("status", "pending"),
        data.get("notes", ""),
        now,
    ))
    db.commit()
    return jsonify({"ok": True, "id": cursor.lastrowid})


@app.route("/api/distribution", methods=["GET"])
def list_distribution():
    db = get_db()
    status_filter = request.args.get("status", "")
    query = "SELECT * FROM distribution ORDER BY created_at DESC LIMIT 200"
    params = []
    if status_filter:
        query = "SELECT * FROM distribution WHERE status = ? ORDER BY created_at DESC LIMIT 200"
        params = [status_filter]
    rows = db.execute(query, params).fetchall()
    return jsonify({"items": [dict(r) for r in rows], "count": len(rows)})


@app.route("/api/distribution/<int:did>", methods=["PUT", "OPTIONS"])
def update_distribution(did):
    if request.method == "OPTIONS":
        return jsonify({"ok": True})
    data = request.get_json(silent=True) or {}
    now = datetime.now(timezone.utc).isoformat()
    db = get_db()
    updates = []
    params = []
    for field in ("assigned_to", "status", "notes", "ticket_count"):
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    if not updates:
        return jsonify({"error": "nothing to update"}), 400
    updates.append("updated_at = ?")
    params.append(now)
    params.append(did)
    db.execute(f"UPDATE distribution SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()
    return jsonify({"ok": True})


# ─── Analytics ──────────────────────────────────────────────────────────────


@app.route("/api/analytics/overview", methods=["GET"])
def analytics_overview():
    db = get_db()
    hours = int(request.args.get("hours", 24))
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    queue_count = db.execute(
        "SELECT COUNT(*) as c FROM queue_events WHERE timestamp > ?", (cutoff,)
    ).fetchone()["c"]

    active_profiles = db.execute(
        "SELECT COUNT(DISTINCT profile_id) as c FROM queue_events WHERE timestamp > ?", (cutoff,)
    ).fetchone()["c"]

    purchase_count = db.execute(
        "SELECT COUNT(*) as c FROM purchases WHERE timestamp > ?", (cutoff,)
    ).fetchone()["c"]

    active_sessions = db.execute(
        "SELECT COUNT(*) as c FROM queue_sessions WHERE started_at > ? AND ended_at IS NULL", (cutoff,)
    ).fetchone()["c"]

    completed_sessions = db.execute(
        "SELECT COUNT(*) as c FROM queue_sessions WHERE started_at > ? AND ended_at IS NOT NULL", (cutoff,)
    ).fetchone()["c"]

    success_sessions = db.execute(
        "SELECT COUNT(*) as c FROM queue_sessions WHERE started_at > ? AND outcome = 'purchased'", (cutoff,)
    ).fetchone()["c"]

    avg_duration = db.execute(
        "SELECT AVG(duration_seconds) as avg FROM queue_sessions WHERE started_at > ? AND ended_at IS NOT NULL",
        (cutoff,)
    ).fetchone()["avg"]

    return jsonify({
        "queue_readings": queue_count,
        "active_profiles": active_profiles,
        "purchases": purchase_count,
        "active_sessions": active_sessions,
        "completed_sessions": completed_sessions,
        "success_sessions": success_sessions,
        "success_rate": round(success_sessions / completed_sessions * 100, 1) if completed_sessions > 0 else 0,
        "avg_queue_duration_minutes": round((avg_duration or 0) / 60, 1),
    })


# ─── Dashboard HTML ────────────────────────────────────────────────────────


def serve_dashboard():
    return Response(DASHBOARD_HTML, content_type="text/html")


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Nickets Data Center</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#e1e4e8;min-height:100vh}
.header{background:#161b22;border-bottom:1px solid #30363d;padding:12px 24px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:18px;font-weight:700;color:#d29922}.header h1 span{color:#58a6ff}
.header .ver{font-size:11px;color:#8b949e;margin-left:8px}
.tabs{display:flex;gap:2px;background:#161b22;padding:0 24px;border-bottom:1px solid #30363d}
.tab{padding:10px 16px;font-size:13px;color:#8b949e;cursor:pointer;border-bottom:2px solid transparent;transition:.2s}
.tab:hover{color:#e1e4e8}.tab.active{color:#58a6ff;border-bottom-color:#58a6ff}
.content{padding:20px 24px;max-width:1400px;margin:0 auto}
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.stat-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.stat-card .label{font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px}
.stat-card .value{font-size:28px;font-weight:700;color:#58a6ff;margin-top:4px}
.stat-card .value.green{color:#3fb950}.stat-card .value.gold{color:#d29922}.stat-card .value.red{color:#f85149}
.table-wrap{background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden;margin-bottom:20px}
.table-title{padding:12px 16px;font-size:14px;font-weight:600;border-bottom:1px solid #30363d;display:flex;align-items:center;justify-content:space-between}
.table-title .badge{background:#30363d;color:#8b949e;font-size:11px;padding:2px 8px;border-radius:10px}
table{width:100%;border-collapse:collapse}
th{text-align:left;padding:8px 12px;font-size:11px;color:#8b949e;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #30363d;background:#0d1117}
td{padding:8px 12px;font-size:13px;border-bottom:1px solid #21262d}
tr:hover{background:#1c2128}
.badge-status{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
.badge-status.active{background:#0d4429;color:#3fb950}
.badge-status.ended{background:#3d1d00;color:#d29922}
.badge-status.purchased{background:#0d4429;color:#3fb950}
.badge-status.dropped{background:#490202;color:#f85149}
.queue-num{font-weight:700;font-size:15px;font-family:'Consolas',monospace}
.queue-num.low{color:#3fb950}.queue-num.mid{color:#d29922}.queue-num.high{color:#f85149}
.empty{text-align:center;padding:40px;color:#484f58;font-size:14px}
.refresh-btn{background:#238636;color:#fff;border:none;padding:6px 14px;border-radius:6px;font-size:12px;cursor:pointer;font-weight:600}
.refresh-btn:hover{background:#2ea043}
.filter-bar{display:flex;gap:8px;margin-bottom:16px;align-items:center;flex-wrap:wrap}
.filter-bar input,.filter-bar select{background:#0d1117;border:1px solid #30363d;color:#e1e4e8;padding:6px 10px;border-radius:6px;font-size:12px}
.filter-bar input:focus,.filter-bar select:focus{outline:none;border-color:#58a6ff}
.filter-bar label{font-size:12px;color:#8b949e}
#live-indicator{width:8px;height:8px;border-radius:50%;background:#3fb950;display:inline-block;margin-right:6px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.section{display:none}.section.active{display:block}
</style>
</head>
<body>
<div class="header">
    <h1><span>Nickets</span> Data Center <span class="ver">v1.0</span></h1>
    <button class="refresh-btn" onclick="refreshAll()">Refresh</button>
</div>
<div class="tabs">
    <div class="tab active" onclick="switchTab('overview')">Overview</div>
    <div class="tab" onclick="switchTab('queue')">Queue History</div>
    <div class="tab" onclick="switchTab('purchases')">Purchases</div>
    <div class="tab" onclick="switchTab('sessions')">Sessions</div>
</div>
<div class="content">

<!-- OVERVIEW -->
<div id="sec-overview" class="section active">
    <div class="stats-row" id="overview-stats"></div>
    <div class="table-wrap">
        <div class="table-title"><span><span id="live-indicator"></span>Live Queue Positions</span><span class="badge" id="live-count">0</span></div>
        <table><thead><tr><th>Profile</th><th>VA</th><th>Event</th><th>Queue #</th><th>Status</th><th>Last Seen</th></tr></thead>
        <tbody id="live-table"></tbody></table>
    </div>
    <div class="table-wrap">
        <div class="table-title"><span>Recent Purchases</span><span class="badge" id="recent-purchase-count">0</span></div>
        <table><thead><tr><th>Profile</th><th>VA</th><th>Event</th><th>Qty</th><th>Total</th><th>When</th></tr></thead>
        <tbody id="recent-purchases"></tbody></table>
    </div>
</div>

<!-- QUEUE HISTORY -->
<div id="sec-queue" class="section">
    <div class="filter-bar">
        <label>Profile:</label><input type="text" id="q-filter-profile" placeholder="Profile ID...">
        <label>Event:</label><input type="text" id="q-filter-event" placeholder="Event name...">
        <label>Hours:</label><select id="q-filter-hours"><option value="6">6h</option><option value="12">12h</option><option value="24" selected>24h</option><option value="48">48h</option><option value="168">7d</option></select>
        <button class="refresh-btn" onclick="loadQueueHistory()">Search</button>
    </div>
    <div class="table-wrap">
        <div class="table-title"><span>Queue Event Log</span><span class="badge" id="queue-history-count">0</span></div>
        <table><thead><tr><th>Time</th><th>Profile</th><th>VA</th><th>Event</th><th>Queue #</th><th>Status</th></tr></thead>
        <tbody id="queue-history-table"></tbody></table>
    </div>
</div>

<!-- PURCHASES -->
<div id="sec-purchases" class="section">
    <div class="filter-bar">
        <label>Profile:</label><input type="text" id="p-filter-profile" placeholder="Profile ID...">
        <label>Event:</label><input type="text" id="p-filter-event" placeholder="Event name...">
        <label>Days:</label><select id="p-filter-days"><option value="7">7d</option><option value="30" selected>30d</option><option value="90">90d</option></select>
        <button class="refresh-btn" onclick="loadPurchases()">Search</button>
    </div>
    <div class="stats-row" id="purchase-stats"></div>
    <div class="table-wrap">
        <div class="table-title"><span>Purchase Records</span><span class="badge" id="purchase-count">0</span></div>
        <table><thead><tr><th>Time</th><th>Profile</th><th>VA</th><th>Event</th><th>Venue</th><th>Qty</th><th>Total</th><th>Section</th><th>Order</th></tr></thead>
        <tbody id="purchase-table"></tbody></table>
    </div>
</div>

<!-- SESSIONS -->
<div id="sec-sessions" class="section">
    <div class="filter-bar">
        <label>Hours:</label><select id="s-filter-hours"><option value="12">12h</option><option value="24" selected>24h</option><option value="48">48h</option><option value="168">7d</option></select>
        <button class="refresh-btn" onclick="loadSessions()">Search</button>
    </div>
    <div class="table-wrap">
        <div class="table-title"><span>Queue Sessions</span><span class="badge" id="session-count">0</span></div>
        <table><thead><tr><th>Profile</th><th>VA</th><th>Event</th><th>Started</th><th>Duration</th><th>Peak</th><th>Final</th><th>Outcome</th></tr></thead>
        <tbody id="session-table"></tbody></table>
    </div>
</div>

</div>
<script>
const BASE = (location.pathname.match(/^\/[^\/]+/) || [''])[0];
function api(path, params) {
    let url = BASE + path;
    if (params) url += '?' + new URLSearchParams(params).toString();
    return fetch(url).then(r => r.json());
}
function switchTab(name) {
    document.querySelectorAll('.tab').forEach((t, i) => t.classList.toggle('active', t.textContent.toLowerCase().includes(name.substring(0, 4))));
    document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
    document.getElementById('sec-' + name).classList.add('active');
    if (name === 'overview') loadOverview();
    else if (name === 'queue') loadQueueHistory();
    else if (name === 'purchases') loadPurchases();
    else if (name === 'sessions') loadSessions();
}
function queueClass(n) { return n < 500 ? 'low' : n < 5000 ? 'mid' : 'high'; }
function fmtTime(iso) {
    if (!iso) return '-';
    let d = new Date(iso);
    return d.toLocaleString('en-US', {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
}
function fmtDuration(sec) {
    if (!sec) return '-';
    let m = Math.floor(sec / 60), s = sec % 60;
    return m > 0 ? m + 'm ' + s + 's' : s + 's';
}
function loadOverview() {
    api('/api/analytics/overview', {hours: 24}).then(d => {
        document.getElementById('overview-stats').innerHTML = `
            <div class="stat-card"><div class="label">Queue Readings (24h)</div><div class="value">${d.queue_readings}</div></div>
            <div class="stat-card"><div class="label">Active Profiles</div><div class="value gold">${d.active_profiles}</div></div>
            <div class="stat-card"><div class="label">Purchases (24h)</div><div class="value green">${d.purchases}</div></div>
            <div class="stat-card"><div class="label">Success Rate</div><div class="value ${d.success_rate > 50 ? 'green' : d.success_rate > 20 ? 'gold' : 'red'}">${d.success_rate}%</div></div>
            <div class="stat-card"><div class="label">Avg Queue Time</div><div class="value">${d.avg_queue_duration_minutes}m</div></div>
            <div class="stat-card"><div class="label">Active Sessions</div><div class="value gold">${d.active_sessions}</div></div>
        `;
    });
    api('/api/queue/live').then(d => {
        document.getElementById('live-count').textContent = d.count;
        document.getElementById('live-table').innerHTML = d.profiles.length ?
            d.profiles.map(p => `<tr><td>${p.profile_id}</td><td>${p.va_name||'-'}</td><td>${p.event_name||'-'}</td>
                <td><span class="queue-num ${queueClass(p.queue_position)}">${p.queue_position.toLocaleString()}</span></td>
                <td>${p.status||'-'}</td><td>${fmtTime(p.last_seen)}</td></tr>`).join('') :
            '<tr><td colspan="6" class="empty">No active queues</td></tr>';
    });
    api('/api/purchases', {days: 7, limit: 10}).then(d => {
        document.getElementById('recent-purchase-count').textContent = d.count;
        document.getElementById('recent-purchases').innerHTML = d.purchases.length ?
            d.purchases.map(p => `<tr><td>${p.profile_id}</td><td>${p.va_name||'-'}</td><td>${p.event_name}</td>
                <td>${p.quantity}</td><td>$${(p.total_amount||0).toFixed(2)}</td><td>${fmtTime(p.timestamp)}</td></tr>`).join('') :
            '<tr><td colspan="6" class="empty">No recent purchases</td></tr>';
    });
}
function loadQueueHistory() {
    let profile = document.getElementById('q-filter-profile').value;
    let event = document.getElementById('q-filter-event').value;
    let hours = document.getElementById('q-filter-hours').value;
    let params = {hours: hours, limit: 500};
    if (profile) params.profile_id = profile;
    if (event) params.event = event;
    api('/api/queue/history', params).then(d => {
        document.getElementById('queue-history-count').textContent = d.count;
        document.getElementById('queue-history-table').innerHTML = d.events.length ?
            d.events.map(e => `<tr><td>${fmtTime(e.timestamp)}</td><td>${e.profile_id}</td><td>${e.va_name||'-'}</td>
                <td>${e.event_name||'-'}</td><td><span class="queue-num ${queueClass(e.queue_position)}">${e.queue_position.toLocaleString()}</span></td>
                <td>${e.status||'-'}</td></tr>`).join('') :
            '<tr><td colspan="6" class="empty">No queue events found</td></tr>';
    });
}
function loadPurchases() {
    let profile = document.getElementById('p-filter-profile').value;
    let event = document.getElementById('p-filter-event').value;
    let days = document.getElementById('p-filter-days').value;
    let params = {days: days};
    if (profile) params.profile_id = profile;
    if (event) params.event = event;
    api('/api/purchases', params).then(d => {
        document.getElementById('purchase-count').textContent = d.count;
        document.getElementById('purchase-table').innerHTML = d.purchases.length ?
            d.purchases.map(p => `<tr><td>${fmtTime(p.timestamp)}</td><td>${p.profile_id}</td><td>${p.va_name||'-'}</td>
                <td>${p.event_name}</td><td>${p.venue||'-'}</td><td>${p.quantity}</td>
                <td>$${(p.total_amount||0).toFixed(2)}</td><td>${p.section||'-'}</td><td>${p.order_id||'-'}</td></tr>`).join('') :
            '<tr><td colspan="9" class="empty">No purchases found</td></tr>';
    });
    api('/api/purchases/stats', {days: days}).then(d => {
        document.getElementById('purchase-stats').innerHTML = `
            <div class="stat-card"><div class="label">Total Purchases</div><div class="value">${d.total_purchases}</div></div>
            <div class="stat-card"><div class="label">Total Tickets</div><div class="value green">${d.total_tickets}</div></div>
            <div class="stat-card"><div class="label">Total Revenue</div><div class="value gold">$${(d.total_revenue||0).toFixed(2)}</div></div>
        `;
    });
}
function loadSessions() {
    let hours = document.getElementById('s-filter-hours').value;
    api('/api/queue/sessions', {hours: hours}).then(d => {
        document.getElementById('session-count').textContent = d.count;
        document.getElementById('session-table').innerHTML = d.sessions.length ?
            d.sessions.map(s => `<tr><td>${s.profile_id}</td><td>${s.va_name||'-'}</td><td>${s.event_name||'-'}</td>
                <td>${fmtTime(s.started_at)}</td><td>${fmtDuration(s.duration_seconds)}</td>
                <td><span class="queue-num ${queueClass(s.peak_position||0)}">${(s.peak_position||0).toLocaleString()}</span></td>
                <td><span class="queue-num ${queueClass(s.final_position||0)}">${(s.final_position||0).toLocaleString()}</span></td>
                <td><span class="badge-status ${s.outcome}">${s.outcome||'unknown'}</span></td></tr>`).join('') :
            '<tr><td colspan="8" class="empty">No sessions found</td></tr>';
    });
}
function refreshAll() { switchTab(document.querySelector('.tab.active').textContent.toLowerCase().trim().split(' ')[0]); }
loadOverview();
setInterval(() => { if (document.querySelector('#sec-overview.active')) loadOverview(); }, 15000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7890))
    app.run(host="0.0.0.0", port=port, debug=False)
