import discord
import database as db
import utils
from constants import BR_TIMEZONE
import datetime
import re

async def notify_confirmed_users(interaction: discord.Interaction, event_id: int, message: str):
    try:
        rsvps = await db.get_rsvps(event_id)
        confirmed_ids = [r['user_id'] for r in rsvps if r['status'] == 'confirmed']
        for uid in confirmed_ids:
            if uid == interaction.user.id: continue
            try:
                user = interaction.client.get_user(uid) or await interaction.client.fetch_user(uid)
                await user.send(message)
            except: pass
    except Exception as e: print(f"[NOTIFY ERROR] {e}")

class EventEditModal(discord.ui.Modal, title="Editar Evento"):
    def __init__(self, event_data, bot):
        super().__init__()
        self.event_data = event_data
        self.bot = bot
        self.title_input = discord.ui.TextInput(label="Título", default=event_data['title'])
        self.add_item(self.title_input)
        self.desc_input = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph, required=False, default=event_data['description'] or "")
        self.add_item(self.desc_input)
        
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
        
        old_date_str = self.date_input.default
        new_date_str = new_dt.strftime("%d/%m %H:%M")
        date_changed = old_date_str != new_date_str
        
        msg_notification = f"📝 **Evento Editado:** O evento **{official_name}** foi alterado por {interaction.user.display_name}."
        if date_changed: msg_notification = f"📅 **DATA ALTERADA:** O evento **{official_name}** foi remarcado para **{new_dt.strftime('%d/%m às %H:%M')}**."

        await db.update_event_details(self.event_data['event_id'], official_name, self.desc_input.value, new_dt, act_type, slots)
        await notify_confirmed_users(interaction, self.event_data['event_id'], msg_notification)
        
        event = await db.get_event(self.event_data['event_id'])
        rsvps = await db.get_rsvps(self.event_data['event_id'])
        embed = await utils.build_event_embed(dict(event), rsvps, self.bot)
        
        channel = interaction.guild.get_channel(event['channel_id'])
        if channel:
            try:
                msg = await channel.fetch_message(event['message_id'])
                await msg.edit(embed=embed)
                confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
                free_slots = max(0, slots - confirmed_count)
                new_name = utils.generate_channel_name(official_name, new_dt, act_type, free_slots, description=self.desc_input.value)
                if channel.name != new_name:
                    try: await channel.edit(name=new_name)
                    except: pass
                if date_changed: await channel.send(f"📢 {interaction.user.mention} alterou a data para **{new_dt.strftime('%d/%m às %H:%M')}**!")
                await interaction.followup.send("✅ Evento atualizado!", ephemeral=True)
            except Exception as e: await interaction.followup.send(f"Erro visual: {e}", ephemeral=True)

