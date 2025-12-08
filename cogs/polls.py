import discord
from discord import app_commands
from discord.ext import commands
import config
import database as db
import json
import utils
from cogs.views_polls import PollBuilderView, VotingPollView

class PollsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="enquete_quando", description="Votação de horários para uma atividade.")
    @app_commands.describe(atividade="Nome da atividade (ex: Voto, Crota)")
    async def poll_when(self, interaction: discord.Interaction, atividade: str):
        if interaction.channel_id != config.CHANNEL_POLLS:
            return await interaction.response.send_message(f"⚠️ Use o canal <#{config.CHANNEL_POLLS}>!", ephemeral=True)

        # Formata o nome da atividade para ficar bonito no título
        pretty_name = utils.format_activity_name(atividade)
        
        view = PollBuilderView(self.bot, pretty_name)
        await interaction.response.send_message(
            f"🛠️ **Configurando enquete para: {pretty_name}**\nSelecione o dia e clique em 'Lançar Enquete'.", 
            view=view, 
            ephemeral=True
        )

    @app_commands.command(name="enquete_atividade", description="Votação entre duas atividades para um horário fixo.")
    @app_commands.describe(
        quando="Data e Hora fixa (ex: Sabado 17h)",
        opcao1="Atividade 1 (ex: Deserto Epico)",
        opcao2="Atividade 2 (ex: Camara Mestre)"
    )
    async def poll_what(self, interaction: discord.Interaction, quando: str, opcao1: str, opcao2: str):
        if interaction.channel_id != config.CHANNEL_POLLS:
            return await interaction.response.send_message(f"⚠️ Use o canal <#{config.CHANNEL_POLLS}>!", ephemeral=True)

        # Formatação automática (Request 1)
        name1 = utils.format_activity_name(opcao1)
        name2 = utils.format_activity_name(opcao2)

        options_list = [
            {'label': name1, 'value': name1},
            {'label': name2, 'value': name2}
        ]

        embed = discord.Embed(
            title=f"📊 Duelo: O que jogar em {quando}?",
            description=f"1️⃣ {name1}\n2️⃣ {name2}\n\n**Meta: 4 votos para confirmar.**",
            color=discord.Color.purple()
        )
        embed.set_footer(text="A enquete encerra automaticamente ao atingir a meta.")

        target_data = json.dumps({'date_str': quando, 'options': options_list})

        view = VotingPollView(self.bot, 'what', target_data, options_list)
        msg = await interaction.channel.send(embed=embed, view=view)
        
        # Notificação no Chat Principal
        main_chat = interaction.guild.get_channel(config.CHANNEL_MAIN_CHAT)
        if main_chat:
            poll_channel = interaction.channel
            await main_chat.send(f"📢 **Duelo de Atividades!**\nEscolha o que jogar em {quando}: {poll_channel.mention}")

        await interaction.response.send_message("Enquete criada!", ephemeral=True)
        await db.create_poll(msg.id, interaction.channel_id, interaction.guild.id, 'what', target_data)

async def setup(bot):
    await bot.add_cog(PollsCog(bot))
