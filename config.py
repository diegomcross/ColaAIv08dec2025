import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# IDs dos Canais Fixos
CHANNEL_RANKING = 1361499182304592012
CHANNEL_MAIN_CHAT = 1357316018535403661
CHANNEL_EVENT_LOGS = 1357722794674229351 
CHANNEL_POLLS = 1447650420691570748 # Canal apenas para notificações automáticas/logs de enquetes
CHANNEL_LFG = 1435294107991019560   # Canal "Procure Atividades"

# Categoria onde os canais de eventos serão criados
CATEGORY_EVENTS_ID = 1357809570298331295
