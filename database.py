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
        # Tabela de RSVPs
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
        # Tabela de Voz
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
        # Tabela de Configurações (Gerentes)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                manager_role_id INTEGER
            )
        """)
        # Tabela de Votos (Enquetes)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                poll_message_id INTEGER,
                user_id INTEGER,
                vote_option TEXT,
                PRIMARY KEY (poll_message_id, user_id)
            )
        """)
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
        await db.commit()

# --- Eventos ---
async def create_event(data):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            INSERT INTO events (guild_id, channel_id, message_id, role_id, title, description, activity_type, date_time, max_slots, creator_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data['guild_id'], data['channel_id'], data['message_id'], data['role_id'], data['title'], data['desc'], data['type'], data['date'], data['slots'], data['creator']))
        await db.commit()
        return cursor.lastrowid

async def get_event(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)) as cursor:
            return await cursor.fetchone()

async def get_active_events():
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM events WHERE status = 'active'") as cursor:
            return await cursor.fetchall()

async def update_event_status(event_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE events SET status = ? WHERE event_id = ?", (status, event_id))
        await db.commit()

async def update_event_details(event_id, title, desc, dt, type_key, slots):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            UPDATE events 
            SET title = ?, description = ?, date_time = ?, activity_type = ?, max_slots = ?
            WHERE event_id = ?
        """, (title, desc, dt, type_key, slots, event_id))
        await db.commit()

async def delete_event(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
        await db.commit()

# --- RSVP ---
async def update_rsvp(event_id, user_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO rsvps (event_id, user_id, status) VALUES (?, ?, ?)", (event_id, user_id, status))
        await db.commit()

async def get_rsvps(event_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM rsvps WHERE event_id = ? ORDER BY timestamp ASC", (event_id,)) as cursor:
            return await cursor.fetchall()

# --- Configurações (Gerentes) ---
async def set_manager_id(guild_id, role_or_user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO guild_settings (guild_id, manager_role_id) VALUES (?, ?)", (guild_id, role_or_user_id))
        await db.commit()

async def get_manager_id(guild_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT manager_role_id FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
            return row['manager_role_id'] if row else None

# --- Voz ---
async def log_voice_session(user_id, start, end, duration):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO voice_sessions (user_id, start_time, end_time, duration_minutes) VALUES (?, ?, ?, ?)", 
                         (user_id, start, end, duration))
        await db.commit()

async def get_voice_hours(days_back):
    limit_date = datetime.datetime.now() - datetime.timedelta(days=days_back)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT user_id, SUM(duration_minutes) as total_mins 
            FROM voice_sessions 
            WHERE start_time > ? AND is_valid = 1 
            GROUP BY user_id
        """, (limit_date,)) as cursor:
            return await cursor.fetchall()

# --- Enquetes ---
async def create_poll(message_id, channel_id, guild_id, poll_type, target_data):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO polls (message_id, channel_id, guild_id, poll_type, target_data)
            VALUES (?, ?, ?, ?, ?)
        """, (message_id, channel_id, guild_id, poll_type, target_data))
        await db.commit()

async def get_active_polls():
    """Retorna enquetes abertas."""
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM polls WHERE status = 'open'") as cursor:
            return await cursor.fetchall()

async def get_poll_details(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM polls WHERE message_id = ?", (message_id,)) as cursor:
            return await cursor.fetchone()

# NOVO: Verifica voto atual do usuário para permitir toggle
async def get_user_vote(message_id, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT vote_option FROM poll_votes WHERE poll_message_id = ? AND user_id = ?", (message_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return row['vote_option'] if row else None

# NOVO: Deleta voto (para toggle)
async def remove_poll_vote(message_id, user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM poll_votes WHERE poll_message_id = ? AND user_id = ?", (message_id, user_id))
        await db.commit()

async def add_poll_vote(message_id, user_id, option):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO poll_votes (poll_message_id, user_id, vote_option) VALUES (?, ?, ?)", 
                         (message_id, user_id, option))
        await db.commit()

async def get_poll_votes(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        # Pega contagem
        async with db.execute("""
            SELECT vote_option, COUNT(*) as count 
            FROM poll_votes 
            WHERE poll_message_id = ? 
            GROUP BY vote_option
        """, (message_id,)) as cursor:
            return await cursor.fetchall()

# NOVO: Pega IDs dos votantes para mostrar nomes
async def get_poll_voters_detailed(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id, vote_option FROM poll_votes WHERE poll_message_id = ?", (message_id,)) as cursor:
            return await cursor.fetchall()

async def get_voters_for_option(message_id, option):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM poll_votes WHERE poll_message_id = ? AND vote_option = ?", (message_id, option)) as cursor:
            return [r['user_id'] for r in await cursor.fetchall()]

async def close_poll(message_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE polls SET status = 'closed' WHERE message_id = ?", (message_id,))
        await db.commit()
