"""Conversão dos outputs do faa_poc + predições BERTimbau em live.json/state.json.

Ponto de contato entre o pipeline frozen (faa_poc/) e o dashboard React.
Consome os CSVs produzidos pelo faa_poc + o DataFrame de predições devolvido
por odrd_bridge.bertimbau.predict_comments() e gera os dois JSONs que o
dashboard consome.

Uso (dentro do notebook Colab):

    from odrd_bridge.build_live import build_live_json, build_state_json
    live = build_live_json(
        output_dir='/content/faa_poc_full_test',
        predictions_df=df_pred,
        pilot_mode=True,
        dry_run=False,  # dados reais dos alertas de hoje
        pipeline_version='0.1.0',
    )
    state = build_state_json(...)
"""
from __future__ import annotations

import json
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .bertimbau import CATEGORY_ORDER

# Rótulos legíveis para o dashboard (devem casar com events.json)
CATEGORY_LABELS = {
    "solidariedade_oracao_luto": "Solidariedade / oração / luto",
    "ajuda_resgate_doacoes": "Ajuda / resgate / doações",
    "responsabilizacao_governanca": "Responsabilização / governança",
    "infraestrutura_ocupacao_risco": "Infraestrutura / ocupação de risco",
    "clima_chuva_meio_ambiente": "Clima / chuva / meio ambiente",
    "experiencia_pessoal_local": "Experiência pessoal / local",
    "alerta_prevencao_cobranca": "Alerta / prevenção / cobrança",
    "critica_midia_informacao": "Crítica à mídia / informação",
}

# Rótulos curtos para top_categories dos cards de vídeo
SHORT_LABELS = {
    "solidariedade_oracao_luto": "Solidariedade",
    "ajuda_resgate_doacoes": "Ajuda",
    "responsabilizacao_governanca": "Responsabilização",
    "infraestrutura_ocupacao_risco": "Infraestrutura",
    "clima_chuva_meio_ambiente": "Clima/chuva",
    "experiencia_pessoal_local": "Experiência",
    "alerta_prevencao_cobranca": "Alerta",
    "critica_midia_informacao": "Crítica mídia",
}

# Cadências por tier (horas) — pactuadas com o Alvaro (6/12/24/48)
CADENCE_HOURS = {
    "muito_alto": 6,
    "alto": 12,
    "moderado": 24,
    "acompanhamento": 48,
}


def _nivel_to_tier(nivel: str) -> str:
    """Mapeia nivel CEMADEN → priority_tier operacional."""
    n = (nivel or "").lower().strip()
    return {"muito alto": "muito_alto", "alto": "alto", "moderado": "moderado"}.get(
        n, "moderado"
    )


def _alert_id_from_cod(cod_alerta: str, uf: str, opened_at: str) -> str:
    """Gera id estável do alerta para events.json/live.json.

    Formato: cemaden_<uf>_<cod_alerta>. Estável ao longo do tempo desde
    que cod_alerta seja estável (é — vem do CEMADEN direto).
    """
    return f"cemaden_{uf.lower()}_{cod_alerta}"


def _isoformat_z(dt_str: str | None) -> str | None:
    """Converte string do faa_poc para ISO 8601 UTC com sufixo Z."""
    if not dt_str:
        return None
    try:
        dt = pd.to_datetime(dt_str, utc=True)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return dt_str  # devolve como veio se não parseou


def _build_distribution(comments_df: pd.DataFrame) -> list[dict]:
    """Contagens por categoria, ordem canônica, com pct."""
    total = len(comments_df)
    dist = []
    for cat in CATEGORY_ORDER:
        col = f"pred_{cat}"
        count = int(comments_df[col].sum()) if col in comments_df.columns else 0
        pct = round(100.0 * count / total, 1) if total > 0 else 0.0
        dist.append(
            OrderedDict(
                [
                    ("key", cat),
                    ("label", CATEGORY_LABELS[cat]),
                    ("count", count),
                    ("pct", pct),
                ]
            )
        )
    return dist


