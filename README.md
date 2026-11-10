<p align="center">
  <img src="assets/capa.png" alt="Capa do DocFLow" width="100%">
</p>

# DocFLow

Sistema desktop local para controle de recebimento de documentos empresariais.

Versao atual: `2.0.10`

Este repositorio publico foi preparado para portfolio tecnico. O codigo-fonte, a interface e o fluxo principal estao aqui para estudo e demonstracao, mas materiais operacionais privados de licenciamento e distribuicao comercial nao acompanham esta edicao.

O projeto foi pensado para substituir planilhas e controles manuais por um fluxo local, auditavel e simples de operar. O foco e manter o uso direto no escritorio: cadastro de empresas, documentos por tipo, controle mensal de recebimento, dashboard executivo, relatorio de pendencias e backup do banco. Os dados ficam em um servidor PostgreSQL, que pode ser compartilhado entre as estacoes do escritorio.

## Visao geral

O DocFLow permite:

- cadastrar e manter empresas, com CNPJ para identificacao automatica
- cadastrar documentos por empresa e por tipo
- vincular meios de recebimento por documento
- controlar status por periodo em uma grade mensal, com selecao em lote
- acompanhar a conferencia mensal por empresa em uma visao panoramica
- visualizar um dashboard executivo com KPIs e graficos (distribuicao por situacao, tendencia de conclusao)
- aplicar regras de ocorrencia mensal, trimestral e anual em janeiro
- exportar pendencias em PDF e Excel
- manter logs administrativos
- gerar backup manual, configurar backup automatico e restaurar o banco pela interface
- alternar entre tema claro e escuro

## Principais recursos

- aplicacao desktop em Python, PySide6 (Qt) e PostgreSQL
- interface com navegacao lateral (sidebar), tema claro/escuro persistente e graficos nativos (QtCharts)
- banco PostgreSQL acessado por rede, configurado na primeira abertura
- autenticacao com perfis `admin` e `comum`
- login lembrado por perfil do computador, com expiracao de `60` dias e rotacao do token
- logs de alteracoes relevantes
- observacao por empresa com ate `255` caracteres
- status automatico `Nao cobrar` para meses fora da ocorrencia do tipo
- regra de encerramento que bloqueia meses posteriores
- dashboard com indicadores e graficos separados da grade operacional (Panorama)
- backup automatico configuravel em pasta fora da instalacao
- importacao e exportacao em Excel
- build com `PyInstaller`
- instalador Windows com `Inno Setup`

## Requisitos

### Desenvolvimento e execucao local

- Python `3.10+` (testado com `3.14`)
- dependencias do `requirements.txt` (inclui `PySide6`, o framework de interface)

### Dependencias Python

- `PySide6`
- `openpyxl`
- `Pillow`
- `cryptography`
- `psycopg` (driver do PostgreSQL, com a `libpq` embutida no pacote `psycopg[binary]`)
- `PyInstaller`

### Servidor de banco

- PostgreSQL `13+` com a extensao `citext` (pacote `contrib`, padrao nas instalacoes)
- um banco vazio criado previamente; as tabelas sao criadas na primeira conexao

```sql
CREATE ROLE docflow LOGIN PASSWORD 'troque-esta-senha';
CREATE DATABASE docflow OWNER docflow;
```

### Dependencias opcionais

- `Inno Setup` para gerar o instalador Windows

## Instalacao do ambiente

### Linux / macOS

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Execucao local

Na primeira abertura, o sistema pede os dados de conexao do PostgreSQL (servidor, porta, banco, usuario e senha). Tambem e possivel definir `DOCFLOW_DATABASE_URL` (por exemplo `postgresql://docflow:senha@localhost:5432/docflow`).

### Linux / macOS

