from pathlib import Path

import duckdb

from src.core.config import logger, settings


class DatabaseManager:
    """Gestor de conexiones y del esquema de DuckDB."""

    @staticmethod
    def get_connection(read_only: bool = False, db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(db_path or settings.db_path), read_only=read_only)

    @staticmethod
    def get_sandbox_connection(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
        """Conexión para el agente: solo lectura y SIN acceso a archivos ni red.

        `read_only` impide escribir en la base, pero no impide que un SELECT lea
        el disco (`SELECT * FROM read_csv('/etc/passwd')`) o la red. Eso lo
        cierra `enable_external_access = false`, y queda fijo con `lock_configuration`
        para que una consulta no pueda volver a encenderlo con SET.
        """
        return duckdb.connect(
            str(db_path or settings.db_path),
            read_only=True,
            config={"enable_external_access": False, "lock_configuration": True},
        )

    @classmethod
    def initialize_schema(cls, db_path: Path | None = None) -> None:
        """Migración inicial idempotente."""
        logger.info("Inicializando esquema de base de datos...")
        with cls.get_connection(db_path=db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metricas_diarias (
                    fecha DATE PRIMARY KEY,
                    ventas_totales DOUBLE,
                    numero_ordenes INTEGER,
                    ticket_promedio DOUBLE,
                    unidades_vendidas INTEGER
                );
                CREATE TABLE IF NOT EXISTS anomalias (
                    fecha DATE,
                    serie VARCHAR,
                    valor DOUBLE,
                    esperado DOUBLE,
                    severidad DOUBLE,
                    PRIMARY KEY (fecha, serie)
                );
                CREATE TABLE IF NOT EXISTS analisis_agente (
                    fecha DATE,
                    serie VARCHAR,
                    hipotesis TEXT,
                    evidencia TEXT,
                    confianza VARCHAR,
                    fecha_analisis TIMESTAMP,
                    PRIMARY KEY (fecha, serie)
                );
            """)
