# Fixtures de HTML real

Cada ficheiro é uma captura **real** de uma página pública de produto, com a loja e a
data de captura no nome. Nenhum seletor deste projeto foi escrito de memória: todos
saíram destes ficheiros.

Estão comprimidos com `gzip` porque uma página de loja moderna ronda 1 MB e duas delas
por loja tornariam o repositório desagradável de clonar. O conteúdo é o HTML original,
byte a byte — descomprimir devolve exatamente o que a loja serviu. Os testes leem-nos
com `gzip.open`, e nunca fazem rede.

| Ficheiro | Origem | Captado em |
|---|---|---|
| `worten-tinteiro-hp-971-5513302-2026-08-15.html.gz` | `https://www.worten.pt/produtos/tinteiro-hp-971-amarelo-cn624ae-5513302` | 2026-08-15 |
| `worten-toner-hp-651a-5844239-2026-08-15.html.gz` | `https://www.worten.pt/produtos/toner-hp-651a-preto-ce340a-5844239` | 2026-08-15 |
| `worten-robots-2026-08-15.txt` | `https://www.worten.pt/robots.txt` | 2026-08-15 |

## Como foram obtidas

Com o user-agent do projeto, um pedido de cada vez e pausa entre pedidos, depois de
confirmar no `robots.txt` que `/produtos/` é permitido. São duas páginas: o que é
preciso para derivar e testar os seletores, e nada mais.

## Como acrescentar uma nova

1. Confirma primeiro o `robots.txt` da loja, e guarda-o também.
2. Captura com o user-agent do projeto, sem paralelismo.
3. Comprime com `gzip -9` e nomeia com `loja-descricao-referencia-AAAA-MM-DD.html.gz`.
4. Acrescenta a linha à tabela acima com o URL de origem.

Se a loja responder 403, 429 ou com uma página de verificação, **para aí**. Essa é a
resposta, e a resposta é não.
