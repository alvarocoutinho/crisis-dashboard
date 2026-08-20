"""Freeze v1.0.0 do ODRD — gera ZIP determinístico + SHA-256 + MANIFEST.

Uso:
    python scripts/freeze_v1.py

Saída em ./freeze/:
    ODRD-core-v1.0.0.zip        — ZIP determinístico do repo
    ODRD-core-v1.0.0.sha256     — hash SHA-256 do ZIP
    MANIFEST.txt                 — lista de arquivos + hash de cada
    FREEZE_v1.0.0.md             — sumário do freeze (commit SHA, timestamps)

Determinismo: mesma árvore Git → mesmo hash do ZIP. Isso permite verificação
por terceiros: quem baixar do Zenodo pode rerodar este script sobre o commit
apontado e conferir que o hash bate.

Determinismo é obtido por:
    - Ordenação alfabética estável das entradas do ZIP
    - Timestamp fixo (data do commit HEAD, não wallclock)
    - Compressão nível fixo (ZIP_DEFLATED, level=6)
    - Exclusão de artefatos não-fonte (.git, node_modules, dist, cache, etc.)
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# ==============================================================================
# Configuração
# ==============================================================================

VERSION = "1.0.0"
PACKAGE_NAME = f"ODRD-core-v{VERSION}"

# Diretórios/padrões a excluir (não fazem parte da baseline técnica)
EXCLUDE_DIRS = {
    ".git", "node_modules", "dist", "build", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".vercel", ".next", ".turbo", "freeze",
}
EXCLUDE_FILES = {
    ".DS_Store", "Thumbs.db", ".env", ".env.local", ".env.production",
}
EXCLUDE_EXT = {".pyc", ".pyo", ".log", ".swp", ".swo"}
EXCLUDE_PATH_CONTAINS = {
    "src/data/backups/",  # backups automáticos da migração v0.1→v0.2
}

# ==============================================================================
# Utilitários
# ==============================================================================

def run_git(args: list[str], cwd: Path) -> str:
    """Executa comando git e retorna stdout stripped. Erro → aborta."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print(f"[freeze] ERRO em `git {' '.join(args)}`:\n{result.stderr}",
              file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def sha256_of_file(path: Path) -> str:
    """SHA-256 de um arquivo, streaming em chunks de 1MB."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def should_exclude(rel_path: str) -> bool:
    """Retorna True se o caminho deve ser excluído do freeze."""
    parts = Path(rel_path).parts
    # Diretório em qualquer nível
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    # Arquivo por nome
    if parts and parts[-1] in EXCLUDE_FILES:
        return True
    # Extensão
    if parts and Path(parts[-1]).suffix in EXCLUDE_EXT:
        return True
    # Substring no path
    norm = rel_path.replace(os.sep, "/")
    for pattern in EXCLUDE_PATH_CONTAINS:
        if pattern in norm:
            return True
    return False


def collect_files(repo_root: Path) -> list[tuple[str, Path]]:
    """Coleta todos os arquivos do repo, aplicando exclusões.

    Retorna lista de (rel_path_posix, abs_path), ordenada alfabeticamente.
    """
    entries: list[tuple[str, Path]] = []
    for abs_path in repo_root.rglob("*"):
        if not abs_path.is_file():
            continue
        rel = abs_path.relative_to(repo_root)
        rel_posix = rel.as_posix()
        if should_exclude(rel_posix):
            continue
        entries.append((rel_posix, abs_path))
    entries.sort(key=lambda x: x[0])
    return entries


def build_deterministic_zip(
    entries: list[tuple[str, Path]],
    output_zip: Path,
    fixed_dt: datetime,
) -> None:
    """Constrói ZIP com metadados fixos → hash determinístico.

    Timestamp de cada entry = fixed_dt (típico: data do commit HEAD).
    """
    date_time = (
        fixed_dt.year, fixed_dt.month, fixed_dt.day,
        fixed_dt.hour, fixed_dt.minute, fixed_dt.second,
    )
    with zipfile.ZipFile(
        output_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
    ) as zf:
        for rel_posix, abs_path in entries:
            arcname = f"{PACKAGE_NAME}/{rel_posix}"
            zi = zipfile.ZipInfo(filename=arcname, date_time=date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16  # rw-r--r--
            with open(abs_path, "rb") as f:
                zf.writestr(zi, f.read())


def write_manifest(
    entries: list[tuple[str, Path]],
    output_manifest: Path,
) -> None:
    """Escreve MANIFEST.txt: 1 linha por arquivo com hash SHA-256 + size."""
    lines = [
        f"# ODRD Freeze v{VERSION} — MANIFEST",
        f"# Formato: <sha256>  <bytes>  <path>",
        "",
    ]
    for rel_posix, abs_path in entries:
        h = sha256_of_file(abs_path)
        size = abs_path.stat().st_size
        lines.append(f"{h}  {size:>12}  {rel_posix}")
    output_manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(
    output_md: Path,
    commit_sha: str,
    commit_date_iso: str,
    zip_path: Path,
    zip_sha: str,
    zip_bytes: int,
    n_files: int,
    freeze_run_at: str,
) -> None:
    """Escreve FREEZE_v1.0.0.md com sumário legível do freeze."""
    md = f"""# ODRD Core — Freeze v{VERSION}

Este documento sumariza o freeze da versão {VERSION} do ODRD.

## Referência Git

