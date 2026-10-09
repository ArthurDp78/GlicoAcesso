# GlicoAcesso — decomposição e fronteiras dos microsserviços

**Etapa:** 2 — Arquitetura  
**Documento:** 01 — Microsserviços  
**Versão:** 1.0  
**Situação:** detalhamento das fronteiras definidas no contrato compartilhado  
**Documento normativo:** [00 — Decisões arquiteturais compartilhadas](./00-decisoes-compartilhadas.md)  
**Última revisão:** 9 de outubro de 2026

> Este documento explica quais são os quatro microsserviços de domínio do GlicoAcesso, qual problema cada um resolve, quais informações controla, quais responsabilidades não lhe pertencem e por que as fronteiras foram escolhidas. Ele detalha o contrato do documento 00; não cria uma segunda definição de estados, eventos, identificadores ou tecnologias.

## 1. Objetivo e relação com o enunciado

O requisito 4.1 do enunciado da Etapa 2 pede:

1. a identificação de quatro ou mais serviços de domínio e a responsabilidade de cada um;
2. a justificativa das fronteiras adotadas;
3. um diagrama de componentes e de comunicação entre serviços.

Este documento atende aos dois primeiros itens. O diagrama geral de componentes e comunicação está no [02 — Diagrama de arquitetura](./02-diagrama-arquitetura.md), que deve representar exatamente as fronteiras descritas aqui.

O objetivo é permitir que uma pessoa que não participou das conversas do grupo consiga responder, sem depender de explicações externas:

- quais serviços existem e qual necessidade de negócio cada um atende;
- quais dados são canônicos em cada serviço;
- o que cada serviço pode fazer e o que não pode fazer;
- como os serviços cooperam sem compartilhar bancos;
- por que a divisão em quatro serviços é adequada ao domínio e aos requisitos do trabalho.

## 2. Escopo do sistema e da decomposição

O GlicoAcesso organiza a consulta de unidades públicas de saúde, a consulta de disponibilidade de medicamentos e insumos para diabetes, a solicitação de uma reserva e o registro da retirada presencial. O sistema coordena etapas administrativas. Não diagnostica, não prescreve, não substitui decisões clínicas e não transforma uma consulta de disponibilidade em garantia de reserva.

Uma reserva representa a solicitação de **um único item**, para **uma unidade de retirada** e em **uma quantidade positiva**. O item pode ser um medicamento ou um insumo. Uma solicitação de dois itens é representada por duas reservas independentes. Essa regra evita que a confirmação de uma solicitação contenha itens confirmados parcialmente.

A decomposição contém exatamente estes quatro microsserviços de domínio:

1. **Unidades**
2. **Estoque**
3. **Reservas**
4. **Retiradas**

Os clientes cidadão e unidade, o API Gateway e os BFFs são componentes da arquitetura de entrada e apresentação. Eles não são serviços adicionais de domínio e não passam a ser donos dos dados descritos neste documento. A arquitetura de entrada e seus caminhos são detalhados nos documentos 02, 06 e 07.

O projeto não cria um quinto microsserviço de identidade nesta etapa. A autenticação pode ser fornecida por um provedor de identidade externo. Os serviços de domínio recebem somente o identificador estável necessário para reconhecer o ator e autorizar a operação; não copiam senha, token ou perfil completo para seus bancos.

## 3. Critérios usados para definir uma fronteira

Uma fronteira de microsserviço representa uma responsabilidade de negócio com dados cuja alteração tem um responsável claro. Para o GlicoAcesso, aplicam-se as seguintes regras:

