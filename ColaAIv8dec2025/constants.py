# constants.py
import pytz

# --- Configurações de Fuso Horário ---
BRAZIL_TZ_STR = 'America/Sao_Paulo'
BR_TIMEZONE = pytz.timezone(BRAZIL_TZ_STR)

# --- Formatação de Data/Hora ---
DIAS_SEMANA_PT_FULL = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
DIAS_SEMANA_PT_SHORT = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
MESES_PT = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# --- Emojis Principais (Emoji 1) ---
ACTIVITY_EMOJIS = {
    'RAID': '💀',
    'MASMORRA': '🗡️',
    'PVP': '⚔️',
    'OUTRO': '🔰'
}

# --- Emojis de Modo (Emoji 2) ---
# O bot procurará estas palavras-chave na descrição/título
ACTIVITY_MODES = {
    'escola': '🧑‍🏫',
    'ensinando': '🧑‍🏫',
    'farm': '🌾',
    'mestre': '⭐',
    'épico': '⭐',
    'desafio': '⭐',
    'selo': '⭐',
    'triunfo': '⭐'
}

# --- Mapeamento para Nomes de Canal Simplificados ---
# De: Nome Oficial -> Para: Nome no Canal
CHANNEL_NAME_MAPPINGS = {
    # Raids
    "Queda do Rei": "oryx",
    "O Fim de Crota": "crota",
    "Câmara de Cristal": "câmara",
    "Último Desejo": "último desejo",
    "Jardim da Salvação": "jardim",
    "Cripta da Pedra Profunda": "cripta",
    "Voto do Discípulo": "voto",
    "Raiz dos Pesadelos": "raiz",
    "Limiar da Salvação": "limiar",
    "Deserto Perpétuo": "deserto",
    
    # Masmorras
    "Profecia": "profecia",
    "Trono Estilhaçado": "trono",
    "Poço da Heresia": "poço",
    "Dualidade": "dualidade",
    "Pináculo da Sentinela": "pináculo",
    "Fantasmas das Profundezas": "fantasmas",
    "Ruína da Senhora da Guerra": "ruina",
    "Domínio de Vesper": "vesper",
    "Doutrina Apartada": "doutrina",
    "Equilíbrio": "equilibrio",
    
    # PvP
    "Desafios de Osíris": "osiris",
    "Bandeira de Ferro": "bandeira",
    "Crisol": "crisol"
}

# --- LISTAS DE ATIVIDADES PARA DETECÇÃO (PT-BR) ---

RAID_INFO_PT = {
    "Queda do Rei": ["queda", "oryx", "queda do rei", "king's fall", "kings fall", "kf"],
    "O Fim de Crota": ["crota", "fim de crota", "crota's end", "crotas end", "ce"],
    "Câmara de Cristal": ["camara", "câmara", "vog", "camara de cristal", "câmara de cristal", "vault of glass"],
    "Último Desejo": ["riven", "ultimo desejo", "último desejo", "last wish", "lw"],
    "Jardim da Salvação": ["jardim", "jardim da salvação", "garden", "garden of salvation", "gos"],
    "Cripta da Pedra Profunda": ["cripta", "cripta da pedra", "dsc", "deep stone crypt"],
    "Voto do Discípulo": ["voto", "discípulo", "voto do discípulo", "disciple", "vod", "vow of the disciple"],
    "Raiz dos Pesadelos": ["raiz", "pesadelos", "raiz dos pesadelos", "ron", "root of nightmares"],
    "Limiar da Salvação": ["limiar", "salvação", "limiar da salvação", "edge", "salvation's edge", "salvations edge"],
    "Deserto Perpétuo": ["deserto", "perpetuo", "desert", "perpetual", "dp", "pd"]
}

MASMORRA_INFO_PT = {
    "Profecia": ["profecia", "prophecy"],
    "Trono Estilhaçado": ["trono", "trono estilhaçado", "estilhaçado", "shattered throne", "st"],
    "Poço da Heresia": ["poço", "heresia", "poco", "poço da heresia", "pit of heresy", "pit", "poh"],
    "Dualidade": ["dualidade", "duality"],
    "Pináculo da Sentinela": ["pinaculo", "pináculo", "sentinela", "pináculo da sentinela", "spire", "spire of the watcher", "sotw"],
    "Fantasmas das Profundezas": ["fantasmas", "profundezas", "fantasmas das profundezas", "ghosts", "ghosts of the deep", "gotd"],
    "Ruína da Senhora da Guerra": ["ruina", "ruína", "senhora da guerra", "ruína da senhora da guerra", "warlord's ruin", "warlords ruin", "wr"],
    "Domínio de Vesper": ["vesper", "domínio de vesper", "dominio de vesper"],
    "Doutrina Apartada": ["doutrina", "apartada", "doutrina apartada", "sundered", "doctrine"],
    "Equilíbrio": ["equilíbrio", "equilibrio", "equilibrium"]
}

PVP_ACTIVITY_INFO_PT = {
    "Desafios de Osíris": ["osiris", "desafios", "trials", "desafios de osíris", "trials of osiris"],
    "Bandeira de Ferro": ["bandeira", "iron banner", "ib"],
    "Crisol": ["crisol", "crucible", "pvp"]
}

ALL_ACTIVITIES_PT = {**RAID_INFO_PT, **MASMORRA_INFO_PT, **PVP_ACTIVITY_INFO_PT}
SIMILARITY_THRESHOLD = 0.75

RANK_THRESHOLDS = {
    'MESTRE': 16,
    'ADEPTO': 12,
    'VANGUARDA': 8,
    'ATIVO': 10,
    'TURISTA': 6,
}