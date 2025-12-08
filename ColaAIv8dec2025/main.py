import discord
from discord.ext import commands
import config
import database
from views import PersistentRsvpView

class ClanBot(commands.Bot):
    def __init__(self):
        # Intents são permissões para o bot ver mensagens, membros, etc.
        intents = discord.Intents.all()
        super().__init__(command_prefix='!', intents=intents, help_command=None)

    async def setup_hook(self):
        # 1. Inicializa o Banco de Dados
        await database.init_db()
        
        # 2. Carrega as extensões (Cogs)
        # Certifique-se de que os arquivos events.py, tasks.py, ranking.py e polls.py estão dentro da pasta "cogs"
        extensions = ['cogs.events', 'cogs.tasks', 'cogs.ranking', 'cogs.polls']
        for ext in extensions:
            try:
                await self.load_extension(ext)
                print(f"Carregado: {ext}")
            except Exception as e:
                print(f"Erro ao carregar {ext}: {e}")
        
        # 3. Adiciona as Views Persistentes (para botões funcionarem após reinício)
        self.add_view(PersistentRsvpView())
        
        # 4. Sincroniza os Comandos Slash (/) com o Discord
        await self.tree.sync()
        print(f"Logado como {self.user} e pronto!")

bot = ClanBot()

if __name__ == '__main__':
    try:
        bot.run(config.TOKEN)
    except Exception as e:
        print(f"Erro ao iniciar o bot: {e}")
