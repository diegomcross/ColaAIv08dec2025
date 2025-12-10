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
        self.voice_sessions = {} # {user_id: start_time}
        self.update_ranking_loop.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        now = datetime.datetime.now(BR_TIMEZONE)
        
        # [DEBUG GERAL] Loga qualquer mudança para garantir que o evento está sendo recebido
        # Útil para saber se o bot tem permissão de ver o canal
        status_mute = "Mutado" if (member.voice and (member.voice.self_mute or member.voice.mute)) else "Ativo"
        status_deaf = "Ensdecido" if (member.voice and (member.voice.self_deaf or member.voice.deaf)) else "Ouvindo"
        nome_canal = after.channel.name if after.channel else "Saiu"
        print(f"[DEBUG-VOZ] {member.display_name} mudou estado: {status_mute} / {status_deaf} -> Canal: {nome_canal}")

        # 1. Entrou no canal (e não está mutado) -> INÍCIO
        if not before.channel and after.channel:
            if not (member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf):
                 self.voice_sessions[member.id] = now
                 print(f"[✅ START] {member.display_name} iniciou contagem em '{after.channel.name}' às {now.strftime('%H:%M:%S')}.")
            else:
                 print(f"[⚠️ START-FALHOU] {member.display_name} entrou mas está mutado/surdo. Contagem não iniciada.")
        
        # 2. Saiu ou Mutou -> FIM
        elif before.channel and (not after.channel or after.self_mute or after.self_deaf):
            if member.id in self.voice_sessions:
                start_time = self.voice_sessions.pop(member.id)
                
                # Cálculo de tempo
                duration_seconds = (now - start_time).total_seconds()
                duration_minutes = duration_seconds / 60
                
                print(f"[🛑 STOP] {member.display_name} parou de contar. Duração bruta: {int(duration_minutes)}m {int(duration_seconds % 60)}s.")

                # Regra Anti-Farm: Só conta se tinha mais de 1 pessoa no canal
                # O membro que saiu ainda consta na lista 'before.channel.members' nesse instante
                member_count = len(before.channel.members)
                
                if member_count > 1: 
                    if duration_minutes > 1: # Mínimo 1 minuto
                         await db.log_voice_session(member.id, start_time, now, int(duration_minutes))
                         print(f"[💰 SALVANDO] Sessão de {member.display_name} validada! (+{int(duration_minutes)} min). Membros no canal: {member_count}")
                    else:
                        print(f"[⚠️ REJEITADO] {member.display_name}: Tempo muito curto (<1 min).")
                else:
                    print(f"[⚠️ ANTI-FARM] Sessão de {member.display_name} ignorada. Estava sozinho (Membros: {member_count}).")
            else:
                # Caso saia mas não tinha sessão aberta (ex: já estava mutado antes)
                if not after.channel:
                    print(f"[ℹ️ INFO] {member.display_name} desconectou, mas não estava contando tempo (provavelmente já estava mutado).")

    # --- COMANDO PARA VERIFICAR TEMPO (MANUAL) ---
    @app_commands.command(name="ver_tempo", description="Admin: Verifica o tempo de voz (Relatório Privado).")
    @app_commands.describe(dias="Quantos dias atrás analisar? (Padrão 7)", usuario="Verificar um usuário específico")
    async def check_voice_time(self, interaction: discord.Interaction, dias: int = 7, usuario: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        try:
            data = await db.get_voice_hours(dias)
            if not data:
                return await interaction.followup.send(f"❌ Nenhum registro de voz encontrado nos últimos {dias} dias.", ephemeral=True)

            hours_map = {r['user_id']: r['total_mins'] for r in data}

            if usuario:
                mins = hours_map.get(usuario.id, 0)
                hours = int(mins / 60)
                minutes = int(mins % 60)
                clean_name = utils.clean_voter_name(usuario.display_name)
                await interaction.followup.send(f"⏱️ **Relatório de {clean_name}** ({dias} dias):\nTempo Total: **{hours}h {minutes}m**", ephemeral=True)
            else:
                sorted_data = sorted(hours_map.items(), key=lambda x: x[1], reverse=True)
                lines = [f"📊 **Relatório de Voz (Últimos {dias} dias)**"]
                for i, (uid, mins) in enumerate(sorted_data[:20]):
                    member = interaction.guild.get_member(uid)
                    name = utils.clean_voter_name(member.display_name) if member else f"User {uid}"
                    h = int(mins / 60)
                    m = int(mins % 60)
                    lines.append(f"**{i+1}. {name}**: {h}h {m}m")
                
                if not sorted_data: lines.append("_Nenhum dado._")
                await interaction.followup.send("\n".join(lines), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Erro ao buscar dados: {e}", ephemeral=True)

    # --- ATUALIZAÇÃO AUTOMÁTICA (A CADA 30 MINUTOS) ---
    @tasks.loop(minutes=30)
    async def update_ranking_loop(self):
        """Atualiza Leaderboard e Cargos"""
        print(f"[🔄 LOOP] Iniciando atualização do Ranking de Voz (Ciclo de 30min)...")
        
        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild: 
            print("[🔄 LOOP] Erro: Guilda não encontrada.")
            return

        # Pega dados do banco
        data_7d = await db.get_voice_hours(7)
        data_14d = await db.get_voice_hours(14)
        
        hours_7d = {r['user_id']: r['total_mins']/60 for r in data_7d}
        hours_14d = {r['user_id']: r['total_mins']/60 for r in data_14d}
        
        leaderboard = []
        
        for member in guild.members:
            if member.bot: continue
            
            h7 = hours_7d.get(member.id, 0)
            if h7 == 0: continue # Ignora quem tem 0 horas

            h14 = hours_14d.get(member.id, 0)
            rank = "INATIVO"
            
            # Lógica de Cargos
            if h7 >= RANK_THRESHOLDS['MESTRE']: rank = "MESTRE ⭐"
            elif h7 >= RANK_THRESHOLDS['ADEPTO']: rank = "ADEPTO ⚔️"
            elif h7 >= RANK_THRESHOLDS['VANGUARDA']: rank = "VANGUARDA ⚡"
            elif h14 >= RANK_THRESHOLDS['ATIVO']: rank = "ATIVO"
            elif h14 >= RANK_THRESHOLDS['TURISTA']: rank = "TURISTA 🟢"
            
            clean_name = utils.clean_voter_name(member.display_name)
            leaderboard.append({'name': clean_name, 'h7': h7, 'rank': rank})

        # Ordenar e Exibir
        leaderboard.sort(key=lambda x: x['h7'], reverse=True)
        
        top_player = leaderboard[0]['name'] if leaderboard else 'Ninguém'
        print(f"[🔄 LOOP] Ranking calculado. {len(leaderboard)} usuários ranqueados. Top 1: {top_player}")

        channel = guild.get_channel(config.CHANNEL_RANKING)
        if channel:
            desc = ""
            if not leaderboard:
                desc = "*Ainda não há registros de atividade esta semana.*"
            else:
                for i, p in enumerate(leaderboard[:20]):
                    desc += f"**{i+1}. {p['name']}**: {p['rank']}\n"
            
            embed = discord.Embed(title="🏆 Ranking de Atividade (Voz - 7 Dias)", description=desc, color=discord.Color.gold())
            embed.set_footer(text=f"Atualizado em {datetime.datetime.now(BR_TIMEZONE).strftime('%H:%M')}")
            
            try:
                last_msg = None
                async for msg in channel.history(limit=20):
                    if msg.author == self.bot.user:
                        last_msg = msg
                        break
                
                if last_msg:
                    await last_msg.edit(embed=embed)
                    print("[🔄 LOOP] Mensagem de Ranking editada com sucesso.")
                else:
                    await channel.purge(limit=5)
                    await channel.send(embed=embed)
                    print("[🔄 LOOP] Nova mensagem de Ranking enviada.")
            except Exception as e:
                print(f"[RANKING ERRO] Falha ao enviar/editar mensagem: {e}")

    @update_ranking_loop.before_loop
    async def before_ranking_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RankingCog(bot))
