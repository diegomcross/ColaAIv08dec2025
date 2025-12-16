import discord
from discord import app_commands
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
        
        if hasattr(self, 'polls_management_loop'): self.polls_management_loop.start()
        if hasattr(self, 'info_board_loop'): self.info_board_loop.start()

    def cog_unload(self):
        self.cleanup_loop.cancel()
        self.reminders_loop.cancel()
        self.channel_rename_loop.cancel()
        self.daily_morning_loop.cancel()
        self.daily_lore_loop.cancel()
        self.attendance_monitor_loop.cancel()
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

    # --- LOOP 1: MANHÃ (GAMEPLAY) - ALEATÓRIO ---
    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=BR_TIMEZONE))
    async def daily_morning_loop(self):
        delay = random.randint(0, 3600) # Até 1h de atraso
        print(f"[Daily Morning] Aguardando {delay/60:.1f} min...")
        await asyncio.sleep(delay)

        channel = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        if not channel: return

        # Aleatório em vez de sequencial
        quote = random.choice(quotes.MORNING_QUOTES)
        
        msg = (
            f"🌞 **Bom dia, Guardião!**\n\n"
            f"{quote}\n\n"
            f">>> 🗓️ **Organize sua fireteam:** Use `/agendar`\n"
            f"📊 **Decida o plano:** Use `/enquete_atividade` ou `/enquete_quando`"
        )
        await channel.send(msg)

    # --- LOOP 2: TARDE (LORE) - FINITO ---
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

    # --- LEMBRETE DE 1 HORA (CORRIGIDO) ---
    @tasks.loop(minutes=1)
    async def reminders_loop(self):
        await self.bot.wait_until_ready()
        events = await db.get_active_events()
        now = datetime.datetime.now(BR_TIMEZONE)
        
        for event in events:
            try:
                # Converter data
                if isinstance(event['date_time'], str): evt_time = datetime.datetime.fromisoformat(event['date_time'])
                else: evt_time = event['date_time']
                if evt_time.tzinfo is None: evt_time = BR_TIMEZONE.localize(evt_time)
                
                # Diferença em minutos
                diff_minutes = (evt_time - now).total_seconds() / 60
                
                # Check 1: Janela segura (50 a 65 min antes)
                if 50 <= diff_minutes <= 65:
                    # Check 2: Flag no Banco (A verdade absoluta)
                    lifecycle = await db.get_event_lifecycle(event['event_id'])
                    
                    # Se não tem lifecycle ou já enviou, pula
                    if not lifecycle: 
                        await db.set_lifecycle_flag(event['event_id'], 'reminder_1h_sent', 0)
                        continue
                        
                    if lifecycle['reminder_1h_sent']:
                        continue # Já enviado

                    # Check 3: Envia e Marca
                    try:
                        guild = self.bot.get_guild(event['guild_id'])
                        if not guild: continue
                        channel = guild.get_channel(event['channel_id'])
                        role = guild.get_role(event['role_id'])
                        
                        if channel and role: 
                            await channel.send(f"{role.mention} ⏰ O evento começa em 1 hora! Preparem-se.")
                            print(f"[REMINDER] Enviado para '{event['title']}'")
                            
                            # MARCA COMO ENVIADO (CRÍTICO)
                            await db.set_lifecycle_flag(event['event_id'], 'reminder_1h_sent', 1)
                    except Exception as e:
                        print(f"[REMINDER ERRO] {e}")

            except Exception as e: continue

    # --- OUTROS LOOPS (Monitoramento, Boards, Cleanup) ---
    
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
                lifecycle = await db.get_event_lifecycle(event['event_id'])
                if not lifecycle:
                    await db.set_lifecycle_flag(event['event_id'], 'start_alert_sent', 0)
                    lifecycle = {'maybe_alert_sent': 0, 'start_alert_sent': 0, 'late_report_sent': 0}
                
                # Aviso de vaga 15 min antes
                if -20 <= diff_minutes <= -10 and not lifecycle['maybe_alert_sent']:
                    rsvps = await db.get_rsvps(event['event_id'])
                    confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
                    if confirmed_count < event['max_slots']:
                        maybe_users = [r['user_id'] for r in rsvps if r['status'] == 'maybe']
                        if maybe_users:
                            for uid in maybe_users:
                                try:
                                    user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
                                    await user.send(f"🔔 **Vaga Disponível!**\nO evento **{event['title']}** começa em 15 minutos e tem vagas. Você marcou 'Talvez'. Pode cobrir?\nConfirme aqui: <#{event['channel_id']}>")
                                except: pass
                        await db.set_lifecycle_flag(event['event_id'], 'maybe_alert_sent')
                
                # Check inicial e DM de atraso
                if 0 <= diff_minutes <= 10 and not lifecycle['start_alert_sent']:
                    guild = self.bot.get_guild(event['guild_id'])
                    channel = guild.get_channel(event['channel_id'])
                    if guild and channel:
                        users_in_voice = [m.id for m in channel.members if not m.bot]
                        rsvps = await db.get_rsvps(event['event_id'])
                        confirmed_ids = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
                        missing_ids = [uid for uid in confirmed_ids if uid not in users_in_voice]
                        if missing_ids:
                            main_chat = guild.get_channel(config.CHANNEL_MAIN_CHAT)
                            mentions = " ".join([f"<@{uid}>" for uid in missing_ids])
                            if main_chat: await main_chat.send(f"🚨 **Atenção!** O evento **{event['title']}** começou e estes Guardiões não estão no canal de voz: {mentions}\nCorre lá: {channel.mention}")
                            for uid in missing_ids:
                                try:
                                    user = guild.get_member(uid)
                                    await user.send(f"⏰ **O Evento Começou!**\nVocê confirmou presença em **{event['title']}** mas não te vi no canal de voz. O esquadrão está te esperando!")
                                except: pass
                        await db.set_lifecycle_flag(event['event_id'], 'start_alert_sent')
                
                # Monitoramento contínuo
                if 0 <= diff_minutes <= 180:
                    guild = self.bot.get_guild(event['guild_id'])
                    channel = guild.get_channel(event['channel_id'])
                    if guild and channel:
                        users_in_voice = [m.id for m in channel.members if not m.bot]
                        rsvps = await db.get_rsvps(event['event_id'])
                        confirmed_ids = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
                        for uid in confirmed_ids:
                            if uid in users_in_voice: await db.mark_attendance_present(event['event_id'], uid)
                
                # Relatório final de faltas
                if 30 <= diff_minutes <= 40 and not lifecycle['late_report_sent']:
                    rsvps = await db.get_rsvps(event['event_id'])
                    confirmed_ids = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
                    absentees = []
                    for uid in confirmed_ids:
                        status = await db.get_attendance_status(event['event_id'], uid)
                        if status != 'present': absentees.append(uid)
                    if absentees:
                        guild = self.bot.get_guild(event['guild_id'])
                        main_chat = guild.get_channel(config.CHANNEL_MAIN_CHAT)
                        names = []
                        for uid in absentees:
                            mem = guild.get_member(uid)
                            names.append(mem.display_name if mem else f"User {uid}")
                        names_str = ", ".join(names)
                        if main_chat: await main_chat.send(f"📋 **Relatório de Ausência:**\nO evento **{event['title']}** já tem 30min de duração e os seguintes membros confirmados NÃO compareceram:\n🚫 **{names_str}**")
                    await db.set_lifecycle_flag(event['event_id'], 'late_report_sent')
            except Exception as e: print(f"[ATTENDANCE ERROR] Evento {event.get('event_id')}: {e}")

    @tasks.loop(minutes=5)
    async def info_board_loop(self):
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

        try:
            poll_channel = self.bot.get_channel(config.CHANNEL_POLLS)
            if poll_channel:
                content_msg = "# @ColaAI 🤖  Utilize os comandos:\n\n## ➡️ Envie  `/enquete_atividade` no chat\n> Para perguntar __qual atividade__ eles querem fazer no dia 'X'. \n> **Por exemplo:** Sábado às 2pm: Crota ou Jardim?\n\n## ➡️ Envie  `/enquete_quando` no chat\n> Para perguntar que __dia ou hora__ eles podem fazer tal atividade.\n> **Por exemplo:** *Deserto Perpétuo (Escola) - Sexta, Sábado ou Domingo?*"
                has_instr = False
                async for msg in poll_channel.history(limit=50):
                    if msg.author == self.bot.user and "Utilize os comandos" in msg.content:
                        has_instr = True
                        break
                if not has_instr: await poll_channel.send(content_msg)
        except: pass

    @tasks.loop(minutes=15)
    async def polls_management_loop(self):
        active_polls = await db.get_active_polls()
        now = datetime.datetime.now(BR_TIMEZONE)
        valid_polls_count = 0
        for poll in active_polls:
            try:
                created_at = datetime.datetime.fromisoformat(poll['created_at'])
                if created_at.tzinfo is None: created_at = created_at.replace(tzinfo=datetime.timezone.utc).astimezone(BR_TIMEZONE)
            except: continue
            diff = now - created_at
            if diff.total_seconds() > 86400:
                await db.close_poll(poll['message_id'])
                try:
                    channel = self.bot.get_channel(poll['channel_id'])
                    if channel:
                        msg = await channel.fetch_message(poll['message_id'])
                        await msg.delete()
                except: pass
                continue
            else: valid_polls_count += 1
            hours_passed = int(diff.total_seconds() / 3600)
            if hours_passed > 0 and hours_passed % 8 == 0 and diff.total_seconds() % 3600 < 900:
                main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
                poll_channel = self.bot.get_channel(poll['channel_id'])
                if main_chat and poll_channel:
                    txt = "Há enquetes em aberto esperando seu voto!"
                    if poll['poll_type'] == 'when': txt = f"Ainda estamos decidindo o horário para **{poll['target_data']}**!"
                    await main_chat.send(f"🔔 {txt} Corre lá: {poll_channel.mention}")
        try:
            poll_channel = self.bot.get_channel(config.CHANNEL_POLLS)
            if poll_channel:
                new_name = "responda-a-enquete‼️" if valid_polls_count > 0 else "📢crie-uma-enquete"
                if poll_channel.name != new_name: await poll_channel.edit(name=new_name)
        except: pass

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
