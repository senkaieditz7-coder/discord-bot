import os
import asyncio
import psycopg2
import psycopg2.extras
import psycopg2.pool
import psycopg2.extensions
from datetime import datetime

DB_URL = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")

_pool = None

# Extra connection kwargs: fail fast if DB unreachable (10s),
# send TCP keepalives so dead Supabase connections are detected within ~55s
# instead of hanging until OS TCP timeout.
_CONN_KWARGS = {
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 5,
    "keepalives_count": 5,
}


def _get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(1, 10, DB_URL, **_CONN_KWARGS)
    return _pool


def _get_conn():
    """Return a live connection from the pool.
    Validates the connection with a quick SELECT 1; if dead, rebuilds the pool."""
    global _pool
    pool = _get_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        if conn.status != psycopg2.extensions.STATUS_READY:
            conn.rollback()
    except Exception:
        try:
            pool.putconn(conn)
        except Exception:
            pass
        try:
            pool.closeall()
        except Exception:
            pass
        _pool = None
        pool = _get_pool()
        conn = pool.getconn()
    return conn


def _put_conn(conn):
    _get_pool().putconn(conn)

def init_db():
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                from_user TEXT,
                to_user TEXT,
                guild_id TEXT,
                note TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
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
    finally:
        _put_conn(conn)


# ── Config ────────────────────────────────────────────────────────────────────

def get_config(guild_id: str, key: str, default=None):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT value FROM config WHERE key=%s", (f"{guild_id}:{key}",))
        row = c.fetchone()
        return row["value"] if row else default
    finally:
        _put_conn(conn)


def set_config(guild_id: str, key: str, value: str):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value",
            (f"{guild_id}:{key}", value)
        )
        conn.commit()
    finally:
        _put_conn(conn)


def get_all_config(guild_id: str) -> dict:
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT key, value FROM config WHERE key LIKE %s", (f"{guild_id}:%",))
        rows = c.fetchall()
        prefix = f"{guild_id}:"
        return {r["key"][len(prefix):]: r["value"] for r in rows}
    finally:
        _put_conn(conn)


# ── Tickets ───────────────────────────────────────────────────────────────────