```bash
.venv/bin/python main.py
```

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe main.py
```

## Servidor MCP

O pacote `docflow_mcp/` expoe o DocFlow como servidor [MCP](https://modelcontextprotocol.io), para ser usado a partir do Claude (Claude Code, Claude Desktop) ou de outro cliente MCP. Ele usa os mesmos services do app desktop, entao as validacoes, as permissoes de admin e o log de auditoria sao os mesmos.

Tools disponiveis (76):

- consulta: empresas, documentos, tipos, meios de recebimento, competencias, `panorama`, `controle_empresa`, relatorio de pendencias, fila e mensagem de cobranca, configuracao de cobranca, logs e usuarios
- cobranca: `o_que_fazer_agora`, `ficha_empresa`, `registro_documento`, `definir_recebimento_empresa` (canais, emails de origem e onde procurar), `registrar_verificacao`, `registrar_cobranca`, `registrar_promessa_envio`, `encaminhar_para_pessoa`, `historico_cobrancas`, `historico_verificacoes` e `definir_regras_acompanhamento`
- rodadas: `iniciar_rodada`, `registrar_ocorrencia`, `finalizar_rodada` e `historico_rodadas`
- cadastro e edicao: empresas (dados, ativa/inativa, pasta, mala direta, WhatsApp, regra de cobranca), documentos, `marcar_status` (um ou varios documentos numa competencia), tipos, meios de recebimento, periodos do ano, usuarios e regra global de cobranca
- arquivos: exportar relatorio de pendencias (xlsx/pdf), importar planilhas, criar e restaurar backup
- envios automaticos (cobranca e mala direta, email e WhatsApp): `listar_envios_programados`, `envios_a_fazer`, `conferir_envio`, `previa_envio`, `registrar_envio`, `enviar_whatsapp`, `historico_envios`, `cadastrar_envio_programado`, `atualizar_envio_programado`, `excluir_envio_programado`, `lista_mala_direta`, `incluir_na_mala_direta`, `remover_da_mala_direta`, `enviar_emails_pelo_docflow` (envia pelo email do escritorio cadastrado) e os modelos de texto (`listar_modelos_mensagem`, `salvar_modelo_mensagem`, `excluir_modelo_mensagem`)
- acesso livre ao banco (admin): `consultar_banco` roda qualquer SELECT numa transacao somente leitura; `executar_sql` roda qualquer comando de escrita/exclusao numa transacao (fica no Historico de acoes)
- exclusoes (empresa, documento, tipo, meio, ano, envio automatico, logs antigos, restauracao de backup) e `executar_sql` so executam com `confirmar=true`

Empresas sao identificadas pelo codigo e competencias pelo formato `MM/AAAA`.

O DocFlow e a memoria da cobranca. Rotina pensada para o Claude:

1. `iniciar_rodada` abre uma passada; tudo o que for registrado depois fica ligado a ela.
2. `o_que_fazer_agora` diz, por documento e competencia, a acao pelas regras do sistema (verificar, cobrar, recobrar, aguardar ou com uma pessoa) e o porque.
3. O Claude procura nos canais da empresa (email, Onvio) com as proprias ferramentas e registra com `registrar_verificacao` um resultado por documento: `recebido` (o sistema da baixa), `documento_com_problema` (com motivo), `nao_encontrado` ou `verificacao_falhou` (nao deu para olhar; nao gera cobranca). Na duvida, nunca `recebido`.
4. Para cobrar ou recobrar, envia a mensagem e registra com `registrar_cobranca`, que numera cobranca e recobranca. Promessas do cliente vao em `registrar_promessa_envio`; o que precisa de decisao humana vai em `encaminhar_para_pessoa`.
5. Falhas que nao sao de um documento (email fora do ar, sem acesso) vao em `registrar_ocorrencia`, e `finalizar_rodada` fecha a passada.

Os prazos e limites (dias de espera depois de cobrar, maximo de recobrancas, documento com problema vai para uma pessoa) ficam em Configuracoes > Depois de cobrar. As pessoas acompanham tudo em `Cobrancas` (proximas acoes, relatorios de verificacao, rodadas), `Precisa de atencao` e `Ficha da empresa`.

### Envios automaticos (email e WhatsApp)

Em `Administracao > Envios automaticos` ficam as cobrancas e malas diretas recorrentes. Tudo e por competencia: o envio diz quais competencias cobrar (ex: Informe de Rendimentos = 3, 6, 9, 12) e, por padrao, sai no mes seguinte a partir do dia escolhido (a competencia 12 e cobrada em janeiro), porque o documento so fica pronto no fim do mes. Publico: as empresas com um tipo de documento (opcionalmente so as que ainda nao entregaram), ou mala direta para todas as ativas ou para empresas escolhidas (respeitando quem pediu para nao receber). Qualquer envio aceita tirar empresas (num envio por tipo elas ficam como excecao, `empresa_ids_excluidas`) e incluir de volta. O texto aceita campos como `{empresa}`, `{competencia}` e `{documentos}`, com um texto proprio opcional para o WhatsApp (`corpo_whatsapp`); textos prontos ficam em `modelos_mensagem`.

A tela e mestre-detalhe: a esquerda todos os envios (com quantas empresas estao para enviar agora); a direita o envio escolhido em tres abas - Quem recebe (por competencia, dividido em Email, WhatsApp e Fica de fora, com a mensagem exata de cada empresa), Mensagem (textos, campos e modelos) e Historico. Ha ainda o Historico geral, com filtro por envio.

WhatsApp: so vai por WhatsApp para a empresa que liberou no cadastro (`Pode usar o WhatsApp nos envios`, coluna `whatsapp_envios`); empresas atendidas num grupo guardam o link de convite (`whatsapp_grupo`), que tem preferencia sobre o numero. No canal automatico quem liberou recebe por WhatsApp e os demais por email. O WhatsApp em sequencia abre uma conversa por vez com a mensagem pronta (wa.me); no grupo, que nao aceita texto no link, a mensagem vai para a area de transferencia.

Email: `email_sender_service.py` envia por SMTP com o login do escritorio, cadastrado na tela (`Email de envio...`, com envio de teste) e guardado no `config.json` (chave `email_envio`, senha protegida com DPAPI). O botao `Enviar emails agora` envia os emails pendentes e registra cada empresa; a copia oculta vai so no envelope (nunca no cabecalho) e listas grandes sao divididas em varios emails. Continua dando para abrir o rascunho no programa de email.

Mala direta em copia oculta: como o escritorio faz, um email so para o email do escritorio (`Para`) com os clientes em copia oculta, todo mes com a competencia anterior; quem liberou o WhatsApp sai da copia oculta e recebe a mensagem individual no WhatsApp. No MCP: modo `cco` em `cadastrar_envio_programado`, e `registrar_envio` sem `codigo_empresa` registra o email para todas as empresas da Cco.

O DocFlow e o centro de informacao. O Claude chama `envios_a_fazer`, envia cada email pela propria ferramenta de email (ou com `enviar_emails_pelo_docflow`) e, no WhatsApp, usa `enviar_whatsapp`; registra tudo com `registrar_envio`. A mesma mensagem nunca vai duas vezes para a mesma empresa na mesma competencia; quem perde o dia continua na lista ate o fim do mes.

Envio direto pelo WhatsApp: `whatsapp_service.py` ja traz o cliente da WhatsApp Cloud API (Meta). Para ligar, grave em `config.json` a chave `whatsapp` com `provedor: "cloud_api"`, `phone_number_id` e `token` (use `save_whatsapp_settings`, que protege o token com DPAPI). Fora da janela de 24h a Meta so aceita mensagens de modelo (template) aprovadas.

### Instalacao

```bash
.venv/bin/python -m pip install -r requirements-mcp.txt
```

O servidor age como o usuario `claude` do DocFlow (criado sozinho na primeira vez; as alteracoes aparecem nos logs com esse nome). Nao precisa de usuario nem senha na configuracao; `DOCFLOW_MCP_USUARIO`/`DOCFLOW_MCP_SENHA` sao opcionais, para agir como outro usuario.

### Configuracao no Claude Code

```bash
claude mcp add docflow \
  -e DOCFLOW_DATABASE_URL=postgresql://docflow:senha@localhost:5432/docflow \
  -- /caminho/do/projeto/.venv/bin/python /caminho/do/projeto/docflow_mcp
