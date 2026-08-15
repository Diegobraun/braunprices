# ADR-0003 — PostgreSQL relacional em vez de uma base de série temporal

## Estado

Aceite — 2026-08-15.

## Contexto

Os dados deste sistema são séries temporais: um preço, por referência de loja, ao longo
do tempo. O reflexo é ir buscar uma base desenhada para isso — TimescaleDB, InfluxDB,
ClickHouse.

Mas o perfil real dos dados não é o de telemetria:

- **Volume baixo.** Uma passagem diária a alguns milhares de referências dá alguns
  milhares de linhas por dia. Um ano são poucos milhões. Uma base de série temporal
  existe para milhões de pontos por *minuto*.
- **Escrita rara e em bloco.** Uma vez por dia, num lote, não em fluxo contínuo.
- **Leitura estreita.** A consulta dominante é "o histórico desta referência" — dezenas
  a centenas de linhas. Não há agregação sobre milhões de pontos, nem *downsampling*,
  nem retenção com expiração: o histórico antigo é o produto e nunca se apaga.
- **Relações a sério.** Produto, referências de loja, casamento por EAN. Isto é um
  modelo relacional, não um conjunto de séries etiquetadas.

## Alternativas consideradas

**TimescaleDB.** É PostgreSQL com hipertabelas, o que a torna a opção menos arriscada
das três. Traria compressão e agregados contínuos que este volume não justifica, ao
custo de uma extensão a instalar em todos os ambientes e nos Testcontainers.

**ClickHouse.** Excelente a varrer colunas, mau a fazer o que aqui se faz a toda a hora:
chaves estrangeiras, unicidade e correções pontuais. E não tem *UPDATE* barato — o que
até seria irónico, num sistema que nunca faz *UPDATE*.

**PostgreSQL 16 simples.** A escolhida.

## Decisão

PostgreSQL 16, sem extensões além do que vem de origem. O modelo é relacional, com
`price_observations` a acumular factos e um índice composto em
`(listing_id, observed_at DESC)` a servir a consulta dominante.

Duas invariantes ficam a viver **na base de dados**, e não apenas no código:

1. Um trigger recusa `UPDATE` e `DELETE` em `price_observations`. Uma regra que
   existisse só na camada de aplicação sobreviveria até à primeira sessão de `psql`.
2. As chaves estrangeiras são `ON DELETE RESTRICT`. Apagar uma referência de loja que
   tenha histórico é impossível, e não apenas desaconselhado.

## Consequências

Fica mais fácil: correr em qualquer sítio que tenha Postgres; fazer *joins* sem
pensar; usar Testcontainers com uma imagem oficial e sem preparação especial.

Fica mais difícil: agregações analíticas sobre todo o histórico, se um dia forem
precisas. Serão lentas antes de serem impossíveis, o que dá tempo para reagir.

**O gatilho que reverte esta decisão:** quando a consulta dominante deixar de caber em
tempo aceitável com o índice existente, ou quando `price_observations` passar de uns
100 milhões de linhas — o que, ao ritmo previsto, são muitos anos. O primeiro passo
nesse dia é migrar para TimescaleDB, que não obriga a mudar nem o modelo nem o SQL: é a
razão de ser esta a alternativa preferida, e não outra.
