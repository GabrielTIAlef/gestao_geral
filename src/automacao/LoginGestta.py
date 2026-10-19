"""Provisiona um token autorizado sem automação do navegador ou clipboard."""
from getpass import getpass
from pathlib import Path
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from security_config import configured_path


def main():
    token_path = configured_path("GESTTA_TOKEN_PATH")
    if token_path.exists():
        raise RuntimeError("Arquivo já existe; faça a rotação pelo procedimento autorizado.")
    token = getpass("Token Gestta de uma conta autorizada (entrada oculta): ").strip()
    if not token:
        raise RuntimeError("Token vazio")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    # 0o600 é aplicado em sistemas POSIX; no Windows configure também a ACL.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(token)
    print("Token salvo. Restrinja o acesso ao arquivo à conta da automação.")


if __name__ == "__main__":
    main()
