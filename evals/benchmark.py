"""Recall del detector con anomalías sintéticas inyectadas.

Toma las métricas diarias de la base (o, si no hay, las de los datos
sintéticos), inyecta UNA anomalía por prueba en una copia en memoria (nunca
en la base) y mira si el detector la encuentra. Repite por magnitud: un pico
de ×3 lo ve cualquiera; la pregunta es desde qué tamaño se ve un ×1,3.

Uso: make benchmark
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.core.config import logger, settings
from src.core.db import DatabaseManager
from src.data.detect import SERIES_OBJETIVO, detectar
from src.data.ingest import agregar_diario

MAGNITUDES = [0.5, 0.7, 1.3, 1.5, 2.0, 3.0]
PRUEBAS_POR_MAGNITUD = 40
SEMILLA = 7


def metricas_base() -> pd.DataFrame:
    if settings.db_path.exists():
        with DatabaseManager.get_connection(read_only=True) as conn:
            df = conn.execute("SELECT * FROM metricas_diarias ORDER BY fecha").df()
        if not df.empty:
            return df
    from scripts.generar_datos_sinteticos import generar

    return agregar_diario(generar()).assign(fecha=lambda d: pd.to_datetime(d["fecha"]))


def correr(df: pd.DataFrame, umbral: float) -> dict:
    rng = np.random.default_rng(SEMILLA)
    base = {(pd.Timestamp(f).date(), s) for f, s, *_ in detectar(df, umbral)}
    fechas_base = {f for f, _ in base}
    # Candidatas: lejos de los bordes (STL ve peor ahí) y de días ya anómalos.
    candidatas = [
        i for i in range(30, len(df) - 30) if pd.Timestamp(df.loc[i, "fecha"]).date() not in fechas_base
    ]
    resultados = {"umbral": umbral, "dias": len(df), "avisos_sin_inyectar": len(base), "recall": {}}
    for m in MAGNITUDES:
        aciertos = 0
        for _ in range(PRUEBAS_POR_MAGNITUD):
            i = int(rng.choice(candidatas))
            serie = str(rng.choice(SERIES_OBJETIVO))
            copia = df.astype({s: float for s in SERIES_OBJETIVO})
            copia.loc[i, serie] = copia.loc[i, serie] * m
            fecha = pd.Timestamp(copia.loc[i, "fecha"]).date()
            if (fecha, serie) in {(pd.Timestamp(f).date(), s) for f, s, *_ in detectar(copia, umbral)}:
                aciertos += 1
        resultados["recall"][f"x{m}"] = round(aciertos / PRUEBAS_POR_MAGNITUD, 3)
    return resultados


def main() -> None:
    df = metricas_base()
    logger.info(f"Benchmark sobre {len(df)} días, {PRUEBAS_POR_MAGNITUD} pruebas por magnitud")
    res = correr(df, settings.umbral_anomalia)
    print(
        f"\nUmbral {res['umbral']} · {res['dias']} días · {res['avisos_sin_inyectar']} avisos sin inyectar nada"
    )
    print("Magnitud  Recall")
    for m, r in res["recall"].items():
        print(f"{m:>8}  {r:.0%}")
    destino = Path("evals/resultados")
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "benchmark.json").write_text(json.dumps(res, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
