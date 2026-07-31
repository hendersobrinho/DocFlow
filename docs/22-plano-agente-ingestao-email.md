# Plano: Ingestão de Documentos por Email

> Documento de planejamento (não é documentação do sistema atual). Guarda o desenho
> refinado da ideia original (ver `Untitled-2026-07-30-2208.svg` enviado na conversa)
> e os prompts prontos pra retomar a implementação fase por fase, numa sessão futura,
> sem precisar reconstruir o raciocínio do zero.

## Ideia original

O escritório de contabilidade recebe boletos/notas/extratos das empresas-cliente por
email. Hoje isso exige alguém baixar manualmente e jogar na "Pasta de entrada" pra cair
na fila de Revisão. A ideia é o próprio sistema ler essa caixa de email e alimentar a
pasta de entrada sozinho.

## Decisões já tomadas (não reabrir sem motivo forte)

1. **Sempre passa por revisão humana.** Mesmo quando o agente tem certeza de qual
   empresa/documento é, ele NUNCA salva nem dá baixa sozinho — só deixa a sugestão
   pronta na fila de Revisão pra um clique de confirmação. Motivo: documento financeiro
   de cliente, o custo de checar é baixo perto do risco de errar sozinho.
2. **Email de origem é um campo novo, separado do `email_contato` que já existe.**
   `email_contato` já é usado pra cobrança (mala direta) e pode ser uma pessoa
   diferente de quem efetivamente envia os documentos.

## O que já existe no DocFlow e será reaproveitado (não reinventar)

- Fila de revisão manual = tela **Revisão de Documentos** (`RevisaoPage`) já existente.
- Identificação de empresa/tipo por CNPJ + IA = `DocumentAgentService.classify_file`.
- Salvar na pasta certa da empresa = `DocumentOrganizerService`.
- Dar baixa no status = `StatusService.update_status` (o chat do Buba já sabe fazer isso
  via `_confirm_and_execute_dar_baixa`).
- Log de erros pra depurar = `document_agent_diagnostics.py`.
- Guardar segredo sensível com criptografia = mesmo mecanismo já usado pra API key da
  IA (`resolve_agent_api_key`) e senha de backup (`backup_encryption.py`).
- Padrão de "tarefa automática configurável + botão manual" = **já existe pronto** pro
  backup automático (`utils/auto_backup.py` + `qt_ui/dialogs/backup_settings_dialog.py`
  + `MainWindow.configure_auto_backup` / `run_auto_backup_if_due`). A Fase 4 é
  basicamente clonar esse padrão trocando "backup" por "verificação de email".

## Insight principal do refino

Como tudo sempre passa por humano (decisão 1), o "agente de email" não precisa
classificar nem decidir nada — ele só precisa **entregar o arquivo na mesma pasta de
entrada que já existe**. O pipeline atual (`scan_folder` → `classify_file` → fila de
Revisão) continua cuidando do resto sem mudar uma linha na Fase 1. É uma torneira nova
alimentando um cano que já existe, não um agente novo do zero.

---

## Fase 1 — MVP: buscar o email e derramar na pasta de entrada

Baixa os anexos de remetentes conhecidos pra pasta de entrada. Não classifica nada -
o pipeline existente cuida do resto. Sem UI nova de resultado (só a fila de Revisão
de sempre, que já existe).

```
Quero implementar a Fase 1 da ingestão de documentos por email no DocFlow.

Contexto: hoje o usuário processa documentos manualmente (RevisaoPage.process_new_documents
escaneia uma pasta local via document_agent_service.scan_folder). Quero adicionar uma segunda
fonte de entrada: uma caixa de email (IMAP) que o próprio escritório de contabilidade usa,
de onde as empresas-cliente mandam boletos/notas/extratos por anexo.

Regra de negócio: cada empresa (tabela empresas) pode ter um ou mais emails de origem
cadastrados (campo novo, separado do email_contato que já existe e é usado só pra cobrança
via mala direta). O novo serviço deve: conectar via IMAP com credenciais do escritório
(guardadas com a mesma criptografia usada pra API key da IA), procurar emails não lidos de
remetentes que batam com algum email de origem cadastrado numa empresa ativa, baixar os
anexos em formato suportado (pdf/xlsx, ver DocumentExtractionService.SUPPORTED_EXTENSIONS)
pra pasta de entrada já configurada pelo usuário (UserService.get_own_inbox_folder), e marcar
o email como processado pra não baixar de novo.

Importante: esse serviço NÃO deve classificar nem decidir nada sozinho - só entrega o arquivo
na pasta de entrada. O pipeline existente (scan_folder -> classify_file -> fila de Revisão)
continua cuidando do resto sem mudanças nessa fase.

Peço que primeiro me proponha o desenho técnico (novo repository/service, onde fica a config
de IMAP na tela de Configurações, como testar sem uma caixa de email real) antes de escrever
código, porque isso mexe com credenciais e é a parte mais sensível do app em termos de LGPD.
```

## Fase 2 — usar o remetente como sinal extra de confiança

Depende da Fase 1 já estar rodando de verdade (precisa ter remetente real salvo pra usar
como sinal).

```
Quero implementar a Fase 2 da ingestão de documentos por email no DocFlow (depende da Fase 1
já estar funcionando - ver docs/22-plano-agente-ingestao-email.md).

Hoje DocumentAgentService.classify_file identifica a empresa de um documento pendente
principalmente pelo CNPJ extraído do texto (ou por IA quando o CNPJ não é encontrado). Quero
que, quando o arquivo veio da ingestão por email (Fase 1), o email do remetente entre como um
sinal extra de confiança: se o remetente bate com um email de origem cadastrado numa empresa,
e o CNPJ não foi encontrado no texto (ou não bateu com nenhuma empresa), sugerir essa empresa
mesmo assim - mas com uma origem/motivo diferenciado (ex: origem "email_remetente" em vez de
"regex_cnpj"/"llm"), pra quem revisa entender que a sugestão veio do remetente e não do
conteúdo do documento.

A tela de Revisão de Documentos (RevisaoPage) já mostra colunas "Origem" e "Motivo" - preciso
que esse novo sinal apareça lá com um texto claro tipo "Email de {empresa}" pra dar contexto
pra quem revisa.

Não mude o comportamento de nenhum documento que já é identificado por CNPJ/IA - o remetente é
só mais um sinal quando os outros dois não bateram.
```