def create_ticket(channel_id, guild_id, opener_id, ticket_type="trade"):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            "INSERT INTO tickets (channel_id, guild_id, opener_id, ticket_type, status, created_at) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (channel_id, guild_id, opener_id, ticket_type, "open", datetime.utcnow().isoformat())
        )
        tid = c.fetchone()["id"]
        c.execute("INSERT INTO ticket_users (ticket_id, user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (tid, opener_id))
        conn.commit()
        return tid
    finally:
        _put_conn(conn)


def get_ticket(channel_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM tickets WHERE channel_id=%s", (channel_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        _put_conn(conn)


def get_ticket_by_id(ticket_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM tickets WHERE id=%s", (ticket_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        _put_conn(conn)


def claim_ticket(channel_id, staff_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("UPDATE tickets SET claimed_by=%s WHERE channel_id=%s", (staff_id, channel_id))
        conn.commit()
    finally:
        _put_conn(conn)


def close_ticket(channel_id, transcript=""):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "UPDATE tickets SET status='closed', closed_at=%s, transcript=%s WHERE channel_id=%s",
            (datetime.utcnow().isoformat(), transcript, channel_id)
        )
        conn.commit()
    finally:
        _put_conn(conn)


def transfer_ticket(channel_id, new_mm_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("UPDATE tickets SET claimed_by=%s WHERE channel_id=%s", (new_mm_id, channel_id))
        conn.commit()
    finally:
        _put_conn(conn)


def add_ticket_user(channel_id, user_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT id FROM tickets WHERE channel_id=%s", (channel_id,))
        row = c.fetchone()
        if row:
            c.execute("INSERT INTO ticket_users (ticket_id, user_id) VALUES (%s,%s) ON CONFLICT DO NOTHING", (row["id"], user_id))
            conn.commit()
    finally:
        _put_conn(conn)


def remove_ticket_user(channel_id, user_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT id FROM tickets WHERE channel_id=%s", (channel_id,))
        row = c.fetchone()
        if row:
            c.execute("DELETE FROM ticket_users WHERE ticket_id=%s AND user_id=%s", (row["id"], user_id))
            conn.commit()
    finally:
        _put_conn(conn)


def get_ticket_users(channel_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT id FROM tickets WHERE channel_id=%s", (channel_id,))
        row = c.fetchone()
        if not row:
            return []
        c.execute("SELECT user_id FROM ticket_users WHERE ticket_id=%s", (row["id"],))
        users = c.fetchall()
        return [u["user_id"] for u in users]
    finally:
        _put_conn(conn)


def get_all_tickets(guild_id, status=None):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if status:
            c.execute("SELECT * FROM tickets WHERE guild_id=%s AND status=%s", (guild_id, status))
        else:
            c.execute("SELECT * FROM tickets WHERE guild_id=%s", (guild_id,))
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        _put_conn(conn)


# ── Vouches ───────────────────────────────────────────────────────────────────

def add_vouch(from_user, to_user, guild_id, note=""):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO vouches (from_user, to_user, guild_id, note, created_at) VALUES (%s,%s,%s,%s,%s)",
            (from_user, to_user, guild_id, note, datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        _put_conn(conn)


def get_vouches(user_id, guild_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM vouches WHERE to_user=%s AND guild_id=%s ORDER BY created_at DESC", (user_id, guild_id))
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        _put_conn(conn)


def count_vouches(user_id, guild_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT COUNT(*) as cnt FROM vouches WHERE to_user=%s AND guild_id=%s", (user_id, guild_id))
        row = c.fetchone()
        return row["cnt"] if row else 0
    finally:
        _put_conn(conn)


def has_vouched_recently(from_user, to_user, guild_id, hours=24):
    conn = _get_conn()
    try:
        from datetime import timedelta
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        c.execute(
            "SELECT COUNT(*) as cnt FROM vouches WHERE from_user=%s AND to_user=%s AND guild_id=%s AND created_at>%s",
            (from_user, to_user, guild_id, cutoff)
        )
        row = c.fetchone()
        return (row["cnt"] if row else 0) > 0
    finally:
        _put_conn(conn)


def set_vouches(user_id, guild_id, count):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM vouches WHERE to_user=%s AND guild_id=%s", (user_id, guild_id))
        for i in range(count):
            c.execute(
                "INSERT INTO vouches (from_user, to_user, guild_id, note, created_at) VALUES (%s,%s,%s,%s,%s)",
                ("system", user_id, guild_id, "Manually set", datetime.utcnow().isoformat())
            )
        conn.commit()
    finally:
        _put_conn(conn)


def delete_vouch(vouch_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM vouches WHERE id=%s", (vouch_id,))
        conn.commit()
    finally:
        _put_conn(conn)


def delete_latest_vouch(from_user, to_user, guild_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            "SELECT id FROM vouches WHERE from_user=%s AND to_user=%s AND guild_id=%s ORDER BY created_at DESC LIMIT 1",
            (from_user, to_user, guild_id)
        )
        row = c.fetchone()
        if row:
            c.execute("DELETE FROM vouches WHERE id=%s", (row["id"],))
            conn.commit()
        return bool(row)
    finally:
        _put_conn(conn)


# ── Deposits ──────────────────────────────────────────────────────────────────

def add_deposit(user_id, guild_id, deposit_type, amount, note, staff_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO deposits (user_id, guild_id, deposit_type, amount, note, staff_id, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (user_id, guild_id, deposit_type, amount, note, staff_id, datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        _put_conn(conn)


def get_deposits(user_id, guild_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM deposits WHERE user_id=%s AND guild_id=%s ORDER BY created_at DESC", (user_id, guild_id))
        rows = c.fetchall()
        return [dict(r) for r in rows]
    finally:
        _put_conn(conn)


def delete_deposit(deposit_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM deposits WHERE id=%s", (deposit_id,))
        conn.commit()
    finally:
        _put_conn(conn)


# ── Blacklist ─────────────────────────────────────────────────────────────────

def blacklist_user(user_id, guild_id, reason, added_by):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO blacklist (user_id, guild_id, reason, added_by, created_at) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (user_id, guild_id) DO UPDATE SET reason=EXCLUDED.reason, added_by=EXCLUDED.added_by",
            (user_id, guild_id, reason, added_by, datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        _put_conn(conn)


def unblacklist_user(user_id, guild_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM blacklist WHERE user_id=%s AND guild_id=%s", (user_id, guild_id))
        conn.commit()
    finally:
        _put_conn(conn)


def is_blacklisted(user_id, guild_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM blacklist WHERE user_id=%s AND guild_id=%s", (user_id, guild_id))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        _put_conn(conn)


# ── Confirmations ─────────────────────────────────────────────────────────────

def create_confirmation(channel_id, guild_id, user1_id, user2_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            "INSERT INTO confirmations (channel_id, guild_id, user1_id, user2_id, created_at) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (channel_id, guild_id, user1_id, user2_id, datetime.utcnow().isoformat())
        )
        row = c.fetchone()
        conn.commit()
        return row["id"]
    finally:
        _put_conn(conn)


def update_confirmation(conf_id, message_id=None, user1_status=None, user2_status=None):
    conn = _get_conn()
    try:
        c = conn.cursor()
        if message_id:
            c.execute("UPDATE confirmations SET message_id=%s WHERE id=%s", (message_id, conf_id))
        if user1_status:
            c.execute("UPDATE confirmations SET user1_status=%s WHERE id=%s", (user1_status, conf_id))
        if user2_status:
            c.execute("UPDATE confirmations SET user2_status=%s WHERE id=%s", (user2_status, conf_id))
        conn.commit()
    finally:
        _put_conn(conn)


def resolve_confirmation(conf_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("UPDATE confirmations SET resolved_at=%s WHERE id=%s", (datetime.utcnow().isoformat(), conf_id))
        conn.commit()
    finally:
        _put_conn(conn)


def get_confirmation(conf_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM confirmations WHERE id=%s", (conf_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        _put_conn(conn)


# ── Auto MM Sessions ──────────────────────────────────────────────────────────

def create_automm_session(channel_id, guild_id, user1_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO automm_sessions (channel_id, guild_id, user1_id, state, created_at) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (channel_id) DO UPDATE SET guild_id=EXCLUDED.guild_id, user1_id=EXCLUDED.user1_id, state=EXCLUDED.state, created_at=EXCLUDED.created_at",
            (channel_id, guild_id, user1_id, "waiting_user2", datetime.utcnow().isoformat())
        )
        conn.commit()
    finally:
        _put_conn(conn)


def get_automm_session(channel_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM automm_sessions WHERE channel_id=%s", (channel_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        _put_conn(conn)


def get_automm_session_by_sender(guild_id, sender_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            "SELECT * FROM automm_sessions WHERE guild_id=%s AND sender_id=%s AND state='waiting_automm'",
            (guild_id, sender_id)
        )
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        _put_conn(conn)


def update_automm_session(channel_id, **kwargs):
    conn = _get_conn()
    try:
        c = conn.cursor()
        for key, value in kwargs.items():
            c.execute(f"UPDATE automm_sessions SET {key}=%s WHERE channel_id=%s", (value, channel_id))
        conn.commit()
    finally:
        _put_conn(conn)


def delete_automm_session(channel_id):
    conn = _get_conn()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM automm_sessions WHERE channel_id=%s", (channel_id,))
        conn.commit()
    finally:
        _put_conn(conn)


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_stats(guild_id):
    conn = _get_conn()
    try:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT COUNT(*) as c FROM tickets WHERE guild_id=%s", (guild_id,))
        total_tickets = c.fetchone()["c"]
        c.execute("SELECT COUNT(*) as c FROM tickets WHERE guild_id=%s AND status='open'", (guild_id,))
        open_tickets = c.fetchone()["c"]
        c.execute("SELECT COUNT(*) as c FROM vouches WHERE guild_id=%s", (guild_id,))
        total_vouches = c.fetchone()["c"]
        c.execute("SELECT COUNT(*) as c FROM confirmations WHERE guild_id=%s", (guild_id,))
        total_confirms = c.fetchone()["c"]
        c.execute("SELECT COUNT(*) as c FROM deposits WHERE guild_id=%s", (guild_id,))
        total_deposits = c.fetchone()["c"]
        return {
            "total_tickets": total_tickets,
            "open_tickets": open_tickets,
            "total_vouches": total_vouches,
            "total_confirms": total_confirms,
            "total_deposits": total_deposits,
        }
    finally:
        _put_conn(conn)