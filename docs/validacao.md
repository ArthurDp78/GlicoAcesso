# GlicoAcesso — validação da instalação

A validação automatizada é independente da execução padrão: cria um projeto Compose temporário, com credenciais e volumes próprios, e remove tudo ao final.

## Validar a instalação do zero

Em um clone da versão a ser entregue, abra o Docker Desktop e execute na raiz do projeto:

```powershell
.\scripts\validar-compose.ps1
```

Use `-ComOrientacao` para incluir o serviço de Orientação, seu banco e o fallback. Com `GOOGLE_API_KEY` configurada no processo, a mesma execução também valida a indexação e uma resposta RAG pelo Gateway. Veja o [roteiro da Parte 4](./parte-4/04-roteiro-de-entrega.md).

O script cria um projeto Compose temporário, com credenciais e volumes próprios. Ele verifica a saúde dos 14 serviços, a abertura dos portais e o funcionamento das APIs via Gateway. Cadastra uma unidade pela CLI. Na unidade de demonstração, registra a entrada de quatro unidades de um medicamento, habilita a reserva, confirma uma solicitação de duas unidades do mesmo medicamento pela SAGA e verifica a projeção CQRS. Também registra a entrega no balcão e aguarda `RETIRADA` e a projeção de duas unidades físicas, zero alocadas e duas disponíveis. Em seguida testa o cancelamento local e o distribuído. Para demonstrar a compensação, recria apenas Retiradas com a falha de autorização habilitada e aceita uma nova reserva. O teste confirma a liberação da alocação no banco de Estoque, a ausência da autorização no banco de Retiradas, o estado `COMPENSADA` no Orquestrador e o saldo na projeção. Depois recria os contêineres com os mesmos volumes e confirma que os dados e as respostas idempotentes foram preservados.

O resultado esperado é a mensagem **Validação concluída**. Em caso de erro, o script informa a etapa e mostra o estado e os últimos logs dos serviços. Use `-Porta 18081` se a porta local 18080 já estiver em uso. Ao final, o script limpa os contêineres e volumes do projeto temporário.
