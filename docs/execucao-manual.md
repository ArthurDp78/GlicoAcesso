# GlicoAcesso — execução manual com Docker Compose

A execução padrão é feita por `.\iniciar.ps1` (ou `./iniciar.sh` no Linux), descrita no [README](../README.md#como-executar). Este guia reúne os comandos equivalentes para quem quiser executar cada etapa manualmente, cadastrar unidades pela CLI ou construir as imagens isoladamente.

## Subir o sistema completo com Docker Compose

Com o Docker Desktop aberto e em modo de contêineres Linux, execute o bloco a seguir na raiz do repositório. Na primeira execução ele gera um `.env` a partir de `.env.example`, com valores aleatórios distintos para as credenciais internas. O campo `GOOGLE_API_KEY` fica vazio até você configurar uma chave do provedor. Se já existir um `.env`, preserve o arquivo e complete os campos faltantes com base no exemplo.

```powershell
if (-not (Test-Path -LiteralPath .env)) {
  $gerador = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $linhas = foreach ($linha in Get-Content -LiteralPath .env.example) {
      if ($linha -ne 'GOOGLE_API_KEY=' -and $linha -match '^[A-Z0-9_]+=$') {
        $bytes = New-Object byte[] 32
        $gerador.GetBytes($bytes)
        $linha + [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
      } else {
        $linha
      }
    }
    [IO.File]::WriteAllLines((Join-Path (Get-Location).Path '.env'),
      [string[]]$linhas, [Text.UTF8Encoding]::new($false))
  } finally {
    $gerador.Dispose()
  }
}
docker compose up --build -d --wait
```

A mesma subida pode ser feita em primeiro plano com `docker compose up --build`. O Compose aguarda os bancos, roda as migrações antes de iniciar as APIs e verifica a saúde de cada serviço. A carga de demonstração é aplicada em Unidades e Estoque por padrão. Use `GLICO_CARREGAR_DEMO=0` no `.env` para iniciar uma base nova apenas com as migrações e o catálogo oficial.

- **Portal do cidadão** em [http://127.0.0.1:8000/cidadao](http://127.0.0.1:8000/cidadao), com `GLICO_CIDADAO_TOKEN` para reservar.
- **Painel da unidade** em [http://127.0.0.1:8000/unidade](http://127.0.0.1:8000/unidade), com `GLICO_PROFISSIONAL_TOKEN`.
- **Diagnóstico** com `docker compose ps` e `docker compose logs <serviço>`. Se a porta 8000 estiver ocupada, ajuste `GLICO_GATEWAY_PORTA` no `.env`.

Para registrar uma entrega, informe o código da reserva no painel profissional, em **Retirada no balcão**. A ação aparece quando a reserva está confirmada e a autorização está ativa. Em instalações existentes, preencha `GLICO_RETIRADAS_SERVICE_TOKEN` no `.env` com um valor aleatório exclusivo de pelo menos 32 caracteres. Na execução manual, configure o mesmo valor em Reservas e Retiradas e disponibilize as credenciais de demonstração do profissional para Retiradas.

O cancelamento distribuído pelo cidadão usa `GLICO_BFF_CIDADAO_SIGNING_KEY`. Em um `.env` existente, acrescente um valor aleatório exclusivo de pelo menos 32 caracteres. Na execução manual, configure a mesma chave no BFF Cidadão e no Orquestrador e defina o token do cidadão também no BFF Cidadão.

Somente o Gateway publica uma porta em `127.0.0.1`. Cada PostgreSQL tem uma rede privada com seu serviço e um volume próprio. Estoque, Retiradas, Reservas e Orquestrador acessam o RabbitMQ pela rede de mensageria. Unidades também participa da rede administrativa usada pela CLI.

`docker compose down` encerra os contêineres e preserva os volumes nomeados. Mantenha o mesmo `.env` entre execuções para reutilizar as credenciais dos bancos e do RabbitMQ.

## Habilitar a orientação com RAG

A orientação fica disponível no portal do cidadão após preparar o índice e iniciar o perfil Docker. Use o item selecionado e a credencial do cidadão para enviar uma pergunta. Veja [a configuração da Parte 4](./parte-4/01-orientacao-com-rag.md#executar-a-orientação-no-portal) e o [roteiro de validação e apresentação](./parte-4/04-roteiro-de-entrega.md).

## Cadastrar uma unidade pelo comando administrativo

Prepare um arquivo `unidade.json` com os campos abaixo. O serviço Unidades gera o identificador e cria a unidade ativa.

```json
{
  "nome": "Unidade de Saúde Central",
  "logradouro": "Rua Exemplo",
  "numero": "200",
  "bairro": "Centro",
  "cidade": "Cidade Exemplo",
  "estado": "MG",
  "cep": "30000-000",
  "orientacoesRetirada": "Apresente o código da reserva no balcão.",
  "contatos": [],
  "horarios": [{"diaSemana": 1, "horarioInicial": "08:00", "horarioFinal": "17:00"}],
  "prazoAnaliseHoras": 24
}
```

O prazo de análise aceita de 1 a 720 horas (30 dias). Se uma unidade antiga tiver prazo superior, o profissional precisa ajustá-lo para receber novas solicitações. Reservas já criadas conservam o prazo original.

Depois de subir o Compose principal, execute o comando pelo `compose.admin.yml`. Ele acessa `unidades:8002` pela rede `GLICO_REDE_ADMINISTRATIVA` e usa a mesma `GLICO_GESTOR_REDE_TOKEN` do `.env`.

```powershell
$arquivo = (Resolve-Path .\unidade.json).Path
$chave = [guid]::NewGuid().ToString()
docker compose -f compose.admin.yml --profile admin run --build --rm `
  --volume "${arquivo}:/dados/unidade.json:ro" cadastro-unidades `
  --arquivo /dados/unidade.json --chave $chave
```

O comando imprime o ID da unidade em caso de sucesso. Em caso de timeout, use o mesmo arquivo e o mesmo valor de `$chave` na próxima tentativa para recuperar a resposta sem repetir o cadastro.

Com Unidades em execução diretamente no Windows, aplique `uv run --locked python -m servicos.migracoes unidades` e configure a mesma credencial no processo de Unidades e no terminal do comando. Nesse ambiente, use `uv run --locked python -m servicos.unidades.cli --arquivo .\unidade.json --chave $chave`. Para outra porta ou endereço local, defina `UNIDADES_URL`. Confira a unidade ativa em `GET /api/cidadao/v1/unidades` pelo Gateway. Ela aparece na busca do portal quando houver disponibilidade projetada para o item consultado.

## Construir as imagens da aplicação

Cada um dos oito serviços tem um Dockerfile em `servicos/<serviço>/Dockerfile`. Use a raiz do repositório como contexto para que o build tenha acesso ao `uv.lock` e aos módulos compartilhados. No PowerShell, com o Docker Desktop em modo de contêineres Linux:

```powershell
foreach ($servico in 'gateway', 'bff_cidadao', 'unidades', 'estoque', 'reservas', 'bff_unidade', 'orquestrador', 'retiradas') {
  docker build --file "servicos/$servico/Dockerfile" --tag "glicoacesso/${servico}:local" .
  if ($LASTEXITCODE -ne 0) { throw "Falha no build de $servico." }
}
```

As imagens usam **build em múltiplos estágios**. O primeiro estágio instala as dependências do `uv.lock` em uma `.venv`. A imagem final usa a mesma base Python slim e leva o ambiente instalado, os módulos compartilhados e os arquivos do serviço. Com isso, o `uv` e o cache de instalação ficam fora da imagem final. Alterações no código do serviço reaproveitam a camada de dependências. Cada processo é executado com usuário sem privilégios de root.

O Gateway leva os arquivos dos dois portais e a logo. As imagens dos serviços com banco levam suas migrações para que a inicialização possa executá-las com `python -m servicos.migracoes <serviço>`. A aplicação das migrações e a configuração de URLs, bancos, RabbitMQ e credenciais fazem parte da subida do sistema.

Para uma checagem isolada da imagem de entrada, suba o Gateway e consulte `http://127.0.0.1:8000/health` em outro terminal:

```powershell
docker run --rm -p 127.0.0.1:8000:8000 glicoacesso/gateway:local
```