```

`DOCFLOW_DATABASE_URL` e opcional: sem ela, o servidor usa a conexao salva pelo app desktop no perfil do usuario do sistema.

### Configuracao pelo proprio DocFlow (recomendado)

Em `Configuracoes > Claude (MCP)`, clique em `Conectar ao Claude Desktop` (nao pede usuario
nem senha). A tela lista os `claude_desktop_config.json` do
computador - o Claude da Microsoft Store le
`%LOCALAPPDATA%\Packages\Claude_<id>\LocalCache\Roaming\Claude\`, o do site le
`%APPDATA%\Claude\` - mostra para onde cada um aponta (pasta antiga, outra instalacao) e
grava em todos, mantendo os outros servidores e uma copia do arquivo anterior. O arquivo do
Claude leva so o caminho do programa: o servidor age como o usuario `claude` do DocFlow,
criado sozinho na primeira vez (admin, senha aleatoria que ninguem precisa saber), e e com
esse nome que as acoes do Claude aparecem no Historico de acoes. Na versao instalada o programa e o
`DocFLow-MCP.exe`, ao lado do `DocFLow.exe`; pelo codigo-fonte, o Python do ambiente com
`docflow_mcp`.

### Configuracao em clientes com arquivo JSON (Claude Desktop e outros)

```json
{
  "mcpServers": {
    "docflow": {
      "command": "/caminho/do/projeto/.venv/bin/python",
      "args": ["/caminho/do/projeto/docflow_mcp"],
      "env": {
        "DOCFLOW_DATABASE_URL": "postgresql://docflow:senha@localhost:5432/docflow"
      }
    }
  }
}
```

## Licenciamento na edicao publica

O fluxo de licenciamento operacional nao faz parte desta publicacao no GitHub.

Na pratica, isso significa:

- a chave privada de licenciamento nao esta versionada aqui
- a geracao operacional de licencas depende de material privado fora deste repositorio
- esta edicao publica deve ser tratada como vitrine tecnica do projeto, nao como pacote pronto para uso em producao

## Primeiro acesso

Em um banco novo, o sistema cria automaticamente um usuario inicial:

- usuario: `admin`
- senha: `admin`

Recomendacao importante:

- altere essa senha imediatamente apos o primeiro login

## Testes

Os testes de banco rodam em um PostgreSQL real: cada teste cria um schema proprio e descartavel no banco apontado por `DOCFLOW_TEST_DATABASE_URL` (padrao: `dbname=docflow_test` no servidor local, com o usuario do sistema operacional; o banco e criado automaticamente se o usuario tiver permissao). Sem servidor acessivel, esses testes sao pulados.

### Suite completa

```bash
python -m unittest discover -s tests
```

### Apenas servicos

```bash
python -m unittest tests.test_services
```

## Empacotamento

Os builds devem ser gerados no proprio sistema operacional de destino.

### Linux

```bash
bash scripts/build_release.sh
```

Saidas esperadas:

- build PyInstaller: `dist/DocFLow/`
- pacote versionado: `dist_release/DocFLow-linux-<arquitetura>-v<versao>.tar.gz`

### macOS

```bash
bash scripts/build_release.sh
```

Saidas esperadas:

- build PyInstaller: `dist/DocFLow/`
- pacote versionado: `dist_release/DocFLow-macos-<arquitetura>-v<versao>.tar.gz`

### Windows

```powershell
scripts\build_release.bat
```

Saidas esperadas:

- build PyInstaller: `dist\DocFLow\`
- executavel principal: `dist\DocFLow\DocFLow.exe`
- pacote versionado: `dist_release\DocFLow-win64-v<versao>.zip`
- se o `Inno Setup` estiver no `PATH`, o script tambem tenta gerar o instalador
- o instalador nao pede administrador: instala por usuario em `%LOCALAPPDATA%\Programs\DocFLow` (a tela inicial ainda oferece instalar para todos, o que pede elevacao)

Se a pasta `dist\DocFLow\` for criada vazia ou sem `DocFLow.exe`, o build nao terminou corretamente. Nesse caso, rode manualmente:

```powershell
py -m PyInstaller --noconfirm --clean documentos_empresa_app.spec
```

e confira a ultima mensagem de erro do `PyInstaller`. Em Windows, as causas mais comuns sao antivirus/Defender removendo o executavel durante o build ou dependencias ausentes no ambiente Python usado pelo script.

### Nova versao (pipeline do GitHub)

O workflow `.github/workflows/release.yml` roda num Windows do GitHub: testes (com
PostgreSQL), PyInstaller, Inno Setup e publicacao da release com o instalador, o `.zip`
e o `.sha256` de cada um. Para lancar uma versao:

1. Suba a versao em `documentos_empresa_app/__init__.py`, `assets/installer/DocFLow.iss`
   (`AppVersion`) e na linha "Versao atual" deste README (o teste `test_release_files`
   confere que as tres batem).
2. Faca o commit na `main` e crie a tag: `git tag v2.1.0 && git push origin main v2.1.0`.
3. O pipeline publica a release `v2.1.0`. As notas (mostradas na tela de atualizacao) vem
   da mensagem da tag, se ela for anotada (`git tag -a v2.1.0 -m "## O que mudou ..."`);
   senao, da lista de commits desde a tag anterior.

O workflow tambem pode ser rodado na mao (aba Actions > Release Windows > Run workflow):
sem tag, ele so gera o instalador como artefato, sem publicar.

### Atualizacao automatica

O DocFlow instalado consulta a ultima release do GitHub alguns segundos depois de abrir.
Se houver versao nova, aparece o botao "Atualizar para X" na barra lateral (ou em
Ajuda > Verificar atualizacoes...). "Atualizar agora" baixa o instalador, confere o
SHA-256, fecha o sistema, instala por cima em modo silencioso e abre a versao nova. Os
dados (PostgreSQL e `%APPDATA%\DocFLow`) nao sao tocados. Rodando pelo codigo-fonte a
atualizacao automatica fica desligada.

### Pular testes no build

Por padrao, os scripts de release executam os testes antes do empacotamento.

#### Linux / macOS

```bash
RUN_TESTS=0 bash scripts/build_release.sh
```

#### Windows PowerShell

```powershell
$env:RUN_TESTS=0
scripts\build_release.bat
```

## Estrutura do projeto

```text
.
├── main.py
├── README.md
├── requirements.txt
├── documentos_empresa_app.spec
├── assets/
│   └── installer/
├── docs/
├── scripts/
├── tests/
└── documentos_empresa_app/
    ├── app_context.py
    ├── database/
    ├── models/
    ├── services/
    ├── qt_ui/
    └── utils/
