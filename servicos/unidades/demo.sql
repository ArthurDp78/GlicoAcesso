INSERT INTO unidades (
    unidade_id, nome, logradouro, numero, bairro, cidade, estado,
    cep, orientacoes_retirada, prazo_analise_horas, ativa
) VALUES (
    '10000000-0000-4000-8000-000000000001', 'Unidade de Demonstração',
    'Rua Exemplo', '100', 'Centro', 'Cidade Exemplo', 'MG',
    '00000-000', 'Apresente a confirmação da reserva no balcão.', 24, true
)
ON CONFLICT (unidade_id) DO NOTHING;

INSERT INTO horarios_unidade (unidade_id, dia_semana, horario_inicial, horario_final)
SELECT '10000000-0000-4000-8000-000000000001'::uuid, dia, TIME '08:00', TIME '17:00'
FROM generate_series(1, 5) AS dias(dia)
ON CONFLICT DO NOTHING;
