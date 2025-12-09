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
        self.polls_management_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()
        self.reminders_loop.cancel()
        self.channel_rename_loop.cancel()
        self.polls_management_loop.cancel()

    @tasks.loop(minutes=15)
    async def polls_management_loop(self):
        """Gerencia enquetes: expira após 24h, notifica a cada 8h, renomeia canal."""
        active_polls = await db.get_active_polls()
        now = datetime.datetime.now(BR_TIMEZONE)
        
        has_new_polls = False
        
        # Lista para manter polls que ainda estão válidas para contagem
        valid_polls_count = 0

        for poll in active_polls:
            created_at_str = poll['created_at']
            try:
                created_at = datetime.datetime.fromisoformat(created_at_str)
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=datetime.timezone.utc).astimezone(BR_TIMEZONE)
            except:
                continue

            diff = now - created_at
            
            # 1. Expirar após 24h
            if diff.total_seconds() > 86400: # 24 horas
                await db.close_poll(poll['message_id'])
                try:
                    channel = self.bot.get_channel(poll['channel_id'])
                    if channel:
                        msg = await channel.fetch_message(poll['message_id'])
                        await msg.delete() # Apaga a mensagem se expirou (opcional, ou pode editar para "Encerrada")
                        # Se preferir manter a mensagem avisando que expirou, use:
                        # await msg.edit(view=None, content="🔒 Esta enquete expirou após 24h sem atingir a meta.")
                except: pass
                continue
            else:
                valid_polls_count += 1
                has_new_polls = True

            # 2. Notificação a cada 8h
            hours_passed = int(diff.total_seconds() / 3600)
            # Verifica se passou pelo menos 1 hora, se é múltiplo de 8, e se estamos no "começo" dessa hora (para não spammar)
            if hours_passed > 0 and hours_passed % 8 == 0 and diff.total_seconds() % 3600 < 900:
                main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
                poll_channel = self.bot.get_channel(poll['channel_id'])
                if main_chat and poll_channel:
                    txt = "Há enquetes em aberto esperando seu voto!"
                    if poll['poll_type'] == 'when':
                        txt = f"Ainda estamos decidindo o horário para **{poll['target_data']}**!"
                    await main_chat.send(f"🔔 {txt} Corre lá: {poll_channel.mention}")

        # 3. Renomear Canal de Enquetes
        try:
            poll_channel = self.bot.get_channel(config.CHANNEL_POLLS)
            if poll_channel:
                # Lógica solicitada:
                # Sem enquetes vigentes -> 📢crie uma enquete
                # Com enquetes vigentes -> responda a enquete‼️
                if valid_polls_count > 0:
                    new_name = "responda-a-enquete‼️"
                else:
                    new_name = "📢crie-uma-enquete"
                
                # Só edita se o nome for diferente para evitar API spam
                if poll_channel.name != new_name:
                    await poll_channel.edit(name=new_name)
        except Exception as e:
            pass

    @tasks.loop(minutes=5)
    async def cleanup_loop(self):
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        for event in events:
            try:
                if isinstance(event['date_time'], str):
                    evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
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
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                free_slots = max(0, event['max_slots'] - confirmed_count)
                new_name = utils.generate_channel_name(event['title'], evt_time, event['activity_type'], free_slots, description=event['description'])
                if channel.name != new_name: await channel.edit(name=new_name)
            except: pass

    @tasks.loop(minutes=1)
    async def reminders_loop(self):
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        for event in events:
            try:
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
            except: continue
            diff = evt_time - now
            if datetime.timedelta(minutes=59) <= diff <= datetime.timedelta(minutes=61):
                try:
                    guild = self.bot.get_guild(event['guild_id'])
                    if not guild: continue
                    channel = guild.get_channel(event['channel_id'])
                    role = guild.get_role(event['role_id'])
                    if channel and role: await channel.send(f"{role.mention} ⏰ O evento começa em 1 hora! Preparem-se.")
                except: pass

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TasksCog(bot))
