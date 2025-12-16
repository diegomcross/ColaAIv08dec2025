import aiosqlite
import datetime
from constants import BR_TIMEZONE

DB_NAME = "clan_bot.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Tabela de Eventos
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER,
                channel_id INTEGER,
                message_id INTEGER,
                role_id INTEGER,
                title TEXT,
                description TEXT,
                activity_type TEXT,
                date_time TIMESTAMP,
                max_slots INTEGER,
                creator_id INTEGER,
                status TEXT DEFAULT 'active'
            )
        """)
        # RSVPs
        await db.execute("""
            CREATE TABLE IF NOT EXISTS rsvps (
                event_id INTEGER,
                user_id INTEGER,
                status TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (event_id, user_id),
                FOREIGN KEY(event_id) REFERENCES events(event_id) ON DELETE CASCADE
            )
        """)
        # Logs de Voz
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voice_sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration_minutes INTEGER,
                is_valid BOOLEAN DEFAULT 1
            )
        """)
        # Configurações
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                manager_role_id INTEGER
            )
        """)
        # Enquetes
        await db.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                guild_id INTEGER,
                poll_type TEXT,
                target_data TEXT,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes_v2 (
                poll_message_id INTEGER,
                user_id INTEGER,
                vote_option TEXT,
                PRIMARY KEY (poll_message_id, user_id, vote_option)
            )
        """)
        # Ciclo de Vida e Presença
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_lifecycle (
                event_id INTEGER PRIMARY KEY,
                maybe_alert_sent BOOLEAN DEFAULT 0,
                start_alert_sent BOOLEAN DEFAULT 0,
                late_report_sent BOOLEAN DEFAULT 0,
                reminder_1h_sent BOOLEAN DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_attendance (
                event_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'absent',
                first_seen_at TIMESTAMP,
                PRIMARY KEY (event_id, user_id)
            )
        """)
        
        # --- NOVA TABELA: HISTÓRICO DE MESTRES (Para cooldown de 3 semanas) ---
        await db.execute("""
            CREATE TABLE IF NOT EXISTS master_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date_won TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migrações de segurança
        try: await db.execute("ALTER TABLE event_lifecycle ADD COLUMN reminder_1h_sent BOOLEAN DEFAULT 0")
        except: pass
        
        await db.commit()

# --- FUNÇÕES NOVAS (MESTRE E ESTATÍSTICAS) ---

async def log_master_winner(user_id):
    """Registra quem ganhou o Mestre da Semana."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO master_history (user_id) VALUES (?)", (user_id,))
        await db.commit()

async def get_recent_masters(weeks=3):
    """Retorna lista de IDs que foram Mestre nas últimas X semanas."""
    limit_date = datetime.datetime.now() - datetime.timedelta(weeks=weeks)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM master_history WHERE date_won > ?", (limit_date,)) as cursor:
            rows = await cursor.fetchall()
            return [r['user_id'] for r in rows]

async def get_event_stats_7d():
    """Retorna estatísticas de eventos dos últimos 7 dias para o resumo semanal."""
    limit_date = datetime.datetime.now() - datetime.timedelta(days=7)
    stats = {}
    
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        
        # Quem criou mais eventos
        async with db.execute("SELECT creator_id, COUNT(*) as count FROM events WHERE date_time > ? GROUP BY creator_id", (limit_date,)) as cursor:
            async for row in cursor:
                uid = row['creator_id']
                if uid not in stats: stats[uid] = {'created': 0, 'participated': 0}
                stats[uid]['created'] = row['count']
        
        # Quem participou mais (attendance = present)
        async with db.execute("SELECT user_id, COUNT(*) as count FROM event_attendance WHERE first_seen_at > ? AND status='present' GROUP BY user_id", (limit_date,)) as cursor:
            async for row in cursor:
                uid = row['user_id']
                if uid not in stats: stats[uid] = {'created': 0, 'participated': 0}
                stats[uid]['participated'] = row['count']
                
    return stats

# --- FUNÇÕES DE MANUTENÇÃO E ANÁLISE ---

async def prune_old_voice_data(days=90):
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM voice_sessions WHERE start_time < ?", (limit_date,))
        await db.commit()

async def get_sessions_in_range(user_id, days_back):
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT start_time, duration_minutes, is_valid 
            FROM voice_sessions 
            WHERE user_id = ? AND start_time > ?
        """, (user_id, limit_date)) as cursor:
            return await cursor.fetchall()

