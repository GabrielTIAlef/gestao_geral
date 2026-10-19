"""Coleta Gestta completa; importar este módulo não executa integrações."""
from datetime import date
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from etl_support import ETLError, discard, notify, publish_files, request_json, stage_csv, stage_json
from security_config import configured_path, gestta_token

LOG = logging.getLogger(__name__)
URL = "https://api.gestta.com.br/core/customer/task/report"


def periods(year=None):
    year = year or date.today().year
    quarters = (("01-01", "03-31"), ("04-01", "06-30"),
                ("07-01", "09-30"), ("10-01", "12-31"))
    return [(f"{y}-{start}", f"{y}-{end}") for y in (year-1, year, year+1)
            for start, end in quarters]


def collect(*, token=None, http=None, requested_periods=None):
    headers = {"authorization": token if token is not None else gestta_token(),
               "Content-Type": "application/json"}
    frames = []
    selected = periods() if requested_periods is None else list(requested_periods)
    if not selected:
        raise ETLError("Gestta: nenhum período selecionado.")
    for start, end in selected:
        payload = {"type": "CUSTOMER_TASK", "filter": "CURRENT_MONTH",
                   "dates": {"startDate": f"{start}T00:00:00-03:00",
                             "endDate": f"{end}T23:59:59-03:00"}}
        data = request_json("post", URL, http=http, headers=headers, json=payload)
        if isinstance(data, dict) and (data.get("has_more") is True or data.get("next_cursor")):
            raise ETLError("Gestta: resposta indica paginação; contrato completo necessário antes da carga.")
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ETLError("Gestta: contrato de resposta inesperado.")
        if data:
            frames.append(pd.json_normalize(data))
        LOG.info("Extração Gestta: período=%s/%s linhas=%d", start, end, len(data))
    if not frames:
        raise ETLError("Gestta: lote total vazio; última versão preservada.")
    return pd.concat(frames, ignore_index=True)


def export(frame):
    from transformacao.PBI_OS import transformar_gestta
    transformar_gestta(frame)  # Validar antes de tocar os arquivos publicados.
    files = []
    try:
        files.append(stage_csv(frame, configured_path("GESTTA_CSV_PATH", "data/gestta_relatorios.csv")))
        files.append(stage_json(frame.astype(object).where(frame.notna(), None).to_dict("records"),
                                configured_path("DATA_DIR", "data") / "gestta_relatorios.json"))
        publish_files(files)
    finally:
        discard(files)


def main():
    try:
        export(collect())
        LOG.info("Extração Gestta concluída. Execute pipeline.py para a carga coordenada.")
    except Exception:
        notify("Falha na extração Gestta; publicação interrompida.")
        raise ETLError("Extração Gestta falhou; nenhuma etapa seguinte foi iniciada.") from None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
