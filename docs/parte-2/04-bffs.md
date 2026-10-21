# GlicoAcesso - Projeto dos BFFs (Backend For Frontend)

**Etapa:** 2 — Arquitetura  
**Documento:** 04 - BFFs   

## 1. Justificativa para separar os BFFs

A decisão de separar a camada de apresentação em dois BFFs distintos (BFF Cidadão e BFF Unidade) baseia-se em três pilares:
1. **Segurança e Privacidade:** O cidadão não deve ter acesso a dados administrativos (como identificadores de alocação no banco de dados ou histórico de quem autorizou retiradas). Ter um BFF exclusivo garante que esses dados sensíveis nunca sejam enviados para o telemóvel do utilizador final.
2. **Otimização de Payload (Tráfego):** A aplicação do cidadão precisa de ser leve e rápida, consumindo o mínimo de dados possível móveis. O BFF Cidadão devolve JSONs enxutos, contendo apenas o necessário para a interface gráfica. O BFF Unidade, a correr em computadores desktop nos postos de saúde, pode receber cargas de dados maiores.
3. **Agregação Específica:** Cada aplicação tem fluxos diferentes. O BFF agrega as chamadas para que o frontend não tenha de fazer múltiplas requisições (ex: buscar a reserva e, em seguida, buscar o endereço da unidade).

## 2. Microsserviços Integrados

* **BFF Cidadão:** Consome operações de **Unidades**, **Estoque** e **Reservas**.
* **BFF Unidade:** Consome operações de **Unidades**, **Estoque**, **Reservas** e **Retiradas**.

Os contratos OpenAPI dos BFFs também cobrem as operações do fluxo de negócio e da operação da unidade: o cidadão cria e cancela a própria solicitação; a unidade mantém seu cadastro, horários e prazo, configura permissão de reserva, registra entradas e ajustes de estoque, decide ou cancela reservas e registra a entrega. Essas rotas preservam os métodos, corpos, respostas e verificações dos serviços proprietários.

Na consulta agregada de uma reserva, ambos os BFFs leem `GET /internal/v1/reservas/{reservaId}` em Reservas. O BFF Unidade também lê `GET /internal/v1/autorizacoes/{reservaId}` em Retiradas e complementa nomes e saldo pelas consultas de Unidades e Estoque. Para uma reserva ainda sem autorização, o `404` desta consulta interna significa apenas que `dadosAutorizacao` é omitido da resposta agregada. A lista de solicitações pendentes usa a leitura de Reservas sem consultar autorizações uma a uma. O BFF Unidade só oferece a ação de entrega para reserva `CONFIRMADA` com autorização ativa; registrar a entrega continua sendo `POST /api/unidade/v1/retiradas` com `autorizacaoId`.

Todos os comandos `POST`/`PUT`/`PATCH` dos BFFs exigem `Idempotency-Key`. O cliente gera uma chave para cada ação lógica e conserva a mesma chave e corpo nos retries; o BFF encaminha a chave ao serviço responsável, que mantém seu próprio escopo de idempotência. Esse cabeçalho não é um campo do corpo JSON do link HATEOAS.

| Operação exposta pelo BFF | Serviço e operação de domínio encaminhada |
|---|---|
| Cidadão: `POST /reservas`, `POST /reservas/{id}/cancelar` | Reservas: criação e cancelamento pelas rotas `/api/cidadao/v1/reservas...`. |
| Cidadão: `GET /unidades` | Unidades: `GET /api/cidadao/v1/unidades`, com dados públicos de atendimento. |
| Cidadão: `GET /itens` | Estoque: `GET /api/cidadao/v1/estoque/itens`, com o catálogo público; o cliente usa o `itemId` escolhido em `GET /explorar`. |
| Cidadão: `GET /explorar` | Unidades: identificação, endereço, horário e orientações das unidades ativas; Estoque: `GET /api/cidadao/v1/estoque/disponibilidade` para cada unidade e item consultados. `disponivel` deriva de quantidade maior que zero; `permiteReserva` é apresentado separadamente. |
| Cidadão: `GET /reservas/{id}` | Reservas: `GET /internal/v1/reservas/{reservaId}`; Unidades e Estoque fornecem dados de apresentação pelos próprios contratos. |
| Unidade: `PUT /unidade`, `/unidade/horarios`, `/unidade/prazo-analise`, `PATCH /unidade/status` | Unidades: atualizar cadastro, horários, prazo e situação operacional em `/internal/v1/unidades...`. |
| Unidade: `GET /unidade` | Unidades: `GET /internal/v1/unidades/{unidadeId}` para o cadastro da unidade vinculada ao profissional. |
| Unidade: operações em `/painel/estoque/{unidadeId}/itens/{itemId}` | Estoque: configurar permissão, registrar entradas e ajustes nas rotas de `/api/unidade/v1/estoque...`. |
| Unidade: `GET /painel/estoque` | Estoque: `GET /api/unidade/v1/estoque/{unidadeId}/itens` fornece os dados do catálogo, saldos e `atualizadoEm`. |
| Unidade: `POST /reservas/{id}/decisao`, `POST /reservas/{id}/cancelar` | Reservas: decisão e cancelamento pelas rotas `/api/unidade/v1/reservas...`. |
| Unidade: `GET /painel/reservas` | Reservas: `GET /api/unidade/v1/reservas` lista as solicitações `SOLICITADA` da unidade autenticada, sem dados de outros estabelecimentos. |
| Unidade: `GET /painel/reservas/{id}` | Reservas: `GET /internal/v1/reservas/{reservaId}`; Retiradas: `GET /internal/v1/autorizacoes/{reservaId}`; Unidades e Estoque fornecem nomes e saldo pelos contratos de consulta existentes. |
| Unidade: `POST /retiradas` | Retiradas: `POST /api/unidade/v1/retiradas`, após consulta do estado canônico de Reservas. |

