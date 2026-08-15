# Operação da recolha diária

O valor deste sistema é o histórico acumulado. Um dia que não corre é um dia que não se
recupera: em Novembro, ninguém consegue voltar atrás e observar o preço de Outubro. Por
isso este documento trata a passagem diária como aquilo que ela é — o serviço — e não
como um script auxiliar.

## O modelo de execução

Um processo por passagem: arranca, percorre as referências ativas de uma loja, grava, e
sai. Não há daemon, não há agendador interno, não há processo residente.

A alternativa seria um agendador dentro da aplicação (APScheduler, Celery beat). Foi
recusada porque acrescenta um processo que tem de estar de pé para o dia acontecer, e
com ele uma classe inteira de falhas — o agendador morreu em silêncio há três dias e
ninguém deu por isso — precisamente sobre a coisa que não se recupera. O cron e o
systemd, esses, já existem, já são supervisionados, e já sabem repetir. Ver
[ADR-0006](adr/0006-politica-de-recolha.md) para a política de recolha em si.

## Configuração

Tudo por ambiente, com o prefixo `BRAUNPRICES_`. O `.env.example` mostra a forma; o
`.env` está no `.gitignore` e nunca entra no repositório.

| Variável | Para que serve |
|---|---|
| `BRAUNPRICES_DATABASE_URL` | Ligação ao PostgreSQL. |
| `BRAUNPRICES_USER_AGENT` | Identificação nos pedidos. Recusada se fingir ser browser ou não trouxer URL de contacto. |
| `BRAUNPRICES_REQUESTS_PER_SECOND` | Ritmo máximo por domínio. O `Crawl-delay` da loja prevalece quando é mais lento. |
| `BRAUNPRICES_REQUEST_TIMEOUT_SECONDS` | Quanto tempo se espera por uma página. |
| `BRAUNPRICES_LOG_LEVEL` / `BRAUNPRICES_LOG_FORMAT` | `json` em produção, `console` em local. |

## Preparar uma loja

```bash
braunprices lojas registar worten --nome Worten --dominio www.worten.pt \
    --pedidos-por-segundo 0.5

braunprices referencias adicionar worten \
    https://www.worten.pt/produtos/exemplo-5513302 \
    --referencia 5513302 --nome "Tinteiro HP 971" --ean 0886112877347
```

Uma referência com EAN já conhecido é ligada ao produto que existe, em vez de criar
outro — é assim que o histórico da mesma coisa em duas lojas fica comparável.

## Correr uma passagem

```bash
braunprices recolher worten
braunprices recolher worten --limite 20   # útil na primeira vez numa loja nova
```

A passagem é idempotente: correr duas vezes no mesmo dia não duplica nem corrompe. A
garantia está na chave natural do facto na base de dados, não na memória do processo —
o que significa que repetir uma passagem interrompida a meio é seguro e é o
procedimento correto.

### Códigos de saída

| Código | O que aconteceu | O que fazer |
|---|---|---|
| `0` | Passagem limpa. | Nada. |
| `1` | Erro de configuração: loja por registar, base inacessível. | Corrigir e repetir. |
| `2` | A passagem correu, mas merece ser investigada. | Ver abaixo. |

O código `2` é o que impede uma degradação silenciosa de passar despercebida. Sai com
`2` quando a loja recusou o acesso, quando a taxa de sucesso ficou abaixo de 95 %, ou
quando mais de 10 % das observações vieram do recurso ao HTML em vez do JSON-LD. Nos
três casos a passagem gravou o que conseguiu — o código não desfaz nada, apenas
garante que o agendador dá por isso sem ninguém ler o output.

**O que foi recolhido antes do problema fica gravado.** Um bloqueio a meio do catálogo
não deita fora as observações das páginas anteriores.

## Agendar

### cron

```cron
# Recolha diária às 04:12, fora das horas de ponta da loja. O minuto não é redondo de
# propósito: às 04:00 em ponto batem à porta todos os cron do mundo.
12 4 * * * cd /opt/braunprices && /opt/braunprices/.venv/bin/braunprices recolher worten >> /var/log/braunprices/worten.log 2>&1
```

O cron manda o output por email quando o comando sai com código diferente de zero — é
por aí que o código `2` chega a alguém.

### systemd

Preferível quando a máquina já usa systemd: dá registo estruturado no journal, limites
de recursos, e um `OnFailure=` que pode disparar uma notificação.

`/etc/systemd/system/braunprices-worten.service`:

