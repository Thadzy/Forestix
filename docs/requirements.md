# System Requirements & Triage Rules (TRL 4)
**Project:** Automated Deforestation Plot Verification & Physical Status Registry
**Scope:** TRL 4 System Integration & Blind Verification (Nan Province Pilot)

## 1. Functional Requirements (SA-1)
- **FR-01 Plot Ingestion & Geometry Guard:** ระบบต้องรับขอบเขตแปลง (GeoJSON/SHP) และวันตัดยอด (Cutoff Date) แปลงพิกัดเป็น UTM Zone 47N คำนวณขนาดพื้นที่ (ไร่) และนับจำนวนพิกเซลบริสุทธิ์ (Pure Pixels) หลังหดขอบเข้าด้านใน 10 เมตร
- **FR-02 Multi-Sensor Satellite Acquisition:** ระบบต้องดึงอนุกรมเวลาย้อนหลัง (2015–ปัจจุบัน) จาก Sentinel-2 L2A (พร้อม Cloud Score+), Sentinel-1 GRD (แยก Ascending/Descending), Landsat 8/9 C2 และ SRTM DEM ผ่าน Google Earth Engine (GEE) API ได้อัตโนมัติ
- **FR-03 Two-Stage Deforestation Analysis:**
  - *Module A (Forest Baseline):* จำแนกสถานะพื้นที่ ณ วันตัดยอด (ป่าธรรมชาติ / สวนไม้ปลูก / ไร่เดิม / ไร่พัก) พร้อมค่าความมั่นใจ (Confidence Probability)
  - *Module B (Change Detection):* ตรวจจับจุดเปลี่ยนโครงสร้างเรือนยอด (Break Date) และขนาดการเปลี่ยนแปลง ($\Delta\text{NDVI}, \Delta\text{NBR}, \Delta\text{VH}$) หลังวันตัดยอด พร้อมตรวจสอบความต่อเนื่องข้ามฤดูฝนถัดไป (Persistence Check)
- **FR-04 3-Color Triage & Evidence Generation:** ระบบต้องจัดกลุ่มแปลงเป็น 3 สถานะ (เขียว / เหลือง / แดง) และสร้างชุดหลักฐาน (กราฟ Time-series ที่มีเส้นมาร์ก Cutoff & Break Date + ภาพคู่เทียบ Before/After RGB & SWIR)
- **FR-05 Human-in-the-Loop (HITL) & Ledger State:** ระบบต้องบันทึกสถานะลงฐานข้อมูล แยกสถานะจากโมเดล (`model_status`) ออกจากสถานะยืนยันโดยคน (`final_verified_status`) และรองรับการบันทึกคำโต้แย้ง (Appeal)

## 2. Non-Functional & Performance Targets (SA-1)
- **NFR-01 Classification Recall (กลุ่มถางใหม่):** $\ge 85.0\%$
- **NFR-02 False Positive Rate (กลุ่มไร่เดิม & ป่าผลัดใบ):** $\le 10.0\%$
- **NFR-03 Cutoff Classification Accuracy:** $\ge 90.0\%$ และ **Median Date Error:** $\le 30$ วัน
- **NFR-04 Pipeline Reliability & Determinism:** รันครบ 60 แปลงทดสอบโดยไม่เกิด Error ($100\%$) และรันซ้ำได้ผลลัพธ์เดิม $100\%$ (เวลาประมวลผลเฉลี่ย $\le 30$ วินาที/แปลง)

## 3. Operating Environment & Edge Conditions (SA-2)
- **พื้นที่เป้าหมาย (จ.น่าน):** ภูมิประเทศภูเขาสลับซับซ้อน ความลาดชันสูง ($> 20^\circ$) ซึ่งทำให้ค่าเรดาร์ Sentinel-1 เกิดความคลาดเคลื่อนระหว่างวงโคจรขาขึ้น (Ascending) และขาลง (Descending) จึงต้องแยกประมวลผลคนละชุด (Late Fusion)
- **สภาพเมฆฤดูฝน (พ.ค.–ต.ค.):** ภาพถ่ายดาวเทียมแสง (Sentinel-2) ถูกเมฆปกคลุมต่อเนื่อง ระบบต้องใช้ Sentinel-1 SAR (VV/VH) เป็นตัวตรวจจับหลักในช่วงฤดูฝน
- **ป่าผลัดใบหน้าแล้ง (ก.พ.–เม.ย.):** ป่าเบญจพรรณและป่าเต็งรังทิ้งใบตามธรรมชาติ ระบบต้องใช้โมเดลแยกฤดูกาล (CCDC Harmonic) ร่วมกับ Persistence Check ข้ามไปถึงต้นฤดูฝนถัดไป
- **ข้อจำกัดขนาดแปลง (Mixed Pixels):** ดาวเทียม Sentinel-2 มีความละเอียด 10–20 ม. แปลงขนาดเล็กกว่า 3 ไร่จะมีจำนวน Pure Pixels น้อยและค่าสัญญาณแกว่งสูง ระบบต้องมีกลไกคัดเข้าคิวคนตรวจแทนการฟันธงอัตโนมัติ

## 4. 3-Color Triage Decision Rules (SA-4)
| สถานะ (Status) | เงื่อนไขการตัดสินใจ (Decision Logic) | การดำเนินการต่อในระบบ (Action) |
| :--- | :--- | :--- |
| **GREEN (`AUTO_PASS`)** | 1) Module A ทายเป็น `Non-Forest` (ไร่เดิม) ด้วย `Conf >= 0.70` **หรือ**<br>2) เคยเป็นป่า ณ วันตัดยอด แต่ Module B ไม่พบการถางหลัง Cutoff และขนาดแปลง $\ge 3$ ไร่ | ผ่านเกณฑ์อัตโนมัติ ผู้ซื้อ/ธนาคารสามารถตรวจสอบสถานะได้ทันที |
| **AMBER (`REVIEW_QUEUE`)** | เข้าเงื่อนไขข้อใดข้อหนึ่ง:<br>1) Module A มี `Conf < 0.70` (แยกสวนยางกับป่าไม่ขาด)<br>2) `Break Date` ตกในช่วง Buffer **$\pm 30$ วัน** รอบวันตัดยอด (1 ธ.ค. 2020 – 30 ม.ค. 2021)<br>3) แปลงขนาดเล็ก (`Area < 3 ไร่` หรือ `Pure Pixels < 9 px`) | ส่งเข้าคิวให้ **Human Reviewer** เปิดดูภาพ VHR ย้อนหลังและกราฟ Time-series เพื่อยืนยัน |
| **RED (`FLAGGED`)** | Module A ยืนยันว่าเป็นป่า (`Conf >= 0.70`) **และ** Module B พบการถางหลังวันตัดยอดชัดเจน (เกินช่วง Buffer +30 วัน) และผ่าน Persistence Check | ติดธงเตือนสถานะ **`PENDING_VERIFY`** (ห้ามตัดสิทธิ์อัตโนมัติ) รอคนตรวจยืนยันและเปิดให้เจ้าของแปลงยื่นคำโต้แย้ง |