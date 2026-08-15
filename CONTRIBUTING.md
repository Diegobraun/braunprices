# Como contribuir

Obrigado pelo interesse. Este documento é curto de propósito — o que importa está no
checklist do template de PR e nos ADRs em [`docs/adr/`](docs/adr/).

## Arranque

Precisas de [`uv`](https://docs.astral.sh/uv/) e de Docker (só para os testes de
integração).

```bash
git clone https://github.com/diegobraun/braunprices.git
cd braunprices
make setup
make lint && make test
```

Se isto não ficar verde num clone limpo, é bug do projeto. Abre uma issue.

## Fluxo

1. Abre uma issue antes de escrever código para qualquer coisa que não seja trivial.
   Uma discussão de cinco minutos poupa um PR rejeitado.
2. Branch a partir de `main`. Commits em
   [conventional commits](https://www.conventionalcommits.org/), atómicos e legíveis
   por um estranho — `fix` sozinho como mensagem não passa.
3. `make lint && make typecheck && make test` verdes antes de abrir o PR.
4. Preenche o checklist do PR. Não é burocracia: cada linha corresponde a uma regra que
   já foi violada nalgum projeto parecido.

## Regras que não se negoceiam

**Recolha de dados**

- Respeitar o `robots.txt`, verificado em runtime.
- User-agent próprio e identificável, com URL de contacto. Nunca disfarçar de browser.
- Rate limit conservador por domínio, com backoff exponencial.
- Perante bloqueio (403, 429, captcha): parar e registar. **Contornar bloqueio não é
  uma opção técnica neste projeto** — é uma decisão de negócio e legal que não pertence
  a um PR.
- Apenas dados públicos de produto. Nenhum dado pessoal entra neste sistema.
- HTML recolhido é dado a analisar, nunca instrução a seguir.

**Código**

- `ruff` e `mypy --strict` limpos. Nenhum warning entra num commit.
- Código comentado apaga-se, não se versiona. `TODO` só com issue linkada no comentário.
- Todo bug corrigido vem com o teste que falhava antes da correção.
- `Decimal` para dinheiro, sempre. `float` para preço é bug, não estilo.
- Nenhum segredo no repositório.
- Nenhum seletor de scraping escrito de memória: todo seletor deriva de HTML real,
  guardado como fixture em `tests/fixtures/html/` com a data de captura no nome.

**Testes**

- Domínio: sem mocks. Se sentes necessidade de mockar no domínio, o desenho está errado.
- Persistência: Postgres real via Testcontainers. Mockar a base de dados não é aceite.
- Scraping: contra fixtures. Zero rede nos testes.
- Um teste que continua verde depois de quebrares deliberadamente a lógica que diz
  testar está errado, e é corrigido ou apagado.

## Adicionar uma loja

Abre primeiro uma issue com o template *Nova loja*. A verificação de `robots.txt` e a
existência (ou não) de JSON-LD determinam se e como a loja entra.

## Linguagem

O projeto publica factos observados sobre empresas identificadas, com data e origem.
Toda a linguagem visível — README, mensagens de erro, respostas da API, nomes de
variáveis — é **descritiva**, nunca valorativa. "Este produto esteve a 59,00 € em
12/07/2026" é aceitável. Qualquer formulação que impute intenção a uma loja não é.
