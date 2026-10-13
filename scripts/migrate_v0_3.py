"""Migração única para o pipeline v0.3.0 (correção de cota, 13/10/2026).

Executa, sobre o state/live atuais do repositório:
1. normalize_legacy_v03 — finaliza a janela dos alertas legados com prova de
   coleta pós-janela; marca como não verificados os que não têm prova.
2. restore_live_from_history — devolve ao live.json o conteúdo apagado por
   falhas de cota e reconta n_comments_valid (legado preservado).

Idempotente. Precisa do histórico git completo (o workflow
`migrate-v0.3.yml` faz checkout com fetch-depth: 0). Depende só de
`requests` (importado pelo pacote faa_poc). O live.json é remontado por
completo no próximo run do pipeline.

Uso: python scripts/migrate_v0_3.py [--dry-run]
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(REPO_ROOT))

from odrd_bridge import state_manager  # noqa: E402

STATE_PATH = REPO_ROOT / "src" / "data" / "state.json"


def main() -> int:
    dry = "--dry-run" in sys.argv
    state = state_manager.load_state(STATE_PATH)
    finalized = state_manager.normalize_legacy_v03(state, datetime.now(timezone.utc))
    unverified = [aid for b in ("active_alerts", "extended_window_alerts")
                  for aid, m in state.get(b, {}).items() if m.get("legacy_unverified")]
    print(f"janela finalizada (legado): {len(finalized)}")
    print(f"sem prova de coleta (recoleta no próximo ciclo): {unverified}")
    if not dry:
        state_manager.save_state(state, STATE_PATH)

    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "restore_live_from_history.py"),
           "--recount-state"] + (["--dry-run"] if dry else [])
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
