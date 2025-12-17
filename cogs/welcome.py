import discord
from discord.ext import commands
from discord import ui
import config
import discord
from discord.ext import commands
from discord import ui
import config

class SetupModal(ui.Modal, title="Registro no Clã"):
    bungie_id = ui.TextInput(label="Seu Bungie ID (Ex: Nome#1234)", placeholder="Guardian#1234", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        raw_input = self.bungie_id.value
        
        # Remove a hashtag e números para o apelido no servidor
        # Ex: "Portador das Trevas#7062" -> "Portador das Trevas"
        new_nick = raw_input.split('#')[0].strip()
        
        # --- CORREÇÃO DO ERRO ---
        # Como o Modal é enviado na DM, interaction.user é um 'User' (genérico).
        # Precisamos encontrar o 'Member' (membro do servidor) correspondente para alterar o nick.
        member = None
        for guild in interaction.client.guilds:
            member = guild.get_member(interaction.user.id)
            if member:
                break # Encontrou o membro no servidor do bot
        
        if not member:
            await interaction.response.send_message("❌ Erro: Não consegui te encontrar no servidor do Discord. Verifique se você entrou corretamente.", ephemeral=True)
            return
        # -------------------------

        try:
            # Edita o MEMBRO encontrado no servidor, e não o usuário da DM
            await member.edit(nick=new_nick[:32])
            await interaction.response.send_message(f"✅ Nome alterado para **{new_nick}** no servidor!", ephemeral=True)
            
            # Envia a próxima etapa (Termo de Voz)
            view = VoiceAgreementView()
            await interaction.user.send("Quase lá! Para manter a ordem no clã, precisamos que concorde com uma regra simples:", view=view)
            
        except discord.Forbidden:
            # Se o bot não tiver permissão (ex: o usuário é dono/admin), avisa mas segue o fluxo
            await interaction.response.send_message(f"⚠️ Registrado como **{new_nick}**, mas não consegui alterar seu apelido no servidor (sem permissão).", ephemeral=True)
            view = VoiceAgreementView()
            await interaction.user.send("Quase lá! Para manter a ordem no clã, precisamos que concorde com uma regra simples:", view=view)
            
        except Exception as e:
            await interaction.response.send_message(f"Erro ao processar: {e}", ephemeral=True)

class VoiceAgreementView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Eu vou participar dos canais de voz", style=discord.ButtonStyle.green, emoji="🎙️")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        button.disabled = True
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
        
        # 1. Envia DM de Configuração (Privado)
        try:
            embed = discord.Embed(
                title=f"Bem-vindo(a) ao Clã, {member.name}!",
                description="Antes de começar, precisamos configurar seu perfil para bater com o jogo.",
                color=discord.Color.gold()
            )
            # Link genérico da Bungie
            embed.add_field(name="🔗 Link do Clã na Bungie", value="[Clique aqui para solicitar entrada no Clã](https://www.bungie.net)", inline=False)
            embed.set_footer(text="Clique abaixo para configurar seu nome.")
            
            await member.send(embed=embed, view=SetupView())
            print(f"[WELCOME] DM enviada para {member.name}")
            
        except discord.Forbidden:
            print(f"[WELCOME] Não consegui enviar DM para {member.name} (Privacidade fechada).")
        except Exception as e:
            print(f"[WELCOME] Erro ao processar entrada de {member.name}: {e}")

        # 2. Anuncia no Chat Principal (Público)
        try:
            main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
            if main_chat:
                await main_chat.send(
                    f"👋 **Olhos para cima, Guardiões!**\n"
                    f"Um novo membro acabou de pousar na Torre: Seja bem-vindo(a), {member.mention}! 🚀\n"
                    f"Não esqueça de conferir sua DM para finalizar o registro."
                )
        except Exception as e:
            print(f"[WELCOME] Erro ao enviar msg no chat principal: {e}")

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
class SetupModal(ui.Modal, title="Registro no Clã"):
    bungie_id = ui.TextInput(label="Seu Bungie ID (Ex: Nome#1234)", placeholder="Guardian#1234", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        raw_input = self.bungie_id.value
        
        # Remove a hashtag e números para o apelido no servidor
        new_nick = raw_input.split('#')[0].strip()
        
        try:
            await interaction.user.edit(nick=new_nick[:32])
            await interaction.response.send_message(f"✅ Nome alterado para **{new_nick}**!", ephemeral=True)
            
            view = VoiceAgreementView()
            await interaction.user.send("Quase lá! Para manter a ordem no clã, precisamos que concorde com uma regra simples:", view=view)
            
        except discord.Forbidden:
            await interaction.response.send_message(f"⚠️ Registrado como **{new_nick}**, mas não consegui alterar seu apelido no servidor (sem permissão).", ephemeral=True)
            view = VoiceAgreementView()
            await interaction.user.send("Quase lá! Para manter a ordem no clã, precisamos que concorde com uma regra simples:", view=view)
            
        except Exception as e:
            await interaction.response.send_message(f"Erro ao processar: {e}", ephemeral=True)

class VoiceAgreementView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Eu vou participar dos canais de voz", style=discord.ButtonStyle.green, emoji="🎙️")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        button.disabled = True
        await interaction.response.edit_message(content="✅ **Termo aceito!** Bem-vindo oficialmente ao esquadrão.", view=None)
        
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
        
        # 1. Envia DM de Configuração (Privado)
        try:
            embed = discord.Embed(
                title=f"Bem-vindo(a) ao Clã, {member.name}!",
                description="Antes de começar, precisamos configurar seu perfil para bater com o jogo.",
                color=discord.Color.gold()
            )
            # Link genérico da Bungie, substitua pelo seu link de clã se tiver
            embed.add_field(name="🔗 Link do Clã na Bungie", value="[Clique aqui para solicitar entrada no Clã](https://www.bungie.net)", inline=False)
            embed.set_footer(text="Clique abaixo para configurar seu nome.")
            
            await member.send(embed=embed, view=SetupView())
            print(f"[WELCOME] DM enviada para {member.name}")
            
        except discord.Forbidden:
            print(f"[WELCOME] Não consegui enviar DM para {member.name} (Privacidade fechada).")
        except Exception as e:
            print(f"[WELCOME] Erro ao processar entrada de {member.name}: {e}")

        # 2. Anuncia no Chat Principal (Público)
        try:
            main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
            if main_chat:
                await main_chat.send(
                    f"👋 **Olhos para cima, Guardiões!**\n"
                    f"Um novo membro acabou de pousar na Torre: Seja bem-vindo(a), {member.mention}! 🚀\n"
                    f"Não esqueça de conferir sua DM para finalizar o registro."
                )
        except Exception as e:
            print(f"[WELCOME] Erro ao enviar msg no chat principal: {e}")

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