```ini
[Unit]
Description=Recolha diária de preços na Worten
After=network-online.target

[Service]
Type=oneshot
User=braunprices
WorkingDirectory=/opt/braunprices
EnvironmentFile=/etc/braunprices/env
ExecStart=/opt/braunprices/.venv/bin/braunprices recolher worten
TimeoutStartSec=6h
# Sem `SuccessExitStatus`, só o código 0 conta como sucesso — que é o que se quer: uma
# passagem que merece investigação (código 2) aparece em `systemctl --failed` e dispara
# o `OnFailure=` se houver um.
```

`/etc/systemd/system/braunprices-worten.timer`:

```ini
[Unit]
Description=Passagem diária à Worten

[Timer]
OnCalendar=*-*-* 04:12:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
```

`Persistent=true` recupera a passagem se a máquina estiver desligada à hora marcada —
que é exatamente o caso em que não se quer perder o dia. `RandomizedDelaySec` espalha o
arranque em vez de bater à porta da loja sempre no mesmo segundo.

```bash
systemctl enable --now braunprices-worten.timer
systemctl list-timers braunprices-\*
```

## Ver como correu

```bash
braunprices estado worten            # últimas 5 passagens
braunprices estado worten --passagens 30
```

Cada passagem fica guardada em `collection_runs`, com as falhas classificadas em
`collection_failures`. Ficam guardadas, e não apenas registadas num log, porque uma
degradação silenciosa reconhece-se ao comparar hoje com a semana passada — e isso exige
que a semana passada ainda exista em algum lado consultável.

Os números que interessam ler:

- **taxa de sucesso** — quantas tentativas produziram observação;
- **recurso ao HTML** — quantas observações não vieram do JSON-LD. É este que denuncia
  uma loja a mudar de marcação sem deixar de dar preços, o modo de falha mais caro,
  porque continua verde enquanto envenena o histórico;
- **falhas por motivo** — `markup_missing` em massa é manutenção do adaptador;
  `blocked` é outra conversa.

## A API de leitura

```bash
braunprices servir                      # 127.0.0.1:8000, documentação em /docs
braunprices servir --host 0.0.0.0 --porta 8000
```

O host por omissão é local de propósito: expor uma porta à rede é uma decisão de
operação, tomada por escrito num ficheiro de serviço, e não por omissão de um comando.
Em produção corre atrás de um proxy, que trata de TLS e de servir a cache.

`/saude` responde com a versão e com o estado da base de dados, e é por aí que a
supervisão pergunta se o processo serve para alguma coisa. Um `200` com
`"base_de_dados": false` significa que o processo está de pé e não consegue responder a
nada de útil — trate-se como indisponível.

As respostas trazem `Cache-Control: public, max-age=300` e `Last-Modified` com o instante
do facto mais recente que contêm. Um proxy à frente reduz a carga sem que nada disso
seja código deste projeto.

### systemd

`/etc/systemd/system/braunprices-api.service`:

```ini
[Unit]
Description=API pública do BraunPrices
After=network-online.target

[Service]
User=braunprices
WorkingDirectory=/opt/braunprices
EnvironmentFile=/etc/braunprices/env
ExecStart=/opt/braunprices/.venv/bin/braunprices servir --host 127.0.0.1 --porta 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

O contrato OpenAPI sai com `make openapi` e é o que qualquer cliente deve gerar a partir
daqui — nunca escrito à mão do outro lado.

## Quando a loja diz que não

Perante `403`, `429`, `451` ou uma parede de captcha, a passagem **para nessa loja** e
regista. Não há rotação de user-agents, de endereços, nem qualquer outra forma de
voltar a bater à porta com outra cara.

Isto não é uma limitação técnica a contornar: contornar um bloqueio é uma decisão de
negócio e legal, e não se toma dentro de um processo automático às quatro da manhã. O
procedimento é:

1. Confirmar que o `robots.txt` da loja não mudou.
2. Confirmar que o ritmo configurado não subiu.
3. Se a loja quer que se pare, para-se — e a loja sai da recolha. Ver
   [`SECURITY.md`](../SECURITY.md), que é a via pelo lado de quem é responsável pelo
   site.

## Migrações

```bash
uv run alembic upgrade head
```

Aplicam-se antes de a primeira passagem correr numa base nova. Os testes de integração
correm sobre as migrações — e não sobre `metadata.create_all` — precisamente para que
este passo esteja coberto pelo que a suite verifica.
