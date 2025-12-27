import discord
from discord.ext import commands, tasks
import database as db
import config
import datetime
import re
from constants import BR_TIMEZONE, RANK_THRESHOLDS, RANK_STYLE

class RolesManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.roles_check_loop.start()
        self.nickname_update_loop.start()
        self.db_cleanup_loop.start()

    def cog_unload(self):
        self.roles_check_loop.cancel()
        self.nickname_update_loop.cancel()
        self.db_cleanup_loop.cancel()

    # --- HELPERS ---
    async def apply_role(self, member, role_name, color=discord.Color.default()):
        guild = member.guild
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            try: role = await guild.create_role(name=role_name, color=color, hover=True, reason="Auto-Criação ColaAI")
            except: return None
        if role and role not in member.roles:
            try: await member.add_roles(role)
            except: pass
        return role

    async def remove_role(self, member, role_name):
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role and role in member.roles:
            try: await member.remove_roles(role)
            except: pass

    async def update_nickname(self, member, rank_key):
        """Renomeia o membro com base no Rank (Ex: ⚔️ ADEPTO Nome)."""
        if member.id == member.guild.owner_id: return

        prefix = RANK_STYLE.get(rank_key, "")
        current_name = member.display_name
        
        # Limpa prefixos antigos
        for p in RANK_STYLE.values():
            if p and current_name.startswith(p):
                current_name = current_name.replace(p, "").strip()
                break 
        
        # Monta novo
        if prefix: new_nick = f"{prefix} {current_name}"
        else: new_nick = current_name

        if len(new_nick) > 32:
            allowed_len = 31 - len(prefix)
            if allowed_len > 0: new_nick = f"{prefix} {current_name[:allowed_len]}…"
            else: new_nick = new_nick[:32]

        if member.display_name != new_nick:
            try: await member.edit(nick=new_nick)
            except: pass

    def get_target_rank(self, member, h7):
        """Calcula o Rank atual baseado em horas e cargos."""
        if member.get_role(config.ROLE_INATIVO):
            return 'INATIVO'
        
        # Mestre Exclusivo (Apenas se tiver o cargo)
        if member.get_role(config.ROLE_MESTRE_ID):
            return 'MESTRE'
            
        # Demais Ranks (Ignora threshold de Mestre)
        if h7 >= RANK_THRESHOLDS['ADEPTO']: return 'ADEPTO'
        if h7 >= RANK_THRESHOLDS['LENDA']: return 'LENDA'
        if h7 >= RANK_THRESHOLDS['ATIVO']: return 'ATIVO'
        return 'TURISTA'

    # --- LOOP 1: GERENCIA CARGOS (A cada 1h) ---
    @tasks.loop(hours=1)
    async def roles_check_loop(self):
        if not self.bot.guilds: return
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        if not guild: return

        valid_hours_data = await db.get_voice_hours(7)
        valid_hours_map = {r['user_id']: r['total_mins']/60 for r in valid_hours_data}
        
        monitoring_active = (datetime.datetime.now() - config.INACTIVITY_START_DATE).days >= 21
        
        colors = {
            "ADEPTO ⚔️": discord.Color.red(),
            "LENDA 💠": discord.Color.purple(),
            "TURISTA": discord.Color.light_grey()
        }

        for member in guild.members:
            if member.bot: continue
            
            h7 = valid_hours_map.get(member.id, 0)
            target_rank = self.get_target_rank(member, h7)
            
            # Aplica Roles
            if target_rank != 'MESTRE':
                # Remove conflitantes
                if target_rank != 'ADEPTO': await self.remove_role(member, "ADEPTO ⚔️")
                if target_rank != 'LENDA': await self.remove_role(member, "LENDA 💠")
                await self.remove_role(member, "VANGUARDA ⚡") # Cleanup legado

                # Aplica novo
                if target_rank == 'ADEPTO': await self.apply_role(member, "ADEPTO ⚔️", colors["ADEPTO ⚔️"])
                elif target_rank == 'LENDA': await self.apply_role(member, "LENDA 💠", colors["LENDA 💠"])

            # --- Lógica de Comportamento (FDS, Presente, Inativo) ---
            sessions_7d = await db.get_sessions_in_range(member.id, 7)
            sessions_21d = await db.get_sessions_in_range(member.id, 21)
            
            days_activity = {}
            for sess in sessions_7d:
                try: s_date = sess['start_time'].split()[0]
                except: continue
                days_activity[s_date] = days_activity.get(s_date, 0) + sess['duration_minutes']
            
            if sum(1 for mins in days_activity.values() if mins >= 60) >= 5:
                await self.apply_role(member, config.ROLE_PRESENTE_SEMPRE)
            else:
                await self.remove_role(member, config.ROLE_PRESENTE_SEMPRE)

            total_mins_7d = sum(days_activity.values())
            unique_days = len(days_activity)
            if unique_days > 0 and unique_days <= 2 and total_mins_7d >= 60:
                await self.apply_role(member, config.ROLE_TURISTA)
            else:
                await self.remove_role(member, config.ROLE_TURISTA)

            is_fds_player = False
            if sessions_21d:
                weekday_mins = 0; weekend_mins = 0
                for sess in sessions_21d:
                    try: st = datetime.datetime.fromisoformat(str(sess['start_time']))
                    except: continue
                    if st.weekday() in [4, 5, 6]: weekend_mins += sess['duration_minutes']
                    else: weekday_mins += sess['duration_minutes']
                if weekday_mins < 30 and weekend_mins >= 60: is_fds_player = True
            
            if is_fds_player: await self.apply_role(member, config.ROLE_GALERA_FDS)
            else: await self.remove_role(member, config.ROLE_GALERA_FDS)

            # Inativo Check
            if monitoring_active:
                last_seen_raw = await db.get_last_activity_timestamp(member.id)
                is_inactive = False
                if last_seen_raw:
                    try:
                        last_seen = datetime.datetime.fromisoformat(str(last_seen_raw))
                        if last_seen.tzinfo is None: last_seen = last_seen.replace(tzinfo=None)
                        if (datetime.datetime.now() - last_seen).days >= 21: is_inactive = True
                    except: pass
                
                if is_inactive:
                    if not member.get_role(config.ROLE_INATIVO):
                        await self.apply_role(member, config.ROLE_INATIVO)
                        try: await member.send("⚠️ **Aviso:** Inatividade detectada (3 semanas).")
                        except: pass
                else:
                    await self.remove_role(member, config.ROLE_INATIVO)

    # --- LOOP 2: GERENCIA NOMES (Apenas às 08:00) ---
    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=BR_TIMEZONE))
    async def nickname_update_loop(self):
        if not self.bot.guilds: return
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        if not guild: return

        # Recalcula horas para garantir frescor
        valid_hours_data = await db.get_voice_hours(7)
        valid_hours_map = {r['user_id']: r['total_mins']/60 for r in valid_hours_data}

        for member in guild.members:
            if member.bot: continue
            if any(r.id in [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID] for r in member.roles): continue

            h7 = valid_hours_map.get(member.id, 0)
            target_rank = self.get_target_rank(member, h7)
            
            await self.update_nickname(member, target_rank)

    @tasks.loop(hours=24)
    async def db_cleanup_loop(self):
        await db.prune_old_voice_data(90)

    @roles_check_loop.before_loop
    async def before_roles(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RolesManager(bot))
