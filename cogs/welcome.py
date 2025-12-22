import discord
from discord.ext import commands, tasks
from discord import ui
import config
import re
import asyncio
import datetime
from constants import BR_TIMEZONE

# --- VIEWS DO QUESTIONÁRIO (INTERATIVIDADE) ---

class FinalDecisionView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member

    async def close_ticket(self, interaction, approved: bool):
        await interaction.response.defer()
        
        if approved:
            # 1. Aplica Cargos Acumulados
            roles_to_add = []
            guild = interaction.guild
            
            # Cargo Base de Membro (Acesso ao Servidor)
            member_role = guild.get_role(config.ROLE_MEMBER_ID)
            if member_role: roles_to_add.append(member_role)
            
            # Cargo de Voz Aceito
            voice_role = guild.get_role(config.ROLE_VOICE_ACCEPTED)
            if voice_role: roles_to_add.append(voice_role)
            
            # Cargos do Quiz
            for rid in self.app_data['roles']:
                r = guild.get_role(rid)
                if r: roles_to_add.append(r)
            
            if roles_to_add:
                try: await self.member.add_roles(*roles_to_add)
                except Exception as e: print(f"Erro ao dar cargos: {e}")

            # 2. Anuncia no Chat Principal
            main_chat = guild.get_channel(config.CHANNEL_MAIN_CHAT)
            if main_chat:
                await main_chat.send(
                    f"👋 **Olhos para cima, Guardiões!**\n"
                    f"Um novo membro pousou na Torre: Seja bem-vindo(a), {self.member.mention}! 🚀\n"
                    f"Identidade: `{self.app_data['bungie_id']}`"
                )
            
            # 3. Mensagem de Autodestruição
            embed = discord.Embed(title="✅ Configuração Concluída!", description="Acesso liberado. Este canal será excluído em 10 segundos...", color=discord.Color.green())
            await interaction.channel.send(embed=embed)
            await asyncio.sleep(10)
            await interaction.channel.delete(reason="Onboarding Concluído")
            
        else:
            # Rejeitado (Kick)
            embed = discord.Embed(title="⛔ Acesso Negado", description="Como a participação em voz é obrigatória, não podemos prosseguir.\nVocê será removido do servidor. Até a próxima!", color=discord.Color.red())
            await interaction.channel.send(embed=embed)
            await asyncio.sleep(5)
            try: await self.member.kick(reason="Recusou regras de voz no onboarding")
            except: pass
            await interaction.channel.delete(reason="Onboarding Falhou")

    @ui.button(label="Concordo em participar dos canais de voz", style=discord.ButtonStyle.green, emoji="🎙️")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        await self.close_ticket(interaction, approved=True)

    @ui.button(label="Não concordo", style=discord.ButtonStyle.red)
    async def disagree(self, interaction: discord.Interaction, button: ui.Button):
        await self.close_ticket(interaction, approved=False)

class QuestionExperienceView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member

    async def next_step(self, interaction, role_id):
        await interaction.response.defer()
        self.app_data['roles'].append(role_id)
        
        embed = discord.Embed(title="4. Termo de Compromisso", description="Você entende que a participação nos **Canais de Voz** é obrigatória durante as atividades do clã?", color=discord.Color.red())
        await interaction.message.edit(embed=embed, view=FinalDecisionView(self.bot, self.app_data, self.member))

    @ui.button(label="Novato", style=discord.ButtonStyle.secondary)
    async def btn_novato(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_NOVATO)
    @ui.button(label="Iniciado", style=discord.ButtonStyle.secondary)
    async def btn_iniciado(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_INICIADO)
    @ui.button(label="Experiente", style=discord.ButtonStyle.primary)
    async def btn_expert(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_EXPERIENTE)
    @ui.button(label="Rank 11", style=discord.ButtonStyle.primary, emoji="🔥")
    async def btn_rank11(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_XP_RANK11)

class QuestionFrequencyView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member

    async def next_step(self, interaction, role_id=None):
        await interaction.response.defer()
        if role_id: self.app_data['roles'].append(role_id)
        
        embed = discord.Embed(title="3. Nível de Experiência", description="Como você classificaria seu conhecimento no Destiny 2?", color=discord.Color.blue())
        await interaction.message.edit(embed=embed, view=QuestionExperienceView(self.bot, self.app_data, self.member))

    @ui.button(label="1-2x por semana", style=discord.ButtonStyle.secondary)
    async def btn_rare(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_FREQ_RARA)
    @ui.button(label="3-4x por semana", style=discord.ButtonStyle.secondary)
    async def btn_med(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction)
    @ui.button(label="Quase todos os dias", style=discord.ButtonStyle.success)
    async def btn_high(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction)
    @ui.button(label="Raramente", style=discord.ButtonStyle.secondary)
    async def btn_very_rare(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_FREQ_RARA)
    @ui.button(label="Sem tempo", style=discord.ButtonStyle.danger)
    async def btn_no_time(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_FREQ_SEM_TEMPO)

