# TR-1: Pre-Registered Blind Test Performance Predictions (Gate G3)

**Date Locked:** 2026-11-28 (prior to extracting or running any blind-zone data)  
**Model Artifact:** `data/train/module_a_rf.pkl` (trained on 92 LDD-2567 plots in Mae Charim, Pua, Tha Wang Pha) + `src/forestix/module_b.py` + `src/forestix/decision.py`  
**Blind Ground Truth SHA-256:** `c3d68d5b0a14c98f57b5174ed4094ce18bd67b740111bebd6175c917ae7809a9` (60 plots in Wiang Sa & Santisuk, held outside repo)

## Locked Predictions (Derived Strictly from Train-Zone LODO Spatial CV)

| Metric | Train Spatial CV (92 plots) | Locked Blind Prediction (60 plots) | TRL 4 Pass Criterion |
| :--- | :---: | :---: | :---: |
| **Module A Forest-Binary Accuracy** | 91.3% (3-class: 89.1%) | **85% – 92%** | Benchmark vs JRC GFC2020 |
| **Module B G1 Clearing Detection (Persistence)** | 92.0% (23/25) | **85% – 93%** (13–14 / 15) | Recall $\ge 85.0\%$ |
| **End-to-End G1 Caught (`RED` + `AMBER`, $\ge 3$ rai)** | 95.0% (19/20; 13 RED + 6 AMBER) | **85% – 95%** | Recall $\ge 85.0\%$ |
| **G2 + G4 False Positive Rate (`RED` on non-deforested)** | 0.0% (0/33 automated, 0/50 all) | **0.0% – 6.7%** (0–2 / 30) | FPR $\le 10.0\%$ |
| **G3 Hard Negative Safe Routing (`AMBER` + `GREEN`)** | 61.5% (8/13 automated; 12/17 all) | **55% – 75%** | Tracked separately (HITL) |
| **Cutoff Side Accuracy (Post-2020 vs Pre/No-Clear)** | 92.4% | **$\ge 88\%$ – 93%** | $\ge 90.0\%$ |
| **Pipeline Reliability & Determinism (NFR-04)** | 93/93 (100%), 15/15 identical | **60/60 (100%)**, **10/10 identical** | 100% / 100% |
