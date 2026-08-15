# ADR-0010 — A passagem diária é um processo único agendado por fora

## Estado

Aceite — 2026-08-15.

## Contexto

A Fase 4 é o marco que interessa: até aqui havia um domínio correto e um scraper que sabe
ler uma página, mas nenhum histórico a acumular. O valor deste produto é proporcional ao
histórico acumulado, e um dia que não corre é um dia que não se recupera — em Novembro
ninguém volta atrás para observar o preço de Outubro.

Isso muda o critério de desenho. A pergunta não é qual a arquitetura de recolha mais
capaz, é qual a que começa a recolher mais cedo e falha de forma mais visível.

Três decisões precisavam de resposta: onde vive o agendamento, quando se grava, e o que
fazer quando a loja recusa.

## Decisão

**Um processo por passagem, agendado por cron ou por um temporizador do systemd.** O
comando `braunprices recolher <loja>` arranca, percorre as referências ativas dessa loja,
grava, e sai.

**Gravação em lotes ao longo da passagem**, com `batch_size` configurável (50 por
omissão), e não uma transação única no fim.

**Um bloqueio para a recolha daquela loja**, e não apenas daquela página.

**Cada passagem deixa um relato guardado** em `collection_runs` e `collection_failures`,
e o comando sai com código `2` quando a passagem merece ser investigada.

## Alternativas consideradas

### Onde vive o agendamento

**Agendador dentro da aplicação** — APScheduler, ou Celery com *beat*. Dá controlo fino,
retentativas próprias e estado partilhado entre passagens. Custa um processo residente
que tem de estar de pé para o dia acontecer, e com ele um modo de falha novo: o agendador
morreu em silêncio há três dias e o histórico desses dias não existe. Ou seja, acrescenta
uma peça frágil precisamente sobre a coisa que não se recupera. Para uma passagem por dia
e por loja, é maquinaria a mais.

**Um serviço residente com um ciclo próprio** — a mesma objeção, com menos biblioteca a
suportá-la.

**Cron ou systemd** — o agendador já existe, já é supervisionado pela máquina, já sabe
repetir, e já sabe avisar quando o comando sai com código diferente de zero. O
`Persistent=true` do systemd recupera a passagem se a máquina estiver desligada à hora
marcada, que é exatamente o caso em que não se quer perder o dia.

O custo aceite: não há estado partilhado entre passagens em memória, e coordenar duas
lojas em paralelo passa a ser trabalho do agendador. Nenhum dos dois é necessário agora.

### Quando se grava

**Uma transação para a passagem toda.** Simples de raciocinar — ou entra tudo ou não
entra nada. Numa passagem de horas a milhares de páginas, segura locks durante esse
tempo, adia o histórico até ao fim, e uma interrupção a meio deita fora tudo o que já
tinha sido observado.

**Uma transação por observação.** Nada se perde, mas multiplica por mil o custo de
transação sem que isso compre coisa nenhuma: cada observação já é um facto independente.

**Lotes.** Como a escrita é idempotente por observação, um lote gravado a meio de uma
passagem que depois falha continua a ser exatamente aquilo que se quer ter. O custo
aceite é que uma passagem interrompida deixa o dia meio recolhido — e a resposta a isso
é repetir a passagem, que é seguro por ser idempotente.

O relato, esse, é gravado numa transação própria. Partilhar a dos lotes faria com que uma
falha a gravar observações levasse consigo o registo de que essa falha aconteceu.

### Perante um bloqueio

**Continuar e contar a falha**, como se faz com uma página cuja marcação mudou. Recusado:
transforma um aviso num problema. Uma loja que responde 429 não está a dizer que aquela
página correu mal, está a dizer que quem está a pedir está a pedir demais.

**Parar a loja e registar.** É o que a secção 2 do documento mestre manda, e é o que está
implementado. O que foi recolhido antes do bloqueio fica gravado.

Não foi considerada nenhuma forma de voltar a tentar com outra identidade. Contornar um
bloqueio é uma decisão de negócio e legal, e não se toma dentro de um processo automático
às quatro da manhã. Ver [ADR-0006](0006-politica-de-recolha.md).

## Consequências

O sistema passa a acumular histórico com uma linha de cron. Não há painel, não há
métricas exportadas, não há alarmística — há um código de saída e uma tabela consultável
por `braunprices estado`.

Isto é deliberadamente pouco, e é o suficiente para o modo de falha que interessa. Um
scraper que rebenta grita e alguém repara. O que mata este projeto é o outro: a loja muda
a marcação, o recurso ao HTML sobe de 2 % para 60 %, a recolha continua verde e o
histórico envenena-se durante semanas. Por isso a taxa de recurso ao HTML é contada,
guardada, e sai com código `2` acima de 10 % — limiar deliberadamente sensível, porque
investigar uma passagem que afinal estava bem custa meia hora e não investigar uma que
estava mal custa semanas de histórico que não se recuperam.

## Como se prova que isto está errado

- Se uma passagem a milhares de páginas mostrar que o custo de transação por lote domina
  o tempo total, o `batch_size` sobe — é configuração, não desenho.
- Se duas lojas passarem a precisar de coordenação real entre si (por exemplo, um limite
  global de pedidos), o agendamento por fora deixa de chegar e volta a discussão do
  processo residente.
- Se o código `2` disparar tantas vezes que deixe de ser lido, o limiar está mal
  calibrado — e um limiar que ninguém lê não protege nada.
- Se aparecerem passagens com o relato gravado e observações em falta, ou o contrário, a
  separação de transações está errada e há um teste a escrever antes da correção.
