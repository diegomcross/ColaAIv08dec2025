import discord
import datetime
import dateparser
import pytz
import re
from typing import Tuple, Optional
from constants import (
    BR_TIMEZONE, RAID_INFO_PT, MASMORRA_INFO_PT, PVP_ACTIVITY_INFO_PT,
    DIAS_SEMANA_PT_SHORT, ACTIVITY_EMOJIS, ACTIVITY_MODES, CHANNEL_NAME_MAPPINGS,
    RANK_STYLE
)

# --- UTILITÁRIOS DE USUÁRIO ---

async def get_user_display_name_static(user_id: int, bot: discord.Client, guild: discord.Guild) -> str:
    if guild:
        member = guild.get_member(user_id)
        if member: return member.display_name
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        return user.display_name
    except: return f"User"

def clean_voter_name(display_name: str) -> str:
    """Limpa discriminadores (#1234) e espaços."""
    if not display_name: return "User"
    name_part = display_name.split('#')[0]
    return name_part.strip() or "User"

def strip_rank_prefix(display_name: str) -> str:
    """
    Remove agressivamente qualquer prefixo de rank (atual ou legado/bugado).
    """
    # Lista de 'Lixo' para remover do início do nome
    # Inclui versões quebradas, antigas e novas
    garbage_list = [
        "🎖️ MESTRE", "⚡ LENDA", "✨ ADEPTO", "🍌", "😵‍💫 TURISTA", "💤", 
        "😵💫 TURISTA", "⚠ TURISTA", "⚠️ TURISTA", "⚔️ ADEPTO", "⚡ VANGUARDA", "💠 LENDA",
        "🟢", "User", "Mestre", "Adepto", "Turista", "Lenda", "Vanguarda",
        "😵", "💫", "⚠", "⚠️", "⚔️", "✨", "⚡" # Emojis soltos
    ]
    
    clean = display_name.split('#')[0].strip()
    
    # Loop de Limpeza Recursiva
    # Continua limpando até que o nome não comece com nenhum lixo
    changed = True
    while changed:
        changed = False
        for trash in garbage_list:
            # Verifica se começa com o lixo (ignorando case para texto)
            if clean.lower().startswith(trash.lower()):
                # Remove o lixo (tamanho exato do que foi encontrado)
                # Mas precisamos remover da string original para manter o Case do nome do usuário
                if clean.startswith(trash):
                    clean = clean[len(trash):].strip()
                else:
                    # Fallback para caso de case insensitive (raro em emojis, mas bom pra texto)
                    clean = clean[len(trash):].strip()
                changed = True
        
        # Limpeza extra de símbolos soltos no início que podem ter sobrado
        if clean and not clean[0].isalnum():
            # Remove caracteres não alfanuméricos do início (ex: "- ", "| ")
            clean = re.sub(r'^[^a-zA-Z0-9]+', '', clean).strip()
            # Se removeu algo, marca changed para verificar garbage_list de novo
            # (ex: "- 🍌 Name" -> "🍌 Name" -> "Name")
            # Mas cuidado com loop infinito, então só faz regex simples
    
    return clean if clean else "User"

# --- UTILITÁRIOS DE DATA E EVENTO ---

def format_datetime_for_embed(dt: datetime.datetime) -> Tuple[str, str]:
    ts = int(dt.timestamp())
    return f"<t:{ts}:f>", f"<t:{ts}:R>"

