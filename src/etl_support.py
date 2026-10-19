"""Validação, HTTP e arquivos temporários compartilhados pelo ETL."""
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import tempfile

import pandas as pd
import requests

LOG = logging.getLogger(__name__)


class ETLError(RuntimeError):
    """Erro operacional cuja mensagem não contém dados da origem."""


def request_json(method, url, *, http=None, **kwargs):
    client = http if http is not None else requests
    response = None
    try:
        response = getattr(client, method)(url, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        status = getattr(response, "status_code", None)
        detail = f" HTTP {status}." if isinstance(status, int) else "."
        raise ETLError("Falha na requisição de extração" + detail) from None
    except ValueError:
        raise ETLError("Resposta JSON inválida na extração.") from None


def notify(message, *, http=None):
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    try:
        response = (http or requests).post(webhook, json={"text": message}, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        LOG.warning("Não foi possível enviar o alerta ao Slack.")


def require_columns(frame, columns, stage):
    if frame.columns.duplicated().any():
        raise ETLError(f"{stage}: colunas duplicadas.")
    if not set(columns).issubset(frame.columns):
        raise ETLError(f"{stage}: faltam colunas obrigatórias.")
    if frame.empty:
        raise ETLError(f"{stage}: lote vazio; última versão será preservada.")


def text_identifier(series, stage):
    # Identificadores que chegam como número podem ter perdido zeros na origem.
    if series.dropna().map(lambda v: not isinstance(v, str)).any():
        raise ETLError(f"{stage}: identificador deve chegar como texto.")
    return series.astype("string").str.strip().replace("", pd.NA)


def numeric_key(series, stage):
    if series.map(lambda value: isinstance(value, bool)).any():
        raise ETLError(f"{stage}: chave booleana inválida.")
    try:
        result = pd.to_numeric(series, errors="raise").astype("Int64")
    except (TypeError, ValueError, OverflowError):
        raise ETLError(f"{stage}: chave deve ser um inteiro válido.") from None
    if result.isna().any():
        raise ETLError(f"{stage}: chave obrigatória ausente.")
    return result


def dates(series, stage):
    values = series.replace("", pd.NA)
    try:
        return values.map(lambda value: None if pd.isna(value) else pd.Timestamp(value).date())
    except (TypeError, ValueError, OverflowError):
        raise ETLError(f"{stage}: data inválida.") from None


def stage_file(target, writer):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + target.stem + "-", suffix=target.suffix,
                                     dir=target.parent)
    os.close(fd)
    temporary = Path(temporary)
    try:
        writer(temporary)
        return temporary, target
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def stage_csv(frame, target):
    return stage_file(target, lambda p: frame.to_csv(p, index=False, encoding="utf-8-sig"))


def stage_json(value, target):
    return stage_file(target, lambda p: p.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"))


def discard(files):
    for temporary, _ in files:
        Path(temporary).unlink(missing_ok=True)


def publish_files(files):
    # Cada rename é atômico; o conjunto não é uma transação distribuída.
    for temporary, target in files:
        os.replace(temporary, target)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_snapshot_pair(gestta_path, notion_path, manifest_path):
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if manifest.get("status") != "complete":
            raise ETLError("A execução de origem não está concluída.")
        buffers = []
        for key, path in (("gestta", gestta_path), ("notion", notion_path)):
            content = Path(path).read_bytes()
            if manifest["sha256"][key] != hashlib.sha256(content).hexdigest():
                raise ETLError("Arquivos não pertencem ao snapshot aprovado.")
            buffers.append(content)
    except (OSError, ValueError, KeyError, TypeError):
        raise ETLError("Snapshot não verificável; execute src/pipeline.py.") from None
    # Retornar frames já lidos evita a etapa de transformação reler arquivos trocados.
    return tuple(pd.read_csv(io.BytesIO(content), dtype="string", keep_default_na=False)
                 for content in buffers)
