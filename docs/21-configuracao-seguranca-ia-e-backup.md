[Voltar ao README](../README.md)

# 21. Configuracao de seguranca, IA e backup

Este documento explica como configurar a chave de API do agente de IA, a senha de criptografia de backup e a troca de senha obrigatoria do usuario `admin`. Esses recursos foram adicionados/alterados numa rodada de ajustes de conformidade com a LGPD, e o comportamento de armazenamento de segredos mudou (ver secao 4).

Tudo aqui e configurado pela propria interface, como usuario `admin` — nao e necessario editar arquivos manualmente.

## 1. Chave de API do agente de IA (Anthropic / OpenAI)

Caminho: **Configuracoes > aba "Agente de IA"** (so aparece pra usuarios `admin`).

Campos:

- **Provedor de IA**: `Anthropic (Claude)` ou `OpenAI (ChatGPT)`. Cada provedor guarda sua propria chave e modelo — trocar de provedor no combo nao apaga a chave do outro.
- **API key**: cole a chave gerada no painel do provedor (`console.anthropic.com` ou `platform.openai.com`). Use o botao **Testar conexao** antes de salvar pra confirmar que a chave e o modelo escolhido funcionam.
- **Modelo usado**: pre-preenchido com um modelo padrao por provedor; pode ser editado se o escritorio tiver acesso a outro modelo.
- **Limiar de confianca (0 a 1)**: abaixo desse valor, a sugestao da IA vai pra fila de revisao manual em vez de aplicar automaticamente.
- **System prompt customizado**: texto opcional que complementa (com prioridade) o prompt padrao de classificacao/chat — util pra regras especificas do escritorio.

Sem chave configurada, o agente organizador de documentos continua funcionando apenas com o casamento local por CNPJ; documentos sem CNPJ reconhecido vao direto pra revisao manual.

### Alternativa via variavel de ambiente

Em vez de salvar pela interface, e possivel definir `ANTHROPIC_API_KEY` ou `OPENAI_API_KEY` no ambiente antes de abrir o programa. A variavel de ambiente tem prioridade sobre o valor salvo na interface e nunca e escrita em disco pelo DocFLow.

### Aviso de transferencia de dados

Ao ativar o agente de IA, o texto extraido dos documentos (e as perguntas do chat) e enviado para os servidores do provedor escolhido, que podem processar os dados fora do Brasil. Numeros de CPF encontrados no texto sao removidos automaticamente antes do envio; outros dados do documento (nome da empresa, valores, datas) sao transmitidos normalmente. Esse aviso tambem aparece direto na tela de Configuracoes.

## 2. Senha de criptografia de backup (opcional)

Caminho: menu **Banco de dados > Configurar backup automatico...** (mesma tela onde se define pasta, intervalo e quantidade de backups mantidos).

Campo **Senha de criptografia do backup (opcional)**:

- Se **preenchida**, todo backup gerado a partir dali (manual ou automatico) e criptografado com essa senha (AES via `Fernet`, chave derivada por PBKDF2). O arquivo `.db` deixa de ser um SQLite legivel diretamente — passa a comecar com um cabecalho `DOCFLOWBK1`.
- Se **vazia** (padrao), os backups continuam sendo gerados como arquivo SQLite comum, igual a antes.
- Pra **restaurar** um backup criptografado, a senha e necessaria. Se o computador que esta restaurando ja tem a mesma senha salva em Configuracoes, a restauracao usa ela automaticamente; caso contrario, o sistema pede a senha na hora de escolher o arquivo de restauracao.

**Risco explicito**: se a senha for perdida, os backups criptografados ficam irrecuperaveis — nao ha recuperacao alternativa. Guarde a senha em lugar seguro (gerenciador de senhas do escritorio, por exemplo), separado do computador onde o DocFLow roda.

Backups antigos (gerados antes dessa funcionalidade) continuam sendo restaurados normalmente, sem senha.

## 3. Troca de senha obrigatoria do `admin`

O usuario inicial (`admin` / senha `admin`, ver README) agora e criado com a flag "deve trocar senha" ativada. No primeiro login com esse usuario, uma tela de troca de senha aparece automaticamente, antes de abrir o sistema, e nao pode ser pulada — só "Sair" (fecha o programa) ou trocar a senha efetivamente.

Depois de qualquer troca de senha (nao so a inicial), o usuario e desconectado das sessoes de login lembrado ativas naquele momento; nas outras estacoes, sera preciso logar de novo com a senha nova.

## 4. Como os segredos ficam guardados (DPAPI no Windows)

Antes: chave de API e token de login lembrado ficavam gravados **em texto plano** dentro do `config.json` do usuario (pasta de configuracao do DocFLow no perfil do Windows).

Agora: esses dois valores sao criptografados com o **DPAPI do Windows** (`CryptProtectData`/`CryptUnprotectData`, via `ctypes`, sem dependencia extra) antes de ir pro `config.json`. Pontos importantes:

- A criptografia esta amarrada ao **usuario do Windows** que configurou a chave (nao ao usuario do DocFLow). Copiar o `config.json` pra outro computador, ou abrir com outro usuario do Windows no mesmo computador, torna o valor ilegivel — nesse caso, e so reconfigurar a chave de novo na tela de Configuracoes.
- E transparente pro dia a dia: nada muda na forma de configurar a chave pela interface, o valor so passa a ser salvo protegido.
- Valores antigos, gravados em texto plano por uma instalacao anterior, continuam sendo lidos normalmente (compatibilidade) e sao automaticamente re-salvos de forma criptografada na proxima vez que forem alterados.
- Fora do Windows (nao e o caso de producao deste sistema), o valor e salvo em texto plano como antes, sem quebrar a aplicacao.

Essa criptografia e local ao computador/usuario do Windows — nao substitui a senha de criptografia de backup (secao 2), que precisa ser portavel entre maquinas.

## 5. Nova dependencia de build: `cryptography`

A criptografia de backup (secao 2) usa a biblioteca `cryptography` (Fernet + PBKDF2), que **nao existia** nas dependencias do projeto antes desta mudanca. Ja foi adicionada em `requirements.txt`.

Antes de gerar um novo instalador/executavel:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O `PyInstaller` detecta a biblioteca automaticamente (ela tem hooks proprios, nao foi necessario mexer em `documentos_empresa_app.spec`), mas confirme apos o build que a criptografia de backup funciona no executavel empacotado (gerar um backup com senha e restaurar), ja que dependencias novas por vezes exigem ajuste de `hiddenimports` em ambientes diferentes.
