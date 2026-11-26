# Forestix DS-7: Exploratory Data Analysis (EDA Report)
**Dataset:** `data/train/train_plots.geojson` (92 LDD-2567-verified plots in Mae Charim, Pua, Tha Wang Pha)  
**Time Series:** Landsat (552 rows), Sentinel-2 (8832 rows), Sentinel-1 (17664 rows), Terrain/JRC (92 rows)

## EDA-1: Cloud-Free Observation Availability (Sentinel-2 vs Sentinel-1)
| Month | Season | S2 Clear Plot-Months (%) | S2 Mean Clear Obs | S1 Valid Plot-Months (%) |
| :---: | :--- | :---: | :---: | :---: |
| 01 | Dry | 100.0% | 8.41 | 100.0% |
| 02 | Dry | 96.6% | 7.33 | 100.0% |
| 03 | Dry | 100.0% | 8.57 | 99.5% |
| 04 | Dry | 98.1% | 7.25 | 100.0% |
| 05 | Rainy | 86.5% | 4.97 | 100.0% |
| 06 | Rainy | 72.6% | 1.85 | 100.0% |
| 07 | Rainy | 65.2% | 1.66 | 100.0% |
| 08 | Rainy | 61.5% | 1.34 | 100.0% |
| 09 | Rainy | 77.0% | 2.23 | 100.0% |
| 10 | Rainy | 85.6% | 5.05 | 100.0% |
| 11 | Dry | 99.9% | 7.11 | 100.0% |
| 12 | Dry | 100.0% | 9.15 | 100.0% |

> **Finding:** Dry-season S2 clear availability averages **99.1%** vs Rainy-season (May–Oct) **74.8%**, confirming SA-2 that Sentinel-1 SAR is essential for rainy-season clearing detection.

## EDA-2: Pre-2020 Phenology & Post-2020 Canopy Drop by Group
| Group | N | Landsat Pre-2020 NDVI | S2 Pre Dry (Feb–Apr) | S2 Pre Rain (Jun–Oct) | Post-2020 dNDVI (p10-med) | Post-2020 dNBR (p10-med) | Post-2020 dVH (dB) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **G1** | 25 | 0.741 | 0.616 | 0.749 | -0.305 | -0.355 | -2.66 |
| **G2** | 25 | 0.513 | 0.369 | 0.541 | -0.135 | -0.173 | -2.33 |
| **G3** | 17 | 0.714 | 0.553 | 0.761 | -0.326 | -0.379 | -3.50 |
| **G4** | 25 | 0.817 | 0.730 | 0.752 | -0.150 | -0.113 | -1.09 |

## EDA-3: Sentinel-1 SAR Orbit Offset & Noise by Terrain Slope
| Slope Bin | Plots | Mean |VH_Asc - VH_Desc| (dB) | Mean Within-Orbit VH Std (dB) |
| :--- | :---: | :---: | :---: |
| <15 deg | 49 | 1.85 dB | 1.45 dB |
| 15-25 deg | 30 | 3.78 dB | 0.97 dB |
| >25 deg | 13 | 6.70 dB | 0.88 dB |

## EDA-4: Geometry Guard (Area & Pure Pixels by Size Bin)
| Size Bin | Plots | Mean Area (rai) | Mean Pure Pixels | Flagged Small (`<3 rai` or `<9 px`) |
| :--- | :---: | :---: | :---: | :---: |
| small_1_2rai | 26 | 1.99 | 13.1 | 26/26 (100%) |
| medium_3_5rai | 31 | 4.54 | 42.5 | 0/31 (0%) |
| mid_6_9rai | 3 | 7.45 | 77.7 | 0/3 (0%) |
| large_10plus_rai | 32 | 14.37 | 167.9 | 0/32 (0%) |

## EDA-5: JRC GFC2020 Baseline Agreement vs LDD 2567
| Group | Plots | JRC Marks as Forest (`frac >= 0.5`) | Interpretation |
| :--- | :---: | :---: | :--- |
| **G1** | 25 | 22/25 (88.0%) | Expected high (forest at 2020 before clearing) |
| **G2** | 25 | 0/25 (0.0%) | Commission error if > 0% (old cropland falsely called forest) |
| **G3** | 17 | 0/17 (0.0%) | Commission error (LDD rubber/teak plantation falsely called natural forest!) |
| **G4** | 25 | 25/25 (100.0%) | Expected high (intact deciduous forest) |
