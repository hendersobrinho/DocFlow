[Voltar ao README](../README.md)

# 19. Observacoes Importantes Para Git E Empacotamento

## 19.1 O que deve ir para o Git

Arquivos e pastas que fazem parte do projeto:

- `documentos_empresa_app/`
- `main.py`
- `README.md`
- `requirements.txt`
- `documentos_empresa_app.spec`
- `assets/`
- `scripts/`
- `tests/`
- `docs/`

## 19.2 O que deve ficar fora do Git

Artefatos locais e gerados:

- `.venv/`
- `build/`
- `dist/`
- `dist_release/`
- `dist_installer/`
- bancos SQLite locais e arquivos auxiliares (`*.db`, `*.sqlite`, `*.db-wal`, `*.db-shm`, etc.)
- caches de teste, lint e tipagem
- planilhas exportadas localmente
- arquivos temporarios de editor
- pacotes finais (`.zip`, `.tar.gz`, `.dmg`, `.deb`, `.rpm`, etc.)

## 19.3 Sobre o `.gitignore`

O `.gitignore` da raiz foi ajustado para cobrir:

- artefatos de release
- arquivos de banco e WAL/SHM
- caches de ferramenta
- ambientes virtuais
- arquivos temporarios comuns

Isso evita que o repositório acumule restos de empacotamento ao longo das entregas.

## 19.4 Fluxo recomendado de release

1. atualizar codigo e documentacao
2. rodar os testes
3. gerar o build no sistema operacional correto
4. validar a pasta `dist/DocFLow`
5. distribuir o artefato de `dist_release/`
6. no Windows, gerar o instalador com `Inno Setup` quando necessario

## 19.5 Observacao sobre o repositorio

Se este projeto for publicado isoladamente, o ideal e que a raiz Git seja a propria pasta do projeto:

- raiz recomendada: `/home/hnd/Projects/python`

Se o Git ficar acima disso, o `.gitignore` precisa continuar cobrindo o escopo inteiro do repositório.

---
