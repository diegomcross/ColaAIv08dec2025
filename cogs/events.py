import discord
from discord import app_commands
from discord.ext import commands
import config
import database as db
import utils
from views import PersistentRsvpView
from typing import Union

# --- View para selecionar Vagas ---
class SlotsView(discord.ui.View):
    def __init__(self, event_data_partial, bot, modal_interaction):
        super().__init__(timeout=60)
        self.event_data = event_data_partial
        self.bot = bot
        self.modal_interaction = modal_interaction

    async def finalize_creation(self, interaction: discord.Interaction, slots: int):
        await interaction.response.defer(ephemeral=True)
        
        # Define as vagas selecionadas
        self.event_data['max_slots'] = slots
        
        # --- Lógica de Criação (Reusada) ---
        guild = interaction.guild
        dt = self.event_data['date_time']
        official_name = self.event_data['title']
        act_type = self.event_data['activity_type']
        description_text = self.event_data['description']
        
        # Cargo
        role_name = f"{official_name[:20]} {dt.strftime('%d/%m')}"
        role = await guild.create_role(name=role_name, mentionable=True, reason="Evento Bot")
        self.event_data['role_id'] = role.id
        
        # Canal
        category = guild.get_channel(config.CATEGORY_EVENTS_ID)
        channel_name = utils.generate_channel_name(official_name, dt, act_type, slots, description=description_text)
        
        if category:
            channel = await guild.create_text_channel(name=channel_name, category=category)
        else:
            channel = await guild.create_text_channel(name=channel_name)
        self.event_data['channel_id'] = channel.id
        
        # DB e Embed
        embed_loading = discord.Embed(title="Criando...", color=discord.Color.blue())
        msg = await channel.send(content=role.mention, embed=embed_loading, view=PersistentRsvpView())
        self.event_data['message_id'] = msg.id
        
        db_payload = {
            'guild_id': self.event_data['guild_id'],
            'channel_id': self.event_data['channel_id'],
            'message_id': self.event_data['message_id'],
            'role_id': self.event_data['role_id'],
            'title': self.event_data['title'],
            'desc': self.event_data['description'],
            'type': self.event_data['activity_type'],
            'date': self.event_data['date_time'],
            'slots': self.event_data['max_slots'],
            'creator': self.event_data['creator_id']
        }
        
        event_id = await db.create_event(db_payload)
        self.event_data['event_id'] = event_id
        
        # RSVP e Finalização
        await db.update_rsvp(event_id, self.event_data['creator_id'], 'confirmed')
        await interaction.user.add_roles(role)
        
        rsvps = await db.get_rsvps(event_id)
        final_embed = await utils.build_event_embed(self.event_data, rsvps, self.bot)
        
        await msg.edit(embed=final_embed)
        await interaction.followup.send(f"✅ Evento criado em {channel.mention} ({slots} vagas)!", ephemeral=True)
        
        self.stop()
        await self.modal_interaction.edit_original_response(content="✅ Vagas definidas.", view=None)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary)
    async def slot_2(self, interaction: discord.Interaction, button: discord.ui.Button): await self.finalize_creation(interaction, 2)
    @discord.ui.button(label="3", style=discord.ButtonStyle.primary)
    async def slot_3(self, interaction: discord.Interaction, button: discord.ui.Button): await self.finalize_creation(interaction, 3)
    @discord.ui.button(label="4", style=discord.ButtonStyle.primary)
    async def slot_4(self, interaction: discord.Interaction, button: discord.ui.Button): await self.finalize_creation(interaction, 4)
    @discord.ui.button(label="6", style=discord.ButtonStyle.primary)
    async def slot_6(self, interaction: discord.Interaction, button: discord.ui.Button): await self.finalize_creation(interaction, 6)
    @discord.ui.button(label="12", style=discord.ButtonStyle.secondary)
    async def slot_12(self, interaction: discord.Interaction, button: discord.ui.Button): await self.finalize_creation(interaction, 12)

