"""Inferência BERTimbau para o ODRD.

Camada isolada do pipeline frozen `faa_poc/`. Lê comentários do CSV canonical
produzido pelo pipeline, chama o checkpoint fine-tuned hospedado no HuggingFace
e devolve um DataFrame com scores + predições binárias por classe.

Uso típico (dentro do notebook Colab):

    from odrd_bridge.bertimbau import predict_comments
    df_pred = predict_comments(
        comments_csv='/content/faa_poc_full_test/youtube_comments_canonical.csv',
        model_repo='alvarocoutinho/bertimbau-weaklabels-odrd',
        hf_token=os.environ['HF_TOKEN'],
        batch_size=32,
    )

Convenções mantidas do dashboard:
- Ordem canônica das 8 classes (do userMemories) preservada
- Threshold default = 0.5 por classe (mesmo default do dashboard v0.1;
  validation_thresholds.csv fica como pendência conhecida)
- Sem GPU: BERT-base roda tranquilo em CPU do Colab para volumes de piloto
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Ordem canônica das 8 classes ODRD — não mudar sem coordenar dashboard
CATEGORY_ORDER = [
    "solidariedade_oracao_luto",
    "ajuda_resgate_doacoes",
    "responsabilizacao_governanca",
    "infraestrutura_ocupacao_risco",
    "clima_chuva_meio_ambiente",
    "experiencia_pessoal_local",
    "alerta_prevencao_cobranca",
    "critica_midia_informacao",
]

# Thresholds default — v0.1 usa 0.5 uniforme; ideal era ler
# validation_thresholds.csv, mas ele não foi localizado (pendência do wrapup)
DEFAULT_THRESHOLDS = {cat: 0.5 for cat in CATEGORY_ORDER}


def load_model(model_repo: str, hf_token: str | None = None, subfolder: str = "best_model"):
    """Baixa e carrega o checkpoint do HuggingFace Hub.

    Retorna (model, tokenizer) prontos para inferência em CPU.
    Não move para GPU intencionalmente: piloto roda em CPU, produção idem.

    Args:
        model_repo: id do repo HF (ex: 'alvarocoutinho/bertimbau-weaklabels-odrd')
        hf_token: token de acesso (opcional se repo público)
        subfolder: subpasta dentro do repo onde estão os arquivos do checkpoint.
            Default 'best_model' porque é a convenção do HuggingFace Trainer.
            Passe '' (string vazia) se os arquivos estiverem na raiz do repo.
    """
    kwargs = {"token": hf_token} if hf_token else {}
    if subfolder:
        kwargs["subfolder"] = subfolder
    tokenizer = AutoTokenizer.from_pretrained(model_repo, **kwargs)
    model = AutoModelForSequenceClassification.from_pretrained(model_repo, **kwargs)
    model.eval()
    return model, tokenizer


def _batch_predict(
    texts: list[str],
    model,
    tokenizer,
    batch_size: int = 32,
    max_length: int = 256,
) -> np.ndarray:
    """Roda inferência batch. Retorna matriz (n_textos, 8) de scores sigmoide."""
    all_scores = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            enc = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            logits = model(**enc).logits
            scores = torch.sigmoid(logits).cpu().numpy()
            all_scores.append(scores)
    return np.vstack(all_scores)


def predict_comments(
    comments_csv: str | Path,
    model_repo: str = "alvarocoutinho/bertimbau-weaklabels-odrd",
    hf_token: str | None = None,
    subfolder: str = "best_model",
    batch_size: int = 32,
    thresholds: dict[str, float] | None = None,
    text_column: str = "text_clean",
) -> pd.DataFrame:
    """Pipeline completo de inferência.

    Lê CSV de comentários canonical do faa_poc, roda BERTimbau, devolve
    DataFrame com colunas originais + score_<classe> + pred_<classe>.

    Args:
        comments_csv: caminho para youtube_comments_canonical.csv
        model_repo: id do repo HF (default: alvarocoutinho/bertimbau-weaklabels-odrd)
        hf_token: token HF; se None, tenta os.environ['HF_TOKEN']
        subfolder: subpasta do repo com arquivos do checkpoint (default 'best_model')
        batch_size: tamanho do batch; 32 é seguro para CPU do Colab
        thresholds: dict {classe: threshold}; default = 0.5 uniforme
        text_column: coluna de texto no CSV; default 'text_clean'

    Returns:
        DataFrame com todas as colunas originais + score_/pred_ por classe +
        n_model_labels (int) + model_labels (str CSV das classes positivas)
    """
    df = pd.read_csv(comments_csv)
    if df.empty:
        print(f"[bertimbau] CSV vazio: {comments_csv}")
        return df

    if text_column not in df.columns:
        raise ValueError(
            f"Coluna '{text_column}' não encontrada. "
            f"Colunas disponíveis: {list(df.columns)}"
        )

    # Trata NaN/vazios como string vazia — modelo prediz baixo, não quebra
    texts = df[text_column].fillna("").astype(str).tolist()

    if hf_token is None:
        hf_token = os.environ.get("HF_TOKEN")

    print(f"[bertimbau] carregando {model_repo} (subfolder='{subfolder}')...")
    model, tokenizer = load_model(model_repo, hf_token=hf_token, subfolder=subfolder)

    print(f"[bertimbau] inferindo {len(texts)} comentários (batch={batch_size}, CPU)...")
    scores = _batch_predict(texts, model, tokenizer, batch_size=batch_size)
    print(f"[bertimbau] inferência ok — shape {scores.shape}")

    thr = thresholds or DEFAULT_THRESHOLDS

    # Adiciona colunas score_ e pred_ por classe, ordem canônica
    for i, cat in enumerate(CATEGORY_ORDER):
        df[f"score_{cat}"] = scores[:, i]
        df[f"pred_{cat}"] = (scores[:, i] >= thr[cat]).astype(int)

    # Contadores auxiliares
    pred_cols = [f"pred_{cat}" for cat in CATEGORY_ORDER]
    df["n_model_labels"] = df[pred_cols].sum(axis=1)
    df["model_labels"] = df[pred_cols].apply(
        lambda row: ",".join(
            cat for cat, val in zip(CATEGORY_ORDER, row) if val == 1
        ),
        axis=1,
    )

    return df


if __name__ == "__main__":
    # Uso via linha de comando: python -m odrd_bridge.bertimbau <csv_path>
    import sys

    if len(sys.argv) < 2:
        print("uso: python -m odrd_bridge.bertimbau <youtube_comments_canonical.csv>")
        sys.exit(1)
    out = predict_comments(sys.argv[1])
    out_path = Path(sys.argv[1]).with_name("predictions.csv")
    out.to_csv(out_path, index=False)
    print(f"salvo em {out_path}")