1. **Um único dono por informação canônica.** O serviço responsável por um domínio é o único que grava a fonte de verdade desse domínio.
2. **Referências entre domínios, não cópias autoritativas.** Um serviço pode guardar identificadores externos necessários à própria operação, mas não replica a tabela de outro serviço como fonte de verdade.
3. **Integração por contrato.** A consulta ou solicitação de mudança em outro domínio ocorre por API do serviço responsável; fatos que precisam atualizar projeções são propagados por eventos.
4. **Sem acesso cruzado a bancos.** Nenhum microsserviço lê ou escreve diretamente na instância PostgreSQL de outro.
5. **Transações locais.** Cada serviço confirma as alterações do próprio domínio em sua transação local. A coordenação de efeitos que atravessam serviços é feita pela SAGA de confirmação, detalhada em [04 — SAGA](./04-saga.md).
6. **Separação entre estado de negócio e fato físico.** Uma reserva confirmada não é uma retirada. Reservas controla o ciclo de vida da solicitação; Retiradas controla a autorização e o fato de a entrega presencial ter ocorrido.

Esses critérios evitam que a divisão seja apenas técnica. Cada serviço corresponde a uma área que possui regras e informações próprias do negócio.

## 4. Visão resumida dos serviços

| Serviço | Pergunta de negócio que responde | Dados canônicos sob sua responsabilidade | Não é responsável por |
|---|---|---|---|
| **Unidades** | “Quais unidades existem e quais são suas informações de atendimento?” | Cadastro da unidade, endereço, contatos institucionais, horários, informações de atendimento e prazo de análise das solicitações da unidade. | Catálogo e saldo de itens, permissão de reserva por item, solicitações, autorizações e retiradas. |
| **Estoque** | “Qual item existe, qual quantidade pertence à unidade e qual quantidade pode ser alocada?” | Catálogo de medicamentos e insumos, estoque físico, movimentações, configuração de permissão de reserva por unidade/item, alocações e projeção de disponibilidade. | Identidade do cidadão, decisão de aceitar uma solicitação, ciclo de vida da reserva, autorização de retirada e prova da entrega. |
| **Reservas** | “Qual é a situação da solicitação e qual etapa distribuída precisa ocorrer?” | Solicitação, decisão da unidade, estado de negócio, referências ao cidadão/unidade/item, prazo aplicado à solicitação e estado durável da SAGA. | Saldo canônico de estoque, cadastro canônico de unidade/item, autorização de balcão e registro da entrega física. |
| **Retiradas** | “Existe autorização válida para esta reserva e a entrega já foi registrada?” | Autorização preparada ou cancelada, referência à reserva e registro de quem e quando efetuou a entrega presencial. | Saldo de estoque, disponibilidade, decisão de aceitar solicitação e ciclo de vida completo da reserva. |

As instâncias de banco são separadas. Cada serviço possui sua própria instância PostgreSQL; “possuir” uma informação significa controlar sua fonte de verdade e as alterações nela, não necessariamente expor todos os campos dessa informação a todos os clientes.

## 5. Microsserviço Unidades

### 5.1 Propósito

O serviço Unidades representa os estabelecimentos públicos em que o cidadão consulta atendimento e em que o estoque é mantido e a retirada presencial pode ocorrer. Sua função é fornecer e manter informações institucionais da unidade.

### 5.2 Informações que controla

Unidades é a fonte de verdade para:

- identificador da unidade, unidadeId;
- cadastro da unidade;
- endereço;
- contatos institucionais;
- horários;
- informações de atendimento;
- prazo de análise das solicitações daquela unidade, prazoAnalise.

O prazoAnalise é uma configuração da unidade. Ao criar uma solicitação, Reservas consulta esse prazo e registra o instante limite aplicável àquela solicitação como decisaoAte. Assim, Unidades controla a configuração vigente e Reservas controla o prazo efetivamente aplicado a cada reserva.

### 5.3 Responsabilidades

Unidades:

- cadastra e atualiza as informações institucionais da unidade;
- disponibiliza informações de unidade para consultas apropriadas aos clientes;
- mantém o prazo de análise configurado para a unidade;
- responde às consultas internas necessárias para a criação de uma reserva e para as telas da unidade ou do cidadão.

### 5.4 Limites explícitos

Unidades não:

