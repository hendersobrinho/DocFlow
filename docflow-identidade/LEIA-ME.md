# DocFlow — Identidade visual v1.0

Arquivo de design no Figma: https://www.figma.com/design/phBS6C1Ptp0yEYrCMewW4x

## O símbolo

Um **D** que abraça um **documento**, com duas **trilhas** recortadas no vazio mostrando que o arquivo acabou de chegar.

- **D (navy)** — o sistema / o escritório
- **Documento (espaço vazio)** — o arquivo do cliente
- **Trilhas** — o agente levando cada arquivo para a pasta certa
- **Dobra ciano** — documento identificado
- **Traço laranja** — o dado extraído (CNPJ, competência)

Geometria: módulo u = 16 px num grid de 512. Símbolo 21 × 20 u, documento 8 × 11 u (≈ A4), dobra 3 u, cantos 2 u.

## Cores (herdadas da Métodos)

| Nome | HEX | Papel |
|---|---|---|
| Navy Métodos | `#203461` | base, fundos, o D |
| Ciano Fluxo | `#4BBDCD` | identificado, ativo, foco (texto em cima: navy) |
| Laranja Dado | `#F9B259` | pendência, destaque pontual (texto em cima: navy) |
| Navy 900 | `#0F1A33` | fundo de janela (tema escuro) |
| Navy 800 | `#16254A` | superfícies (tema escuro) |
| Navy 600 | `#2E4A85` | bordas fortes, hover |
| Navy 300 | `#8C9BC0` | texto secundário no escuro |
| Névoa | `#F2F5FA` | fundo (tema claro) |
| Linha | `#DCE3EE` | bordas (tema claro) |
| Grafite | `#1B2335` | texto principal (tema claro) |
| Cinza | `#5E6B82` | texto secundário (tema claro) |

Proporção: navy e tons 55% · névoa/branco 30% · ciano 10% · laranja 5%.
Branco sobre ciano ou laranja não passa em contraste — use navy.

## Tipografia

- **Sora** — marca e títulos (wordmark: "Doc" SemiBold + "Flow" Light, tracking −2%)
- **Inter** — interface (Segoe UI como reserva no Windows)
- **JetBrains Mono** — CNPJ, competências, números

## Pastas

- `simbolo/` — símbolo em cor, negativo, mono navy e mono branco (SVG + PNG)
- `logo/` — assinatura horizontal e vertical, para fundo claro e navy (SVG + PNG, texto já convertido em curvas)
- `icone/` — ícone do app: `icon.svg` (mestre), `icon.png` (1024), `icon.ico` (16 a 256, com a versão "Pequeno" em 16 e 24 px), `icon.icns`, variantes claras e PNGs avulsos
- `capa/` — capa do repositório no GitHub (1600 × 400)

## Para trocar no repositório

`icone/icon.svg`, `icon.png`, `icon.ico` e `icon.icns` substituem os arquivos de `assets/icons/`, e `capa/capa.png` substitui `assets/capa.png`.

O `scripts/generate_icons.py` (que o build roda) desenha o `icon.svg` com o QtSvg e usa o `assets/icons/icon-pequeno.svg` nos tamanhos de 16 a 48 px, com a folha maior para não sumir no atalho.
