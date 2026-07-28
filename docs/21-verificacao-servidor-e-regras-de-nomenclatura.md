[Voltar ao README](../README.md)

# 21. Verificacao De Servidor E Regras De Nomenclatura

Este documento explica, na pratica, como funciona a verificacao automatica de arquivos no servidor.

A ideia da funcionalidade e simples:

- o usuario informa a pasta raiz onde ficam as empresas
- o sistema procura a pasta de cada empresa pelo codigo cadastrado
- dentro da empresa, procura o ano da competencia
- dentro do ano, procura os documentos esperados
- se encontrar um arquivo com alta confianca, permite marcar o documento como `Recebido`
- se existir duvida, duplicidade ou conflito, manda para `Revisar`
- se nao encontrar arquivo valido para aquela competencia, mostra `Nao encontrado`

Importante: essa verificacao apenas le nomes de pastas e arquivos. Ela nao apaga, nao renomeia e nao move documentos.

## 21.1 Onde abrir

Na aba `Panorama`, use o menu de ferramentas/acoes e abra `Verificar servidor`.

A verificacao sempre parte da competencia selecionada no Panorama, por exemplo `05/2026`.

## 21.2 Conceitos principais

### Pasta raiz

E a pasta que contem todas as empresas.

Exemplo:

```text
/home/usuario/Documents/Empresas
```

Dentro dela podem existir pastas como:

```text
1. METODOS
6. CLINRIM
11. SOFTH
123 - EMPRESA TESTE
```

O sistema tenta relacionar a empresa pelo `codigo_empresa` cadastrado.

### Competencia

Competencia e o mes/ano que esta sendo conferido.

Exemplos:

```text
01/2026
05/2026
12/2026
```

O arquivo pode indicar a competencia no proprio nome:

```text
1. Sicoob CC 05-2026.pdf
1. Sicoob CC maio 2026.pdf
1. Sicoob CC 052026.pdf
```

Ou a competencia pode vir da pasta:

```text
1. METODOS/2026/05 - Maio/Extratos Bancarios/Conta Corrente/Sicoob CC.pdf
```

## 21.3 Modos de verificacao

### Somente competencia atual

Verifica apenas a competencia selecionada.

Exemplo: se o Panorama esta em `05/2026`, ele verifica apenas maio de 2026.

Esse modo e mais rapido e serve para a rotina diaria.

### Pendentes ate a competencia

Verifica todos os meses cobraveis ate a competencia selecionada.

Exemplo: se a competencia e `05/2026`, um documento mensal pode gerar linhas para:

```text
01/2026
02/2026
03/2026
04/2026
05/2026
```

Esse modo e melhor para revisar historico ou corrigir meses antigos.

Se existir arquivo de maio, ele nao deve resolver janeiro, fevereiro, marco ou abril. O arquivo de maio aparece como arquivo de outra competencia ignorado.

## 21.4 Estrutura das pastas

A configuracao `Estrutura das pastas` informa como o cliente costuma organizar os arquivos.

### Detectar automaticamente

O sistema tenta reconhecer varios padroes ao mesmo tempo.

Use quando o escritorio ainda nao tem um padrao unico ou esta testando.

### Arquivos dentro da pasta do ano

Padrao:

```text
Empresas/
  1. METODOS/
    2026/
      1. Sicoob CC 05-2026.pdf
```

Use quando todos os arquivos do ano ficam juntos na pasta `2026`.

### Pasta da competencia dentro do ano

Padrao:

```text
Empresas/
  1. METODOS/
    2026/
      05 - Maio/
        1. Sicoob CC.pdf
```

Use quando o cliente separa os documentos por mes.

Nesse caso, se a opcao permitir competencia pela pasta, o arquivo pode nao ter `05/2026` no nome, porque a pasta `05 - Maio` ja indica a competencia.

### Pasta do documento, depois competencia

Padrao:

```text
Empresas/
  1. METODOS/
    2026/
      DAS Simples Nacional/
        05 - Maio/
          DAS.pdf
```

Use quando a organizacao principal e por documento, e dentro dele ficam os meses.

## 21.5 Fonte da competencia

A configuracao `Competencia vem de` controla onde o sistema pode reconhecer mes/ano.

### Nome do arquivo ou pasta da competencia

Mais flexivel.

Aceita:

```text
Sicoob CC 05-2026.pdf
Sicoob CC maio 2026.pdf
05 - Maio/Sicoob CC.pdf
```

### Somente mes/ano no nome do arquivo

Mais rigido.

Aceita:

```text
Sicoob CC 05-2026.pdf
Sicoob CC maio 2026.pdf
```

Nao aceita apenas:

```text
05 - Maio/Sicoob CC.pdf
```

