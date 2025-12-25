import discord
import database as db
import utils
import config
import json
import datetime
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
        
        # 1. Lógica de Toggle (Votos Múltiplos)
        has_voted = await db.check_user_vote_on_option(message_id, user_id, option)
        
        if has_voted:
            await db.remove_poll_vote_option(message_id, user_id, option)
        else:
            await db.add_poll_vote(message_id, user_id, option)
        
        # 2. Recuperar Votos
        votes = await db.get_poll_voters_detailed(message_id)
        
        vote_map = {}
        for row in votes:
            opt = row['vote_option']
            uid = row['user_id']
            if opt not in vote_map: vote_map[opt] = []
            vote_map[opt].append(uid)
            
        # 3. Recuperar TODAS as opções (incluindo as com 0 votos) dos botões
        all_options = []
        for child in self.children:
            if isinstance(child, VotingButton) and child.value not in all_options:
                all_options.append(child.value)

        # 4. Reconstruir Embed com Design "Suggestion C"
        embed = interaction.message.embeds[0]
        new_desc_lines = []
        winner_option = None
        
        # Ordena opções: primeiro por número de votos (decrescente), depois alfabético
        sorted_options = sorted(all_options, key=lambda x: len(vote_map.get(x, [])), reverse=True)
        
        for opt in sorted_options:
            user_ids = vote_map.get(opt, [])
            count = len(user_ids)
            
            # Checa Vencedor
            if count >= self.threshold and not winner_option: 
                winner_option = opt
            
            # Formata Nomes
            voter_names = []
            guild = interaction.guild
            for uid in user_ids:
                dname = await utils.get_user_display_name_static(uid, self.bot, guild)
                voter_names.append(utils.clean_voter_name(dname))
            names_str = ", ".join(voter_names) if voter_names else "-"

            # --- ESTILIZAÇÃO VISUAL ---
            if self.poll_type == 'when':
                # Parse para Timestamp Dinâmico (<t:XXX:F>)
                try:
                    dt = utils.parse_human_date(opt)
                    # Fallback visual se o parse falhar (usa o texto original)
                    date_display = f"<t:{int(dt.timestamp())}:F>" if dt else opt
                except:
                    date_display = opt
                
                check_mark = "✅" if count >= self.threshold else ""
                line = f"🗓️ **{date_display}** {check_mark}\n`{count}` Votos: {names_str}\n"
                
            else:
                # Estilo para Atividades (Poll What)
                check_mark = "✅" if count >= self.threshold else ""
                line = f"**{opt}** {check_mark}\n`{count}` Votos: {names_str}\n"

            new_desc_lines.append(line)
            
        base_desc = f"Meta para confirmar: **{self.threshold} votos**\n\n"
        embed.description = base_desc + "".join(new_desc_lines)
        await interaction.message.edit(embed=embed)
        
        # 5. Disparar criação se venceu
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
        
        # --- FIX DE DATA CONCRETA ---
        # Resolve "Sexta-feira" para uma data real (ex: "2025-12-26")
        # Isso impede que o poll "quebre" se durar mais de uma semana
        base_dt = utils.parse_human_date(self.selected_day)
        if not base_dt:
            return await interaction.followup.send("Erro ao calcular data.", ephemeral=True)
        
        date_str_concrete = base_dt.strftime("%Y-%m-%d")
        
        raw_times = ["08:00", "11:00", "14:00", "17:00", "20:00", "22:00"]
        valid_times = [t for t in raw_times if int(t.split(':')[0]) <= 22]
        
        options_list = []
        desc_lines = []
        
        for t in valid_times:
            # Value = Data Concreta + Hora (Para estabilidade do DB e Timestamp)
            full_opt = f"{date_str_concrete} {t}"
            
            # Label = Apenas Hora (Para o botão ficar limpo)
            options_list.append({'label': t, 'value': full_opt})
            
            # Monta a linha inicial do Embed com Timestamp
            try:
                dt_opt = utils.parse_human_date(full_opt)
                ts_display = f"<t:{int(dt_opt.timestamp())}:F>"
            except:
                ts_display = full_opt
            
            desc_lines.append(f"🗓️ **{ts_display}**\n0 Votos: -\n")
            
        poll_view = VotingPollView(self.bot, 'when', self.activity_name, options_list)
        
        embed = discord.Embed(
            title=f"📊 Horário: {self.activity_name}",
            description=f"Meta para confirmar: **3 votos**\n\n" + "".join(desc_lines),
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
