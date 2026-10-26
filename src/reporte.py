from datetime import datetime
from pathlib import Path

from src.core.config import settings
from src.core.db import DatabaseManager


def escribir_reporte(db_path: Path | None = None, destino: Path | None = None) -> Path:
    """Reporte Markdown de la última detección, con las explicaciones del agente que haya."""
    with DatabaseManager.get_connection(read_only=True, db_path=db_path) as conn:
        filas = conn.execute("""
            SELECT a.fecha, a.serie, a.valor, a.esperado, a.severidad,
                   aa.hipotesis, aa.evidencia, aa.confianza
            FROM anomalias a
            LEFT JOIN analisis_agente aa ON a.fecha = aa.fecha AND a.serie = aa.serie
            ORDER BY a.severidad DESC
        """).fetchall()
        dias = conn.execute("SELECT count(*), min(fecha), max(fecha) FROM metricas_diarias").fetchone()

    lineas = [
        "# Reporte de anomalías",
        "",
        f"Generado el {datetime.now():%Y-%m-%d %H:%M}. {dias[0]} días analizados, del {dias[1]} al {dias[2]}.",
        f"{len(filas)} anomalías sobre el umbral de {settings.umbral_anomalia}.",
        "",
    ]
    for fecha, serie, valor, esperado, severidad, hipotesis, evidencia, confianza in filas:
        lineas += [
            f"## {fecha} · {serie.replace('_', ' ')}",
            "",
            f"Valor {valor:,.2f}; se esperaba {esperado:,.2f} (severidad {severidad:.1f}).",
            "",
        ]
        if hipotesis:
            lineas += [f"**Hipótesis ({confianza}):** {hipotesis}", "", f"**Evidencia:** {evidencia}", ""]
        else:
            lineas += ["Sin explicación del agente.", ""]
    destino = destino or settings.reportes_dir / f"reporte-{datetime.now():%Y%m%d-%H%M}.md"
    destino.write_text("\n".join(lineas), encoding="utf-8")
    return destino