## 3. Diferenças entre as respostas para o mesmo recurso

A tabela abaixo demonstra como o mesmo recurso ("Reserva") é tratado de forma diferente dependendo de qual BFF é chamado:

| Informação | BFF Cidadão | BFF Unidade |
| :--- | :--- | :--- |
| Situação da reserva | Sim | Sim |
| Local de retirada | Sim | Sim |
| Instruções para retirada | Sim | Sim |
| Identificador da autorização de retirada | Não | Sim |
| Ações administrativas | Não | Sim |
| Detalhes operacionais do estoque | Limitados | Sim |

## 4. Exemplos de Respostas JSON (Agregação)

Ao solicitar os detalhes de uma reserva, os BFFs consultam a operação agregada apropriada (`GET /api/cidadao/v1/reservas/{reservaId}` ou `GET /api/unidade/v1/painel/reservas/{reservaId}`) e montam respostas diferentes, aplicando também HATEOAS para navegação.

**Resposta do BFF Cidadão (`GET /api/cidadao/v1/reservas/{reservaId}`):**
```json
{
  "reservaId": "a1b2c3d4-5678-4abc-8def-1234567890ab",
  "unidadeId": "b2c3d4e5-6789-40ab-8cde-2345678901bc",
  "itemId": "c3d4e5f6-7890-41bc-9def-3456789012cd",
  "quantidade": 1,
  "status": "CONFIRMADA",
  "itemNome": "Insulina NPH",
  "unidadeNome": "Posto Central",
  "enderecoLocal": "Rua Principal, 123",
  "orientacoesRetirada": "Apresentar documento pessoal e receita válida.",
  "_links": {
    "self": {
      "href": "/api/cidadao/v1/reservas/a1b2c3d4-5678-4abc-8def-1234567890ab",
      "method": "GET"
    },
    "cancelar": {
      "href": "/api/cidadao/v1/reservas/a1b2c3d4-5678-4abc-8def-1234567890ab/cancelar",
      "method": "POST"
    }
  }
}
```

**Resposta do BFF Unidade (`GET /api/unidade/v1/painel/reservas/{reservaId}`):**
```json
{
  "reservaId": "a1b2c3d4-5678-4abc-8def-1234567890ab",
  "unidadeId": "b2c3d4e5-6789-40ab-8cde-2345678901bc",
  "itemId": "c3d4e5f6-7890-41bc-9def-3456789012cd",
  "quantidade": 1,
  "status": "CONFIRMADA",
  "itemNome": "Insulina NPH",
  "orientacoesRetirada": "Apresentar documento pessoal e receita válida.",
  "estoqueFisicoAtual": 50,
  "dadosAutorizacao": {
    "autorizacaoId": "0a1b2c3d-4e5f-4abc-8def-0123456789ab",
    "status": "ATIVA"
  },
  "_links": {
    "self": {
      "href": "/api/unidade/v1/painel/reservas/a1b2c3d4-5678-4abc-8def-1234567890ab",
      "method": "GET"
    },
    "autorizacao-retirada": {
      "href": "/api/unidade/v1/retiradas",
      "method": "POST",
      "body": { "autorizacaoId": "0a1b2c3d-4e5f-4abc-8def-0123456789ab" }
    },
    "cancelar": {
      "href": "/api/unidade/v1/reservas/a1b2c3d4-5678-4abc-8def-1234567890ab/cancelar",
      "method": "POST",
      "body": { "justificativa": "Solicitação cancelada pela unidade" }
    }
  }
}
```