- cadastra ou controla o catálogo canônico de medicamentos e insumos;
- mantém quantidade física ou quantidade alocada;
- decide se determinado item pode ser reservado; a configuração permiteReserva por unidade/item pertence a Estoque;
- cria, aceita, rejeita, cancela ou confirma reservas;
- prepara autorização de retirada nem registra a entrega presencial.

Uma referência a unidade em outro serviço é o unidadeId. A existência desse identificador não autoriza o outro serviço a consultar tabelas internas de Unidades.

### 5.5 Motivo da fronteira

Informações institucionais e de atendimento têm regras próprias e não são o mesmo dado que o saldo de produtos. Separar Unidades de Estoque impede que o cadastro institucional se torne acoplado às movimentações e à concorrência de alocação. Também deixa explícito que configurar o prazo de análise da unidade e permitir reservas de determinado item são decisões diferentes, com donos diferentes.

## 6. Microsserviço Estoque

### 6.1 Propósito

Estoque controla os itens e as quantidades que pertencem a cada unidade. É a autoridade para decidir se uma quantidade ainda pode ser alocada a uma reserva.

### 6.2 Informações que controla

Estoque é a fonte de verdade para:

- catálogo de medicamentos e insumos e seus itemId;
- quantidade física registrada por unidade e item;
- movimentações que alteram o estoque físico;
- configuração permiteReserva para cada combinação unidadeId/itemId;
- alocações de quantidade associadas a reservaId;
- modelo de leitura de disponibilidade;
- Outbox de eventos derivados de alterações persistidas em seu domínio.

O nome, o tipo e a descrição canônicos do item pertencem a Estoque. Reservas e Retiradas podem armazenar itemId como referência, mas não são donas do cadastro do item.

### 6.3 Responsabilidades

Estoque:

- administra o catálogo de medicamentos e insumos;
- registra entrada, saída ou ajuste de quantidade física;
- mantém a configuração que permite ou impede reserva para um item em uma unidade;
- calcula e apresenta a disponibilidade para consulta;
- valida a quantidade solicitada contra o modelo de escrita atual;
- cria uma alocação atômica quando há quantidade suficiente e as regras permitem;
- libera somente a alocação vinculada à reserva indicada quando uma compensação ou um cancelamento válido é solicitado;
- publica eventos de estoque por meio de Outbox quando uma alteração persistida precisar atualizar projeções ou outros consumidores.

### 6.4 Distinção entre estoque físico, alocação e disponibilidade

Estes conceitos não podem ser tratados como sinônimos:

| Conceito | Significado |
|---|---|
| **Estoque físico** | Quantidade que a unidade possui segundo os registros de movimentação do Estoque. |
| **Alocação** | Quantidade retida para uma reserva específica; continua sob controle do Estoque e ainda não foi entregue. |
| **Disponibilidade** | Valor derivado para consulta, calculado a partir do estoque físico e das alocações ativas. É uma projeção e pode estar alguns segundos atrasada. |

A disponibilidade mostrada ao cidadão é informativa. A decisão definitiva ocorre quando Estoque tenta alocar a quantidade usando seu modelo de escrita, com validação atômica. Uma projeção atrasada nunca pode autorizar uma alocação acima do saldo disponível.

### 6.5 Limites explícitos

Estoque não:

- guarda dados pessoais, perfil ou credenciais do cidadão;
- decide se a unidade aceita ou rejeita a solicitação;
- controla os estados SOLICITADA, EM_CONFIRMACAO, CONFIRMADA ou demais estados de negócio da reserva;
- cria autorização de retirada;
- registra que o item foi entregue fisicamente;
- consulta diretamente o banco de Reservas, Unidades ou Retiradas.

### 6.6 Motivo da fronteira

O saldo e as alocações exigem uma regra de integridade local: duas solicitações concorrentes não podem consumir a mesma quantidade. Reservas, por sua vez, representa uma solicitação e seu fluxo de decisão, que podem existir mesmo antes de qualquer alocação. Separar esses domínios permite que Estoque proteja o saldo como autoridade e que Reservas coordene o processo sem gravar dados de estoque.

