import discord
from discord import app_commands
from discord.ext import commands, tasks
import database as db
import datetime
from constants import BR_TIMEZONE, RANK_THRESHOLDS
import config
import utils

class RankingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # {user_id: datetime_inicio}
        self.active_timers = {} 
        self.update_ranking_loop.start()

    def cog_unload(self):
        self.update_ranking_loop.cancel()

    def check_validity_conditions(self, member):
        """Retorna True se a sessão é VÁLIDA para Ranking (Anti-Farm)."""
        if member.bot: return False
        voice = member.voice
        if not voice or not voice.channel: return False
        
        # Mutado/Ensurdecido = Apenas Presença
        if voice.self_mute or voice.self_deaf or voice.mute or voice.deaf: return False
        
        # Sozinho = Apenas Presença
        humans_in_channel = [m for m in voice.channel.members if not m.bot]
        if len(humans_in_channel) < 2: return False
            
        return True

    async def reconcile_session(self, member):
        user_id = member.id
        now = datetime.datetime.now(BR_TIMEZONE)
        
        is_in_voice = member.voice and member.voice.channel
        is_counting = user_id in self.active_timers

        if is_in_voice and not is_counting:
            self.active_timers[user_id] = now

        elif not is_in_voice and is_counting:
            start_time = self.active_timers.pop(user_id)
            duration = (now - start_time).total_seconds() / 60
            if duration >= 1:
                # Sessão finalizada ao sair (assumimos validade 0 pois perdeu contexto)
                await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=0)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot:
            await self.reconcile_session(member)

    # --- COMANDO /VER_TEMPO ---
    @app_commands.command(name="ver_tempo", description="Admin: Verifica o tempo de voz (Relatório Privado).")
    async def check_voice_time(self, interaction: discord.Interaction, dias: int = 7, usuario: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        try:
            data = await db.get_voice_hours(dias)
            if not data:
                return await interaction.followup.send(f"❌ Nenhum registro encontrado nos últimos {dias} dias.", ephemeral=True)

            hours_map = {r['user_id']: r['total_mins'] for r in data}

            if usuario:
                mins = hours_map.get(usuario.id, 0)
                h, m = divmod(int(mins), 60)
                clean = utils.clean_voter_name(usuario.display_name)
                status = "🟢 Contando agora!" if usuario.id in self.active_timers else "⚪ Parado"
                await interaction.followup.send(f"⏱️ **{clean}** ({dias}d): **{h}h {m}m**\nStatus Atual: {status}", ephemeral=True)
            else:
                sorted_data = sorted(hours_map.items(), key=lambda x: x[1], reverse=True)
                lines = [f"📊 **Top Voz (Últimos {dias} dias)**"]
                for i, (uid, mins) in enumerate(sorted_data[:20]):
                    mem = interaction.guild.get_member(uid)
                    name = utils.clean_voter_name(mem.display_name) if mem else f"User {uid}"
                    h, m = divmod(int(mins), 60)
                    live = "🟢" if uid in self.active_timers else ""
                    lines.append(f"**{i+1}. {name}**: {h}h {m}m {live}")
                await interaction.followup.send("\n".join(lines), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Erro: {e}", ephemeral=True)

    # --- RANKING AUTOMÁTICO (HORÁRIO FIXO E VISUAL NOVO) ---
    # Define os horários: Todo minuto 00 e minuto 30 de cada hora
    times_list = [datetime.time(hour=h, minute=m, tzinfo=BR_TIMEZONE) for h in range(24) for m in [0, 30]]

    @tasks.loop(time=times_list)
    async def update_ranking_loop(self):
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild: return

        now = datetime.datetime.now(BR_TIMEZONE)
        
        # 1. SALVA PARCIAIS
        for user_id, start_time in list(self.active_timers.items()):
            member = guild.get_member(user_id)
            if member and member.voice:
                duration = (now - start_time).total_seconds() / 60
                if duration >= 1:
                    valid = 1 if self.check_validity_conditions(member) else 0
                    await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=valid)
                    self.active_timers[user_id] = now 

        # 2. COLETA E ORGANIZA DADOS
        data_7d = await db.get_voice_hours(7) # Apenas horas válidas para os Ranks Estéticos
        hours_map = {r['user_id']: r['total_mins']/60 for r in data_7d}
        
        all_members_data = []
        for member in guild.members:
            if member.bot: continue
            
            # FILTRO STAFF
            if any(r.id in [config.ROLE_FOUNDER_ID, config.ROLE_MOD_ID] for r in member.roles):
                continue

            # INATIVIDADE (Checagem visual rápida baseada em cargos atuais)
            # Se tiver o cargo Inativo, forçamos o rank visual para Inativo
            if member.get_role(config.ROLE_INATIVO):
                rank_title = "INATIVOS 🚷"
                h7 = 0 # Irrelevante para ordenação deste grupo
            else:
                h7 = hours_map.get(member.id, 0)
                # Definição de Rank baseada em horas
                if h7 >= RANK_THRESHOLDS['MESTRE']: rank_title = "MASTER ⭐"
                elif h7 >= RANK_THRESHOLDS['ADEPTO']: rank_title = "ADEPTO ⚔️"
                elif h7 >= RANK_THRESHOLDS['VANGUARDA']: rank_title = "VANGUARDA ⚡"
                elif h7 >= RANK_THRESHOLDS['ATIVO']: rank_title = "ATIVOS 🟢" # Mudado para plural para o grupo
                elif h7 >= RANK_THRESHOLDS['TURISTA']: rank_title = "TURISTAS 🧳"
                else: rank_title = "TURISTAS 🧳" # Fallback para quem tem pouca hora mas não é inativo

            all_members_data.append({'name': utils.clean_voter_name(member.display_name), 'h7': h7, 'rank': rank_title})

        # Ordena por horas (desc)
        all_members_data.sort(key=lambda x: x['h7'], reverse=True)

        # Agrupa
        ranks_config = {
            "MASTER ⭐": [],
            "ADEPTO ⚔️": [],
            "VANGUARDA ⚡": [],
            "ASCENDENTE 🚀": [], # Caso exista no futuro
            "TURISTAS 🧳": [],
            "ATIVOS 🟢": [],
            "INATIVOS 🚷": []
        }

        for p in all_members_data:
            key = p['rank']
            if key in ranks_config:
                ranks_config[key].append(p['name'])
            # Se o rank não estiver na config (ex: nome mudou), joga em Ativos
            elif "ATIVOS" in key: ranks_config["ATIVOS 🟢"].append(p['name'])
            else: ranks_config["TURISTAS 🧳"].append(p['name'])

        # 3. MONTA O EMBED
        embed = discord.Embed(
            title="🏆  QUADRO DE HONRA (7 Dias)", 
            color=discord.Color.gold()
        )
        
        # --- BLOCO MASTER (CENTRALIZADO NA DESCRIÇÃO) ---
        masters = ranks_config.pop("MASTER ⭐")
        if masters:
            # Tenta centralizar visualmente com espaços (funciona melhor em desktop)
            # Usando header markdown para aumentar fonte
            master_str = "\n".join([f"> 👑 **{name}**" for name in masters])
            embed.description = f"# 🥇  MASTER  ⭐\n{master_str}\n\n━━━━━━━━━━━━━━━━━━━━━━"
        else:
            embed.description = "# 🥇  MASTER  ⭐\n> *O trono está vazio...*\n\n━━━━━━━━━━━━━━━━━━━━━━"

        # --- BLOCO TIER MÉDIO (INLINE) ---
        # Adepto e Vanguarda lado a lado
        mid_tiers = ["ADEPTO ⚔️", "VANGUARDA ⚡"]
        for rank in mid_tiers:
            names = ranks_config.get(rank, [])
            value = "\n".join([f"• {n}" for n in names]) if names else "*Vazio*"
            embed.add_field(name=f"{rank} ({len(names)})", value=value, inline=True)
        
        # Adiciona um campo vazio se precisar alinhar grade de 3
        # embed.add_field(name="\u200b", value="\u200b", inline=True) 

        # --- BLOCO TIER BAIXO (INLINE - NOVA LINHA) ---
        low_tiers = ["TURISTAS 🧳", "ATIVOS 🟢", "INATIVOS 🚷"]
        for rank in low_tiers:
            names = ranks_config.get(rank, [])
            # Limita lista visual para não estourar o embed se tiver muita gente
            if len(names) > 15:
                display_names = names[:15]
                value = "\n".join([f"• {n}" for n in display_names]) + f"\n*+ {len(names)-15} outros...*"
            else:
                value = "\n".join([f"• {n}" for n in names]) if names else "*Vazio*"
            
            embed.add_field(name=f"{rank}", value=value, inline=True)

        # --- RODAPÉ EXPLICATIVO ---
        info_text = (
            "🎙️ **Como subir de Rank?**\n"
            "Participe das calls em grupo com o audio aberto (microfone tbm) e o bot vai logar cada minuto. "
            "Os minutos sozinho ou mutado contam apenas como 'Presença', mas não pontuam para o **Mestre**!"
        )
        embed.add_field(name="⠀", value=info_text, inline=False) # Campo Full Width no final

        if guild.icon: embed.set_thumbnail(url=guild.icon.url)
        embed.set_footer(text=f"Atualizado às {now.strftime('%H:%M')} • Staff não listado")

        # Envia/Edita
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
            except: pass

    @update_ranking_loop.before_loop
    async def before_ranking_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RankingCog(bot))
