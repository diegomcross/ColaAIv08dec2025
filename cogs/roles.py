import discord
from discord.ext import commands, tasks
import database as db
import config
import datetime
from constants import BR_TIMEZONE, RANK_THRESHOLDS

class RolesManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.roles_check_loop.start()
        self.db_cleanup_loop.start()

    def cog_unload(self):
        self.roles_check_loop.cancel()
        self.db_cleanup_loop.cancel()

    async def apply_role(self, member, role_id):
        """Adiciona cargo se não tiver."""
        if not member.get_role(role_id):
            role = member.guild.get_role(role_id)
            if role: 
                try: await member.add_roles(role)
                except: pass

    async def remove_role(self, member, role_id):
        """Remove cargo se tiver."""
        if member.get_role(role_id):
            role = member.guild.get_role(role_id)
            if role:
                try: await member.remove_roles(role)
                except: pass

    async def ensure_cosmetic_roles_exist(self, guild):
        """Cria os cargos estéticos secundários se não existirem."""
        # Mestre agora é fixo pelo ID no config, então não criamos automaticamente pelo nome
        needed = {
            "ADEPTO ⚔️": discord.Color.red(),
            "VANGUARDA ⚡": discord.Color.blue()
        }
        for name, color in needed.items():
            found = discord.utils.get(guild.roles, name=name)
            if not found:
                try: await guild.create_role(name=name, color=color, hover=True, reason="Auto-Criação ColaAI")
                except: pass

    async def manage_cosmetic_ranks(self, member, hours_7d):
        """Gerencia Mestre, Adepto, Vanguarda (baseado em horas válidas)."""
        guild = member.guild
        
        # Busca Cargo Mestre pelo ID Fixo
        r_mestre = guild.get_role(config.ROLE_MESTRE_ID)
        
        # Busca outros por nome (ou IDs se configurado futuramente)
        r_adepto = discord.utils.get(guild.roles, name="ADEPTO ⚔️")
        r_vanguarda = discord.utils.get(guild.roles, name="VANGUARDA ⚡")

        # IDs para facilitar remoção
        id_mestre = r_mestre.id if r_mestre else config.ROLE_MESTRE_ID
        id_adepto = r_adepto.id if r_adepto else 0
        id_vanguarda = r_vanguarda.id if r_vanguarda else 0

        # Remove todos primeiro (para garantir exclusividade do maior rank)
        if r_mestre: await self.remove_role(member, id_mestre)
        if r_adepto: await self.remove_role(member, id_adepto)
        if r_vanguarda: await self.remove_role(member, id_vanguarda)

        target_role_id = None
        if hours_7d >= RANK_THRESHOLDS['MESTRE']: target_role_id = id_mestre
        elif hours_7d >= RANK_THRESHOLDS['ADEPTO']: target_role_id = id_adepto
        elif hours_7d >= RANK_THRESHOLDS['VANGUARDA']: target_role_id = id_vanguarda

        if target_role_id:
            await self.apply_role(member, target_role_id)

    @tasks.loop(hours=1)
    async def roles_check_loop(self):
        """Loop principal de verificação de comportamento."""
        if not self.bot.guilds: return
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        if not guild: return

        await self.ensure_cosmetic_roles_exist(guild)
        
        # Dados de Ranking (Valid=1) para cargos cosméticos
        valid_hours_data = await db.get_voice_hours(7)
        valid_hours_map = {r['user_id']: r['total_mins']/60 for r in valid_hours_data}

        # Trava de Segurança para Inativos
        monitoring_active = (datetime.datetime.now() - config.INACTIVITY_START_DATE).days >= 21
        
        for member in guild.members:
            if member.bot: continue
            
            # 1. CARGOS ESTÉTICOS (Baseado em horas válidas)
            h7_valid = valid_hours_map.get(member.id, 0)
            await self.manage_cosmetic_ranks(member, h7_valid)

            # 2. ANÁLISE DE COMPORTAMENTO (Baseado em TODAS as sessões)
            sessions_7d = await db.get_sessions_in_range(member.id, 7)
            sessions_21d = await db.get_sessions_in_range(member.id, 21)
            
            # A. PRESENTE SEMPRE (>1h/dia, 5 dias/sem)
            days_activity = {}
            for sess in sessions_7d:
                s_date = sess['start_time'].split()[0]
                days_activity[s_date] = days_activity.get(s_date, 0) + sess['duration_minutes']
            
            days_above_1h = sum(1 for mins in days_activity.values() if mins >= 60)
            
            if days_above_1h >= 5:
                await self.apply_role(member, config.ROLE_PRESENTE_SEMPRE)
            else:
                await self.remove_role(member, config.ROLE_PRESENTE_SEMPRE)

            # B. TURISTA (1 ou 2 dias/sem, total > 1h)
            total_mins_7d = sum(days_activity.values())
            unique_days = len(days_activity)
            
            if unique_days > 0 and unique_days <= 2 and total_mins_7d >= 60:
                await self.apply_role(member, config.ROLE_TURISTA)
            else:
                await self.remove_role(member, config.ROLE_TURISTA)

            # C. GALERA DO FDS (Só Sex/Sab/Dom nos ultimos 21 dias)
            is_fds_player = False
            if sessions_21d:
                weekday_mins = 0
                weekend_mins = 0
                for sess in sessions_21d:
                    try: st = datetime.datetime.fromisoformat(str(sess['start_time']))
                    except: continue
                    
                    if st.weekday() in [4, 5, 6]: weekend_mins += sess['duration_minutes']
                    else: weekday_mins += sess['duration_minutes']
                
                if weekday_mins < 30 and weekend_mins >= 60:
                    is_fds_player = True
            
            if is_fds_player:
                await self.apply_role(member, config.ROLE_GALERA_FDS)
            else:
                await self.remove_role(member, config.ROLE_GALERA_FDS)

            # D. INATIVO (21 dias sem nada)
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
                        await self.apply_role(member, config.ROLE_INATIVO)
                        try:
                            await member.send("⚠️ **Aviso de Inatividade:** Você não participa de atividades há 3 semanas e foi marcado como Inativo.")
                            channel_main = guild.get_channel(config.CHANNEL_MAIN_CHAT)
                            if channel_main:
                                await channel_main.send(f"💤 O membro {member.mention} foi marcado como **Inativo** (21 dias ausente).")
                        except: pass
                else:
                    await self.remove_role(member, config.ROLE_INATIVO)

    @tasks.loop(hours=24)
    async def db_cleanup_loop(self):
        """Limpa logs de voz com mais de 90 dias."""
        await db.prune_old_voice_data(90)

    @roles_check_loop.before_loop
    async def before_roles(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RolesManager(bot))
