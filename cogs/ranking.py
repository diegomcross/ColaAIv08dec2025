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
        Diferente da versão anterior, agora registramos TUDO, mas com a flag is_valid.
        """
        user_id = member.id
        now = datetime.datetime.now(BR_TIMEZONE)
        
        is_in_voice = member.voice and member.voice.channel
        is_counting = user_id in self.active_timers

        if is_in_voice and not is_counting:
            # INICIA O RELÓGIO (Independente de estar sozinho ou mutado)
            self.active_timers[user_id] = now
            # print(f"[▶️ LOG] {member.display_name} entrou em voz.")

        elif not is_in_voice and is_counting:
            # SAIU DA VOZ -> SALVA SESSÃO
            start_time = self.active_timers.pop(user_id)
            duration = (now - start_time).total_seconds() / 60
            
            if duration >= 1:
                # Checa se a sessão foi "Válida" (Anti-Farm) baseada no estado FINAL
                # (Limitação técnica: checamos o estado ao sair ou periodicamente. 
                # Para ser perfeito precisaria logar cada troca de mute, mas isso spamaria o banco)
                # Vamos assumir: Se ele saiu, não temos o estado 'voice' dele mais.
                # Então a validação real acontece no loop de 30min ou assumimos False se saiu?
                # Melhor: Vamos confiar na validação periódica do loop para sessões longas.
                # Para sessões curtas que terminam aqui, vamos assumir is_valid=0 por segurança 
                # ou tentar recuperar o estado anterior (difícil).
                # DECISÃO: Logamos como is_valid=0 aqui se não pudermos provar o contrário,
                # MAS o loop update_ranking_loop vai salvar parciais com a flag correta.
                
                # Como o member.voice é None agora (ele saiu), não dá pra checar mute.
                # Vamos salvar como presença genérica (0) aqui.
                # As horas "Rankeadas" serão salvas principalmente pelo loop periódico enquanto ele ESTÁ no canal.
                await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=0)
                # print(f"[⏹️ LOG] {member.display_name}: {int(duration)} min (Finalizado)")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Apenas dispara o reconciliador para quem mudou
        if not member.bot:
            await self.reconcile_session(member)

    # --- RANKING AUTOMÁTICO (E SALVAMENTO PERIÓDICO) ---
    @tasks.loop(minutes=30)
    async def update_ranking_loop(self):
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild: return

        now = datetime.datetime.now(BR_TIMEZONE)
        
        # 1. SALVA PARCIAIS (Fundamental para Ranking funcionar)
        # Verifica o estado ATUAL de cada um para definir is_valid
        for user_id, start_time in list(self.active_timers.items()):
            member = guild.get_member(user_id)
            if member and member.voice:
                duration = (now - start_time).total_seconds() / 60
                if duration >= 1:
                    # AQUI validamos se conta para o Ranking ou só Presença
                    valid = 1 if self.check_validity_conditions(member) else 0
                    
                    await db.log_voice_session(user_id, start_time, now, int(duration), is_valid=valid)
                    self.active_timers[user_id] = now # Reseta timer para continuar contando

        # 2. GERA PLACAR (Apenas is_valid=1)
        data_7d = await db.get_voice_hours(7)
        hours_map = {r['user_id']: r['total_mins']/60 for r in data_7d}
        
        leaderboard = []
        for member in guild.members:
            if member.bot: continue
            
            # FILTRO: Ignora Fundador e Moderador no PLACAR (mas os dados foram salvos no DB)
            has_founder = any(r.id == config.ROLE_FOUNDER_ID for r in member.roles)
            has_mod = any(r.id == config.ROLE_MOD_ID for r in member.roles)
            if has_founder or has_mod:
                continue

            h7 = hours_map.get(member.id, 0)
            if h7 == 0: continue

            # Define Rank Estético
            rank_title = "Membro"
            if h7 >= RANK_THRESHOLDS['MESTRE']: rank_title = "MESTRE ⭐"
            elif h7 >= RANK_THRESHOLDS['ADEPTO']: rank_title = "ADEPTO ⚔️"
            elif h7 >= RANK_THRESHOLDS['VANGUARDA']: rank_title = "VANGUARDA ⚡"
            elif h7 >= RANK_THRESHOLDS['ATIVO']: rank_title = "ATIVO"
            
            leaderboard.append({'name': utils.clean_voter_name(member.display_name), 'h7': h7, 'rank': rank_title})

        leaderboard.sort(key=lambda x: x['h7'], reverse=True)
        
        channel = guild.get_channel(config.CHANNEL_RANKING)
        if channel:
            desc = ""
            for i, p in enumerate(leaderboard[:20]):
                desc += f"**{i+1}. {p['name']}**: {p['rank']} ({p['h7']:.1f}h)\n"
            
            embed = discord.Embed(title="🏆 Ranking de Atividade (Voz - 7 Dias)", description=desc or "*Sem dados*", color=discord.Color.gold())
            embed.set_footer(text=f"Atualizado em {now.strftime('%H:%M')} • Staff oculto")
            
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
