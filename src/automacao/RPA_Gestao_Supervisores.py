"""Entrada compatível para solicitar atualização do painel."""
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from automacao.powerbi_refresh import run as refresh


def run():
    return refresh("POWERBI_DATASET_SUPERVISORES")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