def _build_timeline(comments_df: pd.DataFrame) -> list[dict]:
    """Série diária de volume. Formato date: dd/mm/yy."""
    if comments_df.empty or "published_at" not in comments_df.columns:
        return []
    dates = pd.to_datetime(comments_df["published_at"], errors="coerce", utc=True)
    counts = dates.dt.strftime("%d/%m/%y").value_counts().sort_index()
    return [
        OrderedDict([("date", d), ("count", int(c))]) for d, c in counts.items()
    ]


def _build_videos(
    comments_df: pd.DataFrame, videos_df: pd.DataFrame
) -> list[dict]:
    """Agregado por vídeo, ordenado por n_comments desc.

    Inclui vídeos linkados ao alerta mesmo sem comentários coletados
    (n_comments=0) — para bater com o campo n_videos do topo do alerta.
    """
    linked_video_ids = set(videos_df["video_id"].unique()) if not videos_df.empty else set()

    if comments_df.empty:
        # Só vídeos sem comentários
        return [
            OrderedDict(
                [
                    ("video_id", vid),
                    ("n_comments", 0),
                    ("total_likes", 0),
                    ("first_comment", ""),
                    ("top_categories", []),
                ]
            )
            for vid in linked_video_ids
        ]

    grouped = comments_df.groupby("video_id")
    videos_with_comments = set(grouped.groups.keys())

    out = []
    for vid, grp in grouped:
        # Top 3 categorias por vídeo
        cat_counts = {cat: int(grp[f"pred_{cat}"].sum()) for cat in CATEGORY_ORDER}
        top3 = sorted(
            [(SHORT_LABELS[c], n) for c, n in cat_counts.items() if n > 0],
            key=lambda x: -x[1],
        )[:3]

        first_comment = pd.to_datetime(
            grp["published_at"], errors="coerce", utc=True
        ).min()
        first_str = first_comment.strftime("%d/%m/%Y") if pd.notna(first_comment) else ""

        out.append(
            OrderedDict(
                [
                    ("video_id", vid),
                    ("n_comments", len(grp)),
                    ("total_likes", int(grp["like_count"].fillna(0).sum())),
                    ("first_comment", first_str),
                    (
                        "top_categories",
                        [
                            OrderedDict([("label", lbl), ("count", n)])
                            for lbl, n in top3
                        ],
                    ),
                ]
            )
        )

    # Adicionar vídeos linkados mas sem comentários (n_comments=0)
    for vid in linked_video_ids - videos_with_comments:
        out.append(
            OrderedDict(
                [
                    ("video_id", vid),
                    ("n_comments", 0),
                    ("total_likes", 0),
                    ("first_comment", ""),
                    ("top_categories", []),
                ]
            )
        )

    out.sort(key=lambda v: -v["n_comments"])
    return out


def _build_all_samples(
    comments_df: pd.DataFrame, top_n: int = 20
) -> dict[str, list[dict]]:
    """Top-N amostras por categoria, ordenadas por score desc."""
    if comments_df.empty:
        return {cat: [] for cat in CATEGORY_ORDER}

    out = {}
    for cat in CATEGORY_ORDER:
        score_col = f"score_{cat}"
        pred_col = f"pred_{cat}"
        if score_col not in comments_df.columns:
            out[cat] = []
            continue

        # Apenas comentários positivos para a classe
        positives = comments_df[comments_df[pred_col] == 1].nlargest(top_n, score_col)

        samples = []
        for _, row in positives.iterrows():
            text = str(row.get("text_clean") or row.get("text") or "")
            samples.append(
                OrderedDict(
                    [
                        ("text", text[:400]),
                        ("likes", int(row.get("like_count", 0) or 0)),
                        ("score", round(float(row[score_col]), 3)),
                        (
                            "date",
                            _isoformat_z(row.get("published_at", ""))[:10]
                            if row.get("published_at")
                            else "",
                        ),
                        ("video_id", row.get("video_id", "")),
                    ]
                )
            )
        out[cat] = samples
    return out


