import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# IDs dos Canais Fixos
CHANNEL_RANKING = 1361499182304592012
CHANNEL_MAIN_CHAT = 1357316018535403661
CHANNEL_EVENT_LOGS = 1357722794674229351 
CHANNEL_POLLS = 1447650420691570748 
CHANNEL_LFG = 1435294107991019560
CHANNEL_SCHEDULE = 1447815990174945290

# Categoria de Eventos
CATEGORY_EVENTS_ID = 1357809570298331295

# --- CONFIGURAÇÃO DE CARGOS E HIERARQUIA ---

# Cargos que NÃO aparecem no Ranking (Staff)
ROLE_FOUNDER_ID = 1362747097824100474
ROLE_MOD_ID = 1362746553600839781

# Cargos de Conquista (Gerenciados pelo Bot - Baseado em Presença/Comportamento)
ROLE_PRESENTE_SEMPRE = 1383132076060184618  # >1h/dia, 5 dias/sem
ROLE_GALERA_FDS = 1361501474563035339       # Só Sex/Sab/Dom
ROLE_TURISTA = 1383131713265340486          # 1-2x na semana
ROLE_INATIVO = 1383131849571696741          # 0 atividade em 21 dias

# Cargos de Ranking (Estéticos - Baseado em Horas Anti-Farm)
# O bot vai procurar por nome, mas se precisar de IDs fixos, podemos por aqui.
# Por enquanto usaremos a lógica de criar/buscar pelo nome definido em constants.py

# Data de Início da "Era da Inatividade" (Para não banir retroativamente)
# O bot só vai checar inatividade se a data atual for > que esta data + 21 dias.
DEPLOY_DATE = datetime(2025, 5, 20) # Coloquei uma data futura segura ou use a data de hoje.
# Sugestão: Deixe o código usar a data do sistema, veja em cogs/roles.py
