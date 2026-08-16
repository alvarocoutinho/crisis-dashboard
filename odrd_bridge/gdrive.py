"""Upload de corpus cru para Google Drive via service account.

Padrão de custódia (M1): pasta existe no Drive pessoal do pesquisador,
compartilhada com o e-mail do service account (permissão Editor). Isso
mantém os dados sob a conta do pesquisador (LGPD) enquanto permite
que o pipeline automatizado escreva.

Estrutura de destino no Drive:
    ODRD-piloto-tecnico/                        (você cria)
      YYYY/                                     (auto)
        MM/                                     (auto)
          alerta_<cemaden_id>/                  (auto)
            metadata.json
            videos_metadata.jsonl
            comments_raw.jsonl
            predictions.jsonl
            collection_log.jsonl

Escrita é append-friendly: cada ciclo do pipeline anexa linhas novas ao
JSONL (não sobrescreve). Idempotência: se o mesmo comentário aparece
duas vezes num ciclo (retry), o dedup por comment_id acontece no state
antes de chegar aqui.

Falha graceful: qualquer erro no upload é logado mas NÃO derruba o
pipeline — o repositório principal (live.json / state.json) é mais
importante que a cópia dos crus.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseUpload
    _GDRIVE_AVAILABLE = True
except ImportError:
    _GDRIVE_AVAILABLE = False


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
"""Escopo mínimo: 'drive.file' só permite acesso a arquivos criados PELA
service account, não ao Drive inteiro do dono da pasta. Este é o escopo
seguro por padrão — não uses 'drive' completo."""

MIME_FOLDER = "application/vnd.google-apps.folder"


class GDriveUploader:
    """Cliente para upload em pasta compartilhada com service account.

    Uso típico:
        uploader = GDriveUploader.from_env(root_folder_name="ODRD-piloto-tecnico")
        uploader.upload_alert_snapshot(
            alert_id="cemaden_sp_2464",
            faa_output_dir=Path("/tmp/faa_pipeline_run"),
            predictions_df=df_pred,
        )
    """

    def __init__(self, service_account_info: dict, root_folder_id: str):
        if not _GDRIVE_AVAILABLE:
            raise RuntimeError(
                "google-api-python-client não instalado. "
                "Verifique requirements-pipeline.txt"
            )
        creds = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=DRIVE_SCOPES,
        )
        self.service = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.sa_email = service_account_info.get("client_email", "unknown")
        self.root_folder_id = root_folder_id
        self._folder_id_cache: dict[str, str] = {}

    @classmethod
    def from_env(
        cls,
        env_var: str = "GOOGLE_SERVICE_ACCOUNT_JSON",
        folder_id_env: str = "GDRIVE_FOLDER_ID",
    ) -> "GDriveUploader":
        """Constrói do secret GitHub Actions.

        Requer duas variáveis de ambiente:
        - GOOGLE_SERVICE_ACCOUNT_JSON: credenciais (JSON cru ou base64)
        - GDRIVE_FOLDER_ID: ID da pasta raiz no Drive (extraído da URL)

        Nota sobre escopo drive.file: como a service account usa escopo
        mínimo, ela não pode LISTAR pastas por nome — só acessa pastas
        cujo ID conhece a priori. Por isso passamos o ID direto em vez
        de buscar por nome. Segurança em profundidade > conveniência.
        """
        raw = os.environ.get(env_var, "").strip()
        if not raw:
            raise RuntimeError(f"variável {env_var} vazia ou não definida")

        folder_id = os.environ.get(folder_id_env, "").strip()
        if not folder_id:
            raise RuntimeError(
                f"variável {folder_id_env} vazia ou não definida. "
                f"Extraia o ID da URL da pasta no Drive (parte após /folders/)."
            )

        # Tenta base64 primeiro (mais robusto para GitHub Secrets)
        info = None
        if not raw.startswith("{"):
            try:
                import base64
                decoded = base64.b64decode(raw).decode("utf-8")
                info = json.loads(decoded)
            except Exception:
                pass

        if info is None:
            info = json.loads(raw)

        return cls(info, folder_id)

    def _validate_root_folder(self) -> str:
        """Confirma que a pasta raiz existe e é acessível pela SA.

        Com escopo drive.file, o get direto por ID funciona SE a SA foi
        compartilhada como Editor ou Viewer da pasta. Se falhar aqui,
        orienta o usuário.
        """
        try:
            folder = self.service.files().get(
                fileId=self.root_folder_id,
                fields="id, name, mimeType",
            ).execute()
        except HttpError as e:
            if e.resp.status in (403, 404):
                raise RuntimeError(
                    f"Pasta {self.root_folder_id} inacessível pela service account.\n"
                    f"Verifique:\n"
                    f"  1. A pasta existe no Drive\n"
                    f"  2. Foi compartilhada com {self.sa_email} como Editor\n"
                    f"  3. O ID em GDRIVE_FOLDER_ID bate com o da URL da pasta"
                ) from e
            raise

        if folder.get("mimeType") != MIME_FOLDER:
            raise RuntimeError(
                f"ID {self.root_folder_id} aponta para um arquivo, não pasta. "
                f"Verifique a URL no Drive."
            )
        return self.root_folder_id

    def _get_or_create_folder(self, name: str, parent_id: str) -> str:
        """Retorna id de pasta existente ou cria nova. Cache em memória."""
        cache_key = f"{parent_id}/{name}"
        if cache_key in self._folder_id_cache:
            return self._folder_id_cache[cache_key]

        query = (
            f"mimeType = '{MIME_FOLDER}' and "
            f"name = '{name}' and "
            f"'{parent_id}' in parents and "
            f"trashed = false"
        )
        resp = self.service.files().list(q=query, fields="files(id)", pageSize=1).execute()
        folders = resp.get("files", [])

        if folders:
            folder_id = folders[0]["id"]
        else:
            metadata = {"name": name, "mimeType": MIME_FOLDER, "parents": [parent_id]}
            created = self.service.files().create(body=metadata, fields="id").execute()
            folder_id = created["id"]

        self._folder_id_cache[cache_key] = folder_id
        return folder_id

    def _get_or_create_alert_folder(self, alert_id: str, now: datetime) -> str:
        """Cria árvore YYYY/MM/alerta_<id>/ dentro da pasta raiz."""
        root_id = self._validate_root_folder()
        year_id = self._get_or_create_folder(str(now.year), root_id)
        month_id = self._get_or_create_folder(f"{now.month:02d}", year_id)
        alert_folder = self._get_or_create_folder(f"alerta_{alert_id}", month_id)
        return alert_folder

    def _find_file_in_folder(self, name: str, folder_id: str) -> str | None:
        query = (
            f"name = '{name}' and "
            f"'{folder_id}' in parents and "
            f"trashed = false"
        )
        resp = self.service.files().list(q=query, fields="files(id)", pageSize=1).execute()
        files = resp.get("files", [])
        return files[0]["id"] if files else None

    def _download_file_content(self, file_id: str) -> str:
        """Baixa conteúdo de arquivo texto no Drive. Usado para append em JSONL."""
        buf = io.BytesIO()
        req = self.service.files().get_media(fileId=file_id)
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue().decode("utf-8")

    def _upload_or_replace(
        self, folder_id: str, filename: str, content: str, mime_type: str = "application/json"
    ) -> str:
        """Cria ou substitui arquivo. Retorna file_id."""
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")), mimetype=mime_type, resumable=False,
        )
        existing = self._find_file_in_folder(filename, folder_id)
        if existing:
            self.service.files().update(fileId=existing, media_body=media).execute()
            return existing
        created = self.service.files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        return created["id"]

    def _append_jsonl(self, folder_id: str, filename: str, new_lines: list[str]) -> str:
        """Append idempotente a JSONL: baixa existente, concatena, sobe. Se
        arquivo não existe, cria com só as linhas novas."""
        existing = self._find_file_in_folder(filename, folder_id)
        if existing:
            old_content = self._download_file_content(existing)
        else:
            old_content = ""

        # Garante \n no final se antigo não tem
        if old_content and not old_content.endswith("\n"):
            old_content += "\n"

        new_content = old_content + "\n".join(new_lines) + ("\n" if new_lines else "")
        return self._upload_or_replace(folder_id, filename, new_content, "application/x-ndjson")

    def upload_alert_snapshot(
        self,
        alert_id: str,
        faa_output_dir: Path,
        predictions_df: pd.DataFrame | None = None,
        collection_metadata: dict | None = None,
        now: datetime | None = None,
    ) -> dict[str, str]:
        """Envia snapshot completo de um alerta para o Drive.

        Args:
            alert_id: ex 'cemaden_sp_2464'
            faa_output_dir: pasta com CSVs do faa_poc
            predictions_df: DataFrame com predições (opcional)
            collection_metadata: dict com contexto do run (pipeline_version, etc.)
            now: timestamp de referência (default: agora UTC)

        Returns:
            Dict {filename: file_id} do que foi enviado.
        """
        now = now or datetime.now(timezone.utc)
        folder_id = self._get_or_create_alert_folder(alert_id, now)
        uploaded: dict[str, str] = {}

        cod_alerta = alert_id.split("_")[-1]

        # 1. metadata.json — sobrescreve com snapshot mais recente
        alerts_csv = faa_output_dir / "alerts_log.csv"
        if alerts_csv.exists():
            try:
                df = pd.read_csv(alerts_csv)
                mine = df[df["cod_alerta"].astype(str) == str(cod_alerta)]
                if not mine.empty:
                    meta = mine.iloc[-1].to_dict()
                    meta["_snapshot_at"] = now.isoformat()
                    meta["_pipeline_version"] = (collection_metadata or {}).get(
                        "pipeline_version", "unknown"
                    )
                    fid = self._upload_or_replace(
                        folder_id, "metadata.json",
                        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
                    )
                    uploaded["metadata.json"] = fid
            except Exception as e:
                print(f"[gdrive] falha metadata {alert_id}: {e}")

        # 2. videos_metadata.jsonl — append
        videos_csv = faa_output_dir / "youtube_alert_video_links.csv"
        if videos_csv.exists():
            try:
                df = pd.read_csv(videos_csv)
                mine = df[df["cod_alerta"].astype(str) == str(cod_alerta)]
                if not mine.empty:
                    lines = [
                        json.dumps({**row.to_dict(), "_ingested_at": now.isoformat()},
                                   ensure_ascii=False, default=str)
                        for _, row in mine.iterrows()
                    ]
                    fid = self._append_jsonl(folder_id, "videos_metadata.jsonl", lines)
                    uploaded["videos_metadata.jsonl"] = fid
            except Exception as e:
                print(f"[gdrive] falha videos {alert_id}: {e}")

        # 3. comments_raw.jsonl — append
        comments_csv = faa_output_dir / "youtube_comments_canonical.csv"
        if comments_csv.exists() and comments_csv.stat().st_size > 0:
            try:
                df = pd.read_csv(comments_csv)
                if "video_id" in df.columns:
                    # Filtrar comentários deste alerta via video_links
                    if videos_csv.exists():
                        vdf = pd.read_csv(videos_csv)
                        alert_video_ids = set(
                            vdf[vdf["cod_alerta"].astype(str) == str(cod_alerta)]["video_id"]
                        )
                        mine = df[df["video_id"].isin(alert_video_ids)]
                    else:
                        mine = df
                    if not mine.empty:
                        lines = [
                            json.dumps({**row.to_dict(), "_ingested_at": now.isoformat()},
                                       ensure_ascii=False, default=str)
                            for _, row in mine.iterrows()
                        ]
                        fid = self._append_jsonl(folder_id, "comments_raw.jsonl", lines)
                        uploaded["comments_raw.jsonl"] = fid
            except Exception as e:
                print(f"[gdrive] falha comments {alert_id}: {e}")

        # 4. predictions.jsonl — append
        if predictions_df is not None and not predictions_df.empty:
            try:
                if "video_id" in predictions_df.columns and videos_csv.exists():
                    vdf = pd.read_csv(videos_csv)
                    alert_video_ids = set(
                        vdf[vdf["cod_alerta"].astype(str) == str(cod_alerta)]["video_id"]
                    )
                    mine = predictions_df[predictions_df["video_id"].isin(alert_video_ids)]
                else:
                    mine = predictions_df
                if not mine.empty:
                    lines = [
                        json.dumps({**row.to_dict(), "_ingested_at": now.isoformat()},
                                   ensure_ascii=False, default=str)
                        for _, row in mine.iterrows()
                    ]
                    fid = self._append_jsonl(folder_id, "predictions.jsonl", lines)
                    uploaded["predictions.jsonl"] = fid
            except Exception as e:
                print(f"[gdrive] falha predictions {alert_id}: {e}")

        # 5. collection_log.jsonl — sempre append, mesmo se todos os outros falharem
        try:
            log_entry = {
                "collected_at": now.isoformat(),
                "alert_id": alert_id,
                "files_uploaded": list(uploaded.keys()),
                "pipeline_version": (collection_metadata or {}).get("pipeline_version"),
                "run_id": (collection_metadata or {}).get("run_id"),
            }
            fid = self._append_jsonl(
                folder_id, "collection_log.jsonl",
                [json.dumps(log_entry, ensure_ascii=False, default=str)],
            )
            uploaded["collection_log.jsonl"] = fid
        except Exception as e:
            print(f"[gdrive] falha collection_log {alert_id}: {e}")

        return uploaded


def upload_run_to_drive(
    alert_ids: list[str],
    faa_output_dir: Path,
    predictions_df: pd.DataFrame | None,
    pipeline_version: str,
    run_id: str,
) -> dict[str, dict[str, str]]:
    """Wrapper de alto nível chamado pelo pipeline.py.

    Envia snapshots de todos os alertas processados neste ciclo. Erros
    individuais não param o loop — pipeline continua e reporta parciais.

    Requer secrets no env:
    - GOOGLE_SERVICE_ACCOUNT_JSON: credenciais (JSON cru ou base64)
    - GDRIVE_FOLDER_ID: ID da pasta raiz no Drive
    """
    if not os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        print("[gdrive] GOOGLE_SERVICE_ACCOUNT_JSON não definido — upload pulado")
        return {}
    if not os.environ.get("GDRIVE_FOLDER_ID"):
        print("[gdrive] GDRIVE_FOLDER_ID não definido — upload pulado")
        return {}

    try:
        uploader = GDriveUploader.from_env()
    except Exception as e:
        print(f"[gdrive] falha ao inicializar cliente: {e}")
        return {}

    results: dict[str, dict[str, str]] = {}
    metadata = {"pipeline_version": pipeline_version, "run_id": run_id}
    for alert_id in alert_ids:
        try:
            results[alert_id] = uploader.upload_alert_snapshot(
                alert_id=alert_id,
                faa_output_dir=faa_output_dir,
                predictions_df=predictions_df,
                collection_metadata=metadata,
            )
            n = len(results[alert_id])
            print(f"[gdrive] {alert_id}: {n} arquivos enviados/atualizados")
        except Exception as e:
            print(f"[gdrive] falha total no alerta {alert_id}: {e}")
            results[alert_id] = {}

    return results
