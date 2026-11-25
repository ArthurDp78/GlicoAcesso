-- A recepção inicial da SAGA persistia apenas o sagaId no corpo da etapa.
-- Reconstrói a intenção a partir do contexto já salvo, mantendo a chave original.
UPDATE saga_etapas AS e
SET dados_comando = jsonb_build_object(
        'metodo', 'POST',
        'caminho', '/internal/v1/reservas/' || s.reserva_id::text || '/aceite',
        'corpo', e.dados_comando,
        'cabecalhos', jsonb_build_object(
            'X-Ator-Papel', 'PROFISSIONAL',
            'X-Ator-Id', s.ator_id,
            'X-Ator-Unidade-Id', s.ator_unidade_id::text
        )
    ),
    proximo_retry_em = now(),
    erro_tecnico = NULL,
    atualizada_em = now()
FROM saga_execucoes AS s
WHERE s.saga_id = e.saga_id
  AND s.tipo = 'CONFIRMACAO'
  AND e.etapa_id = 'ACEITAR_RESERVA'
  AND e.estado_tecnico = 'PENDENTE'
  AND e.dados_comando = jsonb_build_object('sagaId', s.saga_id);