- **Commit SHA (HEAD):** `{commit_sha}`
- **Data do commit (UTC):** {commit_date_iso}
- **Tag:** `v{VERSION}` (criar após review)

## Pacote

- **Arquivo:** `{zip_path.name}`
- **SHA-256:** `{zip_sha}`
- **Tamanho:** {zip_bytes:,} bytes ({zip_bytes / 1024 / 1024:.2f} MiB)
- **Arquivos incluídos:** {n_files}

## Verificação

Para verificar a integridade do pacote:

```bash
# Linux/Mac
sha256sum -c ODRD-core-v{VERSION}.sha256

# Windows (PowerShell)
Get-FileHash ODRD-core-v{VERSION}.zip -Algorithm SHA256
```

O hash acima deve coincidir com o conteúdo de `ODRD-core-v{VERSION}.sha256`.

## Reprodutibilidade

Para reconstruir o pacote a partir do repositório no commit `{commit_sha}`:

```bash
git checkout {commit_sha}
python scripts/freeze_v1.py
```

O ZIP resultante deve ter exatamente o mesmo hash SHA-256. Determinismo é
obtido por: ordenação alfabética estável das entradas, timestamp fixo (data
do commit HEAD), compressão de nível fixo, exclusão de artefatos não-fonte.

## Contexto de PI

Este freeze estabelece linha de base tecnológica anterior a qualquer vínculo
institucional Unicamp ou financiamento FAPESP. Ver `docs/ODRD_decisoes_PI_v1_pre_FAPESP.md`
para o raciocínio estratégico.

- **Licença:** dual — PolyForm Noncommercial 1.0.0 (Parte A) + reserva de uso
  comercial (Parte B). Ver `LICENSE` na raiz do pacote.
- **DOI Zenodo:** a preencher após depósito.

## Freeze executado em

{freeze_run_at}
"""
    output_md.write_text(md, encoding="utf-8")


# ==============================================================================
# Main
# ==============================================================================

def main() -> None:
    # Descobre raiz do repo (o script vive em scripts/, subir 1 nível)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    # Validações Git
    if not (repo_root / ".git").exists():
        print(f"[freeze] ERRO: {repo_root} não é um repo Git.", file=sys.stderr)
        sys.exit(1)

    commit_sha = run_git(["rev-parse", "HEAD"], repo_root)
    commit_date_iso = run_git(
        ["show", "-s", "--format=%cI", "HEAD"], repo_root
    )
    commit_dt = datetime.fromisoformat(commit_date_iso).astimezone(timezone.utc)

    # Avisa se working tree suja
    dirty = run_git(["status", "--porcelain"], repo_root)
    if dirty:
        print("[freeze] AVISO: working tree tem mudanças não commitadas.",
              file=sys.stderr)
        print("        O freeze reflete o estado no disco, não o HEAD.",
              file=sys.stderr)
        print("        Para freeze reproduzível, commit antes de rodar.",
              file=sys.stderr)
        print("", file=sys.stderr)

    # Diretório de saída
    out_dir = repo_root / "freeze"
    out_dir.mkdir(exist_ok=True)

    zip_path = out_dir / f"{PACKAGE_NAME}.zip"
    sha_path = out_dir / f"{PACKAGE_NAME}.sha256"
    manifest_path = out_dir / "MANIFEST.txt"
    summary_path = out_dir / f"FREEZE_v{VERSION}.md"

    print(f"[freeze] repo:        {repo_root}")
    print(f"[freeze] commit:      {commit_sha[:12]} ({commit_date_iso})")
    print(f"[freeze] output:      {out_dir}")

    # Coleta arquivos
    print("[freeze] coletando arquivos...")
    entries = collect_files(repo_root)
    print(f"[freeze] {len(entries)} arquivos serão incluídos")

    # ZIP determinístico
    print(f"[freeze] gerando {zip_path.name}...")
    build_deterministic_zip(entries, zip_path, commit_dt)

    # Hash do ZIP
    print("[freeze] calculando SHA-256 do ZIP...")
    zip_sha = sha256_of_file(zip_path)
    zip_bytes = zip_path.stat().st_size
    sha_path.write_text(f"{zip_sha}  {zip_path.name}\n", encoding="utf-8")

    # Manifest
    print(f"[freeze] gerando {manifest_path.name}...")
    write_manifest(entries, manifest_path)

    # Sumário
    freeze_run_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_summary(
        summary_path, commit_sha, commit_date_iso,
        zip_path, zip_sha, zip_bytes, len(entries), freeze_run_at,
    )

    # Relatório final
    print()
    print("=" * 70)
    print(f"FREEZE v{VERSION} COMPLETO")
    print("=" * 70)
    print(f"  ZIP:       {zip_path}")
    print(f"  SHA-256:   {zip_sha}")
    print(f"  Tamanho:   {zip_bytes:,} bytes ({zip_bytes / 1024 / 1024:.2f} MiB)")
    print(f"  Manifest:  {manifest_path}")
    print(f"  Sumário:   {summary_path}")
    print()
    print("Próximos passos:")
    print(f"  1. git tag -a v{VERSION} -m 'ODRD Core v{VERSION} — pre-institutional baseline'")
    print(f"  2. git push --tags")
    print(f"  3. Criar release no GitHub apontando para a tag, anexar o ZIP")
    print(f"  4. Upload manual no Zenodo (open access, licença dual)")
    print(f"  5. Substituir placeholder DOI em README.md e CHANGELOG.md")


if __name__ == "__main__":
    main()
