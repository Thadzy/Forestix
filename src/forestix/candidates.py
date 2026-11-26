"""Candidate plot point generation using public Earth Engine layers."""

import json
from pathlib import Path
from typing import Any

import ee

_POOL_NAMES = {
    "1": "LOSS_POST2020",
    "2": "G2_EXISTING_CROPLAND",
    "4": "G4_INTACT_FOREST",
}


def district_geometry(
    districts: list[str],
    asset_id: str = "FAO/GAUL/2015/level2",
) -> ee.Geometry:
    """Return the combined Earth Engine geometry for Nan Province districts.

    Serves: DS-2.

    Args:
        districts: List of ``ADM2_NAME`` district names in Nan Province (e.g., ``["Mae Charim", "Pua"]``).
        asset_id: Earth Engine FeatureCollection asset ID for level-2 administrative boundaries.

    Returns:
        Dissolved ``ee.Geometry`` covering all requested districts.

    Raises:
        ValueError: If ``districts`` is empty or any requested name matches no GAUL feature in Nan.
    """
    if not districts:
        raise ValueError("districts must be a non-empty list of district names.")

    gaul = (
        ee.FeatureCollection(asset_id)
        .filter(ee.Filter.eq("ADM1_NAME", "Nan"))
        .filter(ee.Filter.inList("ADM2_NAME", districts))
    )
    matched = set(gaul.aggregate_array("ADM2_NAME").getInfo())
    missing = [d for d in districts if d not in matched]
    if missing:
        raise ValueError(
            f"District(s) not found in Nan Province ({asset_id}): {missing}"
        )
    return gaul.geometry()


def build_pool_image(ds: dict[str, Any], cfg: dict[str, Any]) -> ee.Image:
    """Build a multi-band Earth Engine image classifying pixels into DS-2 sampling pools.

    Pool precedence when a pixel satisfies more than one pool:
    ``LOSS_POST2020`` (1) wins over ``G2_EXISTING_CROPLAND`` (2), which wins over
    ``G4_INTACT_FOREST`` (4). Pixels matching none of the pools are masked.

    Serves: DS-2.

    Args:
        ds: Dataset asset IDs dictionary loaded from ``configs/datasets.yaml``.
        cfg: Candidate-seed configuration dictionary loaded from ``configs/candidates_v1.yaml``.

    Returns:
        ``ee.Image`` with integer band ``"pool"`` (1, 2, 4; masked elsewhere) and attribute bands
        ``"lossyear"``, ``"treecover2000"``, ``"jrc_forest2020"``, ``"wc2020"``, ``"wc2021"``,
        ``"radd_alert"``, and ``"radd_date"``.
    """
    min_tc = int(cfg["min_treecover2000_pct"])
    loss_start, loss_end = (int(y) for y in cfg["loss_years"])
    g4_no_loss_since = int(cfg["g4_no_loss_since"])
    radd_min_date = int(cfg["radd_min_date_yydoy"])

    hansen = ee.Image(ds["hansen_gfc"])
    lossyear = hansen.select("lossyear").unmask(0).toInt16().rename("lossyear")
    treecover2000 = (
        hansen.select("treecover2000").unmask(0).toInt16().rename("treecover2000")
    )

    jrc_forest2020 = (
        ee.Image(ds["jrc_gfc_2020"])
        .select("Map")
        .unmask(0)
        .eq(1)
        .toInt8()
        .rename("jrc_forest2020")
    )

    wc2020 = (
        ee.ImageCollection(ds["esa_worldcover_2020"])
        .first()
        .select("Map")
        .unmask(0)
        .toInt16()
        .rename("wc2020")
    )
    wc2021 = (
        ee.ImageCollection(ds["esa_worldcover_2021"])
        .first()
        .select("Map")
        .unmask(0)
        .toInt16()
        .rename("wc2021")
    )

    radd_img = (
        ee.ImageCollection(ds["radd"])
        .filter(ee.Filter.eq("layer", "alerts"))
        .filter(ee.Filter.eq("geography", "asia"))
        .mosaic()
        .unmask(0)
    )
    radd_alert = radd_img.select("Alert").toInt16().rename("radd_alert")
    radd_date = radd_img.select("Date").toInt32().rename("radd_date")

    hansen_loss_post2020 = lossyear.gte(loss_start).And(lossyear.lte(loss_end))
    radd_after_cutoff = radd_alert.gte(2).And(radd_date.gte(radd_min_date))

    # LOSS_POST2020 does not use JRC (kept only as an attribute for human VHR split of G1 vs G3).
    loss_mask = hansen_loss_post2020.Or(radd_after_cutoff).And(
        treecover2000.gte(min_tc)
    )
    g2_mask = (
        wc2020.eq(40)
        .And(jrc_forest2020.eq(0))
        .And(hansen_loss_post2020.Not())
        .And(radd_after_cutoff.Not())
    )
    g4_mask = (
        jrc_forest2020.eq(1)
        .And(wc2020.eq(10))
        .And(wc2021.eq(10))
        .And(lossyear.gte(g4_no_loss_since).Not())
        .And(radd_after_cutoff.Not())
    )

    # Apply precedence in reverse order so LOSS_POST2020 > G2 > G4.
    pool = (
        ee.Image(0)
        .where(g4_mask, 4)
        .where(g2_mask, 2)
        .where(loss_mask, 1)
        .toInt8()
        .rename("pool")
    )
    pool = pool.updateMask(pool.gt(0))

    return ee.Image.cat(
        [
            pool,
            lossyear,
            treecover2000,
            jrc_forest2020,
            wc2020,
            wc2021,
            radd_alert,
            radd_date,
        ]
    )


