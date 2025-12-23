import discord
from discord.ext import commands, tasks
import datetime
import random
import asyncio
import database as db
import utils
import config
from constants import BR_TIMEZONE
import quotes
import json
import os
from cogs.views_polls import VotingPollView

LORE_STATE_FILE = "lore_state.json"

class TasksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        self.cleanup_loop.start()
        self.reminders_loop.start()
        self.channel_rename_loop.start()
        self.daily_morning_loop.start()
        self.daily_lore_loop.start()
        self.attendance_monitor_loop.start()
        self.auto_survey_loop.start()
        
        if hasattr(self, 'polls_management_loop'): self.polls_management_loop.start()
        if hasattr(self, 'info_board_loop'): self.info_board_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()
        self.reminders_loop.cancel()
        self.channel_rename_loop.cancel()
        self.daily_morning_loop.cancel()
        self.daily_lore_loop.cancel()
        self.attendance_monitor_loop.cancel()
        self.auto_survey_loop.cancel()
        if hasattr(self, 'polls_management_loop'): self.polls_management_loop.cancel()
        if hasattr(self, 'info_board_loop'): self.info_board_loop.cancel()

    # --- ESTADO LORE ---
    def get_lore_index(self):
        if not os.path.exists(LORE_STATE_FILE): return 0
        try:
            with open(LORE_STATE_FILE, "r") as f: return json.load(f).get("next_index", 0)
        except: return 0

    def increment_lore_index(self):
        current = self.get_lore_index()
        with open(LORE_STATE_FILE, "w") as f: json.dump({"next_index": current + 1}, f)

    # --- LOOP: AUTO SURVEY (ENQUETE AUTOMÁTICA) ---
    @tasks.loop(time=datetime.time(hour=10, minute=0, tzinfo=BR_TIMEZONE))
    async def auto_survey_loop(self):
        await self.bot.wait_until_ready()
        
        now = datetime.datetime.now(BR_TIMEZONE)
        events = await db.get_active_events()
        
        has_event_soon = False
        limit_date = now + datetime.timedelta(days=3)
        
        for event in events:
            try:
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                
                if now < evt_time < limit_date:
                    has_event_soon = True
                    break
            except: continue
        
        if not has_event_soon:
            main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
            poll_channel = self.bot.get_channel(config.CHANNEL_POLLS)
            
            if main_chat and poll_channel:
                from constants import RAID_INFO_PT
                all_raids = list(RAID_INFO_PT.keys())
                options = random.sample(all_raids, min(4, len(all_raids)))
                
                options_list = []
                desc_lines = []
                for i, opt in enumerate(options):
                    options_list.append({'label': opt, 'value': opt})
                    desc_lines.append(f"{i+1}\ufe0f\u20e3 {opt}")
                
                desc_text = "\n".join(desc_lines)
                
                embed = discord.Embed(
                    title="📊 O Calendário está vazio!",
                    description=f"Nenhum evento agendado para os próximos 3 dias.\n**O que vocês querem jogar?**\n\n{desc_text}\n\n*Meta: 4 votos para agendar.*",
                    color=discord.Color.gold()
                )
                
                target_data = json.dumps({'date_str': 'hoje 21h', 'options': options_list})
                view = VotingPollView(self.bot, 'what', target_data, options_list)
                
                msg = await poll_channel.send(embed=embed, view=view)
                await db.create_poll(msg.id, poll_channel.id, main_chat.guild.id, 'what', target_data)
                
                await main_chat.send(f"⚠️ **Sem atividades à vista!** O bot sugeriu algumas Raids. Vote aqui: {msg.jump_url}")

    # --- LOOP: MANHÃ ---
    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=BR_TIMEZONE))
    async def daily_morning_loop(self):
        delay = random.randint(0, 3600) 
        await asyncio.sleep(delay)
        channel = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        if not channel: return
        quote = random.choice(quotes.MORNING_QUOTES)
        msg = (f"🌞 **Bom dia, Guardião!**\n\n{quote}\n\n>>> 🗓️ **Organize sua fireteam:** Use `/agendar`")
        await channel.send(msg)

    # --- LOOP: LORE ---
    @tasks.loop(time=datetime.time(hour=15, minute=0, tzinfo=BR_TIMEZONE))
    async def daily_lore_loop(self):
        delay = random.randint(0, 3600)
        await asyncio.sleep(delay)
        channel = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        if not channel: return
        idx = self.get_lore_index()
        if idx >= len(quotes.LORE_QUOTES): return
        quote = quotes.LORE_QUOTES[idx]
        await channel.send(f"{quote}")
        self.increment_lore_index()

    # --- LOOP: LEMBRETES E NOTIFICAÇÕES (24h, 4h, 1h) ---
    @tasks.loop(minutes=1)
    async def reminders_loop(self):
        await self.bot.wait_until_ready()
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        
        for event in events:
            try:
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                
                diff_minutes = (evt_time - now).total_seconds() / 60
                
                lifecycle = await db.get_event_lifecycle(event['event_id'])
                if not lifecycle:
                    await db.set_lifecycle_flag(event['event_id'], 'reminder_1h_sent', 0)
                    lifecycle = {'reminder_1h_sent': 0, 'reminder_4h_sent': 0, 'reminder_24h_sent': 0}

                guild = self.bot.get_guild(event['guild_id'])
                if not guild: continue
                
                rsvps = await db.get_rsvps(event['event_id'])
                confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
                slots = event['max_slots']
                has_slots = confirmed_count < slots
                
                main_chat = guild.get_channel(config.CHANNEL_MAIN_CHAT)
                event_channel = guild.get_channel(event['channel_id'])
                role = guild.get_role(event['role_id'])

                # 1. Notificação de 24h (aprox 1440 min)
                if 1430 <= diff_minutes <= 1450 and has_slots:
                     if not lifecycle.get('reminder_24h_sent'):
                         if main_chat:
                             await main_chat.send(f"📢 **Atenção Guardiões!**\nA atividade **{event['title']}** é amanhã! Ainda há **{slots - confirmed_count} vagas**. Garanta a sua em {event_channel.mention}")
                         await db.set_lifecycle_flag(event['event_id'], 'reminder_24h_sent', 1)

                # 2. Notificação de 4h (240 min)
                if 235 <= diff_minutes <= 245 and has_slots:
                    if not lifecycle.get('reminder_4h_sent'):
                        if main_chat:
                            await main_chat.send(f"📢 **Vagas Abertas!** A atividade **{event['title']}** começa em 4 horas e ainda tem {slots - confirmed_count} vagas! \nCorre lá: {event_channel.mention}")
                        await db.set_lifecycle_flag(event['event_id'], 'reminder_4h_sent', 1)

                # 3. Lembrete de 1h (Original + Promoção)
                if 50 <= diff_minutes <= 65:
                    if not lifecycle.get('reminder_1h_sent'):
                        if event_channel and role: 
                            await event_channel.send(f"{role.mention} ⏰ O evento começa em 1 hora! Preparem-se.")
                        
                        if has_slots and main_chat:
                            await main_chat.send(f"⚠️ **Última Chamada!** **{event['title']}** começa em 1h e precisa de gente! {event_channel.mention}")
                        
                        await db.set_lifecycle_flag(event['event_id'], 'reminder_1h_sent', 1)

            except Exception as e: continue

    # --- LOOP: MONITOR DE PRESENÇA E LOG ---
    @tasks.loop(minutes=5)
    async def attendance_monitor_loop(self):
        await self.bot.wait_until_ready()
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        
        for event in events:
            try:
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                
                diff_minutes = (now - evt_time).total_seconds() / 60
                
                guild = self.bot.get_guild(event['guild_id'])
                if not guild: continue
                channel = guild.get_channel(event['channel_id'])
                if not channel: continue

                # A. 40 MINUTOS: Check Final de Presença
                if 38 <= diff_minutes <= 45:
                    users_in_voice = [m.id for m in channel.members if not m.bot]
                    rsvps = await db.get_rsvps(event['event_id'])
                    confirmed_ids = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
                    
                    for uid in confirmed_ids:
                        if uid in users_in_voice:
                            await db.mark_attendance_present(event['event_id'], uid)
                        else:
                            current_status = await db.get_attendance_status(event['event_id'], uid)
                            if current_status != 'present':
                                print(f"[ATTENDANCE] User {uid} ausente em {event['title']}")

                # B. Monitoramento Contínuo
                if 0 <= diff_minutes <= 180:
                    users_in_voice = [m.id for m in channel.members if not m.bot]
                    confirmed_ids = [r['user_id'] for r in (await db.get_rsvps(event['event_id'])) if r['status'] == 'confirmed']
                    for uid in confirmed_ids:
                        if uid in users_in_voice: await db.mark_attendance_present(event['event_id'], uid)
                
            except Exception as e: print(f"[ATTENDANCE ERROR] Evento {event.get('event_id')}: {e}")

    @tasks.loop(minutes=5)
    async def info_board_loop(self):
        # (Código existente mantido)
        await self.bot.wait_until_ready()
        try:
            sched_channel = self.bot.get_channel(config.CHANNEL_SCHEDULE)
            if sched_channel:
                instr_msg = None
                list_msg = None
                async for msg in sched_channel.history(limit=20):
                    if msg.author == self.bot.user:
                        if msg.embeds and msg.embeds[0].title == "📅 Agendamento de Grades": instr_msg = msg
                        elif msg.embeds and msg.embeds[0].title == "📋 Próximas Atividades": list_msg = msg

                embed_instr = discord.Embed(title="📅 Agendamento de Grades", description="Veja abaixo os eventos já marcados.\n\n**Quer criar o seu?**\nUse o comando `/agendar` no bate-papo!", color=discord.Color.green())
                if not instr_msg: await sched_channel.send(embed=embed_instr)
                
                events = await db.get_active_events()
                valid_events = []
                for evt in events:
                    try:
                        if isinstance(evt['date_time'], str): dt = datetime.datetime.fromisoformat(evt['date_time'])
                        else: dt = evt['date_time']
                        if dt.tzinfo is None: dt = BR_TIMEZONE.localize(dt)
                        rsvps = await db.get_rsvps(evt['event_id'])
                        confirmed = len([r for r in rsvps if r['status'] == 'confirmed'])
                        valid_events.append({'dt': dt, 'title': evt['title'], 'slots': evt['max_slots'], 'confirmed': confirmed, 'channel_id': evt['channel_id']})
                    except: continue
                
                valid_events.sort(key=lambda x: x['dt'])
                if not valid_events: desc_list = "*Nenhum evento agendado no momento.*"
                else:
                    lines = []
                    for e in valid_events:
                        ts = int(e['dt'].timestamp())
                        free = max(0, e['slots'] - e['confirmed'])
                        status_emoji = "🟢" if free > 0 else "🔴"
                        chan_link = f"<#{e['channel_id']}>" if e['channel_id'] else "Canal deletado"
                        lines.append(f"{status_emoji} **<t:{ts}:d> <t:{ts}:t>** | {chan_link}\n└ **{e['title']}** ({free} vagas)")
                    desc_list = "\n\n".join(lines)

                embed_list = discord.Embed(title="📋 Próximas Atividades", description=desc_list, color=discord.Color.blue())
                embed_list.set_footer(text=f"Atualizado em {datetime.datetime.now(BR_TIMEZONE).strftime('%H:%M')}")
                if list_msg: await list_msg.edit(embed=embed_list)
                else: await sched_channel.send(embed=embed_list)
        except: pass

    @tasks.loop(minutes=15)
    async def polls_management_loop(self):
        # (Código existente mantido)
        pass

    @tasks.loop(minutes=5)
    async def cleanup_loop(self):
        # (Código existente mantido)
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        for event in events:
            try:
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
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
        # (Código existente mantido)
        events = await db.get_active_events()
        for event in events:
            try:
                guild = self.bot.get_guild(event['guild_id'])
                if not guild: continue
                channel = guild.get_channel(event['channel_id'])
                if not channel: continue
                rsvps = await db.get_rsvps(event['event_id'])
                confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                free_slots = max(0, event['max_slots'] - confirmed_count)
                new_name = utils.generate_channel_name(event['title'], evt_time, event['activity_type'], free_slots, description=event['description'])
                if channel.name != new_name: await channel.edit(name=new_name)
            except: pass

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TasksCog(bot))
