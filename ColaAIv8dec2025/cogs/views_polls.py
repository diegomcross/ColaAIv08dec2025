import discord
import database as db
import utils
import config
from constants import BR_TIMEZONE

class PollView(discord.ui.View):
    def __init__(self, bot, poll_type, target_data):
        super().__init__(timeout=None)
        self.bot = bot
        self.poll_type = poll_type
        self.target_data = target_data
        self.threshold = 3 if poll_type == 'when' else 4

    async def handle_vote(self, interaction: discord.Interaction, option: str):
        await interaction.response.defer()
        await db.add_poll_vote(interaction.message.id, interaction.user.id, option)
        
        votes = await db.get_poll_votes(interaction.message.id)
        vote_counts = {row['vote_option']: row['count'] for row in votes}
        
        embed = interaction.message.embeds[0]
        new_desc_lines = []
        winner_option = None
        base_desc = f"Meta para confirmar: **{self.threshold} votos**\n\n"
        
        for opt, count in vote_counts.items():
            if count >= self.threshold: winner_option = opt
            line = f"**{opt}**: {count} votos"
            if count >= self.threshold: line += " ✅ **CONFIRMADO**"
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
            final_dt = utils.parse_human_date("hoje 21h") 

        if not final_dt: return await interaction.channel.send("❌ Erro ao processar data.")

        official_name, act_type, slots = utils.detect_activity_details(final_title)
        if slots is None: slots = 6
        
        guild = interaction.guild
        role_name = f"{official_name[:15]} {final_dt.strftime('%d/%m')}"
        role = await guild.create_role(name=role_name, mentionable=True, reason="Enquete Vencedora")

        category = guild.get_channel(config.CATEGORY_EVENTS_ID)
        
        # Enquetes geralmente não têm descrição detalhada para pegar modo, mas passamos string vazia
        channel_name = utils.generate_channel_name(official_name, final_dt, act_type, slots, description="")
        
        if category: channel = await guild.create_text_channel(name=channel_name, category=category)
        else: channel = await guild.create_text_channel(name=channel_name)

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
        for child in self.children: child.disabled = True
        await interaction.message.edit(view=self)

class TimePollView(PollView):
    def __init__(self, bot, event_title, date_base):
        super().__init__(bot, 'when', event_title)
        times = ["19:00", "20:00", "21:00", "22:00"]
        for t in times: self.add_item(TimeButton(t, date_base))

class TimeButton(discord.ui.Button):
    def __init__(self, time_str, date_base):
        super().__init__(label=time_str, style=discord.ButtonStyle.primary, custom_id=f"poll_time_{time_str}")
        self.time_str = time_str
        self.date_base = date_base
    async def callback(self, interaction):
        await self.view.handle_vote(interaction, f"{self.date_base} {self.time_str}")

class ActivityPollView(PollView):
    def __init__(self, bot):
        super().__init__(bot, 'what', 'TBD')
        activities = ["Queda do Rei", "Fim de Crota", "Câmara de Cristal", "Deserto Perpétuo"]
        for act in activities: self.add_item(ActivityButton(act))

class ActivityButton(discord.ui.Button):
    def __init__(self, activity):
        super().__init__(label=activity, style=discord.ButtonStyle.secondary, custom_id=f"poll_act_{activity}")
        self.activity = activity
    async def callback(self, interaction):
        await self.view.handle_vote(interaction, self.activity)