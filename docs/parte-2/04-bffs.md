# GlicoAcesso - Projeto dos BFFs (Backend For Frontend)

**Etapa:** 2 — Arquitetura  
**Documento:** 04 - BFFs   

## 1. Justificativa para separar os BFFs

A decisão de separar a camada de apresentação em dois BFFs distintos (BFF Cidadão e BFF Unidade) baseia-se em três pilares:
1. **Segurança e Privacidade:** O cidadão não deve ter acesso a dados administrativos (como identificadores de alocação no banco de dados ou histórico de quem autorizou retiradas). Ter um BFF exclusivo garante que esses dados sensíveis nunca sejam enviados para o telemóvel do utilizador final.
2. **Otimização de Payload (Tráfego):** A aplicação do cidadão precisa de ser leve e rápida, consumindo o mínimo de dados possível móveis. O BFF Cidadão devolve JSONs enxutos, contendo apenas o necessário para a interface gráfica. O BFF Unidade, a correr em computadores desktop nos postos de saúde, pode receber cargas de dados maiores.
3. **Agregação Específica:** Cada aplicação tem fluxos diferentes. O BFF agrega as chamadas para que o frontend não tenha de fazer múltiplas requisições (ex: buscar a reserva e, em seguida, buscar o endereço da unidade).

## 2. Microsserviços Consultados

* **BFF Cidadão:** Consulta os serviços de **Unidades**, **Estoque** e **Reservas**.
* **BFF Unidade:** Consulta os serviços de **Unidades**, **Estoque**, **Reservas** e **Retiradas**.

## 3. Diferenças entre as respostas para o mesmo recurso

A tabela abaixo demonstra como o mesmo recurso ("Reserva") é tratado de forma diferente dependendo de qual BFF é chamado:

| Informação | BFF Cidadão | BFF Unidade |
| :--- | :--- | :--- |
| Situação da reserva | Sim | Sim |
| Local de retirada | Sim | Sim |
| Instruções para retirada | Sim | Sim |
| Identificador da alocação | Não | Sim |
| Ações administrativas | Não | Sim |
| Detalhes operacionais do estoque | Limitados | Sim |

## 4. Exemplos de Respostas JSON (Agregação)

Ao solicitar os detalhes de uma reserva (`GET /reservas/{id}`), os BFFs montam respostas diferentes, aplicando também o padrão HATEOAS para navegação.

**Resposta do BFF Cidadão (`GET /api/cidadao/v1/reservas/{reservaId}`):**
```json
{
  "reservaId": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "status": "CONFIRMADA",
  "itemNome": "Insulina NPH",
  "unidadeNome": "Posto Central",
  "enderecoLocal": "Rua Principal, 123",
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

**Resposta do BFF Unidade (`GET /api/unidade/v1/painel/reservas/{reservaId}`):**
```json
{
  "reservaId": "a1b2c3d4-5678-90ab-cdef-1234567890ab",
  "status": "CONFIRMADA",
  "itemNome": "Insulina NPH",
  "estoqueFisicoAtual": 50,
  "dadosAlocacao": {
    "alocacaoId": "f9e8d7c6-5432-10ab-cdef-9876543210ab",
    "quantidadeReservada": 1
  },
  "_links": {
    "self": {
      "href": "/api/unidade/v1/painel/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab",
      "method": "GET"
    },
    "autorizacao-retirada": {
      "href": "/api/unidade/v1/retiradas",
      "method": "POST"
    },
    "cancelar": {
      "href": "/api/unidade/v1/reservas/a1b2c3d4-5678-90ab-cdef-1234567890ab/cancelar",
      "method": "POST",
      "notas": "Exige justificativa no corpo da requisição."
    }
  }
}
```