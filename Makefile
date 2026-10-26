.PHONY: setup lint test demo run dashboard benchmark clean

# PYTHONPATH=. porque los módulos se importan como `src.…` desde la raíz.
RUN = PYTHONPATH=. uv run

setup:
	uv sync

lint:
	uv run ruff check src tests evals scripts

test:
	$(RUN) pytest tests/ -v

# Datos sintéticos con el formato de Online Retail: corre todo sin descargar nada.
demo:
	$(RUN) python scripts/generar_datos_sinteticos.py data/demo.csv
	DATAWATCH_DATA_PATH=data/demo.csv $(RUN) python -m src.main

run:
	$(RUN) python -m src.main

dashboard:
	$(RUN) streamlit run src/ui/dashboard.py

benchmark:
	$(RUN) python -m evals.benchmark

clean:
	rm -rf data/*.db reportes/*.md evals/resultados