A separação também dá lugar ao CQRS definido no documento 00: o modelo de escrita de Estoque protege as invariantes e a projeção de leitura otimiza a consulta de disponibilidade. Esses modelos continuam pertencendo ao mesmo microsserviço e não criam um quinto serviço.

## 7. Microsserviço Reservas

### 7.1 Propósito

Reservas controla a solicitação do cidadão desde sua criação até um resultado de negócio, como rejeição, expiração, confirmação, cancelamento, falha final ou retirada registrada. Também coordena a SAGA usada para confirmar uma solicitação aceita.

### 7.2 Informações que controla

Reservas é a fonte de verdade para:

- reservaId e os dados mínimos da solicitação;
- cidadaoId, unidadeId e itemId como referências;
- quantidade solicitada;
- instante de criação e decisaoAte aplicado à solicitação;
- decisão da unidade, incluindo ator e instante;
- status de negócio da reserva;
- histórico de transições e cancelamentos necessário à auditoria;
- execução durável da SAGA, incluindo sagaId, etapa, estado, tentativas e dados necessários à recuperação;
- resultado da confirmação e atualização do estado da reserva quando recebe o fato de retirada concluída.

Reservas guarda identificadores de cidadão, unidade e item conforme a necessidade do fluxo. Isso não transfere para Reservas a propriedade do perfil, cadastro de unidade ou catálogo de itens.

### 7.3 Responsabilidades

Reservas:

- recebe e valida a solicitação quanto à estrutura mínima exigida;
- consulta Estoque para verificar se a combinação de item e unidade permite reservas;
- consulta Unidades para obter o prazoAnalise configurado;
- registra a solicitação como SOLICITADA e calcula decisaoAte;
- autoriza a unidade correspondente a decidir sobre a solicitação;
- registra aceitação ou rejeição e seus responsáveis;
- ao aceitar, inicia e coordena a SAGA de confirmação;
- envia comandos internos idempotentes a Estoque e Retiradas, mantendo o estado durável do processo;
- altera a reserva para CONFIRMADA somente após a alocação no Estoque e a preparação da autorização em Retiradas terem sido confirmadas;
- processa cancelamentos de reserva conforme os estados permitidos e coordena a reversão dos efeitos distribuídos, quando houver;
- expira automaticamente somente solicitações SOLICITADA cujo prazo decisaoAte venceu, conforme a regra do documento 00;
- atualiza o status de negócio para RETIRADA após processar o evento canônico de retirada concluída publicado por Retiradas.

### 7.4 Limites explícitos

Reservas não:

- mantém o saldo físico ou decide unilateralmente a disponibilidade;
- grava alocações diretamente no banco de Estoque;
- mantém o cadastro canônico de unidade ou item;
- prepara a autorização usada no balcão;
- declara que a entrega física ocorreu sem o registro confirmado por Retiradas;
- realiza uma transação distribuída ACID entre bancos.

Reservas é o coordenador da SAGA, não o dono de todos os dados que participam dela. Estoque continua dono da alocação; Retiradas continua dona da autorização e do registro da entrega.

### 7.5 Motivo da fronteira

O fluxo de uma solicitação tem regras próprias: quem pode decidir, em quais condições ela expira, quais estados são permitidos e quando uma confirmação pode ser comunicada. Essas regras não pertencem ao serviço de Estoque, que precisa concentrar-se na integridade de quantidades, nem a Retiradas, que precisa registrar autorização e entrega.

Reservas coordena as etapas porque conhece o estado do processo de negócio. Isso não significa que ele possa editar os dados dos participantes: cada participante aplica sua própria regra e confirma seu próprio efeito local. Como a confirmação atravessa Reservas, Estoque e Retiradas, a coordenação é feita por SAGA orquestrada, e não por transação compartilhada.

## 8. Microsserviço Retiradas

### 8.1 Propósito

