# Architecture Decision Records

Formato [Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).
Numerados, imutáveis: um ADR errado não se edita, substitui-se por outro que o marca
como *substituído*.

| # | Título | Estado |
|---|--------|--------|
| [0001](0001-arquitetura-limpa-com-dominio-isolado.md) | Arquitetura limpa com domínio isolado | Aceite |
| [0002](0002-recolha-do-lado-do-servidor.md) | Recolha do lado do servidor | Por escrever (Fase 3) |
| [0003](0003-postgres-em-vez-de-serie-temporal.md) | Postgres relacional em vez de série temporal dedicada | Por escrever (Fase 2) |
| [0004](0004-json-ld-como-fonte-primaria.md) | JSON-LD como fonte primária, HTML como fallback | Por escrever (Fase 3) |
| [0005](0005-ean-como-chave-de-casamento.md) | EAN como chave de casamento entre lojas | Por escrever (Fase 6) |
| [0006](0006-politica-de-recolha.md) | Política de recolha: robots.txt, rate limit, sem contorno de bloqueios | Por escrever (Fase 3) |
| [0007](0007-licenciamento-de-codigo-e-de-dados.md) | Licenciamento de código e de dados | Proposto |

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
