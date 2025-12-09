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

    def is_allowed_channel(self, interaction: discord.Interaction) -> bool:
        # Permite no Main Chat OU no LFG (Procure Atividades)
        return interaction.channel_id in [config.CHANNEL_MAIN_CHAT, config.CHANNEL_LFG]

    @app_commands.command(name="enquete_quando", description="Votação de horários para uma atividade.")
    @app_commands.describe(atividade="Nome da atividade (ex: Voto, Crota)")
    async def poll_when(self, interaction: discord.Interaction, atividade: str):
        if not self.is_allowed_channel(interaction):
            return await interaction.response.send_message(
                f"⚠️ Use este comando em <#{config.CHANNEL_MAIN_CHAT}> ou <#{config.CHANNEL_LFG}>!", 
                ephemeral=True
            )

        pretty_name = utils.format_activity_name(atividade)
        
        view = PollBuilderView(self.bot, pretty_name)
        await interaction.response.send_message(
            f"🛠️ **Configurando enquete para: {pretty_name}**\nSelecione o dia e clique em 'Lançar Enquete'.", 
            view=view, 
            ephemeral=True
        )

    @app_commands.command(name="enquete_atividade", description="Votação entre até 6 atividades para um horário fixo.")
    @app_commands.describe(
        quando="Data e Hora fixa (ex: Sabado 17h)",
        opcao1="Atividade 1", opcao2="Atividade 2", 
        opcao3="Atividade 3 (Opcional)", opcao4="Atividade 4 (Opcional)",
        opcao5="Atividade 5 (Opcional)", opcao6="Atividade 6 (Opcional)"
    )
    async def poll_what(self, interaction: discord.Interaction, quando: str, 
                        opcao1: str, opcao2: str, 
                        opcao3: str = None, opcao4: str = None, 
                        opcao5: str = None, opcao6: str = None):
        
        if not self.is_allowed_channel(interaction):
            return await interaction.response.send_message(
                f"⚠️ Use este comando em <#{config.CHANNEL_MAIN_CHAT}> ou <#{config.CHANNEL_LFG}>!", 
                ephemeral=True
            )

        # Coletar todas as opções preenchidas
        raw_options = [opcao1, opcao2, opcao3, opcao4, opcao5, opcao6]
        valid_options = [opt for opt in raw_options if opt] # Remove None/Vazio

        # Formatar nomes
        options_list = []
        desc_lines = []
        for i, opt in enumerate(valid_options):
            fmt_name = utils.format_activity_name(opt)
            options_list.append({'label': fmt_name, 'value': fmt_name})
            # Emojis numéricos para o Embed (1️⃣, 2️⃣...)
            emoji_num = f"{i+1}\ufe0f\u20e3"
            desc_lines.append(f"{emoji_num} {fmt_name}")

        desc_text = "\n".join(desc_lines)
        
        embed = discord.Embed(
            title=f"📊 Qual atividade jogar em {quando}?",
            description=f"{desc_text}\n\n**Meta: 4 votos para confirmar.**\n*Você pode votar em múltiplas opções!*",
            color=discord.Color.purple()
        )
        embed.set_footer(text="A enquete encerra automaticamente ao atingir a meta.")

        target_data = json.dumps({'date_str': quando, 'options': options_list})

        view = VotingPollView(self.bot, 'what', target_data, options_list)
        msg = await interaction.channel.send(embed=embed, view=view)
        
        # Notificação no chat principal (se não foi criado lá)
        main_chat = interaction.guild.get_channel(config.CHANNEL_MAIN_CHAT)
        if main_chat and interaction.channel_id != config.CHANNEL_MAIN_CHAT:
            await main_chat.send(f"📢 **Duelo de Atividades!**\nEscolha o que jogar em {quando}: {msg.jump_url}")

        await interaction.response.send_message("Enquete criada!", ephemeral=True)
        await db.create_poll(msg.id, interaction.channel_id, interaction.guild.id, 'what', target_data)

async def setup(bot):
    await bot.add_cog(PollsCog(bot))
