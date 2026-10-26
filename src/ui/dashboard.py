import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.core.config import settings
from src.core.db import DatabaseManager

st.set_page_config(page_title="Datawatch Enterprise 2025", layout="wide")
st.title("Datawatch: centro de control")

if not settings.db_path.exists():
    st.warning("Todavía no hay datos. Corre `make demo` o `make run` primero.")
    st.stop()

with DatabaseManager.get_connection(read_only=True) as conn:
    metricas = conn.execute("SELECT * FROM metricas_diarias ORDER BY fecha").df()
    anomalias = conn.execute("SELECT * FROM anomalias ORDER BY fecha").df()
    analisis = conn.execute("SELECT * FROM analisis_agente ORDER BY fecha_analisis DESC").df()

# Fechas sin hora en las tablas.
for tabla in (metricas, anomalias, analisis):
    if not tabla.empty:
        tabla["fecha"] = tabla["fecha"].dt.date

col1, col2, col3, col4 = st.columns(4)
col1.metric("Días analizados", len(metricas))
col2.metric("Anomalías detectadas", len(anomalias))
col3.metric("Anomalías explicadas por IA", len(analisis))
col4.metric("Pendientes de explicar", max(0, len(anomalias) - len(analisis)))

st.divider()

st.subheader("Tendencias")
serie = st.selectbox(
    "Métrica",
    ["ventas_totales", "numero_ordenes", "ticket_promedio", "unidades_vendidas"],
    format_func=lambda s: s.replace("_", " ").capitalize(),
)
fig = px.line(metricas, x="fecha", y=serie, labels={"fecha": "Fecha", serie: serie.replace("_", " ")})
anom_serie = anomalias[anomalias["serie"] == serie]
if not anom_serie.empty:
    fig.add_trace(
        go.Scatter(
            x=anom_serie["fecha"],
            y=anom_serie["valor"],
            mode="markers",
            marker={"color": "#c2410c", "size": 10, "symbol": "x"},
            name="Anomalía",
            customdata=anom_serie[["esperado", "severidad"]],
            hovertemplate="%{x|%Y-%m-%d}<br>valor %{y:,.0f}<br>esperado %{customdata[0]:,.0f}"
            "<br>severidad %{customdata[1]:.1f}<extra></extra>",
        )
    )
st.plotly_chart(fig, width="stretch")

st.subheader("Anomalías detectadas")
st.dataframe(anomalias.sort_values("severidad", ascending=False), width="stretch", hide_index=True)

st.subheader("Explicaciones del agente")
if analisis.empty:
    st.info("No hay anomalías explicadas. El agente corre con `make run` si hay ANTHROPIC_API_KEY.")
else:
    st.dataframe(
        analisis[["fecha", "serie", "hipotesis", "evidencia", "confianza"]],
        width="stretch",
        hide_index=True,
    )
