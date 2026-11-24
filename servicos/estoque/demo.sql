INSERT INTO itens (item_id, nome, tipo, descricao)
VALUES (
    '20000000-0000-4000-8000-000000000001',
    'Tiras reagentes para glicemia', 'INSUMO', 'Item do catálogo de demonstração.'
)
ON CONFLICT (item_id) DO NOTHING;

INSERT INTO saldos (unidade_id, item_id, estoque_fisico_atual, permite_reserva)
VALUES (
    '10000000-0000-4000-8000-000000000001',
    '20000000-0000-4000-8000-000000000001', 10, true
)
ON CONFLICT (unidade_id, item_id) DO NOTHING;

INSERT INTO disponibilidade (
    unidade_id, item_id, estoque_fisico_atual, quantidade_alocada,
    permite_reserva, atualizado_em, estoque_version
)
SELECT
    unidade_id, item_id, estoque_fisico_atual, quantidade_alocada,
    permite_reserva, updated_at, estoque_version
FROM saldos
WHERE unidade_id = '10000000-0000-4000-8000-000000000001'
  AND item_id = '20000000-0000-4000-8000-000000000001'
ON CONFLICT (unidade_id, item_id) DO NOTHING;
