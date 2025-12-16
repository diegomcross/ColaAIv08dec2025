import discord
from discord.ext import commands, tasks
import database as db
import config
import datetime
import random
import quotes
from constants import BR_TIMEZONE

class WeeklyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.friday_check_loop.start()

    def cog_unload(self):
        self.friday_check_loop.cancel()

    @tasks.loop(time=datetime.time(hour=18, minute=0, tzinfo=BR_TIMEZONE))
    async def friday_check_loop(self):
        now = datetime.datetime.now(BR_TIMEZONE)
        if now.weekday() == 4: # Sexta-feira
            await self.run_weekly_master_selection()
            await self.run_weekly_event_summary()

    async def run_weekly_master_selection(self):
        guild = self.bot.get_guild(self.bot.guilds[0].id) if self.bot.guilds else None
        if not guild: return

        data_7d = await db.get_voice_hours(7)
        sorted_data = sorted(data_7d, key=lambda x: x['total_mins'], reverse=True)
        recent_winners = await db.get_recent_masters(weeks=3)
        
        winner_id = None
        for entry in sorted_data:
            uid = entry['user_id']
            member = guild.get_member(uid)
            if not member: continue
            
            # Filtro Staff
            if any(r.id in [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID] for r in member.roles):
                continue
            # Filtro Cooldown
            if uid in recent_winners:
                continue
            
            winner_id = uid
            break
        
        if winner_id:
            winner = guild.get_member(winner_id)
            if winner:
                role_mestre = guild.get_role(config.ROLE_MESTRE_ID)
                if role_mestre:
                    # Limpa Mestre anterior
                    for m in role_mestre.members:
                        await m.remove_roles(role_mestre)
                    
                    await winner.add_roles(role_mestre)
                    await db.log_master_winner(winner_id)
                    
                    quote = random.choice(quotes.DESTINY_INSPIRATIONAL_QUOTES)
                    channel = guild.get_channel(config.CHANNEL_MAIN_CHAT)
                    
                    embed = discord.Embed(title="👑 Novo Mestre da Semana!", color=discord.Color.gold())
                    embed.description = (
                        f"O Viajante escolheu seu novo campeão.\n\n"
                        f"**Parabéns, {winner.mention}!**\n"
                        f"Você foi o Guardião mais dedicado da semana.\n\n"
                        f"❝ *{quote}* ❞"
                    )
                    embed.set_thumbnail(url=winner.display_avatar.url)
                    embed.set_footer(text="Este título é rotativo. Mantenha a chama acesa!")
                    
                    if channel: await channel.send(content=f"||{winner.mention}||", embed=embed)

    async def run_weekly_event_summary(self):
        guild = self.bot.get_guild(self.bot.guilds[0].id)
        if not guild: return
        channel = guild.get_channel(config.CHANNEL_MAIN_CHAT)
        if not channel: return

        stats = await db.get_event_stats_7d()
        if not stats: return

        top_creator = max(stats.items(), key=lambda x: x[1]['created'])
        top_joiner = max(stats.items(), key=lambda x: x[1]['participated'])
        
        if top_creator[1]['created'] == 0 and top_joiner[1]['participated'] == 0:
            return

        embed = discord.Embed(title="📊 Relatório de Operações da Vanguarda", color=discord.Color.blue())
        
        c_id, c_data = top_creator
        if c_data['created'] > 0:
            c_mem = guild.get_member(c_id)
            name = c_mem.display_name if c_mem else "Desconhecido"
            embed.add_field(name="🛠️ Arquiteto da Semana", value=f"**{name}** agendou **{c_data['created']}** atividades!", inline=False)

        j_id, j_data = top_joiner
        if j_data['participated'] > 0:
            j_mem = guild.get_member(j_id)
            name = j_mem.display_name if j_mem else "Desconhecido"
            embed.add_field(name="⚔️ Guardião Onipresente", value=f"**{name}** lutou em **{j_data['participated']}** missões!", inline=False)

        await channel.send(embed=embed)

    @friday_check_loop.before_loop
    async def before_friday(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(WeeklyCog(bot))
