import discord
from discord.ext import commands, tasks
from discord import ui
import config
import re
import asyncio
import datetime
from constants import BR_TIMEZONE

# --- VIEW: APROVAÇÃO DA STAFF ---
class StaffApprovalView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member

    @ui.button(label="✅ Aprovar Membro", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        user_roles = [r.id for r in interaction.user.roles]
        allowed_roles = [config.ROLE_MOD_ID, config.ROLE_FOUNDER_ID]
        
        if not any(rid in user_roles for rid in allowed_roles) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("⛔ Apenas Moderadores ou o Fundador podem aprovar.", ephemeral=True)

        await interaction.response.defer()
        
        roles_to_add = []
        guild = interaction.guild
        
        member_role = guild.get_role(config.ROLE_MEMBER_ID)
        if member_role: roles_to_add.append(member_role)
        
        voice_role = guild.get_role(config.ROLE_VOICE_ACCEPTED)
        if voice_role: roles_to_add.append(voice_role)
        
        for rid in self.app_data['roles']:
            r = guild.get_role(rid)
            if r: roles_to_add.append(r)
        
        if roles_to_add:
            try: await self.member.add_roles(*roles_to_add)
            except Exception as e: print(f"Erro ao dar cargos: {e}")

        try:
            dm_embed = discord.Embed(title="🚀 Acesso Aprovado!", description="Sua entrada no clã foi aceita pela administração.", color=discord.Color.green())
            dm_embed.add_field(name="Bem-vindo(a)!", value=f"Agora você tem acesso total ao servidor. Nos vemos em órbita!", inline=False)
            await self.member.send(embed=dm_embed)
        except: pass

        main_chat = guild.get_channel(config.CHANNEL_MAIN_CHAT)
        if main_chat:
            await main_chat.send(
                f"👋 **Olhos para cima, Guardiões!**\n"
                f"Um novo membro foi aprovado: Seja bem-vindo(a), {self.member.mention}! 🚀\n"
                f"Identidade: `{self.app_data['bungie_id']}`"
            )

        embed_final = discord.Embed(
            title="✅ Membro Aprovado", 
            description=f"Aprovado por {interaction.user.mention}.\nO canal será excluído em 5 minutos.", 
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed_final)
        
        button.disabled = True
        self.children[1].disabled = True
        await interaction.message.edit(view=self)

        await asyncio.sleep(300)
        await interaction.channel.delete(reason="Onboarding Aprovado")

    @ui.button(label="⛔ Rejeitar/Expulsar", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: ui.Button):
        user_roles = [r.id for r in interaction.user.roles]
        allowed_roles = [config.ROLE_MOD_ID, config.ROLE_FOUNDER_ID]
        
        if not any(rid in user_roles for rid in allowed_roles) and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("⛔ Sem permissão.", ephemeral=True)

        await interaction.response.defer()
        
        embed = discord.Embed(title="❌ Solicitação Recusada", description=f"Recusado por {interaction.user.mention}. O usuário será removido.", color=discord.Color.red())
        await interaction.channel.send(embed=embed)
        
        try: 
            await self.member.send("Sua solicitação para entrar no clã foi recusada pela moderação.")
            await self.member.kick(reason="Recusado no Onboarding")
        except: pass
        
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Onboarding Recusado")

# --- VIEW: CONFIRMAÇÃO DO USUÁRIO ---
class BungieRequestView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member
        # ADICIONADO: Botão de Link com destaque visual
        self.add_item(discord.ui.Button(label="🌐 Abrir Site do Clã (Bungie)", style=discord.ButtonStyle.link, url=config.BUNGIE_CLAN_LINK, row=0))

    @ui.button(label="📨 Já enviei a solicitação", style=discord.ButtonStyle.primary, row=1)
    async def confirm_sent(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        embed_wait = discord.Embed(
            title="🔄 Aguardando Aprovação",
            description="Obrigado! Notifiquei os moderadores.\nAssim que eles confirmarem seu pedido na Bungie, seu acesso será liberado aqui automaticamente.",
            color=discord.Color.orange()
        )
        await interaction.message.edit(embed=embed_wait, view=None)

        roles_selected = self.app_data['roles']
        
        estilo_str = "Indefinido"
        if config.ROLE_SOLO in roles_selected: estilo_str = "👤 Solo (Lobo Solitário)"
        elif config.ROLE_GRUPO in roles_selected: estilo_str = "👥 Grupo (Prefere Fireteam)"
        
        freq_str = "Normal"
        alert_freq = False
        if config.ROLE_FREQ_SEM_TEMPO in roles_selected: 
            freq_str = "⚠️ Sem Tempo (Muito Casual)"
            alert_freq = True
        elif config.ROLE_FREQ_RARA in roles_selected:
            freq_str = "⚠️ Joga Raramente"
            alert_freq = True
        
        xp_str = "Normal"
        if config.ROLE_XP_NOVATO in roles_selected: xp_str = "👶 Novato (New Light)"
        elif config.ROLE_XP_RANK11 in roles_selected: xp_str = "🔥 Rank 11 (Hardcore)"

        guild = interaction.guild
        mod_role = guild.get_role(config.ROLE_MOD_ID)
        founder_role = guild.get_role(config.ROLE_FOUNDER_ID)
        
        mentions = []
        if mod_role: mentions.append(mod_role.mention)
        if founder_role: mentions.append(founder_role.mention)
        mentions_str = " ".join(mentions) if mentions else "@Staff"

        embed_staff = discord.Embed(
            title="🛡️ Nova Solicitação Pendente",
            description=f"O usuário {self.member.mention} completou o cadastro e aguarda aprovação.",
            color=discord.Color.blue()
        )
        
        embed_staff.add_field(name="🆔 Bungie ID", value=f"`{self.app_data['bungie_id']}`", inline=True)
        embed_staff.add_field(name="🔗 Link Rápido", value=f"[Ver na Bungie]({config.BUNGIE_CLAN_LINK})", inline=True)
        
        embed_staff.add_field(name="\u200b", value="**📋 Perfil do Candidato:**", inline=False)
        embed_staff.add_field(name="Estilo de Jogo", value=estilo_str, inline=True)
        embed_staff.add_field(name="Disponibilidade", value=freq_str, inline=True)
        embed_staff.add_field(name="Experiência", value=xp_str, inline=True)
        
        embed_staff.add_field(name="🎙️ Termo de Voz", value="✅ **Aceitou** (Participação Obrigatória)", inline=False)

        if alert_freq:
            embed_staff.set_footer(text="⚠️ ATENÇÃO: Este membro marcou que tem pouco tempo para jogar.")
        else:
            embed_staff.set_footer(text="Verifique se o pedido está na Bungie antes de aprovar.")

        await interaction.channel.send(content=f"{mentions_str}", embed=embed_staff, view=StaffApprovalView(self.bot, self.app_data, self.member))

class FinalDecisionView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member

    @ui.button(label="Concordo em participar dos canais de voz", style=discord.ButtonStyle.green, emoji="🎙️")
    async def agree(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        embed_step = discord.Embed(
            title="🔗 Quase lá...", 
            description="**Passo Final:** Acesse o link do clã (botão cinza) e faça sua solicitação na Bungie.\n\nDepois de enviar, **clique no botão azul** para avisar a moderação.",
            color=discord.Color.gold()
        )
        
        await interaction.message.edit(embed=embed_step, view=BungieRequestView(self.bot, self.app_data, self.member))

    @ui.button(label="Não concordo", style=discord.ButtonStyle.red)
    async def disagree(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        embed = discord.Embed(title="⛔ Acesso Negado", description="Participação em voz é obrigatória. Você será removido do servidor.", color=discord.Color.red())
        await interaction.message.edit(embed=embed, view=None)
        await asyncio.sleep(5)
        try: await self.member.kick(reason="Recusou regras de voz")
        except: pass
        await interaction.channel.delete()

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
        clean_id = re.sub(r'\s*#\s*', '#', self.bungie_id.value.strip())
        try: await self.member.edit(nick=clean_id.split('#')[0][:32])
        except: pass
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
        guild = member.guild
        category = guild.get_channel(config.CATEGORY_WELCOME_ID)
        
        mod_role = guild.get_role(config.ROLE_MOD_ID)
        founder_role = guild.get_role(config.ROLE_FOUNDER_ID)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        if mod_role: overwrites[mod_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if founder_role: overwrites[founder_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        clean_name = re.sub(r'[^a-zA-Z0-9]', '', member.name).lower()
        channel_name = f"👋│boas-vindas-{clean_name}"

        try:
            channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
            await asyncio.sleep(2)
            embed = discord.Embed(title=f"Olá, {member.name}!", description="Seja bem-vindo(a).\n\nPara entrar no clã, precisamos configurar seu perfil. No final, um Moderador irá aprovar seu acesso.\n\n**Clique abaixo para começar.**", color=discord.Color.gold())
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(f"{member.mention}", embed=embed, view=StartOnboardingView(self.bot, member))
        except Exception as e:
            print(f"[WELCOME] Erro: {e}")

    @tasks.loop(minutes=5)
    async def cleanup_channels_loop(self):
        category = self.bot.get_channel(config.CATEGORY_WELCOME_ID)
        if not category: return
        now = datetime.datetime.now(datetime.timezone.utc)
        
        for channel in category.text_channels:
            if channel.name.startswith("👋│boas-vindas-"):
                try:
                    last_msg_time = channel.created_at
                    async for msg in channel.history(limit=1): last_msg_time = msg.created_at
                    
                    # 24 Horas = 86400 segundos (Timeout para Staff decidir)
                    if (now - last_msg_time).total_seconds() > 86400:
                        
                        target_member = None
                        # Tenta achar o membro nas permissões do canal
                        for target in channel.overwrites:
                            if isinstance(target, discord.Member) and not target.bot:
                                target_member = target
                                break
                        
                        if target_member:
                            # Se o membro JÁ TEM o cargo de acesso, ele foi aprovado mas o canal bugou
                            member_role = channel.guild.get_role(config.ROLE_MEMBER_ID)
                            is_approved = member_role in target_member.roles if member_role else False

                            if not is_approved:
                                # Membro NÃO aprovado e estourou o tempo (24h) -> KICK
                                try:
                                    embed_kick = discord.Embed(
                                        title="⏳ Tempo Esgotado",
                                        description="Você foi removido do servidor por inatividade no processo de registro (24h).\n\nSe quiser tentar novamente, entre pelo link abaixo:",
                                        color=discord.Color.red()
                                    )
                                    embed_kick.add_field(name="🔗 Link do Discord", value=config.DISCORD_INVITE_LINK)
                                    await target_member.send(embed=embed_kick)
                                except: pass
                                
                                try:
                                    await target_member.kick(reason="Timeout Onboarding (24h)")
                                except: pass

                        await channel.delete(reason="Canal de Boas-vindas expirado")
                        
                except Exception as e:
                    print(f"[WELCOME CLEANUP] Erro no canal {channel.name}: {e}")

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
