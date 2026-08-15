# Architecture Decision Records

Formato [Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
Numerados, imutáveis: um ADR errado não se edita, substitui-se por outro que o marca
como *substituído*.

| # | Título | Estado |
|---|--------|--------|
| [0001](0001-arquitetura-limpa-com-dominio-isolado.md) | Arquitetura limpa com domínio isolado | Aceite |
| [0002](0002-recolha-do-lado-do-servidor.md) | Recolha do lado do servidor | Aceite |
| [0003](0003-postgres-em-vez-de-serie-temporal.md) | Postgres relacional em vez de série temporal dedicada | Aceite |
| [0004](0004-json-ld-como-fonte-primaria.md) | JSON-LD como fonte primária, HTML como fallback | Aceite |
| [0005](0005-ean-como-chave-de-casamento.md) | EAN como chave de casamento entre lojas | Por escrever (Fase 6) |
| [0006](0006-politica-de-recolha.md) | Política de recolha: robots.txt, rate limit, sem contorno de bloqueios | Aceite |
| [0007](0007-licenciamento-de-codigo-e-de-dados.md) | Licenciamento de código e de dados | Proposto |
| [0008](0008-interpretacao-da-regra-dos-30-dias.md) | Interpretação da regra dos 30 dias e da redução progressiva | Proposto |
| [0009](0009-sqlalchemy-core-em-vez-de-mappers-imperativos.md) | SQLAlchemy Core com tradução explícita | Aceite |
| [0010](0010-passagem-diaria-como-processo-unico.md) | Passagem diária como processo único agendado por fora | Aceite |
| [0011](0011-api-publica-de-leitura.md) | API pública: leitura anónima, paginação por posição, contrato verificado | Aceite |

## Template

```markdown
# ADR-NNNN — Título

## Estado
Proposto | Aceite | Substituído por ADR-NNNN

## Contexto
Os factos e as forças em jogo. Sem a decisão.

## Alternativas consideradas
No mínimo duas, com o que cada uma custaria.

## Decisão
O que fica decidido, na voz ativa.

## Consequências
O que passa a ser mais fácil, o que passa a ser mais difícil, e o gatilho concreto
que faria reverter esta decisão.
```
