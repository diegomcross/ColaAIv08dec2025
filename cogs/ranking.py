import discord
from discord import app_commands
from discord.ext import commands, tasks
import database as db
import datetime
from constants import BR_TIMEZONE, RANK_THRESHOLDS
import config

class RankingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voice_sessions = {} # {user_id: start_time}
        self.update_ranking_loop.start()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        now = datetime.datetime.now(BR_TIMEZONE)
        
        # Entrou no canal (e não está mutado)
        if not before.channel and after.channel:
            if not (member.voice.self_mute or member.voice.self_deaf or member.voice.mute or member.voice.deaf):
                 self.voice_sessions[member.id] = now
                 print(f"[VOZ] {member.display_name} começou a contar tempo.")
        
        # Saiu ou Mutou
        elif before.channel and (not after.channel or after.self_mute or after.self_deaf):
            if member.id in self.voice_sessions:
                start_time = self.voice_sessions.pop(member.id)
                
                # Regra Anti-Farm: Só conta se tinha mais de 1 pessoa no canal (não estava sozinho)
                # Nota: before.channel.members ainda inclui a pessoa que saiu neste momento do evento
                if len(before.channel.members) > 1: 
                    duration = (now - start_time).total_seconds() / 60
                    if duration > 1: # Mínimo 1 minuto
                         await db.log_voice_session(member.id, start_time, now, int(duration))
                         print(f"[VOZ] Sessão salva: {member.display_name} ficou {int(duration)} minutos.")
                    else:
                        print(f"[VOZ] {member.display_name}: Tempo muito curto (<1 min).")
                else:
                    print(f"[VOZ] {member.display_name}: Sozinho no canal (Anti-Farm).")

    # --- NOVO COMANDO PRIVADO ---
    @app_commands.command(name="ver_tempo", description="Admin: Verifica o tempo de voz (Relatório Privado).")
    @app_commands.describe(dias="Quantos dias atrás analisar? (Padrão 7)", usuario="Verificar um usuário específico")
    async def check_voice_time(self, interaction: discord.Interaction, dias: int = 7, usuario: discord.Member = None):
        # Apenas você vê a resposta (ephemeral)
        await interaction.response.defer(ephemeral=True)
        
        # Busca dados do banco
        data = await db.get_voice_hours(dias)
        
        if not data:
            return await interaction.followup.send(f"❌ Nenhum registro de voz encontrado nos últimos {dias} dias.", ephemeral=True)

        # Transforma a lista do banco em um dicionário {id: minutos}
        hours_map = {r['user_id']: r['total_mins'] for r in data}

        if usuario:
            # Mostra apenas o usuário solicitado
            mins = hours_map.get(usuario.id, 0)
            hours = int(mins / 60)
            minutes = int(mins % 60)
            await interaction.followup.send(f"⏱️ **Relatório de {usuario.display_name}** ({dias} dias):\nTempo Total: **{hours}h {minutes}m**", ephemeral=True)
        else:
            # Mostra um Top 20 Geral
            sorted_data = sorted(hours_map.items(), key=lambda x: x[1], reverse=True)
            
            lines = [f"📊 **Relatório de Voz (Últimos {dias} dias)**"]
            for i, (uid, mins) in enumerate(sorted_data[:20]):
                member = interaction.guild.get_member(uid)
                name = member.display_name if member else f"User {uid}"
                h = int(mins / 60)
                m = int(mins % 60)
                lines.append(f"**{i+1}. {name}**: {h}h {m}m")
            
            if not sorted_data:
                lines.append("_Nenhum dado._")
                
            await interaction.followup.send("\n".join(lines), ephemeral=True)

    @tasks.loop(hours=3)
    async def update_ranking_loop(self):
        """Atualiza Leaderboard e Cargos (Edita mensagem para evitar spam)"""
        guild = self.bot.get_guild(int(config.GUILD_ID)) if hasattr(config, 'GUILD_ID') else self.bot.guilds[0]
        if not guild: return

        # Pegar dados (Rolling 7 days para ranking principal)
        data_7d = await db.get_voice_hours(7)
        data_14d = await db.get_voice_hours(14)
        
        hours_7d = {r['user_id']: r['total_mins']/60 for r in data_7d}
        hours_14d = {r['user_id']: r['total_mins']/60 for r in data_14d}
        
        leaderboard = []
        
        for member in guild.members:
            if member.bot: continue
            
            h7 = hours_7d.get(member.id, 0)
            
            # FILTRO: Se não tiver horas, não entra no ranking
            if h7 == 0: continue

            h14 = hours_14d.get(member.id, 0)
            rank = "INATIVO"
            
            # Lógica Hierárquica
            if h7 >= RANK_THRESHOLDS['MESTRE']: rank = "MESTRE ⭐"
            elif h7 >= RANK_THRESHOLDS['ADEPTO']: rank = "ADEPTO ⚔️"
            elif h7 >= RANK_THRESHOLDS['VANGUARDA']: rank = "VANGUARDA ⚡"
            elif h14 >= RANK_THRESHOLDS['ATIVO']: rank = "ATIVO"
            elif h14 >= RANK_THRESHOLDS['TURISTA']: rank = "TURISTA 🟢"
            
            leaderboard.append({'name': member.display_name, 'h7': h7, 'rank': rank})

        # Ordenar
        leaderboard.sort(key=lambda x: x['h7'], reverse=True)
        
        channel = guild.get_channel(config.CHANNEL_RANKING)
        if channel:
            desc = ""
            if not leaderboard:
                desc = "*Ainda não há registros de atividade esta semana.*"
            else:
                for i, p in enumerate(leaderboard[:20]): # Top 20
                    desc += f"**{i+1}. {p['name']}**: {p['rank']}\n"
            
            embed = discord.Embed(title="🏆 Ranking de Atividade (Voz - 7 Dias)", description=desc, color=discord.Color.gold())
            embed.set_footer(text=f"Atualizado em {datetime.datetime.now(BR_TIMEZONE).strftime('%H:%M')}")
            
            try:
                # Tenta encontrar a última mensagem do bot para editar
                last_msg = None
                async for msg in channel.history(limit=20):
                    if msg.author == self.bot.user:
                        last_msg = msg
                        break
                
                if last_msg:
                    await last_msg.edit(embed=embed)
                else:
                    await channel.purge(limit=5)
                    await channel.send(embed=embed)
            except Exception as e:
                print(f"[RANKING] Erro ao atualizar: {e}")

    @update_ranking_loop.before_loop
    async def before_ranking_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RankingCog(bot))
