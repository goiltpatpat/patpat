# Patpat

<img align="right" height="210" alt="Patpat mascot" src="assets/mascot.png">

[![Validate](https://github.com/goiltpatpat/patpat/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/goiltpatpat/patpat/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-2f6f5f.svg)](LICENSE)

[English](README.md) · [ภาษาไทย](README.th.md)

**เพิ่มการพิสูจน์อีกนิด ลดการคาดเดาลงอีกเยอะ (A little more proof. A lot less guesswork.)**

Patpat คือระบบปฏิบัติการบนฐานหลักฐานเชิงประจักษ์ (Evidence-driven operating layer) สำหรับ AI agent เพื่อมอบวิจารณญาณแบบวิศวกรอาวุโส (Senior Engineer) ที่รอบคอบให้กับ Agent: เข้าใจปัญหาที่แท้จริง เลือกความลึกของงานให้เหมาะสม ทำการเปลี่ยนแปลงเฉพาะจุดที่จำเป็น พิสูจน์ผลลัพธ์บนพื้นผิวที่สำคัญจริงๆ และรายงานสิ่งที่ยังไม่ได้รับการพิสูจน์อย่างตรงไปตรงมา ครอบคลุมทั้งงานโค้ด งานใน repository งานส่งมอบประเภทเอกสารและการวิเคราะห์ ตลอดจนงานผสมผสาน ทำงานได้บน Codex, Claude Code, Grok CLI, Antigravity, Cursor และโฮสต์ที่รองรับ Agent Skills อื่นๆ

มาสคอตเป็นมิตร แต่คำถามค่อนข้างจริงจังและเจาะลึก

- **เข้าใจก่อนแก้ไข:** สำรวจ workspace จริง ค้นหาข้อตกลง (contract) ที่มีความสำคัญ และปกป้องงานที่กำลังดำเนินอยู่
- **ทำให้หลักฐานเป็นส่วนหนึ่งของงาน:** ตัดสินว่าหลักฐานใดที่จะแสดงถึงความสำเร็จก่อนลงมือทำ ทดสอบบนพื้นผิวหลัก (authoritative surface) และแยกแยะสิ่งที่พิสูจน์แล้วออกจากข้อสมมุติฐาน
- **ให้มนุษย์เป็นผู้ควบคุมเสมอ:** ปรับระดับกระบวนการทำงานให้เหมาะสมกับความเสี่ยง และไม่เปลี่ยนความสามารถทางเทคนิค (capability) ให้กลายเป็นการอนุญาต (permission) โดยพลการ

[คู่มือ (Guide)](docs/guide/README.md) · [การติดตั้งและอัปเดต](docs/guide/installing.md) · [แผนที่ความสามารถ (Capability map)](docs/guide/capability-map.md) · [Releases](https://github.com/goiltpatpat/patpat/releases) · [ความปลอดภัย](https://github.com/goiltpatpat/patpat/security/policy)

<br clear="all">

## โครงสร้างของ Patpat

```text
Protocol -> Playbooks -> Skills -> Evidence -> Host Adapters
```

| เลเยอร์ | สิ่งที่มอบให้กับ Agent |
| --- | --- |
| [Operating protocol](skills/patpat-loop/references/operating-protocol.md) | แกนกลางของวิจารณญาณ ความปลอดภัย กฎเกณฑ์เกี่ยวกับ Git และหลักฐานเชิงประจักษ์ที่ทุกเส้นทางต้องปฏิบัติตาม |
| [Playbooks](skills/patpat-loop/references/route-catalog.md) | แนวทางการตัดสินใจสำหรับสถานการณ์เฉพาะ: การแก้บั๊ก, การทำ migration, การส่งมอบ PR, ปัญหาประสิทธิภาพถดถอย, การรับช่วงต่องานในเซสชัน |
| [Skills](#เลือก-skill-ที่เหมาะสม) | จุดเริ่มต้นการทำงานที่โฟกัส 29 รูปแบบ ตั้งแต่การอ่านวิเคราะห์อย่างเดียว ไปจนถึงการตรวจ statechart และการส่งมอบงาน |
| Evidence | เครื่องมือแบบ Deterministic ที่ Agent เชื่อถือได้มากกว่าข้อสรุปของตัวเอง: เครื่องจักรสถานะสำหรับงานยาว (durable-run state machine), ตัวตรวจสอบ plan และ program, การทำ assignment fencing, การตรวจสอบโมเดลด้วย TLA+/TLC, รายงานที่ผูกกับใบเสร็จผลการรันจริง (receipts) |
| Host adapters | ส่วนเชื่อมต่อแบบบางสำหรับแต่ละโฮสต์ ไม่มีการกำหนดพฤติกรรมใหม่หรือให้สิทธิ์อำนาจเพิ่มเติมโดยพลการ |

แต่ละเลเยอร์สามารถจำกัดขอบเขตของเลเยอร์ก่อนหน้าได้ แต่ไม่มีเลเยอร์ใดที่สามารถลดทอนความเข้มงวดของเกตความปลอดภัยลงได้

## เริ่มต้นใช้งานอย่างรวดเร็ว

ต้องการ Python 3.11 ขึ้นไป ติดตั้ง เริ่มเซสชัน**ใหม่** และยืนยันว่า Agent มองเห็น Patpat แล้ว (การมีชื่อแพ็กเกจอยู่ในรายการเพียงอย่างเดียวไม่ได้พิสูจน์ว่าถูกค้นพบตอน prompt)

| โฮสต์ | การติดตั้ง | วิธีเรียกใช้ |
| --- | --- | --- |
| Codex | `codex plugin marketplace add goiltpatpat/patpat` แล้วตามด้วย `codex plugin add patpat@patpat` | `$patpat` |
| Claude Code | `claude plugin marketplace add goiltpatpat/patpat` แล้วตามด้วย `claude plugin install patpat@patpat` | `/patpat:patpat` |
| Grok CLI | `grok plugin install goiltpatpat/patpat --trust` | `/patpat` |
| Antigravity | จาก [clean clone](docs/guide/installing.md#antigravity): `agy plugin validate <clone>` แล้วตามด้วย `agy plugin install <clone>` | `/patpat` หรือ UI ของโฮสต์ |
| Cursor | Customize → From GitHub Repository → `goiltpatpat/patpat` | `/patpat` |
| โฮสต์ Agent Skills อื่นๆ | `python3 scripts/install_skills.py --target <proven skills dir> --dry-run` จากนั้นรันซ้ำโดยไม่ต้องใส่ `--dry-run` | `Use patpat to ...` |

การเรียกใช้ในเซสชันใหม่บน Claude Code และ Cursor รวมถึงการ live import ของ Cursor ยังไม่ได้รับการยืนยันโดยโปรเจกต์นี้ สำหรับ [คู่มือการติดตั้ง](docs/guide/installing.md) จะครอบคลุมเรื่อง local trees, portable packages, การอัปเดต, การถอนการติดตั้ง และพฤติกรรมของ hook ในแต่ละโฮสต์ ส่วน Agent ที่จะติดตั้ง Patpat ให้ปฏิบัติตาม [`AGENTS.md`](AGENTS.md)

จากนั้น มอบหมายงานที่เฉพาะเจาะจง:

```text
$patpat reproduce this timeout, fix the cause, and verify the result. local only
$patpat explain where this request is validated and what could bypass it
$patpat plan the migration, identify the risks, and tell me what evidence we need
$patpat can our checkout charge a customer twice? show me the path
```

## คำแนะนำการใช้งานให้ได้ผลลัพธ์ที่ดีที่สุด

- **เลือกความลึกให้เหมาะกับงาน (Proportionality):** สำหรับคำถามง่ายๆ การตรวจสอบ หรือการสำรวจโค้ด ให้เรียก [`patpat-inspect`](skills/patpat-inspect/SKILL.md) โดยตรงเพื่อจำกัดสถานะให้อยู่ในโหมดอ่านอย่างเดียว (read-only) และเก็บการรันเต็มลูป `/patpat` ไว้สำหรับงานที่มีการแก้ไขที่ต้องการการพิสูจน์สาเหตุที่แท้จริง (root cause) และการยืนยันผล
- **ระบุพื้นผิวการยืนยันผลลัพธ์ล่วงหน้า (Verification surface):** บอก Agent ให้ชัดเจนว่าคุณคาดหวังให้พิสูจน์ผลลัพธ์ด้วยอะไร (เช่น `$patpat fix the timeout and verify with existing integration tests`)
- **ใช้ Safety Modifiers เพื่อควบคุมขอบเขต:** จำกัดการทำงานให้อยู่ในกรอบที่ปลอดภัยโดยเติม `local only` (เพื่อป้องกันการ git push หรือเปิด PR) หรือสั่งให้ `plan first` ก่อนลงมือแก้ไขโค้ดใดๆ
- **เรียกใช้ Skill เฉพาะทางโดยตรง:** เมื่อคุณทราบผลลัพธ์ที่ต้องการอย่างชัดเจน (เช่น ต้องการแผนภาพสถาปัตยกรรม ให้เรียก [`patpat-repository-diagram`](skills/patpat-repository-diagram/SKILL.md) หรือต้องการตรวจสอบ race condition ใน flow ให้เรียก [`patpat-statechart`](skills/patpat-statechart/SKILL.md)) ให้เรียก skill นั้นตรงๆ แทนที่จะส่งผ่านตัวจัดเส้นทางของลูป

## การทำงาน

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY
VERIFY -> REPORT เมื่อการแก้ไขเกิดขึ้นเฉพาะที่ (local), ย้อนกลับได้ (reversible), และไม่ต้องการส่งมอบ (not shipping)
VERIFY -> REVIEW ก่อนการส่งมอบ, งานที่มีความเสี่ยงสูง, หรือ durable-run LEARN | REPORT
REVIEW -> LEARN? -> เสนอและรอการอนุมัติ -> แก้ไขหลังได้รับอนุมัติ -> VERIFY -> REVIEW -> REPORT
```

- **เลือกความลึกที่เหมาะสมให้อัตโนมัติ:** การแก้คำผิดจะได้การตรวจสอบแบบรวดเร็ว ส่วนงานด้าน Auth, ระบบเงิน (billing), migration และงานที่มีผลกระทบเป็นวงกว้าง จะต้องผ่านการออกแบบและการรีวิวอิสระก่อนเสมอ Patpat จะประเมินจากสัญญาณความเสี่ยงโดยไม่ต้องให้ผู้ใช้มาคอยเลือกโหมด
- **พิสูจน์ก่อนแก้ไข:** Agent จะระบุสมมุติฐานที่ต้องการยืนยัน (claim), พื้นผิวที่ใช้พิสูจน์ (surface), การกระทำ (action), ผลการสังเกตที่คาดหวัง (expect) และการคืนค่าระบบ (cleanup) ก่อนที่จะลงมือแก้โค้ด การบิลด์ผ่านเป็นเพียงสัญญาณสนับสนุน แต่ไม่ได้พิสูจน์พฤติกรรมที่ผู้ใช้มองเห็นจริง แถบเขียวเป็นเพียงสัญญาณ ไม่ใช่ข้ออ้าง
- **ความล้มเหลวจะเปลี่ยนแผน:** หากหลักฐานล้มเหลว จะถูกจำแนกว่าเป็นข้อบกพร่องของการนำไปใช้ (implementation defect), ข้อบกพร่องของตัวตรวจสอบ (verifier defect) หรืออุปสรรคของสภาพแวดล้อม (environment blocker) แล้วระบบจะย้อนกลับไปยังขั้นตอนแรกสุดที่ไม่ถูกต้อง การล้มเหลวซ้ำเดิม 3 ครั้งจะหยุดการทำงานและระบุหลักฐานที่จำเป็นต้องมีเพื่อดำเนินการต่อ
- **รายงานอย่างตรงไปตรงมา:** ทุกข้ออ้างอิงจะถูกระบุสถานะชัดเจนว่า `verified`, `partially verified`, `implemented but not verified` หรือ `not implemented`
- **ครอบคลุมมากกว่างานโค้ด:** สำหรับเอกสาร การวิเคราะห์ และงานส่งมอบอื่นๆ Patpat จะใช้วิจารณญาณเดียวกันผ่าน [แนวทางสำหรับงานทั่วไป (general task guidance)](skills/patpat-loop/references/general-task-judgment.md) โดยไม่ต้องผ่านกระบวนการของ Git

**คำสั่งของคุณเป็นตัวควบคุมการส่งมอบงาน:** การเปิดใช้งานเป็นการอนุญาตให้เข้าสู่ลูป การพิสูจน์ และการยืนยันผล การทำ commit และสร้าง PR ต้องมีเจตนาในการส่งมอบ (delivery intent); คำสั่งแบบข้ามคืน (overnight) หรือ "don't stop" หมายถึงให้ยืนยันผล รีวิว เปิด PR และหยุดเมื่อพร้อม merge; การ merge ต้องมีคำว่า land หรือ merge ชัดเจน; `local only` จะจำกัดการทำงานให้อยู่เฉพาะที่เครื่อง และ `disable /patpat` จะเป็นการปิดการทำงานของ Patpat

## เลือก Skill ที่เหมาะสม

`/patpat` จะจัดเส้นทางงานให้คุณโดยอัตโนมัติ แต่คุณสามารถเรียกใช้ skill ได้โดยตรงเมื่อทราบประเภทของงานอยู่แล้ว มีเพียง `patpat-inspect` ที่โหลดจากคำขอภาษาธรรมดาได้บนทุก host ส่วนบน Claude Code และ Cursor ทางเข้า Patpat (`patpat`, `patpat-loop`) ก็โหลดได้เช่นกัน skill อื่นต้องเรียกด้วยชื่อ เช่น `/patpat:patpat-debug` บน Claude Code, `/patpat-debug` บน Cursor หรือ `$patpat-debug` บน Codex:

| งานที่ต้องการทำ | Skill |
| --- | --- |
| อธิบายว่าโค้ดทำงานอย่างไรหรือทำไมถึงเขียนแบบนี้ โดยไม่มีการแก้ไขไฟล์ | [`patpat-inspect`](skills/patpat-inspect/SKILL.md) |
| แก้ไขบั๊กที่สร้างซ้ำได้จากสาเหตุที่แท้จริง (root cause) | [`patpat-debug`](skills/patpat-debug/SKILL.md) |
| สร้างฟีเจอร์หรือทำการ refactor ที่มีขอบเขตชัดเจน 1 จุด | [`patpat-change`](skills/patpat-change/SKILL.md) |
| ตกลงการออกแบบ, contract หรือแนวทางการ migration ให้เรียบร้อยก่อน | [`patpat-architect`](skills/patpat-architect/SKILL.md) |
| พิสูจน์ข้ออ้างอิงบนแอปพลิเคชันหรือ artifact จริง | [`patpat-verify`](skills/patpat-verify/SKILL.md) |
| รับการรีวิวโค้ดอย่างเป็นอิสระและตั้งคำถามเชิงท้าทาย | [`patpat-review`](skills/patpat-review/SKILL.md) |
| วาดแผนภาพสถาปัตยกรรม, workflow หรือวงจรชีวิตระบบ (lifecycle) | [`patpat-repository-diagram`](skills/patpat-repository-diagram/SKILL.md) |
| ตรวจสอบว่า flow ทำงานติดขัดหรือทำลายกฎเกณฑ์หรือไม่ และแสดงบั๊กในรูปแบบเส้นทาง | [`patpat-statechart`](skills/patpat-statechart/SKILL.md) |
| ขับเคลื่อนหรือสานต่องานยาวที่แบ่งเป็นหลายเฟส | [`patpat-run`](skills/patpat-run/SKILL.md) |
| Commit และเปิด PR หลังงานผ่านการยืนยันผลแล้ว | [`patpat-ship`](skills/patpat-ship/SKILL.md) |

ทักษะการวาดแผนภาพ (diagram) และ statechart ทำงานร่วมกันเป็นคู่: แผนภาพวงจรชีวิตสามารถใช้เป็นจุดเริ่มต้นสร้าง statechart ด้วย label เดียวกัน และเมื่อพบกฎที่ถูกละเมิด จะส่งผลกลับมายังแผนภาพเป็นเรื่องราวแบบนำทางที่ระบุจุดที่ flow ผิดพลาด

<details>
<summary>ดูรายการ Skill ทั้งหมด 29 รายการ</summary>

| Skill | ใช้เมื่อ |
| --- | --- |
| [`patpat`](skills/patpat/SKILL.md) | คำสั่งย่อ (slash alias) สำหรับเข้าสู่ลูป |
| [`patpat-loop`](skills/patpat-loop/SKILL.md) | งานที่ไม่ใช่งานเล็กๆ และจำเป็นต้องใช้ลูปการทำงานเต็มรูปแบบ |
| [`00-workspace-mapper`](skills/00-workspace-mapper/SKILL.md) | สร้างแผนผัง workspace ที่ยังไม่คุ้นเคยอย่างชัดเจน |
| [`patpat-inspect`](skills/patpat-inspect/SKILL.md) | อธิบาย, ตรวจสอบ (audit), หรือวินิจฉัยโดยไม่มีการแก้ไขไฟล์ |
| [`patpat-impact`](skills/patpat-impact/SKILL.md) | พิสูจน์ผลกระทบ (blast radius) และความถูกต้องของระบบปลายน้ำ |
| [`patpat-plan`](skills/patpat-plan/SKILL.md) | จัดลำดับเฟสงานที่สามารถพิสูจน์ผลได้ โดยยังไม่ลงมือทำจริง |
| [`patpat-architect`](skills/patpat-architect/SKILL.md) | สรุปข้อตกลงสัญญา (contracts), การย้ายระบบ (migrations) และความเสี่ยงก่อน |
| [`patpat-interrogate`](skills/patpat-interrogate/SKILL.md) | ท้าทายการออกแบบหรือการเปลี่ยนแปลงจากมุมมองเชิงปรปักษ์ |
| [`patpat-repository-diagram`](skills/patpat-repository-diagram/SKILL.md) | เปลี่ยนไอเดีย แผนงาน หรือโค้ดเบสให้เป็นแผนภาพอินเทอร์แอคทีฟ |
| [`patpat-statechart`](skills/patpat-statechart/SKILL.md) | จำลองการย้ายสถานะของ flow, ตรวจกฎด้วย TLC, และแสดงบั๊กเป็นเส้นทางเดิน |
| [`patpat-change`](skills/patpat-change/SKILL.md) | นำฟีเจอร์หรือการ refactor 1 จุดที่มีขอบเขตชัดเจนไปปฏิบัติจริง |
| [`patpat-debug`](skills/patpat-debug/SKILL.md) | สร้างซ้ำ (reproduce), หาสาเหตุที่แท้จริง, และแก้ไข |
| [`patpat-perf`](skills/patpat-perf/SKILL.md) | ปรับปรุงประสิทธิภาพที่วัดค่าได้เมื่อพบการถดถอยของทรัพยากร |
| [`patpat-game-builder`](skills/patpat-game-builder/SKILL.md) | สร้างชิ้นส่วนเกมที่เล่นได้จริง แล้วพิสูจน์เส้นทางการเล่นจริงของผู้เล่น |
| [`patpat-verify`](skills/patpat-verify/SKILL.md) | ทดสอบข้ออ้างอิงบนชิ้นงานจริงหรือส่วนติดต่อผู้ใช้จริง |
| [`patpat-verifier`](skills/patpat-verifier/SKILL.md) | สร้างหรือดูแลรักษาตัวตรวจสอบเฉพาะของโปรเจกต์ |
| [`patpat-formal-verify`](skills/patpat-formal-verify/SKILL.md) | สร้างและดูแลรักษา formal model แบบมีขอบเขตเพื่อให้การเปลี่ยนแปลงถัดไปรันซ้ำได้ |
| [`patpat-review`](skills/patpat-review/SKILL.md) | พยายามหาจุดบกพร่องหรือพิสูจน์หักล้างการเปลี่ยนแปลงและหลักฐานอย่างเป็นอิสระ |
| [`patpat-unslop`](skills/patpat-unslop/SKILL.md) | ตัดเนื้อหาส่วนเกินออกจากเอกสารวิศวกรรม, ข้อความ PR และ diff |
| [`patpat-run`](skills/patpat-run/SKILL.md) | ขับเคลื่อนหรือสานต่อกราฟงานหลายเฟสที่ทนทานต่อการขัดจังหวะ |
| [`patpat-engineer`](skills/patpat-engineer/SKILL.md) | ปฏิบัติงานย่อยส่วนหนึ่งที่แยกขาดจากส่วนอื่นสำหรับผู้รับผิดชอบที่ระบุ |
| [`patpat-arena`](skills/patpat-arena/SKILL.md) | แข่งขันแนวทางที่แยกกันจากโจทย์เดียวกัน แล้วสังเคราะห์ผลลัพธ์ที่ผ่านการยืนยัน 1 เดียว |
| [`patpat-swarm`](skills/patpat-swarm/SKILL.md) | ครอบคลุมงานย่อยหรือการแข่งขันแบบคู่ขนาน แล้วส่งรายงานสรุปรวม 1 ฉบับ |
| [`patpat-ship`](skills/patpat-ship/SKILL.md) | Commit และเปิด PR เมื่อมีเจตนาส่งมอบ; merge เฉพาะเมื่อระบุชื่อชัดเจน |
| [`patpat-learn`](skills/patpat-learn/SKILL.md) | แปลงความล้มเหลวที่เกิดขึ้นซ้ำให้กลายเป็นข้อจำกัดที่ทนทานและเล็กที่สุด |
| [`patpat-skill`](skills/patpat-skill/SKILL.md) | สร้าง skill ใหม่ที่นำกลับมาใช้ซ้ำได้ |
| [`patpat-eval`](skills/patpat-eval/SKILL.md) | ประเมินการกระตุ้นและพฤติกรรมของ skill ด้วยเกณฑ์การให้คะแนนอิงหลักฐาน |
| [`patpat-automation`](skills/patpat-automation/SKILL.md) | ออกแบบระบบอัตโนมัติแบบ fail-closed โดยยังไม่เปิดใช้งาน |
| [`patpat-setup`](skills/patpat-setup/SKILL.md) | ติดตั้ง ตรวจสอบความถูกต้อง หรือลบ Patpat บนโฮสต์ |

</details>

<details>
<summary>ดูรายการ Playbooks ทั้งหมด</summary>

| Playbook | สำหรับ |
| --- | --- |
| [Investigation](skills/patpat-loop/playbooks/investigation.md) | การอธิบายแบบอ่านอย่างเดียว: ทำงานอย่างไร อยู่ที่ไหน ใครเป็นเจ้าของ |
| [Rationale forensics](skills/patpat-loop/playbooks/rationale-forensics.md) | ทำไมโค้ดจึงมีรูปแบบปัจจุบัน ยึดจากโค้ดจริงก่อน |
| [Defect](skills/patpat-loop/playbooks/defect.md) | สร้างข้อผิดพลาดซ้ำ พิสูจน์สาเหตุที่แท้จริง แก้ไขด้วยหลักฐานรันไทม์ |
| [Regression first](skills/patpat-loop/playbooks/regression-first.md) | มีการทดสอบที่ทำงานเร็วและแน่นอน: เขียนเทสที่ล้มเหลวก่อน แล้วจึงเขียนโค้ดแก้ |
| [Runtime forensics](skills/patpat-loop/playbooks/runtime-forensics.md) | อาการสด: memory leak, วนลูปไม่หยุด, การแสดงผลผิดพลาด |
| [Trace forensics](skills/patpat-loop/playbooks/trace-forensics.md) | โปรไฟล์ที่บันทึกไว้ trace หรือ heap snapshot |
| [Performance](skills/patpat-loop/playbooks/performance.md) | ความช้าที่วัดค่าได้เทียบกับเกณฑ์มาตรฐานเดิม |
| [Metric hillclimb](skills/patpat-loop/playbooks/metric-hillclimb.md) | ปรับปรุงเมตริกตัวเดียวอย่างต่อเนื่อง โดยยอมรับผลลัพธ์ที่ดีขึ้นทีละก้าว |
| [Blast radius](skills/patpat-loop/playbooks/blast-radius.md) | สิ่งที่การเปลี่ยนแปลงอาจส่งผลกระทบ พิสูจน์จริงแทนการคาดเดา |
| [Architecture change](skills/patpat-loop/playbooks/architecture-change.md) | สัญญา การย้ายระบบ หรือการออกแบบใหม่ที่ต้องลงตัวก่อนเริ่มเขียนโค้ด |
| [Bounded change](skills/patpat-loop/playbooks/bounded-change.md) | พฤติกรรมใหม่หรือพฤติกรรมที่เปลี่ยนไปจากโครงสร้างข้อมูลที่ระบุ |
| [Behavior-preserving refactor](skills/patpat-loop/playbooks/behavior-preserving-refactor.md) | ปรับเปลี่ยนโครงสร้างโดยไม่เปลี่ยนพฤติกรรมการทำงานเดิม |
| [Prototype](skills/patpat-loop/playbooks/prototype.md) | โค้ดร่างแบบใช้แล้วทิ้งที่ช่วยให้การตัดสินใจด้านการออกแบบมีราคาถูกลง |
| [Visual equivalence](skills/patpat-loop/playbooks/visual-equivalence.md) | ความเท่าเทียมกันของ UI ระดับพิกเซลระหว่างการนำไปใช้งานสองแบบ |
| [Bespoke workflow](skills/patpat-loop/playbooks/bespoke-workflow.md) | ไม่มี playbook เฉพาะที่ตรงกับงาน: ให้ออกแบบลำดับขั้นตอนที่พิสูจน์หักล้างได้ |
| [Multi-phase run](skills/patpat-loop/playbooks/multi-phase-run.md) | งานที่ครอบคลุมหลายเฟส มี checkpoint หรือเป็นกราฟงานที่ทนทาน |
| [Session pickup](skills/patpat-loop/playbooks/session-pickup.md) | สานต่องานของตัวเองที่ถูกขัดจังหวะ |
| [Session takeover](skills/patpat-loop/playbooks/session-takeover.md) | รับช่วงต่องานที่กำลังดำเนินการจากสถานะสดของ repository |
| [Pause safely](skills/patpat-loop/playbooks/pause-safely.md) | หยุดพักงานที่กำลังทำอยู่อย่างปลอดภัยโดยไม่เปิด PR หรือ merge |
| [PR drive](skills/patpat-loop/playbooks/pr-drive.md) | จัดการข้อคิดเห็นของ PR ที่ได้รับอนุญาต; land เฉพาะเมื่อได้รับคำขอชัดเจน |
| [PR readiness handoff](skills/patpat-loop/playbooks/pr-handoff.md) | นำ PR ไปสู่สถานะพร้อม merge ที่ผ่านการยืนยัน แล้วส่งมอบการควบคุมกลับ |
| [Worktree cleanup](skills/patpat-loop/playbooks/worktree-cleanup.md) | ลบ Git worktree ที่ถูก merge หรือละทิ้งแล้ว |
| [Arena](skills/patpat-loop/playbooks/arena.md) | ประชันแนวทางที่แยกกันจากโจทย์เดียวกัน แล้วสังเคราะห์ผลลัพธ์ที่ผ่านการยืนยัน |
| [Swarm](skills/patpat-loop/playbooks/swarm.md) | จัดการงานคู่ขนานหรือการแข่งขัน แล้วรวมเป็นรายงานฉบับเดียว |
| [Autopilot](skills/patpat-loop/playbooks/autopilot.md) | จัดการคิวงานหรือ stack ที่ผ่านการยืนยัน; merge เฉพาะเมื่อระบุชื่อชัดเจน |
| [Issue loop](skills/patpat-loop/playbooks/issue-loop.md) | คัดกรองและสร้างข้อผิดพลาดซ้ำจาก issue; หยุดชั่วคราวจนกว่าจะเปิดใช้ PR เริ่มต้นเป็นแบบร่าง |
| [Default delivery](skills/patpat-loop/playbooks/default-delivery.md) | เมื่อมีเจตนาส่งมอบ ให้ commit และเปิด PR ที่พร้อมใช้งาน 1 รายการหลังผ่าน verify และ review |
| [Authorized delivery](skills/patpat-loop/playbooks/authorized-delivery.md) | Merge PR ที่ผ่านการยืนยันและผ่าน provider gate ของ repo เฉพาะเมื่อมีคำสั่ง land หรือ merge ชัดเจน |
| [Independent review](skills/patpat-loop/playbooks/independent-review.md) | ท้าทายการนำไปใช้และหลักฐานโดยไม่มีการแก้ไขไฟล์ |
| [Skill change](skills/patpat-loop/playbooks/skill-change.md) | เขียนหรือแก้ไขไฟล์ SKILL.md |
| [Behavioral evaluation](skills/patpat-loop/playbooks/behavioral-eval.md) | ทดสอบว่า skill ถูกกระตุ้นและทำงานถูกต้องตามพฤติกรรมหรือไม่ |
| [Project verifier](skills/patpat-loop/playbooks/project-verifier.md) | สร้างหรือซ่อมแซมตัวพิสูจน์เฉพาะของโปรเจกต์เทียบกับระบบจริง |
| [Learning](skills/patpat-loop/playbooks/learning.md) | เข้ารหัสความล้มเหลวที่เกิดซ้ำให้เป็นข้อจำกัดที่ทนทานและเล็กที่สุด |
| [Automation design](skills/patpat-loop/playbooks/automation-design.md) | ออกแบบระบบอัตโนมัติแบบ fail-closed สำหรับการเชื่อมต่อที่ระบุ |
| [Build a playable slice](skills/patpat-game-builder/playbooks/build-playable-slice.md) | ลูปเกมแบบ end-to-end ที่เล็กที่สุดสำหรับโจทย์ที่ระบุ |
| [Diagnose gameplay](skills/patpat-game-builder/playbooks/diagnose-gameplay.md) | ค้นหาสถานะแรกของเกมที่เบี่ยงเบนไปจากผลลัพธ์ที่คาดหวัง |
| [Verify a playthrough](skills/patpat-game-builder/playbooks/verify-playthrough.md) | พิสูจน์กฎ การควบคุม ภาพ และพฤติกรรมบนรันไทม์เป้าหมายแยกกัน |
| [Visual iteration](skills/patpat-game-builder/playbooks/visual-iteration.md) | ปรับปรุงงานภาพของเกมตามที่ร้องขอเทียบกับเงื่อนไขที่ถูกล็อกไว้ |

</details>

## การรันแบบต่อเนื่องและการประสานงาน (Durable runs and coordination)

[`patpat-run`](skills/patpat-run/SKILL.md) คือเครื่องจักรสถานะตามมาตรฐาน library ไม่ใช่เพียงรายการตรวจสอบที่เป็นข้อความธรรมดา ระบบจะปฏิเสธการ `ACT` หากไม่มีสัญญาการพิสูจน์ (proof contract), ปฏิเสธการ `REVIEW` หากไม่มีไฟล์หลักฐานที่ผูกกับเนื้อหาปัจจุบัน และปฏิเสธการเสร็จสิ้นงานหากไม่ผ่านการรีวิวอิสระ ข้อขัดข้องที่เกิดขึ้นซ้ำเดิมเป็นครั้งที่สามจะหยุดการรันทันที และงานสามารถกู้คืนได้แม้สูญเสีย context เนื่องจากสถานะถูกเก็บไว้ใน Git metadata แทนที่จะอยู่ในข้อความสนทนา

โปรแกรมที่ครอบคลุมหลาย PR จะใช้แผนงานแบบ checked JSON ที่ถูกตรวจสอบแล้ว โดยระบบจัดเก็บโปรแกรมจะตรวจสอบ dependencies, ไฟล์ที่ครอบครอง, พื้นผิวการพิสูจน์, หลักฐานที่ตรงกับ commit head ล่าสุด, เกตการรีวิว และสิทธิ์ในการส่งมอบ รวมถึงกั้นขอบเขตงานแต่ละชิ้นด้วย generation token และเมื่อส่วนที่ต้องพึ่งพาเปลี่ยน head หลักฐานปลายน้ำจะถือเป็นโมฆะทันที กฎการกั้นขอบเขตนี้ได้รับการตรวจสอบโมเดลด้วย TLA+ แล้ว ระบบจัดเก็บจะประสานสถานะเท่านั้น แต่ไม่ได้สร้าง Agent หรือมอบสิทธิ์อำนาจ ดูเพิ่มเติมที่ [durable runs](docs/guide/06-durable-runs.md) และ [earned parallelism](docs/guide/07-earned-parallelism.md)

บทบาทของ Agent สองบทบาทที่ช่วยรักษางานแบบคู่ขนานให้ซื่อตรง: `patpat-engineer` จะครอบครองงานย่อยส่วนหนึ่งและส่ง artifact กลับไปยังผู้รับผิดชอบการรวมระบบ และบทบาทผู้รีวิว ([`patpat-review`](skills/patpat-review/SKILL.md)) ซึ่งเป็นโหมดอ่านอย่างเดียวที่จะพยายามทำลายผลลัพธ์และหลักฐานให้ล้มเหลว ผู้ปฏิบัติงานย่อย (workers) จะไม่มีสิทธิ์ ship งาน ผู้ควบคุมหลัก (parent) เท่านั้นที่จะเป็นผู้ยืนยันผลลัพธ์ที่รวมแล้ว สำหรับ host-specific reviewer adapters มีระบุไว้ใน [capability map](docs/guide/capability-map.md#host-adapter-boundary)

## ขอบเขตที่ Patpat จะหยุด (Where Patpat stops)

Patpat ไม่เปลี่ยนความสามารถทางเทคนิคให้กลายเป็นสิทธิ์อำนาจ และไม่อ้างผลลัพธ์เกินกว่าที่หลักฐานแสดง:

- **Patpat มีหน้าที่ชี้แนะ แต่โฮสต์เป็นผู้บังคับใช้:** Patpat ประกอบด้วยคำสั่งและสคริปต์แบบ deterministic ข้อความไม่สามารถหยุดการแก้ไขโค้ดได้ มีเพียงเกตที่โฮสต์บังคับใช้เท่านั้นที่ทำได้ และปัจจุบันยังไม่มีเกตการแก้ไขโค้ดดังกล่าวส่งมอบมา
- **ยังไม่มีการอ้างผลการวัดประสิทธิภาพที่เป็นทางการ:** ยังไม่มีการเผยแพร่เกณฑ์มาตรฐานเปรียบเทียบการทำงานของ Agent ระหว่างการใช้และไม่ใช้ Patpat
- **ทำหน้าที่ประสานงาน แต่ไม่ได้รัน Agent เอง:** การ spawn, ตรวจสอบ, ปลุก, จัดตารางเวลา และยกเลิก worker เป็นหน้าที่ของโฮสต์
- **การเขียนแบบคู่ขนานต้องการสภาพแวดล้อมที่แยกขาด:** Arena, swarm และ autopilot ต้องการ Git worktree ที่แยกกัน หรือ sandbox ที่โฮสต์บังคับใช้ มิฉะนั้นจะถอยกลับมาทำงานแบบเรียงลำดับทีละงาน
- **การกระทำที่มีความเสี่ยงสูงจะหยุดพักรอการยืนยันเสมอ:** การ deploy ขึ้น production, การเผยแพร่แพ็กเกจ, การ force-push, การลบข้อมูล, การหมุนเวียน secrets และการเปลี่ยนแปลง auth หรือระบบเงินที่มีความเสี่ยง ต้องได้รับการอนุมัติอย่างชัดเจน และข้อผิดพลาดจริงของ CI จะบล็อกการ merge เสมอ
- **ไม่มีการตั้งค่าโมเดลล่วงหน้า (No model presets):** Worker จะสืบทอดโมเดลจาก parent เว้นแต่คุณหรือโฮสต์จะเป็นผู้เลือก ดูที่ [การเลือกโมเดล](skills/patpat-setup/SKILL.md#model-choice)

## แบบจำลองความเชื่อถือและสิทธิ์ความปลอดภัย (Trust model)

| คำถาม | คำตอบ |
| --- | --- |
| มีการเขียนข้อมูลลงที่ใดบ้าง? | ใน working tree ของคุณ สำหรับงานที่ร้องขอเท่านั้น สถานะการรันต่อเนื่องจะอยู่ใต้ Git metadata (`.git/patpat/` หรือ Git directory ของ worktree นั้นๆ) โหมดของเซสชันจะอยู่ใต้โฟลเดอร์ข้อมูล plugin ของโฮสต์ ส่วน `.patpat/context-graph.json` จะถูกสร้างขึ้นเฉพาะเมื่อคุณร้องขอแผนผัง workspace เท่านั้น |
| มีข้อมูลอะไรออกจากเครื่องบ้าง? | ไม่มีการส่ง telemetry ใดๆ การส่งมอบจะใช้คำสั่ง `git push` และเรียก GitHub ผ่าน CLI `gh` ของคุณ การรัน statechart ดั้งเดิมครั้งแรกจะดาวน์โหลด Java และ TLC ผ่าน mise ส่วนลิงก์ต้นทางของแผนภาพจะสอบถามไปยัง public GitHub API เฉพาะเมื่อคุณเลือกใช้งานเท่านั้น |
| มีอะไรที่คงอยู่ข้ามเซสชันบ้าง? | Hook ของโฮสต์จะกู้คืนโหมด Patpat หลังจาก resume เฉพาะจุดที่ [capability map](docs/guide/capability-map.md#sticky-mode-hook-status) บันทึกไว้ ส่วนที่อื่นๆ จะต้องเรียก Patpat ใหม่อีกครั้ง |
| ผลลัพธ์ได้รับการพิสูจน์อย่างไร? | บนพื้นผิวหลัก (authoritative surface): ผ่านแอปพลิเคชันจริง artifact จริง หรือชุดทดสอบจริง ไม่ใช่การสรุปความ และจำเป็นต้องมีการรีวิวอิสระก่อนการส่งมอบและสำหรับงานที่มีความเสี่ยงสูง |

## สิ่งที่ต้องใช้ (Requirements)

| การใช้งาน | สิ่งที่จำเป็นต้องมี |
| --- | --- |
| Core skills, hooks, durable runs, diagrams, saved model checks และการ replay | Python 3.11 ขึ้นไป, standard library เท่านั้น |
| Native statechart และ TLA+ model checking | Node 22.18 ถึง 22.x หรือ 23.6+ (หรือ Bun 1.1.5+, Deno 2+), Java 11+, และ TLC; โดย mise จะติดตั้ง Java และ TLC ในการรันครั้งแรก หรือกำหนดผ่าน `TLA2TOOLS` |
| การเรนเดอร์ statechart จากใบเสร็จที่บันทึกไว้ | Node 22.18 ถึง 22.x หรือ 23.6+ และรัน `npm ci` ใน `skills/patpat-statechart/scripts` |
| การส่งมอบงานและการตรวจสอบ PR | `git` และ `gh` CLI ที่ยืนยันตัวตนแล้ว |

## การขยายการทำงานและการตรวจสอบ (Extend and validate)

รันคำสั่งตรวจสอบข้อตกลงของ repository ด้วย `python3 scripts/validate.py --self-test` ดูรายการตรวจสอบเพิ่มเติมในระดับ local ได้ที่ [คู่มือการติดตั้ง](docs/guide/installing.md#verification) และ [CI workflow](https://github.com/goiltpatpat/patpat/blob/main/.github/workflows/validate.yml) เป็นรายการอ้างอิงหลัก สำหรับ [การขยายความสามารถของ Patpat](docs/guide/extending.md) และ [การขยายและประเมินผล](docs/guide/08-extend-and-evaluate.md) จะอธิบายวิธีการเพิ่ม skill หรือ playbook รวมถึงวิธีทดสอบการจัดเส้นทางและพฤติกรรม หลักการทำงานจะอยู่ใน [`skills/patpat-loop/principles/`](skills/patpat-loop/principles/) ซึ่งเป็นเอกสารอ้างอิง ไม่ใช่ skill ที่ถูกค้นพบโดยตรง

## ความปลอดภัย การสนับสนุน และการมีส่วนร่วม (Security, support, and contributions)

รายงานช่องโหว่ด้านความปลอดภัยอย่างเป็นส่วนตัวผ่าน [นโยบายความปลอดภัย (security policy)](https://github.com/goiltpatpat/patpat/security/policy) ห้ามใส่ secrets, log ส่วนตัว หรือรายละเอียดของช่องโหว่ใน public issue โดยตรง รองรับ branch `main` ปัจจุบันและ release ที่ถูกติดแท็กล่าสุด การเปิด Pull Request ควรจำกัดขอบเขตให้กระชับและแนบหลักฐานเชิงประจักษ์สำหรับการเปลี่ยนแปลงที่เสนอมาเสมอ

## สัญญาอนุญาต (License)

MIT.
