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
        self.threshold = 3 if poll_type == 'when' else 4

    async def handle_vote(self, interaction: discord.Interaction, option: str):
        await interaction.response.defer()
        user_id = interaction.user.id
        message_id = interaction.message.id
        
        has_voted = await db.check_user_vote_on_option(message_id, user_id, option)
        if has_voted:
            await db.remove_poll_vote_option(message_id, user_id, option)
        else:
            await db.add_poll_vote(message_id, user_id, option)
        
        votes = await db.get_poll_voters_detailed(message_id)
        
        vote_map = {}
        for row in votes:
            opt = row['vote_option']
            uid = row['user_id']
            if opt not in vote_map: vote_map[opt] = []
            vote_map[opt].append(uid)
            
        embed = interaction.message.embeds[0]
        new_desc_lines = []
        winner_option = None
        base_desc = f"Meta para confirmar: **{self.threshold} votos**\n\n"
        
        sorted_options = sorted(vote_map.items(), key=lambda x: len(x[1]), reverse=True)
        
        for opt, user_ids in sorted_options:
            count = len(user_ids)
            if count >= self.threshold and not winner_option: 
                winner_option = opt
            
            voter_names = []
            guild = interaction.guild
            for uid in user_ids:
                dname = await utils.get_user_display_name_static(uid, self.bot, guild)
                voter_names.append(utils.clean_voter_name(dname))
            
            names_str = ", ".join(voter_names)
            
            line = f"**{opt}** ({count}): {names_str}"
            if count >= self.threshold: line += " ✅"
            new_desc_lines.append(line)
            
        embed.description = base_desc + "\n".join(new_desc_lines)
        await interaction.message.edit(embed=embed)
        
        if winner_option:
            await self.trigger_event_creation(interaction, winner_option)

    async def trigger_event_creation(self, interaction, winner_value):
        poll = await db.get_poll_details(interaction.message.id)
        if poll and poll['status'] == 'closed': return
        await db.close_poll(interaction.message.id)

        final_title = ""
        final_dt = None
        
        if self.poll_type == 'when':
            final_title = self.target_data
            final_dt = utils.parse_human_date(winner_value)
        elif self.poll_type == 'what':
            final_title = winner_value
            try:
                data = json.loads(self.target_data)
                final_dt = utils.parse_human_date(data.get('date_str', 'hoje 21h'))
            except:
                final_dt = utils.parse_human_date("hoje 21h")

        if not final_dt: return await interaction.channel.send("❌ Erro ao processar data.")

        official_name, act_type, slots = utils.detect_activity_details(final_title)
        if slots is None: slots = 6
        
        guild = interaction.guild
        role_name = f"{official_name[:15]} {final_dt.strftime('%d/%m')}"
        role = await guild.create_role(name=role_name, mentionable=True, reason="Enquete Vencedora")

        category = guild.get_channel(config.CATEGORY_EVENTS_ID)
        channel_name = utils.generate_channel_name(official_name, final_dt, act_type, slots, description="Criado via Enquete")
        
        if category: channel = await guild.create_text_channel(name=channel_name, category=category)
        else: channel = await guild.create_text_channel(name=channel_name)

        from views import PersistentRsvpView
        embed_loading = discord.Embed(title="Gerando evento...", color=discord.Color.gold())
        msg = await channel.send(content=f"{role.mention} A comunidade decidiu!", embed=embed_loading, view=PersistentRsvpView())

        create_data = {
            'guild_id': guild.id, 'channel_id': channel.id, 'message_id': msg.id,
            'role_id': role.id, 'title': official_name, 'desc': "Criado via Enquete",
            'type': act_type, 'date': final_dt, 'slots': slots, 'creator': self.bot.user.id
        }
        event_id = await db.create_event(create_data)
        
        db_data = create_data.copy()
        db_data['event_id'] = event_id
        db_data['date_time'] = final_dt
        db_data['max_slots'] = slots
        
        winning_voters = await db.get_voters_for_option(interaction.message.id, winner_value)
        for uid in winning_voters:
            await db.update_rsvp(event_id, uid, 'confirmed')
            try:
                member = guild.get_member(uid)
                if member: await member.add_roles(role)
            except: pass
        
        rsvps = await db.get_rsvps(event_id)
        final_embed = await utils.build_event_embed(db_data, rsvps, self.bot)
        await msg.edit(embed=final_embed)
        
        await interaction.channel.send(f"🎉 Evento criado em {channel.mention} com {len(winning_voters)} confirmados!")
        
        try: await interaction.message.delete()
        except: pass

class VotingPollView(PollView):
    def __init__(self, bot, poll_type, target_data, options_list):
        super().__init__(bot, poll_type, target_data)
        for opt in options_list:
            label = opt.get('label', opt.get('value'))
            value = opt.get('value', label)
            self.add_item(VotingButton(label, value))

    @discord.ui.button(label="🗑️ Apagar", style=discord.ButtonStyle.danger, row=4)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Permissão simples: Apenas Admin ou quem criou (mas aqui não temos o criador fácil, então Admin/Mod)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("❌ Apenas Moderadores podem apagar enquetes.", ephemeral=True)
            
        await db.close_poll(interaction.message.id)
        await interaction.message.delete()
        await interaction.response.send_message("Enquete apagada.", ephemeral=True)

class VotingButton(discord.ui.Button):
    def __init__(self, label, value):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, custom_id=f"vote_{label[:20]}")
        self.value = value
    async def callback(self, interaction):
        await self.view.handle_vote(interaction, self.value)

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
        discord.SelectOption(label="Segunda-feira", value="Segunda"),
        discord.SelectOption(label="Terça-feira", value="Terça"),
        discord.SelectOption(label="Quarta-feira", value="Quarta"),
        discord.SelectOption(label="Quinta-feira", value="Quinta"),
        discord.SelectOption(label="Sexta-feira", value="Sexta"),
    ])
    async def select_day(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_day = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Lançar Enquete", style=discord.ButtonStyle.success)
    async def launch(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_day:
            return await interaction.response.send_message("⚠️ Selecione um dia primeiro!", ephemeral=True)
        
        raw_times = ["08:00", "11:00", "14:00", "17:00", "20:00", "22:00"]
        valid_times = [t for t in raw_times if int(t.split(':')[0]) <= 20]
        
        options_list = []
        for t in valid_times:
            full_opt = f"{self.selected_day} {t}"
            options_list.append({'label': t, 'value': full_opt})
            
        poll_view = VotingPollView(self.bot, 'when', self.activity_name, options_list)
        
        embed = discord.Embed(
            title=f"📊 Enquete de Horário: {self.activity_name}",
            description=f"**Dia:** {self.selected_day}\n\nMeta para confirmar: **3 votos** no mesmo horário.\n*Você pode votar em mais de um horário!*",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Vote clicando nos botões abaixo. (Clique novamente para remover)")
        
        try:
            poll_channel = interaction.channel
            msg = await poll_channel.send(embed=embed, view=poll_view)
            await db.create_poll(msg.id, poll_channel.id, interaction.guild.id, 'when', self.activity_name)
            
            main_chat = interaction.guild.get_channel(config.CHANNEL_MAIN_CHAT)
            if main_chat and interaction.channel_id != config.CHANNEL_MAIN_CHAT:
                await main_chat.send(f"📢 **Nova Enquete Disponível!**\nVamos jogar **{self.activity_name}**? Vote no horário aqui: {msg.jump_url}")

            await interaction.followup.send(f"✅ Enquete lançada!", ephemeral=True)
            self.stop()
        except Exception as e:
            await interaction.followup.send(f"Erro ao criar enquete: {e}", ephemeral=True)
