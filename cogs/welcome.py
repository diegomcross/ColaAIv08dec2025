import discord
from discord.ext import commands, tasks
from discord import ui
import config
import database as db
import re
import asyncio
import datetime
from constants import BR_TIMEZONE

# --- HELPER: LOG GENERATOR ---
async def send_onboarding_log(guild, member, status_type, app_data, moderator=None, extra_info=None):
    log_channel = guild.get_channel(config.CHANNEL_WELCOME_LOGS)
    if not log_channel: return

    # 1. Definições de Estilo
    if status_type == 'JOIN':
        color = discord.Color.blue()
        title = "NOVO MEMBRO SE JUNTOU"
    elif status_type == 'APPROVE':
        color = discord.Color.green()
        title = "NOVO MEMBRO ACEITO"
    elif status_type == 'REJECT':
        color = discord.Color.red()
        title = "NOVO MEMBRO RECUSADO"
    else:
        color = discord.Color.dark_grey()
        title = "NOVO MEMBRO SAIU"

    # 2. Processamento de Tags
    roles_list = app_data.get('roles', [])
    tags = []
    
    if config.ROLE_SOLO in roles_list: tags.append("Joga Solo")
    elif config.ROLE_GRUPO in roles_list: tags.append("Joga em Grupo")
    
    if config.ROLE_FREQ_SEM_TEMPO in roles_list: tags.append("Sem Tempo")
    elif config.ROLE_FREQ_RARA in roles_list: tags.append("Raramente")
    else: tags.append("Frequente")
    
    tags.append("Assinou Regras")
    tags_str = " | ".join(tags)
    
    # 3. Data em Português
    now = datetime.datetime.now(BR_TIMEZONE)
    try:
        from constants import MESES_PT
        mes_nome = MESES_PT[now.month - 1]
    except:
        mes_nome = now.strftime("%B")
        
    date_str = f"{now.day} de {mes_nome} de {now.year}, {now.strftime('%H:%M')}"

    # 4. Montagem
    desc = (
        f"**Bungie ID:** `{app_data.get('bungie_id', 'N/A')}`\n"
        f"**Discord:** {member.mention} (`{member.name}`)\n"
        f"**Perfil:** {tags_str}\n"
    )

    if status_type == 'APPROVE' and moderator:
        desc += f"**Aprovado por:** {moderator.mention}\n"
    elif status_type == 'REJECT' and moderator:
        desc += f"**Recusado por:** {moderator.mention}\n"
    elif status_type == 'LEAVE':
        cause = extra_info if extra_info else "SAIU / KICKADO"
        desc += f"**Status:** {cause}\n"

    embed = discord.Embed(description=desc, color=color)
    embed.set_author(name=title, icon_url=member.display_avatar.url)
    embed.set_footer(text=date_str)
    
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)

    await log_channel.send(embed=embed)

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
        
        # Log
        await send_onboarding_log(interaction.guild, self.member, 'APPROVE', self.app_data, moderator=interaction.user)
        
        # Limpa DB
        await db.remove_pending_join(self.member.id)

        # Aplica Cargos
        roles_to_add = []
        guild = interaction.guild
        member_role = guild.get_role(config.ROLE_MEMBER_ID)
        voice_role = guild.get_role(config.ROLE_VOICE_ACCEPTED)
        if member_role: roles_to_add.append(member_role)
        if voice_role: roles_to_add.append(voice_role)
        for rid in self.app_data['roles']:
            r = guild.get_role(rid)
            if r: roles_to_add.append(r)
        
        if roles_to_add:
            try: await self.member.add_roles(*roles_to_add)
            except: pass

        # DM
        try:
            embed_dm = discord.Embed(title="🚀 Acesso Aprovado!", description="Bem-vindo ao Clã! Agora você tem acesso total ao servidor. Nos vemos em órbita!", color=discord.Color.green())
            await self.member.send(embed=embed_dm)
        except: pass

        # Anúncio no Chat Principal (FRASE RESTAURADA)
        main_chat = guild.get_channel(config.CHANNEL_MAIN_CHAT)
        if main_chat:
            await main_chat.send(
                f"👋 **Olhos para cima, Guardiões!**\n"
                f"Um novo membro foi aprovado: Seja bem-vindo(a), {self.member.mention}! 🚀\n"
                f"Identidade: `{self.app_data['bungie_id']}`"
            )

        # Finaliza Canal
        embed_final = discord.Embed(title="✅ Membro Aprovado", description=f"Aprovado por {interaction.user.mention}.\nO canal será excluído em 5 minutos.", color=discord.Color.green())
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
        
        # Log
        await send_onboarding_log(interaction.guild, self.member, 'REJECT', self.app_data, moderator=interaction.user)
        
        # Limpa DB
        await db.remove_pending_join(self.member.id)

        embed = discord.Embed(title="❌ Solicitação Recusada", description=f"Recusado por {interaction.user.mention}. O usuário será removido.", color=discord.Color.red())
        await interaction.channel.send(embed=embed)
        
        try: 
            await self.member.send("Sua solicitação para entrar no clã foi recusada pela moderação.")
            await self.member.kick(reason="Recusado no Onboarding")
        except: pass
        
        await asyncio.sleep(5)
        await interaction.channel.delete(reason="Onboarding Recusado")