Retiradas controla a autorização para a retirada presencial e o registro de que a entrega efetivamente ocorreu na unidade. Ele diferencia a preparação administrativa da autorização do ato físico realizado no balcão.

### 8.2 Informações que controla

Retiradas é a fonte de verdade para:

- autorizacaoId;
- reservaId associado à autorização;
- unidadeId e demais referências necessárias para validar a retirada;
- estado da autorização, inclusive preparada ou cancelada;
- retiradaId quando a entrega física é registrada;
- identificador do ator autorizado que realizou a entrega e instante do registro.

Retiradas mantém apenas os dados necessários para reconhecer a reserva e cumprir a retirada. A reserva e o estoque permanecem sob propriedade de seus respectivos serviços.

### 8.3 Responsabilidades

Retiradas:

- prepara, de forma idempotente, a autorização solicitada pela SAGA depois que Estoque confirmou a alocação;
- cancela uma autorização quando Reservas coordena cancelamento ou compensação;
- valida que a autorização está apta e corresponde à reserva e à unidade envolvidas;
- registra uma única vez a entrega física, com ator e instante;
- publica o evento retirada.concluida.v1 depois de confirmar localmente a entrega;
- assegura que cancelamento da autorização e registro da retirada física sejam mutuamente exclusivos.

### 8.4 Limites explícitos

Retiradas não:

- confirma que existe saldo livre nem cria ou libera alocação de estoque;
- decide se uma solicitação deve ser aceita;
- controla o ciclo de vida completo da reserva;
- altera diretamente o status armazenado no banco de Reservas;
- registra entrega sem autorização válida vinculada à mesma reserva e unidade;
- permite que uma mesma autorização resulte em mais de uma entrega confirmada.

Quando Retiradas confirma a entrega, esse serviço grava o fato em seu próprio banco e publica o evento correspondente. Reservas consome esse fato e atualiza o status da solicitação. Durante o intervalo de propagação do evento, Retiradas pode já registrar a entrega enquanto Reservas ainda apresenta CONFIRMADA; essa defasagem é uma consequência explícita da consistência eventual definida no documento 00.

### 8.5 Motivo da fronteira

Uma autorização preparada não significa que houve entrega. A unidade pode não comparecer para retirar o item, e uma reserva confirmada pode depois ser cancelada antes da entrega. Por isso, autorização, cancelamento da autorização e entrega presencial são regras próprias de Retiradas.

Manter esse serviço separado impede que Reservas registre como fato físico algo que ainda não aconteceu e impede que Estoque seja responsável por uma interação de balcão. Também cria uma fronteira clara para a concorrência entre cancelar e entregar: apenas Retiradas pode serializar esses dois resultados sobre a autorização.

## 9. Propriedade dos dados e referências entre serviços

O dono de cada informação canônica é único. Os demais serviços podem guardar referências para concluir suas próprias operações, mas não podem tratar essas referências como autorização para acessar a base de dados do proprietário.

| Informação canônica | Serviço proprietário | Referências que podem aparecer em outros serviços | Regra de acesso |
|---|---|---|---|
| Dados institucionais e atendimento da unidade | Unidades | unidadeId em Estoque, Reservas e Retiradas | Obter por contrato de Unidades ou por informação explicitamente propagada; nunca ler o banco de Unidades. |
| Prazo de análise configurado para a unidade | Unidades | decisaoAte registrado por reserva em Reservas | Reservas consulta a configuração e guarda o prazo aplicado à solicitação. |
| Catálogo de medicamentos e insumos | Estoque | itemId em Reservas e Retiradas | Obter por contrato de Estoque; não manter cópia como fonte canônica. |
| Estoque físico, movimentações e alocações | Estoque | reservaId e referências de unidade/item | Somente Estoque altera o saldo e as alocações. |
| Disponibilidade para consulta | Estoque | Respostas compostas apresentadas por BFFs | Tratar como projeção atualizável; não usar como validação final de alocação. |
| Solicitação, decisão, status e SAGA | Reservas | reservaId em Estoque e Retiradas | Somente Reservas altera o ciclo de vida da reserva e coordena a SAGA. |
| Autorização e entrega presencial | Retiradas | reservaId, unidadeId e itemId quando necessários | Somente Retiradas prepara/cancela autorização e registra o fato da entrega. |
| Identidade de autenticação | Provedor de identidade | cidadaoId ou identificador estável do ator | Não copiar credenciais, tokens ou perfil completo para bancos de domínio. |