async def build_event_embed(event_details: dict, rsvps_data: list, bot_instance: discord.Client) -> discord.Embed:
    event_id = event_details.get('event_id', 'N/A')
    guild_id = event_details.get('guild_id')
    guild = bot_instance.get_guild(guild_id)

    act_type_db = event_details.get('activity_type', 'OUTRO')
    color = discord.Color.blue()
    if act_type_db == 'RAID': color = discord.Color.purple()
    elif act_type_db == 'MASMORRA': color = discord.Color.orange()
    elif act_type_db == 'PVP': color = discord.Color.red()

    desc = f"**{event_details.get('description', '')}**"
    embed = discord.Embed(title=event_details.get('title', 'Evento'), description=desc, color=color)

    raw_date = event_details.get('date_time', event_details.get('date'))
    if isinstance(raw_date, str):
        try: dt_obj = datetime.datetime.fromisoformat(raw_date)
        except: dt_obj = datetime.datetime.now()
    else: dt_obj = raw_date
    if dt_obj and dt_obj.tzinfo is None: dt_obj = BR_TIMEZONE.localize(dt_obj)

    fmt_date, rel_time = format_datetime_for_embed(dt_obj)
    embed.add_field(name="🗓️ Data e Hora", value=f"{fmt_date} ({rel_time})", inline=False)
    
    display_type = act_type_db.capitalize() if act_type_db else "Outro"
    if act_type_db == 'RAID': display_type = "Incursão"
    embed.add_field(name="🎮 Tipo", value=display_type, inline=True)

    creator_id = event_details.get('creator_id')
    creator_mention = f"<@{creator_id}>" if creator_id else "Desconhecido"
    embed.add_field(name="👑 Organizador", value=creator_mention, inline=True)

    vou_user_ids = [r['user_id'] for r in rsvps_data if r['status'] == 'confirmed']
    le_ids = [r['user_id'] for r in rsvps_data if r['status'] == 'waitlist']
    nv_ids = [r['user_id'] for r in rsvps_data if r['status'] == 'absent']
    tv_ids = [r['user_id'] for r in rsvps_data if r['status'] == 'maybe']

    max_a = event_details.get('max_slots', 0)
    vou_names = []
    for uid in vou_user_ids:
        name = await get_user_display_name_static(uid, bot_instance, guild)
        vou_names.append(name)
    
    vou_lines = []
    if max_a > 0:
        for i in range(max_a):
            if i < len(vou_names): vou_lines.append(f"{i+1}. {vou_names[i]}")
            else: vou_lines.append(f"{i+1}. _________")
        vou_val = "\n".join(vou_lines)
    else:
        vou_val = "\n".join([f"{i+1}. {n}" for i, n in enumerate(vou_names)]) if vou_names else "Ninguém."

    embed.add_field(name=f"✅ Confirmados ({len(vou_names)}/{max_a})", value=vou_val, inline=False)

    if le_ids:
        le_lines = [f"{i+1}. {await get_user_display_name_static(uid, bot_instance, guild)}" for i, uid in enumerate(le_ids)]
        le_val = "\n".join(le_lines)
        embed.add_field(name=f"⏳ Lista de Espera ({len(le_ids)})", value=le_val, inline=False)

    if nv_ids:
        nv_names = [await get_user_display_name_static(uid, bot_instance, guild) for uid in nv_ids]
        embed.add_field(name=f"❌ Não vou ({len(nv_ids)})", value=", ".join(nv_names), inline=True)

    if tv_ids:
        tv_names = [await get_user_display_name_static(uid, bot_instance, guild) for uid in tv_ids]
        embed.add_field(name=f"🔷 Talvez ({len(tv_ids)})", value=", ".join(tv_names), inline=True)

    embed.add_field(name="ℹ️ Como Participar", value="Use os botões abaixo para confirmar presença. Se lotar, você vai para a fila de espera.", inline=False)
    embed.set_footer(text=f"ID do Evento: {event_id}")
    return embed

# --- PARSING E DETECÇÃO ---

def normalize_date_str(date_str: str) -> str:
    text = date_str.lower()
    replacements = {
        r'\bterca\b': 'terça', r'\bterça\b': 'terça-feira',
        r'\bsegunda\b': 'segunda-feira', r'\bquarta\b': 'quarta-feira',
        r'\bquinta\b': 'quinta-feira', r'\bsexta\b': 'sexta-feira',
        r'\bsabado\b': 'sábado', r'\bdomingo\b': 'domingo',
        r'\bamanha\b': 'amanhã', r'\bhoje\b': 'hoje',
    }
    for pattern, repl in replacements.items():
        text = re.sub(pattern, repl, text)
    text = re.sub(r'(\d{1,2})[hH](?!\w)', r'\1:00', text)
    text = re.sub(r'(\d{1,2})[hH](\d{2})', r'\1:\2', text)
    return text

