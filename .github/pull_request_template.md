# O que muda e porquê

<!-- Uma frase sobre o problema. Uma frase sobre a solução. -->

Fecha #

## Decisão

<!-- Se houve uma escolha de desenho: alternativas reais consideradas, a escolhida,
     e o custo aceite. Se a decisão for estrutural, é ADR em docs/adr/, não é este campo. -->

## Checklist

Recolha de dados (aplicável a PRs que toquem em `infrastructure/scraping`):

- [ ] O `robots.txt` é respeitado em runtime, não apenas na implementação
- [ ] O user-agent é o do projeto, identificável, com URL de contacto
- [ ] O rate limit por domínio é explícito e conservador, com backoff exponencial
- [ ] Bloqueios (403, 429, captcha) param e registam — nada aqui contorna bloqueio
- [ ] Nenhum dado pessoal é recolhido ou persistido
- [ ] Nenhum seletor foi escrito de memória: todos derivam de fixture de HTML real

Código:

- [ ] `make lint` e `make typecheck` limpos, sem warnings
- [ ] `make test` verde
- [ ] Dinheiro usa `Decimal`, nunca `float`
- [ ] Nenhum código comentado, nenhum `TODO` sem issue linkada
- [ ] Se corrige um bug: inclui o teste que falhava antes da correção
- [ ] Nenhum segredo no diff
- [ ] Observações de preço continuam append-only (nada faz `UPDATE` nem `DELETE`)
- [ ] A linguagem visível ao utilizador é descritiva, nunca valorativa
