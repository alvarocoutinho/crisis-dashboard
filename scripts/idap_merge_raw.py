"""Mescla o .jsonl.gz bruto de um dia (destino) com outro (origem), sem duplicar identificadores.

Usado pelo workflow idap.yml antes de publicar um dia que já existe no Release e
não foi baixado no início do job, para que um upload nunca apague alertas já arquivados.
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from odrd_idap.store import merge_raw_day  # noqa: E402

destino, origem = Path(sys.argv[1]), Path(sys.argv[2])
with gzip.open(origem, "rt", encoding="utf-8") as fh:
    linhas = [ln.rstrip("\n") for ln in fh if ln.strip()]
print(f"{destino.name}: +{merge_raw_day(destino, linhas)} vindos de {origem.name}")
