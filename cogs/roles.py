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
        self.db_cleanup_loop.start()

    def cog_unload(self):
        self.roles_check_loop.cancel()
        self.db_cleanup_loop.cancel()

    async def apply_role(self, member, role_name, color=discord.Color.default()):
        """Busca role pelo nome, cria se não existir e aplica."""
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
        # Ignora Dono do Servidor (Bot não tem permissão)
        if member.id == member.guild.owner_id: return

        # Pega o estilo do constants.py
        prefix = RANK_STYLE.get(rank_key, "")
        
        # Limpa apelido atual (remove emojis/títulos antigos para não duplicar)
        # Regex busca padrões como "⚔️ ADEPTO ", "🟢 ", "⚠️ TURISTA "
        current_name = member.display_name
        
        # Remove prefixos conhecidos
        for p in RANK_STYLE.values():
            if p and current_name.startswith(p):
                current_name = current_name.replace(p, "").strip()
                break # Removeu um, para
        
        # Monta novo nome
        if prefix:
            new_nick = f"{prefix} {current_name}"
        else:
            new_nick = current_name # Sem rank (ex: staff ou bug)

        # Trunca para 32 caracteres (limite do Discord)
        if len(new_nick) > 32:
            # Tenta preservar o prefixo e cortar o nome
            allowed_len = 31 - len(prefix)
            if allowed_len > 0:
                new_nick = f"{prefix} {current_name[:allowed_len]}…"
            else:
                new_nick = new_nick[:32] # Prefixo gigante? Corta tudo.

        # Aplica apenas se mudou
        if member.display_name != new_nick:
            try: await member.edit(nick=new_nick)
            except: pass # Falta de permissão ou hierarquia

    @tasks.loop(hours=1)
    async def roles_check_loop(self):
        if not self.bot.guilds: return
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        if not guild: return

        valid_hours_data = await db.get_voice_hours(7)
        valid_hours_map = {r['user_id']: r['total_mins']/60 for r in valid_hours_data}
        
        monitoring_active = (datetime.datetime.now() - config.INACTIVITY_START_DATE).days >= 21
        
        # Cores dos Cargos
        colors = {
            "ADEPTO ⚔️": discord.Color.red(),
            "LENDA 💠": discord.Color.purple(), # Substitui Vanguarda
            "ATIVO": discord.Color.green(),     # Opcional se quiser cargo
            "TURISTA": discord.Color.light_grey()
        }

        # Remove cargo antigo Vanguarda se existir e ninguém mais usar
        old_role = discord.utils.get(guild.roles, name="VANGUARDA ⚡")
        # (Opcional: deletar ou deixar como legado)

        for member in guild.members:
            if member.bot: continue
            
            # --- CÁLCULO DE RANK ---
            h7 = valid_hours_map.get(member.id, 0)
            target_rank = 'TURISTA' # Base

            if member.get_role(config.ROLE_INATIVO):
                target_rank = 'INATIVO'
            elif member.get_role(config.ROLE_MESTRE_ID):
                target_rank = 'MESTRE' # Mestre tem imunidade visual
            else:
                # Hierarquia
                if h7 >= RANK_THRESHOLDS['MESTRE']: target_rank = 'MESTRE' # Caso bug do weekly
                elif h7 >= RANK_THRESHOLDS['ADEPTO']: target_rank = 'ADEPTO'
                elif h7 >= RANK_THRESHOLDS['LENDA']: target_rank = 'LENDA'
                elif h7 >= RANK_THRESHOLDS['ATIVO']: target_rank = 'ATIVO'
                elif h7 >= RANK_THRESHOLDS['TURISTA']: target_rank = 'TURISTA'
            
            # --- GERENCIAMENTO DE CARGOS ---
            # Removemos todos os cargos de rank "inferiores/conflitantes" para garantir apenas um
            # (Exceto Mestre que é gerenciado pelo weekly.py)
            if target_rank != 'MESTRE':
                # Remove Adepto se não for
                if target_rank != 'ADEPTO': await self.remove_role(member, "ADEPTO ⚔️")
                # Remove Lenda se não for
                if target_rank != 'LENDA': await self.remove_role(member, "LENDA 💠")
                # Remove Vanguarda (Legado)
                await self.remove_role(member, "VANGUARDA ⚡")

                # Aplica o novo
                if target_rank == 'ADEPTO': await self.apply_role(member, "ADEPTO ⚔️", colors["ADEPTO ⚔️"])
                elif target_rank == 'LENDA': await self.apply_role(member, "LENDA 💠", colors["LENDA 💠"])
                # Ativo e Turista geralmente não ganham cargos "Premium", mas se quiser, descomente:
                # elif target_rank == 'ATIVO': await self.apply_role(member, "ATIVO", colors["ATIVO"])

            # --- RENOMEAÇÃO (NICKNAME) ---
            # Staff (Fundador/Mod) geralmente não deve ser renomeado automaticamente para não bugar
            if not any(r.id in [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID] for r in member.roles):
                await self.update_nickname(member, target_rank)

            # --- ROLES DE COMPORTAMENTO (FDS, Presente, Inativo) ---
            # (Mantido código original abaixo)
            sessions_7d = await db.get_sessions_in_range(member.id, 7)
            sessions_21d = await db.get_sessions_in_range(member.id, 21)
            
            days_activity = {}
            for sess in sessions_7d:
                s_date = sess['start_time'].split()[0]
                days_activity[s_date] = days_activity.get(s_date, 0) + sess['duration_minutes']
            
            if sum(1 for mins in days_activity.values() if mins >= 60) >= 5:
                await self.apply_role(member, config.ROLE_PRESENTE_SEMPRE)
            else:
                await self.remove_role(member, config.ROLE_PRESENTE_SEMPRE)

            total_mins_7d = sum(days_activity.values())
            unique_days = len(days_activity)
            # Regra Turista Role (Comportamental) != Rank Turista (Horas)
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

            # Inativo Logic
            if monitoring_active:
                last_seen_raw = await db.get_last_activity_timestamp(member.id)
                is_inactive = False
                if last_seen_raw:
                    try:
                        last_seen = datetime.datetime.fromisoformat(str(last_seen_raw))
                        if last_seen.tzinfo is None: last_seen = last_seen.replace(tzinfo=None)
                        diff = (datetime.datetime.now() - last_seen).days
                        if diff >= 21: is_inactive = True
                    except: pass
                
                if is_inactive:
                    if not member.get_role(config.ROLE_INATIVO):
                        await self.apply_role(member, config.ROLE_INATIVO) # ID no config
                        try:
                            await member.send("⚠️ **Aviso:** Inatividade detectada (3 semanas).")
                        except: pass
                else:
                    await self.remove_role(member, config.ROLE_INATIVO)

    @tasks.loop(hours=24)
    async def db_cleanup_loop(self):
        await db.prune_old_voice_data(90)

    @roles_check_loop.before_loop
    async def before_roles(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RolesManager(bot))
