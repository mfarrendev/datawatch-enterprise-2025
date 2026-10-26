"""Transacciones sintéticas con el formato de Online Retail (UCI / Kaggle).

Sirven para correr el pipeline sin descargar nada (`make demo`) y para las
pruebas. Imitan lo que tiene el dataset real que importa para detectar
anomalías: sin ventas los sábados, cierre de fin de año, tendencia al alza,
estacionalidad semanal, peak de noviembre y anulaciones (facturas con C).

Trae tres anomalías plantadas a propósito, para ver al detector y al agente
trabajar sobre algo conocido:
  - 2011-05-17: un pedido mayorista enorme (unidades y ventas se disparan,
    las órdenes no).
  - 2011-08-09: caída del sitio a media mañana (órdenes y ventas a un tercio).
  - 2011-10-06: error de precios, todo a una décima parte (el ticket se
    desploma, las órdenes no).

Uso: python scripts/generar_datos_sinteticos.py data/demo.csv
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SEMILLA = 2025
PLANTADAS = {
    "2011-05-17": "pedido mayorista",
    "2011-08-09": "caída del sitio",
    "2011-10-06": "error de precios",
}


def generar(semilla: int = SEMILLA) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    dias = pd.date_range("2010-12-01", "2011-12-09", freq="D")
    dias = dias[(dias.day_of_week != 5) & ~((dias >= "2010-12-23") & (dias <= "2011-01-03"))]
    factor_dia = {0: 1.0, 1: 1.1, 2: 1.05, 3: 1.25, 4: 0.85, 6: 0.7}
    productos = [f"{rng.integers(10000, 99999)}" for _ in range(400)]
    precios = rng.lognormal(mean=1.0, sigma=0.7, size=len(productos)).round(2)

    filas = []
    factura = 536365
    for i, dia in enumerate(dias):
        avance = i / len(dias)
        noviembre = 1.6 if dia.month == 11 else 1.0
        ordenes = rng.poisson(28 * (1 + 0.6 * avance) * factor_dia[dia.day_of_week] * noviembre)
        fecha = dia.strftime("%Y-%m-%d")
        multiplicador_precio = 1.0
        if fecha == "2011-08-09":
            ordenes //= 3
        if fecha == "2011-10-06":
            multiplicador_precio = 0.1
        for _ in range(ordenes):
            factura += 1
            hora = dia + pd.Timedelta(minutes=int(rng.integers(8 * 60, 18 * 60)))
            anulada = rng.random() < 0.02
            for _ in range(rng.integers(3, 15)):
                j = rng.integers(len(productos))
                filas.append(
                    (
                        ("C" if anulada else "") + str(factura),
                        productos[j],
                        int(rng.integers(1, 13)),
                        hora.strftime("%m/%d/%Y %H:%M"),
                        round(precios[j] * multiplicador_precio, 2),
                    )
                )
        if fecha == "2011-05-17":
            factura += 1
            for j in rng.choice(len(productos), 30, replace=False):
                filas.append((str(factura), productos[j], 900, f"{dia:%m/%d/%Y} 10:15", precios[j]))

    df = pd.DataFrame(filas, columns=["InvoiceNo", "StockCode", "Quantity", "InvoiceDate", "UnitPrice"])
    df["Description"] = "PRODUCTO " + df["StockCode"]
    df["CustomerID"] = rng.integers(12346, 18288, size=len(df))
    df["Country"] = "United Kingdom"
    return df[
        [
            "InvoiceNo",
            "StockCode",
            "Description",
            "Quantity",
            "InvoiceDate",
            "UnitPrice",
            "CustomerID",
            "Country",
        ]
    ]


if __name__ == "__main__":
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo.csv")
    destino.parent.mkdir(parents=True, exist_ok=True)
    df = generar()
    df.to_csv(destino, index=False)
    print(f"{len(df):,} transacciones sintéticas en {destino}")
