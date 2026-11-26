-- Períodos válidos no mesmo dia e sem sobreposição. Dados anteriores que violem as regras são
-- preservados e marcados como legado, fora das constraints; novos registros são sempre protegidos.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE horarios_unidade ADD COLUMN legado boolean NOT NULL DEFAULT false;

UPDATE horarios_unidade AS h SET legado = true
WHERE h.horario_inicial >= h.horario_final
   OR EXISTS (
        SELECT 1 FROM horarios_unidade AS o
        WHERE o.unidade_id = h.unidade_id AND o.dia_semana = h.dia_semana
          AND (o.horario_inicial, o.horario_final) <> (h.horario_inicial, h.horario_final)
          AND o.horario_inicial < h.horario_final AND h.horario_inicial < o.horario_final
   )
   OR h.horario_final = TIME '24:00';

ALTER TABLE horarios_unidade
    ADD CONSTRAINT horarios_periodo_valido
        CHECK (legado OR (horario_inicial < horario_final AND horario_final < TIME '24:00')),
    ADD CONSTRAINT horarios_sem_sobreposicao EXCLUDE USING gist (
        unidade_id WITH =, dia_semana WITH =,
        tsrange(DATE '2000-01-01' + horario_inicial, DATE '2000-01-01' + horario_final, '[)') WITH &&
    ) WHERE (NOT legado);
