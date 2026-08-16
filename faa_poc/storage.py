"""Small append-safe CSV store plus persistent indexes/state."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from .constants import ACTIVE_ALERT_FIELDS, ACTIVE_VIDEO_FIELDS, PROCESSING_STATUS_FIELDS

def utcnow() -> datetime: return datetime.now(timezone.utc)
def utcnow_iso() -> str: return utcnow().isoformat()
def out_dir(config: dict) -> Path:
    path = Path(config["OUTPUT_DIR"]); path.mkdir(parents=True, exist_ok=True); return path

def append_csv(config: dict, filename: str, rows: Iterable[dict], fields: Sequence[str]) -> int:
    data = list(rows)
    if not data: return 0
    path = out_dir(config)/filename
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        if path.stat().st_size == 0: writer.writeheader()
        writer.writerows(data)
    return len(data)

def overwrite_csv(config: dict, filename: str, rows: Iterable[dict], fields: Sequence[str]) -> int:
    data = list(rows); path = out_dir(config)/filename
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader(); writer.writerows(data)
    return len(data)

def read_csv(config: dict, filename: str) -> list[dict]:
    path = out_dir(config)/filename
    if not path.exists(): return []
    with path.open(encoding="utf-8") as handle: return list(csv.DictReader(handle))

def build_set_index(config: dict, filename: str, key: str) -> set[str]:
    return {row[key] for row in read_csv(config, filename) if row.get(key)}

def build_pair_index(config: dict, filename: str, first: str, second: str) -> set[tuple[str,str]]:
    return {(str(row.get(first)), str(row.get(second))) for row in read_csv(config, filename) if row.get(first) and row.get(second)}

def load_status(config: dict) -> dict[str, dict]:
    return {str(row["cod_alerta"]): row for row in read_csv(config, "alert_processing_status.csv") if row.get("cod_alerta")}

def save_status(config: dict, status: dict[str, dict]) -> None:
    overwrite_csv(config, "alert_processing_status.csv", status.values(), PROCESSING_STATUS_FIELDS)

def load_active_alerts(config: dict) -> list[dict]: return read_csv(config, "active_alert_events.csv")
def save_active_alerts(config: dict, rows: list[dict]) -> None: overwrite_csv(config, "active_alert_events.csv", rows, ACTIVE_ALERT_FIELDS)
def load_active_videos(config: dict) -> list[dict]: return read_csv(config, "active_video_tracking.csv")
def save_active_videos(config: dict, rows: list[dict]) -> None: overwrite_csv(config, "active_video_tracking.csv", rows, ACTIVE_VIDEO_FIELDS)
