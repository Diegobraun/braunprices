# ADR-0008 — Interpretação da regra dos 30 dias e da redução progressiva

## Estado

**Proposto** — 2026-08-15. As decisões marcadas abaixo como *interpretação* não têm
confirmação de nenhuma autoridade; estão registadas aqui para poderem ser contestadas
com precisão em vez de descobertas por leitura do código.

## Contexto

O Decreto-Lei n.º 109-G/2021 obriga quem anuncia uma redução a indicar o preço mais
baixo praticado nos 30 dias consecutivos anteriores, incluindo períodos que já tenham
sido de saldos ou promoções. O n.º 5 do mesmo artigo acrescenta que, quando a redução
é progressivamente aumentada, o preço anterior é o que vigorava antes da primeira
aplicação da redução.

O texto legal fala de duas coisas que a implementação tende a confundir numa só:

1. **Qual foi o preço mais baixo praticado na janela.** É um mínimo sobre observações.
2. **Que número a loja tem de indicar no anúncio.** Coincide com o anterior na maioria
   dos casos, mas não no caso do n.º 5.

Uma única função que respondesse ora a uma pergunta ora à outra, conforme o feitio dos
dados, seria imprevisível no ponto onde a previsibilidade é o produto — e o erro que
produzisse seria um erro legal, não um defeito de apresentação.

Além disso, a lei fala em dias, e "dia" só tem significado dentro de um fuso. E fala em
preço praticado, o que obriga a decidir o que fazer com observações em que o produto
não estava disponível.

## Alternativas consideradas

**Uma função só, que devolve o mínimo.** Simples, mas deixa o n.º 5 por implementar —
justamente o caso que a especificação assinala como o que mais falha.

**Uma função só, que decide internamente qual regra aplicar.** Cobre os dois casos com
uma assinatura, ao custo de o mesmo nome devolver coisas com significados jurídicos
diferentes. Quem consome não consegue saber qual foi aplicada sem reimplementar a
deteção.

**Duas funções, com a segunda a devolver também a base usada.** A escolhida.

## Decisão

### Duas funções, não uma

- `lowest_price_in_window(observations, reference_date, window_days=30) -> Money | None`
  responde ao mínimo, e só a isso. É a assinatura fixada na especificação.
- `reference_price_for_announcement(...) -> ReferencePrice | None` responde ao número a
  indicar num anúncio, e devolve com ele a `ReferenceBasis` que o produziu
  (`LOWEST_IN_WINDOW` ou `BEFORE_PROGRESSIVE_REDUCTION`), a janela e quantas observações
  foram consideradas. Um número sem a regra que o gerou não é verificável por quem o lê.

### Fronteira da janela — decisão

A janela é `[reference_date - 30 dias, reference_date)`: fechada à esquerda, aberta à
direita. "Anteriores" exclui o dia da aplicação do desconto. Incluir esse dia deixaria
entrar no cálculo o preço já promocional — precisamente o número que a norma quer manter
de fora — porque não sabemos a que hora a loja aplicou a redução.

### Fuso horário — decisão

`Europe/Lisbon`. Os instantes são guardados em UTC e convertidos para o fuso local
apenas para determinar o dia, o que mantém distinguíveis as duas ocorrências de 01:30 na
noite em que o relógio recua.

### Buracos na série — decisão

Não há interpolação. Dias sem observação continuam sem observação. Inventar o valor de
um dia em falta seria fabricar exatamente o tipo de facto que este sistema existe para
verificar.

### Disponibilidade — decisão

Contam como preço praticado: `IN_STOCK`, `LIMITED_AVAILABILITY`, `PRE_ORDER`,
`BACK_ORDER`. Não contam: `OUT_OF_STOCK`, `SOLD_OUT`, `DISCONTINUED` e `UNKNOWN`.

`UNKNOWN` não contar é a escolha conservadora: contar uma observação cuja
disponibilidade não conseguimos ler seria afirmar um facto que não observámos. O custo é
concreto — se uma loja não declarar disponibilidade, a sua série fica vazia e o sistema
não consegue dizer nada sobre ela.

### Deteção da redução progressiva — **interpretação**

O n.º 5 é aplicado apenas quando **as duas** condições se verificam:

1. a série de degraus de preço dentro da janela é estritamente decrescente do princípio
   ao fim, ou seja **não houve qualquer subida**; e
2. há pelo menos **duas reduções sucessivas** (três degraus distintos).

Os degraus são obtidos colapsando repetições consecutivas: a recolha é diária e o preço
costuma manter-se, pelo que a série crua é sobretudo repetição. Avaliar a monotonia
sobre a série crua faria a igualdade entre dias consecutivos partir a cadeia, e o n.º 5
nunca seria detetado em dados reais.

A condição 1 é estreita de propósito. Uma subida a meio significa que o preço foi
reposto e que a campanha não é contínua; interpretar de forma mais larga permitiria
indicar como referência um preço mais alto do que o consumidor chegou a ver dentro da
mesma janela, que é o abuso que a norma existe para impedir.

A condição 2 existe porque uma redução única não é uma redução "progressivamente
aumentada". Sem ela, uma série como `100 → 80 → 120 → 110` daria 120 € como referência,
quando o consumidor viu 80 € na mesma janela.

Quando qualquer das condições falha, aplica-se a regra geral.

## Consequências

Fica mais fácil: expor os dois números na API sem ambiguidade, e justificar cada
resposta com a base que a produziu.

Fica mais difícil: quem consome tem de escolher qual das funções quer. É deliberado —
essa escolha é uma decisão sobre o que se está a afirmar, e não deve ser tomada por
omissão.

**O que provaria estas decisões erradas:**

- Uma orientação da ASAE ou da Comissão Europeia que fixe a fronteira da janela de forma
  diferente: muda o teste de fronteira e a propriedade `start`/`end_exclusive`.
- Um caso real de campanha contínua com uma subida técnica no meio (correção de erro de
  preço, por exemplo) em que a interpretação estreita produza um número que uma
  autoridade considere errado.
- Uma fração alta de observações `UNKNOWN` na Fase 4 — se a disponibilidade não for
  legível na maioria das lojas, a escolha conservadora deixa o sistema sem nada a dizer,
  e passa a valer a pena distinguir "a página não declara" de "a página declara
  esgotado".