def candidate_points(
    districts: list[str],
    ds: dict[str, Any],
    cfg: dict[str, Any],
) -> ee.FeatureCollection:
    """Stratified-sample candidate seed points per district across the three DS-2 pools.

    Serves: DS-2.

    Args:
        districts: List of Nan Province district names to sample (e.g., training districts).
        ds: Dataset asset IDs dictionary loaded from ``configs/datasets.yaml``.
        cfg: Candidate-seed configuration dictionary loaded from ``configs/candidates_v1.yaml``.

    Returns:
        ``ee.FeatureCollection`` of candidate points with ``district``, ``pool``, ``pool_name``,
        ``seed_source``, and attribute bands.
    """
    if not districts:
        raise ValueError("districts must be a non-empty list of district names.")

    n_districts = len(districts)
    pools_cfg = cfg["pools"]
    class_values = [1, 2, 4]
    class_points = [
        int(pools_cfg["LOSS_POST2020"]["n_points"]) // n_districts,
        int(pools_cfg["G2_EXISTING_CROPLAND"]["n_points"]) // n_districts,
        int(pools_cfg["G4_INTACT_FOREST"]["n_points"]) // n_districts,
    ]
    scale_m = int(cfg["scale_m"])
    seed = int(cfg["seed"])
    loss_start, loss_end = (int(y) for y in cfg["loss_years"])
    radd_min_date = int(cfg["radd_min_date_yydoy"])

    image = build_pool_image(ds, cfg)
    admin_asset = ds.get("admin_boundaries", "FAO/GAUL/2015/level2")
    pool_names_ee = ee.Dictionary(_POOL_NAMES)

    def _annotate_feature(feat: ee.Feature) -> ee.Feature:
        pool_num = ee.Number(feat.get("pool")).int()
        pool_name = pool_names_ee.get(pool_num.format("%d"))
        ly = ee.Number(feat.get("lossyear"))
        ra = ee.Number(feat.get("radd_alert"))
        rd = ee.Number(feat.get("radd_date"))
        hansen_ok = ly.gte(loss_start).And(ly.lte(loss_end))
        radd_ok = ra.gte(2).And(rd.gte(radd_min_date))
        loss_source = ee.Algorithms.If(
            hansen_ok.And(radd_ok),
            "both",
            ee.Algorithms.If(
                hansen_ok,
                "hansen",
                ee.Algorithms.If(radd_ok, "radd", "none"),
            ),
        )
        seed_source = ee.Algorithms.If(pool_num.eq(1), loss_source, "none")
        return feat.set({"pool_name": pool_name, "seed_source": seed_source})

    per_district_fcs: list[ee.FeatureCollection] = []
    for district in districts:
        geom = district_geometry([district], asset_id=admin_asset)
        sampled = image.stratifiedSample(
            numPoints=0,
            classBand="pool",
            classValues=class_values,
            classPoints=class_points,
            region=geom,
            scale=scale_m,
            seed=seed,
            geometries=True,
            dropNulls=True,
            tileScale=4,
        )
        sampled = sampled.map(
            lambda feat, d=district: _annotate_feature(feat).set("district", d)
        )
        per_district_fcs.append(sampled)

    return ee.FeatureCollection(per_district_fcs).flatten()


def to_geojson(fc: ee.FeatureCollection, path: str | Path) -> int:
    """Download a candidate FeatureCollection, write EPSG:4326 GeoJSON, and print count summary.

    Serves: DS-2.

    Args:
        fc: Small ``ee.FeatureCollection`` of candidate points.
        path: Output ``.geojson`` file path.

    Returns:
        Number of features written.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fc_dict = fc.getInfo()
    features = fc_dict.get("features", [])
    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)

    counts: dict[tuple[str, str], int] = {}
    pools: set[str] = set()
    districts: set[str] = set()
    for feat in features:
        props = feat.get("properties", {})
        pool_name = str(props.get("pool_name", "UNKNOWN"))
        district = str(props.get("district", "UNKNOWN"))
        pools.add(pool_name)
        districts.add(district)
        counts[(pool_name, district)] = counts.get((pool_name, district), 0) + 1

    sorted_pools = sorted(pools)
    sorted_districts = sorted(districts)
    if sorted_pools and sorted_districts:
        col_w = max(len(d) for d in sorted_districts + ["Total"]) + 2
        pool_w = max(len(p) for p in sorted_pools + ["Pool"]) + 2
        header = f"{'Pool':<{pool_w}}" + "".join(
            f"{d:>{col_w}}" for d in sorted_districts
        ) + f"{'Total':>{col_w}}"
        print(header)
        print("-" * len(header))
        for p in sorted_pools:
            row_vals = [counts.get((p, d), 0) for d in sorted_districts]
            row = f"{p:<{pool_w}}" + "".join(f"{v:>{col_w}}" for v in row_vals)
            row += f"{sum(row_vals):>{col_w}}"
            print(row)

    return len(features)
