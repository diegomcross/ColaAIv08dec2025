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
CHANNEL_NAME_MAPPINGS = {
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
    "Desafios de Osíris": "osiris",
    "Bandeira de Ferro": "bandeira",
    "Crisol": "crisol"
}

# --- LISTAS DE ATIVIDADES ---
RAID_INFO_PT = {
    "Queda do Rei": ["queda", "oryx", "king's fall", "kings fall", "kf"],
    "O Fim de Crota": ["crota", "fim de crota", "crota's end", "ce"],
    "Câmara de Cristal": ["camara", "câmara", "vog", "vault of glass"],
    "Último Desejo": ["riven", "ultimo desejo", "último desejo", "last wish", "lw"],
    "Jardim da Salvação": ["jardim", "garden", "gos"],
    "Cripta da Pedra Profunda": ["cripta", "dsc", "deep stone crypt"],
    "Voto do Discípulo": ["voto", "discípulo", "vod", "vow"],
    "Raiz dos Pesadelos": ["raiz", "ron", "root"],
    "Limiar da Salvação": ["limiar", "salvação", "edge", "salvation"],
    "Deserto Perpétuo": ["deserto", "perpetuo", "perpetual"]
}

MASMORRA_INFO_PT = {
    "Profecia": ["profecia", "prophecy"],
    "Trono Estilhaçado": ["trono", "shattered"],
    "Poço da Heresia": ["poço", "pit"],
    "Dualidade": ["dualidade", "duality"],
    "Pináculo da Sentinela": ["pinaculo", "spire"],
    "Fantasmas das Profundezas": ["fantasmas", "ghosts"],
    "Ruína da Senhora da Guerra": ["ruina", "warlord"],
    "Domínio de Vesper": ["vesper"],
    "Doutrina Apartada": ["doutrina", "sundered"],
    "Equilíbrio": ["equilíbrio", "equilibrium"]
}

PVP_ACTIVITY_INFO_PT = {
    "Desafios de Osíris": ["osiris", "trials"],
    "Bandeira de Ferro": ["bandeira", "ib"],
    "Crisol": ["crisol", "pvp"]
}

ALL_ACTIVITIES_PT = {**RAID_INFO_PT, **MASMORRA_INFO_PT, **PVP_ACTIVITY_INFO_PT}
SIMILARITY_THRESHOLD = 0.75

# --- SISTEMA DE RANKING ---
RANK_THRESHOLDS = {
    'MESTRE': 20,
    'LENDA': 10,
    'ADEPTO': 6,
    'ATIVO': 2,
    'TURISTA': 0,
}

# --- ESTILO DOS NICKNAMES (NOVOS TÍTULOS) ---
RANK_STYLE = {
    'MESTRE': "🏆 O Mestre",
    'LENDA': "⚡O Lendário",
    'ADEPTO': "✨ Adepto",
    'ATIVO': "👍",
    'TURISTA': "👎",
    'INATIVO': "💤",
    'DEFAULT': ""
}
