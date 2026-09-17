# Parte 1 - Concepção e Pitch

## Identidade da startup

- **Nome:** GlicoAcesso
- **Slogan:** Encontre. Reserve. Continue seu cuidado.
- **Definição:** plataforma que facilita a localização, a solicitação de reserva e o acompanhamento da retirada de medicamentos e insumos para diabetes em unidades públicas de saúde participantes.
- **Identidade visual:** logotipo em [`/identidade-visual/logo.png`](./identidade-visual/logo.png)

### Em uma frase

O **GlicoAcesso conecta cidadãos e unidades públicas de saúde participantes** para facilitar a descoberta de **onde um medicamento ou insumo está disponível, quando a informação foi atualizada, quais são as regras de retirada e, quando permitido, como solicitar uma reserva antes do deslocamento**.

### Cenário ilustrativo

> **Cenário fictício:** Ana depende da rede pública para retirar regularmente um insumo relacionado ao tratamento do diabetes. Antes de sair de casa, ela precisa saber qual unidade próxima fornece o item, se há disponibilidade, em que horário pode retirá-lo e quais documentos precisa levar. Sem uma forma simples de consultar essas informações, ela pode não conseguir contato por telefone ou descobrir, apenas ao chegar, que o item não está disponível ou que a retirada depende de outro procedimento.
>
> No GlicoAcesso, Ana pesquisa o item, visualiza as unidades participantes próximas, consulta a data de atualização da disponibilidade e as orientações para retirada. Quando a unidade permitir, solicita uma reserva e acompanha a confirmação antes de se deslocar.

Esse cenário representa a dificuldade que a plataforma pretende reduzir. O GlicoAcesso organiza a informação e o fluxo de acesso, mas não garante que o item exista em estoque nem substitui o funcionamento da rede pública.

### Público beneficiado

- Pessoas com diabetes que dependem do SUS.
- Familiares e cuidadores responsáveis pelos medicamentos.
- Profissionais de farmácias públicas e unidades de saúde.
- Gestores municipais de saúde.

## Problema e motivação

Pessoas com diabetes podem precisar retirar medicamentos e insumos de forma contínua. A rede pública tem papel importante nesse acesso, mas a dispensação é descentralizada: unidades e localidades podem ter disponibilidades, horários, documentos exigidos e critérios de retirada distintos.

O problema que o GlicoAcesso enfrenta **não é a existência do direito ao atendimento nem a falta nacional de medicamentos**. É uma barreira mais específica: **a dificuldade de descobrir, antes do deslocamento, onde e como obter um item informado como disponível na rede pública participante**.

Na prática, o cidadão precisa descobrir:

- qual unidade próxima fornece o medicamento ou insumo;
- se a disponibilidade foi informada recentemente;
- quando essa informação foi atualizada;
- qual é o horário de retirada;
- quais documentos ou requisitos são necessários;
- se é possível solicitar uma reserva;
- quais alternativas próximas existem caso aquela unidade não possa atender.

Quando esses dados estão dispersos, desatualizados ou difíceis de localizar, podem ocorrer deslocamentos sem sucesso, gasto desnecessário de tempo e transporte e atraso na retirada. O impacto tende a ser maior para pessoas de baixa renda, sem plano de saúde, com mobilidade reduzida ou que vivem longe das unidades de dispensação.

### Evidências que fundamentam o problema

Em 2024, a International Diabetes Federation estimou cerca de **16,6 milhões de adultos com diabetes no Brasil**, equivalentes a 10,6% da população adulta. Esse dado dimensiona o público potencial, mas não é usado como prova de dificuldade de acesso.

As evidências que sustentam a formulação do problema são:

- Estudo de 2024, com dados da Pesquisa Nacional de Saúde, identificou que **69,7% da obtenção de insulina analisada ocorreu pelo serviço público** e apontou desigualdades de acesso associadas a fatores como renda, raça/cor e ausência de plano de saúde.
- O Ministério da Saúde informa que as insulinas e agulhas são distribuídas às secretarias estaduais e municipais e que, após o recebimento, as localidades são responsáveis pela distribuição, armazenamento e dispensação. A mesma fonte registra particularidades e critérios locais de dispensação.
- Pesquisa nacional realizada em 273 municípios encontrou **disponibilidade média de 52,9% para medicamentos traçadores na atenção primária do SUS**, além de diferenças regionais e relato de falta de medicamentos sempre ou repetidamente por 38,0% dos responsáveis pela dispensação. O estudo não mede especificamente insulina ou medicamentos para diabetes; por isso, é utilizado apenas como evidência de desafios gerais de disponibilidade e gestão da assistência farmacêutica.
- A Lei nº 14.654/2023 exige a divulgação on-line dos estoques de medicamentos das farmácias públicas do SUS, com atualização quinzenal e apresentação acessível ao cidadão. A necessidade de tornar essa informação fácil de localizar e utilizar é uma inferência a partir da exigência legal e da organização descentralizada da dispensação.

Também há evidência de que o acesso não é universalmente baixo: a PNAUM encontrou alto acesso autorreferido a hipoglicemiantes não insulínicos prescritos. Portanto, o projeto **não parte da premissa de que todas as pessoas com diabetes deixam de obter seus medicamentos**.

As desigualdades de acesso possuem causas amplas e estruturais e não podem ser solucionadas por uma plataforma digital. O GlicoAcesso atua apenas sobre a incerteza descrita acima, sem pretender resolver essas causas.

### Delimitação

O GlicoAcesso:

- não fabrica, compra ou distribui medicamentos;
- não garante disponibilidade nacional ou local de estoque;
- não realiza diagnóstico;
- não recomenda doses;
- não altera prescrições;
- não substitui profissionais de saúde;
- não pretende resolver todas as causas das desigualdades de acesso a medicamentos.

Sua atuação é **facilitar a localização, a organização e o acompanhamento do acesso aos itens disponíveis nas unidades participantes**.

## Esboço da solução

O GlicoAcesso será uma plataforma com **dois lados complementares**: um voltado ao cidadão e outro às unidades de saúde participantes. O cidadão consulta opções e acompanha uma eventual reserva; os profissionais mantêm os dados de disponibilidade e retirada e gerenciam as solicitações.

### Como a plataforma funcionaria

**1. A unidade informa a disponibilidade.**  
A unidade participante mantém informações sobre os itens que disponibiliza, horário, requisitos de retirada e data da última atualização.

**2. O cidadão pesquisa o item.**  
O usuário informa o medicamento ou insumo previamente prescrito e visualiza as unidades participantes que o disponibilizam.

**3. O sistema apresenta as opções.**  
Para cada unidade, são exibidos endereço, distância, horário, disponibilidade informada, data da última atualização e requisitos para retirada.

**4. Quando permitido, o cidadão solicita uma reserva.**  
A solicitação é enviada à unidade, que pode confirmá-la ou rejeitá-la conforme a disponibilidade e as regras locais.

**5. O cidadão acompanha até a retirada.**  
Após a confirmação, o usuário visualiza o status da solicitação e as orientações para comparecer à unidade.

### Jornada do cidadão

1. Informa o medicamento ou insumo prescrito.
2. Compara unidades participantes próximas e os dados de disponibilidade, atualização, endereço, horário e requisitos.
3. Quando permitido, solicita uma reserva e acompanha a confirmação.
4. Realiza a retirada na unidade ou consulta alternativas participantes caso ela não possa atender.

### Jornada da unidade de saúde

1. Mantém disponibilidade, horários e requisitos atualizados.
2. Visualiza solicitações recebidas e confirma ou rejeita cada uma conforme as regras locais.
3. Registra as retiradas e acompanha demanda, indisponibilidades e itens próximos do vencimento.

### Origem e atualização das informações

No protótipo acadêmico, os dados serão **simulados** e as unidades participantes poderão atualizá-los pelo próprio sistema.

Em uma implantação real, o modelo poderia combinar, conforme a infraestrutura de cada rede:

- atualização manual por profissionais autorizados;
- importação periódica de dados;
- integração com sistemas de gestão de estoque já existentes, quando possível.

