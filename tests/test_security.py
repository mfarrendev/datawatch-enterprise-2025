"""El sandbox SQL del agente.

Medición (cada capa desactivada a mano; arnés que exige 13 pruebas corridas):
- sin el chequeo de una sola sentencia: cae 1 de 13.
- sin el chequeo de tipo SELECT: cae 1 de 13 (EXPLAIN, que no tiene palabras prohibidas).
- sin la lista de palabras prohibidas: no cae ninguna. Con el parser
  funcionando es redundante; queda como respaldo y así se dice.
- sin el parser de tipo NI las palabras: caen 4 de 13.
- conexión sin `enable_external_access = false`: cae 1 de 13 (leer el disco con un SELECT).
- sin el LIMIT envolvente: cae 1 de 13.
"""

import pytest

from src.ai.tools import MAX_FILAS, SQLSandbox


@pytest.fixture
def sandbox(db):
    return SQLSandbox(db)


def test_select_valido_responde(sandbox):
    res = sandbox.execute_read_only(
        "SELECT fecha, ventas_totales FROM metricas_diarias WHERE fecha = '2024-01-05'"
    )
    assert "2024-01-05" in res and "ERROR" not in res


def test_drop_bloqueado(sandbox, db):
    assert "ERROR" in sandbox.execute_read_only("DROP TABLE metricas_diarias")
    assert "2024-01-05" in sandbox.execute_read_only(
        "SELECT fecha FROM metricas_diarias WHERE fecha = '2024-01-05'"
    )


def test_varias_sentencias_bloqueadas(sandbox):
    res = sandbox.execute_read_only("SELECT 1; DELETE FROM anomalias")
    assert "una sola sentencia" in res


def test_comentario_no_esconde_la_segunda_sentencia(sandbox):
    assert "ERROR" in sandbox.execute_read_only("SELECT 1 /* inocente */ ; DROP TABLE anomalias")


@pytest.mark.parametrize(
    "query",
    [
        "COPY metricas_diarias TO '/tmp/fuga.csv'",
        "ATTACH '/tmp/otra.db' AS otra",
        "SET enable_external_access = true",
    ],
)
def test_sentencias_que_no_son_select(sandbox, query):
    assert "ERROR" in sandbox.execute_read_only(query)


def test_select_que_lee_archivos_del_disco(sandbox):
    # Es un SELECT válido: lo que lo para es la conexión sin acceso externo.
    res = sandbox.execute_read_only("SELECT * FROM read_text('/etc/hostname')")
    assert "ERROR" in res


def test_limite_de_filas_aunque_la_consulta_diga_limit(sandbox):
    res = sandbox.execute_read_only("SELECT fecha FROM metricas_diarias LIMIT 1000")
    assert len(res.strip().splitlines()) == MAX_FILAS + 1  # encabezado + filas


# validar() por separado: en execute_read_only, el envoltorio SELECT * FROM (…)
# y la conexión sin acceso externo atajan casi todo aunque falle esta capa, y
# eso escondía en la medición si la capa servía.
def test_validar_rechaza_lo_que_no_es_select_aunque_no_tenga_palabras_prohibidas(sandbox):
    assert sandbox.validar("EXPLAIN ANALYZE SELECT * FROM metricas_diarias") is not None


@pytest.mark.parametrize(
    "query", ["COPY metricas_diarias TO '/tmp/x.csv'", "ATTACH '/tmp/x.db'", "DROP TABLE x"]
)
def test_validar_rechaza_sentencias_peligrosas(sandbox, query):
    assert sandbox.validar(query) is not None