def _build_alert_entry(
    cod_alerta: str,
    alerts_df: pd.DataFrame,
    videos_df: pd.DataFrame,
    comments_df: pd.DataFrame,
    visibility_df: pd.DataFrame,
    now_iso: str,
) -> OrderedDict:
    """Monta um alerta completo no schema live.json."""
    # Metadata do alerta (última linha para pegar snapshot mais recente)
    alert_rows = alerts_df[alerts_df["cod_alerta"].astype(str) == str(cod_alerta)]
    if alert_rows.empty:
        raise ValueError(f"Alerta {cod_alerta} não encontrado em alerts_log.csv")
    alert = alert_rows.iloc[-1].to_dict()

    # Comentários deste alerta (via join com video_links seria mais correto,
    # mas para piloto assumimos que todos os comentários coletados na sessão
    # pertencem aos alertas processados naquela sessão — join fica na v2)
    if not videos_df.empty and "cod_alerta" in videos_df.columns and "video_id" in videos_df.columns:
        my_video_ids = set(
            videos_df[videos_df["cod_alerta"].astype(str) == str(cod_alerta)][
                "video_id"
            ].unique()
        )
        my_videos = videos_df[videos_df["cod_alerta"].astype(str) == str(cod_alerta)]
    else:
        my_video_ids = set()
        my_videos = pd.DataFrame(columns=["cod_alerta", "video_id"])

    if not comments_df.empty and "video_id" in comments_df.columns:
        my_comments = comments_df[comments_df["video_id"].isin(my_video_ids)].copy()
    else:
        my_comments = pd.DataFrame()

    # Collection health baseado em visibility_observations
    if not visibility_df.empty and "cod_alerta" in visibility_df.columns:
        vis_rows = visibility_df[
            visibility_df["cod_alerta"].astype(str) == str(cod_alerta)
        ]
    else:
        vis_rows = pd.DataFrame()
    if not vis_rows.empty:
        vis = vis_rows.iloc[-1]
        n_relevant = int(vis.get("n_relevant_videos", 0) or 0)
        if n_relevant == 0:
            silence_type = "no_videos_found"
            status = "silent"
        elif my_comments.empty:
            silence_type = "videos_without_comments"
            status = "silent"
        else:
            silence_type = None
            status = "ok"
    else:
        # Sem log de visibility — inferir do que temos
        if len(my_video_ids) == 0:
            silence_type = "no_videos_found"
            status = "silent"
        elif my_comments.empty:
            silence_type = "videos_without_comments"
            status = "silent"
        else:
            silence_type = None
            status = "ok"

    nivel = alert.get("nivel", "Moderado")
    tier = _nivel_to_tier(nivel)
    opened_at = _isoformat_z(alert.get("datahoracriacao"))

    # data_alerta em dd/mm/yyyy (schema do dashboard)
    if opened_at:
        _y, _m, _d = opened_at[:4], opened_at[5:7], opened_at[8:10]
        data_alerta_br = f"{_d}/{_m}/{_y}"
    else:
        data_alerta_br = ""

    # tipo: remover "- Moderado/Alto/Muito Alto" se vier concatenado do CEMADEN
    tipo_raw = alert.get("evento", "")
    tipo_clean = tipo_raw.split(" - ")[0].strip() if " - " in tipo_raw else tipo_raw

    # municipio em Title Case brasileiro (CEMADEN devolve CAPS)
    # Preposições em minúsculo, exceto se forem a primeira palavra
    _LOWERCASE = {"de", "da", "do", "das", "dos", "e"}
    raw_muni = str(alert.get("municipio", "")).lower()
    parts = raw_muni.split()
    municipio_clean = " ".join(
        p.capitalize() if (i == 0 or p not in _LOWERCASE) else p
        for i, p in enumerate(parts)
    )

    # Next collection baseado no tier
    from datetime import timedelta
    now_dt = datetime.now(timezone.utc)
    next_dt = now_dt + timedelta(hours=CADENCE_HOURS[tier])
    next_iso = next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    entry = OrderedDict(
        [
            ("id", _alert_id_from_cod(cod_alerta, alert.get("uf", ""), opened_at or "")),
            ("municipio", municipio_clean),
            ("uf", alert.get("uf", "")),
            ("tipo", tipo_clean),
            ("nivel", nivel),
            ("data_alerta", data_alerta_br),
            ("codibge", str(alert.get("codibge", ""))),
            ("lat", float(alert.get("latitude", 0)) if alert.get("latitude") else None),
            ("lon", float(alert.get("longitude", 0)) if alert.get("longitude") else None),
            ("regime", "prospective_live"),
            ("n_comments", len(my_comments)),
            ("n_videos", len(my_videos)),
            (
                "unlabeled",
                int((my_comments["n_model_labels"] == 0).sum())
                if not my_comments.empty and "n_model_labels" in my_comments.columns
                else 0,
            ),
            (
                "unlabeled_pct",
                round(
                    100.0 * (my_comments["n_model_labels"] == 0).sum() / len(my_comments),
                    1,
                )
                if not my_comments.empty and "n_model_labels" in my_comments.columns
                else 0.0,
            ),
            (
                "date_range",
                [
                    pd.to_datetime(my_comments["published_at"], errors="coerce", utc=True)
                    .min()
                    .strftime("%Y-%m-%d")
                    if not my_comments.empty
                    else "",
                    pd.to_datetime(my_comments["published_at"], errors="coerce", utc=True)
                    .max()
                    .strftime("%Y-%m-%d")
                    if not my_comments.empty
                    else "",
                ],
            ),
            ("distribution", _build_distribution(my_comments)),
            ("timeline", _build_timeline(my_comments)),
            ("videos", _build_videos(my_comments, my_videos)),
            ("all_samples", _build_all_samples(my_comments)),
            ("academic_studies", []),
            # Campos prospectivos
            ("observation_status", "active"),
            ("priority_tier", tier),
            ("alert_opened_at", opened_at),
            ("alert_closed_at", None),
            ("alert_transitions", []),
            (
                "collection_health",
                OrderedDict(
                    [
                        ("status", status),
                        ("silence_type", silence_type),
                        ("last_error", None),
                        ("consecutive_failures", 0),
                    ]
                ),
            ),
            ("last_collection_at", now_iso),
            ("next_collection_at", next_iso),
        ]
    )
    return entry


