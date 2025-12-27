import discord
from discord.ext import commands, tasks
import database as db
import config
import datetime
import asyncio
from constants import BR_TIMEZONE, RANK_THRESHOLDS, RANK_STYLE
import utils

class RolesManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sync_loop.start()
        self.db_cleanup_loop.start()

    def cog_unload(self):
        self.sync_loop.cancel()
        self.db_cleanup_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Força atualização de cargos e nomes assim que o bot liga."""
        await self.bot.wait_until_ready()
        print("[ROLES] Iniciando sincronização (Modo Seguro - Delay 2.0s)...")
        # Roda em background para não bloquear o bot
        asyncio.create_task(self.sync_member_ranks())

    async def sync_member_ranks(self):
        if not self.bot.guilds: return
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        if not guild: return

        valid_hours_data = await db.get_voice_hours(7)
        valid_hours_map = {r['user_id']: r['total_mins']/60 for r in valid_hours_data}
        
        colors = {
            "ADEPTO ✨": discord.Color.red(),
            "LENDA ⚡": discord.Color.purple()
        }

        staff_roles = [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID, config.ROLE_ADMIN_ID]

        for member in guild.members:
            if member.bot: continue
            
            # --- CRÍTICO: DELAY ALTO PARA EVITAR 429 ---
            await asyncio.sleep(2.0)

            # Ignora Staff
            if any(r.id in staff_roles for r in member.roles):
                await self.remove_role(member, "ADEPTO ✨")
                await self.remove_role(member, "LENDA ⚡")
                continue

            h7 = valid_hours_map.get(member.id, 0)
            target_rank = self.get_target_rank(member, h7)
            
            # 1. ATUALIZAR NOME (Com Limpeza Profunda)
            await self.update_nickname(member, target_rank)

            # 2. ATUALIZAR CARGOS
            if target_rank != 'MESTRE':
                # Remove incorretos
                if target_rank != 'ADEPTO': await self.remove_role(member, "ADEPTO ✨")
                if target_rank != 'LENDA': await self.remove_role(member, "LENDA ⚡")
                
                # Limpa legados
                await self.remove_role(member, "ADEPTO ⚔️")
                await self.remove_role(member, "VANGUARDA ⚡")
                await self.remove_role(member, "LENDA 💠")

                # Aplica novo
                if target_rank == 'ADEPTO': await self.apply_role(member, "ADEPTO ✨", colors["ADEPTO ✨"])
                elif target_rank == 'LENDA': await self.apply_role(member, "LENDA ⚡", colors["LENDA ⚡"])

            # 3. COMPORTAMENTO
            await self.check_behavior_roles(member)

    async def check_behavior_roles(self, member):
        sessions_7d = await db.get_sessions_in_range(member.id, 7)
        days_activity = {}
        for sess in sessions_7d:
            try: s_date = sess['start_time'].split()[0]
            except: continue
            days_activity[s_date] = days_activity.get(s_date, 0) + sess['duration_minutes']
        
        if sum(1 for mins in days_activity.values() if mins >= 60) >= 5:
            await self.apply_role(member, "Presente Sempre", discord.Color.green())
        else:
            await self.remove_role(member, "Presente Sempre")

        monitoring_active = (datetime.datetime.now() - config.INACTIVITY_START_DATE).days >= 21
        if monitoring_active:
            last_seen = await db.get_last_activity_timestamp(member.id)
            if last_seen:
                try:
                    dt = datetime.datetime.fromisoformat(str(last_seen))
                    if dt.tzinfo is None: dt = dt.replace(tzinfo=None)
                    if (datetime.datetime.now() - dt).days >= 21:
                        if not member.get_role(config.ROLE_INATIVO):
                            await self.apply_role(member, "Inativo", discord.Color.dark_grey())
                            try: await member.send("⚠️ **Aviso:** Inatividade detectada.")
                            except: pass
                    else:
                        await self.remove_role(member, "Inativo")
                except: pass

    async def update_nickname(self, member, rank_key):
        if member.id == member.guild.owner_id: return
        
        prefix = RANK_STYLE.get(rank_key, "")
        
        # Limpa TUDO antes de aplicar o novo
        clean_current = utils.strip_rank_prefix(member.display_name)
        
        if prefix: new_nick = f"{prefix} {clean_current}"
        else: new_nick = clean_current

        if len(new_nick) > 32:
            allowed = 31 - len(prefix)
            if allowed > 0: new_nick = f"{prefix} {clean_current[:allowed]}…"
            else: new_nick = new_nick[:32]

        if member.display_name != new_nick:
            try: await member.edit(nick=new_nick)
            except: pass

    def get_target_rank(self, member, h7):
        if member.get_role(config.ROLE_INATIVO): return 'INATIVO'
        if member.get_role(config.ROLE_MESTRE_ID): return 'MESTRE'
        
        if h7 >= RANK_THRESHOLDS['LENDA']: return 'LENDA'
        if h7 >= RANK_THRESHOLDS['ADEPTO']: return 'ADEPTO'
        if h7 >= RANK_THRESHOLDS['ATIVO']: return 'ATIVO'
        return 'TURISTA'

    async def apply_role(self, member, role_name, color):
        guild = member.guild
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            try: role = await guild.create_role(name=role_name, color=color, hover=True, reason="Auto-Criação")
            except: return
        if role and role not in member.roles:
            try: await member.add_roles(role)
            except: pass

    async def remove_role(self, member, role_name):
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role and role in member.roles:
            try: await member.remove_roles(role)
            except: pass

    @tasks.loop(hours=1)
    async def sync_loop(self):
        await self.bot.wait_until_ready()
        await self.sync_member_ranks()

    @tasks.loop(hours=24)
    async def db_cleanup_loop(self):
        await db.prune_old_voice_data(90)

    @sync_loop.before_loop
    async def before_roles(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RolesManager(bot))
