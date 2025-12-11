==============================================================================
📘 DOCUMENTAÇÃO TÉCNICA - COLA.AI BOT (Versão Renegades v1.0)
==============================================================================

Este documento descreve todas as funcionalidades, lógica interna e arquitetura
do bot ColaAI. Use este guia para manutenção e futuras atualizações.

------------------------------------------------------------------------------
1. ESTRUTURA GERAL
------------------------------------------------------------------------------
O bot é construído em Python usando `discord.py` e `aiosqlite`.
- Arquitetura: Modular (Cogs).
- Banco de Dados: SQLite (`clan_bot.db`).
- Persistência: Arquivos JSON para estados simples (`lore_state.json`, `morning_state.json`).
- Conteúdo: Textos fixos em `quotes.py` (sem dependência de APIs externas).

------------------------------------------------------------------------------
2. SISTEMA DE EVENTOS (Agendamento)
------------------------------------------------------------------------------
Arquivo: `cogs/events.py`, `views.py`

A. CRIAÇÃO (/agendar)
   - O comando abre um Modal.
   - O bot tenta detectar automaticamente o tipo de atividade (Raid, Masmorra, PvP) pelo título.
   - Se o tipo for desconhecido, ele pergunta o número de vagas via botões.
   - Cria automaticamente:
     1. Um Cargo temporário (ex: "Câmara 12/12").
     2. Um Canal de Texto/Voz (nome formatado dinamicamente).
     3. Uma mensagem Embed com botões de RSVP.

B. RSVP (Presença)
   - Botões: [Vou], [Não Vou], [Talvez].
   - Lógica de Fila: Se as vagas (Slots) acabarem, quem clicar em "Vou" vai automaticamente para a "Lista de Espera".
   - Promoção Automática: Se um confirmado mudar para "Não Vou", o primeiro da Lista de Espera é promovido automaticamente e notificado.

C. GERENCIAMENTO
   - Edição: Apenas Criador ou Gerentes podem editar data/descrição.
   - Notificação: Se a data mudar, todos os confirmados recebem DM.
   - Permissões: Comando `/definir_cargo_gerente` permite que mods editem eventos de outros.

------------------------------------------------------------------------------
3. SISTEMA DE ENQUETES (Votação Inteligente)
------------------------------------------------------------------------------
Arquivo: `cogs/polls.py`, `cogs/views_polls.py`

A. COMANDOS
   - `/enquete_atividade`: Votação para decidir O QUE jogar (até 6 opções).
   - `/enquete_quando`: Votação para decidir O HORÁRIO (baseado em dia pré-selecionado).

B. MECÂNICA DE VOTO
   - Voto Múltiplo (Toggle): O usuário pode selecionar várias opções. Clicar novamente remove o voto.
   - Visual Limpo: O bot remove números do nome do usuário no display (ex: "Joao#1234" vira "Joao").

C. AUTOMAÇÃO DE SUCESSO
   - Meta: Se uma opção atingir 4 votos (atividade) ou 3 votos (horário), a enquete encerra.
   - Criação Automática: O bot cria o evento automaticamente com os dados vencedores.
   - RSVP Automático: Quem votou na opção vencedora já entra no evento como "Confirmado".

------------------------------------------------------------------------------
4. SISTEMA DE RANKING DE VOZ (Anti-Farm)
------------------------------------------------------------------------------
Arquivo: `cogs/ranking.py`

A. RASTREAMENTO
   - Monitora o evento `on_voice_state_update`.
   - Regra de Ouro: Só conta tempo se o usuário estiver (1) Em canal, (2) Desmutado/Ouvindo e (3) Com companhia humana (>1 pessoa).

B. LÓGICA DE SESSÃO DINÂMICA
   - Entrada: Se entrar e tiver gente, o relógio inicia (`PLAY`). Se entrar sozinho, fica em espera.
   - Validação Cruzada: Se alguém entra num canal onde tinha uma pessoa esperando, AMBOS começam a contar tempo imediatamente.
   - Saída: Ao sair, o tempo é calculado e salvo no DB.
   - Pausa: Se sobrar apenas 1 pessoa no canal, o relógio dela PAUSA (`PAUSE`) para evitar farm AFK.

C. EXIBIÇÃO
   - Loop (30 min): Atualiza o canal de Ranking com o Top 20 (baseado nos últimos 7 dias).
   - Comando `/ver_tempo`: Mostra relatório privado detalhado de um usuário.

------------------------------------------------------------------------------
5. MONITOR DE PRESENÇA (Attendance & Penalidade)
------------------------------------------------------------------------------
Arquivo: `cogs/tasks.py` (Loop: `attendance_monitor_loop`)

O bot fiscaliza os eventos a cada 5 minutos.

A. PRÉ-EVENTO (15 min antes)
   - Se o evento não estiver lotado, o bot manda DM para quem marcou "Talvez": "Vaga disponível, pode cobrir?".

B. INÍCIO (0 a 10 min)
   - Verifica quem confirmou ("Vou") vs. Quem está no canal de voz.
   - Ação: Manda DM para os atrasados ("O evento começou!") e notifica no chat principal.

C. DURANTE O EVENTO
   - Se um confirmado aparecer no canal de voz em qualquer momento, ele é marcado como `present` no banco de dados (salvo de penalidade).

D. PÓS-INÍCIO (30 min)
   - Gera um "Relatório de Ausência" no chat principal expondo quem confirmou e não apareceu.

------------------------------------------------------------------------------
6. AUTOMAÇÃO E TAREFAS DE FUNDO
------------------------------------------------------------------------------
Arquivo: `cogs/tasks.py`

A. MENSAGENS DIÁRIAS
   - Manhã (08h-10h): Envia frase de humor/gameplay. (Ciclo infinito sem repetição imediata).
   - Tarde (15h-17h): Envia fato de Lore (Renegades). (Para quando a lista acaba).
   - Estado: Salva o índice em `.json` para não perder a conta se reiniciar.

B. QUADRO DE HORÁRIOS (Info Board)
   - Canal `#agende-uma-grade`.
   - O bot edita a mensagem existente a cada 5 min (evita spam de notificação).
   - Mostra: Lista limpa de próximos eventos, vagas restantes e link para o canal.

C. LIMPEZA E MANUTENÇÃO
   - Cleanup Loop: Apaga canais e cargos de eventos que terminaram há 1 hora.
   - Channel Rename: Atualiza o nome dos canais (ex: "raid-2vagas") a cada 15 min (para respeitar o rate limit do Discord).
   - Reminders: Manda aviso no canal do evento 1 hora antes do início.

------------------------------------------------------------------------------
7. BANCO DE DADOS (Estrutura)
------------------------------------------------------------------------------
Arquivo: `database.py`

- `events`: Dados core do evento.
- `rsvps`: Quem vai (user_id, status).
- `voice_sessions`: Logs de tempo de voz bruto.
- `event_attendance`: Log de quem realmente apareceu no evento (para histórico de faltas).
- `event_lifecycle`: Controle de quais avisos (DM, atraso) já foram enviados para não repetir.
- `polls` / `poll_votes_v2`: Dados das enquetes.

==============================================================================
FIM DA DOCUMENTAÇÃO
==============================================================================
