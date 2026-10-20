# GlicoAcesso — Projeto de HATEOAS

**Etapa:** 2 — Arquitetura  
**Documento:** 05 — HATEOAS 
**Documento normativo:** [00 — Decisões arquiteturais compartilhadas](./00-decisoes-compartilhadas.md)  
**Documento complementar:** [01 — Decomposição e fronteiras dos microsserviços](./01-microsservicos.md)  
**Recurso Escolhido:** Reserva  

> Este documento detalha a implementação do padrão HATEOAS para o recurso de Reserva. As regras, estados e transições aqui descritas obedecem estritamente às definições estabelecidas no documento normativo (00) e respeitam as fronteiras definidas no documento 01.

## 1. Introdução ao HATEOAS no Recurso Reserva

O padrão HATEOAS (Hypermedia as the Engine of Application State) foi aplicado ao recurso **Reserva** do microsserviço de Reservas. O objetivo é fornecer ao cliente (através dos BFFs) não apenas os dados da solicitação, mas também os links para as transições de estado permitidas no momento da consulta.

Desta forma, os clientes frontend não precisam de embutir regras de negócio complexas (ex: "se o estado for X, mostra o botão Y"). O cliente apenas verifica a presença do link no objeto `_links` da resposta JSON e renderiza a ação correspondente.

## 2. Mapeamento de Links por Estado de Negócio

Os links disponíveis dependem do estado atual da reserva e do ator que faz a consulta (Cidadão ou Profissional da Unidade), respeitando as regras estabelecidas no contrato base.

### 2.1. Estado: `SOLICITADA`
A solicitação foi criada, mas a unidade ainda não tomou uma decisão.
*   **Links para o Cidadão:**
    *   `self`: Link para recarregar a reserva.
    *   `cancelar`: Ação para o cidadão cancelar o próprio pedido.
*   **Links para o Profissional da Unidade:**
    *   `self`: Link para recarregar a reserva.
    *   `aceitar`: Ação para dar início à SAGA de confirmação.
    *   `rejeitar`: Ação para rejeitar o pedido.
    *   `cancelar`: Ação para cancelar (exige o envio de justificativa no corpo da requisição).

### 2.2. Estado: `EM_CONFIRMACAO`
A unidade aceitou o pedido e a SAGA está em andamento.
*   **Links (Comuns):**
    *   `self`: Link para recarregar a reserva.
    *   `cancelar`: Interrompe a SAGA e inicia a compensação.

### 2.3. Estado: `CONFIRMADA`
A alocação de estoque e a preparação da autorização de retirada foram concluídas com sucesso.

O link de consulta da autorização não substitui a validação da entrega: ao registrar a retirada, Retiradas consulta o estado canônico de Reservas e exige `CONFIRMADA`, além de revalidar a autorização local. Falha na consulta impede a entrega naquele momento, conforme o documento 00, seção 9.8.

*   **Links para o Cidadão:**
    *   `self`: Link para recarregar a reserva.
    *   `cancelar`: Inicia o cancelamento e a reversão de efeitos.
*   **Links para o Profissional da Unidade:**
    *   `self`: Link para recarregar a reserva.
    *   `autorizacao-retirada`: Link (GET) para consultar os dados da autorização no microsserviço de Retiradas e proceder com o registo de entrega no balcão.
    *   `cancelar`: Inicia o cancelamento (exige justificativa).

### 2.4. Estados em Transição e Terminais
Para os estados `CANCELAMENTO_EM_ANDAMENTO`, `RETIRADA`, `REJEITADA`, `CANCELADA`, `EXPIRADA` e `FALHA_CONFIRMACAO`, **nenhuma ação adicional é oferecida** além da própria consulta.
*   **Links (Comuns):**
    *   `self`: Link para recarregar a reserva.

## 3. Exemplos de Respostas JSON

Abaixo estão exemplos de como o microsserviço de Reservas devolve as informações incorporando a hipermedia.

### Exemplo 1: Reserva `SOLICITADA` (Visão do Profissional)
```json
{
  "reservaId": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "cidadaoId": "user-123",
  "unidadeId": "unidade-456",
  "itemId": "item-789",
  "quantidade": 2,
  "status": "SOLICITADA",
  "criadaEm": "2026-10-10T10:00:00Z",
  "decisaoAte": "2026-10-12T10:00:00Z",
  "_links": {
    "self": {
      "href": "/api/unidade/v1/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab",
      "method": "GET"
    },
    "aceitar": {
      "href": "/api/unidade/v1/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab/decisao",
      "method": "POST",
      "body": { "decisao": "ACEITAR" }
    },
    "rejeitar": {
      "href": "/api/unidade/v1/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab/decisao",
      "method": "POST",
      "body": { "decisao": "REJEITADA" }
    },
    "cancelar": {
      "href": "/api/unidade/v1/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab/cancelar",
      "method": "POST",
      "notas": "Corpo da requisição deve conter 'justificativa'."
    }
  }
}
```

### Exemplo 2: Reserva `CONFIRMADA` (Visão do Cidadão)
```json
{
  "reservaId": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "cidadaoId": "user-123",
  "unidadeId": "unidade-456",
  "itemId": "item-789",
  "quantidade": 2,
  "status": "CONFIRMADA",
  "criadaEm": "2026-10-10T10:00:00Z",
  "_links": {
    "self": {
      "href": "/api/cidadao/v1/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab",
      "method": "GET"
    },
    "cancelar": {
      "href": "/api/cidadao/v1/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab/cancelar",
      "method": "POST"
    }
  }
}
```

## 4. Como o Cliente Utiliza os Links
Os clientes (aplicação do cidadão ou portal da unidade, via BFF) processam as ações da seguinte forma:
1. Fazem um `GET` para consultar a reserva.
2. Lêem o objeto `_links`.
3. Se existir a chave `cancelar`, o frontend apresenta um botão "Cancelar Pedido". Se o link possuir a anotação para adicionar uma justificativa (no caso do profissional), o frontend exibe o campo de texto obrigatório.
4. Ao clicar no botão, o frontend extrai o `href` e o `method` do objeto e executa a chamada HTTP para o BFF correspondente, sem precisar de saber a URL exata previamente.
5. Em estados como `RETIRADA` ou `CANCELADA`, o objeto `_links` apenas conterá `self`, logo, nenhum botão de ação será renderizado no ecrã.