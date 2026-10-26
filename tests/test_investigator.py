"""El bucle del agente, con un cliente falso (sin API ni costo).

Medición (defecto puesto a mano; arnés que exige 4 pruebas corridas):
- un tool_result por mensaje en vez de todos en uno: cae 1 de 4.
- pedido final como mensaje nuevo cuando el último ya es del usuario: cae 1 de 4.
- una conexión de escritura abierta durante la investigación (DuckDB choca
  con la del sandbox): cae 1 de 4.
"""

from itertools import pairwise
from types import SimpleNamespace

from src.ai.investigator import MAX_RONDAS_HERRAMIENTAS, ClaudeInvestigator, ExplicacionAnomalia
from src.core.db import DatabaseManager


def uso(id_, query):
    return SimpleNamespace(type="tool_use", id=id_, input={"query": query})


class ClienteFalso:
    """Responde con una lista fija de mensajes y guarda lo que recibió."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.recibido = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create, parse=self._parse))

    def _create(self, **kw):
        self.recibido.append([dict(m) for m in kw["messages"]])
        return self.respuestas.pop(0)

    def _parse(self, **kw):
        self.final = kw["messages"]
        return SimpleNamespace(
            stop_reason="end_turn",
            parsed_output=ExplicacionAnomalia(hipotesis="h", evidencia_citada="e", nivel_confianza="Media"),
        )


def respuesta(stop, bloques):
    return SimpleNamespace(stop_reason=stop, content=bloques)


def test_todos_los_resultados_van_en_un_solo_mensaje(db):
    q = "SELECT fecha FROM metricas_diarias WHERE fecha = '2024-01-05'"
    cliente = ClienteFalso(
        [
            respuesta("tool_use", [uso("a", q), uso("b", q)]),
            respuesta("end_turn", [SimpleNamespace(type="text", text="listo")]),
        ]
    )
    ClaudeInvestigator(db_path=db, client=cliente).analizar_incidente("2024-01-05", "ventas_totales", 1, 2)
    mensaje_resultados = cliente.recibido[1][-1]
    assert mensaje_resultados["role"] == "user"
    assert [r["tool_use_id"] for r in mensaje_resultados["content"]] == ["a", "b"]
    assert "2024-01-05" in mensaje_resultados["content"][0]["content"]


def test_si_se_acaban_las_rondas_el_pedido_final_va_junto_a_los_resultados(db):
    q = "SELECT 1"
    cliente = ClienteFalso([respuesta("tool_use", [uso(str(i), q)]) for i in range(MAX_RONDAS_HERRAMIENTAS)])
    ClaudeInvestigator(db_path=db, client=cliente).analizar_incidente("2024-01-05", "ventas_totales", 1, 2)
    ultimo = cliente.final[-1]
    roles = [m["role"] for m in cliente.final]
    assert all(a != b for a, b in pairwise(roles)), "dos mensajes seguidos del mismo rol"
    assert ultimo["content"][0]["type"] == "tool_result"
    assert ultimo["content"][-1]["type"] == "text"


def test_execute_guarda_la_explicacion(db):
    with DatabaseManager.get_connection(db_path=db) as conn:
        conn.execute("INSERT INTO anomalias VALUES ('2024-01-05', 'ventas_totales', 1, 2, 9)")
    cliente = ClienteFalso(
        [
            respuesta("tool_use", [uso("a", "SELECT * FROM anomalias")]),
            respuesta("end_turn", [SimpleNamespace(type="text", text="listo")]),
        ]
    )
    assert ClaudeInvestigator(db_path=db, client=cliente).execute() == 1
    with DatabaseManager.get_connection(read_only=True, db_path=db) as conn:
        assert conn.execute("SELECT confianza FROM analisis_agente").fetchone() == ("Media",)


def test_sin_cliente_se_salta_el_agente(db, monkeypatch):
    monkeypatch.setattr("src.ai.investigator.settings.anthropic_api_key", None)
    assert ClaudeInvestigator(db_path=db).execute() == 0
