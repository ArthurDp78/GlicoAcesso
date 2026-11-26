-- Programa Farmácia Popular do Brasil, Elenco de Medicamentos e Insumos,
-- seção DIABETES, página 1, edição de 31/08/2026.
-- Mantém o catálogo incluído na main também em instalações limpas desta branch.
-- Em upgrades, item_id é estável; linhas existentes (e seus dados) são preservadas.
INSERT INTO itens (item_id, nome, tipo)
VALUES
    ('31a8296a-87a9-58ef-b8fc-a2248dab22b3', 'Cloridrato de metformina 500 mg', 'MEDICAMENTO'),
    ('6eab6077-2ace-5313-bfd4-2597ab7fa680', 'Cloridrato de metformina 500 mg, ação prolongada', 'MEDICAMENTO'),
    ('25057d00-8d2c-5ad0-87a8-b3f6f294493d', 'Cloridrato de metformina 850 mg', 'MEDICAMENTO'),
    ('06fa44c3-af81-5ff8-9749-76f2d46938e4', 'Glibenclamida 5 mg', 'MEDICAMENTO'),
    ('84218dfb-8903-5ed8-96e5-64f6de33272b', 'Insulina humana regular 100 UI/mL', 'MEDICAMENTO'),
    ('dde341d5-ea06-5dbe-bc38-44025b734ceb', 'Insulina humana 100 UI/mL', 'MEDICAMENTO')
ON CONFLICT (item_id) DO NOTHING;
