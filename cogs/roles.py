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
        """Cria os cargos estéticos se não existirem."""
        needed = {
            "MESTRE ⭐": discord.Color.gold(),
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
        r_mestre = discord.utils.get(guild.roles, name="MESTRE ⭐")
        r_adepto = discord.utils.get(guild.roles, name="ADEPTO ⚔️")
        r_vanguarda = discord.utils.get(guild.roles, name="VANGUARDA ⚡")

        # Remove todos primeiro (para garantir exclusividade do maior rank)
        if r_mestre: await self.remove_role(member, r_mestre.id)
        if r_adepto: await self.remove_role(member, r_adepto.id)
        if r_vanguarda: await self.remove_role(member, r_vanguarda.id)

        target_role = None
        if hours_7d >= RANK_THRESHOLDS['MESTRE']: target_role = r_mestre
        elif hours_7d >= RANK_THRESHOLDS['ADEPTO']: target_role = r_adepto
        elif hours_7d >= RANK_THRESHOLDS['VANGUARDA']: target_role = r_vanguarda

        if target_role:
            await self.apply_role(member, target_role.id)

    @tasks.loop(hours=1)
    async def roles_check_loop(self):
        """Loop principal de verificação de comportamento."""
        guild = self.bot.get_guild(self.bot.guilds[0].id) if self.bot.guilds else None
        if not guild: return

        await self.ensure_cosmetic_roles_exist(guild)
        
        # Carrega dados de 21 dias (necessário para FDS/Inativo)
        # Nota: Para 'ranking estético' usamos get_voice_hours(7) que filtra is_valid=1
        # Para comportamento, usamos get_sessions_in_range que pega TUDO.
        
        valid_hours_data = await db.get_voice_hours(7)
        valid_hours_map = {r['user_id']: r['total_mins']/60 for r in valid_hours_data}

        now = datetime.datetime.now(BR_TIMEZONE)
        
        # Trava de Segurança para Inativos (21 dias após deploy)
        # Defina a data de hoje como start se não quiser usar config fixa
        start_monitor_date = datetime.datetime.now() # Na prática, use a data de deploy
        # Se quiser fixar: datetime.datetime(2023, 12, 11)
        
        for member in guild.members:
            if member.bot: continue
            
            # 1. CARGOS ESTÉTICOS (Baseado em horas válidas)
            h7_valid = valid_hours_map.get(member.id, 0)
            await self.manage_cosmetic_ranks(member, h7_valid)

            # 2. ANÁLISE DE COMPORTAMENTO (Baseado em todas as sessões)
            sessions_7d = await db.get_sessions_in_range(member.id, 7)
            sessions_21d = await db.get_sessions_in_range(member.id, 21)
            
            # A. PRESENTE SEMPRE (>1h/dia, 5 dias/sem)
            # Agrupa minutos por dia
            days_activity = {}
            for sess in sessions_7d:
                s_date = sess['start_time'].split()[0] # YYYY-MM-DD
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
            # Analisa padrão
            is_fds_player = False
            if sessions_21d:
                weekday_mins = 0
                weekend_mins = 0
                for sess in sessions_21d:
                    # Converte string ISO para datetime se necessário
                    try: st = datetime.datetime.fromisoformat(str(sess['start_time']))
                    except: continue
                    
                    # 0=Seg, 4=Sex, 5=Sab, 6=Dom
                    if st.weekday() in [4, 5, 6]: weekend_mins += sess['duration_minutes']
                    else: weekday_mins += sess['duration_minutes']
                
                # Regra: Quase nada na semana (<30min em 21 dias) e Ativo no FDS (>1h)
                if weekday_mins < 30 and weekend_mins >= 60:
                    is_fds_player = True
            
            if is_fds_player:
                await self.apply_role(member, config.ROLE_GALERA_FDS)
            else:
                await self.remove_role(member, config.ROLE_GALERA_FDS)

            # D. INATIVO (21 dias sem nada)
            # Só executa se o bot já roda há 21 dias (segurança)
            # Como não temos persistência da data de install, usamos a lógica:
            # Se last_activity for None ou muito antiga.
            last_seen_raw = await db.get_last_activity_timestamp(member.id)
            
            # Se nunca foi visto, assumimos que é ativo (para não banir quem acabou de entrar ou antes do bot existir)
            # A menos que tenhamos certeza.
            if last_seen_raw:
                try:
                    last_seen = datetime.datetime.fromisoformat(str(last_seen_raw))
                    if last_seen.tzinfo is None: last_seen = last_seen.replace(tzinfo=None) # Comparar naive
                    
                    diff = (datetime.datetime.now() - last_seen).days
                    if diff >= 21:
                        # Adiciona cargo Inativo se não tiver
                        if not member.get_role(config.ROLE_INATIVO):
                            await self.apply_role(member, config.ROLE_INATIVO)
                            try:
                                await member.send("⚠️ **Aviso de Inatividade:** Você não participa de atividades há 3 semanas e foi marcado como Inativo.")
                                channel_main = guild.get_channel(config.CHANNEL_MAIN_CHAT)
                                if channel_main:
                                    await channel_main.send(f"💤 O membro {member.mention} foi marcado como **Inativo** (21 dias ausente).")
                            except: pass
                    else:
                        # Se voltou, tira o cargo
                        await self.remove_role(member, config.ROLE_INATIVO)
                except: pass

    @tasks.loop(hours=24)
    async def db_cleanup_loop(self):
        """Limpa logs de voz com mais de 90 dias."""
        await db.prune_old_voice_data(90)

    @roles_check_loop.before_loop
    async def before_roles(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RolesManager(bot))
