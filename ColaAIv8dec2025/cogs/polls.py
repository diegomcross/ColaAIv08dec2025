import discord
from discord import app_commands
from discord.ext import commands
import config
import database as db
import json
# CORREÇÃO: Importação ajustada para a pasta cogs
from cogs.views_polls import PollBuilderView, VotingPollView

class PollsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="enquete_horario", description="Votação de horários (8h, 11h, 14h, 17h, 20h) para uma atividade.")
    @app_commands.describe(atividade="Nome da atividade (ex: Voto, Crota)")
    async def poll_when(self, interaction: discord.Interaction, atividade: str):
        # Validação de canal
        if interaction.channel_id != config.CHANNEL_POLLS:
            return await interaction.response.send_message(f"⚠️ Use o canal <#{config.CHANNEL_POLLS}>!", ephemeral=True)

        # Inicia o construtor privado
        view = PollBuilderView(self.bot, atividade)
        await interaction.response.send_message(
            f"🛠️ **Configurando enquete para: {atividade}**\nUse os menus abaixo para selecionar os dias e horários possíveis.", 
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

        # Montar opções
        options_list = [
            {'label': opcao1, 'value': opcao1},
            {'label': opcao2, 'value': opcao2}
        ]

        embed = discord.Embed(
            title=f"📊 Duelo: O que jogar em {quando}?",
            description=f"1️⃣ {opcao1}\n2️⃣ {opcao2}\n\n**Meta: 4 votos para confirmar.**",
            color=discord.Color.purple()
        )
        embed.set_footer(text="A enquete encerra automaticamente ao atingir a meta.")

        view = VotingPollView(self.bot, 'what', quando, options_list)
        msg = await interaction.channel.send(embed=embed, view=view)
        # Confirmação efêmera para quem criou
        await interaction.response.send_message("Enquete criada!", ephemeral=True)

        # Persistir
        target_data = json.dumps({'date_str': quando, 'options': options_list})
        await db.create_poll(msg.id, interaction.channel_id, interaction.guild.id, 'what', target_data)

async def setup(bot):
    await bot.add_cog(PollsCog(bot))