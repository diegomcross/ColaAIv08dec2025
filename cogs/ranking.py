import discord
from discord import app_commands
from discord.ext import commands, tasks
import database as db
import datetime
import asyncio
from constants import BR_TIMEZONE, RANK_THRESHOLDS
import config
import utils

class RankingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {user_id: datetime_inicio}
        self.active_timers = {} 
        # Inicia o loop de horário fixo
        self.update_ranking_loop.start()

    def cog_unload(self):
        self.update_ranking_loop.cancel()

    # --- EVENTO: AO INICIAR ---
    @commands.Cog.listener()
    async def on_ready(self):
        """Força uma atualização imediata ao ligar o bot."""
        # Aguarda um pouco para garantir que o cache de membros carregou
        await asyncio.sleep(10)
        await self.update_ranking_board()

    # --- COMANDO MANUAL (DEBUG) ---
    @app_commands.command(name="forcar_ranking", description="Admin: Atualiza o Embed de Ranking imediatamente.")
    @app_commands.checks.has_permissions(administrator=True)
    async def force_ranking(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.update_ranking_board()
        await interaction.followup.send("✅ Ranking atualizado com sucesso!", ephemeral=True)

    # --- LÓGICA DE TEMPO ---
    def check_validity_conditions(self, member):
        """Retorna True se a sessão é VÁLIDA para Ranking (Anti-Farm)."""
        if member.bot: return False
        
        voice = member.voice
        if not voice or not voice.channel: return False
        
        # Mutado/Ensurdecido = Apenas Presença (is_valid=0)
        if voice.self_mute or voice.self_deaf or voice.mute or voice.deaf:
            return False
            
        # Sozinho = Apenas Presença (is_valid=0)
        humans_in_channel = [m for m in voice.channel.members if not m.bot]
        if len(humans_in_channel) < 2:
            return False
            
        return True

    async def reconcile_session(self, member):
        user_id = member.id
        now = datetime.datetime.now(BR_TIMEZONE)
        
        is_in_voice = member.voice and member.voice.channel
        is_counting = user_id in self.active_timers

        if is_in_voice and not is_counting:
            # INICIA O RELÓGIO
            self.active_timers[user_id] = now

        elif not is_in_voice and is_counting:
            # SAIU DA VOZ -> SALVA SESSÃO
            start_time = self.active_timers.pop(user_id)
            duration = (now - start_time).total_seconds() / 60
            
            if duration >= 1:
                # Se saiu, não temos o estado 'voice' dele mais.
                # Assumimos presença geral (is_valid=0) para o trecho final.
                await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=0)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Dispara reconciliação para quem mudou
        if not member.bot:
            await self.reconcile_session(member)

    # --- LÓGICA PRINCIPAL DO EMBED ---
    async def update_ranking_board(self):
        guild = self.bot.get_guild(self.bot.guilds[0].id) if self.bot.guilds else None
        if not guild: return

        now = datetime.datetime.now(BR_TIMEZONE)
        
        # 1. SALVA PARCIAIS (Sincroniza quem está na call agora)
        for user_id, start_time in list(self.active_timers.items()):
            member = guild.get_member(user_id)
            if member and member.voice:
                duration = (now - start_time).total_seconds() / 60
                if duration >= 1:
                    valid = 1 if self.check_validity_conditions(member) else 0
                    await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=valid)
                    self.active_timers[user_id] = now # Reseta timer

        # 2. COLETA DADOS (7 Dias)
        data_7d = await db.get_voice_hours(7)
        hours_map = {r['user_id']: r['total_mins']/60 for r in data_7d}
        
        all_members_data = []
        for member in guild.members:
            if member.bot: continue
            
            # FILTRO STAFF (Ignora Fundador e Moderador no PLACAR)
            if any(r.id in [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID] for r in member.roles):
                continue

            # DEFINE O RANK VISUAL
            if member.get_role(config.ROLE_INATIVO):
                rank_title = "INATIVOS 🚷"
                h7 = 0
            else:
                h7 = hours_map.get(member.id, 0)
                if h7 >= RANK_THRESHOLDS['MESTRE']: rank_title = "MASTER ⭐"
                elif h7 >= RANK_THRESHOLDS['ADEPTO']: rank_title = "ADEPTO ⚔️"
                elif h7 >= RANK_THRESHOLDS['VANGUARDA']: rank_title = "VANGUARDA ⚡"
                elif h7 >= RANK_THRESHOLDS['ATIVO']: rank_title = "ATIVOS 🟢" 
                elif h7 >= RANK_THRESHOLDS['TURISTA']: rank_title = "TURISTAS 🧳"
                else: rank_title = "TURISTAS 🧳" # Fallback

            all_members_data.append({'name': utils.clean_voter_name(member.display_name), 'h7': h7, 'rank': rank_title})

        # Ordena por horas (maior para menor) para manter ordem dentro dos grupos
        all_members_data.sort(key=lambda x: x['h7'], reverse=True)

        # 3. AGRUPA OS NOMES
        ranks_config = {
            "MASTER ⭐": [],
            "ADEPTO ⚔️": [],
            "VANGUARDA ⚡": [],
            "ASCENDENTE 🚀": [],
            "TURISTAS 🧳": [],
            "ATIVOS 🟢": [],
            "INATIVOS 🚷": []
        }

        for p in all_members_data:
            key = p['rank']
            if key in ranks_config:
                ranks_config[key].append(p['name'])
            elif "ATIVOS" in key: ranks_config["ATIVOS 🟢"].append(p['name'])
            else: ranks_config["TURISTAS 🧳"].append(p['name'])

        # 4. CONSTRÓI O EMBED (DESIGN NOVO)
        embed = discord.Embed(title="🏆  QUADRO DE HONRA (7 Dias)", color=discord.Color.gold())
        
        # -- MASTER (Topo em Destaque com Quote) --
        masters = ranks_config.pop("MASTER ⭐")
        if masters:
            # Uso do > para criar um bloco de citação lateral, destacando o nome
            master_str = "\n".join([f"> 👑 **{name}**" for name in masters])
            embed.description = f"### 🥇 MASTER ⭐\n{master_str}"
        else:
            embed.description = "### 🥇 MASTER ⭐\n> *O trono está vazio...*"

        # -- TIERS MÉDIOS (Lista Vertical Limpa) --
        # Usamos inline=True para ficarem lado a lado no PC, e empilharem bonito no mobile
        mid_tiers = ["ADEPTO ⚔️", "VANGUARDA ⚡"]
        for rank in mid_tiers:
            names = ranks_config.get(rank, [])
            # Usa bloco de código simples `Nome` para destacar
            value = "\n".join([f"`{n}`" for n in names]) if names else "*Vazio*"
            embed.add_field(name=f"{rank} ({len(names)})", value=value, inline=True)
        
        # Quebra de linha forçada para separar a Elite da Galera
        embed.add_field(name="\u200b", value="\u200b", inline=False) 

        # -- TIERS BAIXOS (Lista Horizontal Compacta) --
        # Aqui mudamos para horizontal (separado por vírgula) para economizar tela no celular
        low_tiers = ["TURISTAS 🧳", "ATIVOS 🟢", "INATIVOS 🚷"]
        for rank in low_tiers:
            names = ranks_config.get(rank, [])
            
            if names:
                # Formata como: `Nome`, `Nome2`, `Nome3`
                # Isso cria um bloco de texto fluido que ocupa menos altura
                formatted_names = [f"`{n}`" for n in names]
                value = ", ".join(formatted_names)
                
                # Se ficar MUITO grande (limite do discord é 1024 chars), corta
                if len(value) > 1000:
                    value = value[:950] + "..."
            else:
                value = "*Ninguém*"
            
            # Inline=False para ocupar a largura toda e permitir o texto fluir
            embed.add_field(name=f"{rank} ({len(names)})", value=value, inline=False)

        # -- RODAPÉ --
        info_text = (
            "🎙️ **Como subir de Rank?**\n"
            "Participe das calls em grupo com o áudio aberto e o bot vai logar seus minutos. "
            "Call sozinho ou mutado conta apenas presença!"
        )
        embed.add_field(name="⠀", value=info_text, inline=False)

        if guild.icon: embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Atualizado às {now.strftime('%H:%M')} • Staff não listado")

        # ENVIA OU EDITA
        channel = guild.get_channel(config.CHANNEL_RANKING)
        if channel:
            try:
                last_msg = None
                async for msg in channel.history(limit=10):
                    if msg.author == self.bot.user:
                        last_msg = msg
                        break
                if last_msg: await last_msg.edit(embed=embed)
                else: await channel.send(embed=embed)
            except Exception as e:
                print(f"[RANKING ERROR] Falha ao enviar embed: {e}")

    # --- LOOP AGENDADO (:00 e :30) ---
    times_list = [datetime.time(hour=h, minute=m, tzinfo=BR_TIMEZONE) for h in range(24) for m in [0, 30]]

    @tasks.loop(time=times_list)
    async def update_ranking_loop(self):
        await self.bot.wait_until_ready()
        await self.update_ranking_board()

    @update_ranking_loop.before_loop
    async def before_ranking_loop(self):
        await self.bot.wait_until_ready()

# --- FUNÇÃO SETUP OBRIGATÓRIA ---
async def setup(bot):
    await bot.add_cog(RankingCog(bot))
