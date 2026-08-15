# ADR-0006 — Política de recolha: robots.txt, ritmo, e nunca contornar bloqueios

## Estado

Aceite — 2026-08-15. É a decisão que separa este projeto de um scraper qualquer, e a que
menos margem tem para ser revista.

## Contexto

Este sistema visita, todos os dias, páginas de empresas identificadas, e publica
afirmações baseadas no que lá encontra. Faz isso sem pedir autorização, porque os dados
são públicos e a lei que motiva o projeto é de interesse público.

Isso só é defensável se a recolha for irrepreensível. Uma loja que descubra que está a
ser lida deve poder verificar, em poucos minutos, que o projeto se identificou, respeitou
as regras publicadas, não lhe causou carga, e parou quando foi mandado parar.

Há ainda um ponto que não é de cortesia mas de risco: contornar um bloqueio técnico pode
deixar de ser uma questão de boas maneiras e passar a ser uma questão de acesso não
autorizado. Não é uma decisão que caiba num adaptador de loja.

## Alternativas consideradas

**Recolher com o cuidado técnico habitual mas sem regras explícitas.** Funciona até ao
dia em que alguém, com boas intenções e um prazo, acrescenta um user-agent de browser
para desbloquear uma loja. A regra que não está escrita não existe.

**Pedir autorização a cada loja antes de recolher.** O mais defensável de todos, e
impraticável: uma resposta negativa por omissão bloquearia o projeto inteiro, e os dados
são públicos.

**Regras explícitas, verificadas em runtime e por teste.** A escolhida.

## Decisão

**Identificação.** O user-agent é `BraunPricesBot/<versão> (+<URL do projeto>)`, com
contacto acessível. É o mesmo com que se lê o `robots.txt` e com que se pede a página —
perguntar com um nome e pedir com outro tornaria a resposta irrelevante. **Nunca se
finge ser um browser.**

**`robots.txt`, em runtime.** Verificado a cada URL, com as regras em cache por uma hora.
Ler o ficheiro uma vez durante a implementação não é respeitá-lo: é respeitá-lo no dia em
que se leu. Se o `robots.txt` não puder ser obtido ou lido, **o domínio fica interdito**.
A única ausência que se lê como permissão é o 404, porque é a que o próprio protocolo
define. Um `Crawl-delay` declarado pela loja prevalece sobre o ritmo configurado, mesmo
que seja mais lento: quem recebe os pedidos é que sabe o que aguenta.

**Ritmo.** Conservador e por domínio — 0,5 pedidos por segundo e uma ligação de cada vez,
por omissão — com recuo exponencial nas falhas passageiras. Os limites são validados no
domínio e também por *check constraint* na base de dados, para que nem uma inserção que
contorne a aplicação consiga configurar uma loja para ser martelada.

**Bloqueios.** Perante 401, 403, 429, 451 ou uma página de verificação servida com 200,
**para-se e regista-se**. Sem repetições, sem rotação de agentes, sem rotação de
endereços, sem resolver desafios. A falha é classificada como `BLOCKED` e marca a loja
inteira, não a página: quem está a travar está a travar o cliente.

**Âmbito.** Apenas dados públicos de produto: preço, disponibilidade, identificador,
nome. Nenhum dado pessoal, nunca. Ver ADR-0002.

**Conteúdo como dado.** O HTML recolhido é analisado, nunca seguido. Nada do que vem de
uma página é executado nem usado para construir caminhos ou consultas.

## Como se verifica que isto é verdade

Não por leitura do código. Os testes cobrem: um URL proibido nunca chega a ser pedido; um
`robots.txt` ilegível interdita o domínio; um `Crawl-delay` da loja atrasa a recolha; os
pedidos ao mesmo domínio são espaçados e os de domínios diferentes não; cada um dos
quatro códigos de bloqueio produz **uma só** tentativa; o user-agent nunca contém
`Mozilla` nem `Chrome`.

As quatro decisões mais importantes foram verificadas por falsificação — desligadas uma a
uma, com os testes a falhar em todas.

## Consequências

Fica mais fácil: responder a uma loja que pergunte o que se está a fazer; aceitar um
pedido de exclusão sem discussão, como o `SECURITY.md` promete; dormir descansado.

Fica mais difícil: recolher de lojas atrás de proteção anti-bot. A Fnac.pt, por exemplo,
respondeu 403 ao próprio `robots.txt` durante a escolha da primeira loja, e foi
descartada em vez de contornada. Perde-se cobertura, e é o custo aceite.

**O que reverteria esta decisão:** nada de técnico. Uma autorização escrita de uma loja
pode alargar o que se recolhe **nessa** loja, e passaria a constar aqui. A regra de não
contornar bloqueios não se revê por conveniência de engenharia.