class EventModal(discord.ui.Modal, title="Agendar Evento"):
    title_input = discord.ui.TextInput(label="Título", placeholder="Ex: Raid Cripta da Pedra")
    desc_input = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, required=False)
    date_input = discord.ui.TextInput(label="Data/Hora", placeholder="Ex: hoje 21h, amanha 18h30")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Parse Data
        dt = utils.parse_human_date(self.date_input.value)
        if not dt:
            return await interaction.followup.send("❌ Data inválida.", ephemeral=True)
        
        # 2. Detectar Detalhes
        official_name, act_type, slots = utils.detect_activity_details(self.title_input.value)
        
        # Dados parciais
        event_data_partial = {
            'guild_id': interaction.guild.id,
            'title': official_name,
            'description': self.desc_input.value or "",
            'activity_type': act_type,
            'date_time': dt,
            'creator_id': interaction.user.id
        }

        # CASO 1: Tipo desconhecido/Outro -> Pergunta Vagas
        if slots is None:
            view = SlotsView(event_data_partial, interaction.client, interaction)
            await interaction.followup.send("🔢 Quantas vagas para este evento?", view=view, ephemeral=True)
            return

        # CASO 2: Raid/Masmorra/PvP -> Cria Direto
        event_data_partial['max_slots'] = slots
        
        # --- Criação Direta (Cópia da lógica acima) ---
        guild = interaction.guild
        role_name = f"{official_name[:20]} {dt.strftime('%d/%m')}"
        role = await guild.create_role(name=role_name, mentionable=True, reason="Evento Bot")
        event_data_partial['role_id'] = role.id
        
        category = interaction.guild.get_channel(config.CATEGORY_EVENTS_ID)
        channel_name = utils.generate_channel_name(official_name, dt, act_type, slots, description=event_data_partial['description'])
        
        if category:
            channel = await guild.create_text_channel(name=channel_name, category=category)
        else:
            channel = await guild.create_text_channel(name=channel_name)
        event_data_partial['channel_id'] = channel.id
        
        embed_loading = discord.Embed(title="Criando...", color=discord.Color.blue())
        msg = await channel.send(content=role.mention, embed=embed_loading, view=PersistentRsvpView())
        event_data_partial['message_id'] = msg.id
        
        db_payload = {
            'guild_id': event_data_partial['guild_id'],
            'channel_id': event_data_partial['channel_id'],
            'message_id': event_data_partial['message_id'],
            'role_id': event_data_partial['role_id'],
            'title': event_data_partial['title'],
            'desc': event_data_partial['description'],
            'type': event_data_partial['activity_type'],
            'date': event_data_partial['date_time'],
            'slots': event_data_partial['max_slots'],
            'creator': event_data_partial['creator_id']
        }
        
        event_id = await db.create_event(db_payload)
        event_data_partial['event_id'] = event_id
        
        await db.update_rsvp(event_id, interaction.user.id, 'confirmed')
        await interaction.user.add_roles(role)
        
        rsvps = await db.get_rsvps(event_id)
        final_embed = await utils.build_event_embed(event_data_partial, rsvps, interaction.client)
        
        await msg.edit(embed=final_embed)
        await interaction.followup.send(f"✅ Evento criado em {channel.mention}!", ephemeral=True)

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="agendar", description="Cria um novo evento.")
    async def agendar(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventModal())

    @app_commands.command(name="definir_cargo_gerente", description="Define quem pode editar/apagar eventos.")
    @app_commands.describe(alvo="Selecione um Cargo ou Usuário")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_manager(self, interaction: discord.Interaction, alvo: Union[discord.Role, discord.Member]):
        await db.set_manager_id(interaction.guild.id, alvo.id)
        name = alvo.name if hasattr(alvo, 'name') else str(alvo)
        await interaction.response.send_message(f"✅ Configurado! **{name}** agora é Gerente de Eventos.", ephemeral=True)

    @app_commands.command(name="gerenciar_rsvp", description="Admin: Altera status de um usuário.")
    @app_commands.describe(status="Novo status")
    @app_commands.choices(status=[
        app_commands.Choice(name="Confirmado", value="confirmed"),
        app_commands.Choice(name="Lista de Espera", value="waitlist"),
        app_commands.Choice(name="Talvez", value="maybe"),
        app_commands.Choice(name="Não Vou", value="absent")
    ])
    @app_commands.checks.has_permissions(manage_messages=True)
    async def manage_rsvp(self, interaction: discord.Interaction, event_id: int, member: discord.Member, status: app_commands.Choice[str]):
        status_val = status.value
        await db.update_rsvp(event_id, member.id, status_val)
        
        event = await db.get_event(event_id)
        if event:
            try:
                channel = interaction.guild.get_channel(event['channel_id'])
                msg = await channel.fetch_message(event['message_id'])
                rsvps = await db.get_rsvps(event_id)
                new_embed = await utils.build_event_embed(dict(event), rsvps, self.bot)
                await msg.edit(embed=new_embed)
                
                status_map = {'confirmed': 'Confirmado', 'waitlist': 'Lista de Espera', 'maybe': 'Talvez', 'absent': 'Não Vou'}
                display_status = status_map.get(status_val, status_val)
                
                await interaction.response.send_message(f"RSVP de {member.display_name} alterado para {display_status}.", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Erro ao atualizar: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EventsCog(bot))