Use esse modo quando a pasta de mes nao for confiavel ou quando o cliente mistura arquivos de outros meses dentro da mesma pasta.

## 21.6 Aliases de pastas

O botao `Aliases de pastas...` permite ensinar nomes alternativos de pastas.

Exemplos de pasta bancaria:

```text
Extratos Bancarios
Bancos
Banco
Movimento Bancario
```

Exemplos de conta corrente:

```text
Conta Corrente
CC
C C
C.C
Corrente
```

Exemplos de aplicacao:

```text
Aplicacao
Aplicacoes
Investimentos
Poupanca
```

Isso ajuda o sistema a entender variacoes reais de cada cliente.

## 21.7 Regras de nomenclatura

O botao `Nomenclatura...` configura como o nome do arquivo deve ser interpretado.

O sistema aceita padroes com variaveis:

```text
{codigo}
{documento}
{competencia}
{banco}
{tipo}
```

### Exemplos de padrao

Padrao generico:

```text
{codigo} {documento} {competencia}
```

Arquivo que combina:

```text
1 DAS Simples Nacional 05-2026.pdf
```

Padrao bancario:

```text
{codigo}. {banco} {tipo} {competencia}
```

Arquivo que combina:

```text
1. Sicoob CC 05-2026.pdf
```

Padrao sem codigo:

```text
{documento} {competencia}
```

Arquivo que combina:

```text
DAS Simples Nacional maio 2026.pdf
```

## 21.8 Exigir padrao de nomenclatura

Na tela de nomenclatura existe a opcao:

```text
Exigir que o arquivo siga pelo menos um dos padroes abaixo
```

Quando marcada, o sistema fica mais rigoroso.

Exemplo de padrao exigido:

```text
{codigo} {documento} {competencia}
```

Arquivo aceito:

```text
1 DAS Simples Nacional 05-2026.pdf
```

Arquivo que vai para revisar:

```text
DAS 05-2026.pdf
```

Motivo: faltou uma parte esperada do padrao, como o codigo ou termos suficientes do documento.

## 21.9 Termos obrigatorios e proibidos

### Termos obrigatorios

Use quando todo arquivo valido precisa ter uma palavra especifica.

Exemplo:

```text
oficial; assinado
```

Se o arquivo nao tiver esses termos, vai para `Revisar`.

### Termos proibidos

Use para evitar baixa automatica com arquivo errado.

Exemplo:

```text
cancelado; rascunho; comprovante
```

Se o arquivo tiver um desses termos, vai para `Revisar`.

Exemplo:

```text
1 Sicoob CC cancelado 05-2026.pdf
```

Resultado esperado: `Revisar`.

## 21.10 Documentos nao bancarios

A opcao `Conferir documentos nao bancarios pelo nome cadastrado` permite verificar documentos como:

```text
DAS Simples Nacional
DARF IRPJ
Folha de Pagamento
Contrato de Locacao
Relatorio de Estoque
Certidao Negativa
```

O sistema usa o nome cadastrado do documento como base.

Exemplo de documento cadastrado:

```text
DAS Simples Nacional
```

Arquivo aceito:

```text
1 DAS Simples Nacional 05-2026.pdf
```

Arquivo suspeito:

```text
1 Recibo qualquer 05-2026.pdf
```

Resultado esperado: `Nao encontrado` ou `Revisar`, dependendo da pontuacao.

## 21.11 Documentos bancarios

Para extratos bancarios, o sistema tenta considerar:

- banco esperado
- tipo do documento, como `CC` ou `Aplicacao`
- competencia
- codigo da empresa
- pasta onde o arquivo esta

Exemplo de documento cadastrado:

```text
Sicoob C/C 78837-6
```

Arquivo bom:

```text
1. Sicoob CC 05-2026.pdf
```

Arquivo suspeito:

```text
1. Bradesco CC 05-2026.pdf
```

Motivo: banco diferente.

## 21.12 Duplicidade

Se o sistema encontrar mais de um arquivo forte para o mesmo documento e competencia, ele nao deve marcar automaticamente.

Exemplo:

```text
1 Sicoob CC 05-2026.pdf
1 Sicoob CC maio 2026 copia.pdf
```

Resultado esperado:

```text
Revisar
```

Motivo: possivel duplicidade.

## 21.13 Mes errado ou arquivo de outra competencia

Se a verificacao esta em `03/2026` e o sistema encontra:

```text
1 Sicoob CC maio 2026.pdf
```

Ele nao deve usar esse arquivo para marco.

Resultado esperado para `03/2026`:

```text
Nao encontrado
```

Alerta:

```text
Arquivo de mes futuro ignorado: 05/2026
```

