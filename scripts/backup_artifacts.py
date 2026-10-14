"""Backup mensal dos artifacts do pipeline (workflow backup-mensal.yml).

Os dados brutos de cada execução do pipeline (CSVs com comentários, vídeos e
candidatos) só existem como artifacts do GitHub, que expiram em 90 dias. Este
script baixa todos os artifacts ainda válidos com o prefixo indicado e grava um
manifesto (nome, id, datas, tamanho, sha256). O workflow cifra a pasta num .7z e
publica como um único artifact, para o pesquisador baixar e guardar.

Como cada backup leva TODOS os artifacts ainda válidos (até 90 dias), dois
backups seguidos se sobrepõem: perder um mês não perde dados.

Também apaga, sob pedido explícito, os artifacts listados num manifesto já
commitado — ou seja, só o que comprovadamente entrou num backup.

Uso (no Actions, com GITHUB_TOKEN):
    python scripts/backup_artifacts.py baixar --saida /tmp/backup --manifesto data/backups/manifesto_AAAA-MM.csv
    python scripts/backup_artifacts.py apagar --manifesto data/backups/manifesto_AAAA-MM.csv --confirmar APAGAR
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

import requests

API = "https://api.github.com"
CAMPOS = ["nome", "id", "criado_em", "expira_em", "bytes", "sha256", "run_id"]


def _sessao() -> tuple[requests.Session, str]:
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        sys.exit("GITHUB_TOKEN e GITHUB_REPOSITORY são obrigatórios")
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                      "X-GitHub-Api-Version": "2022-11-28"})
    return s, repo


def listar(s: requests.Session, repo: str, prefixo: str) -> list[dict]:
    out, page = [], 1
    while True:
        r = s.get(f"{API}/repos/{repo}/actions/artifacts", params={"per_page": 100, "page": page}, timeout=60)
        r.raise_for_status()
        arts = r.json().get("artifacts", [])
        out += [a for a in arts if a["name"].startswith(prefixo) and not a.get("expired")]
        if len(arts) < 100:
            return sorted(out, key=lambda a: a["created_at"])
        page += 1


def baixar(args) -> int:
    s, repo = _sessao()
    arts = listar(s, repo, args.prefixo)
    args.saida.mkdir(parents=True, exist_ok=True)
    linhas, total = [], 0
    for a in arts:
        destino = args.saida / f"{a['name']}.zip"
        r = s.get(a["archive_download_url"], timeout=300)
        r.raise_for_status()
        destino.write_bytes(r.content)
        total += len(r.content)
        linhas.append({"nome": a["name"], "id": a["id"], "criado_em": a["created_at"], "expira_em": a["expires_at"],
                       "bytes": len(r.content), "sha256": hashlib.sha256(r.content).hexdigest(),
                       "run_id": (a.get("workflow_run") or {}).get("id", "")})
    args.manifesto.parent.mkdir(parents=True, exist_ok=True)
    with args.manifesto.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(linhas)
    primeiro = linhas[0]["criado_em"][:10] if linhas else "-"
    ultimo = linhas[-1]["criado_em"][:10] if linhas else "-"
    expira = min((l["expira_em"] for l in linhas), default="-")[:10]
    print(f"::notice title=Backup::{len(linhas)} artifacts ({total / 1e6:.1f} MB), de {primeiro} a {ultimo}; "
          f"o mais antigo expira em {expira}")
    return 0 if linhas else 1


def apagar(args) -> int:
    if args.confirmar != "APAGAR":
        sys.exit("para apagar, passe --confirmar APAGAR")
    s, repo = _sessao()
    with args.manifesto.open(encoding="utf-8") as fh:
        ids = [row["id"] for row in csv.DictReader(fh)]
    apagados = 0
    for i in ids:
        r = s.delete(f"{API}/repos/{repo}/actions/artifacts/{i}", timeout=60)
        if r.status_code in (204, 404):   # 404: já expirou ou já apagado
            apagados += r.status_code == 204
        else:
            print(f"::warning::falha ao apagar {i}: {r.status_code}")
    print(f"::notice title=Artifacts apagados::{apagados} de {len(ids)} listados em {args.manifesto.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baixar")
    b.add_argument("--saida", type=Path, required=True)
    b.add_argument("--manifesto", type=Path, required=True)
    b.add_argument("--prefixo", default="pipeline-crus-")
    d = sub.add_parser("apagar")
    d.add_argument("--manifesto", type=Path, required=True)
    d.add_argument("--confirmar", default="")
    args = ap.parse_args()
    return baixar(args) if args.cmd == "baixar" else apagar(args)


if __name__ == "__main__":
    raise SystemExit(main())
