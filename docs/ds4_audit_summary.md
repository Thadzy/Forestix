# DS-4 Double-Blind Inter-Rater Agreement Audit (Aggregate Summary Only)

> **Gate G2 Compliance:** This file contains aggregate audit statistics and the SHA-256 lock hash only. No blind plot IDs, coordinates, or individual labels are stored in this repository.

## 1. Ground-Truth Lock (`ground_truth_locked.csv`)
- **Location:** Held outside repository (`~/Documents/forestix_test_holdout/ground_truth_locked.csv`)
- **Blind Zone:** Wiang Sa (24 plots) & Santisuk (36 plots) — **60 plots total** (`G1=15, G2=15, G3=15, G4=15`)
- **SHA-256 Lock:** `c3d68d5b0a14c98f57b5174ed4094ce18bd67b740111bebd6175c917ae7809a9`
- **Resolution Protocol (Option B):** Official **LDD 2567** land-use classes (`A202`/`A602`, `A302`/`A305`, `F201`) combined with post-2020 Hansen/RADD loss serve as the locked primary ground truth (`15/15/15/15`, preserving the VP-2 Wilson CI sample design), independently audited by two blind human reviewers (**Chai** and **Boom**) on Before (2020 Wayback) vs After (Google Satellite) imagery.

## 2. Inter-Rater Agreement (Cohen's Kappa)

| Pairwise Comparison | N | 4-Class (`G1/G2/G3/G4`) | 3-Class (`LOSS [G1+G3] / G2 / G4`) |
| :--- | :---: | :---: | :---: |
| **Boom vs LDD 2567** | 60 | 68.3% ($\kappa = 0.578$) | **90.0% ($\kappa = 0.844 \ge 0.80$ PASS)** |
| **Chai vs LDD 2567** | 56 *(4 UNSURE)* | 71.4% ($\kappa = 0.617$) | 80.4% ($\kappa = 0.710$) |
| **Chai vs Boom** | 56 | 64.3% ($\kappa = 0.506$) | 73.2% ($\kappa = 0.601$) |

## 3. Key Audit Findings
- **Old Cropland (`G2`, N=15):** **15/15 (100%)** agreement by both Chai and Boom.
- **Intact Forest (`G4`, N=15):** **14/15 (93.3%)** agreement by both Chai and Boom.
- **3-Way Consensus (LDD + Chai + Boom):** Unanimous (3/3) on **32/60**, Majority ($\ge 2/3$) on **53/60 (88.3%)**, 3-way split on only **7/60**.
- **Engineering Justification:** Disagreements concentrated almost entirely on separating natural forest clearing (`G1`) from rubber/teak plantation harvest (`G3`) by VHR eye alone ($\kappa = 0.506$), empirically confirming both the necessity of LDD 2567 for `G3` ground-truthing and the need for the `AMBER` human-review triage status in Forestix.
