import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# IDs dos Canais Fixos
CHANNEL_RANKING = 1361499182304592012
CHANNEL_MAIN_CHAT = 1357316018535403661
CHANNEL_EVENT_LOGS = 1357722794674229351 # Canal para logs de conclusão
CHANNEL_POLLS = 1447650420691570748 # Substitua pelo ID do canal de enquetes

# Categoria onde os canais de eventos serão criados (ID Corrigido)
CATEGORY_EVENTS_ID = 1357809570298331295
