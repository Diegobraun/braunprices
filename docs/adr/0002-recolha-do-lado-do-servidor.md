# ADR-0002 — Recolha do lado do servidor, e não a partir do browser dos utilizadores

## Estado

Aceite — 2026-08-15.

## Contexto

Há duas formas conhecidas de acumular um histórico de preços de retalho.

A primeira é uma extensão de browser: os utilizadores instalam-na, e quando visitam uma
página de produto a extensão envia o preço que veem. É como vários serviços deste tipo
arrancaram.

A segunda é um recolhedor do lado do servidor, que visita as páginas por sua iniciativa
e num ritmo que controla.

Três forças decidem entre as duas.

**Arranque a frio.** O valor deste produto é proporcional ao histórico acumulado, e um
dia sem coletar é um dia perdido para sempre. Uma extensão só produz dados depois de ter
utilizadores, e só tem utilizadores depois de o produto valer alguma coisa. É um ciclo
que começa com meses de zero.

**Cobertura previsível.** Uma extensão observa o que os utilizadores calham de visitar.
O histórico fica denso onde há tráfego e vazio no resto, e a janela de 30 dias de um
produto pouco visitado fica cheia de buracos — que é precisamente onde a regra legal
importa mais e onde a lacuna é mais difícil de justificar.

**RGPD.** Recolher a partir do browser de uma pessoa significa saber que aquela pessoa
visitou aquela página. Isso é dado pessoal, com tudo o que traz: base legal,
consentimento, direitos do titular, retenção, subcontratantes. Passa a ser o problema
central do projeto, e o projeto não é sobre isso.

## Alternativas consideradas

**Extensão de browser.** Volume potencialmente maior e sem custo de infraestrutura de
recolha. Custo: arranque a frio de meses, cobertura enviesada, e o RGPD no caminho
crítico.

**Modelo misto — servidor agora, extensão depois.** Adiar não é decidir: a arquitetura
de recolha ficaria refém de uma decisão de RGPD ainda por tomar.

**Recolha do lado do servidor, apenas.** A escolhida.

## Decisão

A recolha é do lado do servidor. **Nenhum dado é recolhido a partir do browser de
utilizadores**, e o sistema não processa nem armazena dados pessoais de espécie alguma:
apenas preço, disponibilidade, identificador e nome de produto, todos públicos.

Uma consequência que vale por si: como não há dados pessoais, não há RGPD a gerir. Não é
um atalho — é o resultado de uma escolha de âmbito, e o âmbito fica registado aqui para
que ninguém o alargue por distração.

## Consequências

Fica mais fácil: começar a acumular histórico já, com cobertura escolhida e não
sorteada; publicar os dados sem ter de os anonimizar; explicar o projeto a uma loja que
pergunte o que se está a fazer.

Fica mais difícil: escalar em largura. Cada loja é um adaptador a escrever e a manter, e
o ritmo conservador impõe um teto de páginas por dia. É trabalho previsível, ao
contrário do problema que se evita.

**O que reverteria esta decisão:** uma extensão só passa a fazer sentido se houver
utilizadores primeiro e se a recolha do browser não trouxer dados pessoais consigo —
o que exigiria um desenho em que a extensão envia preço e identificador de produto e
mais nada, sem identificador de sessão nem de utilizador. É um ADR à parte, para o dia
em que houver quem instale.
