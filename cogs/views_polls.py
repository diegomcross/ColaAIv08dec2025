import discord
import database as db
import utils
import config
import json
from constants import BR_TIMEZONE

# --- CLASSE BASE PARA ENQUETES ---
class PollView(discord.ui.View):
    def __init__(self, bot, poll_type, target_data):
        super().__init__(timeout=None)
        self.bot = bot
        self.poll_type = poll_type
        self.target_data = target_data
        # Meta: 3 votos para horário ('when'), 4 para atividade ('what')
        self.threshold = 3 if poll_type == 'when' else 4

    async def handle_vote(self, interaction: discord.Interaction, option: str):
        await interaction.response.defer()
        # Salva o voto no banco
        await db.add_poll_vote(interaction.message.id, interaction.user.id, option)
        
        # Recalcula votos
        votes = await db.get_poll_votes(interaction.message.id)
        vote_counts = {row['vote_option']: row['count'] for row in votes}
        
        # Atualiza a Embed
        embed = interaction.message.embeds[0]
        new_desc_lines = []
        winner_option = None
        base_desc = f"Meta para confirmar: **{self.threshold} votos**\n\n"
        
        # Ordena opções por votos
        sorted_votes = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)
        
        for opt, count in sorted_votes:
            if count >= self.threshold: 
                winner_option = opt
            line = f"**{opt}**: {count} votos"
            if count >= self.threshold: line += " ✅ **CONFIRMADO**"
            new_desc_lines.append(line)
            
        embed.description = base_desc + "\n".join(new_desc_lines)
        await interaction.message.edit(embed=embed)
        
        # Se atingiu a meta, dispara a criação do evento
        if winner_option:
            await self.trigger_event_creation(interaction, winner_option)

    async def trigger_event_creation(self, interaction, winner_value):
        poll = await db.get_poll_details(interaction.message.id)
        if poll and poll['status'] == 'closed': return
        await db.close_poll(interaction.message.id)

        final_title = ""
        final_dt = None
        
        # Lógica 'when': target_data é o nome da atividade, winner_value é a data
        if self.poll_type == 'when':
            final_title = self.target_data
            final_dt = utils.parse_human_date(winner_value)
            
        # Lógica 'what': winner_value é o nome da atividade, target_data é JSON com a data
        elif self.poll_type == 'what':
            final_title = winner_value
            try:
                data = json.loads(self.target_data)
                date_str = data.get('date_str', 'hoje 21h')
                final_dt = utils.parse_human_date(date_str)
            except:
                final_dt = utils.parse_human_date("hoje 21h")

        if not final_dt: 
            return await interaction.channel.send("❌ Erro ao processar data para criação do evento.")

        # Criação do Evento
        official_name, act_type, slots = utils.detect_activity_details(final_title)
        if slots is None: slots = 6
        
        guild = interaction.guild
        role_name = f"{official_name[:15]} {final_dt.strftime('%d/%m')}"
        role = await guild.create_role(name=role_name, mentionable=True, reason="Enquete Vencedora")

        category = guild.get_channel(config.CATEGORY_EVENTS_ID)
        channel_name = utils.generate_channel_name(official_name, final_dt, act_type, slots, description="Criado via Enquete")
        
        if category: 
            channel = await guild.create_text_channel(name=channel_name, category=category)
        else: 
            channel = await guild.create_text_channel(name=channel_name)

        from views import PersistentRsvpView
        embed_loading = discord.Embed(title="Gerando evento...", color=discord.Color.gold())
        msg = await channel.send(content=f"{role.mention} A comunidade decidiu!", embed=embed_loading, view=PersistentRsvpView())

        db_data = {
            'guild_id': guild.id, 'channel_id': channel.id, 'message_id': msg.id,
            'role_id': role.id, 'title': official_name, 'desc': "Criado via Enquete",
            'type': act_type, 'date': final_dt, 'slots': slots, 'creator': self.bot.user.id
        }
        event_id = await db.create_event(db_data)
        db_data['event_id'] = event_id
        
        rsvps = [] 
        final_embed = await utils.build_event_embed(db_data, rsvps, self.bot)
        await msg.edit(embed=final_embed)
        
        await interaction.channel.send(f"🎉 Evento criado em {channel.mention}")
        
        # Desativa os botões da enquete
        for child in self.children: 
            child.disabled = True
        await interaction.message.edit(view=self)

# --- CLASSE DE VOTAÇÃO GENÉRICA ---
class VotingPollView(PollView):
    def __init__(self, bot, poll_type, target_data, options_list):
        super().__init__(bot, poll_type, target_data)
        for opt in options_list:
            # Pega label e value (ou usa o mesmo valor para ambos)
            label = opt.get('label', opt.get('value'))
            value = opt.get('value', label)
            self.add_item(VotingButton(label, value))

class VotingButton(discord.ui.Button):
    def __init__(self, label, value):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id=f"vote_{label[:20]}")
        self.value = value
    async def callback(self, interaction):
        await self.view.handle_vote(interaction, self.value)

# --- CLASSE CONSTRUTORA (Setup da Enquete) ---
class PollBuilderView(discord.ui.View):
    def __init__(self, bot, activity_name):
        super().__init__(timeout=180)
        self.bot = bot
        self.activity_name = activity_name
        self.selected_day = None

    @discord.ui.select(placeholder="Selecione o Dia...", options=[
        discord.SelectOption(label="Hoje", value="Hoje"),
        discord.SelectOption(label="Amanhã", value="Amanhã"),
        discord.SelectOption(label="Sábado", value="Sábado"),
        discord.SelectOption(label="Domingo", value="Domingo"),
        discord.SelectOption(label="Segunda-feira", value="Segunda-feira"),
        discord.SelectOption(label="Terça-feira", value="Terça-feira"),
        discord.SelectOption(label="Quarta-feira", value="Quarta-feira"),
        discord.SelectOption(label="Quinta-feira", value="Quinta-feira"),
        discord.SelectOption(label="Sexta-feira", value="Sexta-feira"),
    ])
    async def select_day(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_day = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Lançar Enquete", style=discord.ButtonStyle.success)
    async def launch(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_day:
            return await interaction.response.send_message("⚠️ Selecione um dia primeiro!", ephemeral=True)
        
        # Cria opções de horário baseadas no dia selecionado
        times = ["08:00", "11:00", "14:00", "17:00", "20:00", "22:00"]
        options_list = []
        for t in times:
            full_opt = f"{self.selected_day} {t}"
            options_list.append({'label': t, 'value': full_opt})
            
        # Cria a View pública de votação
        poll_view = VotingPollView(self.bot, 'when', self.activity_name, options_list)
        
        embed = discord.Embed(
            title=f"📊 Enquete de Horário: {self.activity_name}",
            description=f"**Dia:** {self.selected_day}\n\nMeta para confirmar: **3 votos** no mesmo horário.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Vote clicando nos botões abaixo.")
        
        try:
            # Envia no canal oficial de enquetes
            poll_channel = interaction.guild.get_channel(config.CHANNEL_POLLS)
            if not poll_channel: poll_channel = interaction.channel # Fallback
            
            msg = await poll_channel.send(embed=embed, view=poll_view)
            await db.create_poll(msg.id, poll_channel.id, interaction.guild.id, 'when', self.activity_name)
            
            await interaction.followup.send(f"✅ Enquete lançada em {poll_channel.mention}!", ephemeral=True)
            self.stop()
        except Exception as e:
            await interaction.followup.send(f"Erro ao criar enquete: {e}", ephemeral=True)
