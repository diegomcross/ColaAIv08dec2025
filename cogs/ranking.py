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

    def check_validity_conditions(self, member):
        """
        Retorna True se a sessão é VÁLIDA para Ranking (Anti-Farm).
        Retorna False se é apenas Presença (Sozinho ou Mutado).
        """
        if member.bot: return False
        
        voice = member.voice
        if not voice or not voice.channel: return False
        
        # Se estiver mutado/ensurdecido = INVÁLIDO para ranking, mas conta como PRESENÇA
        if voice.self_mute or voice.self_deaf or voice.mute or voice.deaf:
            return False
            
        # Se estiver sozinho = INVÁLIDO para ranking, mas conta como PRESENÇA
        humans_in_channel = [m for m in voice.channel.members if not m.bot]
        if len(humans_in_channel) < 2:
            return False
            
        return True

    async def reconcile_session(self, member):
        """
        Registra entrada/saída.
        """
        user_id = member.id
        now = datetime.datetime.now(BR_TIMEZONE)
        
        is_in_voice = member.voice and member.voice.channel
        is_counting = user_id in self.active_timers

        if is_in_voice and not is_counting:
            # INICIA O RELÓGIO (Sempre que entrar)
            self.active_timers[user_id] = now

        elif not is_in_voice and is_counting:
            # SAIU DA VOZ -> SALVA SESSÃO
            start_time = self.active_timers.pop(user_id)
            duration = (now - start_time).total_seconds() / 60
            
            if duration >= 1:
                # Se saiu, não temos o estado 'voice' dele mais para validar.
                # Assumimos presença geral (is_valid=0) para o trecho final.
                await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=0)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Dispara reconciliação para quem mudou
        if not member.bot:
            await self.reconcile_session(member)

    # --- COMANDO /VER_TEMPO ---
    @app_commands.command(name="ver_tempo", description="Admin: Verifica o tempo de voz (Relatório Privado).")
    @app_commands.describe(dias="Quantos dias atrás analisar? (Padrão 7)", usuario="Verificar um usuário específico")
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

    # --- RANKING AUTOMÁTICO (VISUAL AGRUPADO) ---
    @tasks.loop(minutes=30)
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

        # 2. COLETA DADOS
        data_7d = await db.get_voice_hours(7)
        hours_map = {r['user_id']: r['total_mins']/60 for r in data_7d}
        
        # Lista temporária para ordenar todos antes de agrupar
        all_members_data = []

        for member in guild.members:
            if member.bot: continue
            
            # FILTRO: Ignora Fundador e Moderador no PLACAR
            has_founder = any(r.id == config.ROLE_FOUNDER_ID for r in member.roles)
            has_mod = any(r.id == config.ROLE_MOD_ID for r in member.roles)
            if has_founder or has_mod:
                continue

            h7 = hours_map.get(member.id, 0)
            if h7 == 0: continue

            # Define Rank
            rank_title = "Membro"
            if h7 >= RANK_THRESHOLDS['MESTRE']: rank_title = "MESTRE ⭐"
            elif h7 >= RANK_THRESHOLDS['ADEPTO']: rank_title = "ADEPTO ⚔️"
            elif h7 >= RANK_THRESHOLDS['VANGUARDA']: rank_title = "VANGUARDA ⚡"
            elif h7 >= RANK_THRESHOLDS['ATIVO']: rank_title = "ATIVO"
            
            all_members_data.append({'name': utils.clean_voter_name(member.display_name), 'h7': h7, 'rank': rank_title})

        # Ordena geral por horas (maior para menor) para manter a ordem dentro dos grupos
        all_members_data.sort(key=lambda x: x['h7'], reverse=True)

        # 3. AGRUPA POR RANK
        ranks_order = ["MESTRE ⭐", "ADEPTO ⚔️", "VANGUARDA ⚡", "ATIVO", "Membro"]
        grouped_ranks = {k: [] for k in ranks_order}

        for p in all_members_data:
            if p['rank'] in grouped_ranks:
                grouped_ranks[p['rank']].append(p['name'])

        # 4. MONTA O EMBED
        channel = guild.get_channel(config.CHANNEL_RANKING)
        if channel:
            desc = ""
            for rank in ranks_order:
                names_list = grouped_ranks[rank]
                if names_list:
                    # Formata: Titulo do Rank em Negrito e nomes abaixo
                    names_str = ", ".join(names_list)
                    desc += f"### {rank}\n{names_str}\n\n"
            
            if not desc:
                desc = "*O silêncio reina... Ninguém entrou em call essa semana.*"

            embed = discord.Embed(
                title="🏆  Ranking de Atividade (Voz - 7 Dias)", 
                description=desc, 
                color=discord.Color.gold()
            )
            
            if guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
                
            embed.set_footer(text=f"Atualizado às {now.strftime('%H:%M')} • Staff não listado")
            
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
