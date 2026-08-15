# ADR-0007 — Licenciamento de código e de dados

## Estado

**Proposto** — aguarda confirmação do proprietário do projeto antes do primeiro
lançamento público. O `LICENSE` no repositório reflete já esta proposta.

## Contexto

O repositório é público desde o primeiro commit. Duas coisas distintas saem dele, e
têm regimes jurídicos diferentes:

1. **O código.** Direito de autor clássico. A licença determina o que terceiros podem
   fazer com ele, incluindo operar um serviço fechado em cima.
2. **Os dados recolhidos.** As observações individuais de preço são *factos* — um preço
   praticado por uma loja numa data não é obra protegida por direito de autor. Mas a
   **base de dados** que resulta de os recolher sistematicamente pode beneficiar do
   direito *sui generis* do fabricante de bases de dados (Diretiva 96/9/CE, transposta
   em Portugal pelo Decreto-Lei n.º 122/2000), quando houve investimento substancial na
   obtenção e verificação do conteúdo. Recolha diária continuada durante meses é
   precisamente esse tipo de investimento.

Aplicar a mesma licença aos dois é um erro comum: uma licença de software não é desenhada
para direitos de base de dados, e uma licença de dados não cobre código.

Há ainda uma força não jurídica: o repositório é peça de portefólio. Uma licença
demasiado restritiva reduz a probabilidade de alguém reutilizar ou contribuir; uma
demasiado permissiva permite que o histórico acumulado — que é o ativo real do projeto,
e que só existe porque se coletou todos os dias desde cedo — seja empacotado num serviço
fechado sem devolver nada.

## Alternativas consideradas

**MIT para tudo.** Alcance máximo, zero atrito para quem avalia o código. Custo: nada
impede que o serviço seja replicado como produto fechado, e não diz absolutamente nada
sobre os dados, deixando a sua reutilização num vazio que ninguém sabe interpretar.

**Apache-2.0 para tudo.** Como MIT, mais concessão explícita de patentes e proteção de
marca. Melhor higiene jurídica para um portefólio. Mesmo silêncio sobre os dados.

**AGPL-3.0 para tudo.** Fecha o buraco do serviço fechado, mas afasta contribuidores
empresariais e não é o instrumento certo para uma base de dados — aplicar copyleft de
software a factos é ambíguo e, na prática, inaplicável.

**Separar: AGPL-3.0-or-later no código, ODbL-1.0 nos dados.** A escolhida.

## Decisão

- **Código:** `AGPL-3.0-or-later`. Quem operar este sistema como serviço acessível pela
  rede disponibiliza as modificações. É a única cláusula que tem efeito real num projeto
  cujo modo natural de uso é *ser um serviço*.
- **Dados recolhidos e base de dados publicada:** `ODbL-1.0` (Open Database License),
  com atribuição e partilha nos mesmos termos. É o instrumento desenhado para o direito
  *sui generis*, e é o que a comunidade de dados abertos já reconhece.
- **Observações individuais**, citadas isoladamente (por exemplo, "este produto esteve a
  59,00 € em 12/07/2026"), são factos e não estão sujeitas a restrição. O projeto não
  reivindica exclusividade sobre factos de preço, e nada no ODbL deve ser lido nesse
  sentido.

O ficheiro `LICENSE` contém o texto da AGPL-3.0. O regime dos dados é declarado no
`README` e voltará a sê-lo no endpoint de metadados da API (Fase 5).

## Consequências

Fica mais fácil: publicar dumps do histórico sem ambiguidade sobre o que terceiros podem
fazer com eles; recusar, com base contratual e não apenas moral, que o histórico seja
absorvido por um serviço fechado.

Fica mais difícil: adoção por empresas com política interna anti-AGPL, e contribuições de
programadores empregados por essas empresas. É um custo real e aceite conscientemente,
porque o valor do projeto está no histórico acumulado, não na base de código.

**O que provaria esta decisão errada:** se contribuições concretas forem recusadas por
causa da AGPL, ou se uma parte terceira útil (uma associação de defesa do consumidor, um
regulador) não puder reutilizar os dados por causa da cláusula de partilha do ODbL, a
decisão inverte-se para Apache-2.0 no código e CC-BY-4.0 nos dados. Ambos os casos são
observáveis: aparecem numa issue ou num email, não numa métrica.
