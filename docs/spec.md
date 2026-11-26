# Dataset & Spatial Split Specification
**Locked Version:** v1.0 (Pre-Model Lock)

## 1. Core Spatial & Temporal Parameters
- **Study Area:** จังหวัดน่าน (Nan Province, Thailand)
- **Coordinate Reference System (CRS):**
  - Input / Storage Standard: `EPSG:4326` (WGS 84)
  - Area & Buffer Calculation: `EPSG:32647` (WGS 84 / UTM Zone 47N)
- **Simulated / Policy Cutoff Date:** **`2020-12-31`** (31 ธันวาคม 2020 ตามเกณฑ์ TFM / EUDR และตรงกับปีฐานของแผนที่ `JRC/GFC2020/V4`)
- **Historical Data Window:** `2015-01-01` ถึง `2025-12-31` (แบ่งเป็น Pre-Cutoff Baseline: 2015–2020 และ Post-Cutoff Monitoring: 2021–2025)

## 2. Spatial Split (Zero Data Leakage Policy)
แบ่งพื้นที่อำเภอใน จ.น่าน ออกเป็น 2 โซนขาดจากกัน เพื่อป้องกันไม่ให้โมเดลจำลักษณะภูมิประเทศของชุดทดสอบได้:
- **Calibration / Training Zone (80–120 แปลง):**
  - อำเภอเป้าหมาย: **อ.แม่จริม, อ.ปัว, อ.ท่าวังผา**
  - สัดส่วน: 4 กลุ่ม กลุ่มละ 20–30 แปลง (ใช้สำหรับ EDA, เทรน Random Forest และจูน Threshold)
  - ผู้เข้าถึงข้อมูล: ชาย และ Thadzy
- **Blind Verification Zone (60 แปลง):**
  - อำเภอเป้าหมาย: **อ.เวียงสา, อ.สันติสุข**
  - สัดส่วน: 4 กลุ่ม กลุ่มละ 15 แปลง (คละขนาดแปลง 1–2 ไร่, 3–5 ไร่, $\ge 10$ ไร่)
  - กฎการเข้าถึง (Gate G2): **ชาย และ ผู้ประเมินคนที่ 3 เท่านั้น** (ห้าม Thadzy เปิดดูจนกว่าจะถึงวันรันทดสอบ `TR-3`)

## 3. Target Classes & Labeling Schema (`ground_truth_locked.csv`)
| รหัสกลุ่ม | ชื่อกลุ่ม (Class) | นิยามการติดป้ายจากภาพ VHR (Google Earth Pro + ESRI Wayback + S2 Chips) |
| :--- | :--- | :--- |
| **G1** | `NEW_DEFORESTATION` | เคยเป็นป่าธรรมชาติ ณ 31 ธ.ค. 2020 และถูกเปิดหน้าดิน/ถางหลัง 31 ธ.ค. 2020 (แบ่งครึ่งถางหน้าแล้ง vs ถางหน้าฝน) |
| **G2** | `EXISTING_CROPLAND` | เป็นพื้นที่เกษตร/ไร่ข้าวโพดที่ไถพรวนต่อเนื่องอยู่แล้วก่อน 31 ธ.ค. 2020 |
| **G3** | `PLANTATION_HARVEST` | เป็นสวนยางพาราหรือสวนไม้เศรษฐกิจ (เห็นแนวแถวปลูกชัดเจน) และมีการโค่นตัดหลัง 31 ธ.ค. 2020 |
| **G4** | `INTACT_FOREST` | เป็นป่าธรรมชาติ ณ 31 ธ.ค. 2020 และคงสภาพป่าต่อเนื่อง (เน้นป่าผลัดใบ/เบญจพรรณ) |