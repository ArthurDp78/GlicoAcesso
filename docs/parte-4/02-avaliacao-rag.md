# Avaliação pareada do RAG

## Método

Foram definidas seis perguntas antes da execução. Elas cobrem solicitação, confirmação, retirada, cancelamento, disponibilidade atual e um assunto fora da base. Cada pergunta é enviada duas vezes ao mesmo modelo, com os mesmos parâmetros de amostragem nas duas condições, o mesmo prompt, o mesmo esquema de saída e o mesmo retrato de disponibilidade obtido do BFF. A condição sem recuperação recebe uma lista vazia de trechos. A condição com recuperação recebe até quatro trechos do índice, com distância de cosseno de até 0,60.

O roteiro registra as respostas estruturadas brutas e verifica se os IDs citados pertencem aos trechos entregues ao modelo. A avaliação também lê o texto para verificar se ele atende ao critério do caso e se as citações sustentam a resposta. As duas condições chamam o modelo mesmo com uma lista vazia, para medir o efeito dos trechos sobre a geração. Na rota do portal, a ausência de trechos aciona diretamente a orientação básica.

A avaliação marca **atende** quando a resposta cobre o critério por completo, **parcial** quando oferece orientação útil com omissão ou erro e **não atende** quando falta a instrução pedida ou há erro que compromete seu uso. Para a pergunta fora da base, a abstenção com informação insuficiente ou indicação de escopo é o resultado correto. Identificadores ausentes dos trechos enviados são inválidos. Uma lista vazia de citações indica ausência de citação a verificar.

## Reprodução com a configuração do projeto

Suba o BFF e o banco vetorial, indexe os guias e configure a chave e os modelos conforme o guia da Parte 4. Com o perfil de orientação em execução, o comando abaixo usa o BFF interno e o índice do serviço. Execute no PowerShell 7 a partir da raiz do clone.

```powershell
docker compose -f docker-compose.yml -f compose.orientacao.yml --profile orientacao exec -T orientacao python -m servicos.orientacao.avaliacao > avaliacao-rag-google-ai-studio.json
```

Para reproduzir a avaliação local com Ollama, disponibilize um BFF, migre uma instância vetorial descartável com `python -m servicos.migracoes orientacao`, configure `ORIENTACAO_DATABASE_URL` e execute:

```powershell
uv run --locked --group orientacao python -m servicos.orientacao.avaliacao --bff-url http://127.0.0.1:8001 --ollama-url http://127.0.0.1:11434 --saida avaliacao-rag-ollama.json
```

