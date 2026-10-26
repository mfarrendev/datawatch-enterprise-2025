import re
from pathlib import Path

import duckdb

from src.core.config import logger
from src.core.db import DatabaseManager

MAX_FILAS = 50
MAX_CARACTERES = 6000
PALABRAS_PROHIBIDAS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|COPY|ATTACH|DETACH|PRAGMA|SET|INSTALL|LOAD|EXPORT|IMPORT|CALL)\b",
    re.IGNORECASE,
)


class SQLSandbox:
    """Ejecución SQL de solo lectura para el agente, en tres capas.

    1. El parser de DuckDB: exactamente UNA sentencia y de tipo SELECT. Una
       expresión regular sobre el texto se engaña con comentarios o mayúsculas;
       el parser no.
    2. Palabras prohibidas: respaldo por si una versión futura del parser
       clasifica distinto alguna sentencia. Hoy es redundante (medido en
       tests/test_security.py: sacarla no hace caer ninguna prueba).
    3. La conexión: solo lectura y sin acceso a archivos ni red
       (`DatabaseManager.get_sandbox_connection`). Es la capa que de verdad
       impide un `SELECT * FROM read_csv('/etc/passwd')`, que pasa las dos
       primeras porque ES un SELECT.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path

    def validar(self, query: str) -> str | None:
        """None si la consulta se puede ejecutar; si no, el motivo."""
        try:
            sentencias = duckdb.connect(":memory:").extract_statements(query)
        except duckdb.Error as e:
            return f"ERROR: la consulta no se pudo interpretar: {e}"
        if len(sentencias) != 1:
            return "ERROR: Operación bloqueada. Se permite una sola sentencia."
        if sentencias[0].type != duckdb.StatementType.SELECT:
            return "ERROR: Operación bloqueada. Solo se permiten sentencias SELECT."
        if PALABRAS_PROHIBIDAS.search(query):
            return "ERROR: Operación bloqueada. Sentencia no permitida detectada."
        return None

    def execute_read_only(self, query: str) -> str:
        query = query.strip().rstrip(";").strip()
        logger.debug(f"Agente ejecutando query: {query}")
        motivo = self.validar(query)
        if motivo:
            logger.warning(f"Consulta del agente bloqueada: {motivo} | {query}")
            return motivo
        # El límite se pone envolviendo la consulta, no buscando la palabra LIMIT
        # en el texto: una columna llamada "limite" no debe saltárselo.
        envuelta = f"SELECT * FROM ({query}) AS consulta_agente LIMIT {MAX_FILAS}"
        try:
            with DatabaseManager.get_sandbox_connection(self.db_path) as conn:
                res = conn.execute(envuelta).df()
        except duckdb.Error as e:
            return f"ERROR de DuckDB: {e}"
        if res.empty:
            return "Consulta exitosa, pero no retornó resultados."
        return res.to_csv(index=False)[:MAX_CARACTERES]
