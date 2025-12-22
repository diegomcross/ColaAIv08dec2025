import discord
from discord.ext import commands
from discord import ui
import config
import database as db
import re

# --- CLASSE PARA GERENCIAR O FLUXO DO ONBOARDING (WIZARD) ---

class VoiceAgreementView(ui.View):
    def __init__(self, bot, app_data):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data # Dicionário acumulado com as respostas

    async def finalize_application(self, interaction):
        # 1. Salva no Banco de Dados
        await db.save_pending_join(
            interaction.user.id, 
            self.app_data['bungie_id'], 
            self.app_data['roles']
        )
        
        # 2. Descobre o Servidor (Guilda) Alvo
        # Usamos o canal principal para achar a guilda
        target_guild = None
        main_channel = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
        if main_channel:
            target_guild = main_channel.guild
        
        if not target_guild:
            return await interaction.message.edit(content="❌ Erro Interno: Não consegui localizar o servidor do clã. Contate um admin.", view=None)

        # 3. Gera o Convite de Uso Único
        try:
            # Tenta criar no canal de boas-vindas ou no main chat
            invite_channel = main_channel
            invite = await invite_channel.create_invite(
                max_uses=1,
                unique=True,
                max_age=86400, # 24 horas
                reason=f"Aplicação aceita para {self.app_data['bungie_id']}"
            )
        except discord.Forbidden:
            return await interaction.message.edit(content="❌ **Erro de Permissão:** O bot não tem permissão de 'Criar Convite' no servidor. Avise o dono!", view=None)
        except Exception as e:
            return await interaction.message.edit(content=f"❌ Erro ao gerar convite: {e}", view=None)

        # 4. Envia o Convite
        embed = discord.Embed(title="🎉 Inscrição Aprovada!", description="Seus dados foram salvos. Use o ingresso abaixo para entrar na Torre.", color=discord.Color.green())
        embed.add_field(name="🎟️ Seu Convite Único", value=f"{invite.url}", inline=False)
        embed.add_field(name="⚠️ Atenção", value="Este link só funciona 1 vez e vale por 24h.", inline=False)
        embed.set_footer(text="Assim que você entrar, seus cargos serão aplicados automaticamente.")
        
        await interaction.message.edit(content=None, embed=embed, view=None)

    @ui.button(label="Concordo em participar dos canais de voz", style=discord.ButtonStyle.green, emoji="🎙️")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        # Adiciona cargo de aceite
        self.app_data['roles'].append(config.ROLE_VOICE_ACCEPTED)
        await self.finalize_application(interaction)

    @ui.button(label="Não concordo", style=discord.ButtonStyle.red)
    async def disagree(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        # Adiciona cargo de rejeição
        self.app_data['roles'].append(config.ROLE_VOICE_REJECTED)
        await self.finalize_application(interaction)

class QuestionExperienceView(ui.View):
    def __init__(self, bot, app_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.app_data = app_data

    async def next_step(self, interaction, role_id):
        await interaction.response.defer()
        self.app_data['roles'].append(role_id)
        
        embed = discord.Embed(title="4. Termo de Compromisso", description="Você entende que a participação nos **Canais de Voz** é obrigatória durante as atividades do clã?", color=discord.Color.red())
        await interaction.message.edit(embed=embed, view=VoiceAgreementView(self.bot, self.app_data))

    @ui.button(label="Novato", style=discord.ButtonStyle.secondary)
    async def btn_novato(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_NOVATO)
    
    @ui.button(label="Iniciado", style=discord.ButtonStyle.secondary)
    async def btn_iniciado(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_INICIADO)

    @ui.button(label="Experiente", style=discord.ButtonStyle.primary)
    async def btn_expert(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_EXPERIENTE)

    @ui.button(label="Rank 11", style=discord.ButtonStyle.primary, emoji="🔥")
    async def btn_rank11(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_RANK11)

class QuestionFrequencyView(ui.View):
    def __init__(self, bot, app_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.app_data = app_data

    async def next_step(self, interaction, role_id=None):
        await interaction.response.defer()
        if role_id: self.app_data['roles'].append(role_id)
            
        embed = discord.Embed(title="3. Nível de Experiência", description="Como você classificaria seu conhecimento no Destiny 2?", color=discord.Color.blue())
        await interaction.message.edit(embed=embed, view=QuestionExperienceView(self.bot, self.app_data))

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
    def __init__(self, bot, app_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.app_data = app_data

    async def next_step(self, interaction, role_id):
        await interaction.response.defer()
        self.app_data['roles'].append(role_id)
        
        embed = discord.Embed(title="2. Frequência de Jogo", description="Com que frequência você costuma jogar?", color=discord.Color.blue())
        await interaction.message.edit(embed=embed, view=QuestionFrequencyView(self.bot, self.app_data))

    @ui.button(label="Solo", style=discord.ButtonStyle.secondary, emoji="👤")
    async def btn_solo(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_SOLO)

    @ui.button(label="Grupo", style=discord.ButtonStyle.success, emoji="👥")
    async def btn_grupo(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_GRUPO)

class SetupModal(ui.Modal, title="Aplicação para o Clã"):
    bungie_id = ui.TextInput(label="Seu Bungie ID", placeholder="Nome#1234", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        raw_input = self.bungie_id.value
        # Limpeza do ID (Espaços)
        clean_id = re.sub(r'\s*#\s*', '#', raw_input.strip())
        
        # Inicia o dicionário de dados da aplicação
        app_data = {
            'bungie_id': clean_id,
            'roles': []
        }
        
        embed = discord.Embed(title="1. Estilo de Jogo", description="Você costuma jogar mais sozinho ou em grupo?", color=discord.Color.blue())
        # Passamos app_data para a próxima view
        await interaction.response.send_message(embed=embed, view=QuestionStyleView(interaction.client, app_data))

class SetupStartView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="📝 Iniciar Aplicação", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SetupModal())

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- LISTENER DE MENSAGENS (DM) ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot: return
        
        if isinstance(message.channel, discord.DMChannel):
            keywords = ["entrar", "join", "clan", "clã", "participar", "convite", "vaga", "quero"]
            if any(word in message.content.lower() for word in keywords):
                
                # Verifica se JÁ ESTÁ no servidor
                member = None
                for guild in self.bot.guilds:
                    member = guild.get_member(message.author.id)
                    if member: break
                
                if member:
                    await message.channel.send("✅ Você já está no servidor do Discord! Fale com um admin se precisar de ajuda.")
                else:
                    await message.channel.send(
                        "👋 Olá! Para entrar no clã, precisamos te conhecer melhor.\n"
                        "Responda ao questionário abaixo e, se tudo estiver certo, **vou gerar um convite exclusivo para você**.",
                        view=SetupStartView()
                    )

    # --- LISTENER DE ENTRADA NO SERVIDOR ---
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Quando o usuário entra com o convite, aplica os dados salvos."""
        
        # 1. Busca dados pendentes no DB
        pending_data = await db.get_pending_join(member.id)
        
        if pending_data:
            bungie_id = pending_data['bungie_id']
            roles_ids = pending_data['roles']
            clean_nick = bungie_id.split('#')[0][:32]
            
            # 2. Aplica Nickname
            try:
                await member.edit(nick=clean_nick)
            except: pass
            
            # 3. Aplica Cargos
            roles_to_add = []
            for rid in roles_ids:
                role = member.guild.get_role(rid)
                if role: roles_to_add.append(role)
            
            if roles_to_add:
                try: await member.add_roles(*roles_to_add)
                except: pass
                
            # 4. Envia Mensagem de Boas-vindas
            try:
                main_chat = self.bot.get_channel(config.CHANNEL_MAIN_CHAT)
                if main_chat:
                    await main_chat.send(f"👋 **Bem-vindo(a), {member.mention}!**\nSeu registro foi carregado automaticamente: `{bungie_id}`.\nNão esqueça de solicitar a entrada no jogo: {config.BUNGIE_CLAN_LINK}")
            except: pass
            
            # 5. Remove do DB (Limpeza)
            await db.remove_pending_join(member.id)
            print(f"[WELCOME] Auto-setup aplicado para {clean_nick}")

        else:
            # Caso entre sem passar pelo fluxo (ex: link vazado ou antigo),
            # O bot pode mandar o link do setup normal (fallback) ou ignorar.
            print(f"[WELCOME] {member.name} entrou sem aplicação pendente.")

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