class QuestionStyleView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member

    async def next_step(self, interaction, role_id):
        await interaction.response.defer()
        self.app_data['roles'].append(role_id)
        
        embed = discord.Embed(title="2. Frequência de Jogo", description="Com que frequência você costuma jogar?", color=discord.Color.blue())
        await interaction.message.edit(embed=embed, view=QuestionFrequencyView(self.bot, self.app_data, self.member))

    @ui.button(label="Solo", style=discord.ButtonStyle.secondary, emoji="👤")
    async def btn_solo(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_SOLO)
    @ui.button(label="Grupo", style=discord.ButtonStyle.success, emoji="👥")
    async def btn_grupo(self, interaction: discord.Interaction, button: ui.Button): await self.next_step(interaction, config.ROLE_GRUPO)

class SetupModal(ui.Modal, title="Identificação"):
    bungie_id = ui.TextInput(label="Bungie ID", placeholder="Nome#1234", required=True)

    def __init__(self, bot, member):
        super().__init__()
        self.bot = bot
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        # Sanitização
        raw_input = self.bungie_id.value
        clean_id = re.sub(r'\s*#\s*', '#', raw_input.strip())
        new_nick = clean_id.split('#')[0]

        # Tenta Renomear
        try: await self.member.edit(nick=new_nick[:32])
        except: pass

        # Inicia Dados
        app_data = {'bungie_id': clean_id, 'roles': []}

        embed = discord.Embed(title="1. Estilo de Jogo", description="Você costuma jogar mais sozinho ou em grupo?", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=QuestionStyleView(self.bot, app_data, self.member))

class StartOnboardingView(ui.View):
    def __init__(self, bot, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member

    @ui.button(label="📝 Iniciar Registro", style=discord.ButtonStyle.primary, emoji="🚀")
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SetupModal(self.bot, self.member))

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_channels_loop.start()

    def cog_unload(self):
        self.cleanup_channels_loop.cancel()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Cria o canal privado de boas-vindas ao entrar."""
        guild = member.guild
        category = guild.get_channel(config.CATEGORY_WELCOME_ID)
        
        # Se não tiver categoria configurada, tenta criar no topo
        if not category:
            print("[WELCOME] AVISO: CATEGORY_WELCOME_ID não encontrado. Criando no topo.")
        
        # FIX: read_message_history=True garante que ele veja a msg mesmo se lagar
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        # Nome do canal limpo
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', member.name).lower()
        channel_name = f"👋│boas-vindas-{clean_name}"

        try:
            channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
            
            # Delay de segurança para o Discord propagar permissões
            await asyncio.sleep(2)
            
            embed = discord.Embed(
                title=f"Olá, {member.name}!",
                description="Seja bem-vindo(a) à ante-sala do Clã.\n\nPara liberar seu acesso ao restante do servidor, precisamos configurar seu perfil e confirmar algumas regras.\n\n**Clique abaixo para começar.**",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            
            await channel.send(f"{member.mention}", embed=embed, view=StartOnboardingView(self.bot, member))
            
        except Exception as e:
            print(f"[WELCOME] Erro ao criar canal para {member.name}: {e}")

    # --- TAREFA DE LIMPEZA (GHOST CHANNELS) ---
    @tasks.loop(hours=1)
    async def cleanup_channels_loop(self):
        """Remove canais de boas-vindas abandonados há mais de 24h."""
        await self.bot.wait_until_ready()
        
        category = self.bot.get_channel(config.CATEGORY_WELCOME_ID)
        if not category: return

        now = datetime.datetime.now(datetime.timezone.utc)
        
        for channel in category.text_channels:
            if channel.name.startswith("👋│boas-vindas-"):
                try:
                    last_msg_time = channel.created_at
                    async for msg in channel.history(limit=1):
                        last_msg_time = msg.created_at
                    
                    diff = (now - last_msg_time).total_seconds()
                    
                    if diff > 86400: # 24h
                        await channel.delete(reason="Canal de Boas-vindas abandonado")
                except:
                    continue

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
