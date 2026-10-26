"""Ingesta y detección.

Medición (defecto puesto a mano; arnés que exige 6 pruebas corridas):
- INSERT con las columnas en el orden del DataFrame original (ticket y
  unidades cruzados): cae 1 de 6.
- sin excluir las facturas anuladas (con C): caen 2 de 6.
- periodo_semanal fijo en 7: cae 1 de 6.
- z_score_mad devolviendo un array en vez de Series: cae 1 de 6.
- sin el logaritmo en detectar: cae 1 de 6.
"""

import numpy as np
import pandas as pd

from src.core.db import DatabaseManager
from src.data.detect import detectar, periodo_semanal, z_score_mad
from src.data.ingest import DataIngestionPipeline, agregar_diario

TRANSACCIONES = pd.DataFrame(
    {
        "InvoiceNo": ["1", "1", "2", "C3", "4"],
        "Quantity": [2, 3, 1, 5, 4],
        "InvoiceDate": [
            "12/1/2010 8:26",
            "12/1/2010 8:26",
            "12/1/2010 9:00",
            "12/1/2010 9:30",
            "12/2/2010 10:00",
        ],
        "UnitPrice": [10.0, 5.0, 100.0, 20.0, 0.0],
    }
)


def test_agregar_diario_excluye_anulaciones_y_precio_cero():
    d = agregar_diario(TRANSACCIONES)
    assert len(d) == 1  # el 2 de diciembre solo tiene una línea con precio cero
    fila = d.iloc[0]
    assert fila["ventas_totales"] == 2 * 10 + 3 * 5 + 100
    assert fila["numero_ordenes"] == 2
    assert fila["unidades_vendidas"] == 6


def test_ingesta_deja_cada_metrica_en_su_columna(tmp_path):
    ruta_csv = tmp_path / "t.csv"
    TRANSACCIONES.to_csv(ruta_csv, index=False)
    db = tmp_path / "t.db"
    DatabaseManager.initialize_schema(db_path=db)
    DataIngestionPipeline(ruta=ruta_csv, db_path=db).execute()
    with DatabaseManager.get_connection(read_only=True, db_path=db) as conn:
        ticket, unidades = conn.execute(
            "SELECT ticket_promedio, unidades_vendidas FROM metricas_diarias"
        ).fetchone()
    assert ticket == 135 / 2
    assert unidades == 6


def test_periodo_semanal_sin_sabados():
    fechas = pd.Series(pd.date_range("2024-01-01", periods=70, freq="D"))
    assert periodo_semanal(fechas[fechas.dt.day_of_week != 5]) == 6


def test_z_score_con_mad_cero_es_una_serie_de_ceros():
    z = z_score_mad(pd.Series([5.0] * 10))
    assert isinstance(z, pd.Series) and (z == 0).all()


def _serie_sintetica(pico_en: int, factor: float) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    fechas = pd.date_range("2024-01-01", periods=400, freq="D")
    crecimiento = np.linspace(1, 3, len(fechas))  # triplica en el año
    semana = 1 + 0.2 * np.sin(2 * np.pi * np.arange(len(fechas)) / 7)
    base = 1000 * crecimiento * semana * rng.lognormal(0, 0.05, len(fechas))
    base[pico_en] *= factor
    return pd.DataFrame(
        {
            "fecha": fechas,
            "ventas_totales": base,
            "numero_ordenes": 10 * crecimiento * semana,
            "ticket_promedio": 100.0,
            "unidades_vendidas": 50 * crecimiento * semana,
        }
    )


def test_detecta_un_pico_plantado():
    encontradas = detectar(_serie_sintetica(200, 2.5), umbral=3.5)
    assert ("2024-07-19", "ventas_totales") in {(str(f), s) for f, s, *_ in encontradas}


def test_sin_pico_pocas_falsas_alarmas_con_tendencia_fuerte():
    # Una serie que triplica en el año con 5 % de ruido y ningún pico. Medido
    # sobre esta misma serie, días marcados con umbral 3,5:
    #   - configuración original (sin log, ventanas de omisión de STL): 56
    #   - sin el logaritmo, con las ventanas de ahora: 19
    #   - como está ahora: 7
    # Siete falsas alarmas al año por serie es lo que hay que saber de este
    # detector; la prueba impide volver a lo de antes.
    encontradas = [a for a in detectar(_serie_sintetica(200, 1.0), umbral=3.5) if a[1] == "ventas_totales"]
    assert len(encontradas) <= 8
