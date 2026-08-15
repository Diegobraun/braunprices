# ADR-0011 — A API pública: leitura anónima, paginação por posição, contrato verificado

## Estado

Aceite — 2026-08-15.

## Contexto

Com histórico a acumular, faltava a forma de o ler. A API é onde as afirmações deste
sistema deixam de ser privadas: cada resposta é uma afirmação sobre uma empresa
identificada, publicada para quem a quiser ler.

Isso muda o que está em jogo em três decisões que noutro projeto seriam rotina — como se
serializa dinheiro, como se pagina, e quem pode ler.

## Decisão

**Leitura anónima, sem autenticação.** Os dados são públicos por natureza: foram lidos de
páginas públicas. Pôr uma chave à frente deles serviria para saber quem lê, e isso é
recolher dados de pessoas — exatamente o que este sistema não faz.

**Dinheiro viaja como texto decimal, com a moeda ao lado**: `{"montante": "59.99",
"moeda": "EUR"}`.

**Paginação por posição** (o último facto lido), com cursor opaco, e não por
deslocamento.

**Superfícies separadas desde já.** A pública vive em `interfaces/api/public/`, com
prefixo `/api/v1` e sem nenhuma rota de escrita. A de administração terá o seu prefixo,
as suas dependências de autenticação, e a sua política de CORS.

**O contrato é gerado a partir do código e verificado contra o serviço** por
schemathesis, que gera pedidos a partir do OpenAPI publicado e valida as respostas.

## Alternativas consideradas

### Serialização de dinheiro

**Número JSON** (`59.99`). É o que quase toda a gente faz, e é o que quase toda a gente
lê como `double`. Um cêntimo perdido num arredondamento aqui não é um erro de
apresentação: é um facto errado publicado sobre uma empresa identificada, exatamente no
número que a lei manda verificar. Recusado.

**Inteiro de cêntimos** (`5999`). Correto e à prova de arredondamento, mas obriga quem lê
a saber quantas casas a moeda tem antes de mostrar seja o que for, e transforma cada
cliente distraído num erro de fator 100.

**Texto decimal com moeda ao lado.** Preserva a escala tal como foi observada — `59.90` e
`59.9` são o mesmo número e não são o mesmo preço praticado — e é impossível de ler mal
por acidente. O custo aceite é que quem quiser fazer contas tem de converter, o que é o
comportamento correto de qualquer forma.

### Paginação

**Deslocamento** (`OFFSET`/`limit`). É o mais simples de escrever e o mais fácil de
explicar. Numa série a que se acrescentam factos, também é uma forma discreta de mentir:
entre a página 1 e a página 2 entram observações, e o leitor recebe repetições ou saltos
sem nada lhe dizer que isso aconteceu. Num sistema cujo produto é a fidelidade do
histórico, isto é a falha errada para se ter.

**Página por data** (`?desde=&ate=`). Continua disponível como filtro, e resolve o caso
comum. Não chega como paginação: um dia pode ter várias observações, e nada garante que
um intervalo caiba numa página.

**Posição do último facto lido.** O histórico é append-only e ordenado pelo instante
observado, o que torna esta posição estável para sempre. A página seguinte é sempre "o
que vem depois disto", e a consulta usa o índice `(listing_id, observed_at)` em vez de
contar linhas a saltar. O custo aceite: não há "ir à página 7", e o cursor tem de incluir
preço e disponibilidade para desempatar duas observações no mesmo instante.

O cursor é opaco — base64, que não é segurança nenhuma, apenas sinalização de que aquilo
não é para ser lido nem construído à mão. Um cursor ilegível dá 400, e nunca a primeira
página em silêncio: devolver "aqui está" a quem pediu mal fá-lo recomeçar o histórico sem
perceber porquê.

### Cache

**Sem cache.** Cada leitura bate na base de dados. Para um histórico que muda uma vez por
dia, é gastar a base de dados a responder a perguntas cuja resposta já foi dada.

**Cache em memória do processo, ou Redis.** Mais peças, mais uma coisa que pode servir
dados velhos, e nenhuma delas justificada pelo tráfego que este projeto tem.

**Cabeçalhos HTTP** (`Cache-Control: public, max-age=300`, `Last-Modified` com o instante
do facto mais recente da resposta). A cache passa a ser trabalho de quem já a sabe fazer
— o browser, o CDN, o proxy — e não código para manter aqui. Cinco minutos é curto face
ao ritmo de recolha e curto o suficiente para que uma correção apareça depressa.

### Verificação do contrato

**OpenAPI escrito à mão.** Diverge do código na semana seguinte e ninguém dá por isso até
um cliente rebentar.

**Gerado, e verificado só por testes escritos à mão.** Melhor, mas os testes escritos à
mão testam os casos em que se pensou.

**Gerado e verificado por schemathesis**, que lê o contrato publicado e gera pedidos a
partir dele. Apanha o que ninguém escreveria: o campo obrigatório que vem a nulo, o 500
onde devia estar um 400, o código de estado não documentado.

A lista de estados aceites inclui `400`, porque há pedidos que respeitam o contrato e
ainda assim são recusados: o esquema diz que `ean` é texto, mas o dígito de controlo não
cabe num tipo. Alargar essa lista é uma decisão consciente e está comentada no teste — o
que continua garantido é o essencial: nenhum `5xx`, e cada resposta a caber no esquema
prometido.

## Consequências

A API não sabe calcular nada. A regra dos 30 dias vive no domínio e a API traduz a
resposta — incluindo **a base que a produziu**, para que o número possa ser justificado e
não apenas dado. Quem construir um painel sobre isto não deve recalcular a regra do outro
lado.

A linguagem publicada é descritiva em todos os campos, e há um teste que recusa qualquer
campo cujo nome qualifique conduta. O sistema afirma que um preço foi observado num dia,
com o URL de onde foi lido; não afirma que alguma loja cumpriu ou deixou de cumprir seja
o que for, porque para isso seria preciso saber o que a loja anunciou — e isso não é
observado.

## Como se prova que isto está errado

- Se aparecer um cliente que precise de saltar para o meio do histórico, a paginação por
  posição deixa de chegar e o filtro por data tem de crescer.
- Se o tráfego crescer ao ponto de os cabeçalhos de cache não bastarem, a discussão do
  Redis volta — com números, e não por antecipação.
- Se o `400` do schemathesis começar a esconder erros reais, a lista de estados aceites
  está larga demais e deve passar a ser por operação.
- Se uma rota de escrita alguma vez aparecer sob `/api/v1`, o teste que exige que a
  superfície pública só tenha `GET` falha — e é isso que ele existe para fazer.
