# ADR-0004 — JSON-LD como fonte primária, HTML como recurso

## Estado

Aceite — 2026-08-15.

## Contexto

Um preço numa página de loja está tipicamente em três sítios ao mesmo tempo: no bloco
`schema.org/Product` em JSON-LD, em microdados espalhados pelo HTML, e no texto visível
formatado para pessoas.

As três fontes não são igualmente estáveis. O JSON-LD existe para ser lido por máquinas
— é o que alimenta os resultados enriquecidos dos motores de busca — e é a mesma
estrutura em todo o catálogo. O HTML de apresentação muda com cada redesenho.

E não são igualmente inequívocas. A página real que serviu de base a este adaptador traz
**três** elementos `meta[itemprop="price"]`: o preço da loja, repetido na barra fixa, e o
preço de um **vendedor terceiro** dentro de `.product-other-offers__price`. O JSON-LD
declara uma oferta só — a da loja.

Isto define o problema. Ler o texto visível ou os microdados sem cuidado registaria, num
dia qualquer, o preço de um vendedor terceiro como se fosse o da loja. Nada rebentaria.
O número entraria no histórico e ficaria lá para sempre, a servir de base a uma
afirmação pública sobre uma empresa identificada.

## Alternativas consideradas

**Só JSON-LD, sem recurso.** O mais previsível. Custo: no dia em que a loja mexer na
marcação, a recolha para por completo, e perdem-se dias de histórico enquanto alguém
repara.

**Extração por seletores de CSS sobre o texto visível.** É o que a maioria dos scrapers
faz. Custo: parte com cada redesenho, e obriga a analisar preços formatados para pessoas
— com vírgula decimal, ponto de milhares e espaços não separáveis — quando existe uma
fonte com o número já normalizado ao lado.

**JSON-LD primeiro, microdados como recurso, com a ambiguidade a resultar em recusa.**
A escolhida.

## Decisão

1. A fonte primária é o bloco `schema.org/Product` em JSON-LD. Procura-se também dentro
   de `@graph` e de listas, e aceitam-se as formas de `@type` que aparecem em lojas
   reais.
2. Quando o JSON-LD falta ou não serve, tenta-se os microdados — e **regista-se sempre**
   que isso aconteceu, com `ExtractionSource.HTML_FALLBACK` na observação. Sem esse
   registo, uma loja podia passar de uma fonte para a outra e continuar a devolver
   preços, e ninguém daria por isso.
3. O recurso **descarta as ofertas de vendedores terceiros** e, se ainda assim restar
   mais do que um preço próprio distinto, **recusa em vez de escolher**. Uma falha
   visível é recuperável; um número errado no histórico não é.
4. O texto visível não é usado como fonte de preço. `Money.from_pt_string` existe e está
   testado para o dia em que uma loja não deixe alternativa, mas nenhum adaptador o usa
   hoje.

Nada do que vem da página é tratado como instrução. É dado a analisar, e há um teste que
o afirma com um bloco JSON-LD cujo `name` contém texto a fingir-se de comando.

## Consequências

Fica mais fácil: extrair preço, disponibilidade e código de barras de uma vez, já
normalizados; acrescentar uma loja nova, porque a maioria publica JSON-LD e o extrator é
comum; medir a degradação, porque a fonte de cada observação fica registada.

Fica mais difícil: recolher de lojas que não publiquem marcação nenhuma. Essas exigem um
adaptador com seletores próprios, derivados de HTML real capturado, e é trabalho que se
faz caso a caso e não por antecipação.

**O que provaria esta decisão errada:** se a fração de observações que vêm do recurso
subir de forma consistente, o JSON-LD deixou de ser a fonte fiável que se assumiu. Se
uma loja passar a declarar no JSON-LD um preço diferente do que mostra ao consumidor, a
fonte primária deixa de descrever a realidade e a ordem inverte-se — mas isso seria, por
si só, um facto sobre essa loja que valeria a pena publicar.
