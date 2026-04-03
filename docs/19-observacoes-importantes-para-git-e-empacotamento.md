[Voltar ao README](../README.md)

# 19. Observacoes Importantes Para Git E Empacotamento

## 19.1 O que deve ir para o Git

Arquivos importantes para versionamento:

- codigo-fonte em `documentos_empresa_app/`
- `main.py`
- `requirements.txt`
- `README.md`
- `documentos_empresa_app.spec`
- `assets/icons/`
- `scripts/`
- `installer/`
- `tests/`

## 19.2 O que deve ficar fora do Git

Artefatos locais e gerados:

- `.venv/`
- `build/`
- `dist/`
- `dist_installer/`
- caches
- logs
- bancos locais
- arquivos temporarios de editor

## 19.3 Observacao sobre o seu repositorio atual

No ambiente em que esta documentacao foi gerada, o `git rev-parse --show-toplevel` aponta para `/home/hnd`, ou seja, o repositorio Git atual esta acima da pasta do projeto.

Na pratica, isso significa:

- se voce pretende publicar somente este projeto, o ideal e criar um repositorio Git proprio em `/home/hnd/Projects/python`
- se for manter o repositorio atual na pasta home, o `.gitignore` da raiz do repositorio precisa cobrir o escopo inteiro, nao apenas esta pasta

---
