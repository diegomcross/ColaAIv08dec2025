import discord
from discord.ext import commands, tasks
import datetime
import random
import asyncio
import database as db
import utils
import config
from constants import BR_TIMEZONE

# --- FRASES DE BOM DIA (ColaAI - Otimista) ---
MOTIVATIONAL_QUOTES = [
    "Bom dia, Guardião! O Testemunha virou fumaça, mas o seu loot continua lá esperando. Vamos farmar!",
    "Acorda! Se um Titã consegue comer uma caixa de giz de cera antes do café e ficar bem, você consegue enfrentar essa manhã.",
    "O Viajante curou o Coração Pálido, agora trate de curar essa preguiça! O dia está lindo para explodir alguns Desprezíveis.",
    "Caçadores, parem de usar a esquiva para fugir das responsabilidades! O café está na mesa e o Zavala estaria orgulhoso.",
    "Arcanos, fechem os livros e abram os olhos! A teoria acabou, a prática de sobreviver ao despertador começa agora.",
    "Se o Corvo aguentou a culpa de ser o Uldren por tanto tempo, você aguenta levantar cedo hoje. Força!",
    "Rahool pode te dar um item azul num engrama lendário, mas hoje o dia promete ser Exótico! Não desperdice seu RNG dormindo.",
    "A Forma Final foi evitada, mas a 'Forma do seu Travesseiro' ainda parece ser o inimigo mais forte? Quebre esse vínculo!",
    "Levanta! A Vanguarda precisa de você mais do que o Drifter precisa de motes.",
    "Olhos para cima, Guardião! O sol nasceu e a Treva recuou... pelo menos até a próxima DLC."
]

# --- FRASES DA JURURU (Blue - A Fantasma Ácida) ---
JURURU_QUOTES = [
    "Corta essa baboseira. O Testemunha queria congelar o universo numa forma perfeita, e olhando pro seu DPS de ontem, acho que ele só queria te poupar da vergonha.",
    "Bom dia? Só se for pro inimigo. Você chama isso de 'Build'? Até um Dreg na ZME com uma pistola enferrujada tem mais sinergia que você.",
    "Interrompendo esse protocolo de otimismo para avisar: O Mestre Rahool me contou que aquele Exótico que você quer NÃO vai cair hoje. Aceita.",
    "A Luz te dá imortalidade apenas para que você possa errar o pulo na Raid infinitas vezes. O Viajante comete erros, e você é a prova viva flutuante disso.",
    "Dizem que 'Guardiões fazem o seu próprio destino'. No seu caso, o destino parece ser invariavelmente 'Morto pelos Arquitetos' por pisar numa pedra torta.",
    "Se a Lógica da Espada da Colmeia fosse aplicada neste clã, você já teria virado um cristal decorativo na estante da Savathûn há muito tempo.",
    "Eris Morn passou anos sozinha na escuridão da Lua, e ainda assim ela é uma companhia mais agradável do que você explicando mecânica de Raid.",
    "Não se preocupe com a Próxima Ameaça. A sua forma atual de jogar já é trágica o suficiente para convencer a Treva a desistir da invasão por pura pena.",
    "Você farma, farma e farma. Para quê? Para guardar a arma no cofre e continuar usando a mesma de 4 anos atrás. A definição de insanidade é o seu inventário.",
    "Bip. Bop. O Cayde-6 não morreu heroicamente para você errar a Super desse jeito vergonhoso. Volte para a órbita e reflita."
]

class TasksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_loop.start()
        self.reminders_loop.start()
        self.channel_rename_loop.start()
        self.polls_management_loop.start()
        self.info_board_loop.start()
        self.daily_morning_loop.start() # Inicia o loop de Bom Dia

    def cog_unload(self):
        self.cleanup_loop.cancel()
        self.reminders_loop.cancel()
        self.channel_rename_loop.cancel()
        self.polls_management_loop.cancel()
        self.info_board_loop.cancel()
        self.daily_morning_loop.cancel()

    # --- LOOP DE BOM DIA / HACK DA JURURU ---
    # Roda todos os dias às 08:00 (Horário de Brasília)
    @tasks.loop(time=datetime.time(hour=8, minute=0, tzinfo=BR_TIMEZONE))
    async def daily_morning_loop(self):
        # 1. Delay Aleatório (Entre 0 e 120 minutos) -> Mensagem sai entre 08:00 e 10:00
        delay_seconds = random.randint(0, 7200) 
        print(f"[Daily] Aguardando {delay_seconds/60:.1f} minutos para mandar o bom dia...")
        await asyncio.sleep(delay_seconds)

        channel = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        if not channel: return

        # 2. Rola o dado: 15% de chance de Hack da Jururu (aprox 1 vez por semana)
        chance_jururu = 0.15 
        is_hacked = random.random() < chance_jururu

        if is_hacked:
            # MODO JURURU (Blue)
            frase = random.choice(JURURU_QUOTES)
            embed = discord.Embed(
                description=f"🔵 **CONEXÃO INTERROMPIDA...**\n\n*\"Chega dessa baboseira motivacional, ColaAI. Deixa a tia falar a verdade.\"*\n\n💀 **A mensagem real de hoje é:**\n\n> {frase}\n\n*— Ass: Jururu (Blue)*",
                color=discord.Color.dark_teal() # Uma cor "Blue/Drifter"
            )
            # Sem lembretes de agendar, porque a Jururu não liga pra isso.
            await channel.send(embed=embed)
        
        else:
            # MODO NORMAL (ColaAI)
            frase = random.choice(MOTIVATIONAL_QUOTES)
            msg = (
                f"🌞 **Bom dia, Guardião!**\n\n"
                f"{frase}\n\n"
                f">>> 🗓️ **Organize sua fireteam:** Use `/agendar`\n"
                f"📊 **Decida o plano:** Use `/enquete_atividade` ou `/enquete_quando`"
            )
            await channel.send(msg)

    # --- OUTROS LOOPS (JÁ EXISTENTES) ---
    
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
        except Exception as e: print(f"[DEBUG] Erro no quadro de horários: {e}")

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
