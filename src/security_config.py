"""Configuração local: nenhum segredo deve ser definido neste módulo."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)


def required_env(name):
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    return value


def configured_path(name, default=None):
    value = os.getenv(name) or default
    if not value:
        raise RuntimeError(f"Variável obrigatória ausente: {name}")
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


def database_url():
    return URL.create(
        "postgresql+psycopg2",
        username=required_env("POSTGRES_USER"),
        password=required_env("POSTGRES_PASSWORD"),
        host=required_env("POSTGRES_HOST"),
        port=int(required_env("POSTGRES_PORT")),
        database=required_env("POSTGRES_DB"),
    )


def gestta_token():
    token = configured_path("GESTTA_TOKEN_PATH").read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Arquivo de token vazio")
    return token
