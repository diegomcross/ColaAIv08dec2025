import discord
from discord.ext import commands
from discord import ui
import config
import re

# --- MÁQUINA DE ESTADOS DO ONBOARDING (WIZARD) ---

class VoiceAgreementView(ui.View):
    def __init__(self, member):
        super().__init__(timeout=None)
        self.member = member

    @ui.button(label="Concordo em participar dos canais de voz", style=discord.ButtonStyle.green, emoji="🎙️")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        # Atribui cargo de Aceite
        role = self.member.guild.get_role(config.ROLE_VOICE_ACCEPTED)
        if role: await self.member.add_roles(role)
        
        # Embed Final com Link
        embed = discord.Embed(title="🎉 Iniciação Concluída!", description="Bem-vindo oficialmente ao esquadrão.", color=discord.Color.purple())
        embed.add_field(name="🚀 Próximo Passo", value=f"[Clique aqui para aplicar no Clã na Bungie]({config.BUNGIE_CLAN_LINK})", inline=False)
        embed.add_field(name="📚 Guia Rápido", value="Use `/agendar` para criar eventos.\nUse `/enquete_atividade` para sugerir jogos.", inline=False)
        
        await interaction.message.edit(content=None, embed=embed, view=None)

    @ui.button(label="Não concordo", style=discord.ButtonStyle.red)
    async def disagree(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        # Atribui cargo de Rejeição
        role = self.member.guild.get_role(config.ROLE_VOICE_REJECTED)
        if role: await self.member.add_roles(role)
        
        await interaction.message.edit(content="⚠️ **Entendido.** Sem a participação em voz, o acesso ao clã será limitado. Procure um administrador se mudar de ideia.", view=None)

class QuestionExperienceView(ui.View):
    def __init__(self, member):
        super().__init__(timeout=180)
        self.member = member

    async def apply_role_and_next(self, interaction, role_id):
        await interaction.response.defer()
        role = self.member.guild.get_role(role_id)
        if role: await self.member.add_roles(role)
        
        embed = discord.Embed(title="4. Termo de Compromisso", description="Você entende que a participação nos **Canais de Voz** é obrigatória durante as atividades do clã?", color=discord.Color.red())
        await interaction.message.edit(embed=embed, view=VoiceAgreementView(self.member))

    @ui.button(label="Novato", style=discord.ButtonStyle.secondary)
    async def btn_novato(self, interaction: discord.Interaction, button: ui.Button): await self.apply_role_and_next(interaction, config.ROLE_XP_NOVATO)
    
    @ui.button(label="Iniciado", style=discord.ButtonStyle.secondary)
    async def btn_iniciado(self, interaction: discord.Interaction, button: ui.Button): await self.apply_role_and_next(interaction, config.ROLE_XP_INICIADO)

    @ui.button(label="Experiente", style=discord.ButtonStyle.primary)
    async def btn_expert(self, interaction: discord.Interaction, button: ui.Button): await self.apply_role_and_next(interaction, config.ROLE_XP_EXPERIENTE)

    @ui.button(label="Rank 11", style=discord.ButtonStyle.primary, emoji="🔥")
    async def btn_rank11(self, interaction: discord.Interaction, button: ui.Button): await self.apply_role_and_next(interaction, config.ROLE_XP_RANK11)

class QuestionFrequencyView(ui.View):
    def __init__(self, member):
        super().__init__(timeout=180)
        self.member = member

    async def next_step(self, interaction, role_id=None):
        await interaction.response.defer()
        if role_id:
            role = self.member.guild.get_role(role_id)
            if role: await self.member.add_roles(role)
            
        embed = discord.Embed(title="3. Nível de Experiência", description="Como você classificaria seu conhecimento no Destiny 2?", color=discord.Color.blue())
        await interaction.message.edit(embed=embed, view=QuestionExperienceView(self.member))

    @ui.button(label="1-2x por semana", style=discord.ButtonStyle.secondary)
    async def btn_rare(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_FREQ_RARA)

    @ui.button(label="3-4x por semana", style=discord.ButtonStyle.secondary)
    async def btn_med(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction)

    @ui.button(label="Quase todos os dias", style=discord.ButtonStyle.success)
    async def btn_high(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction)

    @ui.button(label="Raramente", style=discord.ButtonStyle.secondary)
    async def btn_very_rare(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_FREQ_RARA)

    @ui.button(label="Quase não tenho tempo", style=discord.ButtonStyle.danger)
    async def btn_no_time(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_FREQ_SEM_TEMPO)

class QuestionStyleView(ui.View):
    def __init__(self, member):
        super().__init__(timeout=180)
        self.member = member

    async def apply_role_and_next(self, interaction, role_id):
        await interaction.response.defer()
        role = self.member.guild.get_role(role_id)
        if role: await self.member.add_roles(role)
        
        embed = discord.Embed(title="2. Frequência de Jogo", description="Com que frequência você costuma jogar?", color=discord.Color.blue())
        await interaction.message.edit(embed=embed, view=QuestionFrequencyView(self.member))

    @ui.button(label="Solo", style=discord.ButtonStyle.secondary, emoji="👤")
    async def btn_solo(self, interaction: discord.Interaction, button: ui.Button): await self.apply_role_and_next(interaction, config.ROLE_SOLO)

    @ui.button(label="Grupo", style=discord.ButtonStyle.success, emoji="👥")
    async def btn_grupo(self, interaction: discord.Interaction, button: ui.Button): await self.apply_role_and_next(interaction, config.ROLE_GRUPO)

class SetupModal(ui.Modal, title="Registro no Clã"):
    bungie_id = ui.TextInput(label="Seu Bungie ID", placeholder="Nome#1234 (com ou sem espaços)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        raw_input = self.bungie_id.value
        
        # FIX: Sanitização robusta para remover espaços extras
        # Ex: " Nome # 1234 " vira "Nome#1234"
        clean_id = re.sub(r'\s*#\s*', '#', raw_input.strip())
        
        # Pega o nome antes da cerquilha para o Discord
        new_nick = clean_id.split('#')[0]
        
        # Busca o membro no servidor (não na DM)
        member = None
        for guild in interaction.client.guilds:
            member = guild.get_member(interaction.user.id)
            if member: break
        
        if not member:
            return await interaction.response.send_message("❌ Não te encontrei no servidor do Discord. Entre lá primeiro!", ephemeral=True)

        try:
            await member.edit(nick=new_nick[:32])
            await interaction.response.send_message(f"✅ Identificado como **{new_nick}**!", ephemeral=True)
            
            # Inicia o Quiz
            embed = discord.Embed(title="1. Estilo de Jogo", description="Você costuma jogar mais sozinho ou em grupo?", color=discord.Color.blue())
            await interaction.user.send(embed=embed, view=QuestionStyleView(member))
            
        except discord.Forbidden:
            await interaction.response.send_message(f"✅ Registrado como **{new_nick}** (sem permissão para alterar apelido).", ephemeral=True)
            embed = discord.Embed(title="1. Estilo de Jogo", description="Você costuma jogar mais sozinho ou em grupo?", color=discord.Color.blue())
            await interaction.user.send(embed=embed, view=QuestionStyleView(member))
        except Exception as e:
            await interaction.response.send_message(f"Erro: {e}", ephemeral=True)

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- LISTENER DE MENSAGENS (DM) ---
    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignora mensagens do próprio bot
        if message.author.bot: return
        
        # Verifica se é DM
        if isinstance(message.channel, discord.DMChannel):
            # Lógica simples de intenção (pode ser melhorada com Regex)
            keywords = ["entrar", "join", "clan", "clã", "participar", "convite", "vaga"]
            if any(word in message.content.lower() for word in keywords):
                
                # Verifica se o usuário está em algum servidor que o bot conhece
                member = None
                for guild in self.bot.guilds:
                    member = guild.get_member(message.author.id)
                    if member: break
                
                if member:
                    await message.channel.send("👋 Olá! Vi que você quer se juntar ao clã. Vamos configurar seu perfil rapidinho.\nClique no botão abaixo para informar seu Bungie ID.", view=SetupStartView())
                else:
                    await message.channel.send("❌ Você precisa entrar no nosso servidor do Discord primeiro para iniciar o registro.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Dispara quando alguém entra no servidor."""
        try:
            embed = discord.Embed(
                title=f"Bem-vindo(a) ao Clã, {member.name}!",
                description="Vamos configurar seu perfil para bater com o jogo.",
                color=discord.Color.gold()
            )
            embed.set_footer(text="Clique abaixo para começar.")
            await member.send(embed=embed, view=SetupStartView())
        except:
            print(f"[WELCOME] DM bloqueada para {member.name}")

        try:
            main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
            if main_chat:
                await main_chat.send(f"👋 **Olhos para cima!** {member.mention} pousou na Torre. Verifique sua DM para se registrar!")
        except: pass

class SetupStartView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📝 Iniciar Registro", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SetupModal())

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
