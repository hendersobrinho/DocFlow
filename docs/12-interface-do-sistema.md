[Voltar ao README](../README.md)

# 12. Interface Do Sistema

## 12.1 Janelas principais

### `LoginWindow`

- captura usuario e senha
- mostra mensagem simples em erro
- posiciona a janela no monitor preferencial
- aplica icone do app

### `MainWindow`

- mostra nome do sistema
- mostra banco atual
- mostra usuario logado
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
- conversa com:
  - `CompanySelector`
  - `PeriodoService`
  - `StatusService`

### `EmpresaTab`

- trata:
  - cadastro/edicao de empresa
  - selecao na `Treeview`
  - inativacao/reativacao
  - exclusao
  - importacao Excel

### `DocumentoTab`

- trata:
  - selecao de empresa
  - cadastro/edicao de documento
  - criacao rapida de tipo
  - exclusao
  - importacao Excel

### `TipoTab`

- trata:
  - CRUD de tipos
  - bloqueio de exclusao em uso

### `EdicaoTab`

- concentra:
  - selecao de empresa
  - atualizacao de dados da empresa
  - ativacao/inativacao
  - exclusao da empresa
  - edicao e exclusao de documentos vinculados

### `PeriodoTab`

- subaba `Gerar periodos`
- subaba `Excluir ano`
- faz dupla confirmacao em exclusao

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
- limpa contexto quando a selecao fica invalida
- evita auto-selecao arriscada por substring

### `ScrollableFrame`

- usado para a grade mensal grande da aba `Controle`

### `DeliveryMethodsField`

- encapsula combobox + listbox para meios de recebimento
- evita duplicacao em duas abas

### `DatabasePathDialog`

- aparece na primeira execucao ou quando o banco salvo nao pode ser aberto
- deixa escolher pasta, criar pasta e definir nome do arquivo do banco

---