Em todos os casos, a plataforma deverá exibir claramente **quando a informação foi atualizada**, evitando apresentar uma disponibilidade antiga como confirmação em tempo real.

### Escopo inicial proposto

O GlicoAcesso pode começar em **uma rede municipal ou conjunto de unidades participantes**, deixando explícito ao cidadão quais estabelecimentos fazem parte da plataforma. O valor do sistema tende a aumentar conforme novas unidades aderem e compartilham informações atualizadas; não é necessário depender da adesão de todas as unidades do país.

## Impacto social esperado

O impacto pretendido pelo GlicoAcesso não é “resolver o desabastecimento”, mas **reduzir a incerteza e o custo de encontrar e retirar um item disponível na rede participante**.

Os beneficiários diretos incluem pessoas de baixa renda, idosos, pessoas sem plano de saúde, moradores afastados das unidades de distribuição, familiares e cuidadores responsáveis pela retirada.

Os efeitos esperados são:

- menos tempo gasto procurando onde um item está disponível;
- menos deslocamentos até unidades que não podem atender à solicitação;
- maior clareza sobre horários, documentos e requisitos;
- maior previsibilidade quando houver possibilidade de reserva;
- melhor organização das solicitações e retiradas pelas unidades;
- maior visibilidade da demanda e das indisponibilidades para os gestores.

### Como o impacto poderá ser medido

Os indicadores abaixo estão diretamente relacionados aos resultados esperados:

| Problema ou objetivo | Indicador | Como será medido |
| --- | --- | --- |
| Dificuldade para localizar o item | **Tempo para localizar uma unidade apta** | Tempo médio entre o início da busca e a identificação de uma unidade participante que informe disponibilidade |
| Deslocamentos improdutivos | **Taxa de deslocamentos sem sucesso** | Percentual de usuários que, mesmo após selecionar uma unidade pela plataforma, não conseguem realizar a retirada |
| Incerteza na solicitação | **Taxa de reservas confirmadas** | Reservas confirmadas em relação ao total de solicitações realizadas |
| Demora entre busca e acesso | **Tempo entre solicitação e retirada** | Intervalo médio entre a solicitação de reserva e o registro da retirada |
| Continuidade do uso da rede | **Continuidade das retiradas** | Frequência com que usuários que necessitam de retirada recorrente conseguem registrar novas retiradas no período esperado |
| Organização da unidade | **Solicitações atendidas e não atendidas** | Quantidade e proporção de solicitações concluídas, rejeitadas ou expiradas por unidade |
| Experiência do cidadão | **Satisfação do usuário** | Avaliação simples após a retirada ou encerramento da solicitação |

Indicadores como perdas por vencimento podem ser acompanhados futuramente pelas unidades, mas não são considerados um efeito direto garantido da plataforma nesta etapa.

O grupo pretende contribuir para a continuidade do cuidado, mas **não atribui diretamente ao GlicoAcesso a redução de amputações, internações ou mortes**, pois esses resultados dependem de múltiplos fatores clínicos, sociais e estruturais externos ao sistema.

## Pitch de cinco minutos

O roteiro abaixo apresenta primeiro **a situação concreta do cidadão**, depois **por que ela ocorre**, **como o GlicoAcesso funciona** e **qual impacto pretende gerar**.

A duração-alvo continua entre **4min30s e 4min50s**, permitindo pequena margem para pausas e troca entre os quatro integrantes.

### Integrante 1 - Situação concreta e problema

> Imagine uma pessoa com diabetes que precisa retirar regularmente um medicamento ou insumo pela rede pública. Antes de sair de casa, ela precisa responder a perguntas simples: em qual unidade esse item está disponível? Quando essa informação foi atualizada? Qual é o horário de retirada? Que documentos precisa levar?
>
> Quando essas informações não são fáceis de localizar, o cidadão pode se deslocar até uma unidade e descobrir apenas no local que o item não está disponível ou que a retirada depende de outro procedimento. Isso significa tempo perdido, gasto com transporte e possível atraso na retirada.
>
> Foi para reduzir essa incerteza que surgiu o **GlicoAcesso**: uma plataforma que conecta cidadãos a unidades públicas de saúde participantes para facilitar a localização, a reserva e o acompanhamento da retirada de medicamentos e insumos para diabetes.

