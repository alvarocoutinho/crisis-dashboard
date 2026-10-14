"""Backup mensal: listagem paginada, manifesto e apagamento só do que está no manifesto."""
import csv
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import backup_artifacts as b  # noqa: E402


class FakeResp:
    def __init__(self, status=200, json=None, content=b""):
        self.status_code, self._json, self.content = status, json, content

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def __init__(self, arts):
        self.arts, self.deleted, self.headers = arts, [], {}

    def get(self, url, params=None, timeout=None):
        if url.endswith("/actions/artifacts"):
            page = params["page"]
            return FakeResp(json={"artifacts": self.arts[(page - 1) * 100: page * 100]})
        return FakeResp(content=url.encode())        # "download" = a própria URL

    def delete(self, url, timeout=None):
        self.deleted.append(url.rsplit("/", 1)[-1])
        return FakeResp(status=204)


def _art(i, name="pipeline-crus-", expired=False):
    return {"id": i, "name": f"{name}{i}", "expired": expired, "created_at": f"2026-09-{1 + i % 28:02d}T00:00:00Z",
            "expires_at": "2026-12-01T00:00:00Z", "archive_download_url": f"https://x/{i}/zip",
            "workflow_run": {"id": 1000 + i}}


def test_baixa_paginado_filtra_e_grava_manifesto(tmp_path, monkeypatch):
    arts = [_art(i) for i in range(150)] + [_art(999, expired=True), _art(500, name="odrd-backup-")]
    fake = FakeSession(arts)
    monkeypatch.setattr(b, "_sessao", lambda: (fake, "o/r"))
    man = tmp_path / "m.csv"
    assert b.baixar(SimpleNamespace(saida=tmp_path / "out", manifesto=man, prefixo="pipeline-crus-")) == 0
    rows = list(csv.DictReader(man.open(encoding="utf-8")))
    assert len(rows) == 150                                   # sem o expirado nem o próprio backup
    assert len(list((tmp_path / "out").glob("*.zip"))) == 150
    assert all(len(r["sha256"]) == 64 for r in rows)


def test_apagar_exige_confirmacao_e_usa_so_o_manifesto(tmp_path, monkeypatch):
    fake = FakeSession([])
    monkeypatch.setattr(b, "_sessao", lambda: (fake, "o/r"))
    man = tmp_path / "m.csv"
    with man.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=b.CAMPOS)
        w.writeheader()
        w.writerows([{"nome": "a", "id": "11"}, {"nome": "b", "id": "12"}])
    try:
        b.apagar(SimpleNamespace(manifesto=man, confirmar="sim"))
        assert False, "deveria recusar sem APAGAR"
    except SystemExit:
        pass
    assert fake.deleted == []
    b.apagar(SimpleNamespace(manifesto=man, confirmar="APAGAR"))
    assert fake.deleted == ["11", "12"]
