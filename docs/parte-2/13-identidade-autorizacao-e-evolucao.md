# Identidade, autorização e evolução para usuários reais

## Estado verificado da demonstração

O modelo atual usa tokens fixos por papel e IDs estáticos em `servicos/identidade_demo.py`. A delegação entre serviços usa cabeçalhos `X-Ator-*` protegidos por uma credencial compartilhada do BFF ou do Orquestrador. Isso permite o fluxo local e os serviços de domínio ainda verificam propriedade da reserva e unidade, mas os cabeçalhos não são prova criptográfica de identidade. Esse modelo não serve para usuários reais nem fornece responsabilização individual.

O Gateway não recebe credencial de serviço: ele encaminha o Bearer do usuário ao BFF e mantém a lista explícita de rotas. O BFF valida a credencial de demonstração e encaminha a identidade delegada. Credenciais estão em `.env` local e em variáveis de ambiente dos containers que as consomem; essa distribuição é adequada apenas ao Compose local, não equivale a um cofre de segredos.

## Reservas do cidadão

O produto precisa permitir que o cidadão consulte uma reserva pelo código. A coleção “Minhas reservas” não está especificada com critérios de conta, histórico, retenção, filtros ou paginação; portanto não se adiciona uma rota nesta etapa. Alternativas para decisão do grupo:

1. manter a consulta pelo código da reserva;
2. exigir uma conta individual e oferecer, além da consulta por código, uma lista paginada das reservas próprias;
3. substituir a consulta por código pela lista autenticada.

Recomendação técnica, caso o grupo confirme a segunda opção: `GET /api/cidadao/v1/reservas` sem aceitar `cidadaoId` do cliente; o BFF obteria um identificador estável da identidade autenticada e o serviço Reservas faria o filtro de proprietário. Ordenação por criação decrescente e paginação por cursor são propostas, ainda dependentes de decisão sobre retenção, estados históricos e filtros. A resposta deve reutilizar a projeção pública de reserva e não expor identificadores internos.

## Modelo recomendado para piloto real

- Usar um provedor OpenID Connect/OAuth 2.0 já operado, sem criar autenticação própria. A aplicação web deve usar Authorization Code com PKCE; validar `iss`, `aud`, assinatura, `exp`, `nbf`, `state` e `nonce` conforme o fluxo aplicável.
- Associar o cidadão por chave estável `(iss, sub)`, não por e-mail, nome ou ID estático. A escolha do provedor, recuperação de conta, MFA e ciclo de vida de contas ainda precisa de aprovação.
- Obter papel profissional e vínculo de unidade de uma fonte autoritativa. Não aceitar `unidadeId` vindo do navegador como autorização. Mudanças ou revogações de vínculo precisam ser refletidas antes de novas ações.
- Preservar autorização por objeto nos serviços de domínio: cidadão apenas na própria reserva; profissional apenas nos recursos da unidade autorizada. Fazer essas verificações antes de enriquecer respostas com dados associados.
- Substituir os cabeçalhos `X-Ator-*` por credenciais de delegação verificáveis, de curta duração, limitadas por audiência e escopo, emitidas por um Authorization Server compatível com OAuth Token Exchange. O recurso valida emissor, destinatário, expiração, escopos e identidade do sujeito/ator. Não implementar assinatura caseira.
- Registrar ator, serviço delegado, operação, recurso, resultado e correlação com minimização de dados pessoais e retenção aprovada.
- Usar TLS em toda comunicação que atravesse hosts ou redes não confiáveis; a rede privada do Compose local não representa transporte seguro para implantação distribuída.

## Decisões pendentes

| Decisão | Recomendação técnica | Dependência |
|---|---|---|
| Lista pessoal de reservas | Adotar a opção 2 acima somente se houver requisito de conta individual | Grupo/produto |
| Provedor OIDC e cadastro de cidadãos | Selecionar provedor e política de ciclo de vida antes do piloto | Produto/operação |
| Fonte de vínculo profissional/unidade | Diretório institucional autoritativo, com processo de revogação | Administração das unidades |
| Token Exchange e topologia de confiança | Selecionar provedor que emita tokens delegados com audiência/escopo; definir identidade de workload | Plataforma/segurança |
| MFA, recuperação e retenção de auditoria | Definir risco e obrigações aplicáveis | Produto/segurança |

## Critérios de aceite para a evolução

1. Dois cidadãos autenticados não conseguem consultar, cancelar ou listar recursos um do outro, mesmo alterando IDs e repetindo chaves idempotentes.
2. Um profissional sem vínculo, com vínculo revogado ou de outra unidade não consegue executar ações nem recuperar respostas idempotentes protegidas.
3. Tokens destinados a um serviço não são aceitos por outro; tokens expirados, inválidos ou sem escopo são recusados.
4. O serviço de domínio valida autorização no recurso em cada leitura e escrita.
5. Testes de segurança cobrem BOLA/IDOR, falsificação de cabeçalhos, replay, expiração e revogação; auditoria identifica ator e operação sem registrar credenciais.
6. Jornada de conta/listagem só será implementada após decisão formal dos campos, filtros, ordenação, retenção e paginação.

## Referências

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) define as afirmações de identidade e o identificador `sub` no contexto de um emissor.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700.html) orienta o uso de Authorization Code, PKCE e proteção contra ataques em fluxos OAuth.
- [OAuth 2.0 Token Exchange (RFC 8693)](https://www.rfc-editor.org/rfc/rfc8693.html) fornece um formato padronizado para credenciais delegadas e distingue sujeito e ator.
- [OWASP API Security Top 10 — API1:2023 BOLA](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/) exige autorização no nível do objeto para cada operação que use identificadores controláveis pelo cliente.