Isso evita a baixa errada de meses antigos usando arquivo do mes atual.

## 21.14 Quando o sistema marca automaticamente

O sistema so deve liberar marcacao automatica quando a linha esta como:

```text
Alta confianca
```

E quando o arquivo encontrado pertence a mesma competencia analisada.

Exemplo:

```text
Competencia analisada: 05/2026
Arquivo encontrado: 1 Sicoob CC 05-2026.pdf
Comp. arquivo: 05/2026
Resultado: Alta confianca
```

Nesse caso, o botao de aplicar marcacoes pode marcar como `Recebido`.

## 21.15 Quando o sistema manda revisar

Vai para `Revisar` quando existe algum risco, por exemplo:

- banco diferente
- tipo diferente, como `Aplicacao` quando o esperado era `CC`
- competencia nao identificada
- padrao de nomenclatura nao confirmado
- termo obrigatorio ausente
- termo proibido presente
- mais de um arquivo possivel para o mesmo documento

O objetivo do `Revisar` e evitar baixa automatica indevida.

## 21.16 Como orientar o cliente ou setor

Para a automacao funcionar melhor, o ideal e orientar um padrao simples.

Padrao recomendado:

```text
{codigo} {documento} {competencia}
```

Exemplos:

```text
1 DAS Simples Nacional 05-2026.pdf
1 Sicoob CC 05-2026.pdf
1 Folha de Pagamento 05-2026.pdf
```

Se o cliente usa pastas por mes, tambem funciona:

```text
1. METODOS/
  2026/
    05 - Maio/
      1 DAS Simples Nacional.pdf
      1 Sicoob CC.pdf
```

Nesse caso, configure:

- `Estrutura das pastas`: `Pasta da competencia dentro do ano`
- `Competencia vem de`: `Nome do arquivo ou pasta da competencia`

## 21.17 Configuracao sugerida para escritorio contabil

Para o cenario atual do escritorio:

```text
Empresas/
  1. METODOS/
    2026/
      Extratos Bancarios/
        Conta Corrente/
          1. Sicoob CC maio 2026.pdf
        Aplicacao/
          1. Sicoob Aplicacao maio 2026.pdf
```

Configuracao sugerida:

- `Estrutura das pastas`: `Detectar automaticamente`
- `Competencia vem de`: `Nome do arquivo ou pasta da competencia`
- marcar `Conferir documentos nao bancarios pelo nome cadastrado`
- marcar `Exigir termos do documento no nome do arquivo`
- em `Nomenclatura...`, manter pelo menos:

```text
{codigo} {documento} {competencia}
{codigo}. {banco} {tipo} {competencia}
{documento} {competencia}
```

Se o escritorio quiser padronizar de forma mais rigida, marque tambem:

```text
Exigir que o arquivo siga pelo menos um dos padroes abaixo
```

## 21.18 Configuracao sugerida para outros tipos de empresa

Para uma empresa nao contabil, a ideia e cadastrar documentos recorrentes e criar um padrao de nome.

Exemplo para imobiliaria:

```text
Contrato de Locacao
Comprovante de Pagamento
Relatorio de Inadimplencia
```

Padrao:

```text
{codigo} {documento} {competencia}
```

Exemplos:

```text
25 Contrato de Locacao 05-2026.pdf
25 Comprovante de Pagamento 05-2026.pdf
25 Relatorio de Inadimplencia 05-2026.pdf
```

Exemplo para clinica:

```text
Relatorio de Convenio
Nota Fiscal Prestador
Folha de Ponto
```

O mesmo motor de regras funciona, porque ele se baseia no documento cadastrado e no padrao configurado.

## 21.19 Como interpretar os resultados

### Alta confianca

O sistema encontrou um arquivo forte para o documento e competencia.

Pode ser aplicado automaticamente, desde que a competencia do arquivo seja a mesma da linha.

### Revisar

O sistema encontrou algo possivel, mas existe duvida.

O usuario deve abrir a pasta e conferir manualmente.

### Nao encontrado

O sistema nao encontrou arquivo valido para aquela competencia.

Pode existir arquivo de outro mes, mas ele sera ignorado para evitar baixa errada.

### Erro

Alguma pasta nao existe, nao foi configurada ou nao pode ser acessada.

## 21.20 Regra de ouro

A automacao deve ser conservadora.

Melhor mandar para `Revisar` do que marcar `Recebido` com arquivo errado.

O caminho ideal e:

1. cadastrar bem os documentos
2. combinar um padrao de nomenclatura
3. configurar aliases de pastas quando necessario
4. rodar a verificacao
5. aplicar automaticamente apenas alta confianca
6. revisar manualmente os conflitos