async def get_last_activity_timestamp(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT MAX(start_time) as last_voice FROM voice_sessions WHERE user_id = ?", (user_id,)) as c:
            voice_row = await c.fetchone()
            last_voice = voice_row['last_voice'] if voice_row and voice_row['last_voice'] else None

        async with db.execute("SELECT MAX(first_seen_at) as last_event FROM event_attendance WHERE user_id = ?", (user_id,)) as c:
            event_row = await c.fetchone()
            last_event = event_row['last_event'] if event_row and event_row['last_event'] else None

        if not last_voice and not last_event: return None
        if not last_voice: return last_event
        if not last_event: return last_voice
        
        try:
            lv_dt = datetime.datetime.fromisoformat(str(last_voice)) if isinstance(last_voice, str) else last_voice
            le_dt = datetime.datetime.fromisoformat(str(last_event)) if isinstance(last_event, str) else last_event
            if lv_dt.tzinfo is None: lv_dt = lv_dt.replace(tzinfo=None)
            if le_dt.tzinfo is None: le_dt = le_dt.replace(tzinfo=None)
            return max(lv_dt, le_dt)
        except: return last_voice

# --- FUNÇÕES DE EVENTOS (PADRÃO) ---
async def create_event(data):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""INSERT INTO events (guild_id, channel_id, message_id, role_id, title, description, activity_type, date_time, max_slots, creator_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (data['guild_id'], data['channel_id'], data['message_id'], data['role_id'], data['title'], data['desc'], data['type'], data['date'], data['slots'], data['creator']))
        await db.commit()
        return cursor.lastrowid
async def get_event(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor: return await cursor.fetchone()
async def get_active_events():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE status = 'active'") as cursor: return await cursor.fetchall()
async def update_event_status(event_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE events SET status = ? WHERE event_id = ?", (status, event_id)); await db.commit()
async def update_event_details(event_id, title, desc, dt, type_key, slots):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE events SET title = ?, description = ?, date_time = ?, activity_type = ?, max_slots = ? WHERE event_id = ?", (title, desc, dt, type_key, slots, event_id)); await db.commit()
async def delete_event(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM events WHERE event_id = ?", (event_id,)); await db.commit()
async def update_rsvp(event_id, user_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO rsvps (event_id, user_id, status) VALUES (?, ?, ?)", (event_id, user_id, status)); await db.commit()
async def get_rsvps(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rsvps WHERE event_id = ? ORDER BY timestamp ASC", (event_id,)) as cursor: return await cursor.fetchall()
async def set_manager_id(guild_id, role_or_user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, manager_role_id) VALUES (?, ?)", (guild_id, role_or_user_id)); await db.commit()
async def get_manager_id(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT manager_role_id FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return row['manager_role_id'] if row else None
async def log_voice_session(user_id, start, end, duration, is_valid=1):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO voice_sessions (user_id, start_time, end_time, duration_minutes, is_valid) VALUES (?, ?, ?, ?, ?)", (user_id, start, end, duration, is_valid)); await db.commit()
async def get_voice_hours(days_back):
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row 
        async with db.execute("SELECT user_id, SUM(duration_minutes) as total_mins FROM voice_sessions WHERE start_time > ? AND is_valid = 1 GROUP BY user_id", (limit_date,)) as cursor: return await cursor.fetchall()
async def create_poll(message_id, channel_id, guild_id, poll_type, target_data):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO polls (message_id, channel_id, guild_id, poll_type, target_data) VALUES (?, ?, ?, ?, ?)", (message_id, channel_id, guild_id, poll_type, target_data)); await db.commit()
async def get_active_polls():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM polls WHERE status = 'open'") as cursor: return await cursor.fetchall()
async def get_poll_details(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM polls WHERE message_id = ?", (message_id,)) as cursor: return await cursor.fetchone()
async def check_user_vote_on_option(message_id, user_id, option):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT 1 FROM poll_votes_v2 WHERE poll_message_id = ? AND user_id = ? AND vote_option = ?", (message_id, user_id, option)) as cursor: return await cursor.fetchone() is not None
async def remove_poll_vote_option(message_id, user_id, option):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM poll_votes_v2 WHERE poll_message_id = ? AND user_id = ? AND vote_option = ?", (message_id, user_id, option)); await db.commit()
async def add_poll_vote(message_id, user_id, option):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO poll_votes_v2 (poll_message_id, user_id, vote_option) VALUES (?, ?, ?)", (message_id, user_id, option)); await db.commit()
async def get_poll_votes(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT vote_option, COUNT(*) as count FROM poll_votes_v2 WHERE poll_message_id = ? GROUP BY vote_option", (message_id,)) as cursor: return await cursor.fetchall()
async def get_poll_voters_detailed(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, vote_option FROM poll_votes_v2 WHERE poll_message_id = ?", (message_id,)) as cursor: return await cursor.fetchall()
async def get_voters_for_option(message_id, option):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM poll_votes_v2 WHERE poll_message_id = ? AND vote_option = ?", (message_id, option)) as cursor: return list(set([r['user_id'] for r in await cursor.fetchall()]))
async def close_poll(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE polls SET status = 'closed' WHERE message_id = ?", (message_id,)); await db.commit()
async def get_event_lifecycle(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM event_lifecycle WHERE event_id = ?", (event_id,)) as cursor: return await cursor.fetchone()
async def set_lifecycle_flag(event_id, flag_name, value=1):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO event_lifecycle (event_id) VALUES (?)", (event_id,)); query = f"UPDATE event_lifecycle SET {flag_name} = ? WHERE event_id = ?"; await db.execute(query, (value, event_id)); await db.commit()
async def reset_event_lifecycle_flags(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE event_lifecycle SET maybe_alert_sent = 0, start_alert_sent = 0, late_report_sent = 0, reminder_1h_sent = 0 WHERE event_id = ?", (event_id,)); await db.commit()
async def mark_attendance_present(event_id, user_id):
    now = datetime.datetime.now()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO event_attendance (event_id, user_id, status, first_seen_at) VALUES (?, ?, 'present', ?) ON CONFLICT(event_id, user_id) DO UPDATE SET status = 'present', first_seen_at = COALESCE(first_seen_at, excluded.first_seen_at)", (event_id, user_id, now)); await db.commit()
async def get_attendance_status(event_id, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT status FROM event_attendance WHERE event_id = ? AND user_id = ?", (event_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row['status'] if row else 'absent'
