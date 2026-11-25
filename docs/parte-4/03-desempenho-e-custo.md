# Desempenho e custo da orientação com RAG

## Como a medição foi feita

A execução de 25/11/2026 usou duas rodadas das seis perguntas da avaliação de qualidade, chamadas sequenciais e relógio monotônico. Unidades, Estoque e BFF Cidadão foram executados com PostgreSQL local. O índice usou pgvector em PGlite. Os modelos reais executados no Ollama foram `qwen3-embedding:0.6b` e `qwen2.5:3b`. As medições cobrem a consulta HTTP ao BFF, o embedding da pergunta, a busca vetorial, a geração e a validação do resultado. As métricas de tokens locais vêm dos campos reportados pelo Ollama. [Dados das amostras](./medicao-rag-ollama.json)

O total por etapa vai da execução da ferramenta até o resultado da chain. O teste foi sequencial e serve para diagnóstico na máquina atual. O p50 é a mediana e o p95 usa o posto mais próximo por arredondamento para cima. Com amostra pequena, o p95 coincide com a pior observação. A coluna de geração considera as consultas que chamaram o modelo.

## Como repetir a medição

Use uma base vetorial descartável e o BFF real. No ambiente Python, configure `ORIENTACAO_DATABASE_URL`, indexe os guias em modo Ollama segundo a [avaliação de qualidade](./02-avaliacao-rag.md) e execute:

```powershell
uv run --locked --group orientacao python -m servicos.orientacao.desempenho --bff-url http://127.0.0.1:8001 --rodadas 2 --saida medicao-rag-ollama.json
```

## Tarifas históricas da projeção OpenAI

Tarifa Standard em USD por milhão de tokens, consultada em **25/11/2026**.

| Etapa | Modelo | Tarifa |
|---|---|---:|
| Embedding de documentos e perguntas | `text-embedding-3-small` | US$ 0,02 |
| Entrada de geração | `gpt-4.1-mini-2025-04-14` | US$ 0,40 |
| Saída de geração | `gpt-4.1-mini-2025-04-14` | US$ 1,60 |

