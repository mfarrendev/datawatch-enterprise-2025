from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal

import anthropic
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.ai.tools import SQLSandbox
from src.core.config import logger, settings
from src.core.db import DatabaseManager

MAX_RONDAS_HERRAMIENTAS = 6

# Solo se reintenta lo que se arregla esperando (red, 429, 5xx). Un 400 o una
# respuesta que no valida se reintentaría igual de mal y gastaría tokens.
REINTENTABLES = (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError)
reintentar = retry(
    retry=retry_if_exception_type(REINTENTABLES),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    reraise=True,
)


class ExplicacionAnomalia(BaseModel):
    hipotesis: str = Field(description="Explicación de negocio clara y concisa.")
    evidencia_citada: str = Field(
        description="Fechas y cifras concretas, sacadas de las consultas, que respaldan la hipótesis."
    )
    nivel_confianza: Literal["Alta", "Media", "Baja"]


class ClaudeInvestigator:
    """Agente analítico: investiga cada anomalía consultando la base con SQL de solo lectura."""

    SYSTEM_PROMPT = """Eres un analista de datos senior. Investigas anomalías en métricas diarias de un e-commerce.
Usa la herramienta SQL para consultar la tabla `metricas_diarias` (columnas: fecha, ventas_totales, numero_ordenes, ticket_promedio, unidades_vendidas) y la tabla `anomalias` (fecha, serie, valor, esperado, severidad).
Busca patrones: ¿cayeron las órdenes pero subió el ticket? ¿Es un día de la semana o una fecha especial? ¿Se mueven juntas varias métricas?
Formula la hipótesis SOLO con lo que muestren tus consultas. Si los datos no alcanzan para explicar la anomalía, dilo y baja la confianza: una hipótesis sin evidencia no sirve."""

    TOOLS: ClassVar[list[dict]] = [
        {
            "name": "consultar_sql_negocio",
            "description": "Ejecuta un SELECT de solo lectura en DuckDB y devuelve hasta 50 filas en CSV.",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Una sola sentencia SELECT."}},
                "required": ["query"],
                "additionalProperties": False,
            },
            "strict": True,
        }
    ]

    # fallbacks="default": si un clasificador declina la petición, la API la
    # reintenta en el modelo de respaldo que corresponda, dentro de la misma llamada.
    API_EXTRA: ClassVar[dict] = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

    def __init__(self, db_path: Path | None = None, client: anthropic.Anthropic | None = None):
        self.db_path = db_path
        self.sandbox = SQLSandbox(db_path)
        self.client = client
        if self.client is None and settings.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())

    @reintentar
    def _llamar(self, mensajes: list) -> anthropic.types.beta.BetaMessage:
        return self.client.beta.messages.create(
            model=settings.claude_model,
            max_tokens=8000,
            output_config={"effort": settings.claude_effort},
            system=self.SYSTEM_PROMPT,
            tools=self.TOOLS,
            messages=mensajes,
            **self.API_EXTRA,
        )

    @reintentar
    def _veredicto(self, mensajes: list) -> ExplicacionAnomalia:
        res = self.client.beta.messages.parse(
            model=settings.claude_model,
            max_tokens=4000,
            output_config={"effort": settings.claude_effort},
            system=self.SYSTEM_PROMPT,
            tools=self.TOOLS,
            messages=mensajes,
            output_format=ExplicacionAnomalia,
            **self.API_EXTRA,
        )
        if res.stop_reason == "refusal" or res.parsed_output is None:
            raise ValueError(f"Sin veredicto válido (stop_reason={res.stop_reason})")
        return res.parsed_output

    def analizar_incidente(
        self, fecha: str, serie: str, valor: float, esperado: float
    ) -> ExplicacionAnomalia:
        mensajes: list = [
            {
                "role": "user",
                "content": (
                    f"Anomalía detectada el {fecha} en la métrica '{serie}'. Valor real: {valor:,.2f}; "
                    f"el modelo estadístico esperaba {esperado:,.2f}. Investiga la causa consultando la base."
                ),
            }
        ]
        for _ in range(MAX_RONDAS_HERRAMIENTAS):
            respuesta = self._llamar(mensajes)
            if respuesta.stop_reason == "refusal":
                raise ValueError("El modelo declinó la petición")
            mensajes.append({"role": "assistant", "content": respuesta.content})
            usos = [b for b in respuesta.content if b.type == "tool_use"]
            if respuesta.stop_reason != "tool_use" or not usos:
                break
            # Todos los resultados van en UN mensaje de usuario, uno por cada
            # tool_use: la API exige que cada llamada tenga su resultado ahí.
            mensajes.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": b.id,
                            "content": self.sandbox.execute_read_only(b.input["query"]),
                        }
                        for b in usos
                    ],
                }
            )

        pedido = {"type": "text", "text": "Con lo que consultaste, entrega el veredicto final."}
        if mensajes[-1]["role"] == "user":
            # Se acabaron las rondas con resultados pendientes: el pedido va en el
            # mismo mensaje, después de los tool_result.
            mensajes[-1]["content"].append(pedido)
        else:
            mensajes.append({"role": "user", "content": [pedido]})
        return self._veredicto(mensajes)

    def execute(self) -> int:
        logger.info("Iniciando agente investigador...")
        if self.client is None:
            logger.warning("Sin ANTHROPIC_API_KEY: se salta el análisis con IA.")
            return 0

        with DatabaseManager.get_connection(read_only=True, db_path=self.db_path) as conn:
            pendientes = conn.execute("""
                SELECT a.* FROM anomalias a
                LEFT JOIN analisis_agente aa ON a.fecha = aa.fecha AND a.serie = aa.serie
                WHERE aa.fecha IS NULL
                ORDER BY a.severidad DESC
            """).df()
        # La conexión se cierra antes de investigar: DuckDB no deja abrir el mismo
        # archivo con otra configuración (la del sandbox) mientras siga abierta.
        if pendientes.empty:
            logger.info("No hay nuevas anomalías para investigar.")
            return 0

        analizadas = 0
        for _, row in pendientes.iterrows():
            fecha = str(row["fecha"])[:10]
            logger.info(f"Investigando anomalía: {row['serie']} ({fecha})")
            try:
                e = self.analizar_incidente(fecha, row["serie"], row["valor"], row["esperado"])
            except Exception as err:  # una anomalía que falla no detiene las demás
                logger.error(f"Falló el análisis de {row['serie']} ({fecha}): {err}")
                continue
            with DatabaseManager.get_connection(db_path=self.db_path) as conn:
                conn.execute(
                    "INSERT INTO analisis_agente VALUES (?, ?, ?, ?, ?, ?)",
                    (fecha, row["serie"], e.hipotesis, e.evidencia_citada, e.nivel_confianza, datetime.now()),
                )
            analizadas += 1
        logger.info(f"Agente finalizado: {analizadas} de {len(pendientes)} anomalías explicadas.")
        return analizadas
