<p align="center">
  <img src="assets/capa.png" alt="Capa do G-docs" width="100%">
</p>

# G-docs

Sistema desktop local para controle de recebimento de documentos por empresa.

Versao atual: `1.1.0`

O G-docs foi pensado para organizar uma rotina operacional que normalmente fica espalhada entre planilhas, e-mails, mensagens e controles manuais. A proposta do projeto e oferecer uma aplicacao simples, clara e funcional para acompanhar documentos recorrentes, registrar pendencias, marcar recebimentos e manter historico operacional com mais seguranca.

## Objetivo

Centralizar o controle mensal de documentos empresariais em um sistema leve, local e facil de manter, permitindo que a operacao saiba com clareza:

- quais documentos devem ser recebidos
- de qual empresa cada documento pertence
- em qual periodo ele esta pendente ou recebido
- quando um documento foi encerrado e deixou de fazer parte da rotina
- quem realizou alteracoes importantes dentro do sistema

## Missao

Reduzir o trabalho manual e a desorganizacao operacional, transformando um processo repetitivo e sensivel em um fluxo mais confiavel, rastreavel e simples de executar no dia a dia.

## Principais caracteristicas

- aplicacao desktop local, sem dependencia de servidor
- interface em abas, objetiva e voltada para uso operacional
- banco SQLite separado do programa, facilitando atualizacoes sem perda de dados
- controle mensal por empresa, documento e periodo
- regra de encerramento para retirar documentos dos meses futuros
- login de usuarios com senha protegida por hash e opcao de lembrar credencial
- perfis `admin` e `comum`
- logs das alteracoes mais importantes
- importacao completa por Excel para empresas, tipos e documentos no mesmo arquivo
- relatorio de pendencias em Excel por empresa e periodo
- backup do banco pela interface e restauracao restrita a admin
- vinculo opcional de pasta local para documentos por empresa
- reaproveitamento de tipos e nomenclaturas de documentos ja usados no sistema
- preparacao para empacotamento e instalacao

## O que o sistema entrega

- cadastro de empresas
- manutencao de meios de recebimento por empresa
- cadastro de tipos de documento no painel lateral da aba `Documentos`
- cadastro de documentos vinculados a cada empresa com sugestoes reutilizaveis por tipo
- geracao de periodos mensais por ano
- consulta por intervalo de ate 12 meses
- atualizacao de status como `Recebido`, `Pendente` e `Encerrado`
- vinculo de pasta local para cada empresa
- exportacao de relatorio de pendencias em Excel
- backup do banco e restauracao por administradores
- controle de usuarios
- visualizacao de logs administrativos
- estrutura pronta para build por Windows, macOS e Linux

## Fluxo principal de uso

1. O usuario faz login no sistema.
2. Cadastra empresas manualmente ou usa a importacao completa para trazer empresas, tipos e documentos de uma vez.
3. Complementa os documentos necessarios na aba `Documentos`, reutilizando tipos e nomenclaturas ja existentes quando fizer sentido.
4. Gera os periodos anuais de controle.
5. Consulta uma empresa por periodo na aba `Controle`.
6. Atualiza os status mensais dos documentos.
7. Exporta relatorios de pendencias ou faz backup quando necessario.
8. O sistema registra logs das alteracoes relevantes.

## Tecnologias utilizadas

- Python
- Tkinter
- SQLite
- openpyxl
- PyInstaller

## Estrutura da documentacao

Este `README` funciona como apresentacao geral do projeto. A documentacao tecnica detalhada foi separada em arquivos `.md` dentro da pasta [`docs/`](docs), para facilitar estudo, manutencao e navegacao por assunto.

### Documentacao tecnica

- [1. Visao Geral Do Sistema](docs/01-visao-geral-do-sistema.md)
- [2. Estrutura De Pastas E Arquivos](docs/02-estrutura-de-pastas-e-arquivos.md)
- [3. Arquitetura Geral Do Projeto](docs/03-arquitetura-geral-do-projeto.md)
- [4. Hierarquia Das Classes](docs/04-hierarquia-das-classes.md)
- [5. Documentacao Completa Das Classes](docs/05-documentacao-completa-das-classes.md)
- [6. Documentacao Completa Das Funcoes E Metodos](docs/06-documentacao-completa-das-funcoes-e-metodos.md)
- [7. Relacionamento Entre Classes](docs/07-relacionamento-entre-classes.md)
- [8. Mapa De Chamadas Entre Classes E Modulos](docs/08-mapa-de-chamadas-entre-classes-e-modulos.md)
- [9. Fluxos Importantes Do Sistema](docs/09-fluxos-importantes-do-sistema.md)
- [10. Banco De Dados](docs/10-banco-de-dados.md)
- [11. Regras De Negocio](docs/11-regras-de-negocio.md)
- [12. Interface Do Sistema](docs/12-interface-do-sistema.md)
- [13. Dependencias E Bibliotecas Usadas](docs/13-dependencias-e-bibliotecas-usadas.md)
- [14. UML Textual / Diagrama Descritivo](docs/14-uml-textual-diagrama-descritivo.md)
- [15. Ordem Ideal Para Estudar O Projeto](docs/15-ordem-ideal-para-estudar-o-projeto.md)
- [16. Pontos De Melhoria E Refatoracao](docs/16-pontos-de-melhoria-e-refatoracao.md)
- [17. Resumo Final](docs/17-resumo-final.md)
- [18. Icones E Empacotamento Por Sistema Operacional](docs/18-icones-e-empacotamento-por-sistema-operacional.md)
- [19. Observacoes Importantes Para Git E Empacotamento](docs/19-observacoes-importantes-para-git-e-empacotamento.md)
- [20. Encerramento](docs/20-encerramento.md)
