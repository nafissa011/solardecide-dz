import time
from flask import Blueprint, jsonify, request

bp = Blueprint("misc", __name__)

# ── Offline packs ─────────────────────────────────────────────────────────────

_OFFLINE_PACKS = [
    {
        "id": "pack_south",
        "name": "Algérie du Sud",
        "description": "Données complètes pour les wilayas sahariennes (Tamanrasset, Adrar, Illizi…)",
        "size_mb": 48,
        "wilayas": 12,
        "last_updated": "2025-01-15",
        "status": "available",
    },
    {
        "id": "pack_north",
        "name": "Algérie du Nord",
        "description": "Wilayas côtières et hauts plateaux (Alger, Oran, Constantine…)",
        "size_mb": 35,
        "wilayas": 20,
        "last_updated": "2025-01-15",
        "status": "available",
    },
    {
        "id": "pack_models",
        "name": "Modèles IA embarqués",
        "description": "Checkpoints PatchTST + VMD-PatchTST pour inférence hors-ligne",
        "size_mb": 120,
        "wilayas": 0,
        "last_updated": "2025-01-10",
        "status": "available",
    },
]


@bp.get("/offline/packs")
def get_offline_packs():
    return jsonify({"data": _OFFLINE_PACKS, "status": 200})


@bp.post("/offline/packs/<pack_id>/download")
def download_pack(pack_id):
    pack = next((p for p in _OFFLINE_PACKS if p["id"] == pack_id), None)
    if not pack:
        return jsonify({"error": "Pack introuvable", "status": 404}), 404
    return jsonify({
        "data": {**pack, "status": "downloaded", "downloaded_at": time.strftime("%Y-%m-%d")},
        "status": 200,
    })


# ── Data sources ──────────────────────────────────────────────────────────────

_DATA_SOURCES = [
    {
        "id": "nasa_power",
        "name": "NASA POWER API",
        "description": "Données radiométriques satellitaires GHI/DNI/DHI sur 0.5°×0.5°. Résolution horaire 2019–2025.",
        "coverage": "Algérie complète (48 wilayas + communes)",
        "period": "2019–2025",
        "variables": ["GHI", "DNI", "DHI", "CLEARNESS_KT"],
        "resolution": "Horaire",
        "reliability": 0.94,
        "url": "https://power.larc.nasa.gov",
    },
    {
        "id": "rp5",
        "name": "rp5.ru Stations Météo",
        "description": "Observations au sol issues de stations synoptiques algériennes.",
        "coverage": "48 stations (chefs-lieux de wilaya)",
        "period": "2019–2025",
        "variables": ["T2M", "WS10M", "RH2M"],
        "resolution": "3-horaire",
        "reliability": 0.88,
        "url": "https://rp5.ru",
    },
    {
        "id": "sonelgaz",
        "name": "Sonelgaz — Demande électrique",
        "description": "Données de consommation électrique par wilaya.",
        "coverage": "48 wilayas",
        "period": "2019–2023",
        "variables": ["demand_mw"],
        "resolution": "Horaire (interpolé)",
        "reliability": 0.82,
        "url": "https://www.sonelgaz.dz",
    },
]


@bp.get("/data-sources")
def get_data_sources():
    return jsonify({"data": _DATA_SOURCES, "total": len(_DATA_SOURCES), "status": 200})