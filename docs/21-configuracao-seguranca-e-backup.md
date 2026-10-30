[Voltar ao README](../README.md)

# 21. Configuracao de seguranca e backup

Este documento explica como configurar a senha de criptografia de backup e a troca de senha obrigatoria do usuario `admin`. Esses recursos foram adicionados/alterados numa rodada de ajustes de conformidade com a LGPD, e o comportamento de armazenamento de segredos mudou (ver secao 3).

Tudo aqui e configurado pela propria interface, como usuario `admin` — nao e necessario editar arquivos manualmente.

## 1. Senha de criptografia de backup (opcional)

Caminho: menu **Banco de dados > Configurar backup automatico...** (mesma tela onde se define pasta, intervalo e quantidade de backups mantidos).

Campo **Senha de criptografia do backup (opcional)**:

- Se **preenchida**, todo backup gerado a partir dali (manual ou automatico) e criptografado com essa senha (AES via `Fernet`, chave derivada por PBKDF2). O arquivo `.dfbak` deixa de ser legivel diretamente — passa a comecar com um cabecalho `DOCFLOWBK1`.
- Se **vazia** (padrao), os backups sao gerados sem criptografia (JSON compactado, extensao `.dfbak`).
- Pra **restaurar** um backup criptografado, a senha e necessaria. Se o computador que esta restaurando ja tem a mesma senha salva em Configuracoes, a restauracao usa ela automaticamente; caso contrario, o sistema pede a senha na hora de escolher o arquivo de restauracao.

**Risco explicito**: se a senha for perdida, os backups criptografados ficam irrecuperaveis — nao ha recuperacao alternativa. Guarde a senha em lugar seguro (gerenciador de senhas do escritorio, por exemplo), separado do computador onde o DocFLow roda.

Backups antigos (gerados antes dessa funcionalidade) continuam sendo restaurados normalmente, sem senha.

## 2. Troca de senha obrigatoria do `admin`

O usuario inicial (`admin` / senha `admin`, ver README) agora e criado com a flag "deve trocar senha" ativada. No primeiro login com esse usuario, uma tela de troca de senha aparece automaticamente, antes de abrir o sistema, e nao pode ser pulada — só "Sair" (fecha o programa) ou trocar a senha efetivamente.

Depois de qualquer troca de senha (nao so a inicial), o usuario e desconectado das sessoes de login lembrado ativas naquele momento; nas outras estacoes, sera preciso logar de novo com a senha nova.

## 3. Como os segredos ficam guardados (DPAPI no Windows)

Antes: segredos como o token de login lembrado ficavam gravados **em texto plano** dentro do `config.json` do usuario (pasta de configuracao do DocFLow no perfil do Windows).

Agora: esses valores (token de login lembrado e senha do banco PostgreSQL) sao criptografados com o **DPAPI do Windows** (`CryptProtectData`/`CryptUnprotectData`, via `ctypes`, sem dependencia extra) antes de ir pro `config.json`. Pontos importantes:

- A criptografia esta amarrada ao **usuario do Windows** que configurou o valor (nao ao usuario do DocFLow). Copiar o `config.json` pra outro computador, ou abrir com outro usuario do Windows no mesmo computador, torna o valor ilegivel — nesse caso, e so configurar de novo pela interface.
- E transparente pro dia a dia: nada muda na forma de configurar pela interface, o valor so passa a ser salvo protegido.
- Valores antigos, gravados em texto plano por uma instalacao anterior, continuam sendo lidos normalmente (compatibilidade) e sao automaticamente re-salvos de forma criptografada na proxima vez que forem alterados.
- Fora do Windows (nao e o caso de producao deste sistema), o valor e salvo em texto plano como antes, sem quebrar a aplicacao.

Essa criptografia e local ao computador/usuario do Windows — nao substitui a senha de criptografia de backup (secao 1), que precisa ser portavel entre maquinas.

## 4. Nova dependencia de build: `cryptography`

A criptografia de backup (secao 1) usa a biblioteca `cryptography` (Fernet + PBKDF2), que **nao existia** nas dependencias do projeto antes desta mudanca. Ja foi adicionada em `requirements.txt`.

Antes de gerar um novo instalador/executavel:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

O `PyInstaller` detecta a biblioteca automaticamente (ela tem hooks proprios, nao foi necessario mexer em `documentos_empresa_app.spec`), mas confirme apos o build que a criptografia de backup funciona no executavel empacotado (gerar um backup com senha e restaurar), ja que dependencias novas por vezes exigem ajuste de `hiddenimports` em ambientes diferentes.

## 5. Recursos removidos

O agente de IA (classificacao por IA, chat e organizacao em lote) e o agente organizador de documentos (pasta de entrada, fila de Revisao de Documentos e ingestao de anexos por email) foram removidos do sistema. Na abertura do programa, as configuracoes que esses recursos gravavam no `config.json` (API keys, caixa de email IMAP com a senha, pasta de entrada) sao apagadas automaticamente; no banco, a tabela da fila de revisao e a de pastas por usuario sao removidas. Os emails de origem das empresas voltaram a existir como parte da forma de envio (Ficha da empresa > Como receber).
