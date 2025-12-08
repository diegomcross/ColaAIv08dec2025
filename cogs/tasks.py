import discord
from discord.ext import commands, tasks
import datetime
import database as db
import utils
import config
from constants import BR_TIMEZONE

class TasksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_loop.start()
        self.reminders_loop.start()
        self.channel_rename_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()
        self.reminders_loop.cancel()
        self.channel_rename_loop.cancel()

    @tasks.loop(minutes=5)
    async def cleanup_loop(self):
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        
        for event in events:
            try:
                if isinstance(event['date_time'], str):
                    evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else:
                    evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
            except: continue

            if now > evt_time + datetime.timedelta(hours=1):
                guild = self.bot.get_guild(event['guild_id'])
                if guild:
                    log_channel = guild.get_channel(config.CHANNEL_EVENT_LOGS)
                    if log_channel:
                        try:
                            rsvps = await db.get_rsvps(event['event_id'])
                            confirmed = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
                            names = [f"<@{uid}>" for uid in confirmed]
                            await log_channel.send(f"**Evento Concluído:** {event['title']}\n**Data:** {evt_time.strftime('%d/%m %H:%M')}\n**Participantes:** {', '.join(names) if names else 'Ninguém'}")
                        except: pass

                    try:
                        channel = guild.get_channel(event['channel_id'])
                        if channel: await channel.delete(reason="Evento Expirado")
                    except: pass

                    try:
                        role = guild.get_role(event['role_id'])
                        if role: await role.delete(reason="Evento Expirado")
                    except: pass
                
                await db.update_event_status(event['event_id'], 'completed')

    # --- ATUALIZAÇÃO DE VAGAS/NOMES (15 min para evitar bloqueio) ---
    @tasks.loop(minutes=15)
    async def channel_rename_loop(self):
        events = await db.get_active_events()
        for event in events:
            try:
                guild = self.bot.get_guild(event['guild_id'])
                if not guild: continue
                channel = guild.get_channel(event['channel_id'])
                if not channel: continue
                
                rsvps = await db.get_rsvps(event['event_id'])
                confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
                
                if isinstance(event['date_time'], str):
                    evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else:
                    evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)

                free_slots = max(0, event['max_slots'] - confirmed_count)
                
                # Gera o nome atualizado (com vagas corretas)
                new_name = utils.generate_channel_name(event['title'], evt_time, event['activity_type'], free_slots, description=event['description'])
                
                if channel.name != new_name:
                    await channel.edit(name=new_name)
            except Exception as e:
                # Se der erro (ex: Rate Limit), ignora e tenta na próxima rodada
                pass

    @tasks.loop(minutes=1)
    async def reminders_loop(self):
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        for event in events:
            try:
                if isinstance(event['date_time'], str):
                    evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else:
                    evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
            except: continue

            diff = evt_time - now
            if datetime.timedelta(minutes=59) <= diff <= datetime.timedelta(minutes=61):
                try:
                    guild = self.bot.get_guild(event['guild_id'])
                    if not guild: continue
                    channel = guild.get_channel(event['channel_id'])
                    role = guild.get_role(event['role_id'])
                    if channel and role:
                        await channel.send(f"{role.mention} ⏰ O evento começa em 1 hora! Preparem-se.")
                except: pass

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TasksCog(bot))
