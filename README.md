# Forestix

Checks whether a farm plot in Nan Province, Thailand, was forest on 31 Dec 2020 and was cleared after that date. Built from satellite data in Google Earth Engine.

Course project for FRA361/362 Studio IV, FIBO, KMUTT. Solution team: Thadzy and Chai (ชาย ชาตรี). Target: TRL 4.

> **Status: draft.** Methods, thresholds and dates below are the current plan, not results. Nothing here is validated yet.

## What it does

```
plot polygon
   │
   ├─ Module A: was this plot forest on 31 Dec 2020?
   │            Random Forest on pre-2020 features
   │
   ├─ Module B: was it cleared after 2020, and in which month?
   │            CCDC on Sentinel-2, plus Sentinel-1 radar drop for cloudy months
   │
   └─ Decision: red    = forest at cutoff, cleared after
                green  = not forest before 2020, or no clearing
                yellow = unsure, sent to human review
      Output: status plus evidence (clearing month, time-series plots)
```

Test groups:

| Group | Expected |
|---|---|
| New clearing after 2020 | red |
| Old farm, cleared before 2020 | green |
| Rubber cut after 2020 | green (hardest case) |
| Intact forest | green, no false alarm |

## Data sources (planned)

| Use | Earth Engine ID |
|---|---|
| Optical time series | `COPERNICUS/S2_SR_HARMONIZED` with Cloud Score+ |
| Radar | `COPERNICUS/S1_GRD` (ascending and descending kept apart) |
| Pre-2020 history | `LANDSAT/LC08/C02/T1_L2` |
| Slope | `USGS/SRTMGL1_003` |
| 2020 forest baseline | `JRC/GFC2020/V4` |
| Candidate plots | Hansen GFC, ESA WorldCover, LDD land use |

## Setup

1. Register your own Google Cloud project for Earth Engine (non-commercial).
2. Install:

   ```bash
   pip install earthengine-api geemap
   ```

3. Set your project ID and test the connection. It should print `elevation`.

   ```bash
   export EE_PROJECT=your-project-id
   ```

   ```python
   import os, ee
   ee.Authenticate()
   ee.Initialize(project=os.environ["EE_PROJECT"])
   print(ee.Image("USGS/SRTMGL1_003").getInfo()["bands"][0]["id"])
   ```

## Layout (planned)

```
docs/        verification plan, interface spec, decision rules
src/         extraction, features, Module A, Module B, decision
notebooks/   EDA
data/train/  training plot polygons and labels only
```

## Rules for this repo

This repo is **public**.

- **Never commit the blind test set** (`blind_plots.geojson` or its labels). It stays with the labellers until the single blind run.
- **Never commit keys or credentials** (service account JSON, tokens).
- Large exports (`*.parquet`, `*.tif`) go to Google Drive, not git.
