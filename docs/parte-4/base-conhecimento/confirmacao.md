# Confirmação da reserva

Versão: 1

<a id="acompanhar"></a>

## Acompanhar a decisão

Em **Minhas reservas**, informe a credencial do cidadão e o código recebido ao solicitar. Clique em **Consultar reserva** para ver o estado e a quantidade. Consulte de novo para acompanhar mudanças.

- **SOLICITADA** indica que a unidade ainda pode analisar o pedido dentro do prazo.
- **EM_CONFIRMACAO** indica que o profissional aceitou e a confirmação está em processamento. O sistema ainda precisa alocar o item no estoque e preparar a autorização de retirada.
- **CONFIRMADA** indica que o item foi alocado e a autorização foi preparada. Confira as orientações da unidade para a retirada.

<a id="sem-confirmacao"></a>

## Entender por que o pedido não confirmou

- **REJEITADA** indica que a unidade recusou a solicitação.
- **EXPIRADA** indica que o prazo de decisão terminou com o pedido ainda pendente.
- **FALHA_CONFIRMACAO** indica que a confirmação falhou após o aceite.
- **CANCELADA** indica que o cancelamento foi concluído.

Se ainda precisar do item, faça uma nova consulta de disponibilidade. Uma nova solicitação depende das condições exibidas para o item e a unidade no momento da consulta.

### Fontes

- [Fluxo e estados da reserva](../../parte-2/05-fluxo-reservas.md)
- [Orquestração da confirmação](../../../servicos/orquestrador/executor.py)
- [Consulta da reserva no portal](../../../servicos/gateway/portal/portal.js)
