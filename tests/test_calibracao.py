"""Alfa de Krippendorff do script de análise da calibração.

    python -m pytest tests/        ou        python tests/test_calibracao.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from analyze_annotation import alfa_nominal, prec_rec  # noqa: E402


def test_exemplo_canonico_krippendorff():
    # Krippendorff (2011), "Computing Krippendorff's alpha-reliability": 4 codificadores,
    # 12 unidades, dados faltantes; alfa nominal = 0,743
    A = [1, 2, 3, 3, 2, 1, 4, 1, 2, None, None, None]
    B = [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, None, 3]
    C = [None, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, None]
    D = [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, None]
    unidades = [[str(v) for v in col if v is not None] for col in zip(A, B, C, D)]
    assert round(alfa_nominal(unidades), 3) == 0.743


def test_exemplo_do_texto_80_por_cento_de_acordo():
    unidades = [["sim", "sim"]] * 5 + [["nao", "nao"]] * 3 + [["sim", "nao"]] * 2
    assert round(alfa_nominal(unidades), 3) == 0.604


def test_acordo_perfeito_e_ponderacao():
    assert alfa_nominal([["a", "a"], ["b", "b"]]) == 1.0
    pr, rc, _ = prec_rec([(1, 1, 2.0), (1, 0, 1.0), (0, 1, 1.0)])
    assert round(pr, 3) == 0.667 and round(rc, 3) == 0.667


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
