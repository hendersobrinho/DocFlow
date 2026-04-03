[Voltar ao README](../README.md)

# 12. Interface Do Sistema

## 12.1 Janelas principais

### `LoginWindow`

- captura usuario e senha
- permite lembrar credencial neste usuario do computador
- mostra mensagem simples em erro
- posiciona a janela no monitor preferencial
- aplica icone do app

### `MainWindow`

- mostra nome do sistema
- mostra banco atual
- mostra usuario logado
- oferece menu `Banco` com backup e restauracao
- libera restauracao apenas para admin
- oferece `Logout`
- abre abas conforme permissao

## 12.2 Abas e seus eventos

### `ControleTab`

- trata:
  - mudanca de ano inicial/final
  - consulta
  - limpeza de filtros
  - clique para expandir/recolher grupo
  - alteracao de status
  - vinculo/alteracao da pasta local da empresa
- conversa com:
  - `CompanySelector`
  - `PeriodoService`
  - `StatusService`

### `EmpresaTab`

- trata:
  - cadastro/edicao de empresa
  - consulta por seletor reutilizavel
  - inativacao/reativacao
  - exclusao
  - importacao Excel
  - download de modelo de planilha

### `DocumentoTab`

- trata:
  - selecao de empresa
  - cadastro/edicao de documento
  - manutencao de tipos de documento no painel lateral
  - exclusao de um ou varios documentos
  - importacao Excel
  - download de modelo de planilha

### `PeriodoTab`

- subaba `Gerar periodos`
- subaba `Excluir ano`
- subaba `Relatorio de pendencias`
- faz dupla confirmacao em exclusao
- permite exportar pendencias em Excel por empresa(s) e periodo
- aplica o mesmo limite de ate 12 meses nas consultas/exportacoes

### `UserTab`

- lista usuarios
- carrega usuario selecionado para edicao
- permite senha em branco para manter a atual

### `LogTab`

- atualiza filtros dinamicamente
- filtra por empresa, ano e mes
- mostra logs em ordem decrescente de data/hora

## 12.3 Componentes auxiliares de UI

### `CompanySelector`

- busca por codigo
- filtra sugestoes por nome
- abre janela de lista com `F2` ou `...`
- a lista faz filtro em tempo real conforme digitacao
- limpa contexto quando a selecao fica invalida
- evita auto-selecao arriscada por substring

### `ScrollableFrame`

- usado para a grade mensal grande da aba `Controle`

### `DeliveryMethodsField`

- encapsula combobox + acoes compactas para meios de recebimento
- evita duplicacao em duas abas

### `DatabasePathDialog`

- aparece na primeira execucao ou quando o banco salvo nao pode ser aberto
- deixa escolher pasta, criar pasta e definir nome do arquivo do banco

---
