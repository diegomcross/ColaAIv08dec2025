import aiosqlite
import datetime
from constants import BR_TIMEZONE

DB_NAME = "clan_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # --- TABELAS EXISTENTES (MANTIDAS) ---
        await db.execute("CREATE TABLE IF NOT EXISTS events (event_id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, channel_id INTEGER, message_id INTEGER, role_id INTEGER, title TEXT, description TEXT, activity_type TEXT, date_time TIMESTAMP, max_slots INTEGER, creator_id INTEGER, status TEXT DEFAULT 'active')")
        await db.execute("CREATE TABLE IF NOT EXISTS rsvps (event_id INTEGER, user_id INTEGER, status TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (event_id, user_id), FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE)")
        await db.execute("CREATE TABLE IF NOT EXISTS voice_sessions (session_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, start_time TIMESTAMP, end_time TIMESTAMP, duration_minutes INTEGER, is_valid BOOLEAN DEFAULT 1)")
        await db.execute("CREATE TABLE IF NOT EXISTS guild_settings (guild_id INTEGER PRIMARY KEY, manager_role_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS polls (message_id INTEGER PRIMARY KEY, channel_id INTEGER, guild_id INTEGER, poll_type TEXT, target_data TEXT, status TEXT DEFAULT 'open', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("CREATE TABLE IF NOT EXISTS poll_votes_v2 (poll_message_id INTEGER, user_id INTEGER, vote_option TEXT, PRIMARY KEY (poll_message_id, user_id, vote_option))")
        await db.execute("CREATE TABLE IF NOT EXISTS event_lifecycle (event_id INTEGER PRIMARY KEY, maybe_alert_sent BOOLEAN DEFAULT 0, start_alert_sent BOOLEAN DEFAULT 0, late_report_sent BOOLEAN DEFAULT 0, reminder_1h_sent BOOLEAN DEFAULT 0, reminder_4h_sent BOOLEAN DEFAULT 0, reminder_24h_sent BOOLEAN DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS master_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, date_won TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("CREATE TABLE IF NOT EXISTS pending_joins (user_id INTEGER PRIMARY KEY, bungie_id TEXT, roles_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        await db.execute("CREATE TABLE IF NOT EXISTS probation_extensions (user_id INTEGER PRIMARY KEY, extended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

        # --- UPDATE: ATTENDANCE COM MINUTOS ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_attendance (
                event_id INTEGER, 
                user_id INTEGER, 
                status TEXT DEFAULT 'present', 
                first_seen_at TIMESTAMP, 
                minutes_active INTEGER DEFAULT 0,
                PRIMARY KEY (event_id, user_id)
            )
        """)
        # Migração de segurança para DB existente
        try: await db.execute("ALTER TABLE event_attendance ADD COLUMN minutes_active INTEGER DEFAULT 0")
        except: pass
        
        await db.commit()

# --- TRACKING DE MINUTOS ---
async def increment_event_attendance(event_id, user_id, minutes_to_add=5):
    """Soma minutos para um usuário confirmado."""
    now = datetime.datetime.now()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO event_attendance (event_id, user_id, status, first_seen_at, minutes_active) 
            VALUES (?, ?, 'present', ?, ?) 
            ON CONFLICT(event_id, user_id) 
            DO UPDATE SET 
                minutes_active = minutes_active + excluded.minutes_active,
                first_seen_at = COALESCE(first_seen_at, excluded.first_seen_at)
        """, (event_id, user_id, now, minutes_to_add))
        await db.commit()

async def get_valid_attendees(event_id, min_minutes=60):
    """Retorna lista de quem cumpriu o tempo mínimo."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM event_attendance WHERE event_id = ? AND minutes_active >= ?", (event_id, min_minutes)) as cursor:
            rows = await cursor.fetchall()
            return [r['user_id'] for r in rows]

# --- FUNÇÕES PRESERVADAS ---
# (Mantenha todo o resto do seu arquivo aqui: create_event, get_active_events, rsvps, polls, etc.)
# ...
async def save_pending_join(user_id, bungie_id, roles_list):
    import json
    roles_json = json.dumps(roles_list)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO pending_joins (user_id, bungie_id, roles_json) VALUES (?, ?, ?)", (user_id, bungie_id, roles_json)); await db.commit()
async def get_pending_join(user_id):
    import json
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM pending_joins WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row: return {'bungie_id': row['bungie_id'], 'roles': json.loads(row['roles_json'])}
            return None
async def remove_pending_join(user_id):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("DELETE FROM pending_joins WHERE user_id = ?", (user_id,)); await db.commit()
async def extend_probation(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO probation_extensions (user_id, extended_at) VALUES (?, ?)", (user_id, datetime.datetime.now())); await db.commit()
async def is_probation_extended(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT extended_at FROM probation_extensions WHERE user_id = ?", (user_id,)) as c:
            row = await c.fetchone()
            if not row: return False
            try:
                dt = datetime.datetime.fromisoformat(str(row['extended_at']))
                return (datetime.datetime.now() - dt).days < 14
            except: return False
async def get_last_activity_timestamp(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT MAX(start_time) as l FROM voice_sessions WHERE user_id = ?", (user_id,)) as c:
            r = await c.fetchone(); return r['l'] if r else None
async def get_active_events():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE status = 'active'") as cursor: return await cursor.fetchall()
async def get_rsvps(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rsvps WHERE event_id = ?", (event_id,)) as cursor: return await cursor.fetchall()
async def update_event_status(event_id, status):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("UPDATE events SET status = ? WHERE event_id = ?", (status, event_id)); await db.commit()
async def get_event_lifecycle(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM event_lifecycle WHERE event_id = ?", (event_id,)) as c: return await c.fetchone()
async def set_lifecycle_flag(event_id, flag, val=1):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO event_lifecycle (event_id) VALUES (?)", (event_id,))
        await db.execute(f"UPDATE event_lifecycle SET {flag} = ? WHERE event_id = ?", (val, event_id)); await db.commit()
async def create_event(data):
    async with aiosqlite.connect(DB_NAME) as db:
        c = await db.execute("INSERT INTO events (guild_id, channel_id, message_id, role_id, title, description, activity_type, date_time, max_slots, creator_id) VALUES (?,?,?,?,?,?,?,?,?,?)", (data['guild_id'], data['channel_id'], data['message_id'], data['role_id'], data['title'], data['desc'], data['type'], data['date'], data['slots'], data['creator']))
        await db.commit(); return c.lastrowid
async def get_voice_hours(days):
    limit = datetime.datetime.now(BR_TIMEZONE) - datetime.timedelta(days=days)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, SUM(duration_minutes) as total_mins FROM voice_sessions WHERE start_time > ? AND is_valid=1 GROUP BY user_id", (limit,)) as c: return await c.fetchall()
async def get_sessions_in_range(user_id, days):
    limit = datetime.datetime.now(BR_TIMEZONE) - datetime.timedelta(days=days)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT start_time, duration_minutes FROM voice_sessions WHERE user_id=? AND start_time>?", (user_id, limit)) as c: return await c.fetchall()
async def log_voice_session(uid, start, end, dur, is_valid):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT INTO voice_sessions (user_id, start_time, end_time, duration_minutes, is_valid) VALUES (?,?,?,?,?)", (uid, start, end, dur, is_valid)); await db.commit()
async def create_poll(mid, cid, gid, ptype, data):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT INTO polls (message_id, channel_id, guild_id, poll_type, target_data) VALUES (?,?,?,?,?)", (mid, cid, gid, ptype, data)); await db.commit()
async def mark_attendance_present(event_id, user_id):
    await increment_event_attendance(event_id, user_id, 5)
async def check_user_vote_on_option(mid, uid, opt):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM poll_votes_v2 WHERE poll_message_id=? AND user_id=? AND vote_option=?", (mid, uid, opt)) as c: return await c.fetchone() is not None
async def remove_poll_vote_option(mid, uid, opt):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("DELETE FROM poll_votes_v2 WHERE poll_message_id=? AND user_id=? AND vote_option=?", (mid, uid, opt)); await db.commit()
async def add_poll_vote(mid, uid, opt):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("INSERT OR IGNORE INTO poll_votes_v2 (poll_message_id, user_id, vote_option) VALUES (?,?,?)", (mid, uid, opt)); await db.commit()
async def get_poll_voters_detailed(mid):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, vote_option FROM poll_votes_v2 WHERE poll_message_id=?", (mid,)) as c: return await c.fetchall()
async def get_voters_for_option(mid, opt):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM poll_votes_v2 WHERE poll_message_id=? AND vote_option=?", (mid, opt)) as c: return [r['user_id'] for r in await c.fetchall()]
async def get_poll_details(mid):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM polls WHERE message_id=?", (mid,)) as c: return await c.fetchone()
async def close_poll(mid):
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("UPDATE polls SET status='closed' WHERE message_id=?", (mid,)); await db.commit()
async def prune_old_voice_data(days):
    limit = datetime.datetime.now() - datetime.timedelta(days=days)
    async with aiosqlite.connect(DB_NAME) as db: await db.execute("DELETE FROM voice_sessions WHERE start_time < ?", (limit,)); await db.commit()
