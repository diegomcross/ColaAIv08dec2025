import discord
from discord import app_commands
from discord.ext import commands, tasks
import database as db
import datetime
import asyncio
from constants import BR_TIMEZONE, RANK_THRESHOLDS, RANK_STYLE
import config
import utils

class RankingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_timers = {} 
        self.update_ranking_loop.start()

    def cog_unload(self):
        self.update_ranking_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        await asyncio.sleep(10)
        await self.update_ranking_board()

    @app_commands.command(name="forcar_ranking", description="Admin: Atualiza o Embed de Ranking.")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_ranking(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.update_ranking_board()
        await interaction.followup.send("✅ Ranking atualizado!", ephemeral=True)

    def check_validity_conditions(self, member):
        if member.bot: return False
        voice = member.voice
        if not voice or not voice.channel: return False
        if voice.self_mute or voice.self_deaf or voice.mute or voice.deaf: return False
        humans_in_channel = [m for m in voice.channel.members if not m.bot]
        if len(humans_in_channel) < 2: return False
        return True

    async def reconcile_session(self, member):
        user_id = member.id
        now = datetime.datetime.now(BR_TIMEZONE)
        is_in_voice = member.voice and member.voice.channel
        is_counting = user_id in self.active_timers

        if is_in_voice and not is_counting:
            self.active_timers[user_id] = now
        elif not is_in_voice and is_counting:
            start_time = self.active_timers.pop(user_id)
            duration = (now - start_time).total_seconds() / 60
            if duration >= 1:
                await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=0)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot:
            await self.reconcile_session(member)

    async def update_ranking_board(self):
        guild = self.bot.get_guild(self.bot.guilds[0].id) if self.bot.guilds else None
        if not guild: return

        now = datetime.datetime.now(BR_TIMEZONE)
        
        # 1. Sincroniza parciais
        for user_id, start_time in list(self.active_timers.items()):
            member = guild.get_member(user_id)
            if member and member.voice:
                duration = (now - start_time).total_seconds() / 60
                if duration >= 1:
                    valid = 1 if self.check_validity_conditions(member) else 0
                    await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=valid)
                    self.active_timers[user_id] = now

        # 2. Coleta dados (7 Dias)
        data_7d = await db.get_voice_hours(7)
        hours_map = {r['user_id']: r['total_mins']/60 for r in data_7d}
        
        all_members_data = []
        for member in guild.members:
            if member.bot: continue
            if any(r.id in [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID] for r in member.roles): continue

            # LÓGICA ATUALIZADA: Mestre Exclusivo por Cargo
            if member.get_role(config.ROLE_INATIVO):
                rank_key = 'INATIVO'
                h7 = 0
            elif member.get_role(config.ROLE_MESTRE_ID):
                # Somente quem tem o cargo vira Mestre aqui, independente das horas
                rank_key = 'MESTRE'
                h7 = hours_map.get(member.id, 0)
            else:
                h7 = hours_map.get(member.id, 0)
                # Removemos a verificação if h7 >= MESTRE. 
                # Se tiver 100 horas mas não tem cargo, cai no Adepto.
                if h7 >= RANK_THRESHOLDS['ADEPTO']: rank_key = 'ADEPTO'
                elif h7 >= RANK_THRESHOLDS['LENDA']: rank_key = 'LENDA'
                elif h7 >= RANK_THRESHOLDS['ATIVO']: rank_key = 'ATIVO'
                elif h7 >= RANK_THRESHOLDS['TURISTA']: rank_key = 'TURISTA'
                else: rank_key = 'TURISTA'

            display_title = RANK_STYLE.get(rank_key, "")
            clean_name = utils.clean_voter_name(member.display_name)
            
            all_members_data.append({
                'name': clean_name, 
                'h7': h7, 
                'rank_key': rank_key, 
                'display_title': display_title
            })

        all_members_data.sort(key=lambda x: x['h7'], reverse=True)

        ranks_config = {
            'MESTRE': [], 'ADEPTO': [], 'LENDA': [],
            'ATIVO': [], 'TURISTA': [], 'INATIVO': []
        }

        for p in all_members_data:
            k = p['rank_key']
            if k in ranks_config: ranks_config[k].append(p['name'])

        # 4. Construção do Embed
        embed = discord.Embed(title="🏆  QUADRO DE HONRA (7 Dias)", color=discord.Color.gold())
        
        masters = ranks_config['MESTRE']
        if masters:
            master_str = "\n".join([f"> 👑 **{name}**" for name in masters])
            embed.description = f"### {RANK_STYLE['MESTRE']}\n{master_str}"
        else:
            embed.description = f"### {RANK_STYLE['MESTRE']}\n> *O trono está vazio...*"

        mid_tiers = ['ADEPTO', 'LENDA']
        for key in mid_tiers:
            names = ranks_config[key]
            title = RANK_STYLE[key]
            value = "\n".join([f"`{n}`" for n in names]) if names else "*Vazio*"
            embed.add_field(name=f"{title} ({len(names)})", value=value, inline=True)
        
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        low_tiers = ['ATIVO', 'TURISTA', 'INATIVO']
        for key in low_tiers:
            names = ranks_config[key]
            title = RANK_STYLE[key]
            if names:
                formatted_names = [f"`{n}`" for n in names]
                value = ", ".join(formatted_names)
                if len(value) > 1000: value = value[:950] + "..."
            else: value = "*Ninguém*"
            embed.add_field(name=f"{title} ({len(names)})", value=value, inline=False)

        embed.add_field(name="⠀", value="🎙️ **Suba de Rank:** Entre em calls com grupo, áudio aberto e fale!", inline=False)
        if guild.icon: embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Atualizado às {now.strftime('%H:%M')} • Staff não listado")

        channel = guild.get_channel(config.CHANNEL_RANKING)
        if channel:
            try:
                last_msg = None
                async for msg in channel.history(limit=10):
                    if msg.author == self.bot.user: last_msg = msg; break
                if last_msg: await last_msg.edit(embed=embed)
                else: await channel.send(embed=embed)
            except: pass

    times_list = [datetime.time(hour=h, minute=m, tzinfo=BR_TIMEZONE) for h in range(24) for m in [0, 30]]
    @tasks.loop(time=times_list)
    async def update_ranking_loop(self):
        await self.bot.wait_until_ready()
        await self.update_ranking_board()

    @update_ranking_loop.before_loop
    async def before_ranking_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RankingCog(bot))