def _read_csv_or_empty(path: Path, expected_columns: list[str] | None = None) -> pd.DataFrame:
    """Lê CSV ou retorna DataFrame vazio se arquivo não existe.

    Ausência de arquivo != erro. Ocorre legitimamente quando o pipeline
    faa_poc rodou mas não encontrou dados (ex: nenhum alerta na região,
    ou silêncio total de mídia — H2 do protocolo).
    """
    if not path.exists():
        print(f"[build_live] CSV ausente (tratado como vazio): {path.name}")
        return pd.DataFrame(columns=expected_columns or [])
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        print(f"[build_live] CSV vazio (0 bytes): {path.name}")
        return pd.DataFrame(columns=expected_columns or [])


def load_previous_live(path: str | Path) -> dict | None:
    """Carrega o live.json anterior (se existir) para preservar histórico.

    Retorna None se o arquivo não existe ou está corrompido — nesse caso
    build_live_json fará o melhor esforço com apenas state + CSVs do ciclo.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[build_live] live.json anterior corrompido ({e}) — ignorando histórico")
        return None


def _refresh_alert_entry_from_state(
    prev_entry: dict,
    state_meta: dict,
    alert_id: str,
    now_iso: str,
) -> OrderedDict:
    """Atualiza um entry do live.json anterior com metadados operacionais do state.

    Preserva TODOS os campos de conteúdo coletado (n_comments, n_videos,
    distribution, timeline, videos, all_samples, date_range, unlabeled*)
    porque não houve coleta nova para este alerta neste ciclo.

    Atualiza APENAS os campos operacionais que podem ter mudado no state:
    priority_tier, observation_status, alert_closed_at, alert_transitions,
    last_collection_at, next_collection_at.

    Args:
        prev_entry: entry deste alerta no live.json anterior (fonte de conteúdo)
        state_meta: metadata deste alerta em state.active_alerts ou state.extended_window_alerts
        alert_id: id canônico do alerta (cemaden_<uf>_<cod>)
        now_iso: timestamp desta execução

    Returns:
        OrderedDict no mesmo schema de _build_alert_entry.
    """
    # observation_status inferido: se state_meta tem closed_at, está em extended_window
    is_extended = bool(state_meta.get("closed_at"))
    observation_status = "extended" if is_extended else "active"

    # Reconstroi na mesma ordem canônica de _build_alert_entry para consistência
    entry = OrderedDict()
    # Campos de identidade — do prev_entry (imutáveis por alerta)
    for k in ("id", "municipio", "uf", "tipo", "nivel", "data_alerta",
              "codibge", "lat", "lon", "regime"):
        entry[k] = prev_entry.get(k)
    # Campos de conteúdo coletado — preservados integralmente do prev_entry
    for k in ("n_comments", "n_videos", "unlabeled", "unlabeled_pct",
              "date_range", "distribution", "timeline", "videos",
              "all_samples", "academic_studies"):
        entry[k] = prev_entry.get(k)
    # Campos operacionais — refletem estado ATUAL do state
    entry["observation_status"] = observation_status
    entry["priority_tier"] = state_meta.get("priority_tier",
                                            prev_entry.get("priority_tier", "moderado"))
    entry["alert_opened_at"] = state_meta.get("opened_at",
                                              prev_entry.get("alert_opened_at"))
    entry["alert_closed_at"] = state_meta.get("closed_at")
    entry["alert_transitions"] = state_meta.get("transitions",
                                                prev_entry.get("alert_transitions", []))
    # collection_health: preserva do prev_entry (é resultado da última coleta real,
    # não muda em ciclos sem coleta)
    entry["collection_health"] = prev_entry.get("collection_health", OrderedDict([
        ("status", "unknown"), ("silence_type", None),
        ("last_error", None), ("consecutive_failures", 0),
    ]))
    # Timestamps de coleta vêm do state (canônico), não do prev_entry
    entry["last_collection_at"] = state_meta.get("last_collection_at",
                                                 prev_entry.get("last_collection_at"))
    entry["next_collection_at"] = state_meta.get("next_collection_at",
                                                 prev_entry.get("next_collection_at"))
    return entry


def build_live_json(
    output_dir: str | Path,
    predictions_df: pd.DataFrame,
    pilot_mode: bool = True,
    dry_run: bool = False,
    pipeline_version: str = "0.1.0",
    state: dict | None = None,
    previous_live: dict | None = None,
) -> dict:
    """Monta o live.json completo.

    Fonte-de-verdade dos alertas: `state` (parâmetro). Fonte de conteúdo:
    CSVs do ciclo em `output_dir` (para alertas coletados agora) OU
    `previous_live` (para alertas em state mas sem coleta neste ciclo).

    Args:
        output_dir: pasta onde o faa_poc gravou os CSVs do ciclo (pode não existir
            ou estar vazia se este run não coletou nada)
        predictions_df: DataFrame retornado por bertimbau.predict_comments() no ciclo
        pilot_mode: True enquanto CEP não aprovado
        dry_run: True quando alertas são replicados de histórico
        pipeline_version: versão do pipeline
        state: state.json atual (dict com active_alerts + extended_window_alerts).
            Se None, cai no comportamento legado (só CSVs do ciclo, para
            retrocompatibilidade em testes/notebooks).
        previous_live: conteúdo do live.json anterior (dict), usado para preservar
            histórico de alertas que estão no state mas não foram coletados
            neste ciclo. Se None, alertas sem CSV e sem entry anterior aparecem
            como entry mínimo (só metadados do state).

    Returns:
        Dict serializável do live.json.
    """
    output_dir = Path(output_dir)

    alerts_df = _read_csv_or_empty(
        output_dir / "alerts_log.csv",
        expected_columns=["cod_alerta", "codibge", "municipio", "uf", "nivel",
                          "evento", "datahoracriacao", "latitude", "longitude"],
    )
    videos_df = _read_csv_or_empty(
        output_dir / "youtube_alert_video_links.csv",
        expected_columns=["cod_alerta", "video_id"],
    )
    visibility_df = _read_csv_or_empty(
        output_dir / "visibility_observations.csv",
        expected_columns=["cod_alerta", "n_relevant_videos"],
    )

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ================================================================
    # Comportamento LEGADO (state=None): só CSVs do ciclo.
    # Usado por notebooks/testes que não passam state.
    # ================================================================
    if state is None:
        if alerts_df.empty:
            print("[build_live] alerts_log.csv vazio e state=None — retornando alerts=[]")
            return OrderedDict([
                ("generated_at", now_iso),
                ("pipeline_version", pipeline_version),
                ("pilot_mode", pilot_mode),
                ("dry_run", dry_run),
                ("alerts", []),
            ])
        active_cods = alerts_df["cod_alerta"].astype(str).unique().tolist()
        alerts = []
        for cod in active_cods:
            try:
                entry = _build_alert_entry(
                    cod, alerts_df, videos_df, predictions_df, visibility_df, now_iso
                )
                alerts.append(entry)
            except Exception as e:
                print(f"[build_live] pulando alerta {cod}: {e}")
        return OrderedDict([
            ("generated_at", now_iso),
            ("pipeline_version", pipeline_version),
            ("pilot_mode", pilot_mode),
            ("dry_run", dry_run),
            ("alerts", alerts),
        ])

    # ================================================================
    # Comportamento NOVO (state passado): state é fonte-de-verdade.
    # ================================================================
    # cods que foram efetivamente coletados neste ciclo (têm CSV)
    if not alerts_df.empty:
        collected_cods = set(alerts_df["cod_alerta"].astype(str).unique())
    else:
        collected_cods = set()

    # Índice do live anterior por alert_id, para preservar histórico
    prev_by_id = {}
    if previous_live and isinstance(previous_live.get("alerts"), list):
        for a in previous_live["alerts"]:
            if a.get("id"):
                prev_by_id[a["id"]] = a

    # União dos alertas no state (active + extended)
    # Ordem: active primeiro (mais recentes/importantes), extended depois
    state_alerts = OrderedDict()
    for aid, meta in state.get("active_alerts", {}).items():
        state_alerts[aid] = meta
    for aid, meta in state.get("extended_window_alerts", {}).items():
        state_alerts[aid] = meta

    alerts = []
    stats = {"from_csv": 0, "from_history": 0, "skipped_no_data": 0}

    for alert_id, meta in state_alerts.items():
        # cod_alerta é a parte após o último "_"
        cod = alert_id.rsplit("_", 1)[-1]

        if cod in collected_cods:
            # Path A: alerta coletado neste ciclo — monta entry completo dos CSVs
            try:
                entry = _build_alert_entry(
                    cod, alerts_df, videos_df, predictions_df, visibility_df, now_iso
                )
                # Sobrescreve id/status com valores do state (canônico) —
                # _build_alert_entry usa dados do CSV que podem estar defasados
                entry["id"] = alert_id
                entry["priority_tier"] = meta.get("priority_tier", entry["priority_tier"])
                if meta.get("closed_at"):
                    entry["observation_status"] = "extended"
                    entry["alert_closed_at"] = meta["closed_at"]
                entry["alert_transitions"] = meta.get("transitions",
                                                     entry.get("alert_transitions", []))
                entry["last_collection_at"] = meta.get("last_collection_at",
                                                      entry.get("last_collection_at"))
                entry["next_collection_at"] = meta.get("next_collection_at",
                                                      entry.get("next_collection_at"))
                alerts.append(entry)
                stats["from_csv"] += 1
            except Exception as e:
                print(f"[build_live] falha ao montar alerta {alert_id} do CSV: {e}")
                # Fallback: se tem no histórico, usa ele
                if alert_id in prev_by_id:
                    alerts.append(_refresh_alert_entry_from_state(
                        prev_by_id[alert_id], meta, alert_id, now_iso
                    ))
                    stats["from_history"] += 1
                else:
                    stats["skipped_no_data"] += 1
        elif alert_id in prev_by_id:
            # Path B: sem coleta neste ciclo, mas existe entry anterior — preserva histórico
            alerts.append(_refresh_alert_entry_from_state(
                prev_by_id[alert_id], meta, alert_id, now_iso
            ))
            stats["from_history"] += 1
        else:
            # Path C: alerta no state mas sem CSV e sem histórico — não podemos
            # construir entry rico (falta lat/lon, tipo, etc). Skip silencioso;
            # aparecerá no próximo ciclo com coleta.
            stats["skipped_no_data"] += 1

    print(f"[build_live] alertas montados: {stats['from_csv']} do CSV, "
          f"{stats['from_history']} do histórico, {stats['skipped_no_data']} pulados "
          f"(sem CSV nem histórico)")

    live = OrderedDict(
        [
            ("generated_at", now_iso),
            ("pipeline_version", pipeline_version),
            ("pilot_mode", pilot_mode),
            ("dry_run", dry_run),
            ("alerts", alerts),
        ]
    )
    return live


def build_state_json(
    live_data: dict,
    quota_used: int = 0,
    last_run_duration_seconds: int = 0,
    pipeline_version: str = "0.1.0",
) -> dict:
    """Monta state.json a partir do live.json.

    Piloto: extended_window_alerts fica vazio (não estamos processando
    janela de 365 dias no piloto). Produção: será populado quando alertas
    fecharem e transitarem para acompanhamento.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    active = OrderedDict()

    for alert in live_data.get("alerts", []):
        active[alert["id"]] = OrderedDict(
            [
                ("codibge", alert["codibge"]),
                ("municipio", alert["municipio"]),
                ("uf", alert["uf"]),
                ("nivel_atual", alert["nivel"]),
                ("priority_tier", alert["priority_tier"]),
                ("opened_at", alert["alert_opened_at"]),
                ("last_seen_open_at", now_iso),
                ("transitions", alert.get("alert_transitions", [])),
                (
                    "videos_collected",
                    [v["video_id"] for v in alert.get("videos", [])],
                ),
                ("last_collection_at", alert["last_collection_at"]),
                ("next_collection_at", alert["next_collection_at"]),
            ]
        )

    # Próximo reset da cota YouTube é 00h Pacific = 07/08h UTC
    from datetime import timedelta
    now_dt = datetime.now(timezone.utc)
    pacific_midnight = (now_dt + timedelta(days=1)).replace(
        hour=7, minute=0, second=0, microsecond=0
    )
    reset_iso = pacific_midnight.strftime("%Y-%m-%dT%H:%M:%SZ")

    state = OrderedDict(
        [
            ("pipeline_version", pipeline_version),
            ("last_run_at", now_iso),
            ("last_run_status", "success"),
            ("last_run_duration_seconds", last_run_duration_seconds),
            (
                "youtube_quota",
                OrderedDict(
                    [("used_today", quota_used), ("reset_at", reset_iso)]
                ),
            ),
            ("active_alerts", active),
            ("extended_window_alerts", OrderedDict()),
        ]
    )
    return state


def save_json(data: dict, path: str | Path) -> None:
    """Salva dict como JSON com ensure_ascii=False e indent=2."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[build_live] salvo: {path} ({path.stat().st_size} bytes)")
