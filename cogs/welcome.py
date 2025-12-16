import discord
from discord.ext import commands
from discord import ui
import config

class SetupModal(ui.Modal, title="Registro no Clã"):
    bungie_id = ui.TextInput(label="Seu Bungie ID (Ex: Nome#1234)", placeholder="Guardian#1234", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        new_nick = self.bungie_id.value
        # Tenta renomear
        try:
            # Remove a tag #1234 se quiser deixar só o nome, ou mantém tudo.
            # O pedido foi "dar match", então usaremos o nome completo ou simplificado.
            # Vamos simplificar visualmente removendo números se preferir, ou manter full.
            # Vou manter full para ser exato.
            await interaction.user.edit(nick=new_nick[:32]) # Limite discord 32 chars
            await interaction.response.send_message(f"✅ Nome alterado para **{new_nick}**!", ephemeral=True)
            
            # Envia a próxima etapa (Termo de Voz)
            view = VoiceAgreementView()
            await interaction.user.send("Quase lá! Para manter a ordem no clã, precisamos que concorde com uma regra simples:", view=view)
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ Não consegui mudar seu apelido (sem permissão). Mas seu ID foi registrado!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Erro: {e}", ephemeral=True)

class VoiceAgreementView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Eu vou participar dos canais de voz", style=discord.ButtonStyle.green, emoji="🎙️")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="✅ **Termo aceito!** Bem-vindo oficialmente ao esquadrão.", view=None)
        
        # Envia Tutorial Final
        embed = discord.Embed(title="📚 Guia Rápido do ColaAI", color=discord.Color.purple())
        embed.add_field(name="📅 Agendar Jogos", value="Use `/agendar` em qualquer canal de texto para criar uma Raid ou atividade.", inline=False)
        embed.add_field(name="📊 Enquetes", value="Use `/enquete_atividade` para decidir o que jogar ou `/enquete_quando` para decidir a hora.", inline=False)
        embed.add_field(name="📌 Emojis", value="💀 Raids\n🗡️ Masmorras\n⚔️ PvP\n⭐ Atividades Mestre/Desafio", inline=False)
        embed.set_footer(text="Dúvidas? Chame um Moderador.")
        
        await interaction.user.send(embed=embed)

class SetupView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📝 Registrar Bungie ID", style=discord.ButtonStyle.primary)
    async def start_setup(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SetupModal())

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Dispara quando alguém entra no servidor."""
        try:
            embed = discord.Embed(
                title=f"Bem-vindo(a) ao Clã, {member.name}!",
                description="Antes de começar, precisamos configurar seu perfil para bater com o jogo.",
                color=discord.Color.gold()
            )
            embed.add_field(name="🔗 Link do Clã na Bungie", value="[Clique aqui para solicitar entrada no Clã](https://www.bungie.net/en/ClanV2?groupid=SEU_ID_AQUI)", inline=False)
            embed.set_footer(text="Clique abaixo para configurar seu nome.")
            
            await member.send(embed=embed, view=SetupView())
            
        except discord.Forbidden:
            print(f"[WELCOME] Não consegui enviar DM para {member.name} (Privacidade fechada).")

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
