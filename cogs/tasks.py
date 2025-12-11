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
import google.generativeai as genai
from google.api_core import exceptions

# --- LISTA DE FALLBACK (Plano C) ---
FALLBACK_MOTIVATIONAL = [
    "Bom dia, Guardião! O Testemunha virou fumaça, mas o seu loot continua lá esperando. Vamos farmar!",
    "Acorda! Se um Titã consegue comer uma caixa de giz de cera antes do café e ficar bem, você consegue enfrentar essa manhã.",
    "O Viajante curou o Coração Pálido, agora trate de curar essa preguiça! Vamos à luta.",
    "Se o Corvo aguentou a culpa de ser o Uldren por tanto tempo, você aguenta levantar cedo hoje. Força!",
    "Rahool pode te dar um item azul num engrama lendário, mas hoje o dia promete ser Exótico! Não desperdice seu RNG dormindo."
]

FALLBACK_JURURU = [
    "Corta essa baboseira. O Mestre Rahool me contou que aquele Exótico que você quer NÃO vai cair hoje. Aceita.",
    "Bom dia? Só se for pro inimigo. Você chama isso de 'Build'? Até um Dreg na ZME tem mais sinergia.",
    "Bip. Bop. O Cayde-6 não morreu heroicamente para você errar a Super desse jeito vergonhoso.",
    "A Luz te dá imortalidade apenas para que você possa errar o pulo na Raid infinitas vezes. O Viajante comete erros.",
    "Não se preocupe com A Forma Final. A sua forma atual de jogar já é trágica o suficiente."
]

class TasksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_loop.start()
        self.reminders_loop.start()
        self.channel_rename_loop.start()
        if hasattr(self, 'polls_management_loop'): self.polls_management_loop.start()
        if hasattr(self, 'info_board_loop'): self.info_board_loop.start()
        self.daily_morning_loop.start()
        
        # Tenta configurar a IA silenciosamente ao iniciar
        if hasattr(config, 'GEMINI_API_KEY') and config.GEMINI_API_KEY:
            genai.configure(api_key=config.GEMINI_API_KEY)

    def cog_unload(self):
        self.cleanup_loop.cancel()
        self.reminders_loop.cancel()
        self.channel_rename_loop.cancel()
        self.daily_morning_loop.cancel()
        if hasattr(self, 'polls_management_loop'): self.polls_management_loop.cancel()
        if hasattr(self, 'info_board_loop'): self.info_board_loop.cancel()

    # --- GERADOR DE TEXTO ---
    async def generate_ai_message(self, mode="motivacional"):
        if not hasattr(config, 'GEMINI_API_KEY') or not config.GEMINI_API_KEY:
            return None

        # Definição dos Prompts
        if mode == "jururu":
            prompt = (
                "Aja como Jururu (Blue), a fantasma sarcástica e ácida do Drifter em Destiny 2. "
                "Escreva uma frase curta (máx 200 caracteres) interrompendo um 'bom dia'. "
                "Seja cômica e desmotivacional. Critique o jogador (mira ruim, build feia)."
            )
        else:
            prompt = (
                "Escreva uma frase de 'Bom dia' curta (máx 280 caracteres), engraçada e motivacional para clã de Destiny 2. "
                "Use lore atual (Fikrul, Ecos). Termine com 'Vamos à luta, Guardião!'."
            )

        # Tenta usar o modelo mais estável diretamente (gemini-1.5-flash)
        # Se falhar, tenta o antigo (gemini-pro)
        models_to_force = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"]
        
        for model_name in models_to_force:
            try:
                model = genai.GenerativeModel(model_name)
                response = await asyncio.wait_for(
                    asyncio.to_thread(model.generate_content, prompt), 
                    timeout=8.0
                )
                if response.text:
                    return response.text.strip()
            except exceptions.ResourceExhausted:
                print(f"[IA AVISO] Cota excedida para {model_name}. Tentando próximo...")
                continue
            except Exception as e:
                # Ignora erros de "not found" e tenta o próximo
                if "404" not in str(e) and "not found" not in str(e).lower():
                    print(f"[IA ERRO] {e}")
                continue
        
        return None # Se tudo falhar, retorna None para usar Fallback

    # --- COMANDO DE TESTE (Modificado para evitar Cota) ---
    @app_commands.command(name="debug_bomdia", description="Teste rápido de IA (3 msgs).")
    async def debug_bomdia(self, interaction: discord.Interaction):
        TARGET_ID = 1385769340149829682
        channel = self.bot.get_channel(TARGET_ID) or interaction.channel
        
        await interaction.response.send_message(f"🧪 Testando IA em {channel.mention}...", ephemeral=True)

        # Reduzi para 3 mensagens para não estourar a cota gratuita no teste
        for i in range(1, 4):
            is_hacked = random.random() < 0.5
            mode = "jururu" if is_hacked else "motivacional"
            
            frase = await self.generate_ai_message(mode=mode)
            source = "IA"
            
            if not frase:
                frase = random.choice(FALLBACK_JURURU if is_hacked else FALLBACK_MOTIVATIONAL)
                source = "Fallback (Erro IA)"

            if is_hacked:
                embed = discord.Embed(
                    description=f"🔵 **[TESTE {i}/3 - {source}] INTERROMPIDO...**\n\n*\"Chega dessa baboseira. Aqui é a Jururu.\"*\n\n💀 **Mensagem:**\n> {frase}",
                    color=discord.Color.dark_teal()
                )
                await channel.send(embed=embed)
            else:
                await channel.send(f"🌞 **[TESTE {i}/3 - {source}] Bom dia!**\n\n{frase}")
            
            # Delay maior entre mensagens de teste
            if i < 3: await asyncio.sleep(10)

    # --- LOOP ORIGINAL ---
    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=BR_TIMEZONE))
    async def daily_morning_loop(self):
        delay = random.randint(0, 7200)
        print(f"[Daily] Aguardando {delay/60:.1f} min...")
        await asyncio.sleep(delay)

        channel = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        if not channel: return

        is_hacked = random.random() < 0.15
        if is_hacked:
            frase = await self.generate_ai_message(mode="jururu")
            if not frase: frase = random.choice(FALLBACK_JURURU)
            embed = discord.Embed(
                description=f"🔵 **CONEXÃO INTERROMPIDA...**\n\n*\"Chega dessa baboseira motivacional, ColaAI. Deixa a tia falar a verdade.\"*\n\n💀 **A mensagem real de hoje é:**\n\n> {frase}\n\n*— Ass: Jururu (Blue)*",
                color=discord.Color.dark_teal()
            )
            await channel.send(embed=embed)
        else:
            frase = await self.generate_ai_message(mode="motivacional")
            if not frase: frase = random.choice(FALLBACK_MOTIVATIONAL)
            msg = f"🌞 **Bom dia, Guardião!**\n\n{frase}\n\n>>> 🗓️ **Organize sua fireteam:** Use `/agendar`\n📊 **Decida o plano:** Use `/enquete_atividade` ou `/enquete_quando`"
            await channel.send(msg)

    # --- INFO BOARD ---
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

    # --- POLLS MANAGEMENT ---
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

    # --- CLEANUP LOOP ---
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

    # --- CHANNEL RENAME LOOP ---
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

    # --- REMINDERS LOOP ---
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
