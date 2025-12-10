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
        # Armazena apenas QUEM está contando tempo AGORA
        # {user_id: datetime_inicio}
        self.active_timers = {} 
        self.update_ranking_loop.start()

    def is_eligible(self, member):
        """
        Regras de Ouro para contar tempo:
        1. Estar em canal de voz
        2. NÃO estar mutado (mic) e NÃO estar ensurdecido (fone)
        3. Ter companhia humana (Total de humanos no canal > 1)
        """
        if member.bot: return False
        
        voice = member.voice
        if not voice or not voice.channel:
            return False
        
        # Regra de Mute/Deaf (Vale tanto para o próprio quanto para mute de servidor)
        if voice.self_mute or voice.self_deaf or voice.mute or voice.deaf:
            return False
            
        # Regra de Companhia (Anti-Farm)
        # Conta quantos humanos (não bots) estão no canal
        humans_in_channel = [m for m in voice.channel.members if not m.bot]
        if len(humans_in_channel) < 2:
            return False
            
        return True

    async def reconcile_session(self, member):
        """
        Avalia o estado atual do usuário e decide se Inicia ou Para o relógio.
        """
        user_id = member.id
        now = datetime.datetime.now(BR_TIMEZONE)
        should_be_counting = self.is_eligible(member)
        is_counting = user_id in self.active_timers

        if should_be_counting and not is_counting:
            # INICIA O RELÓGIO
            self.active_timers[user_id] = now
            print(f"[▶️ PLAY] {member.display_name} começou a contar em '{member.voice.channel.name}'.")

        elif not should_be_counting and is_counting:
            # PARA O RELÓGIO E SALVA
            start_time = self.active_timers.pop(user_id)
            duration = (now - start_time).total_seconds() / 60
            
            if duration >= 1: # Só salva se tiver pelo menos 1 minuto
                await db.log_voice_session(user_id, start_time, now, int(duration))
                print(f"[⏸️ PAUSE] {member.display_name}: Salvo +{int(duration)} min. (Condição falhou ou saiu)")
            else:
                print(f"[⚠️ CURTO] {member.display_name}: Sessão descartada (<1 min).")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Lista de usuários que precisam ser reavaliados devido a essa mudança
        users_to_check = set()
        
        # 1. O próprio usuário que mexeu
        users_to_check.add(member)
        
        # 2. Se saiu de um canal, reavalia TODOS que ficaram lá (podem ter ficado sozinhos)
        if before.channel:
            for m in before.channel.members:
                users_to_check.add(m)
        
        # 3. Se entrou num canal, reavalia TODOS que já estavam lá (podem ter ganho companhia)
        if after.channel:
            for m in after.channel.members:
                users_to_check.add(m)

        # Processa a lista (remove bots da checagem)
        for m in users_to_check:
            if not m.bot:
                await self.reconcile_session(m)

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
                # Avisa se o usuário está contando tempo AGORA
                status = "🟢 Contando agora!" if usuario.id in self.active_timers else "⚪ Parado"
                await interaction.followup.send(f"⏱️ **{clean}** ({dias}d): **{h}h {m}m**\nStatus Atual: {status}", ephemeral=True)
            else:
                sorted_data = sorted(hours_map.items(), key=lambda x: x[1], reverse=True)
                lines = [f"📊 **Top Voz (Últimos {dias} dias)**"]
                for i, (uid, mins) in enumerate(sorted_data[:20]):
                    mem = interaction.guild.get_member(uid)
                    name = utils.clean_voter_name(mem.display_name) if mem else f"User {uid}"
                    h, m = divmod(int(mins), 60)
                    
                    # Indicador visual se está online na voz contando
                    live = "🟢" if uid in self.active_timers else ""
                    lines.append(f"**{i+1}. {name}**: {h}h {m}m {live}")
                
                await interaction.followup.send("\n".join(lines), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Erro: {e}", ephemeral=True)

    # --- RANKING AUTOMÁTICO ---
    @tasks.loop(minutes=30)
    async def update_ranking_loop(self):
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild: return

        # Força salvamento de todos os timers ativos para atualizar o ranking com o tempo atual
        # (Isso faz "parciais" de tempo em vez de esperar a pessoa sair para contar no ranking)
        now = datetime.datetime.now(BR_TIMEZONE)
        for user_id, start_time in list(self.active_timers.items()):
            duration = (now - start_time).total_seconds() / 60
            if duration >= 1:
                await db.log_voice_session(user_id, start_time, now, int(duration))
                self.active_timers[user_id] = now # Reseta o timer para 'agora' para continuar contando

        # Gera Ranking
        data_7d = await db.get_voice_hours(7)
        data_14d = await db.get_voice_hours(14)
        
        hours_7d = {r['user_id']: r['total_mins']/60 for r in data_7d}
        hours_14d = {r['user_id']: r['total_mins']/60 for r in data_14d}
        
        leaderboard = []
        for member in guild.members:
            if member.bot: continue
            h7 = hours_7d.get(member.id, 0)
            if h7 == 0: continue

            h14 = hours_14d.get(member.id, 0)
            rank = "INATIVO"
            if h7 >= RANK_THRESHOLDS['MESTRE']: rank = "MESTRE ⭐"
            elif h7 >= RANK_THRESHOLDS['ADEPTO']: rank = "ADEPTO ⚔️"
            elif h7 >= RANK_THRESHOLDS['VANGUARDA']: rank = "VANGUARDA ⚡"
            elif h14 >= RANK_THRESHOLDS['ATIVO']: rank = "ATIVO"
            elif h14 >= RANK_THRESHOLDS['TURISTA']: rank = "TURISTA 🟢"
            
            leaderboard.append({'name': utils.clean_voter_name(member.display_name), 'h7': h7, 'rank': rank})

        leaderboard.sort(key=lambda x: x['h7'], reverse=True)
        
        channel = guild.get_channel(config.CHANNEL_RANKING)
        if channel:
            desc = ""
            for i, p in enumerate(leaderboard[:20]):
                desc += f"**{i+1}. {p['name']}**: {p['rank']}\n"
            
            embed = discord.Embed(title="🏆 Ranking de Atividade (Voz - 7 Dias)", description=desc or "*Sem dados*", color=discord.Color.gold())
            embed.set_footer(text=f"Atualizado em {now.strftime('%H:%M')}")
            
            try:
                last_msg = None
                async for msg in channel.history(limit=20):
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