def parse_human_date(date_str: str) -> Optional[datetime.datetime]:
    if not date_str: return None
    clean_date_str = normalize_date_str(date_str)
    now = datetime.datetime.now(BR_TIMEZONE)
    settings = {'PREFER_DATES_FROM': 'future', 'RELATIVE_BASE': now.replace(tzinfo=None), 'TIMEZONE': 'America/Sao_Paulo', 'RETURN_AS_TIMEZONE_AWARE': True, 'DATE_ORDER': 'DMY', 'PREFER_DAY_OF_MONTH': 'current'}
    dt = dateparser.parse(clean_date_str, settings=settings, languages=['pt'])
    if not dt: return None
    if dt.tzinfo is None: dt = BR_TIMEZONE.localize(dt)
    if (dt - now).days > 180:
        try_year_current = dt.replace(year=now.year)
        if try_year_current > now: dt = try_year_current
    return dt

def detect_activity_details(user_input: str) -> Tuple[str, str, int]:
    text_lower = user_input.lower()
    def check_match(catalog, type_name, default_slots):
        for official_name, aliases in catalog.items():
            if official_name.lower() in text_lower: 
                return official_name, type_name, default_slots
            for alias in aliases:
                if f" {alias} " in f" {text_lower} " or (len(alias) > 3 and alias in text_lower):
                    return official_name, type_name, default_slots
        return None

    match = check_match(RAID_INFO_PT, 'RAID', 6)
    if match: return match
    match = check_match(MASMORRA_INFO_PT, 'MASMORRA', 3)
    if match: return match
    match = check_match(PVP_ACTIVITY_INFO_PT, 'PVP', 3)
    if match: return match
    return user_input.strip().title(), 'OUTRO', None

def generate_channel_name(title: str, dt: datetime.datetime, type_key: str, free_slots: int, description: str = "") -> str:
    emoji1 = ACTIVITY_EMOJIS.get(type_key, ACTIVITY_EMOJIS['OUTRO'])
    emoji2 = ""
    search_text = (title + " " + description).lower()
    for keyword, icon in ACTIVITY_MODES.items():
        if keyword in search_text:
            emoji2 = icon
            break
            
    simple_name = title
    if title in CHANNEL_NAME_MAPPINGS: simple_name = CHANNEL_NAME_MAPPINGS[title]
    else:
        for official_key, simple_val in CHANNEL_NAME_MAPPINGS.items():
            if official_key.lower() in title.lower():
                simple_name = simple_val
                break
    
    clean_name = simple_name.lower().replace(' ', '-')
    clean_name = ''.join(e for e in clean_name if e.isalnum() or e == '-' or e in ['à', 'á', 'â', 'ã', 'é', 'ê', 'í', 'ó', 'ô', 'õ', 'ú', 'ç']) 
    
    now = datetime.datetime.now(BR_TIMEZONE)
    days_diff = (dt.date() - now.date()).days
    weekday = DIAS_SEMANA_PT_SHORT[dt.weekday()].lower()
    
    if days_diff < 7:
        time_str = dt.strftime('%Hh%M').replace('h00', 'h')
        slots_str = "lotado" if free_slots <= 0 else f"{free_slots}vagas"
        name = f"{emoji1}{emoji2}{clean_name}-{weekday}-{time_str}-{slots_str}"
    else:
        date_str = dt.strftime('%d-%m')
        name = f"{emoji1}{emoji2}{clean_name}-{weekday}-{date_str}"
        
    return name[:100]

def format_activity_name(raw_name: str) -> str:
    official_name, type_key, _ = detect_activity_details(raw_name)
    emoji1 = ACTIVITY_EMOJIS.get(type_key, "")
    emoji2 = ""
    mode_str = ""
    search_text = raw_name.lower()
    for keyword, icon in ACTIVITY_MODES.items():
        if keyword in search_text:
            emoji2 = icon
            mode_str = f" ({keyword.capitalize()})"
            break
    return f"{official_name}{mode_str} {emoji1}{emoji2}".strip()
