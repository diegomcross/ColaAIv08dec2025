import discord
import database as db
import utils
from constants import BR_TIMEZONE
import datetime

# --- AUXILIAR DE NOTIFICAÇÃO ---
async def notify_confirmed_users(interaction: discord.Interaction, event_id: int, message: str):
    """Envia DM para todos os confirmados no evento."""
    try:
        rsvps = await db.get_rsvps(event_id)
        confirmed_ids = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
        
        for uid in confirmed_ids:
            if uid == interaction.user.id: continue # Não notificar quem fez a ação
            try:
                user = interaction.client.get_user(uid) or await interaction.client.fetch_user(uid)
                await user.send(message)
            except: pass
    except Exception as e:
        print(f"[DEBUG] Erro ao notificar usuários: {e}")

# --- MODAL DE EDIÇÃO ---
class EventEditModal(discord.ui.Modal, title="Editar Evento"):
    def __init__(self, event_data, bot):
        super().__init__()
        self.event_data = event_data
        self.bot = bot
        
        self.title_input = discord.ui.TextInput(label="Título", default=event_data['title'])
        self.add_item(self.title_input)
        
        self.desc_input = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, required=False, default=event_data['description'] or "")
        self.add_item(self.desc_input)
        
        # Formatar data
        raw_date = event_data['date_time']
        if isinstance(raw_date, str):
            try: dt_obj = datetime.datetime.fromisoformat(raw_date)
            except: dt_obj = datetime.datetime.now()
        else: dt_obj = raw_date
        
        if dt_obj.tzinfo is None: dt_obj = BR_TIMEZONE.localize(dt_obj)
        self.date_input = discord.ui.TextInput(label="Data/Hora", default=dt_obj.strftime("%d/%m %H:%M"))
        self.add_item(self.date_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        new_dt = utils.parse_human_date(self.date_input.value)
        if not new_dt: return await interaction.followup.send("❌ Data inválida.", ephemeral=True)
            
        new_title = self.title_input.value
        official_name, act_type, slots = utils.detect_activity_details(new_title)
        if slots is None: slots = self.event_data['max_slots'] or 6
        
        # Atualizar DB
        await db.update_event_details(
            self.event_data['event_id'], official_name, self.desc_input.value, new_dt, act_type, slots
        )
        
        # Notificar
        await notify_confirmed_users(interaction, self.event_data['event_id'], f"📝 **Evento Editado:** O evento **{official_name}** foi alterado por {interaction.user.display_name}.")
        
        # Atualizar Visual
        event = await db.get_event(self.event_data['event_id'])
        rsvps = await db.get_rsvps(self.event_data['event_id'])
        
        embed = await utils.build_event_embed(dict(event), rsvps, self.bot)
        channel = interaction.guild.get_channel(event['channel_id'])
        if channel:
            try:
                msg = await channel.fetch_message(event['message_id'])
                await msg.edit(embed=embed)
                
                # Renomear canal
                confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
                free_slots = max(0, slots - confirmed_count)
                new_name = utils.generate_channel_name(official_name, new_dt, act_type, free_slots, description=self.desc_input.value)
                if channel.name != new_name: await channel.edit(name=new_name)
                    
                await interaction.followup.send("✅ Evento atualizado!", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Salvo, mas erro visual: {e}", ephemeral=True)

# --- VIEW PRINCIPAL ---
class PersistentRsvpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def update_event_embed(self, interaction: discord.Interaction, event_id: int):
        event = await db.get_event(event_id)
        if not event: return
        
        rsvps = await db.get_rsvps(event_id)
        confirmed = [r for r in rsvps if r['status'] == 'confirmed']
        waitlist = [r for r in rsvps if r['status'] == 'waitlist']
        slots = event['max_slots']
        
        changed = False
        while len(confirmed) < slots and len(waitlist) > 0:
            lucky_user = waitlist.pop(0) 
            await db.update_rsvp(event_id, lucky_user['user_id'], 'confirmed')
            confirmed.append(lucky_user)
            changed = True
        
        if changed: rsvps = await db.get_rsvps(event_id)

        embed = await utils.build_event_embed(dict(event), rsvps, interaction.client)
        await interaction.message.edit(embed=embed)
        
        confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
        free_slots = max(0, slots - confirmed_count)
        
        if isinstance(event['date_time'], str):
            try: event_dt = datetime.datetime.fromisoformat(event['date_time'])
            except: event_dt = datetime.datetime.now()
        else: event_dt = event['date_time']
        if event_dt.tzinfo is None: event_dt = BR_TIMEZONE.localize(event_dt)

        new_name = utils.generate_channel_name(event['title'], event_dt, event['activity_type'], free_slots, description=event['description'])
        if interaction.channel.name != new_name:
            try: await interaction.channel.edit(name=new_name)
            except: pass

    async def handle_click(self, interaction: discord.Interaction, status: str):
        try:
            footer_text = interaction.message.embeds[0].footer.text
            event_id = int(footer_text.split(": ")[1])
        except: return await interaction.response.send_message("Erro ID.", ephemeral=True)
        
        event = await db.get_event(event_id)
        if not event: return await interaction.response.send_message("Evento deletado.", ephemeral=True)

        rsvps = await db.get_rsvps(event_id)
        confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
        
        final_status = status
        if status == 'confirmed':
            user_current = next((r for r in rsvps if r['user_id'] == interaction.user.id), None)
            is_confirmed = user_current and user_current['status'] == 'confirmed'
            if confirmed_count >= event['max_slots'] and not is_confirmed:
                final_status = 'waitlist'
                await interaction.response.send_message("Vagas cheias! Você foi para a **Lista de Espera**.", ephemeral=True)
            else:
                await interaction.response.send_message("Confirmado!", ephemeral=True)
        else:
            await interaction.response.send_message(f"Status: {status}", ephemeral=True)

        await db.update_rsvp(event_id, interaction.user.id, final_status)
        
        role = interaction.guild.get_role(event['role_id'])
        if role:
            try:
                if final_status in ['confirmed', 'waitlist']: await interaction.user.add_roles(role)
                else: await interaction.user.remove_roles(role)
            except: pass
        
        await self.update_event_embed(interaction, event_id)

    async def check_manager_permission(self, interaction: discord.Interaction, event):
        if interaction.user.id == event['creator_id']: return True
        if interaction.user.guild_permissions.administrator: return True
        manager_id = await db.get_manager_id(interaction.guild.id)
        if manager_id:
            if interaction.user.id == manager_id: return True
            if interaction.user.get_role(manager_id): return True
        return False

    # BOTÕES CINZAS (SECONDARY)
    @discord.ui.button(label="Vou", style=discord.ButtonStyle.secondary, custom_id="rsvp_yes", emoji="✅")
    async def btn_yes(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 'confirmed')

    @discord.ui.button(label="Não Vou", style=discord.ButtonStyle.secondary, custom_id="rsvp_no", emoji="❌")
    async def btn_no(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 'absent')

    @discord.ui.button(label="Talvez", style=discord.ButtonStyle.secondary, custom_id="rsvp_maybe", emoji="🔷")
    async def btn_maybe(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 'maybe')

    @discord.ui.button(label="Editar", style=discord.ButtonStyle.primary, custom_id="btn_edit", emoji="✏️", row=1)
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            event_id = int(interaction.message.embeds[0].footer.text.split(": ")[1])
            event = await db.get_event(event_id)
        except: return await interaction.response.send_message("Erro buscar evento.", ephemeral=True)

        if not await self.check_manager_permission(interaction, event):
            return await interaction.response.send_message("❌ Apenas o Criador ou Gerentes podem editar.", ephemeral=True)

        await interaction.response.send_modal(EventEditModal(dict(event), interaction.client))

    @discord.ui.button(label="Apagar", style=discord.ButtonStyle.danger, custom_id="btn_delete", emoji="🗑️", row=1)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            event_id = int(interaction.message.embeds[0].footer.text.split(": ")[1])
            event = await db.get_event(event_id)
        except: return await interaction.response.send_message("Erro buscar evento.", ephemeral=True)

        if not await self.check_manager_permission(interaction, event):
            return await interaction.response.send_message("❌ Apenas o Criador ou Gerentes podem apagar.", ephemeral=True)

        # 1. Notificar
        await notify_confirmed_users(interaction, event_id, f"⚠️ **Aviso:** O evento **{event['title']}** foi CANCELADO por {interaction.user.display_name}.")

        # 2. Resposta imediata
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("✅ Iniciando exclusão...", ephemeral=True)

        # 3. Deletar
        guild = interaction.guild
        if guild:
            try:
                channel = guild.get_channel(event['channel_id'])
                if channel: await channel.delete(reason="Apagado pelo usuário")
            except: pass
            try:
                role = guild.get_role(event['role_id'])
                if role: await role.delete(reason="Apagado pelo usuário")
            except: pass
        
        await db.delete_event(event_id)