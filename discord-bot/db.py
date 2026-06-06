import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE,
            guild_id TEXT,
            opener_id TEXT,
            claimed_by TEXT,
            status TEXT DEFAULT 'open',
            ticket_type TEXT DEFAULT 'trade',
            created_at TEXT,
            closed_at TEXT,
            transcript TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ticket_users (
            ticket_id INTEGER,
            user_id TEXT,
            PRIMARY KEY (ticket_id, user_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS vouches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT,
            to_user TEXT,
            guild_id TEXT,
            note TEXT,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            guild_id TEXT,
            deposit_type TEXT,
            amount TEXT,
            note TEXT,
            staff_id TEXT,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS blacklist (
            user_id TEXT,
            guild_id TEXT,
            reason TEXT,
            added_by TEXT,
            created_at TEXT,
            PRIMARY KEY (user_id, guild_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS automm_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE,
            guild_id TEXT,
            user1_id TEXT,
            user2_id TEXT,
            sender_id TEXT,
            receiver_id TEXT,
            payment_method TEXT,
            state TEXT DEFAULT 'waiting_user2',
            user1_ready INTEGER DEFAULT 0,
            user2_ready INTEGER DEFAULT 0,
            trade_done_1 INTEGER DEFAULT 0,
            trade_done_2 INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS confirmations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            guild_id TEXT,
            user1_id TEXT,
            user2_id TEXT,
            user1_status TEXT DEFAULT 'pending',
            user2_status TEXT DEFAULT 'pending',
            message_id TEXT,
            created_at TEXT,
            resolved_at TEXT
        )
    """)

    conn.commit()
    conn.close()


# ── Config ────────────────────────────────────────────────────────────────────

def get_config(guild_id: str, key: str, default=None):
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM config WHERE key=?", (f"{guild_id}:{key}",)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_config(guild_id: str, key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
        (f"{guild_id}:{key}", value)
    )
    conn.commit()
    conn.close()


def get_all_config(guild_id: str) -> dict:
    conn = get_conn()
    rows = conn.execute(
        "SELECT key, value FROM config WHERE key LIKE ?", (f"{guild_id}:%",)
    ).fetchall()
    conn.close()
    prefix = f"{guild_id}:"
    return {r["key"][len(prefix):]: r["value"] for r in rows}


# ── Tickets ───────────────────────────────────────────────────────────────────

def create_ticket(channel_id, guild_id, opener_id, ticket_type="trade"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO tickets (channel_id, guild_id, opener_id, ticket_type, status, created_at) VALUES (?,?,?,?,?,?)",
        (channel_id, guild_id, opener_id, ticket_type, "open", datetime.utcnow().isoformat())
    )
    conn.commit()
    tid = conn.execute("SELECT id FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()["id"]
    conn.execute("INSERT OR IGNORE INTO ticket_users (ticket_id, user_id) VALUES (?,?)", (tid, opener_id))
    conn.commit()
    conn.close()
    return tid


def get_ticket(channel_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_ticket_by_id(ticket_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def claim_ticket(channel_id, staff_id):
    conn = get_conn()
    conn.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?", (staff_id, channel_id))
    conn.commit()
    conn.close()


def close_ticket(channel_id, transcript=""):
    conn = get_conn()
    conn.execute(
        "UPDATE tickets SET status='closed', closed_at=?, transcript=? WHERE channel_id=?",
        (datetime.utcnow().isoformat(), transcript, channel_id)
    )
    conn.commit()
    conn.close()


def transfer_ticket(channel_id, new_mm_id):
    conn = get_conn()
    conn.execute("UPDATE tickets SET claimed_by=? WHERE channel_id=?", (new_mm_id, channel_id))
    conn.commit()
    conn.close()


def add_ticket_user(channel_id, user_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()
    if row:
        conn.execute("INSERT OR IGNORE INTO ticket_users (ticket_id, user_id) VALUES (?,?)", (row["id"], user_id))
        conn.commit()
    conn.close()


def remove_ticket_user(channel_id, user_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()
    if row:
        conn.execute("DELETE FROM ticket_users WHERE ticket_id=? AND user_id=?", (row["id"], user_id))
        conn.commit()
    conn.close()


def get_ticket_users(channel_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM tickets WHERE channel_id=?", (channel_id,)).fetchone()
    if not row:
        conn.close()
        return []
    users = conn.execute("SELECT user_id FROM ticket_users WHERE ticket_id=?", (row["id"],)).fetchall()
    conn.close()
    return [u["user_id"] for u in users]


def get_all_tickets(guild_id, status=None):
    conn = get_conn()
    if status:
        rows = conn.execute("SELECT * FROM tickets WHERE guild_id=? AND status=?", (guild_id, status)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tickets WHERE guild_id=?", (guild_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Vouches ───────────────────────────────────────────────────────────────────

def add_vouch(from_user, to_user, guild_id, note=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO vouches (from_user, to_user, guild_id, note, created_at) VALUES (?,?,?,?,?)",
        (from_user, to_user, guild_id, note, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_vouches(user_id, guild_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM vouches WHERE to_user=? AND guild_id=? ORDER BY created_at DESC",
        (user_id, guild_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_vouches(user_id, guild_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM vouches WHERE to_user=? AND guild_id=?",
        (user_id, guild_id)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def has_vouched_recently(from_user, to_user, guild_id, hours=24):
    conn = get_conn()
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM vouches WHERE from_user=? AND to_user=? AND guild_id=? AND created_at>?",
        (from_user, to_user, guild_id, cutoff)
    ).fetchone()
    conn.close()
    return (row["cnt"] if row else 0) > 0


def set_vouches(user_id, guild_id, count):
    conn = get_conn()
    conn.execute("DELETE FROM vouches WHERE to_user=? AND guild_id=?", (user_id, guild_id))
    for i in range(count):
        conn.execute(
            "INSERT INTO vouches (from_user, to_user, guild_id, note, created_at) VALUES (?,?,?,?,?)",
            ("system", user_id, guild_id, "Manually set", datetime.utcnow().isoformat())
        )
    conn.commit()
    conn.close()


def delete_vouch(vouch_id):
    conn = get_conn()
    conn.execute("DELETE FROM vouches WHERE id=?", (vouch_id,))
    conn.commit()
    conn.close()


def delete_latest_vouch(from_user, to_user, guild_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM vouches WHERE from_user=? AND to_user=? AND guild_id=? ORDER BY created_at DESC LIMIT 1",
        (from_user, to_user, guild_id)
    ).fetchone()
    if row:
        conn.execute("DELETE FROM vouches WHERE id=?", (row["id"],))
        conn.commit()
    conn.close()
    return bool(row)


# ── Deposits ──────────────────────────────────────────────────────────────────

def add_deposit(user_id, guild_id, deposit_type, amount, note, staff_id):
    conn = get_conn()
    conn.execute(
        "INSERT INTO deposits (user_id, guild_id, deposit_type, amount, note, staff_id, created_at) VALUES (?,?,?,?,?,?,?)",
        (user_id, guild_id, deposit_type, amount, note, staff_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_deposits(user_id, guild_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM deposits WHERE user_id=? AND guild_id=? ORDER BY created_at DESC",
        (user_id, guild_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_deposit(deposit_id):
    conn = get_conn()
    conn.execute("DELETE FROM deposits WHERE id=?", (deposit_id,))
    conn.commit()
    conn.close()


# ── Blacklist ─────────────────────────────────────────────────────────────────

def blacklist_user(user_id, guild_id, reason, added_by):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO blacklist (user_id, guild_id, reason, added_by, created_at) VALUES (?,?,?,?,?)",
        (user_id, guild_id, reason, added_by, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def unblacklist_user(user_id, guild_id):
    conn = get_conn()
    conn.execute("DELETE FROM blacklist WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    conn.commit()
    conn.close()


def is_blacklisted(user_id, guild_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM blacklist WHERE user_id=? AND guild_id=?", (user_id, guild_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Confirmations ─────────────────────────────────────────────────────────────

def create_confirmation(channel_id, guild_id, user1_id, user2_id):
    conn = get_conn()
    conn.execute(
        "INSERT INTO confirmations (channel_id, guild_id, user1_id, user2_id, created_at) VALUES (?,?,?,?,?)",
        (channel_id, guild_id, user1_id, user2_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
    conn.close()
    return row["id"]


def update_confirmation(conf_id, message_id=None, user1_status=None, user2_status=None):
    conn = get_conn()
    if message_id:
        conn.execute("UPDATE confirmations SET message_id=? WHERE id=?", (message_id, conf_id))
    if user1_status:
        conn.execute("UPDATE confirmations SET user1_status=? WHERE id=?", (user1_status, conf_id))
    if user2_status:
        conn.execute("UPDATE confirmations SET user2_status=? WHERE id=?", (user2_status, conf_id))
    conn.commit()
    conn.close()


def resolve_confirmation(conf_id):
    conn = get_conn()
    conn.execute(
        "UPDATE confirmations SET resolved_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), conf_id)
    )
    conn.commit()
    conn.close()


def get_confirmation(conf_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM confirmations WHERE id=?", (conf_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Auto MM Sessions ──────────────────────────────────────────────────────────

def create_automm_session(channel_id, guild_id, user1_id):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO automm_sessions (channel_id, guild_id, user1_id, state, created_at) VALUES (?,?,?,?,?)",
        (channel_id, guild_id, user1_id, "waiting_user2", datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_automm_session(channel_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM automm_sessions WHERE channel_id=?", (channel_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_automm_session_by_sender(guild_id, sender_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM automm_sessions WHERE guild_id=? AND sender_id=? AND state='waiting_automm'",
        (guild_id, sender_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_automm_session(channel_id, **kwargs):
    conn = get_conn()
    for key, value in kwargs.items():
        conn.execute(f"UPDATE automm_sessions SET {key}=? WHERE channel_id=?", (value, channel_id))
    conn.commit()
    conn.close()


def delete_automm_session(channel_id):
    conn = get_conn()
    conn.execute("DELETE FROM automm_sessions WHERE channel_id=?", (channel_id,))
    conn.commit()
    conn.close()


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats(guild_id):
    conn = get_conn()
    total_tickets = conn.execute("SELECT COUNT(*) as c FROM tickets WHERE guild_id=?", (guild_id,)).fetchone()["c"]
    open_tickets = conn.execute("SELECT COUNT(*) as c FROM tickets WHERE guild_id=? AND status='open'", (guild_id,)).fetchone()["c"]
    total_vouches = conn.execute("SELECT COUNT(*) as c FROM vouches WHERE guild_id=?", (guild_id,)).fetchone()["c"]
    total_confirms = conn.execute("SELECT COUNT(*) as c FROM confirmations WHERE guild_id=?", (guild_id,)).fetchone()["c"]
    total_deposits = conn.execute("SELECT COUNT(*) as c FROM deposits WHERE guild_id=?", (guild_id,)).fetchone()["c"]
    conn.close()
    return {
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "total_vouches": total_vouches,
        "total_confirms": total_confirms,
        "total_deposits": total_deposits,
    }
