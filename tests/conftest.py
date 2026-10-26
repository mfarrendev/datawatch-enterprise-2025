import pandas as pd
import pytest

from src.core.db import DatabaseManager


@pytest.fixture
def db(tmp_path):
    """Base DuckDB propia de cada prueba, con 100 días de métricas."""
    ruta = tmp_path / "prueba.db"
    DatabaseManager.initialize_schema(db_path=ruta)
    dias = pd.DataFrame(
        {
            "fecha": pd.date_range("2024-01-01", periods=100, freq="D").date,
            "ventas_totales": 1000.0,
            "numero_ordenes": 10,
            "ticket_promedio": 100.0,
            "unidades_vendidas": 50,
        }
    )
    with DatabaseManager.get_connection(db_path=ruta) as conn:
        conn.register("dias", dias)
        conn.execute("INSERT INTO metricas_diarias SELECT * FROM dias")
    return ruta