class PersistentRsvpView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    async def update_event_embed(self, interaction: discord.Interaction, event_id: int):
        try:
            event = await db.get_event(event_id)
            if not event: return
            rsvps = await db.get_rsvps(event_id)
            confirmed = [r for r in rsvps if r['status'] == 'confirmed']
            waitlist = [r for r in rsvps if r['status'] == 'waitlist']
            slots = event['max_slots']
            changed = False
            while len(confirmed) < slots and len(waitlist) > 0:
                lucky = waitlist.pop(0) 
                await db.update_rsvp(event_id, lucky['user_id'], 'confirmed')
                confirmed.append(lucky); changed = True
            if changed: rsvps = await db.get_rsvps(event_id)
            embed = await utils.build_event_embed(dict(event), rsvps, interaction.client)
            await interaction.message.edit(embed=embed)
        except Exception as e: print(f"[UPDATE ERROR] {e}")

    async def handle_click(self, interaction: discord.Interaction, status: str):
        # FIX: Immediate defer to prevent timeouts
        await interaction.response.defer(ephemeral=True)
        try:
            # FIX: Regex extraction instead of brittle split
            if not interaction.message.embeds: return await interaction.followup.send("Erro: Embed sumiu.", ephemeral=True)
            footer_text = interaction.message.embeds[0].footer.text
            match = re.search(r'\d+', footer_text)
            if not match: return await interaction.followup.send("Erro: ID não encontrado.", ephemeral=True)
            event_id = int(match.group())
            
            event = await db.get_event(event_id)
            if not event: return await interaction.followup.send("❌ Evento deletado.", ephemeral=True)

            rsvps = await db.get_rsvps(event_id)
            confirmed_count = len([r for r in rsvps if r['status'] == 'confirmed'])
            
            final_status = status
            if status == 'confirmed':
                user_current = next((r for r in rsvps if r['user_id'] == interaction.user.id), None)
                is_confirmed = user_current and user_current['status'] == 'confirmed'
                if confirmed_count >= event['max_slots'] and not is_confirmed:
                    final_status = 'waitlist'
                    await interaction.followup.send("⚠️ Cheio! Entrou na **Lista de Espera**.", ephemeral=True)
                else: await interaction.followup.send("✅ Confirmado!", ephemeral=True)
            elif status == 'absent': await interaction.followup.send("❌ Ausente.", ephemeral=True)
            elif status == 'maybe': await interaction.followup.send("🔷 Talvez.", ephemeral=True)

            await db.update_rsvp(event_id, interaction.user.id, final_status)
            role = interaction.guild.get_role(event['role_id'])
            if role:
                try:
                    if final_status in ['confirmed', 'waitlist']: await interaction.user.add_roles(role)
                    else: await interaction.user.remove_roles(role)
                except: pass
            await self.update_event_embed(interaction, event_id)
        except Exception as e:
            print(f"[HANDLE CLICK ERROR] {e}")
            await interaction.followup.send("Erro interno.", ephemeral=True)

    async def check_manager_permission(self, interaction: discord.Interaction, event):
        if interaction.user.id == event['creator_id']: return True
        if interaction.user.guild_permissions.administrator: return True
        manager_id = await db.get_manager_id(interaction.guild.id)
        if manager_id:
            if interaction.user.id == manager_id: return True
            if interaction.user.get_role(manager_id): return True
        return False

    @discord.ui.button(label="Vou", style=discord.ButtonStyle.secondary, custom_id="rsvp_yes", emoji="✅")
    async def btn_yes(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 'confirmed')
    @discord.ui.button(label="Não Vou", style=discord.ButtonStyle.secondary, custom_id="rsvp_no", emoji="❌")
    async def btn_no(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 'absent')
    @discord.ui.button(label="Talvez", style=discord.ButtonStyle.secondary, custom_id="rsvp_maybe", emoji="🔷")
    async def btn_maybe(self, interaction: discord.Interaction, button: discord.ui.Button): await self.handle_click(interaction, 'maybe')

    @discord.ui.button(label="Editar", style=discord.ButtonStyle.primary, custom_id="btn_edit", emoji="✏️", row=1)
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Edição exige Modal, então não pode Defer
        try:
            footer_text = interaction.message.embeds[0].footer.text
            match = re.search(r'\d+', footer_text)
            if not match: return await interaction.response.send_message("Erro ID.", ephemeral=True)
            event_id = int(match.group())
            event = await db.get_event(event_id)
            if not event: return await interaction.response.send_message("Evento não encontrado.", ephemeral=True)
            if not await self.check_manager_permission(interaction, event): return await interaction.response.send_message("Sem permissão.", ephemeral=True)
            await interaction.response.send_modal(EventEditModal(dict(event), interaction.client))
        except Exception as e: print(f"[EDIT ERROR] {e}")

    @discord.ui.button(label="Apagar", style=discord.ButtonStyle.danger, custom_id="btn_delete", emoji="🗑️", row=1)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            footer_text = interaction.message.embeds[0].footer.text
            match = re.search(r'\d+', footer_text)
            if not match: return await interaction.followup.send("Erro ID.", ephemeral=True)
            event_id = int(match.group())
            event = await db.get_event(event_id)
            if not event: return await interaction.followup.send("Já apagado.", ephemeral=True)
            if not await self.check_manager_permission(interaction, event): return await interaction.followup.send("Sem permissão.", ephemeral=True)
            
            await notify_confirmed_users(interaction, event_id, f"⚠️ **Aviso:** O evento **{event['title']}** foi CANCELADO.")
            await interaction.followup.send("✅ Apagando...", ephemeral=True)
            guild = interaction.guild
            if guild:
                try: 
                    c = guild.get_channel(event['channel_id'])
                    if c: await c.delete(reason="User Delete")
                except: pass
                try: 
                    r = guild.get_role(event['role_id'])
                    if r: await r.delete(reason="User Delete")
                except: pass
            await db.delete_event(event_id)
        except Exception as e: print(f"[DELETE ERROR] {e}")
