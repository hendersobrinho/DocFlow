[Voltar ao README](../README.md)

# 12. Interface Do Sistema

## 12.1 Janelas principais

### `LoginWindow`

- captura usuario e senha
- permite lembrar credencial neste usuario do computador
- mostra mensagens de erro simples
- aplica icone do app

### `MainWindow`

- mostra nome do sistema, banco atual e usuario logado
- oferece menu `Banco` com backup manual, backup automatico e restauracao
- oferece menu `Ajuda` com a tela `Sobre`
- libera restauracao apenas para admin
- monta abas conforme permissao

## 12.2 Abas principais

### `ControleTab`

- consulta empresa por intervalo de ate 12 meses
- agrupa documentos por tipo
- mostra badge visual para tipos com ocorrencia especial
- exibe `OptionMenu` apenas em meses cobraveis
- exibe `Nao cobrar` automaticamente nos meses fora da ocorrencia
- exibe observacao da empresa e meios de recebimento dos documentos na consulta
- permite vincular/alterar a pasta local da empresa selecionada

### `PanoramaTab`

- mostra a conferencia mensal de empresas em uma lista geral
- filtra por ano, mes, situacao, fila de trabalho, busca textual e empresas ativas
- resume cada empresa como `Sem documentos`, `Sem cobranca`, `Nao iniciada`, `Em andamento`, `Com pendencia` ou `Concluida`
- ordena a lista por prioridade operacional
- mostra progresso, recebidos, pendentes, faltantes e ultima marcacao
- permite abrir a empresa diretamente na aba `Controle` para o mes escolhido

### `EmpresaTab`

- cadastra e edita empresa
- trabalha com codigo, nome, email, contato e observacao
- nao configura mais meios de recebimento no nivel da empresa
- permite importar empresas por Excel
- permite baixar modelo atualizado da planilha

### `DocumentoTab`

- exige selecao de empresa
- cadastra e edita documentos
- configura meios de recebimento por documento
- oferece sugestoes reutilizaveis de nome por tipo
- inclui painel lateral para manter tipos
- o painel lateral agora permite definir a ocorrencia do tipo
- permite importar documentos por Excel e baixar modelo atualizado

### `PeriodoTab`

- gera periodos anuais
- exclui um ano com dupla confirmacao
- exporta relatorio de pendencias por empresa e periodo
- respeita o mesmo limite de ate 12 meses por consulta

### `UserTab`

- lista usuarios
- carrega usuario selecionado para edicao
- permite senha em branco para manter a atual

### `LogTab`

- atualiza filtros dinamicamente
- filtra por empresa, ano e mes
- mostra logs em ordem decrescente

## 12.3 Componentes auxiliares

### `CompanySelector`

- busca por codigo
- filtra sugestoes por nome
- abre janela de lista com `F2` ou `...`
- evita selecao automatica arriscada

### `ScrollableFrame`

- usado para a grade mensal grande da aba `Controle`

### `DeliveryMethodsField`

- encapsula combobox e acoes compactas para meios de recebimento
- reduz duplicacao entre `DocumentoTab` e `EdicaoTab`

### `DatabasePathDialog`

- aparece na primeira execucao ou quando o banco salvo nao pode ser aberto
- deixa escolher pasta, criar pasta e definir nome do arquivo do banco

## 12.4 Experiencia operacional atual

- empresas continuam simples de manter
- documentos concentram o que realmente varia por item:
  - meio de recebimento
  - tipo
  - nome
- tipos concentram a regra de recorrencia
- a aba `Controle` reflete essa regra sem exigir configuracao manual por mes

---