[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini) · [Text Embedding 3 Small](https://developers.openai.com/api/docs/models/text-embedding-3-small)

O cálculo soma o custo dos três tipos de tokens. Para estimar o volume OpenAI, o script tokeniza os conteúdos de embedding com `cl100k_base` e aproxima as entradas e saídas de geração com `o200k_base`. A estimativa inclui mensagens e esquema JSON no prompt. O volume real de tokens cobrados pode variar com o empacotamento do provedor e o texto produzido. Os dados assumem a distribuição de perguntas da bateria e tarifas sem desconto de cache. A indexação é contabilizada à parte. Infraestrutura, rede, impostos e variação cambial ficam fora da estimativa.

## Latência com os prazos de produção

As 12 amostras instrumentadas daquela execução local mantiveram o prazo total de 12 segundos e o limite então configurado de 4 segundos por tentativa de geração. Esses dados são históricos e não representam a configuração atual do Gemini, que exige pelo menos 10 segundos por chamada de geração. Os tempos incluem os efeitos das novas tentativas no cliente. A geração inclui o tempo acumulado das tentativas, e a espera entre elas aparece em processamento da chain e validação.

| Etapa | Amostras | p50 | p95 |
|---|---:|---:|---:|
| Consulta ao BFF | 12 | 102 ms | 184 ms |
| Embedding da pergunta | 12 | 3.087 ms | 3.516 ms |
| Busca vetorial | 12 | 20 ms | 33 ms |
| Geração, incluindo novas tentativas | 10 | 8.055 ms | 11.060 ms |
| Processamento da chain e validação | 12 | 746 ms | 781 ms |
| Total da orientação | 12 | 12.005 ms | 12.015 ms |

Todas as dez perguntas operacionais que chegaram ao gerador atingiram o limite e receberam orientação básica. As duas perguntas fora da base pularam a geração e terminaram em 3,24 s e 3,63 s. O Ollama contabilizou 210 tokens de embedding das 12 consultas, média de 17,5. As gerações canceladas não devolveram seus contadores de tokens. A estimativa de entrada das tentativas abortadas consta na evidência para inspeção e não é usada como custo de uma resposta concluída.

## Latência da rota pública

Em uma rodada adicional, fiz seis requisições HTTP reais e sequenciais ao Gateway. Elas passaram por Gateway, BFF e serviço Orientação. Usei um adaptador de protocolo local para encaminhar as chamadas ao Ollama com os mesmos modelos. As seis requisições retornaram HTTP 200 em modo de orientação básica. As cinco perguntas operacionais levaram de **12,06 a 12,10 s**. A pergunta sem evidência terminou em **0,27 s**. Essa rodada mede um sistema local real e inclui as operações do Gateway e do BFF. Sua latência não representa um ambiente remoto da OpenAI. [Amostras da rota pública](./medicao-gateway-ollama.json)

## Janela local ampliada

Para observar a geração completa e seus contadores, a medição por etapa foi repetida com `--rodadas 1 --prazo-local 45` e uma saída JSON própria. Essa opção se aplica ao roteiro de medição. As configurações de prazo da rota pública continuam com os valores de produção.

Quatro das cinco gerações operacionais concluíram dentro da janela ampliada. A geração que restou atingiu 45 s. Na pergunta fora da base, a chain retornou orientação básica sem geração. O Ollama registrou **105 tokens de embedding, 4.224 de entrada e 619 de saída**. Os contadores de geração cobrem apenas as quatro chamadas concluídas. A mediana da geração concluída foi **8,89 s**, com variação de **4,44 a 18,86 s**. As quatro gerações concluídas ainda resultaram em orientação básica por causa das regras de validação da resposta local. Assim, medir a geração e medir uma resposta aceita são duas verificações distintas. [Amostras da janela ampliada](./medicao-rag-ollama-janela-ampliada.json)

## Estimativa de custo em escala

Nas quatro chamadas concluídas, a estimativa OpenAI por consulta foi de **17,75 tokens de embedding, 1.049,5 de entrada e 120 de saída**, em média. Esses valores representam uma consulta que chega à geração e recebe uma saída completa. A projeção pressupõe uma chamada concluída por consulta, com o mesmo perfil de tokens e as tarifas Standard.

| Volume | Custo estimado de consultas com geração |
|---|---:|
| 1 consulta | US$ 0,000612 |
| 1.000 consultas | US$ 0,61 |
| 10.000 consultas | US$ 6,12 |
| 100.000 consultas | US$ 61,22 |

A **indexação inicial** usa aproximadamente **1.126 tokens para 8 trechos**, com custo estimado de **US$ 0,0000225**. O custo de uma consulta que termina após o embedding, sem geração, é de cerca de **US$ 0,00000026** para a pergunta fora da base desta amostra. Novas tentativas podem aumentar o custo. Chamadas interrompidas podem consumir tokens sem devolver o contador ao cliente.

A medição local mostra que o limite de produção funciona e que o Ollama utilizado nesta máquina excedeu esse limite nos cinco casos operacionais medidos pelo Gateway. As estimativas de custo deste relatório são históricas e usam tarifas OpenAI.

## Gemini na rota de orientação

Em 25/11/2026, três consultas HTTP autenticadas passaram por Gateway, BFF Cidadão, Orientação, Unidades e Estoque em processos locais, com instâncias descartáveis de PGlite para os três bancos envolvidos e chamadas reais ao Gemini. As três retornaram HTTP 200 em modo RAG, disponibilidade consultada e a fonte `retirada#balcao`. Para a mesma pergunta, os tempos foram 1,739 s, 1,376 s e 7,356 s. A mediana foi **1,739 s**. A amostra mede o percurso da retirada na máquina do ensaio. [Amostras](./medicao-gateway-gemini.json)

Nos cinco casos operacionais concluídos com recuperação, o provedor registrou em média 871.4 tokens de entrada e 101.6 de saída por geração. A projeção Standard paga considera US$ 0,30 por milhão de tokens de entrada e US$ 2,50 por milhão de saída para Flash-Lite. Para o embedding de texto, considera US$ 0,20 por milhão e assume 25 tokens por pergunta. Isso resulta em **US$ 0.000520 por consulta**, **US$ 0.52 por mil** e **US$ 52.04 por cem mil**. A estimativa considera uma geração concluída por consulta. Indexação inicial, novas tentativas, infraestrutura e impostos ficam fora desse valor. [Uso reportado](./avaliacao-rag-gemini.json) · [Tarifas do Google](https://ai.google.dev/gemini-api/docs/pricing)