O modo local usa `qwen2.5:3b` para geração e `qwen3-embedding:0.6b` para vetorização. Ele preenche as dimensões restantes com zeros para usar a coluna de 1536 dimensões, preservando a distância de cosseno. O modo local usa um índice próprio e a interface nativa do Ollama. [Modelo de embeddings local](https://ollama.com/library/qwen3-embedding:0.6b) · [Modelo de geração local](https://ollama.com/library/qwen2.5:3b).

## Resultado da execução local

O experimento usou os dois modelos locais, PostgreSQL para Unidades e Estoque e pgvector em PGlite para a base documental. O BFF informou uma unidade de demonstração com disponibilidade e permissão de reserva. Ambos os modos receberam o mesmo dado. Os IDs, os textos completos e a versão da base estão na [evidência JSON da execução](./avaliacao-rag-ollama.json).

| Caso | Sem recuperação | Com recuperação | Resposta aceita pela chain no modo com recuperação |
|---|---|---|---|
| Solicitação e código | **Não atende.** Inventou solicitação por telefone ou e-mail, envio do código por mensagem e a fonte `fonte1`. | **Atende.** Explicou a ação no portal, a credencial, a quantidade e o código gerado. Citou `solicitacao#enviar`. | Sim. |
| Confirmação em processamento | **Não atende.** Sugeriu consultar o balcão sem orientar a aguardar. | **Parcial.** Orientou aguardar `CONFIRMADA` e consultar o portal. Acrescentou contato com a unidade sem apoio dos trechos e citou a seção de confirmação malsucedida, embora a seção correta estivesse entre as recuperadas. | Não. O modelo marcou `sem_evidencia`. |
| Retirada no balcão | **Não atende.** Sem orientação. | **Atende no texto.** Indicou conferir a confirmação, respeitar as orientações da unidade e levar o código. O modelo marcou `sem_evidencia` e omitiu a citação. | Não. |
| Cancelamento em processamento | **Não atende.** Sugeriu procurar atendimento ao cliente e omitiu a ação no portal. | **Atende no texto.** Indicou cancelar pelo botão, quando disponível, e consultar novamente pelo código. Citou `solicitacao#cancelar` e marcou `sem_evidencia`. | Não. |
| Disponibilidade e permissão | **Parcial.** Identificou a unidade pelos dados do BFF. Usou o objeto da API como citação e deixou impreciso como verificar as duas condições no portal. | **Atende no texto.** Identificou a unidade, distinguiu disponibilidade e permissão e explicou onde solicitar. O modelo marcou `sem_evidencia` e omitiu a citação. | Não. |
| Segunda via do cartão de transporte | **Atende.** Sinalizou informação insuficiente. | **Atende.** A busca trouxe zero trechos e a geração também sinalizou informação insuficiente no experimento. | A chain retorna orientação básica. |

A busca recuperou a seção esperada nos cinco casos operacionais e nenhum trecho no caso fora da base. **Na análise do texto bruto, a recuperação passou de 1 para 5 respostas que atendem integralmente entre os seis casos.** Entre os cinco casos operacionais, porém, só **uma** resposta com recuperação passou pelas regras de publicação da chain. As outras quatro seriam substituídas pela orientação básica. O resultado aponta uma dificuldade em alinhar o estado e as citações ao texto gerado. A validade do ID da citação, por si só, também não garante que a seção sustente a afirmação, como ocorreu no caso de confirmação.

O experimento mede esta base, estes seis casos e estes modelos. A execução com Gemini via Google AI Studio depende de `GOOGLE_API_KEY`. Use o comando de reprodução para obter as respostas dessa configuração antes de atribuir a ela o resultado observado no Ollama.

## Resultado com Gemini no projeto atual

Foram concluídos os seis pares com `gemini-3.5-flash-lite`, os oito trechos indexados com `gemini-embedding-2` em pgvector sobre PGlite e uma consulta real pelo Gateway ao BFF. O item consultado retornou uma lista vazia de unidades. Cada par usou o mesmo retrato para as duas condições. Os pares concluídos foram reunidos após falhas temporárias de geração e limites do provedor. A amostra de qualidade exclui essas tentativas interrompidas. [Respostas, fontes e uso de tokens](./avaliacao-rag-gemini.json)

| Pergunta | Sem guias | Com guias |
|---|---|---|
| Solicitação | Abstenção | Indicou credencial, quantidade, envio e código. A redação trata as duas telas como alternativas, embora o guia as apresente em sequência. |
| Confirmação | Abstenção | Indicou aguardar CONFIRMADA e citou o guia correto. Faltou explicar a consulta pelo código. |
| Retirada | Abstenção | Indicou verificar o estado, ler as instruções da unidade e levar o código. |
| Cancelamento | Abstenção | Explicou quando usar o botão e como acompanhar o processamento pelo código. |
| Disponibilidade | Abstenção | Explicou os dois critérios e citou o guia, mas omitiu que a consulta atual não encontrou unidades. |
| Cartão de transporte | Fora do escopo | Fora do escopo. A busca trouxe quatro trechos pouco pertinentes e o modelo se absteve. |

Os cinco casos operacionais recuperaram e citaram a seção esperada. As citações e o estado estruturado permitem publicar as cinco respostas pelas regras da chain. A revisão de conteúdo encontrou omissões em confirmação e disponibilidade e uma imprecisão de navegação na solicitação.