## Fase 3 — regra do extrato bancário "não clicável"

Independente das outras fases (pode ser feita a qualquer momento, inclusive antes).

```
Quero implementar a Fase 3 da ingestão de documentos por email no DocFlow (ver
docs/22-plano-agente-ingestao-email.md) - na verdade essa regra vale pra qualquer documento
pendente, não só os que vieram por email.

Contexto: DocumentExtractionService.extract_text usa pypdf pra extrair texto de PDFs. Um PDF
escaneado (imagem, sem camada de texto - "não clicável") retorna texto vazio ou quase vazio,
porque não tem OCR nenhum no projeto hoje.

Regra: quando o tipo de documento sugerido/identificado for extrato bancário e o texto extraído
vier vazio ou abaixo de um limite mínimo de caracteres, a confiança da classificação deve ser
forçada pra baixa (nunca deixar a sugestão parecer "certeza"), garantindo que esse documento
sempre passe pela fila de revisão humana em vez de qualquer atalho automático futuro.

Me proponha onde encaixar essa checagem no pipeline atual (classify_file? build_row do
BatchOrganizeService? os dois?) antes de mexer no código, e como cobrir isso com teste
(tests/test_document_agent.py ou tests/test_services.py, seguindo o padrão dos testes que já
existem pra classify_file).
```

## Fase 4 — verificação automática configurável + botão manual

Reaproveita o mesmo padrão de UX/código já usado pelo backup automático - **não inventar um
padrão novo aqui**, só clonar o existente:

- `utils/auto_backup.py` (`load_auto_backup_settings`, `should_run_auto_backup`,
  `mark_auto_backup_created`, `save_auto_backup_settings`) → equivalente pra email.
- `qt_ui/dialogs/backup_settings_dialog.py` (`BackupSettingsDialog`, com checkbox
  "ativado" + intervalo) → um `EmailCheckSettingsDialog` equivalente.
- `main_window.py`: `configure_auto_backup()` (abre o dialog) e
  `run_auto_backup_if_due()` (chamado via `QTimer.singleShot(800, ...)` no `__init__`,
  roda em thread de fundo via `CallableWorker`) → os mesmos dois métodos pra email.
- O botão manual "Fazer backup..." já existe dentro do menu **Banco** no topo da janela
  → o botão pedido ("Verificar email agora") deve ficar no mesmo estilo/lugar, ou dentro
  do menu **Banco** como mais uma ação, ou como botão próprio perto de "Pasta de
  entrada" na tela de Revisão (a decidir na hora, com base em qual fica mais natural
  visualmente).

```
Quero implementar a Fase 4 da ingestão de documentos por email no DocFlow (depende da Fase 1
já estar funcionando - ver docs/22-plano-agente-ingestao-email.md).

Quero dois jeitos de disparar a verificação de email, do jeito mais simples possível: rodar
automaticamente numa cadência configurável, e também poder rodar na hora via um botão manual.

Quero que isso siga EXATAMENTE o mesmo padrão já usado pelo backup automático nesse projeto,
só trocando "backup" por "verificação de email" - não quero um mecanismo novo:

- utils/auto_backup.py tem load_auto_backup_settings/should_run_auto_backup/
  save_auto_backup_settings guardando um dict de config (enabled, interval_days, etc) via
  load_config/save_config. Quero o equivalente pra email (enabled, interval_minutes ou
  interval_hours - a cadência de checar email costuma ser mais curta que a de backup, pensar
  no intervalo padrão certo).
- qt_ui/dialogs/backup_settings_dialog.py é o dialog de configuração (checkbox "ativado" +
  campo de intervalo + confirmar). Quero um dialog espelhado pra configurar a verificação de
  email.
- main_window.py tem configure_auto_backup() (abre o dialog e salva) e
  run_auto_backup_if_due() (roda em background thread via CallableWorker, chamado 800ms
  depois do app abrir via QTimer.singleShot, silencioso a menos que falhe). Quero os dois
  métodos equivalentes pra email, plus um jeito do timer se repetir sozinho enquanto o app
  estiver aberto (o backup só roda uma vez ao abrir o app - pra email eu quero que continue
  checando periodicamente enquanto o programa estiver rodando, não só uma vez no início).
- Quero um botão "Verificar email agora" que dispara a mesma verificação na hora, sem esperar
  o intervalo - igual ao botão "Fazer backup..." que já existe dentro do menu "Banco" no topo
  da janela (main_window.py, _build_main_area). Pode ficar nesse mesmo menu como mais uma
  opção, ou perto do campo "Pasta de entrada" na tela de Revisão de Documentos - me proponha
  qual faz mais sentido antes de implementar.

Me proponha o desenho (nomes de arquivo, onde fica cada pedaço) antes de escrever código.
```

---

## Ordem recomendada

Fase 1 é obrigatória primeiro (é a base). Fase 3 pode ser feita a qualquer momento, até antes
da Fase 1, porque não depende de email nenhum. Fase 2 depende da Fase 1 já estar em uso real
(precisa ter remetente de verdade salvo). Fase 4 pode vir logo depois da Fase 1 (só precisa
que a verificação manual já funcione pra automatizar em cima dela).