# --- VIEW: CONFIRMAÇÃO USUÁRIO ---
class BungieRequestView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member
        self.add_item(discord.ui.Button(label="🌐 Abrir Site do Clã (Bungie)", style=discord.ButtonStyle.link, url=config.BUNGIE_CLAN_LINK, row=0))

    @ui.button(label="📨 Já enviei a solicitação", style=discord.ButtonStyle.primary, row=1)
    async def confirm_sent(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        # LOG DE ENTRADA (JOIN)
        await send_onboarding_log(interaction.guild, self.member, 'JOIN', self.app_data)

        # Feedback Visual
        embed_wait = discord.Embed(
            title="🔄 Aguardando Aprovação",
            description="Obrigado! Notifiquei os moderadores.\nAssim que eles confirmarem seu pedido na Bungie, seu acesso será liberado aqui automaticamente.",
            color=discord.Color.orange()
        )
        await interaction.message.edit(embed=embed_wait, view=None)

        # Monta Embed para Staff (LAYOUT RESTAURADO)
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
        mentions = []
        mod_role = guild.get_role(config.ROLE_MOD_ID)
        founder_role = guild.get_role(config.ROLE_FOUNDER_ID)
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
        
        embed_staff.add_field(name="🎙️ Termo de Voz", value="✅ **Assinado Manualmente**", inline=False)

        if alert_freq:
            embed_staff.set_footer(text="⚠️ ATENÇÃO: Este membro marcou que tem pouco tempo para jogar.")
        else:
            embed_staff.set_footer(text="Verifique se o pedido está na Bungie antes de aprovar.")

        await interaction.channel.send(content=mentions_str, embed=embed_staff, view=StaffApprovalView(self.bot, self.app_data, self.member))

# --- MODAL DE JURAMENTO ---
class VoiceOathModal(ui.Modal, title="Termo de Compromisso"):
    confirmation = ui.TextInput(
        label="Digite: 'Eu concordo em participar das calls'",
        placeholder="Eu concordo em participar das calls",
        required=True,
        style=discord.TextStyle.short
    )

    def __init__(self, bot, app_data, member):
        super().__init__()
        self.bot = bot
        self.app_data = app_data
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation.value.strip().lower() != "eu concordo em participar das calls":
            return await interaction.response.send_message(
                f"❌ **Frase incorreta.**\nVocê digitou: *'{self.confirmation.value}'*\nPara entrar, você deve digitar exatamente: **Eu concordo em participar das calls**", 
                ephemeral=True
            )

        await interaction.response.defer()
        
        # Salva Progresso no DB
        await db.save_pending_join(self.member.id, self.app_data['bungie_id'], self.app_data['roles'])

        embed = discord.Embed(
            title="🔗 Passo Final: Bungie.net", 
            description="**Compromisso aceito.**\n\nAgora, acesse o link do clã (botão cinza) e faça sua solicitação oficial na Bungie.\nDepois de enviar lá, **clique no botão azul** para avisar a moderação.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Link do Clã", value=f"[Clique para Entrar]({config.BUNGIE_CLAN_LINK})", inline=False)
        await interaction.message.edit(embed=embed, view=BungieRequestView(self.bot, self.app_data, self.member))

# --- VIEW: PROPOSTA DE JURAMENTO ---
class VoiceOathView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member

    @ui.button(label="📝 Assinar Compromisso", style=discord.ButtonStyle.green, emoji="🎙️")
    async def sign_oath(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(VoiceOathModal(self.bot, self.app_data, self.member))

    @ui.button(label="Não é meu estilo (Sair)", style=discord.ButtonStyle.secondary)
    async def leave(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        # Log de Saída Manual
        await send_onboarding_log(interaction.guild, self.member, 'LEAVE', self.app_data, extra_info="NÃO CONCORDOU COM REGRAS")
        
        embed = discord.Embed(
            title="🤝 Sem problemas!", 
            description="Entendemos que cada um tem seu estilo de jogo. Como nosso foco é a comunicação em voz, talvez outro clã seja melhor para você.\n\nVocê será removido do servidor em instantes. Boa sorte, Guardião!", 
            color=discord.Color.light_grey()
        )
        await interaction.message.edit(embed=embed, view=None)
        await asyncio.sleep(5)
        try: await self.member.kick(reason="Prefere jogar sem voz (Auto-seleção)")
        except: pass
        await interaction.channel.delete()

# --- VIEWS DE PERGUNTAS (Quiz - TEXTOS RESTAURADOS) ---
class QuestionExperienceView(ui.View):
    def __init__(self, bot, app_data, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.app_data = app_data
        self.member = member
    async def next_step(self, interaction, role_id):
        await interaction.response.defer()
        self.app_data['roles'].append(role_id)
        # TEXTO RESTAURADO
        embed = discord.Embed(
            title="4. Termo de Compromisso (CRÍTICO)", 
            description="Nosso servidor é focado em interação. **A participação nos canais de voz é obrigatória** durante atividades.\n\nSe você não gosta de falar ou não pode usar microfone, infelizmente não somos o clã ideal para você.", 
            color=discord.Color.red()
        )
        embed.set_footer(text="Para prosseguir, você precisará digitar uma confirmação.")
        await interaction.message.edit(embed=embed, view=VoiceOathView(self.bot, self.app_data, self.member))
    @ui.button(label="Novato", style=discord.ButtonStyle.secondary)
    async def b1(self, i, b): await self.next_step(i, config.ROLE_XP_NOVATO)
    @ui.button(label="Iniciado", style=discord.ButtonStyle.secondary)
    async def b2(self, i, b): await self.next_step(i, config.ROLE_XP_INICIADO)
    @ui.button(label="Experiente", style=discord.ButtonStyle.primary)
    async def b3(self, i, b): await self.next_step(i, config.ROLE_XP_EXPERIENTE)
    @ui.button(label="Rank 11", style=discord.ButtonStyle.primary, emoji="🔥")
    async def b4(self, i, b): await self.next_step(i, config.ROLE_XP_RANK11)

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
    async def b1(self, i, b): await self.next_step(i, config.ROLE_FREQ_RARA)
    @ui.button(label="3-4x por semana", style=discord.ButtonStyle.secondary)
    async def b2(self, i, b): await self.next_step(i)
    @ui.button(label="Quase todos os dias", style=discord.ButtonStyle.success)
    async def b3(self, i, b): await self.next_step(i)
    @ui.button(label="Raramente", style=discord.ButtonStyle.secondary)
    async def b4(self, i, b): await self.next_step(i, config.ROLE_FREQ_RARA)
    @ui.button(label="Sem tempo", style=discord.ButtonStyle.danger)
    async def b5(self, i, b): await self.next_step(i, config.ROLE_FREQ_SEM_TEMPO)

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
    async def b1(self, i, b): await self.next_step(i, config.ROLE_SOLO)
    @ui.button(label="Grupo", style=discord.ButtonStyle.success, emoji="👥")
    async def b2(self, i, b): await self.next_step(i, config.ROLE_GRUPO)

class SetupModal(ui.Modal, title="Identificação"):
    bungie_id = ui.TextInput(label="Bungie ID", placeholder="Nome#1234", required=True)
    def __init__(self, bot, member):
        super().__init__()
        self.bot = bot
        self.member = member
    async def on_submit(self, interaction: discord.Interaction):
        clean_id = re.sub(r'\s*#\s*', '#', self.bungie_id.value.strip())
        if not re.match(r'^.+#\d+$', clean_id):
            return await interaction.response.send_message(
                "❌ **Formato Inválido!**\n"
                "Você deve incluir o número do seu Bungie ID.\n"
                "Exemplo correto: `Guardian#1234`\n\n"
                "Tente novamente.",
                ephemeral=True
            )
        
        try: await self.member.edit(nick=clean_id.split('#')[0][:32])
        except: pass
        
        app_data = {'bungie_id': clean_id, 'roles': []}
        # TEXTO RESTAURADO
        embed = discord.Embed(title="1. Estilo de Jogo", description="Você costuma jogar mais sozinho ou em grupo?", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=QuestionStyleView(self.bot, app_data, self.member))

class StartOnboardingView(ui.View):
    def __init__(self, bot, member):
        super().__init__(timeout=None)
        self.bot = bot
        self.member = member
    @ui.button(label="🚀 Iniciar Registro", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SetupModal(self.bot, self.member))

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cleanup_channels_loop.start()

    def cog_unload(self):
        self.cleanup_channels_loop.cancel()

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        pending_data = await db.get_pending_join(member.id)
        if pending_data:
            await send_onboarding_log(member.guild, member, 'LEAVE', pending_data, extra_info="KICKADO / QUITOU")
            await db.remove_pending_join(member.id)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        category = guild.get_channel(config.CATEGORY_WELCOME_ID)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        r_mod = guild.get_role(config.ROLE_MOD_ID)
        r_founder = guild.get_role(config.ROLE_FOUNDER_ID)
        if r_mod: overwrites[r_mod] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if r_founder: overwrites[r_founder] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        c_name = re.sub(r'[^a-zA-Z0-9]', '', member.name).lower()
        channel_name = f"👋│boas-vindas-{c_name}"

        try:
            channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)
            await asyncio.sleep(2)
            # TEXTO RESTAURADO
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
                    
                    if (now - last_msg_time).total_seconds() > 86400: # 24h
                        target_member = None
                        for target in channel.overwrites:
                            if isinstance(target, discord.Member) and not target.bot:
                                target_member = target
                                break
                        
                        if target_member:
                            mem_role = channel.guild.get_role(config.ROLE_MEMBER_ID)
                            if mem_role and mem_role not in target_member.roles:
                                try:
                                    # MENSAGEM RESTAURADA
                                    embed_kick = discord.Embed(
                                        title="⏳ Tempo Esgotado",
                                        description="Você foi removido do servidor por inatividade no processo de registro (24h).\n\nSe quiser tentar novamente, entre pelo link abaixo:",
                                        color=discord.Color.red()
                                    )
                                    embed_kick.add_field(name="🔗 Link do Discord", value=config.DISCORD_INVITE_LINK)
                                    await target_member.send(embed=embed_kick)
                                except: pass
                                
                                try: await target_member.kick(reason="Timeout Onboarding (24h)")
                                except: pass

                        await channel.delete(reason="Expirado")
                except: continue

async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))