As relações entre bancos são referências por UUID, sem chave estrangeira entre instâncias. Cada participante valida os dados e as permissões relevantes à própria operação. Um BFF não substitui essa validação.

## 10. Como os serviços cooperam

Esta seção descreve responsabilidades e direção das chamadas em nível arquitetural. Os endpoints, payloads, códigos HTTP e esquemas de eventos são definidos nos OpenAPI e nos documentos especializados.

| Origem | Destino | Necessidade de negócio | Forma definida no contrato |
|---|---|---|---|
| BFF Cidadão ou BFF Unidade | Unidades | Consultar informações de unidades necessárias às jornadas de cada público. | API do serviço Unidades; a autorização de cada operação é validada pelo serviço. |
| BFF Cidadão ou BFF Unidade | Estoque | Consultar disponibilidade ou executar ações de estoque permitidas ao perfil da unidade. | API do serviço Estoque; a disponibilidade é projeção e o comando de alocação é autoridade. |
| BFF Cidadão ou BFF Unidade | Reservas | Criar e acompanhar solicitações; permitir decisão e ações da equipe autorizada. | API do serviço Reservas; clientes não coordenam diretamente a SAGA. |
| BFF Unidade | Retiradas | Consultar autorização e registrar uma entrega presencial por profissional autorizado. | API do serviço Retiradas. |
| Reservas | Unidades | Obter prazoAnalise para definir decisaoAte ao criar uma solicitação. | Chamada interna ao serviço proprietário do prazo. |
| Reservas | Estoque | Verificar permiteReserva e executar alocação ou liberação durante a SAGA. | Comandos REST internos, idempotentes e versionados. |
| Reservas | Retiradas | Preparar ou cancelar autorização durante confirmação, compensação ou cancelamento. | Comandos REST internos, idempotentes e versionados. |
| Estoque | Consumidores interessados | Informar alterações persistidas que atualizam disponibilidade e projeções. | Eventos publicados por Outbox no RabbitMQ; consumidores deduplicam por eventId. |
| Retiradas | Reservas | Informar que a entrega presencial foi registrada. | Evento retirada.concluida.v1 publicado por Outbox; Reservas atualiza seu status ao consumi-lo. |

Os clientes chamam o API Gateway, e o Gateway encaminha cada público ao BFF correspondente. Clientes não chamam APIs dos microsserviços de domínio diretamente. Os BFFs podem agregar respostas para uma tela, mas não possuem regras de domínio, não gravam nos bancos dos microsserviços e não orquestram a SAGA.

As chamadas entre serviços usam rotas internas e não são expostas pelo Gateway. Os eventos comunicam fatos já ocorridos e atualizam projeções ou estados derivados; eles não substituem os comandos REST da SAGA definidos no documento 00.

## 11. Justificativa consolidada da decomposição

### 11.1 Por que Unidades e Estoque são serviços diferentes

Unidades controla o estabelecimento e as informações institucionais; Estoque controla itens, quantidades físicas, movimentações e alocações. A configuração de prazo de análise também pertence à unidade, enquanto permiteReserva pertence à combinação de unidade e item no Estoque. São regras diferentes. Separá-las evita que uma alteração de cadastro institucional grave ou leia diretamente dados de estoque.

### 11.2 Por que Estoque e Reservas são serviços diferentes