### Integrante 2 - Evidências e relevância social

> O problema é relevante porque o tratamento do diabetes envolve uma população numerosa e a rede pública tem papel importante nesse acesso. A International Diabetes Federation estimou cerca de **16,6 milhões de adultos com diabetes no Brasil em 2024**.
>
> Um estudo publicado em 2024, com dados da Pesquisa Nacional de Saúde, identificou que **69,7% da obtenção de insulina analisada ocorreu pelo serviço público** e encontrou desigualdades de acesso associadas a fatores como renda, raça/cor e ausência de plano de saúde.
>
> Além disso, o Ministério da Saúde informa que, após a distribuição federal de insulinas e agulhas, estados e municípios assumem responsabilidades de distribuição, armazenamento e dispensação, com particularidades locais. Isso ajuda a explicar por que o cidadão pode precisar lidar com diferentes unidades, regras e disponibilidades.
>
> O GlicoAcesso não pretende resolver todas as desigualdades de acesso nem criar estoque onde ele não existe. Ele atua sobre uma barreira específica: **a dificuldade de descobrir onde e como acessar o que está disponível**.

### Integrante 3 - Como a solução funciona

> O GlicoAcesso possui dois lados.
>
> Para o cidadão, a experiência começa com uma busca pelo medicamento ou insumo previamente prescrito. A plataforma mostra as unidades participantes próximas, a disponibilidade informada, a data da última atualização, endereço, horário e requisitos para retirada.
>
> Quando a unidade permitir, o cidadão também poderá solicitar uma reserva e acompanhar sua confirmação antes de se deslocar.
>
> Do outro lado, profissionais das unidades participantes mantêm essas informações atualizadas, visualizam solicitações, confirmam ou rejeitam reservas e registram as retiradas.
>
> No protótipo acadêmico, os dados serão simulados. Em uma implantação real, a plataforma poderia combinar atualização manual com integração aos sistemas de estoque já utilizados pelas redes de saúde.

### Integrante 4 - Impacto, legislação e encerramento

> O impacto do GlicoAcesso será medido por resultados diretamente ligados ao problema: quanto tempo o usuário leva para localizar uma unidade apta, quantos deslocamentos terminam sem retirada, quantas solicitações são atendidas e quanto tempo passa entre a solicitação e a retirada.
>
> A proposta também dialoga com a **Lei nº 14.654/2023**, que exige a divulgação on-line dos estoques das farmácias públicas do SUS. O GlicoAcesso parte dessa necessidade de transparência e busca transformar a informação disponível em uma experiência mais simples de utilizar.
>
> Nosso objetivo não é substituir a rede pública, fazer diagnóstico ou garantir que todos os medicamentos estejam disponíveis. É reduzir a distância entre **existir um recurso na rede e o cidadão conseguir descobrir onde, quando e como acessá-lo**.
>
> **GlicoAcesso: encontre, reserve e continue seu cuidado.**

## Referências

1. [International Diabetes Federation - Dados sobre diabetes no Brasil](https://diabetesatlas.org/es/data-by-location/country/brazil/). Estimativa de 16,6 milhões de adultos com diabetes em 2024.
2. [Leal et al. - Acesso a medicamentos para hipertensão e diabetes](https://doi.org/10.1590/0102-311XPT241022). *Cadernos de Saúde Pública*, 2024.
3. [Nascimento et al. - Disponibilidade de medicamentos essenciais](https://doi.org/10.11606/S1518-8787.2017051007062). *Revista de Saúde Pública*, 2017.
4. [Ministério da Saúde - Insulinas humanas e agulhas para caneta](https://www.gov.br/saude/pt-br/composicao/sectics/daf/cbaf/insulinas-humanas).
5. [Brasil - Lei nº 14.654/2023](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2023/lei/l14654.htm).
6. [PNAUM - Acesso e adesão a medicamentos entre pessoas com diabetes no Brasil](https://doi.org/10.1590/1980-549720180003). *Revista Brasileira de Epidemiologia*, 2018.

