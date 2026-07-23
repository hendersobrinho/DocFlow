[Voltar ao README](../README.md)

# 1. Visao Geral Do Sistema

## 1.1 Objetivo do sistema

O DocFLow e uma aplicacao desktop local, escrita em Python com Tkinter e SQLite, voltada ao controle operacional de documentos recebidos de diferentes empresas. O projeto prioriza simplicidade de uso, persistencia local, rastreabilidade e manutencao direta.

## 1.2 Problema que o sistema resolve

O sistema organiza uma rotina que costuma ficar espalhada entre planilhas, mensagens e memoria operacional:

- quais documentos devem ser cobrados
- de qual empresa cada documento faz parte
- por qual meio aquele documento costuma chegar
- em quais meses ele precisa mesmo ser cobrado
- quais periodos estao pendentes, recebidos, encerrados ou automaticamente marcados como `Nao cobrar`

## 1.3 Proposta do projeto

O projeto permanece propositalmente enxuto:

- aplicacao desktop local
- sem servidor
- com persistencia em SQLite
- com autenticacao simples
- com auditoria das alteracoes principais
- com interface em abas focada em operacao

## 1.4 Funcionamento geral

1. O sistema sobe a aplicacao por `main.py`.
2. Resolve o caminho do banco SQLite e monta os servicos.
3. `initialize_schema()` cria tabelas, aplica ajustes de compatibilidade e semeia dados basicos.
4. O usuario faz login.
5. A janela principal abre as abas conforme permissao.
6. A UI conversa com servicos.
7. Os servicos validam regra de negocio, acionam repositÃ³rios e gravam logs quando aplicavel.

## 1.5 Modulos principais

- bootstrap e configuracao inicial
- persistencia SQLite e migracoes leves
- repositÃ³rios SQL
- servicos de negocio
- autenticacao e sessao
- interface Tkinter
- utilitarios de apoio
- testes automatizados

## 1.6 Principais funcionalidades

- cadastro, edicao, inativacao e exclusao de empresas
- observacao livre por empresa com limite de 255 caracteres
- cadastro de documentos com meios de recebimento por documento
- manutencao de tipos com ocorrencia configuravel
- ocorrencia especial por tipo:
  - mensal
  - trimestral
  - anual em janeiro
- controle de status mensal com `Recebido`, `Pendente` e `Encerrado`
- exibicao automatica de `Nao cobrar` nos meses fora da ocorrencia do tipo
- regra de encerramento para ocultar/bloquear meses futuros
- importacao Excel de empresas, documentos e cadastro completo
- compatibilidade com layouts legados de importacao
- relatorio de pendencias em Excel
- backup e restauracao do banco
- backup automatico configuravel em pasta externa
- tela `Sobre` com versao e contato de suporte
- vinculo opcional de pasta local por empresa
- logs por usuario, empresa e periodo

## 1.7 Fluxo principal de uso pelo usuario

1. Fazer login.
2. Cadastrar ou importar empresas.
3. Cadastrar tipos, se necessario, definindo a ocorrencia apropriada.
4. Cadastrar documentos por empresa.
5. Gerar os periodos anuais.
6. Abrir a aba `Controle`.
7. Consultar a empresa no intervalo desejado.
8. Alterar apenas os meses cobraveis daquele tipo.
9. Exportar pendencias, consultar logs ou configurar backup quando necessario.

---