Estoque precisa manter a verdade quantitativa e proteger a invariável de não alocar mais que o saldo disponível. Reservas precisa manter a solicitação, decisão, estados e coordenação do processo. A solicitação pode ser criada antes de qualquer alocação; somente depois da aceitação a SAGA solicita a alocação. Essa separação permite que o Estoque seja a autoridade quantitativa enquanto Reservas é a autoridade do fluxo da reserva.

### 11.3 Por que Reservas e Retiradas são serviços diferentes

Reservas controla a solicitação e sua confirmação administrativa. Retiradas controla a autorização de balcão e comprova se ocorreu a entrega física. A reserva pode estar confirmada sem que tenha sido retirada, e o cancelamento pode ocorrer antes da retirada. Separar esses fatos evita uma falsa confirmação de entrega e permite que Retiradas controle a concorrência entre cancelar uma autorização e registrar a entrega.

### 11.4 Por que Retiradas não é incorporado a Estoque

O Estoque registra quantidades e alocações; Retiradas registra a autorização e o fato operacional de entrega a uma pessoa na unidade. A alocação reduz o que está disponível para novas reservas, mas não é baixa física nem comprovação de entrega. Retiradas não pode editar diretamente o saldo ou a alocação no banco de Estoque. O contrato atual ainda não especifica qual operação de integração efetua a baixa física e encerra a alocação depois da entrega; essa lacuna está registrada na seção 13.1 e precisa ser resolvida antes de os contratos e a persistência serem considerados fechados.

### 11.5 Por que Reservas coordena a SAGA

Reservas recebe a decisão de negócio que inicia a confirmação e é dono do estado visível da solicitação. Por isso mantém o registro durável da SAGA e coordena os participantes Estoque e Retiradas. Os participantes continuam donos dos efeitos que executam e das respectivas compensações. Essa divisão mantém uma sequência compreensível sem criar um serviço coordenador adicional.

### 11.6 Por que não criar outros microsserviços nesta decomposição

O escopo aprovado exige quatro serviços de domínio e o fluxo de confirmação precisa atravessar pelo menos três serviços. As quatro fronteiras acima cobrem cadastro de unidades, estoque, solicitação e retirada, além de sustentarem a SAGA Reservas–Estoque–Retiradas. Criar um serviço de identidade, catálogo separado ou orquestrador independente nesta etapa acrescentaria fronteiras e integrações que não são necessárias para demonstrar os requisitos definidos. Identidade é atendida por provedor externo; o catálogo continua dentro de Estoque; Reservas mantém a orquestração.

Esta escolha não impede uma evolução futura. Uma nova fronteira só deve ser criada quando houver responsabilidade de negócio, dados e regras que justifiquem a autonomia, e após revisar o impacto no documento 00, nos contratos, na SAGA, nos eventos e nos diagramas.

## 12. Resumo das autoridades de negócio

Para eliminar interpretações divergentes, as perguntas abaixo têm um único serviço responsável:

| Pergunta | Autoridade |
|---|---|
| Qual é o endereço, horário, contato ou prazo configurado de uma unidade? | **Unidades** |
| Este item existe no catálogo e qual é sua descrição canônica? | **Estoque** |
| A unidade permite reserva deste item? | **Estoque** |
| Qual é o saldo físico e quanto pode ser alocado? | **Estoque** |
| Qual é a situação da solicitação e quem tomou a decisão? | **Reservas** |
| Quais etapas da confirmação ou do cancelamento ainda precisam ser reconciliadas? | **Reservas**, por meio do estado durável da SAGA |
| A autorização da reserva está apta ou cancelada? | **Retiradas** |
| A entrega presencial aconteceu, por quem e quando? | **Retiradas** |

Se uma operação precisar de informações de mais de um serviço, ela consulta os proprietários por seus contratos ou consome eventos definidos. Não deve resolver a integração por consultas SQL entre bancos.

## 13. O que este documento não define

Para evitar sobreposição entre as frentes, este documento não fixa:

- caminhos, parâmetros, corpos, respostas, códigos HTTP ou especificações OpenAPI de cada operação;
- estrutura de tabelas, índices, migrations, mecanismos específicos de concorrência ou configuração de instâncias PostgreSQL;
- detalhes de filas, exchanges, roteamento de mensagens, política operacional de DLQ ou implementação do publicador da Outbox;
- configuração técnica do API Gateway, autenticação detalhada ou políticas de roteamento;
- composição de telas e diferenças completas de apresentação dos BFFs;
- sequência detalhada de cada etapa, timeout, retry e compensação da SAGA;
- fluxo detalhado de estados e ações apresentado ao cidadão e à equipe.

Os detalhes ficam nos documentos OpenAPI e 02–11 indicados na estrutura compartilhada pelo documento 00. Os documentos especializados podem detalhar a implementação, mas não podem alterar as responsabilidades e fronteiras aqui descritas sem revisar primeiro o contrato compartilhado.

### 13.1 Lacuna de integração identificada

O documento 00 define que Retiradas publica retirada.concluida.v1 e que Reservas consome esse evento para mudar a reserva de CONFIRMADA para RETIRADA. Também define que Estoque controla o saldo físico e as alocações. Porém, o contrato atual não declara como o Estoque toma conhecimento da retirada concluída, como a quantidade física é baixada nem como a alocação ativa daquela reserva é encerrada.

Essa regra precisa ser decidida no contrato compartilhado antes de fechar a integração de retirada. Ela afeta, no mínimo, o documento 00, o contrato OpenAPI/eventos da Pessoa 2 e os documentos de bancos, consistência, Outbox e CQRS da Pessoa 4. Até essa definição:

- Retiradas continua sendo a autoridade do fato de entrega presencial;
- Estoque continua sendo a autoridade do saldo físico e da alocação;
- nenhum serviço pode contornar essa fronteira gravando no banco do outro;
- este documento não presume um comando ou evento adicional nem considera a baixa de estoque resolvida.

## 14. Critério de conformidade

Uma proposta de API, banco, evento, Gateway, BFF ou diagrama está de acordo com esta decomposição quando:

- existem os quatro serviços de domínio identificados neste documento;
- cada informação canônica tem um único serviço proprietário;
- nenhum serviço lê ou grava diretamente no banco de outro;
- referências externas usam identificadores estáveis, sem copiar a fonte de verdade do serviço proprietário;
- Estoque é a autoridade de saldo e alocação;
- Reservas é a autoridade da solicitação e coordenador da SAGA;
- Retiradas é a autoridade da autorização e da entrega física;
- Unidades é a autoridade dos dados institucionais e do prazoAnalise configurado;
- o processamento de retirada não altera o banco de Estoque diretamente; a integração que baixa o estoque e encerra a alocação precisa estar definida no contrato compartilhado antes do fechamento dos documentos dependentes;
- Gateway e BFFs permanecem componentes de borda e não se tornam donos ou coordenadores do domínio;
- o diagrama de arquitetura do documento 02 mostra as mesmas fronteiras e os caminhos de comunicação descritos aqui.

Se qualquer item falhar, a proposta deve ser corrigida ou a decisão compartilhada deve ser revisada formalmente antes da integração.

## 15. Referências internas

- [00 — Decisões arquiteturais compartilhadas](./00-decisoes-compartilhadas.md): vocabulário, propriedade de dados, identificadores, estados, tecnologia e decisões normativas.
- [02 — Diagrama de arquitetura](./02-diagrama-arquitetura.md): representação visual dos componentes, bancos, Gateway, BFFs e comunicação.
- [03 — Fluxo de reservas](./03-fluxo-reservas.md): fluxo de negócio, atores, decisões e transições da reserva.
- [04 — SAGA](./04-saga.md): orquestração, etapas, compensações, falhas, recuperação e idempotência.

Os arquivos especializados acima são referências previstas na estrutura da Etapa 2. Se algum deles ainda não existir na branch, o link deve passar a funcionar quando a respectiva frente for integrada.