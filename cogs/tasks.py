import discord
from discord.ext import commands, tasks
from discord import ui
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

class ProbationDecisionView(ui.View):
    def __init__(self, bot, member_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.member_id = member_id
    @ui.button(label="💀 Kick", style=discord.ButtonStyle.danger, custom_id="prob_kick")
    async def btn_kick(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        member = guild.get_member(self.member_id)
        if not member: return await interaction.followup.send("Membro já saiu.", ephemeral=True)
        try: await member.send(embed=discord.Embed(title="❌ Removido", description="Inatividade.", color=discord.Color.red()))
        except: pass
        try: await member.kick(reason="Probation"); await interaction.message.edit(content=f"💀 **{member.name}** kickado.", view=None, embed=None)
        except: await interaction.followup.send("Erro ao kickar.", ephemeral=True)
    @ui.button(label="🛡️ Keep", style=discord.ButtonStyle.success, custom_id="prob_keep")
    async def btn_keep(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        member = guild.get_member(self.member_id)
        if not member: return await interaction.followup.send("Membro não encontrado.", ephemeral=True)
        await db.extend_probation(self.member_id)
        try: await member.send(embed=discord.Embed(title="⚠️ Aviso", description="Segunda chance dada.", color=discord.Color.green()))
        except: pass
        await interaction.message.edit(content=f"🛡️ **{member.name}** salvo.", view=None, embed=None)

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
        self.probation_monitor_loop.start()
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
        self.probation_monitor_loop.cancel()
        if hasattr(self, 'polls_management_loop'): self.polls_management_loop.cancel()
        if hasattr(self, 'info_board_loop'): self.info_board_loop.cancel()

    def get_lore_index(self):
        if not os.path.exists(LORE_STATE_FILE): return 0
        try:
            with open(LORE_STATE_FILE, "r") as f: return json.load(f).get("next_index", 0)
        except: return 0
    def increment_lore_index(self):
        current = self.get_lore_index()
        with open(LORE_STATE_FILE, "w") as f: json.dump({"next_index": current + 1}, f)

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
                    has_event_soon = True; break
            except: continue
        if not has_event_soon:
            main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
            poll_channel = self.bot.get_channel(config.CHANNEL_POLLS)
            if main_chat and poll_channel:
                from constants import RAID_INFO_PT
                all_raids = list(RAID_INFO_PT.keys())
                options = random.sample(all_raids, min(4, len(all_raids)))
                options_list = [{'label': opt, 'value': opt} for opt in options]
                desc_lines = [f"{i+1}\ufe0f\u20e3 {opt}" for i, opt in enumerate(options)]
                embed = discord.Embed(title="📊 O Calendário está vazio!", description=f"O que vocês querem jogar?\n\n" + "\n".join(desc_lines), color=discord.Color.gold())
                target_data = json.dumps({'date_str': 'hoje 21h', 'options': options_list})
                view = VotingPollView(self.bot, 'what', target_data, options_list)
                msg = await poll_channel.send(embed=embed, view=view)
                await db.create_poll(msg.id, poll_channel.id, main_chat.guild.id, 'what', target_data)
                await main_chat.send(f"⚠️ **Sem atividades!** Vote aqui: {msg.jump_url}")

    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=BR_TIMEZONE))
    async def daily_morning_loop(self):
        delay = random.randint(0, 3600); await asyncio.sleep(delay)
        chan = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        if chan: await chan.send(f"🌞 **Bom dia!**\n\n{random.choice(quotes.MORNING_QUOTES)}")

    @tasks.loop(time=datetime.time(hour=15, minute=0, tzinfo=BR_TIMEZONE))
    async def daily_lore_loop(self):
        delay = random.randint(0, 3600); await asyncio.sleep(delay)
        chan = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        idx = self.get_lore_index()
        if chan and idx < len(quotes.LORE_QUOTES): await chan.send(f"{quotes.LORE_QUOTES[idx]}"); self.increment_lore_index()

    @tasks.loop(minutes=1)
    async def reminders_loop(self):
        await self.bot.wait_until_ready()
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        next_event = None
        min_diff = float('inf')

        for event in events:
            try:
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                diff_minutes = (evt_time - now).total_seconds() / 60
                
                if 0 < diff_minutes < min_diff:
                    min_diff = diff_minutes
                    next_event = (event['title'], diff_minutes)

                lifecycle = await db.get_event_lifecycle(event['event_id'])
                if not lifecycle: 
                    await db.set_lifecycle_flag(event['event_id'], 'reminder_1h_sent', 0)
                    lifecycle = {'reminder_1h_sent': 0, 'reminder_4h_sent': 0, 'reminder_24h_sent': 0, 'start_alert_sent': 0}

                guild = self.bot.get_guild(event['guild_id'])
                if not guild: continue
                rsvps = await db.get_rsvps(event['event_id'])
                confirmed_users = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
                maybe_users = [r['user_id'] for r in rsvps if r['status'] == 'maybe']
                slots = event['max_slots']
                has_slots = len(confirmed_users) < slots
                main_chat = guild.get_channel(config.CHANNEL_MAIN_CHAT)
                event_channel = guild.get_channel(event['channel_id'])
                role = guild.get_role(event['role_id'])

                if 1430 <= diff_minutes <= 1450 and has_slots:
                     if not lifecycle.get('reminder_24h_sent'):
                         if main_chat: await main_chat.send(f"📢 **Atenção Guardiões!**\nA atividade **{event['title']}** é amanhã! Ainda há vagas. {event_channel.mention}")
                         await db.set_lifecycle_flag(event['event_id'], 'reminder_24h_sent', 1)
                if 235 <= diff_minutes <= 245 and has_slots:
                    if not lifecycle.get('reminder_4h_sent'):
                        if main_chat: await main_chat.send(f"📢 **Vagas Abertas!** **{event['title']}** começa em 4h! {event_channel.mention}")
                        await db.set_lifecycle_flag(event['event_id'], 'reminder_4h_sent', 1)
                if 50 <= diff_minutes <= 65:
                    if not lifecycle.get('reminder_1h_sent'):
                        if event_channel and role: await event_channel.send(f"{role.mention} ⏰ O evento começa em 1 hora!")
                        if has_slots and main_chat: await main_chat.send(f"⚠️ **Última Chamada!** **{event['title']}** em 1h! {event_channel.mention}")
                        
                        targets = set(confirmed_users + maybe_users)
                        for uid in targets:
                            try:
                                member = guild.get_member(uid)
                                if member: await member.send(embed=discord.Embed(title=f"⏰ Lembrete: {event['title']}", description="Começa em **1 hora**.", color=discord.Color.orange()))
                            except: pass
                        await db.set_lifecycle_flag(event['event_id'], 'reminder_1h_sent', 1)
                if -2 <= diff_minutes <= 5:
                    if not lifecycle.get('start_alert_sent'):
                        for uid in confirmed_users:
                            try:
                                member = guild.get_member(uid)
                                if member: await member.send(embed=discord.Embed(title=f"🚀 Hora do Show: {event['title']}", description=f"A fireteam está reunindo!\n**Entre:** {event_channel.jump_url}", color=discord.Color.green()))
                            except: pass
                        await db.set_lifecycle_flag(event['event_id'], 'start_alert_sent', 1)
            except: continue

        try:
            if next_event:
                t, m = next_event
                ts = f"{int(m//60)}h" if m > 60 else f"{int(m)}m"
                await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{t} em {ts}"))
            else:
                await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.custom, name="🛡️ Patrulhando a Torre"))
        except: pass

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
                diff = (now - evt_time).total_seconds() / 60
                
                if 30 <= diff <= 210:
                    guild = self.bot.get_guild(event['guild_id'])
                    if not guild: continue
                    channel = guild.get_channel(event['channel_id'])
                    if not channel: continue
                    
                    voice_ids = {m.id for m in channel.members if not m.bot}
                    if not voice_ids: continue
                    
                    rsvps = await db.get_rsvps(event['event_id'])
                    confirmed_ids = {r['user_id'] for r in rsvps if r['status'] == 'confirmed'}
                    
                    if not confirmed_ids.intersection(voice_ids): continue
                    
                    valid_track = voice_ids.intersection(confirmed_ids)
                    for uid in valid_track:
                        await db.increment_event_attendance(event['event_id'], uid, 5)
            except: pass

    @tasks.loop(minutes=5)
    async def info_board_loop(self):
        await self.bot.wait_until_ready()
        try:
            sched_channel = self.bot.get_channel(config.CHANNEL_SCHEDULE)
            if sched_channel:
                instr_msg, list_msg = None, None
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
    async def polls_management_loop(self): pass

    @tasks.loop(minutes=5)
    async def cleanup_loop(self):
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        for event in events:
            try:
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
            except: continue
            
            if now > evt_time + datetime.timedelta(minutes=215):
                guild = self.bot.get_guild(event['guild_id'])
                if guild:
                    rsvps = await db.get_rsvps(event['event_id'])
                    confirmed_ids = {r['user_id'] for r in rsvps if r['status'] == 'confirmed'}
                    
                    valid_attendees = await db.get_valid_attendees(event['event_id'], min_minutes=60)
                    valid_set = set(valid_attendees)
                    
                    users_present = confirmed_ids.intersection(valid_set)
                    users_flake = confirmed_ids.difference(valid_set)

                    def format_clean(uids):
                        if not uids: return "Ninguém"
                        names = []
                        for uid in uids:
                            mem = guild.get_member(uid)
                            dname = utils.clean_voter_name(mem.display_name) if mem else f"ID {uid}"
                            names.append(f"`{dname}`")
                        return ", ".join(names)

                    log_channel = guild.get_channel(config.CHANNEL_EVENT_LOGS)
                    if log_channel:
                        embed = discord.Embed(title=f"📝 Relatório: {event['title']}", description=f"**Data:** {evt_time.strftime('%d/%m %H:%M')}\n**Critério:** RSVP + 60min na call.", color=discord.Color.blue())
                        embed.add_field(name=f"✅ Presentes ({len(users_present)})", value=format_clean(users_present), inline=False)
                        if users_flake: embed.add_field(name=f"❌ Faltas ({len(users_flake)})", value=format_clean(users_flake), inline=False)
                        await log_channel.send(embed=embed)
                    
                    try: 
                        c = guild.get_channel(event['channel_id'])
                        if c: await c.delete(reason="Fim")
                    except: pass
                    try:
                        r = guild.get_role(event['role_id'])
                        if r: await r.delete(reason="Fim")
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
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                free_slots = max(0, event['max_slots'] - confirmed_count)
                new_name = utils.generate_channel_name(event['title'], evt_time, event['activity_type'], free_slots, description=event['description'])
                if channel.name != new_name: await channel.edit(name=new_name)
            except: pass

    @tasks.loop(hours=24)
    async def probation_monitor_loop(self):
        await self.bot.wait_until_ready()
        log_channel = self.bot.get_channel(config.CHANNEL_EVENT_LOGS)
        if not log_channel: return
        guild = log_channel.guild
        now = datetime.datetime.now(datetime.timezone.utc)
        
        for member in guild.members:
            if member.bot: continue
            if member.joined_at < config.INACTIVITY_START_DATE.replace(tzinfo=datetime.timezone.utc): continue
            
            # FIX: Added ROLE_ADMIN_ID
            staff_roles = [config.ROLE_MOD_ID, config.ROLE_FOUNDER_ID, config.ROLE_ADMIN_ID]
            if any(r.id in staff_roles for r in member.roles): continue
            
            days = (now - member.joined_at).days
            if days < 4: continue
            if await db.is_probation_extended(member.id): continue
            if await db.get_last_activity_timestamp(member.id): continue
            
            try:
                embed = discord.Embed(title="⚠️ Probation Alert", description=f"**Membro:** {member.mention} (`{member.name}`)\n**Dias:** {days}\n**Status:** Sem atividade.", color=discord.Color.gold())
                # Removed dangerous local import
                await log_channel.send(embed=embed, view=ProbationDecisionView(self.bot, member.id))
            except: pass

    @cleanup_loop.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(TasksCog(bot))
