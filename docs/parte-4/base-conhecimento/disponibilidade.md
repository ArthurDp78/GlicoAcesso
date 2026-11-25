# Disponibilidade por unidade

Versão: 1

<a id="consulta"></a>

## Consultar um item

No portal do cidadão, abra **Consultar disponibilidade**, selecione um medicamento ou insumo do catálogo e clique em **Consultar**. A lista **Unidades participantes** mostra as unidades com informação de estoque para o item. A consulta ao catálogo e à disponibilidade é aberta. O token do cidadão é usado nas ações de reserva.

Em cada unidade, confira o endereço, o horário, as orientações de retirada e o campo **Disponibilidade atualizada em**. Esse campo indica quando a projeção de estoque foi atualizada. Consulte novamente se quiser uma leitura mais recente.

<a id="reserva-permitida"></a>

## Identificar onde solicitar

O botão **Solicitar reserva** aparece quando o cartão do item indica **Disponível** e **Reserva pela unidade — Permitida**. Um item pode ter saldo e, mesmo assim, a unidade pode não permitir reservas pelo portal. O indicador **Disponível** mostra que havia saldo positivo na leitura consultada. A confirmação depende da análise da unidade e da alocação efetiva.

Se o portal disser que nenhuma unidade informou disponibilidade para o item, a busca veio sem registros. Se mostrar que não foi possível consultar, a consulta falhou e pode ser repetida.

### Fontes

- [Tela de consulta do cidadão](../../../servicos/gateway/portal/portal.js)
- [Agregação de disponibilidade no BFF Cidadão](../../../servicos/bff_cidadao/main.py)
