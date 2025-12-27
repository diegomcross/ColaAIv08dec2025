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
        await self.bot.wait_until_ready()
        print("[ROLES] Iniciando sincronização (Modo Seguro - Delay 2.0s)...")
        self.bot.loop.create_task(self.sync_member_ranks())

    async def sync_member_ranks(self):
        if not self.bot.guilds: return
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        if not guild: return

        valid_hours_data = await db.get_voice_hours(7)
        valid_hours_map = {r['user_id']: r['total_mins']/60 for r in valid_hours_data}
        
        staff_roles = [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID, config.ROLE_ADMIN_ID]

        # Mapeamento de Rank -> ID do Cargo
        rank_to_id = {
            'LENDA': config.ROLE_LENDA_ID,
            'ADEPTO': config.ROLE_ADEPTO_ID,
            'ATIVO': config.ROLE_ATIVO_ID,
            'TURISTA': config.ROLE_TURISTA_ID,
            'INATIVO': config.ROLE_INATIVO_ID
        }

        for member in guild.members:
            if member.bot: continue
            
            await asyncio.sleep(2.0) # Rate Limit Protection

            if any(r.id in staff_roles for r in member.roles):
                continue

            h7 = valid_hours_map.get(member.id, 0)
            target_rank = self.get_target_rank(member, h7)
            
            # 1. Atualizar Nome
            await self.update_nickname(member, target_rank)

            # 2. Atualizar Cargos
            if target_rank != 'MESTRE':
                # Remove cargos que NÃO são o alvo
                for r_key, r_id in rank_to_id.items():
                    if r_key != target_rank and r_id:
                        role = guild.get_role(r_id)
                        if role and role in member.roles:
                            try: await member.remove_roles(role)
                            except: pass
                
                # Adiciona o cargo alvo
                target_role_id = rank_to_id.get(target_rank)
                if target_role_id:
                    role = guild.get_role(target_role_id)
                    if role and role not in member.roles:
                        try: await member.add_roles(role)
                        except: pass

            # 3. Comportamento
            await self.check_behavior_roles(member)

    async def check_behavior_roles(self, member):
        # Presente Sempre
        sessions_7d = await db.get_sessions_in_range(member.id, 7)
        days_activity = {}
        for sess in sessions_7d:
            try: s_date = sess['start_time'].split()[0]
            except: continue
            days_activity[s_date] = days_activity.get(s_date, 0) + sess['duration_minutes']
        
        presente_role = member.guild.get_role(config.ROLE_PRESENTE_SEMPRE)
        if presente_role:
            if sum(1 for mins in days_activity.values() if mins >= 60) >= 5:
                if presente_role not in member.roles:
                    try: await member.add_roles(presente_role)
                    except: pass
            else:
                if presente_role in member.roles:
                    try: await member.remove_roles(presente_role)
                    except: pass

    async def update_nickname(self, member, rank_key):
        if member.id == member.guild.owner_id: return
        
        prefix = RANK_STYLE.get(rank_key, "")
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
        if member.get_role(config.ROLE_INATIVO_ID): return 'INATIVO'
        if member.get_role(config.ROLE_MESTRE_ID): return 'MESTRE'
        if h7 >= RANK_THRESHOLDS['LENDA']: return 'LENDA'
        if h7 >= RANK_THRESHOLDS['ADEPTO']: return 'ADEPTO'
        if h7 >= RANK_THRESHOLDS['ATIVO']: return 'ATIVO'
        return 'TURISTA'

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
