"""normalize_priority_tier_v0_2.py

One-shot para corrigir resíduo da migração v0.1→v0.2 onde alertas migrados
retroativamente ficaram com priority_tier='acompanhamento' — valor que em v0.2
foi movido para o campo `flag`. priority_tier em v0.2 é APENAS metadado visual
do nível CEMADEN (muito_alto/alto/moderado).

O `build_live.py` já normaliza ao gerar `live.json`, então o dashboard mostra
corretamente. Este script é OPCIONAL: só limpa o dado em disco para consistência
auditável do state.json.

Uso:
    python scripts/normalize_priority_tier_v0_2.py --state src/data/state.json
    python scripts/normalize_priority_tier_v0_2.py --state src/data/state.json --dry-run
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


NIVEL_TO_TIER = {
    "Muito Alto": "muito_alto",
    "Alto": "alto",
    "Moderado": "moderado",
}


def normalize(state: dict) -> tuple[dict, list[str]]:
    """Retorna (state_modificado, lista_de_ids_corrigidos)."""
    fixed = []
    for bucket in ("active_alerts", "extended_window_alerts", "archived_alerts"):
        for aid, alert in state.get(bucket, {}).items():
            if alert.get("priority_tier") == "acompanhamento":
                nivel = alert.get("nivel_atual", "Moderado")
                alert["priority_tier"] = NIVEL_TO_TIER.get(nivel, "moderado")
                fixed.append(f"{aid} ({bucket}): acompanhamento → {alert['priority_tier']}")
    return state, fixed


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--backup-dir", type=Path, default=Path("src/data/backups"))
    args = p.parse_args()

    with args.state.open("r", encoding="utf-8") as f:
        state = json.load(f)

    if state.get("schema_version") != "0.2":
        print(f"ERRO: state.json não está em v0.2 (schema_version={state.get('schema_version')})")
        return 1

    state, fixed = normalize(state)

    if not fixed:
        print("Nada a fazer — nenhum alerta com priority_tier='acompanhamento'")
        return 0

    print(f"{len(fixed)} alertas a corrigir:")
    for line in fixed:
        print(f"  {line}")

    if args.dry_run:
        print("\n=== DRY-RUN: nada escrito ===")
        return 0

    args.backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = args.backup_dir / f"state.v0_2.pre-normalize.{ts}.json"
    shutil.copy2(args.state, backup)
    print(f"\nBackup: {backup}")

    with args.state.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"State normalizado: {args.state}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
