# TR-1 Pre-Test Locked Performance Prediction (Gate G3)

> **Locked BEFORE running the 60-plot blind test (`TR-3`).** Predictions below are derived exclusively from the 92-plot Training Zone Leave-One-District-Out Spatial CV (`Mae Charim`, `Pua`, `Tha Wang Pha`). Zero blind-zone data was inspected or used.

## 1. Locked Basis (Training Spatial CV Summary)
- **Module A (Random Forest, 400 trees, 24 pre-2020 features, no JRC input):**
  - Overall 3-class Accuracy: **89.1%** | Forest-Binary Accuracy: **91.3%**
  - Per-district Forest-Binary: Pua **100.0%**, Mae Charim **100.0%**, Tha Wang Pha **76.5%**
- **Module B (S2 Optical + S1 Per-Orbit Asc/Desc + Persistence-First Break Detection):**
  - G1 persistence recall: **23/25 (92.0%)**
  - G4 deciduous false persistence: **1/25 (4.0%)**
- **End-to-End 3-Color Triage (Automated `>= 3 rai`, N=66):**
  - G2 + G4 FPR: **0/33 (0.0%)**
  - G1 caught (`RED + AMBER`): **19/20 (95.0%)** (`13 RED + 6 AMBER`)
  - G3 safe routing (`GREEN + AMBER`): **8/13 (61.5%)**

## 2. Locked Pre-Test Predictions for 60-Plot Blind Zone (`Wiang Sa` + `Santisuk`)

| TRL 4 Metric | Target (VP-1) | Locked Prediction (TR-1) | Rationale |
| :--- | :---: | :---: | :--- |
| **Module A Forest-Binary Acc** | — | **85% – 92%** | Spatial CV averaged 91.3% across 3 districts |
| **Recall G1 — Caught (`RED + AMBER`)** | $\ge 85.0\%$ | **86.7% – 93.3%** (13–14/15) | Train OOF caught 95% (19/20) including small/borderline AMBER |
| **Recall G1 — Module B Persistence** | $\ge 85.0\%$ | **86.7% – 93.3%** (13–14/15) | Train Module B detected 92% (23/25) persistent clearings |
| **FPR (G2 + G4 combined, N=30)** | $\le 10.0\%$ | **0.0% – 6.7%** (0–2/30) | Train OOF FPR was 0.0% (0/33); allowing 1–2 terrain edge cases |
| **Hard Negative G3 (`AMBER + GREEN`)** | Report separately | **53% – 73%** (8–11/15) | Train OOF safely routed 61.5% away from false RED |
| **Cutoff Accuracy (all 60 plots)** | $\ge 90.0\%$ | **90.0% – 95.0%** (54–57/60) | Clear post-2020 signal separation seen in EDA-2 |
| **Pipeline Reliability & Determinism** | 100% / 100% | **100% (60/60) & 100% (10/10)** | Verified by `tests/test_pipeline.py` (19/19 passed) |
