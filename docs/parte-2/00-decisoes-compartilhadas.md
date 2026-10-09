# GlicoAcesso — Decisões Arquiteturais Compartilhadas

## 1. Objetivo
Estabelecer as decisões arquiteturais utilizadas
pelos quatro integrantes na Parte 2.

## 2. Escopo
Sistema de consulta de disponibilidade, solicitação
de reservas e acompanhamento da retirada de
medicamentos e insumos para diabetes nas unidades
públicas participantes.

## 3. Microsserviços
- Unidades
- Estoque
- Reservas
- Retiradas

## 4. Clientes
- Portal do Cidadão
- Painel da Unidade de Saúde

## 5. Comunicação
- Clientes acessam o API Gateway.
- Gateway encaminha requisições aos BFFs.
- BFFs consultam os microsserviços de domínio.
- Reservas coordena a SAGA.
- Eventos assíncronos serão utilizados no CQRS.

## 6. Persistência
- Cada microsserviço possui banco independente.
- Um serviço não acessa diretamente o banco de outro.

## 7. Fluxo principal
1. Cidadão solicita reserva.
2. Unidade analisa a solicitação.
3. Funcionário solicita confirmação.
4. Reservas inicia a SAGA.
5. Estoque realiza alocação.
6. Retiradas prepara autorização.
7. Reservas finaliza confirmação.
8. Posteriormente, a retirada física é registrada.

## 8. Identificadores compartilhados
- unidadeId
- itemId
- reservaId
- retiradaId

## 9. Estados da reserva
- SOLICITADA
- EM_CONFIRMACAO
- CONFIRMADA
- REJEITADA
- FALHA_CONFIRMACAO
- CANCELADA
- RETIRADA

## 10. Decisões pendentes
- Contratos REST: Pessoa 2.
- Compensações da SAGA: Pessoa 3.
- Persistência e eventos: Pessoa 4.s