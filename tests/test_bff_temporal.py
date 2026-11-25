"""Ações HATEOAS respeitam o mesmo limite temporal do domínio."""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from servicos.bff_unidade.reservas import links_da_reserva
from servicos.contratos_reserva import ReservaInterna


class PrazoDasAcoes(unittest.TestCase):
    def reserva(self, prazo):
        return ReservaInterna(
            unidadeId=uuid4(), itemId=uuid4(), quantidade=1, reservaId=uuid4(),
            status="SOLICITADA", criadaEm=prazo - timedelta(hours=1), decisaoAte=prazo, cidadaoId="cidadao",
        )

    def test_antes_do_prazo_exibe_acoes_validas(self):
        agora = datetime.now(timezone.utc)
        links = links_da_reserva(self.reserva(agora + timedelta(microseconds=1)), None, True, agora=agora)
        self.assertIn("aceitar", links)
        self.assertIn("rejeitar", links)

    def test_no_prazo_e_apos_prazo_nao_exibe_decisao(self):
        agora = datetime.now(timezone.utc)
        for prazo in (agora, agora - timedelta(microseconds=1)):
            with self.subTest(prazo=prazo):
                links = links_da_reserva(self.reserva(prazo), None, True, agora=agora)
                self.assertNotIn("aceitar", links)
                self.assertNotIn("rejeitar", links)