```

## Pastas principais

- `documentos_empresa_app/`: codigo-fonte da aplicacao
- `docflow_mcp/`: servidor MCP do DocFlow
- `documentos_empresa_app/database/`: conexao, repositorios e schema PostgreSQL
- `documentos_empresa_app/services/`: regras de negocio
- `documentos_empresa_app/qt_ui/`: interface PySide6 (paginas, dialogos, widgets, tema e viewmodels)
- `documentos_empresa_app/utils/`: constantes, seguranca, recursos e helpers
- `assets/installer/`: script do Inno Setup para Windows
- `scripts/`: build e geracao de icones
- `tests/`: testes automatizados
- `docs/`: documentacao tecnica detalhada

## Arquivos de release importantes

- `documentos_empresa_app.spec`: receita do `PyInstaller`
- `scripts/build_release.sh`: build Linux/macOS com pacote `.tar.gz`
- `scripts/build_release.bat`: build Windows com `.zip` e tentativa opcional de instalador
- `assets/installer/DocFLow.iss`: instalador Windows
- `scripts/generate_icons.py`: gera `icon.png`, `icon.ico` e `icon.icns`

## Banco e seguranca

- o banco e PostgreSQL (detalhes, requisitos e migracao em [Banco de dados](docs/10-banco-de-dados.md))
- os dados de conexao sao salvos no perfil do usuario do computador (senha protegida com DPAPI no Windows); a variavel `DOCFLOW_DATABASE_URL` tem prioridade quando definida
- para trazer os dados de uma instalacao antiga (SQLite), use **Banco > Restaurar backup...** e selecione o arquivo `.db` antigo
- o login lembrado e local ao perfil do sistema operacional
- a credencial lembrada expira em `60` dias sem uso
- o token lembrado e renovado automaticamente a cada autenticacao bem-sucedida
- o backup automatico fica em pasta configuravel, com padrao em `Documents/DocFLow/backups` ou `Documentos/DocFLow/backups` quando disponivel
- backups restaurados precisam conter a estrutura esperada do sistema
- erros inesperados sao registrados em `error.log`, na mesma pasta de configuracao do usuario, em vez de fechar o programa silenciosamente

## Fluxo principal de uso

1. Fazer login.
2. Cadastrar empresas manualmente ou por importacao.
3. Cadastrar documentos por empresa.
4. Definir ou revisar tipos e meios de recebimento.
5. Gerar os periodos do ano.
6. Controlar os status na aba `Controle`.
7. Acompanhar o resumo executivo na aba `Dashboard` e a grade operacional em `Panorama`.
8. Exportar pendencias ou consultar logs quando necessario.
9. Configurar backup automatico ou gerar backup manual periodicamente.

## Regras de negocio principais

- empresa e unica por `codigo_empresa`
- documento e unico por `(empresa, tipo_documento, nome_documento)`
- consultas e relatorios aceitam no maximo `12` meses por vez
- tipos podem ser `Mensal`, `Trimestral` ou `Anual em janeiro`
- meses fora da ocorrencia aparecem como `Nao cobrar`
- `Encerrado` bloqueia meses posteriores do documento

## Documentacao tecnica

Os documentos detalhados continuam na pasta [`docs/`](docs). Alguns refletem ainda a versao anterior da interface (Tkinter) e estao sendo atualizados; os mais confiaveis para a estrutura atual sao:

- [Banco de dados](docs/10-banco-de-dados.md)
- [Dependencias e bibliotecas](docs/13-dependencias-e-bibliotecas-usadas.md)
- [Icones e empacotamento](docs/18-icones-e-empacotamento-por-sistema-operacional.md)
- [Git e empacotamento](docs/19-observacoes-importantes-para-git-e-empacotamento.md)
- [Configuracao de seguranca e backup](docs/21-configuracao-seguranca-e-backup.md)

## O que nao deve ir para o Git

- bancos locais
- artefatos de build (`build/`, `dist/`, `dist_release/`, `dist_installer/`)
- ambientes virtuais
- caches
- planilhas exportadas localmente

## Status desta revisao

- interface reconstruida em PySide6 (Qt), com tema claro/escuro, dashboard com graficos e todas as telas migradas do Tkinter
- `.gitignore` ampliado para artefatos de release e arquivos SQLite auxiliares
- README refeito para uso, manutencao e distribuicao
