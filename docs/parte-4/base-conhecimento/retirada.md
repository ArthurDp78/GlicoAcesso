# Retirada no balcão

Versão: 1

<a id="balcao"></a>

## Como retirar

Consulte a reserva em **Minhas reservas** e verifique se o estado está **CONFIRMADA**. No cartão da unidade, confira o endereço, o horário e o campo **Orientações de retirada**. Siga as instruções exibidas para aquela unidade. Leve o código da reserva para que o profissional localize o pedido.

No balcão, o profissional consulta a reserva pelo código. Para registrar a entrega, o sistema exige uma reserva confirmada e uma autorização ativa. O registro é feito no painel da unidade.

<a id="acompanhar-entrega"></a>

## Conferir se a entrega foi registrada

Depois do atendimento, consulte a reserva pelo mesmo código no portal do cidadão. O estado **RETIRADA** indica que a entrega foi registrada e processada por Reservas. A atualização pode levar alguns instantes, pois o registro da entrega é comunicado entre serviços. Consulte novamente após esse intervalo se o portal ainda mostrar **CONFIRMADA**.

### Fontes

- [Consulta por código e registro no painel profissional](../../../servicos/gateway/portal/unidade.js)
- [Validação da entrega no serviço Retiradas](../../../servicos/retiradas/main.py)
- [Atualização da reserva após o evento de entrega](../../../servicos/reservas/eventos.py)
