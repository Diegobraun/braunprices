# ADR-0009 — SQLAlchemy Core com tradução explícita, em vez de mappers imperativos

## Estado

Aceite — 2026-08-15. Substitui, quanto ao mecanismo, a indicação de usar mappers
imperativos; mantém integralmente o objetivo que a motivava.

## Contexto

O objetivo era claro: persistir sem que o domínio soubesse que existe uma base de
dados. O mecanismo previsto para o conseguir era o mapeamento imperativo do SQLAlchemy
(`registry.map_imperatively`), que mantém as classes de domínio livres de qualquer
declaração de ORM.

Ao implementar, apareceu um obstáculo que não é de configuração:

`PriceObservation` é `@dataclass(frozen=True, slots=True)`. A imutabilidade não é um
gosto — é a invariante de que depende todo o valor do sistema, porque um histórico
editável não prova nada sobre ninguém.

O ORM do SQLAlchemy, para mapear uma classe, precisa de:

1. **instrumentar os atributos**, substituindo-os por descritores — o que `slots`
   impede sem uma alteração à classe; e
2. **escrever nos atributos ao carregar** uma linha da base de dados — o que `frozen`
   impede por construção.

Ou seja: o mecanismo previsto exigiria abrir mão exatamente daquilo que o objetivo
existe para proteger.

## Alternativas consideradas

**Tirar `frozen` a `PriceObservation`.** Resolveria o mapeamento e destruiria a
invariante central. Recusada sem hesitação.

**Manter `frozen` no domínio e ter uma segunda classe mutável só para o ORM.** Funciona,
mas produz duas classes com os mesmos campos, tradução entre elas, e o risco permanente
de divergirem — que é o custo da tradução explícita, mais o custo de manter uma classe
a fingir que é outra.

**SQLAlchemy Core, com `Table` e tradução explícita nos repositórios.** A escolhida.

## Decisão

O esquema é declarado com `Table` do SQLAlchemy Core em `tables.py`. A tradução entre
linha e entidade é uma função por sentido, em `mappers.py`, com os dois sentidos lado a
lado para que um campo acrescentado num e esquecido no outro salte à vista em revisão.

O domínio fica exatamente como estava: sem herança, sem metaclasses, sem descritores,
sem `import sqlalchemy` — o que o contrato de `import-linter` continua a verificar em
cada build.

Duas consequências desta escolha ficam registadas onde acontecem:

- `observation_id` é gerado no mapper, não no domínio. Uma observação é identificada
  pelo facto que descreve; a chave técnica é assunto do armazenamento.
- `observed_day` é escrito a partir do domínio em vez de calculado em SQL, porque
  `AT TIME ZONE 'Europe/Lisbon'` é `STABLE` e não `IMMUTABLE` em PostgreSQL, e por isso
  não pode entrar num índice nem numa coluna gerada. Um teste de integração verifica
  que os dois concordam, incluindo nas noites de mudança de hora.

## Consequências

Fica mais fácil: garantir que o histórico é append-only, porque não existe nenhum
mecanismo de *dirty tracking* capaz de emitir um `UPDATE` sem que alguém o tenha
escrito; perceber que SQL corre, olhando para o repositório; manter o domínio testável
sem qualquer infraestrutura.

Fica mais difícil: cada campo novo obriga a tocar em três sítios — tabela, mapper de
ida e mapper de volta. É trabalho mecânico e visível em revisão, ao contrário do
carregamento preguiçoso que um ORM traria de graça e que aqui não faz falta: o agregado
`Product` é pequeno e carrega-se inteiro.

**O que provaria esta decisão errada:** se os mappers passarem a representar mais
linhas do que o domínio que servem, ou se aparecer um agregado profundo o suficiente
para que carregá-lo inteiro deixe de ser aceitável, o custo da tradução manual deixa de
se pagar e vale a pena reabrir a hipótese de duas classes com mapeamento automático.

## Nota sobre o alcance da garantia de append-only

O trigger cobre `UPDATE` e `DELETE` por linha. **Não** cobre `TRUNCATE`, que não dispara
triggers de linha — e é isso que permite aos testes de integração limpar as tabelas.
Em produção, a defesa contra `TRUNCATE` é de privilégios: o utilizador da aplicação não
deve ser dono das tabelas. Fica registado como pendente para o momento em que houver um
ambiente de produção a configurar.
