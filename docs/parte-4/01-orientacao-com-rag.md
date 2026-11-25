# Orientação ao cidadão com RAG

## Escopo

O portal cidadão oferece orientação em português para um item selecionado no catálogo. O cidadão pode perguntar onde consultar disponibilidade, como solicitar e acompanhar uma reserva ou como retirar o item. A conversa tem uma pergunta por requisição. Perguntas clínicas, posologia, substituição de medicamento e consultas a reservas individuais recebem uma indicação de escopo e o caminho adequado no portal. A operação é somente de leitura.

A base própria será versionada em Markdown e descreverá consulta, solicitação, confirmação e retirada no GlicoAcesso. Disponibilidade e permissão de reserva vêm da projeção lida pela API. A interface exibe o horário informado pela projeção. Uma unidade elegível para solicitação precisa ter `disponivel` e `permiteReserva` verdadeiros. A disponibilidade pode mudar e o aceite da unidade continua sujeito à SAGA. A API atual informa disponibilidade booleana por item e unidade. A orientação não deduz quantidades ou promete atendimento.

## Arquitetura e dependências

- **HTTP** · Portal → Gateway → BFF Cidadão → serviço Orientação (FastAPI). O serviço é interno, com credencial entre serviços. O BFF usa o mecanismo de autenticação do cidadão existente e repassa o identificador de correlação. Para demonstração, a rota tem limitação de chamadas por cidadão e de concorrência no serviço.
- **Ferramenta LangChain** · `consultar_disponibilidade` recebe o UUID validado pelo servidor. A chain executa a ferramenta de leitura e fornece o resultado ao modelo. A ferramenta reutiliza `GET /api/cidadao/v1/explorar?itemId=…` diretamente no BFF. O caminho de consulta termina em Unidades e na projeção de Estoque. As chamadas são assíncronas e o BFF não depende da saúde de Orientação para iniciar.
- **Geração e embeddings** · Google AI Studio via `langchain-google-genai`. O padrão usa `gemini-3.5-flash-lite` para geração e `gemini-embedding-2` com saída de 1536 dimensões para indexação e consulta. Configure os modelos por ambiente e `GOOGLE_API_KEY` no serviço Orientação e no indexador. A aplicação fixa a API Gemini Developer (AI Studio), sem selecionar Vertex AI. O provedor recebe a pergunta operacional, os trechos próprios e os dados públicos relevantes. Tokens de autenticação e códigos de reserva não integram o contexto. O portal orienta a não incluir dados pessoais, e a entrada passa por validação antes do envio ao provedor. [Integração LangChain Gemini](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai) · [Embeddings Gemini](https://docs.langchain.com/oss/python/integrations/embeddings/google_generative_ai) · [Modelos Gemini](https://ai.google.dev/gemini-api/docs/models).
- **Base vetorial** · PostgreSQL 17 com pgvector em instância própria, em volume nomeado e rede privada com Orientação. Reutilizar Psycopg 3 com o cliente Python do pgvector. Para a base pequena inicial, usar busca exata por distância de cosseno. Persistir ID estável, versão, caminho do documento, seção, conteúdo, modelo e vetor. Alteração de modelo ou dimensão exige reindexação. [pgvector](https://github.com/pgvector/pgvector) · [Cliente Python](https://github.com/pgvector/pgvector-python).
- **Compose** · Conectar Orientação ao BFF pela rede interna e dar saída HTTPS ao provedor por uma rede adicional sem porta publicada. A inicialização e as consultas atuais do BFF permanecem independentes do provedor, do índice e de Orientação.

Fluxo da chain em LangChain Core: validação de escopo → recuperação de trechos mais consulta de disponibilidade → montagem do contexto → geração estruturada → validação de citações. A aplicação controla a execução da ferramenta, os argumentos e o conjunto de fontes permitidas. As unidades retornadas no JSON são montadas a partir do resultado validado da ferramenta. A resposta textual usa apenas esse contexto e cita identificadores de documentos recuperados. Dados dinâmicos têm origem indicada como API do GlicoAcesso. A aplicação gera o estado do RAG e da consulta, independentemente do texto do modelo.

## Contrato proposto

`POST /api/cidadao/v1/orientacoes` via Gateway, com a credencial do cidadão. Corpo JSON de exemplo:

```json
{
  "itemId": "20000000-0000-4000-8000-000000000001",
  "pergunta": "Onde posso reservar tiras reagentes e como faço para retirá-las?"
}
```

Validar `itemId` como UUID de item do catálogo e `pergunta` como texto de 1 a 500 caracteres após remoção de espaços nas bordas. O servidor rejeita campos extras. O UUID da requisição é o item de demonstração. A unidade, o horário da projeção e as fontes do exemplo são ilustrativos.

```json
{
  "modo": "rag",
  "resposta": "A Unidade de Demonstração tem disponibilidade e aceita solicitações de reserva para o item selecionado. Solicite pelo portal, aguarde a confirmação e apresente-a no balcão.",
  "fontes": [
    {"id": "retirada#balcao", "titulo": "Retirada no balcão", "secao": "Como retirar"}
  ],
  "consulta": {
    "status": "consultada",
    "unidades": [
      {
        "unidadeId": "10000000-0000-4000-8000-000000000001",
        "nomeUnidade": "Unidade de Demonstração",
        "disponivel": true,
        "permiteReserva": true,
        "atualizadoEm": "2026-11-25T13:00:00Z"
      }
    ]
  }
}
```

- `200` usa `modo` igual a `rag`, `orientacao_basica` ou `fora_do_escopo`. A consulta pode estar `consultada`, `indisponivel` ou `nao_consultada`. Lista vazia após consulta bem-sucedida significa que a API não retornou unidades para o item. Falhas de consulta têm estado próprio.
- `401/403` para credencial ausente, inválida ou de papel incompatível conforme a política atual do Gateway. `404` para item inexistente confirmado pelo catálogo, `422` para entrada inválida e `429` para limite de chamadas. `503` fica reservado para impossibilidade de atender até a resposta básica.
- Em falha do provedor ou falta de evidência, retornar orientação básica determinística e acesso à consulta convencional. A resposta inclui dados reais se a ferramenta tiver sucesso e distingue dados ausentes de ausência de disponibilidade.
- Na implementação, reservar 12 s totais em Orientação; o BFF e o Gateway têm prazos maiores (14 s e 19 s). A API Gemini exige prazo de pelo menos 10 s para a geração, enquanto o prazo total de Orientação continua impondo o limite final. Aplicar retry/backoff apenas a falhas transitórias dentro do prazo total e fornecer fallback. Ajustar os prazos com a medição da 7.9.

## Verificação e dependências das próximas subtarefas

Os quatro guias estão versionados junto ao código. A primeira indexação requer uma chave válida do Google AI Studio. A avaliação compara seis perguntas com e sem recuperação e registra o comportamento do provedor escolhido.


## Base de conhecimento

A base inicial está em [base-conhecimento](./base-conhecimento/). Os quatro guias tratam de [disponibilidade](./base-conhecimento/disponibilidade.md), [solicitação](./base-conhecimento/solicitacao.md), [confirmação](./base-conhecimento/confirmacao.md) e [retirada](./base-conhecimento/retirada.md).

Cada guia tem um título, uma versão e uma seção de fontes. O nome do arquivo sem extensão identifica o documento. Cada título de nível 2 indexável tem uma âncora explícita que deve permanecer estável quando o texto mudar. Use o identificador no formato `documento#ancora` nas citações. Por exemplo, `retirada#balcao` aponta para [Como retirar](./base-conhecimento/retirada.md#balcao). Na ingestão, trate cada seção de nível 2 como a unidade inicial de recuperação. Guarde a seção **Fontes** como metadado e exclua seus links do texto enviado para embeddings.

## Indexar a base de conhecimento

Para criar o índice do zero em um clone, execute os comandos na raiz do repositório com o Docker Desktop aberto. Defina `ORIENTACAO_DB_PASSWORD` no `.env` local com um valor hexadecimal aleatório e conserve o mesmo valor enquanto usar o volume. No PowerShell 7, informe a chave do provedor em uma entrada mascarada.

```powershell
$env:GOOGLE_API_KEY = Read-Host -MaskInput 'Chave da API Google AI Studio'
docker compose -f docker-compose.yml -f compose.orientacao.yml --profile indexacao run --build --rm indexar-orientacao
```

Esse comando sobe o PostgreSQL com pgvector, aplica a migração e carrega os guias do clone. O comando imprime o total de seções, os embeddings gerados e as seções removidas. O banco conserva o índice no volume nomeado. Repita o comando após alterar ou remover guias. O indexador reaproveita vetores quando o conteúdo e o modelo permanecem iguais. Se a geração falhar, o índice anterior continua disponível. O modelo configurado deve produzir vetores de 1536 dimensões; ao trocar o modelo de embeddings, execute novamente a ingestão antes de consultar o índice.

O indexador também pode rodar no host com Python 3.14 e `uv`. Configure `ORIENTACAO_DATABASE_URL` para uma instância dedicada com pgvector instalado e permissões para aplicar a migração.

```powershell
uv run --locked --group orientacao python -m servicos.orientacao.ingestao
```

O argumento `--pasta` permite sincronizar uma cópia da base em ambiente de teste. Use uma instância dedicada à base informada, pois a sincronização remove do índice as seções ausentes dessa pasta.

## Consultar a chain de RAG

Depois de indexar os guias, configure `ORIENTACAO_DATABASE_URL` e `GOOGLE_API_KEY` no ambiente Python que tem acesso ao banco. Use o mesmo `ORIENTACAO_MODELO_EMBEDDING` da ingestão. Para chamar a chain internamente, use `criar_chain_configurada().invoke(pergunta)` de `servicos.orientacao.rag`. O modelo de geração pode ser configurado por `ORIENTACAO_MODELO_GERACAO`.

A recuperação seleciona até quatro seções do modelo ativo, em ordem de distância de cosseno. O corte inicial é 0,60 e será revisto com a avaliação da base. Quando a consulta não obtém trechos dentro do corte, a chain devolve orientação básica sem chamar o modelo de geração. Quando há trechos, o LangChain pede uma saída estruturada. A aplicação só retorna citações cujos IDs correspondem às seções recuperadas. Uma saída sem evidência, inválida ou com citações desconhecidas recebe orientação básica sem fontes.

Execute os testes da chain com `uv run --locked --group orientacao python -m unittest tests.orientacao_rag`.

## Consultar disponibilidade na chain

A integração interna usa `criar_chain_com_disponibilidade(cliente, origem_bff)` e executa a chain com `await chain.ainvoke(PerguntaSobreItem(pergunta, itemId))`. Passe um cliente HTTP assíncrono gerenciado pelo chamador e a origem interna do BFF. A chain chama a ferramenta LangChain `consultar_disponibilidade` com o UUID do item selecionado. A ferramenta faz uma leitura de `/api/cidadao/v1/explorar` a cada pergunta.

A fonte de disponibilidade é a projeção do Estoque servida pelo BFF. A chain passa ao modelo o estado da consulta, as unidades, os indicadores de disponibilidade e permissão e o horário da projeção. Ela devolve esses dados separadamente da resposta textual, preservando a diferença entre consulta sem unidades e erro de consulta. A atualização aparece na próxima pergunta após a projeção convergir. Os guias continuam sendo a fonte de instruções operacionais.

Execute os testes da ferramenta e da chain com `uv run --locked --group orientacao python -m unittest tests.orientacao_rag tests.orientacao_disponibilidade`. A rota HTTP e a configuração do portal estão descritas a seguir.

## Executar a orientação no portal

No `.env` do projeto, configure `ORIENTACAO_DB_PASSWORD` e `GLICO_ORIENTACAO_SERVICE_TOKEN` com valores hexadecimais distintos. A credencial interna precisa ter pelo menos 32 caracteres. Configure a chave do provedor, indexe a base com o comando acima e suba o sistema com o perfil de orientação usando a mesma combinação de arquivos Compose. Assim, a indexação e o serviço usam o mesmo volume.

```powershell
docker compose -f docker-compose.yml -f compose.orientacao.yml --profile orientacao up --build -d --wait
```

No portal do cidadão, informe o token de demonstração em **Minhas reservas**, selecione um item e use **Pedir orientação**. O contrato da rota está no [OpenAPI do BFF Cidadão](../parte-2/api/bff-cidadao.yaml). A resposta distingue as fontes dos guias e a disponibilidade consultada na API. O serviço Orientação e seu banco são internos. Somente o Gateway publica uma porta no host.

Para o ambiente de demonstração, o BFF aceita até dez consultas por cidadão por janela de um minuto em cada processo. Orientação aceita até três chamadas simultâneas. O BFF e o Gateway têm prazos próprios para a rota.

### Resiliência do provedor

A orientação tem prazo total de 12 segundos, a partir do início da consulta ao BFF. A ferramenta usa até 3 segundos. Cada tentativa de embedding usa até 2,5 segundos. A API Gemini requer um prazo de pelo menos 10 segundos por chamada de geração; o prazo total de 12 segundos continua limitando a duração efetiva da orientação. Para falhas de conexão, timeout, HTTP 408, 429 transitório ou 5xx, a aplicação faz até duas novas tentativas, aguardando pelo menos 250 e 500 milissegundos. A política respeita o cabeçalho `Retry-After`. Se a espera indicada atingir o prazo de uma tentativa, a etapa desiste e aciona o fallback. Erros de credencial e falta de cota do provedor seguem direto para a orientação básica. O SDK tem as tentativas automáticas desativadas nas chamadas da rota.

Quando a IA ou a base vetorial está indisponível, o serviço retorna HTTP 200 com `modo: orientacao_basica`, instruções fixas sobre onde continuar no portal e as unidades consultadas pela API. Esse modo também funciona quando o serviço inicia sem chave. Se a própria consulta de disponibilidade falhar, o campo `consulta.status` informa `indisponivel`. As operações convencionais do portal seguem disponíveis pelo Gateway.

Para verificar as regras de retry e o fallback com falhas simuladas, execute:

```powershell
uv run --locked --group orientacao python -m unittest tests.orientacao_resiliencia
```

## Avaliar a qualidade do RAG

Use a bateria de seis perguntas e o roteiro de reprodução no [relatório da avaliação pareada](./02-avaliacao-rag.md).

## Medir latência e projetar custo

O [relatório de desempenho da orientação](./03-desempenho-e-custo.md) registra o método, as amostras por etapa e pelo Gateway, o consumo de tokens e a projeção com as tarifas Standard da OpenAI.
