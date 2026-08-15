# ADR-0001 — Arquitetura limpa com domínio isolado

## Estado

Aceite — 2026-08-15.

## Contexto

O sistema é pequeno em superfície (recolher preços, guardar, ler) mas tem uma regra de
negócio que não é pequena: o cálculo do preço mais baixo praticado nos 30 dias
consecutivos anteriores, tal como exigido pelo Decreto-Lei n.º 109-G/2021. Essa regra é
uma invariante de domínio, não um detalhe de relatório, e a sua correção é o produto.

Três forças puxam o desenho:

1. **A regra dura mais do que a tecnologia.** As lojas mudam de HTML todos os anos, o
   armazenamento pode mudar, a API vai mudar. A definição legal de janela de 30 dias
   não muda com nenhuma delas.
2. **A regra tem de ser testável sem infraestrutura.** Os casos que mais falham em
   implementações ingénuas — descida gradual de preço, buracos na série, produto sem
   stock — precisam de dezenas de testes rápidos. Se cada um exigir uma base de dados,
   escrevem-se menos testes do que os necessários.
3. **O projeto vai receber colaboração externa**, sobretudo adaptadores de novas lojas.
   Uma fronteira explícita torna óbvio onde um contribuidor pode mexer sem risco de
   partir a regra central.

## Alternativas consideradas

**Camada única com serviços e ORM ativo (estilo Django/script).** Mais rápida a arrancar,
menos ficheiros. Custo: a regra dos 30 dias acabaria a ser calculada em SQL ou num
serviço que já tem sessão de base de dados à mão, e testá-la exigiria infraestrutura.
Rejeitada porque torna caro exatamente o teste que mais precisa de ser barato.

**Arquitetura hexagonal sem separar `application` de `domain`.** Casos de uso a viver
junto das entidades. Menos uma camada, menos indireção. Custo: a orquestração
transacional e a idempotência da recolha diária (Fase 4) misturam-se com regras puras, e
a fronteira do que pode fazer I/O deixa de ser verificável por ferramenta. Rejeitada por
pouca margem — é a alternativa mais defensável.

**Arquitetura limpa com quatro camadas e portos no domínio.** A escolhida.

## Decisão

Quatro camadas, com a regra de dependência a apontar sempre para dentro:
`interfaces` → `infrastructure` → `application` → `domain`.

- O `domain` não importa nada de fora de si — nem SQLAlchemy, nem httpx, nem pydantic.
- Os portos (`ProductRepository`, `PriceRepository`, `StoreScraper`) são `Protocol`
  definidos no domínio; a `infrastructure` implementa-os.
- `pydantic` vive só nas bordas (entrada da API, parsing de payloads externos), nunca
  no domínio.

A regra é **verificada por `import-linter` em CI e em `make test`**, com contratos
declarados em `pyproject.toml`. Não depende de disciplina: um import proibido falha o
build.

## Consequências

Fica mais fácil: testar a regra dos 30 dias sem qualquer I/O; trocar o adaptador de uma
loja sem tocar em nada mais; acrescentar uma segunda loja como código isolado.

Fica mais difícil: passar um campo novo da base de dados até à API exige tocar em
mappers em vez de expor a linha diretamente. É o custo aceite, e é pago sobretudo em
CRUD trivial — que aqui é a parte menos interessante do sistema.

**O que provaria esta decisão errada:** se ao fim de três lojas os mappers imperativos e
os DTOs de fronteira representarem mais linhas do que o domínio e a aplicação somados,
sem que nenhum teste de domínio tenha apanhado um bug real, a indireção não se está a
pagar e a camada `application` deve fundir-se no `domain`.
