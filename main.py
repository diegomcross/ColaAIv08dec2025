import discord
from discord.ext import commands
import config
import database
from views import PersistentRsvpView

class ClanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix='!', intents=intents, help_command=None)

    async def setup_hook(self):
        # 1. Banco de Dados
        await database.init_db()
        
        # 2. Cogs
        extensions = ['cogs.events', 'cogs.tasks', 'cogs.ranking', 'cogs.polls'] # Adicionado polls
        for ext in extensions:
            try:
                await self.load_extension(ext)
            except Exception as e:
                print(f"Erro ao carregar {ext}: {e}")
        
        # 3. Persistent Views
        self.add_view(PersistentRsvpView())
        
        # 4. Sync Comandos Slash
        await self.tree.sync()
        print(f"Logado como {self.user} e pronto!")

bot = ClanBot()

if __name__ == '__main__':
    bot.run(config.TOKEN)