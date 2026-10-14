"""Geometria das áreas CAP → GeoJSON simplificado para o painel.

CAP 1.2: ``<polygon>`` é uma lista de pares "lat,lon" separados por espaço, com o
primeiro ponto repetido no fim; ``<circle>`` é "lat,lon raio_km". O GeoJSON usa
[lon, lat]. A geometria original (precisão total) fica no arquivo bruto; aqui sai
uma versão para exibição: união das partes, simplificação e arredondamento.
"""
from __future__ import annotations

import math

from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

SIMPLIFY_TOL = 0.003     # graus (~300 m): suficiente para escala municipal no mapa
COORD_DECIMALS = 4       # ~11 m


def parse_polygon(text: str) -> tuple[Polygon | None, bool]:
    """"lat,lon lat,lon …" → (Polygon, foi_fechado). None se tiver menos de 3 pontos válidos."""
    pts = []
    for pair in (text or "").split():
        try:
            lat, lon = (float(x) for x in pair.split(",")[:2])
        except ValueError:
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            pts.append((lon, lat))
    if len(pts) < 3:
        return None, False
    fechado = pts[0] != pts[-1]
    if fechado:
        pts.append(pts[0])
    if len(pts) < 4:
        return None, fechado
    return Polygon(pts), fechado


def parse_circle(text: str):
    """"lat,lon raio_km" → polígono aproximado (raio convertido em graus na latitude)."""
    try:
        center, radius = text.split()
        lat, lon = (float(x) for x in center.split(","))
        r_km = float(radius)
    except ValueError:
        return None
    if r_km <= 0:
        return None
    dlat = r_km / 111.32
    dlon = r_km / (111.32 * max(math.cos(math.radians(lat)), 0.01))
    return Polygon([(lon + dlon * math.cos(a), lat + dlat * math.sin(a))
                    for a in (2 * math.pi * i / 64 for i in range(65))])


def _round(geom, nd: int):
    def r(coords):
        return [[round(x, nd), round(y, nd)] for x, y in coords]
    g = mapping(geom)
    if g["type"] == "Polygon":
        g["coordinates"] = [r(ring) for ring in g["coordinates"]]
    elif g["type"] == "MultiPolygon":
        g["coordinates"] = [[r(ring) for ring in poly] for poly in g["coordinates"]]
    return g


def _polygons_only(geom):
    if geom.is_empty:
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
    return unary_union(parts) if parts else None


def area_geometry(areas: list[dict], *, tol: float = SIMPLIFY_TOL, nd: int = COORD_DECIMALS) -> tuple[dict | None, dict]:
    """Áreas CAP de um alerta → (geometria GeoJSON simplificada ou None, controle de qualidade)."""
    parts, n_fechados, n_invalidos = [], 0, 0
    for a in areas:
        for text in a.get("polygons", []):
            poly, fechado = parse_polygon(text)
            n_fechados += int(fechado)
            if poly is None:
                n_invalidos += 1
                continue
            if not poly.is_valid:
                n_invalidos += 1
                poly = make_valid(poly)
            parts.append(poly)
        for text in a.get("circles", []):
            c = parse_circle(text)
            if c is not None:
                parts.append(c)
    qa = {"poligonos_fechados_pelo_coletor": n_fechados, "poligonos_invalidos_corrigidos": n_invalidos}
    if not parts:
        return None, {**qa, "sem_geometria": True}
    union = _polygons_only(unary_union(parts))
    if union is None:
        return None, {**qa, "sem_geometria": True}
    # tolerância adaptativa: áreas estaduais (centenas de milhares de km²) não precisam do
    # detalhe de 300 m; o detalhe fica proporcional à extensão (≈ 1/400 do lado equivalente)
    tol = max(tol, math.sqrt(union.area) / 400)
    simple = union.simplify(tol, preserve_topology=True)
    simple = _polygons_only(simple) or union
    minx, miny, maxx, maxy = union.bounds
    rep = union.representative_point()
    qa.update({
        "sem_geometria": False,
        "bbox": [round(minx, nd), round(miny, nd), round(maxx, nd), round(maxy, nd)],
        "ponto": [round(rep.x, nd), round(rep.y, nd)],
        # área em km² aproximada (projeção equiretangular local); serve para ordenar e filtrar
        "tolerancia_graus": round(tol, 5),
        "area_km2": round(union.area * 111.32 ** 2 * math.cos(math.radians((miny + maxy) / 2)), 1),
    })
    return _round(simple, nd), qa
