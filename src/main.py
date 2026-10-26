from src.ai.investigator import ClaudeInvestigator
from src.core.config import logger
from src.core.db import DatabaseManager
from src.data.detect import AnomalyDetector
from src.data.ingest import DataIngestionPipeline
from src.reporte import escribir_reporte


def main() -> None:
    logger.info("=== Iniciando pipeline de Datawatch ===")
    DatabaseManager.initialize_schema()
    DataIngestionPipeline().execute()
    AnomalyDetector().execute()
    ClaudeInvestigator().execute()
    logger.info(f"Reporte: {escribir_reporte()}")
    logger.info("=== Pipeline completado ===")


if __name__ == "__main__":
    main()
