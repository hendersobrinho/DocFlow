[Voltar ao README](../README.md)

# 1. Visao Geral Do Sistema

## 1.1 Objetivo do sistema

O G-docs e uma aplicacao desktop local, escrita em Python com Tkinter e SQLite, destinada ao controle operacional de documentos recorrentes recebidos de diferentes empresas. O foco do projeto e oferecer um fluxo simples, direto e persistente para cadastro, consulta, acompanhamento mensal, encerramento de documentos, auditoria basica por usuario e empacotamento para uso interno.

## 1.2 Problema que o sistema resolve

O sistema resolve um problema comum de operacao interna: acompanhar, por empresa e por periodo, quais documentos deveriam ter sido recebidos, quais estao pendentes, quais ja chegaram e quais deixaram de ser exigidos a partir de um determinado mes.

Sem uma ferramenta assim, a operacao tende a depender de planilhas dispersas, memoria operacional, trocas de mensagem e controles manuais pouco confiaveis. O G-docs centraliza essa rotina em um banco local com interface grafica e regras de negocio consistentes.

## 1.3 Proposta do projeto

A proposta do projeto e deliberadamente enxuta:

- aplicacao desktop local
- sem servidor
- sem multiusuario concorrente
- sem arquitetura distribuida
- sem dashboards complexos
- com persistencia local em SQLite
- com interface simples por abas
- com autenticacao basica e trilha de auditoria funcional

Em outras palavras, o projeto prioriza estabilidade, manutencao simples e clareza de fluxo sobre sofisticacao arquitetural.

## 1.4 Como o sistema funciona de forma geral

O fluxo geral e este:

1. O sistema inicia em `main.py`.
2. Antes de abrir a aplicacao, garante que existe um caminho valido para o banco SQLite.
3. O arquivo do banco fica fora da pasta instalada do programa, em local configuravel pelo usuario.
4. O sistema inicializa o esquema do banco, aplica migracoes e garante dados basicos, como tipos iniciais e usuario admin padrao.
5. A tela de login e aberta.
6. Depois da autenticacao, a janela principal abre com abas de operacao.
7. As abas chamam servicos de negocio.
8. Os servicos validam regras, acionam repositórios e gravam logs quando necessario.
9. Os repositórios leem e escrevem no SQLite.
10. Os resultados voltam para a interface, que atualiza listas, tabelas e filtros.

## 1.5 Modulos principais

Os modulos principais do sistema sao:

- bootstrap e orquestracao inicial
- persistencia SQLite
- camada de repositórios
- camada de servicos de negocio
- sessao/autenticacao/autorizacao simples
- interface Tkinter
- utilitarios de configuracao, caminhos, icones e exibicao
- testes automatizados
- scripts de build e instalador

## 1.6 Principais funcionalidades

As funcionalidades principais atualmente implementadas sao:

- escolha e persistencia do caminho do banco
- login com usuario e senha
- login lembrado neste usuario do computador
- criacao automatica do admin padrao
- cadastro, edicao, inativacao, reativacao e exclusao de empresas
- configuracao de meios de recebimento e pasta vinculada por empresa
- cadastro, edicao e exclusao de tipos de documento
- cadastro, edicao e exclusao de documentos vinculados a empresas
- geracao de periodos mensais por ano
- consulta de ate 12 meses por vez
- controle de status mensal por documento
- regra de encerramento que oculta meses futuros
- importacao de empresas e documentos por Excel
- exportacao de relatorio de pendencias por empresa e periodo
- backup e restauracao do banco pela interface
- cadastro e manutencao de usuarios
- logs de operacoes relevantes
- filtros de logs por empresa e periodo
- preparacao para empacotamento com PyInstaller
- base para instalador Windows com Inno Setup

## 1.7 Fluxo principal de uso pelo usuario

O fluxo operacional mais comum e:

1. Fazer login.
2. Cadastrar ou importar empresas.
3. Cadastrar tipos de documento, se necessario.
4. Cadastrar documentos por empresa.
5. Gerar os periodos anuais que serao controlados.
6. Abrir a aba `Controle`.
7. Selecionar a empresa e o intervalo de meses.
8. Visualizar os documentos agrupados por tipo.
9. Marcar os status mensais como `Recebido`, `Pendente` ou `Encerrado`.
10. Consultar logs e ajustes administrativos, se o usuario for admin.

---
