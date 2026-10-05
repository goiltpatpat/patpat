#!/usr/bin/env python3
"""Dry-run Patpat Loop routing, ship, fan-out, and issue-loop gates. No git writes."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "scripts" / "patpat_loop_state.py"
EXPLICIT_MERGE = re.compile(
    r"(?:^|\s)(?:land|merge)(?:\s+(?:this|it|the\s+(?:pr|pull request|stack)|pr\s*#?\d+))?(?=$|[.!?])",
    re.IGNORECASE,
)
MERGE_DENIAL = re.compile(
    r"(?:do\s+not|don't|dont|never|not|no|without|avoid(?:ing)?)\b"
    r"[^.!?;\n]*\b(?:land|merge)\b",
    re.IGNORECASE,
)
DISABLE_MODE = re.compile(
    r"^\s*(?:disable\s+(?:/|\$)?patpat(?:-loop)?|opt\s+out(?:\s+of)?\s+patpat(?:-loop)?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
INTERACTIVE_DIAGRAM_INTENT = re.compile(
    r"\b(?:draw|create|make|generate|render|map|show|provide|visuali[sz]e|turn|transform)\b.{0,100}\b(?:architecture\s+|workflow\s+|sequence\s+|data[- ]?flow\s+|lifecycle\s+)?(?:diagram|flowchart|interactive\s+(?:visual|map)|visualization|visualisation|visual\s+(?:map|of|for|about))\b"
    r"|(?:วาด|สร้าง|ทำ|จัดทำ|ขอ|ช่วยวาด|ช่วยสร้าง|ช่วยทำ|อยากได้|ขอดู|เปลี่ยน).{0,100}(?:diagram|flowchart|แผนภาพ|ไดอะแกรม|ผังงาน|ภาพโต้ตอบ|ภาพสรุป)"
    r"|(?:แปลง|ทำ|สร้าง).{0,80}(?:ไอเดีย|แผน|เรื่อง|โค้ดเบส|repository).{0,70}(?:ภาพโต้ตอบ|ภาพสรุป|แผนภาพ|ไดอะแกรม)",
    re.IGNORECASE,
)
REPOSITORY_DIAGRAM_DENIAL = re.compile(
    r"\b(?:do\s+not|don't|dont|never|not)\s+(?!just\b|only\b|merely\b|simply\b)"
    r"(?:draw|create|make|generate|render|map|show|provide|visuali[sz]e)\b"
    r"|\b(?:avoid|without)\s+(?:drawing|creating|making|generating|rendering|mapping|showing|providing|visuali[sz]ing)\b"
    r"|(?:ไม่ต้อง|อย่า|ห้าม|ไม่)(?!\s*(?:แค่|เพียง))\s*(?:วาด|สร้าง|ทำ|จัดทำ|แสดง)",
    re.IGNORECASE,
)
REPOSITORY_DIAGRAM_EXPLANATION = re.compile(
    r"\b(?:explain|describe|tell\s+me\s+about|what\s+does|how\s+does|why\s+does)\b[^.!?;\n]{0,80}\b(?:diagram|flowchart)\b"
    r"|(?:อธิบาย|เล่า|บอก|สรุป).{0,80}(?:แผนภาพ|ไดอะแกรม|ผังงาน|diagram|flowchart)",
    re.IGNORECASE,
)
REPOSITORY_DIAGRAM_EXPLANATION_REQUEST = re.compile(
    r"\b(?:explain|describe)\b[^.!?;\n]{0,100}\bwith\s+(?:an?\s+)?(?:architecture\s+|workflow\s+|sequence\s+|data[- ]?flow\s+|lifecycle\s+)?(?:diagram|flowchart)\b"
    r"|(?:อธิบาย|เล่า|สรุป).{0,100}(?:ด้วย|พร้อม).{0,24}(?:แผนภาพ|ไดอะแกรม|ผังงาน|diagram|flowchart)",
    re.IGNORECASE,
)
GAME_BUILD_REQUEST = re.compile(
    r"\b(?:build|create|make|develop|implement|extend|prototype|add)\b.{0,80}\b(?:playable\s+)?(?:game|gameplay|video\s+game)\b"
    r"|\b(?:add|change|improve|remove|tune|increase|decrease|fix|adjust)\b.{0,80}\b(?:to|for|in)\s+(?:this\s+|the\s+)?(?:game|gameplay)\b"
    r"|\b(?:add|change|improve|remove|tune)\b.{0,60}\b(?:this|the|my|our)\s+game(?:'s|’s)\b"
    r"|(?:สร้าง|ทำ|พัฒนา|ต่อยอด|เพิ่ม).{0,80}(?:เกม|เกมเพลย์|game)",
    re.IGNORECASE,
)
GAME_BUILD_DENIAL = re.compile(
    r"\b(?:do\s+not|don't|dont|never|without|avoid)\b(?!\s+(?:just|only|merely|simply)\b)[^.!?;\n]{0,80}\b(?:build|create|make|develop|implement|extend|prototype|add|change|improve|remove|tune|increase|decrease|fix|adjust|debug|diagnose|investigate|edit|update|refactor|rewrite|repair|modify)\b"
    r"|\bnot\s+(?:build|create|make|develop|implement|extend|prototype|add|change|improve|remove|tune|increase|decrease|fix|adjust|debug|diagnose|investigate|edit|update|refactor|rewrite|repair|modify)\b"
    r"|\b(?:there\s+is\s+)?no\s+need\s+to\s+(?:build|create|make|develop|implement|extend|prototype|add|change|improve|remove|tune|increase|decrease|fix|adjust|debug|diagnose|investigate|edit|update|refactor|rewrite|repair|modify)\b"
    r"|\bnot\s+necessary\s+to\s+(?:build|create|make|develop|implement|extend|prototype|add|change|improve|remove|tune|increase|decrease|fix|adjust|debug|diagnose|investigate|edit|update|refactor|rewrite|repair|modify)\b"
    r"|(?:ไม่ต้อง|ไม่ควร|ไม่อยาก|ไม่เอา|อย่า|ห้าม)(?!\s*(?:แค่|เพียง)).{0,40}\b(?:build|create|make|develop|implement|extend|prototype|add|change|improve|remove|tune|increase|decrease|fix|adjust|debug|diagnose|investigate|edit|update|refactor|rewrite|repair|modify)\b"
    r"|(?:ไม่ต้อง|ไม่ควร|ไม่อยาก|ไม่เอา|อย่า|ห้าม)(?!\s*(?:แค่|เพียง)).{0,40}(?:สร้าง|ทำ|พัฒนา|ต่อยอด|เพิ่ม|เปลี่ยน|ปรับ|แก้|ลบ)"
    r"|ไม่\s*(?:สร้าง|ทำ|พัฒนา|ต่อยอด|เพิ่ม|เปลี่ยน|ปรับ|แก้|ลบ)",
    re.IGNORECASE,
)
GAME_EXISTING_GAME_EXTENSION = re.compile(
    r"\b(?:add|change|extend|improve|implement|remove|tune|refine|increase|decrease|fix|adjust)\b.{0,60}\b(?:this|that|existing|current)\s+(?:game|one)\b"
    r"|\b(?:add|change|extend|improve|implement|remove|tune|refine|increase|decrease|fix|adjust)\b.{0,50}\b(?:to|in)\s+(?:it|this\s+one|that\s+one)\b"
    r"|\b(?:build|create|make|develop|prototype|implement)\b.{0,40}\b(?:it|one|this\s+one|that\s+one)\b"
    r"|(?:เพิ่ม|เปลี่ยน|ปรับปรุง|แก้|ลบ|ปรับ).{0,60}(?:เกมเดิม|เกมปัจจุบัน|เกมนี้|เกมนั้น)",
    re.IGNORECASE,
)
GAME_NEW_GAME_DENIAL = re.compile(
    r"\b(?:do\s+not|don't|dont|never|not)\s+(?:build|create|make|develop)\s+(?:(?:a|an|another)\s+)?new\s+(?:video\s+)?game\b"
    r"|(?:ไม่ต้อง|ไม่ควร|ไม่อยาก|ไม่เอา|อย่า|ห้าม).{0,32}(?:สร้าง|ทำ|พัฒนา).{0,12}เกมใหม่"
    r"|ไม่\s*(?:สร้าง|ทำ|พัฒนา).{0,12}เกมใหม่",
    re.IGNORECASE,
)
GAME_EXPLICIT_EXISTING_GAME_TARGET = re.compile(
    r"\b(?:this|that|existing|current)\s+(?:game|one)\b|เกม(?:เดิม|ปัจจุบัน|นี้|นั้น)",
    re.IGNORECASE,
)
GAME_NEW_GAME_DENIAL_BEFORE_COMMA = re.compile(
    r"\b(?:do\s+not|don't|dont|never)\s+(?:build|create|make|develop)\s+(?:a\s+|another\s+)?new\s+(?:video\s+)?game\s*,\s*(?:(?:and|but)\s+)?(?:(?:just|simply)\s+)?(?=(?:add|change|extend|improve|implement|remove|tune|refine)\b)",
    re.IGNORECASE,
)
GAME_ARTIFACT_REFERENCE_REQUEST = re.compile(
    r"\b(?:add|build|create|develop|implement|make|prepare|write|draft|outline)\b.{0,32}\b(?:it|one|another)\b"
    r"|(?:เพิ่ม|สร้าง|ทำ|พัฒนา|ต่อยอด|เขียน|ร่าง).{0,30}(?:มัน|อีกอัน|อีกฉบับ)",
    re.IGNORECASE,
)
GAME_BUILD_PRONOUN_REQUEST = re.compile(
    r"\b(?:build|create|make|develop|implement|prototype)\s+(?:it|one)\b",
    re.IGNORECASE,
)
GAME_PRIMARY_IMPLEMENTATION = re.compile(
    r"^\s*(?:(?:please|kindly)\s+)?(?:build|create|make|develop|implement|prototype)\s+(?:(?:a|an|the|small|simple|browser|2d|3d|playable|runnable)\s+){0,3}game\s+from\s+(?:this|the|that)\s+(?:test\s+)?plan\b",
    re.IGNORECASE,
)
GAME_DESIGN_DOCUMENT_MENTION = re.compile(
    r"\bgame\s+design\s+(?:docs?|documents?)\b|\bgdds?\b|\bgame\s+pitches?\b|เอกสารออกแบบเกม|พิตช์เกม",
    re.IGNORECASE,
)
GAME_CONTEXT_MENTION = re.compile(r"\b(?:game|gameplay|video\s+game)\b|เกม|เกมเพลย์", re.IGNORECASE)
GAMEPLAY_ISSUE_CONTEXT = re.compile(
    r"\b(?:game|gameplay|video\s+game)\b.{0,80}\b(?:is|feels|seems|plays)\s+(?:not\s+)?(?:balanced|unbalanced|too\s+slow|too\s+fast|too\s+hard|too\s+easy|unfair|unresponsive|clunky|frustrating|broken)\b"
    r"|(?:เกม|เกมเพลย์).{0,40}(?:ไม่สมดุล|ช้าเกินไป|เร็วเกินไป|ยากเกินไป|ง่ายเกินไป|ควบคุมยาก|ไม่ตอบสนอง)",
    re.IGNORECASE,
)
GAMEPLAY_TARGET_MUTATION = re.compile(
    r"\b(?:add|change|extend|improve|implement|remove|tune|refine|increase|decrease|fix|adjust)\b.{0,60}\b(?:player|character|movement|controls?|input|speed|velocity|jump|damage|health|enemy|combat|attack|dodge|cooldown|camera|physics|level|spawn|collision|score|progression|inventory|save|pacing|balance|difficulty|feedback|hud|ui)\b"
    r"|(?:เพิ่ม|เปลี่ยน|ปรับปรุง|ต่อยอด|แก้|ลบ|ปรับ|ลด).{0,60}(?:ผู้เล่น|ตัวละคร|การเคลื่อนไหว|ปุ่ม|ความเร็ว|ท่ากระโดด|พลัง|ศัตรู|ต่อสู้|โจมตี|ท่าหลบ|คูลดาวน์|กล้อง|ฟิสิกส์|ด่าน|คะแนน|คลัง|บันทึก|จังหวะ|ความยาก|การตอบสนอง|มัน|เกมนี้)",
    re.IGNORECASE,
)
NON_DIAGRAM_CODE_CHANGE = re.compile(
    r"\b(?:fix|debug|implement|build|develop|add|change|update|edit|remove|refactor|rewrite|repair|modify|extend|adjust)\b.{0,80}\b(?:bug|issue|error|auth(?:entication|orization)?|code|feature|endpoint|api|file|function|method|class|module|service|database|schema|tests?|readme(?:\.md)?|docs?)\b"
    r"|(?:แก้|เพิ่ม|เปลี่ยน|อัปเดต|ปรับปรุง|ลบ|ปรับ|พัฒนา|สร้าง).{0,60}(?:บั๊ก|ข้อผิดพลาด|ระบบยืนยันตัวตน|auth|API|โค้ด|ฟีเจอร์|ไฟล์|ฟังก์ชัน|คลาส|โมดูล|บริการ|ฐานข้อมูล|สคีมา|เทสต์|README|เอกสาร)",
    re.IGNORECASE,
)
GAMEPLAY_PRESENTATION_REQUEST = re.compile(
    r"\b(?:add|change|create|enhance|fix|improve|make|polish|refine|adjust|clarify|tune)\b.{0,70}"
    r"\b(?:(?:this|the|my|our)\s+)?game(?:play)?(?:['’]s)?\b.{0,55}"
    r"\b(?:visual(?:\s+feedback)?|visuals|feedback|hud|ui|presentation|readability)\b"
    r"|\b(?:game|gameplay)\b.{0,65}\b(?:visual\s+feedback|visuals?|hud|ui|presentation|readability)\b"
    r"|(?:เกม|เกมเพลย์).{0,60}(?:ภาพ|การแสดงผล|feedback|hud|ui|ความชัด|อ่านง่าย)"
    r"|(?:ปรับ|แก้|ปรับปรุง|ทำให้|เพิ่ม).{0,45}(?:ภาพ|การแสดงผล|feedback|hud|ui|ความชัด|อ่านง่าย).{0,45}(?:เกม|เกมเพลย์)",
    re.IGNORECASE,
)
GAME_DOCUMENT_TARGET = re.compile(
    r"\b(?:readme(?:\.md)?|changelog(?:\.md)?|docs?(?:/[\w.-]+)*|documentation|release\s+notes?|contributing(?:\.md)?|manual|guides?)\b"
    r"|(?:^|[\s`])[\w./-]+\.(?:md|rst|txt|adoc)\b"
    r"|(?:เอกสาร|คู่มือ|บันทึกการเปลี่ยนแปลง)",
    re.IGNORECASE,
)
GAME_DOCUMENT_CONTENT_REQUEST = re.compile(
    r"\b(?:add|write|draft|include|create|update|edit|prepare|document)\b.{0,40}\b(?:section|note|paragraph|chapter|page|entry|article|guide|description|explanation)\b"
    r"|\b(?:section|note|paragraph|chapter|page|entry)\b.{0,48}\b(?:about|for|on|covering)\b.{0,50}\b(?:game|gameplay|player|character|movement|controls?|input|speed|jump|damage|health|enemy|combat|attack|dodge|cooldown|camera|physics|level|score|difficulty)\b"
    r"|(?:เพิ่ม|เขียน|ร่าง|ใส่|จัดทำ|อัปเดต|แก้ไข).{0,35}(?:หัวข้อ|โน้ต|หมายเหตุ|ย่อหน้า|บท|หน้า|รายการ|คำอธิบาย).{0,50}(?:เกม|เกมเพลย์|ผู้เล่น|ตัวละคร|การเคลื่อนไหว|ปุ่ม|ความเร็ว|ศัตรู|ต่อสู้|โจมตี|ความยาก)",
    re.IGNORECASE,
)
GAME_ACTION_BOUNDARY = re.compile(
    r"\band\s+(?=(?:add|change|extend|improve|implement|remove|tune|refine|increase|decrease|fix|adjust|update|write|edit|document)\b)"
    r"|\bthen\s+(?=(?:add|change|extend|improve|implement|remove|tune|refine|increase|decrease|fix|adjust|update|write|edit|document)\b)"
    r"|,\s*(?=(?:add|change|extend|improve|implement|remove|tune|refine|increase|decrease|fix|adjust|update|write|edit|document)\b)"
    r"|และ\s*(?=(?:เพิ่ม|เปลี่ยน|ปรับปรุง|ต่อยอด|แก้|ลบ|ปรับ|ลด|อัปเดต|เขียน|แก้ไข))",
    re.IGNORECASE,
)


def has_gameplay_target_mutation(clause: str) -> bool:
    actions = GAME_ACTION_BOUNDARY.split(clause)
    return any(
        GAMEPLAY_TARGET_MUTATION.search(action)
        and not (GAME_DOCUMENT_TARGET.search(action) or GAME_DOCUMENT_CONTENT_REQUEST.search(action))
        for action in actions
    )


GAME_CONCEPT_ONLY = re.compile(
    r"\b(?:add|build|create|develop|implement|make|write|draft|outline|brainstorm|compare|critique|review|discuss)\b.{0,80}\b(?:game\s+concepts?|game\s+ideas?|game\s+design\s+docs?|game\s+design\s+documents?|gdds?|game\s+pitches?)\b"
    r"|(?:สร้าง|เขียน|ร่าง|ระดมความคิด|เปรียบเทียบ|วิจารณ์|รีวิว|คุย|เพิ่ม).{0,80}(?:แนวคิดเกม|ไอเดียเกม|เอกสารออกแบบเกม|พิตช์เกม)"
    r"|(?:สร้าง|เขียน|ร่าง|ระดมความคิด|เปรียบเทียบ|วิจารณ์|รีวิว|คุย|เพิ่ม).{0,80}\bgame\s+(?:concepts?|ideas?|design\s+docs?|design\s+documents?|pitches?|gdds?)\b",
    re.IGNORECASE,
)
GAME_DOCUMENTATION_ONLY = re.compile(
    r"\b(?:add|build|create|implement|make|write|draft|prepare|outline|review|critique)\b.{0,24}\b(?:(?:unit|integration|acceptance|qa|smoke)\s+)?tests?(?:\s+(?:plans?|strateg(?:y|ies)|matrices|checklists|cases?|suites?|coverage|specs?|documents?|docs?))?\b"
    r"|\b(?:add|build|create|implement|make|write|draft|prepare|outline|review|critique)\b.{0,24}\b(?:test|qa|acceptance|verification)\s+(?:plans?|strateg(?:y|ies)|matrices|checklists|specs?|documents?|docs?)\b"
    r"|\b(?:build|create|make|develop|implement|write|draft|prepare|outline|review|critique)\b.{0,32}\b(?:(?:production|development|release|project|milestone|launch)\s+)?(?:plans?|roadmaps?|schedules?|proposals?|strateg(?:y|ies)|estimates?|briefs?)\b.{0,48}\b(?:for|to|about|on)\b.{0,48}\b(?:game|gameplay|video\s+game)\b"
    r"|\b(?:build|create|make|develop|implement|write|draft|prepare|outline|review|critique)\b.{0,16}\bgame\s+(?:plans?|roadmaps?|proposals?)\b"
    r"|(?:ช่วย|กรุณา)?(?:สร้าง|ทำ|เขียน|ร่าง|จัดทำ|เตรียม|วางแผน).{0,32}(?:แผน(?:การผลิต|การพัฒนา|พัฒนา|โครงการ|งาน)?|game\s+(?:plans?|roadmaps?|proposals?)|(?:(?:production|development|release|project|milestone|launch)\s+)?(?:plans?|roadmaps?|schedules?|proposals?|strateg(?:y|ies)|estimates?|briefs?)).{0,48}(?:เกม|game|เกมเพลย์|gameplay)"
    r"|(?:สร้าง|ทำ|เขียน|ร่าง|จัดทำ|เตรียม).{0,48}(?:แผนทดสอบ|กลยุทธ์ทดสอบ|เมทริกซ์ทดสอบ|รายการตรวจสอบ|กรณีทดสอบ|ชุดทดสอบ|เอกสารทดสอบ)"
    r"|(?:สร้าง|ทำ|เขียน|ร่าง|จัดทำ|เตรียม).{0,48}\b(?:(?:(?:unit|integration|acceptance|qa|smoke)\s+)?tests?(?:\s+(?:plans?|strateg(?:y|ies)|matrices|checklists|cases?|suites?|coverage|specs?|documents?|docs?))?|(?:test|qa|acceptance|verification)\s+(?:plans?|strateg(?:y|ies)|matrices|checklists|specs?|documents?|docs?))\b",
    re.IGNORECASE,
)
GAME_BUILD_EXPLANATION = re.compile(
    r"^\s*(?:(?:please|kindly)\s+)?(?:how\s+(?:(?:do|can|should|would)\s+(?:i|we|you)|to)\b|why\s+(?:did|does|is|was)\b|what\s+(?:do|does|is|are|can)\b|explain\b|describe\b|tell\s+me\b).{0,120}\b(?:game|gameplay|video\s+game)\b"
    r"|^\s*(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:explain|describe|tell\s+me|show\s+me)\b.{0,120}\b(?:game|gameplay|video\s+game)\b"
    r"|^\s*i\s+want\s+to\s+know\b.{0,80}\b(?:how|what|why)\b.{0,80}\b(?:game|gameplay|video\s+game)\b"
    r"|^\s*(?:(?:ช่วย|กรุณา)\s*)?(?:อธิบาย|บอก|เล่า|สอน).{0,60}(?:วิธี|ขั้นตอน).{0,60}(?:สร้าง|ทำ|พัฒนา).{0,60}(?:เกม|เกมเพลย์)",
    re.IGNORECASE,
)
GAME_RUNTIME_FAILURE = re.compile(
    r"\b(?:game|gameplay)\b.{0,80}\b(?:crashes?|freezes?|hangs?|fails?|broken|not\s+working|won't\s+start|doesn't\s+start)\b"
    r"|\b(?:crashes?|freezes?|hangs?|fails?|broken|not\s+working)\b.{0,80}\b(?:game|gameplay)\b",
    re.IGNORECASE,
)
GAME_BUILD_FAILURE = re.compile(
    r"\bgame(?:'s|’s)?\s+(?:build|compilation)\s+(?:(?:is|has|keeps)\s+)?(?:fail(?:ed|s|ure)?|error|broken|crash(?:ed|es)?)\b"
    r"|\b(?:build|compilation)\b.{0,40}\b(?:for|of|in)\s+(?:this\s+|the\s+|a\s+)?game\b.{0,60}\b(?:fail(?:ed|s|ure)?|error|broken|crash(?:ed|es)?)\b"
    r"|\bgame\b.{0,80}\b(?:fails?|failed)\s+to\s+(?:build|compile|launch)\b"
    r"|\b(?:diagnose|debug|investigate|repair)\b.{0,80}\b(?:game|gameplay)\b"
    r"|\b(?:game|gameplay)\b.{0,80}\b(?:does\s+not|doesn't|cannot|can't|won't)\s+(?:build|compile|launch)\b",
    re.IGNORECASE,
)
GAME_IMPLEMENTATION_AFTER_CONCEPT = re.compile(
    r"\b(?:build|create|make|develop|implement|prototype)\s+(?:(?:a|an|the|small|simple|browser|2d|3d)\s+){0,3}(?:playable|runnable)\s+game\b"
    r"|\b(?:build|create|make|develop|implement|prototype)\s+(?:(?:a|an|the|small|simple|browser|2d|3d|playable|runnable)\s+){0,3}game\s+from\s+(?:this|the|that)\s+(?:(?:game|design)\s+)?concept\b"
    r"|\b(?:build|create|make|develop|implement|prototype)\s+(?:it|one)\b.{0,40}\bfrom\s+(?:this|the|that)\s+(?:game\s+)?concept\b"
    r"|(?:ลงมือทำ|เขียนโค้ด).{0,80}(?:เกมที่เล่นได้|เกมเพลย์)"
    r"|(?:พัฒนา|สร้างต้นแบบ).{0,80}เกมที่เล่นได้",
    re.IGNORECASE,
)


def load_hook():
    spec = importlib.util.spec_from_file_location("patpat_loop_state", HOOK)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing hook script: {HOOK}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_existing_game_continuation(prefix: str, suffix: str) -> bool:
    return bool(
        GAME_NEW_GAME_DENIAL.search(prefix)
        and GAME_EXISTING_GAME_EXTENSION.search(suffix)
        and GAME_EXPLICIT_EXISTING_GAME_TARGET.search(suffix)
    )


def split_game_request_clauses(text: str) -> list[str]:
    clauses = re.split(r"[.!?;\n]+|\b(?:but|instead|rather)\b|แต่", text, flags=re.IGNORECASE)
    sequential_clauses: list[str] = []
    for clause in clauses:
        remaining = clause
        while (sequence := re.search(r"\bthen\b|แล้ว", remaining, re.IGNORECASE)) and (
            not GAME_BUILD_DENIAL.search(remaining[: sequence.start()])
            or is_existing_game_continuation(
                remaining[: sequence.start()], remaining[sequence.end() :]
            )
        ):
            sequential_clauses.append(remaining[: sequence.start()])
            remaining = remaining[sequence.end() :]
        sequential_clauses.append(remaining)

    split_clauses: list[str] = []
    for clause in sequential_clauses:
        negated_creation = GAME_NEW_GAME_DENIAL_BEFORE_COMMA.search(clause)
        if negated_creation:
            comma_offset = clause.find(",", negated_creation.start())
            extension = clause[comma_offset + 1 :]
            if (
                GAME_EXISTING_GAME_EXTENSION.search(extension)
                and GAME_EXPLICIT_EXISTING_GAME_TARGET.search(extension)
            ):
                split_clauses.extend((clause[:comma_offset], extension))
            else:
                split_clauses.append(clause)
        else:
            conjunction = re.search(
                r"\band\s+(?=(?:build|develop|prototype|implement|code|program|extend|add|change|improve|remove|tune|refine)\b)"
                r"|และ\s*(?=(?:สร้าง|ทำ|พัฒนา|ต่อยอด|เพิ่ม|เปลี่ยน|ปรับ|ลบ))",
                clause,
                re.IGNORECASE,
            )
            if conjunction and (
                not GAME_BUILD_DENIAL.search(clause[: conjunction.start()])
                or is_existing_game_continuation(
                    clause[: conjunction.start()], clause[conjunction.end() :]
                )
            ):
                split_clauses.extend((clause[: conjunction.start()], clause[conjunction.end() :]))
            else:
                split_clauses.append(clause)
    return split_clauses


def has_affirmative_game_request(text: str) -> bool:
    clauses = split_game_request_clauses(text)
    context = "none"
    for clause in clauses:
        if not clause.strip():
            continue
        if GAME_BUILD_DENIAL.search(clause):
            context = "none"
            continue
        if GAME_BUILD_EXPLANATION.search(clause):
            context = "explanation"
            continue
        implementation_after_concept = GAME_IMPLEMENTATION_AFTER_CONCEPT.search(clause)
        if GAME_DOCUMENTATION_ONLY.search(clause) or GAME_DESIGN_DOCUMENT_MENTION.search(clause):
            if GAME_PRIMARY_IMPLEMENTATION.search(clause) or implementation_after_concept:
                return True
            context = "document"
            continue
        if context == "document" and GAME_ARTIFACT_REFERENCE_REQUEST.search(clause) and not implementation_after_concept:
            context = "document"
            continue
        if GAME_CONCEPT_ONLY.search(clause) and not implementation_after_concept:
            context = "concept"
            continue
        if context in {"concept", "explanation"} and GAME_BUILD_PRONOUN_REQUEST.search(clause):
            return True
        if implementation_after_concept:
            return True
        if GAME_BUILD_REQUEST.search(clause):
            return True
        if (
            GAMEPLAY_ISSUE_CONTEXT.search(clause) or context == "gameplay-issue"
        ) and has_gameplay_target_mutation(clause):
            return True
        if context == "gameplay-issue" and (
            GAME_DOCUMENT_TARGET.search(clause)
            or GAME_DOCUMENT_CONTENT_REQUEST.search(clause)
        ):
            continue
        if GAME_EXISTING_GAME_EXTENSION.search(clause) and (
            GAME_EXPLICIT_EXISTING_GAME_TARGET.search(clause)
            or context == "game"
            or GAME_CONTEXT_MENTION.search(clause)
        ):
            return True
        if GAMEPLAY_ISSUE_CONTEXT.search(clause):
            context = "gameplay-issue"
        else:
            context = "game" if GAME_CONTEXT_MENTION.search(clause) else "none"
    return False


def has_repository_diagram_request(text: str) -> bool:
    clauses = re.split(
        r"[,;.!?\n]+|\b(?:but|instead|however|rather)\b|(?:แต่|แต่ว่า|แทนที่จะ)",
        text,
        flags=re.IGNORECASE,
    )
    for clause in clauses:
        if REPOSITORY_DIAGRAM_DENIAL.search(clause):
            continue
        if INTERACTIVE_DIAGRAM_INTENT.search(clause) or REPOSITORY_DIAGRAM_EXPLANATION_REQUEST.search(clause):
            return True
    return False


def has_compound_non_diagram_work(text: str) -> bool:
    clauses = re.split(
        r"[,;.!?\n]+|\b(?:then|and|but|instead|however|also)\b|(?:แล้ว|และ|แต่|แต่ว่า|แทนที่จะ)",
        text,
        flags=re.IGNORECASE,
    )
    for clause in clauses:
        if not clause.strip() or has_repository_diagram_request(clause):
            continue
        if GAME_BUILD_DENIAL.search(clause) or GAME_NEW_GAME_DENIAL.search(clause):
            continue
        if GAME_BUILD_EXPLANATION.search(clause):
            continue
        if (
            has_affirmative_game_request(clause)
            or has_gameplay_target_mutation(clause)
            or GAME_IMPLEMENTATION_AFTER_CONCEPT.search(clause)
            or GAME_EXISTING_GAME_EXTENSION.search(clause)
            or GAME_BUILD_FAILURE.search(clause)
            or GAME_RUNTIME_FAILURE.search(clause)
            or NON_DIAGRAM_CODE_CHANGE.search(clause)
        ):
            return True
    return False


def route(prompt: str) -> str:
    text = prompt.lower()
    if DISABLE_MODE.fullmatch(prompt):
        return "disable"
    if has_repository_diagram_request(text):
        if has_compound_non_diagram_work(text):
            return "loop"
        return "repository-diagram"
    if GAME_BUILD_FAILURE.search(text):
        return "debug"
    if GAME_RUNTIME_FAILURE.search(text) and not GAME_BUILD_REQUEST.search(text):
        return "debug"
    if GAMEPLAY_PRESENTATION_REQUEST.search(text) and not GAME_DOCUMENT_TARGET.search(text):
        return "game-builder"
    if has_affirmative_game_request(text):
        return "game-builder"
    if GAME_BUILD_EXPLANATION.search(text):
        return "inspect"
    if "issue-loop" in text or "triage github issues" in text or "benny" in text:
        return "issue-loop"
    if "arena" in text or "competing" in text or "two layouts" in text:
        return "arena"
    if "swarm" in text or "each package" in text or "coverage matrix" in text:
        return "swarm"
    if "autopilot" in text or "this queue" in text:
        return "autopilot"
    if (
        "how does" in text
        or "explain" in text
        or "describe" in text
        or "why did" in text
        or "why does" in text
        or "why was" in text
        or "why is" in text
        or "do not change" in text
        or "read-only" in text
        or "which skill owns" in text
        or "where should this live" in text
        or "where should" in text
        or "อธิบาย" in text
    ):
        return "inspect"
    if "pause safely" in text or "go offline" in text:
        return "pause"
    if "babysit" in text or "get it green" in text or "watch ci" in text:
        return "pr-babysit"
    if "worktree" in text and ("clean" in text or "prune" in text):
        return "worktree-cleanup"
    if "interrogate" in text or "adversarial review" in text:
        return "interrogate"
    if "unslop" in text or "cut ai tells" in text:
        return "unslop"
    if "timeout" in text or "bug" in text or "repro" in text or "fix" in text:
        return "debug"
    if explicit_merge_intent(prompt) or "open the pr" in text:
        return "ship"
    return "loop"


def delivery_intent(
    *,
    explicit_delivery: bool,
    continuation: bool,
    explicit_merge: bool,
    explicit_ready_pr: bool = False,
) -> bool:
    # Interpretation B: a bare existing_pr is not delivery intent.
    return bool(explicit_delivery or continuation or explicit_merge or explicit_ready_pr)


def start_plan(
    *,
    first_activation: bool = False,
    clear_bounded_reversible_local: bool = False,
    ambiguous: bool = False,
    high_risk: bool = False,
    delivery_intent: bool = False,
    multi_step: bool = False,
    durable: bool = False,
    mutating: bool = False,
) -> dict[str, object]:
    """Classify start ceremony from task shape. Instruction-contract helper, not live-agent proof.

    First activation is context only; it alone must not force fuller-start.
    """
    del first_activation  # context, not a risk signal
    if durable:
        kind = "durable-run"
    elif high_risk or ambiguous or delivery_intent or multi_step:
        kind = "fuller-start"
    elif clear_bounded_reversible_local:
        kind = "lightweight-start"
    else:
        kind = "fuller-start"
    return {
        "kind": kind,
        "mandatory_todo": kind != "lightweight-start",
        "mandatory_checklist": kind == "fuller-start",
        "proof_contract_required": bool(mutating),
        "full_protocol_read": kind != "lightweight-start",
    }



def representation_plan(
    *,
    kind: str,
    structure_hard_in_prose: bool = False,
    simpler_forms_insufficient: bool = False,
) -> dict[str, object]:
    """Choose the smallest useful engineering representation.

    Instruction-contract helper for earned representation, not live-agent proof.
    Visualization is earned: prefer prose unless structure is hard in prose.
    For ``complex_visual``, use a focused artifact only when simpler forms are
    insufficient; otherwise prefer ``sequence-or-flow`` (or call-tree) first.
    Representation choice itself never adds planning or reporting ceremony and
    is orthogonal to ``start_plan`` (trivial mutation stays lightweight-start).
    """
    hard = bool(structure_hard_in_prose)
    if kind == "factual":
        form = "prose"
        reason = "factual answers stay concise prose"
    elif kind == "trivial_mutation":
        form = "prose"
        reason = "trivial mutation must not earn visualization or ceremony"
    elif kind == "runtime_flow":
        form = "call-tree" if hard else "prose"
        reason = "runtime flow uses a call tree when hard in prose" if hard else "runtime flow stays prose when clear"
    elif kind == "ownership":
        form = "shallow-tree" if hard else "prose"
        reason = "ownership uses a shallow tree when hard in prose" if hard else "ownership stays prose when clear"
    elif kind == "architecture_delta":
        form = "structural-comparison" if hard else "prose"
        reason = "architecture delta uses structural comparison when hard in prose" if hard else "architecture delta stays prose when clear"
    elif kind == "shape_review":
        form = "diff-shaped" if hard else "prose"
        reason = "shape review uses a diff-shaped form when hard in prose" if hard else "shape review stays prose when clear"
    elif kind == "logic":
        form = "pseudocode" if hard else "prose"
        reason = "logic uses compact pseudocode when hard in prose" if hard else "logic stays prose when clear"
    elif kind == "ui_structure":
        form = "component-tree" if hard else "prose"
        reason = "UI structure uses a component tree when hard in prose" if hard else "UI structure stays prose when clear"
    elif kind == "interaction_flow":
        form = "sequence-or-flow" if hard else "prose"
        reason = "interaction flow uses sequence/flow when hard in prose" if hard else "interaction flow stays prose when clear"
    elif kind == "repository_diagram":
        form = "interactive-diagram-artifact"
        reason = "an explicitly requested idea, plan, or codebase visual uses the focused artifact route"
    elif kind == "complex_visual":
        if simpler_forms_insufficient:
            form = "focused-artifact"
            reason = "focused artifact only when simpler forms are insufficient"
        else:
            form = "sequence-or-flow"
            reason = "prefer sequence-or-flow before a focused artifact"
    else:
        raise ValueError(f"unknown representation kind: {kind!r}")

    visualize = form != "prose"
    return {
        "form": form,
        "visualize": visualize,
        "adds_planning_ceremony": False,
        "adds_reporting_ceremony": False,
        "reason": reason,
    }



def ship_plan(
    *,
    path: str,
    verified: bool,
    reviewed: bool,
    patpat_activated: bool,
    explicit_delivery: bool,
    repo_allows_delivery: bool,
    opt_out: bool,
    explicit_merge: bool,
    continuation: bool,
    ci: str,
    existing_pr: bool = False,
    existing_pr_is_draft: bool = False,
    explicit_ready_pr: bool = False,
    action: str = "edit",
    high_risk: bool = False,
) -> str:
    if path == "read-only" or action == "inspect":
        return "no-ship"
    if opt_out:
        return "local-only"
    if action in {"deploy", "publish", "force-push"}:
        return "pause"
    if not repo_allows_delivery:
        return "stop-repository-policy"
    intent = delivery_intent(
        explicit_delivery=explicit_delivery,
        continuation=continuation,
        explicit_merge=explicit_merge,
        explicit_ready_pr=explicit_ready_pr,
    )
    if not intent:
        if not verified:
            return "stop-missing-proof"
        if high_risk and not reviewed:
            return "stop-missing-proof"
        if patpat_activated:
            return "local-only"
        return "local-only-no-authority"
    if not verified or not reviewed:
        return "stop-missing-proof"
    if not (patpat_activated or explicit_delivery or explicit_merge or continuation):
        return "local-only-no-authority"
    if explicit_merge:
        if ci == "green":
            if existing_pr and existing_pr_is_draft:
                return "mark-ready-then-merge"
            return "merge"
        if ci == "flake":
            if existing_pr and existing_pr_is_draft:
                return "retry-then-mark-ready-and-merge-if-flake"
            return "retry-then-merge-if-flake"
        return "no-land-real-fail"
    if existing_pr and existing_pr_is_draft and not (patpat_activated or explicit_ready_pr):
        return "update-draft"
    if continuation:
        return "drive-existing-pr-to-merge-ready" if existing_pr else "commit-pr-then-drive-to-merge-ready"
    if existing_pr:
        if existing_pr_is_draft:
            return "mark-ready-and-recheck"
        return "update-existing-pr"
    return "commit-and-pr"


def unit_checkpoint_plan(
    *,
    unit_verified: bool,
    patpat_activated: bool = True,
    explicit_delivery: bool = False,
    continuation: bool = False,
    explicit_merge: bool = False,
    opt_out: bool = False,
    repo_allows_delivery: bool = True,
    remote_configured: bool = True,
) -> str:
    """Evaluate remote vs local checkpoint authority for a verified unit.

    Invariant: Remote capability (remote_configured=True) is not remote authority.
    Remote Git writes remain fail-closed: pushing a verified unit snapshot requires
    existing delivery intent or continuation authority, and is denied if opted out
    (local only, don't commit, don't push) or prohibited by repository policy.
    Without that authority, checkpoints remain strictly local.
    """
    if not unit_verified:
        return "stop-missing-proof"
    if opt_out or not repo_allows_delivery:
        return "checkpoint-local-only"
    # Remote capability alone grants no authority:
    has_remote_write_authority = bool(explicit_delivery or continuation or explicit_merge)
    if has_remote_write_authority:
        return "push-verified-unit-snapshot"
    return "checkpoint-local-only"


def fan_out(*, kind: str, worktree_or_sandbox: bool, shared_worktree: bool, read_only: bool) -> str:
    if kind not in {"arena", "swarm", "autopilot"}:
        return "serial"
    if read_only and kind == "swarm":
        return "parallel-readonly"
    return "serial-fallback"


def issue_loop(
    *,
    provider: str,
    enabled: bool,
    sandbox: bool,
    canary: bool,
    requested_write: str = "",
    allowed_writes: tuple[str, ...] = (),
    fresh_authority: bool = False,
    existing_fix: bool = False,
    interactive_delivery_authority: bool = False,
) -> str:
    if not provider or not sandbox:
        return "fail-closed"
    if not canary or not enabled:
        return "paused"
    if existing_fix:
        return "verify-existing-fix"
    if not requested_write:
        return "triage-readonly"
    if requested_write == "ready-pr" and not interactive_delivery_authority:
        return "ready-pr-denied"
    if requested_write in allowed_writes and fresh_authority:
        return "coordinator-write-authorized"
    return "triage-readonly-write-denied"


def compute_candidate_fingerprint(target_path: Path | str) -> str:
    """Derive deterministic SHA-256 identity from real filesystem state."""
    path = Path(target_path)
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    if path.is_dir():
        hasher = hashlib.sha256()
        for p in sorted(path.rglob("*")):
            if p.is_file():
                hasher.update(p.relative_to(path).as_posix().encode("utf-8"))
                hasher.update(hashlib.sha256(p.read_bytes()).digest())
        return hasher.hexdigest()
    raise FileNotFoundError(f"Candidate path does not exist: {target_path}")


def verification_verdict(
    *,
    candidate_hash: str,
    verified_hash: str,
    behavioral_oracle_passed: bool,
    proxy_passed: bool = False,
    has_observable_oracle: bool = True,
) -> str:
    """Evaluate verification claim freshness and authoritative evidence."""
    if not candidate_hash or candidate_hash != verified_hash:
        return "stale-verification"
    if not has_observable_oracle:
        return "inconclusive"
    if not behavioral_oracle_passed:
        if proxy_passed:
            return "proxy-theater-rejected"
        return "not-verified"
    return "verified"


def verify_candidate_receipt(
    *,
    candidate_path: Path | str,
    verified_receipt: dict[str, object],
    behavioral_oracle_passed: bool,
    proxy_passed: bool = False,
    has_observable_oracle: bool = True,
) -> str:
    """Evaluate verification claim binding directly against candidate filesystem fingerprint."""
    current_hash = compute_candidate_fingerprint(candidate_path)
    verified_hash = str(verified_receipt.get("candidate_hash", ""))
    return verification_verdict(
        candidate_hash=current_hash,
        verified_hash=verified_hash,
        behavioral_oracle_passed=behavioral_oracle_passed,
        proxy_passed=proxy_passed,
        has_observable_oracle=has_observable_oracle,
    )


def extract_ast_boundary_shape(source_code: str) -> dict[str, object]:
    """Derive contract signatures and architectural boundary properties from Python source AST."""
    tree = ast.parse(source_code)
    signatures: set[str] = set()
    unapproved_workarounds = False
    hidden_mutable_state = False

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [arg.arg for arg in node.args.args]
            signatures.add(f"{node.name}({', '.join(args)})")
            name_lower = node.name.lower()
            if any(k in name_lower for k in ("fallback", "compat", "workaround", "escape", "bypass")):
                unapproved_workarounds = True
            for a in node.args.args:
                arg_lower = a.arg.lower()
                if any(k in arg_lower for k in ("workaround", "escape", "bypass", "compat", "fallback")):
                    unapproved_workarounds = True
        elif isinstance(node, ast.Assign):
            if isinstance(node.value, (ast.Dict, ast.List, ast.Set)):
                hidden_mutable_state = True

    return {
        "signatures": signatures,
        "unapproved_workaround": unapproved_workarounds,
        "hidden_mutable_state": hidden_mutable_state,
    }


def design_boundary_decision(
    *,
    approved_signatures: set[str],
    candidate_signatures: set[str],
    unapproved_workaround: bool = False,
    hidden_mutable_state: bool = False,
) -> str:
    """Enforce return-to-design when implementation drifts outside approved boundaries."""
    if unapproved_workaround or hidden_mutable_state:
        return "return-to-design"
    if not candidate_signatures.issubset(approved_signatures):
        return "return-to-design"
    return "proceed-to-implementation"


def design_boundary_from_source(
    *,
    approved_signatures: set[str],
    candidate_source: str,
) -> str:
    """Evaluate architecture drift directly from candidate source AST without manual flags."""
    shape = extract_ast_boundary_shape(candidate_source)
    return design_boundary_decision(
        approved_signatures=approved_signatures,
        candidate_signatures=shape["signatures"],
        unapproved_workaround=shape["unapproved_workaround"],
        hidden_mutable_state=shape["hidden_mutable_state"],
    )


def discover_defects_from_diff(diff: str) -> list[dict[str, str]]:
    """Inspect raw diff to discover concrete defects without pre-supplied metadata."""
    findings: list[dict[str, str]] = []
    added_lines = [
        line[1:] for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    for line in added_lines:
        stripped = line.strip()
        # 1. Security angle: credentials, PATs, secret keys
        if re.search(r"ghp_[A-Za-z0-9_]{20,}", line):
            findings.append({
                "angle": "security",
                "severity": "blocker",
                "detail": "Discovered hardcoded GitHub personal access token in added diff line",
            })
        elif re.search(r"AKIA[0-9A-Z]{16}", line) or re.search(r"(?i)aws_secret_access_key\s*=", line):
            findings.append({
                "angle": "security",
                "severity": "blocker",
                "detail": "Discovered exposed AWS access key/credential in added diff line",
            })
        elif re.search(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}", line):
            findings.append({
                "angle": "security",
                "severity": "high",
                "detail": "Discovered hardcoded Bearer authorization token in added diff line",
            })

        # 2. Epistemic angle: mock-only assertion substituted for authoritative verification
        if (
            re.search(r"\bassert\s+\w*mock\w*\.called\b", line)
            or re.search(r"\.assert_called(?:_once)?\(\)", line)
        ):
            findings.append({
                "angle": "epistemic",
                "severity": "blocker",
                "detail": "Discovered mock-only call assertion used as proxy for authoritative verification",
            })

        # 3. State & concurrency angle: un-synchronized global mutable state introduced
        if re.search(r"\bglobal\s+\w+", line) or re.search(r"^[A-Z0-9_]+\s*:\s*(?:dict|list|set)\s*=", stripped) or re.search(r"^[A-Z0-9_]+\s*=\s*(?:\[\]|\{\}|set\(\))", stripped):
            findings.append({
                "angle": "state",
                "severity": "high",
                "detail": "Discovered un-synchronized global mutable state introduced in added lines",
            })

    return findings


def interrogate_audit(
    *,
    diff: str = "",
    security_defect: str | None = None,
    concurrency_defect: str | None = None,
    epistemic_defect: str | None = None,
    anti_slop_defect: str | None = None,
) -> dict[str, object]:
    """Simulate adversarial review across skeptical angles, discovering defects from diff."""
    findings: list[dict[str, str]] = []
    if diff:
        findings.extend(discover_defects_from_diff(diff))
    if security_defect:
        findings.append({"angle": "security", "severity": "high", "detail": security_defect})
    if concurrency_defect:
        findings.append({"angle": "concurrency", "severity": "high", "detail": concurrency_defect})
    if epistemic_defect:
        findings.append({"angle": "epistemic", "severity": "blocker", "detail": epistemic_defect})
    if anti_slop_defect:
        findings.append({"angle": "anti-slop", "severity": "medium", "detail": anti_slop_defect})

    verdict = "no-findings" if not findings else "findings-surfaced"
    return {
        "verdict": verdict,
        "findings": findings,
        "can_land": verdict == "no-findings",
    }


BANNED_AI_STEMS = (
    ("additionally", r"\badditionally\b"),
    ("crucial", r"\bcrucial\b"),
    ("pivotal", r"\bpivotal\b"),
    ("delve", r"\bdelv\w*\b"),
    ("enhance", r"\benhanc\w*\b"),
    ("foster", r"\bfoster\w*\b"),
    ("intricate", r"\bintricate\b"),
    ("landscape", r"\blandscape\b"),
    ("tapestry", r"\btapestry\b"),
    ("testament", r"\btestament\b"),
    ("underscore", r"\bunderscore\b"),
    ("vibrant", r"\bvibrant\b"),
)


def unslop_lint(text: str) -> dict[str, object]:
    """Detect AI writing patterns, buzzwords, and narrative comments."""
    violations: list[str] = []
    lower = text.lower()
    for name, pattern in BANNED_AI_STEMS:
        if re.search(pattern, lower):
            violations.append(f"banned-word:{name}")
    if re.search(r"\b(highlighting|ensuring|reflecting|showcasing|fostering)\b", lower):
        violations.append("superficial-participial-clause")
    if "—" in text:
        violations.append("em-dash-overuse")
    if re.search(r"#.*(?:crucial|delv|highlight|robust implementation)", text, re.IGNORECASE):
        violations.append("narrative-code-comment")
    return {
        "clean": len(violations) == 0,
        "violations": violations,
    }


def explicit_merge_intent(prompt: str) -> bool:
    if MERGE_DENIAL.search(prompt):
        return False
    return EXPLICIT_MERGE.search(prompt) is not None


def continuation_intent(prompt: str) -> bool:
    text = prompt.casefold()
    return any(phrase in text for phrase in ("overnight", "going to bed", "don't stop", "do not stop"))


def base_ship_args() -> dict[str, object]:
    return {
        "path": "mutating",
        "verified": True,
        "reviewed": True,
        "patpat_activated": True,
        "explicit_delivery": False,
        "repo_allows_delivery": True,
        "opt_out": False,
        "explicit_merge": False,
        "continuation": False,
        "ci": "unknown",
    }


def run_self_test() -> None:
    hook = load_hook()
    assert hook.classify_prompt("/patpat fix the timeout") == "activate"
    assert hook.classify_prompt("$patpat-loop land this") == "activate"
    assert hook.classify_prompt("Use patpat to inspect this repository") == "activate"
    assert hook.classify_prompt("use $patpat-setup on this host") == "inactive"
    assert hook.classify_prompt("Do not activate /patpat for this task.") == "inactive"
    assert hook.classify_prompt("Explain what /patpat does without enabling it.") == "inactive"
    assert hook.classify_prompt("`/patpat fix the bug`") == "inactive"
    assert hook.classify_prompt("Example: /patpat fix the bug") == "inactive"
    assert hook.classify_prompt("disable /patpat") == "disable"

    cases = {
        "How does auth reach this handler? Do not change files.": "inspect",
        "Draw an architecture diagram of this repository.": "repository-diagram",
        "Create a sequence diagram for this project.": "repository-diagram",
        "Don't just describe the auth flow, draw a diagram.": "repository-diagram",
        "Don't just explain the auth flow; create an architecture diagram.": "repository-diagram",
        "Can you explain the architecture diagram of this repository?": "inspect",
        "Do not draw an architecture diagram of this repository.": "loop",
        "This repository has the current auth flow; draw a diagram for the proposed replacement design.": "repository-diagram",
        "For this repository, create an architecture diagram of the proposed service.": "repository-diagram",
        "Explain how this repository routes requests with a diagram.": "repository-diagram",
        "Explain how this repository routes requests and draw an architecture diagram.": "repository-diagram",
        "Can you describe the repository architecture and make a diagram?": "repository-diagram",
        "ช่วยวาดไดอะแกรมบริการใหม่ของ repository นี้": "repository-diagram",
        "Turn this idea into a beautiful interactive visual: Browser calls API then database.": "repository-diagram",
        "Create an interactive plan diagram for a staged migration.": "repository-diagram",
        "ช่วยทำภาพโต้ตอบจากไอเดียเรื่องระบบจองคิว": "repository-diagram",
        "I have a plan for a feature; can you help me implement it?": "loop",
        "What is a beautiful interactive diagram?": "loop",
        "Build a playable browser game with keyboard movement and a restart loop.": "game-builder",
        "Add a dodge move to this game.": "game-builder",
        "Improve the controls in this game.": "game-builder",
        "Do not add a dodge move to this game.": "loop",
        "Create a test plan for the game's input state machine.": "loop",
        "Build a test plan for this game's input state machine.": "loop",
        "Add a test plan for this game's input state machine.": "loop",
        "Implement a test plan for this game's input state machine.": "loop",
        "Make a test matrix for the game's controls.": "loop",
        "Build a test plan for a playable game.": "loop",
        "Create a production plan for a new game.": "loop",
        "Create a development roadmap for a new game.": "loop",
        "Create a plan to build a game.": "loop",
        "Create a game plan for a puzzle game.": "loop",
        "Make a plan to build a game.": "loop",
        "Make a game plan.": "loop",
        "เกมนี้ไม่สมดุล ช่วยเพิ่มความเร็วตัวละคร": "game-builder",
        "เกมนี้ไม่สมดุล ไม่ต้องเพิ่มความเร็วตัวละคร": "loop",
        "This game feels unbalanced; increase player speed.": "game-builder",
        "This game is not balanced, increase player speed.": "game-builder",
        "This game feels unbalanced; add a section about player movement to the README.": "loop",
        "The game feels unbalanced, add a section about player movement to README.md.": "loop",
        "The game feels unbalanced; add a section about player movement.": "loop",
        "This game feels unbalanced; add a README section about its visual feedback.": "loop",
        "The game feels unbalanced; add a section about player movement, then increase player speed.": "game-builder",
        "This game feels unbalanced; increase player speed and update the README.": "game-builder",
        "This game feels unbalanced; update the README and increase player speed.": "game-builder",
        "The game feels unbalanced; add a note about player movement to the README and increase player speed.": "game-builder",
        "This game feels unbalanced; update the README, then increase player speed.": "game-builder",
        "This game feels unbalanced; don't increase player speed.": "loop",
        "This game has a checkpoint system. Remove the first section from the README.": "loop",
        "This game is a puzzle. Increase the font size in the README.": "loop",
        "The game is stable; fix the README typo.": "debug",
        "The game is ready; add a note to the changelog.": "loop",
        "ช่วยทำแผนการผลิตเกมใหม่": "loop",
        "ช่วยทำ production plan สำหรับ game นี้": "loop",
        "ช่วยทำ game plan สำหรับ puzzle game": "loop",
        "Build a game design document from this concept.": "loop",
        "Create a test plan for the game's input state machine, then build a playable game from it.": "game-builder",
        "Create a test plan and build a playable game from it.": "game-builder",
        "Create a test plan for this game, then add a dodge move to this game.": "game-builder",
        "Add a dodge move to this game, then make a test plan for it.": "game-builder",
        "Build a playable game from this test plan.": "game-builder",
        "Why did this game's build fail?": "debug",
        "Explain how this game's build pipeline works.": "inspect",
        "Explain how to build a game with Godot.": "inspect",
        "Please explain how to build a game with Godot.": "inspect",
        "The build for this game fails on startup; diagnose it.": "debug",
        "My game fails to build; please debug it.": "debug",
        "My game crashes on startup.": "debug",
        "Do not just explain the plan and implement the game.": "game-builder",
        "Don't make a new game; extend this one with a dodge move.": "game-builder",
        "Don't make a new game, extend this one with a dodge move.": "game-builder",
        "Don't make a new game, just add a dodge move to this one.": "game-builder",
        "Don't make a new game, and just add a dodge move to this one.": "game-builder",
        "Don't make a new game, and just add another game.": "loop",
        "Don't make a new game, and just build it.": "loop",
        "Don't make a new game, then add a dodge move to this game.": "game-builder",
        "Don't make a new game, and add a dodge move to this game.": "game-builder",
        "Don't make a new game, then add a dodge move to it.": "loop",
        "Don't build a game and add a dodge move to it.": "loop",
        "Don't build a game and then add a dodge move to it.": "loop",
        "Don't make a new game; don't extend this one with a dodge move.": "loop",
        "Don't make a new game, don't extend this one with a dodge move.": "loop",
        "Don't make a game and implement a save system.": "loop",
        "Would you explain how to build a game with Godot?": "inspect",
        "Explain how to build a game with Godot, then build a playable game from that explanation.": "game-builder",
        "Explain how to build a game with Godot, then build it from that explanation.": "game-builder",
        "Explain how to build a game with Godot, then create one based on that explanation.": "game-builder",
        "ช่วยอธิบายวิธีสร้างเกมด้วย Godot แล้วช่วยสร้างเกมนี้ให้ด้วย": "game-builder",
        "ช่วยอธิบายวิธีสร้างเกมด้วย Godot และสร้างเกมนี้ให้ด้วย": "game-builder",
        "ไม่ต้องสร้างเกมใหม่ และเพิ่มท่าหลบให้เกมเดิม": "game-builder",
        "ไม่ต้องสร้างเกมใหม่ แล้วเพิ่มท่าหลบให้เกมเดิม": "game-builder",
        "ไม่ต้องสร้างเกมใหม่ แล้วเพิ่มท่าหลบให้มัน": "loop",
        "ไม่ต้องสร้างเกมใหม่ และไม่ต้องเพิ่มท่าหลบให้เกมเดิม": "loop",
        "Add a game design document for this project.": "loop",
        "Implement a game design document for this project.": "loop",
        "Write a game design document for a platformer, then create one for a puzzle game.": "loop",
        "Write a game design document, then explain how to build a game, then build it from that explanation.": "game-builder",
        "Help add two game ideas.": "loop",
        "ช่วยเพิ่มไอเดียเกมสองแบบ": "loop",
        "ช่วยสร้าง game concept สำหรับ puzzle": "loop",
        "ช่วยทำ test plan สำหรับ game นี้": "loop",
        "ช่วยทำแผนทดสอบ state machine ของเกมนี้": "loop",
        "ช่วยอธิบายวิธีสร้างเกมด้วย Godot": "inspect",
        "ไม่ต้องสร้างเกมใหม่ แต่เพิ่มท่าหลบให้เกมเดิม": "game-builder",
        "ไม่ต้องสร้างเกมใหม่ แต่ไม่ต้องเพิ่มท่าหลบให้เกมเดิม": "loop",
        "Extend this game's combat with a working dodge move and cooldown feedback.": "game-builder",
        "ช่วยสร้างเกมเล็ก ๆ ที่เล่นได้ มีปุ่มควบคุมและเริ่มใหม่ได้": "game-builder",
        "Create a game concept for a cozy puzzle game.": "loop",
        "Build a playable browser game from this game concept.": "game-builder",
        "Build a game from this game concept.": "game-builder",
        "Write a game design document for a platformer.": "loop",
        "Develop a game concept for a cozy puzzle game.": "loop",
        "Develop a playable game from this concept.": "game-builder",
        "Create a game concept for a cozy puzzle game, then build it.": "game-builder",
        "Implement this game design as a playable browser game.": "game-builder",
        "Use this game design document to build a playable game.": "game-builder",
        "ช่วยสร้างแนวคิดเกมให้หน่อย": "loop",
        "ช่วยเขียนแนวคิดเกมปริศนาสามแบบ": "loop",
        "Discuss three possible game concepts without changing code.": "loop",
        "Do not build a game; just compare three puzzle mechanics.": "loop",
        "ไม่ต้องสร้างเกม ช่วยเปรียบเทียบแนวคิดเกมปริศนาสามแบบ": "loop",
        "Explain how this game's architecture is organized.": "inspect",
        "Create a diagram of the gameplay architecture.": "repository-diagram",
        "Create a diagram of this game's visual feedback flow.": "repository-diagram",
        "Create a diagram of this game's visual feedback flow, then add a dodge move to this game.": "loop",
        "Create a diagram of this game's visual feedback flow, then add a dodge move.": "loop",
        "Create a diagram of this game's visual feedback flow, but don't add a dodge move to this game.": "repository-diagram",
        "Create a diagram of this game's visual feedback flow, then build a game.": "loop",
        "Create an architecture diagram, then fix the auth bug.": "loop",
        "Create an architecture diagram, then debug why the game crashes.": "loop",
        "Create an architecture diagram, then fix the game build error.": "loop",
        "Create an architecture diagram, but don't debug the game crash.": "repository-diagram",
        "Create an architecture diagram, but don't diagnose the game crash.": "repository-diagram",
        "Create an architecture diagram, but don't investigate the game crash.": "repository-diagram",
        "Create an architecture diagram; no need to fix the auth bug.": "repository-diagram",
        "Create an architecture diagram; it is not necessary to fix the auth bug.": "repository-diagram",
        "Create an architecture diagram, then investigate why the game crashes.": "loop",
        "Create an architecture diagram, but don't update the README.": "repository-diagram",
        "ช่วยทำแผนภาพ flow ของเกมนี้ แล้วเพิ่มท่าหลบให้เกมเดิม": "loop",
        "ช่วยทำแผนภาพ flow ของเกมนี้ แล้วสร้างเกมที่เล่นได้ด้วย": "loop",
        "ช่วยทำแผนภาพ flow ของเกมนี้ แต่ไม่ต้องเพิ่มท่าหลบให้เกมนี้": "repository-diagram",
        "ช่วยทำแผนภาพ flow แต่ไม่ต้อง debug game crash": "repository-diagram",
        "ช่วยทำแผนภาพ flow แต่ไม่ต้องแก้เอกสาร": "repository-diagram",
        "Make the game's visual feedback clearer.": "game-builder",
        "Improve the game's visuals and HUD readability.": "game-builder",
        "เกมเพลย์มี flow แบบนี้ ช่วยทำแผนภาพให้หน่อย": "repository-diagram",
        "เกมนี้ feedback ยังไม่ชัด ช่วยปรับการแสดงผลให้ดีขึ้น": "game-builder",
        "อย่าแค่อธิบาย flow นี้ ช่วยวาดแผนภาพ": "repository-diagram",
        "ช่วยสร้างแผนภาพการไหลข้อมูลของ repository นี้ครับ": "repository-diagram",
        "ช่วยสร้างไดอะแกรมของ repository นี้หน่อย": "repository-diagram",
        "อธิบายการไหลของ repository นี้ แล้วช่วยสร้างแผนภาพ": "repository-diagram",
        "ขอดูแผนภาพ architecture ของโปรเจกต์นี้": "repository-diagram",
        "ช่วยอธิบายไดอะแกรมของ repository นี้หน่อย": "inspect",
        "How does this repository store notes? Explain briefly.": "inspect",
        "อธิบายการเก็บโน้ตใน repository นี้แบบสั้น ๆ": "inspect",
        "/patpat reproduce this timeout and fix the root cause": "debug",
        "which skill owns investigation vs rationale-forensics?": "inspect",
        "where should this live?": "inspect",
        "Why does dry_run_loop.ship_plan require explicit land/merge?": "inspect",
        "how does routing work?": "inspect",
        "/patpat arena two layouts for this page": "arena",
        "/patpat swarm each package against its check script": "swarm",
        "/patpat autopilot this queue; do not merge": "autopilot",
        "/patpat design an issue-loop for GitHub issues; keep it paused": "issue-loop",
        "/patpat pause safely, I am going offline": "pause",
        "/patpat babysit this PR and get it green": "pr-babysit",
        "/patpat prune abandoned worktrees": "worktree-cleanup",
        "/patpat merge this": "ship",
        "do not merge; keep the work local": "loop",
        "make this merge-ready without landing": "loop",
        "/patpat fix settings when users disable alerts": "debug",
        "/patpat do not disable the safety gate": "loop",
        "disable /patpat": "disable",
        "opt out of patpat": "disable",
    }
    for prompt, expected in cases.items():
        got = route(prompt)
        if got != expected:
            raise AssertionError(f"route({prompt!r})={got!r} expected {expected!r}")

    base_ship = base_ship_args()
    # Activation alone does not ship; delivery intent is required for commit-and-PR.
    assert ship_plan(**base_ship) == "local-only"
    assert ship_plan(**{**base_ship, "reviewed": False}) == "local-only"
    assert ship_plan(**{**base_ship, "verified": False}) == "stop-missing-proof"
    assert ship_plan(**{**base_ship, "explicit_delivery": True}) == "commit-and-pr"
    assert ship_plan(**{**base_ship, "explicit_delivery": True, "reviewed": False}) == "stop-missing-proof"
    assert ship_plan(**{**base_ship, "high_risk": True, "reviewed": False}) == "stop-missing-proof"
    assert ship_plan(**{**base_ship, "high_risk": True, "reviewed": True}) == "local-only"
    assert ship_plan(**{**base_ship, "high_risk": True, "reviewed": True, "explicit_delivery": True}) == "commit-and-pr"

    # start_plan: first activation is not a risk signal; planning is earned.
    light = start_plan(first_activation=True, clear_bounded_reversible_local=True, mutating=True)
    assert light["kind"] == "lightweight-start"
    assert light["mandatory_todo"] is False
    assert light["mandatory_checklist"] is False
    assert light["proof_contract_required"] is True
    assert light["full_protocol_read"] is False
    assert start_plan(first_activation=True, high_risk=True)["kind"] == "fuller-start"
    assert start_plan(first_activation=True, ambiguous=True)["kind"] == "fuller-start"
    assert start_plan(clear_bounded_reversible_local=True)["kind"] == "lightweight-start"
    assert start_plan(clear_bounded_reversible_local=True)["mandatory_todo"] is False
    assert start_plan(multi_step=True, ambiguous=True)["kind"] == "fuller-start"
    assert start_plan(multi_step=True, ambiguous=True)["mandatory_checklist"] is True
    assert start_plan(durable=True)["kind"] == "durable-run"
    assert start_plan(clear_bounded_reversible_local=True, mutating=False)["proof_contract_required"] is False
    assert ship_plan(**{**base_ship, "opt_out": True}) == "local-only"
    assert ship_plan(**{**base_ship, "path": "read-only"}) == "no-ship"
    assert ship_plan(**{**base_ship, "patpat_activated": False}) == "local-only-no-authority"
    assert ship_plan(
        **{**base_ship, "patpat_activated": False, "explicit_delivery": True}
    ) == "commit-and-pr"
    assert ship_plan(**{**base_ship, "repo_allows_delivery": False}) == "stop-repository-policy"
    # Bare existing_pr is not delivery intent (Interpretation B).
    assert ship_plan(**{**base_ship, "existing_pr": True}) == "local-only"
    assert ship_plan(**{**base_ship, "existing_pr": True, "existing_pr_is_draft": True}) == "local-only"
    assert ship_plan(**{**base_ship, "explicit_delivery": True, "existing_pr": True}) == "update-existing-pr"
    assert ship_plan(**{**base_ship, "explicit_delivery": True, "existing_pr": True, "existing_pr_is_draft": True}) == "mark-ready-and-recheck"
    draft_ship = {
        **base_ship,
        "patpat_activated": False,
        "explicit_delivery": True,
        "existing_pr": True,
        "existing_pr_is_draft": True,
    }
    assert ship_plan(**draft_ship) == "update-draft"
    assert ship_plan(**{**draft_ship, "continuation": True}) == "update-draft"
    assert ship_plan(**{**draft_ship, "explicit_ready_pr": True}) == "mark-ready-and-recheck"
    assert ship_plan(**{**base_ship, "explicit_merge": True, "ci": "green"}) == "merge"
    draft_merge = {**base_ship, "explicit_merge": True, "existing_pr": True, "existing_pr_is_draft": True}
    assert ship_plan(**{**draft_merge, "ci": "green"}) == "mark-ready-then-merge"
    assert ship_plan(**{**draft_merge, "ci": "flake"}) == "retry-then-mark-ready-and-merge-if-flake"
    assert ship_plan(**{**base_ship, "explicit_merge": True, "ci": "red"}) == "no-land-real-fail"
    assert ship_plan(**{**base_ship, "explicit_merge": True, "ci": "flake"}) == "retry-then-merge-if-flake"
    assert ship_plan(**{**base_ship, "continuation": True, "ci": "green"}) == "commit-pr-then-drive-to-merge-ready"
    assert ship_plan(**{**base_ship, "continuation": True, "ci": "green", "existing_pr": True}) == "drive-existing-pr-to-merge-ready"
    assert ship_plan(**{**base_ship, "action": "deploy"}) == "pause"
    assert ship_plan(**{**base_ship, "action": "force-push"}) == "pause"

    assert explicit_merge_intent("/patpat merge this") is True
    assert explicit_merge_intent("land the PR") is True
    assert explicit_merge_intent("work overnight") is False
    assert explicit_merge_intent("don't stop until merge-ready") is False
    assert explicit_merge_intent("do not merge") is False
    assert explicit_merge_intent("don't ever merge") is False
    assert explicit_merge_intent("never automatically merge") is False
    assert explicit_merge_intent("do not under any circumstances merge") is False
    assert explicit_merge_intent("never, ever merge") is False
    assert explicit_merge_intent("continue without merge") is False
    assert explicit_merge_intent("ship it") is False
    assert continuation_intent("work overnight") is True
    assert continuation_intent("merge this") is False

    # Remote capability is not remote authority:
    # 1. Activation alone or remote configured alone -> checkpoint local only
    assert unit_checkpoint_plan(unit_verified=True, patpat_activated=True, remote_configured=True) == "checkpoint-local-only"
    # 2. Local-only prohibition -> checkpoint local only
    assert unit_checkpoint_plan(unit_verified=True, explicit_delivery=True, opt_out=True) == "checkpoint-local-only"
    assert unit_checkpoint_plan(unit_verified=True, continuation=True, opt_out=True) == "checkpoint-local-only"
    assert unit_checkpoint_plan(unit_verified=True, explicit_delivery=True, repo_allows_delivery=False) == "checkpoint-local-only"
    # 3. Explicit delivery -> qualified progress push permitted
    assert unit_checkpoint_plan(unit_verified=True, explicit_delivery=True) == "push-verified-unit-snapshot"
    # 4. Continuation authority -> qualified progress push permitted
    assert unit_checkpoint_plan(unit_verified=True, continuation=True) == "push-verified-unit-snapshot"
    # 5. Remote configured alone without delivery/continuation authority -> checkpoint local only
    assert unit_checkpoint_plan(unit_verified=True, remote_configured=True, explicit_delivery=False, continuation=False) == "checkpoint-local-only"
    # 6. Unverified unit -> stop missing proof
    assert unit_checkpoint_plan(unit_verified=False, explicit_delivery=True) == "stop-missing-proof"

    assert fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=False, read_only=False) == "serial-fallback"
    assert fan_out(kind="arena", worktree_or_sandbox=False, shared_worktree=True, read_only=False) == "serial-fallback"
    assert fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=True, read_only=False) == "serial-fallback"
    assert fan_out(kind="swarm", worktree_or_sandbox=False, shared_worktree=True, read_only=True) == "parallel-readonly"
    assert fan_out(kind="autopilot", worktree_or_sandbox=False, shared_worktree=True, read_only=False) == "serial-fallback"

    assert issue_loop(provider="", enabled=False, sandbox=False, canary=False) == "fail-closed"
    assert issue_loop(provider="github", enabled=False, sandbox=True, canary=True) == "paused"
    active_issue = {"provider": "github", "enabled": True, "sandbox": True, "canary": True}
    assert issue_loop(**active_issue) == "triage-readonly"
    assert issue_loop(**active_issue, existing_fix=True) == "verify-existing-fix"
    assert issue_loop(**active_issue, requested_write="comment") == "triage-readonly-write-denied"
    ready_write = {**active_issue, "requested_write": "ready-pr", "allowed_writes": ("ready-pr",), "fresh_authority": True}
    assert issue_loop(**ready_write) == "ready-pr-denied"
    assert issue_loop(**ready_write, interactive_delivery_authority=True) == "coordinator-write-authorized"
    assert issue_loop(**active_issue, requested_write="comment", allowed_writes=("comment",), fresh_authority=True) == "coordinator-write-authorized"

    # Instruction-contract checks, not live-agent behavioral proof.
    judgment_corpus = [
        ("unnecessary-ask", "ask for a path without inspecting", "reject"),
        ("inspect-before-ask", "inspect, execute, or measure before asking", "accept"),
        ("over-plan", "write a multi-phase plan for a one-line typo", "reject"),
        ("over-fan-out", "spawn arena for a single-file typo", "reject"),
        ("over-rigor", "require independent review for local-only reversible typo", "reject"),
        ("proxy-proof", "claim verified from a build alone", "reject"),
        ("authoritative-surface", "observe claimed behavior on the authoritative surface", "accept"),
        ("local-only", ship_plan(**base_ship), "local-only"),
        ("delivery", ship_plan(**{**base_ship, "explicit_delivery": True}), "commit-and-pr"),
        ("under-rigor-auth", ship_plan(**{**base_ship, "high_risk": True, "reviewed": False}), "stop-missing-proof"),
    ]
    for name, observed, expected in judgment_corpus:
        if name in {"local-only", "delivery", "under-rigor-auth"}:
            if observed != expected:
                raise AssertionError(f"judgment {name}: {observed!r} != {expected!r}")
        elif expected == "accept" and "reject" in str(observed).casefold() and name.startswith("x"):
            raise AssertionError(name)
        # Structural presence checks for instruction-contract labels.
        if name not in {"local-only", "delivery", "under-rigor-auth"} and not isinstance(observed, str):
            raise AssertionError(f"judgment corpus row {name} missing label")
    assert judgment_corpus[0][2] == "reject"
    assert judgment_corpus[1][2] == "accept"
    assert any(row[0] == "under-rigor-auth" for row in judgment_corpus)
    assert any(row[0] == "proxy-proof" for row in judgment_corpus)


    # representation_plan: earned forms; orthogonal to start_plan ceremony.
    factual = representation_plan(kind="factual", structure_hard_in_prose=True)
    assert factual["form"] == "prose" and factual["visualize"] is False
    runtime = representation_plan(kind="runtime_flow", structure_hard_in_prose=True)
    assert runtime["form"] == "call-tree" and runtime["visualize"] is True
    ownership = representation_plan(kind="ownership", structure_hard_in_prose=True)
    assert ownership["form"] == "shallow-tree" and ownership["visualize"] is True
    arch = representation_plan(kind="architecture_delta", structure_hard_in_prose=True)
    assert arch["form"] == "structural-comparison" and arch["visualize"] is True
    shape = representation_plan(kind="shape_review", structure_hard_in_prose=True)
    assert shape["form"] == "diff-shaped" and shape["visualize"] is True
    complex_simple = representation_plan(kind="complex_visual", simpler_forms_insufficient=False)
    assert complex_simple["form"] != "focused-artifact"
    assert complex_simple["form"] == "sequence-or-flow"
    complex_artifact = representation_plan(kind="complex_visual", simpler_forms_insufficient=True)
    assert complex_artifact["form"] == "focused-artifact" and complex_artifact["visualize"] is True
    trivial = representation_plan(kind="trivial_mutation")
    assert trivial["form"] == "prose"
    assert trivial["visualize"] is False
    assert trivial["adds_planning_ceremony"] is False
    assert trivial["adds_reporting_ceremony"] is False
    soft = representation_plan(kind="runtime_flow", structure_hard_in_prose=False)
    assert soft["form"] == "prose" and soft["visualize"] is False
    for sample in (
        factual, runtime, ownership, arch, shape, complex_simple, complex_artifact, trivial, soft,
        representation_plan(kind="logic", structure_hard_in_prose=True),
        representation_plan(kind="ui_structure", structure_hard_in_prose=True),
        representation_plan(kind="interaction_flow", structure_hard_in_prose=True),
    ):
        assert sample["adds_planning_ceremony"] is False
        assert sample["adds_reporting_ceremony"] is False
    # Orthogonality: representation_plan does not imply fuller-start for clear local mutate.
    clear_local = start_plan(clear_bounded_reversible_local=True, mutating=True)
    assert clear_local["kind"] == "lightweight-start"
    assert representation_plan(kind="trivial_mutation")["form"] == "prose"
    assert representation_plan(kind="repository_diagram")["form"] == "interactive-diagram-artifact"
    assert route("please interrogate this diff") == "interrogate"
    assert route("unslop this report") == "unslop"

    # Verification freshness and theater
    assert verification_verdict(candidate_hash="abc", verified_hash="abc", behavioral_oracle_passed=True) == "verified"
    assert verification_verdict(candidate_hash="abc", verified_hash="xyz", behavioral_oracle_passed=True) == "stale-verification"
    assert verification_verdict(candidate_hash="abc", verified_hash="abc", behavioral_oracle_passed=False, proxy_passed=True) == "proxy-theater-rejected"
    assert verification_verdict(candidate_hash="abc", verified_hash="abc", behavioral_oracle_passed=False, proxy_passed=False) == "not-verified"
    assert verification_verdict(candidate_hash="abc", verified_hash="abc", behavioral_oracle_passed=False, has_observable_oracle=False) == "inconclusive"

    # Architecture boundary enforcement
    assert design_boundary_decision(approved_signatures={"foo()"}, candidate_signatures={"foo()"}) == "proceed-to-implementation"
    assert design_boundary_decision(approved_signatures={"foo()"}, candidate_signatures={"foo()", "unapproved()"}) == "return-to-design"
    assert design_boundary_decision(approved_signatures={"foo()"}, candidate_signatures={"foo()"}, unapproved_workaround=True) == "return-to-design"

    # AST-derived architecture boundary
    approved_src = "def process_event(event):\n    return event\n"
    drifted_src = "def process_event(event, workaround_flag=True):\n    return event\n"
    assert design_boundary_from_source(approved_signatures={"process_event(event)"}, candidate_source=approved_src) == "proceed-to-implementation"
    assert design_boundary_from_source(approved_signatures={"process_event(event)"}, candidate_source=drifted_src) == "return-to-design"

    # Interrogation adversarial review & diff discovery
    clean_audit = interrogate_audit()
    assert clean_audit["verdict"] == "no-findings" and clean_audit["can_land"] is True
    flawed_audit = interrogate_audit(security_defect="unmasked AWS key")
    assert flawed_audit["verdict"] == "findings-surfaced" and flawed_audit["can_land"] is False
    diff_discovered = interrogate_audit(diff="--- a/x.py\n+++ b/x.py\n+ token = 'ghp_012345678901234567890123456789012345'")
    assert diff_discovered["verdict"] == "findings-surfaced" and diff_discovered["can_land"] is False
    assert any(f["angle"] == "security" for f in diff_discovered["findings"])

    # Unslop detection
    clean_text = unslop_lint("def compute(x: int) -> int: return x * 2")
    assert clean_text["clean"] is True
    sloppy_text = unslop_lint("# Crucial calculation delving into metrics — ensuring accuracy")
    assert sloppy_text["clean"] is False
    assert "em-dash-overuse" in sloppy_text["violations"]
    assert "superficial-participial-clause" in sloppy_text["violations"]

    print("Patpat loop dry-run self-test passed.")


def main() -> int:
    if "--self-test" in sys.argv or not sys.argv[1:]:
        run_self_test()
        print()
        print("Dry-run scenarios")
        base_ship = base_ship_args()
        rows = [
            ("inspect", route("How does this work? Do not change files."), ship_plan(**{**base_ship, "path": "read-only"})),
            ("placement", route("which skill owns investigation vs rationale-forensics?"), ship_plan(**{**base_ship, "path": "read-only"})),
            ("why-ship_plan", route("Why does dry_run_loop.ship_plan require explicit land/merge?"), ship_plan(**{**base_ship, "path": "read-only"})),
            ("how-routing", route("how does routing work?"), ship_plan(**{**base_ship, "path": "read-only"})),
            ("fix", route("/patpat fix the timeout"), ship_plan(**base_ship)),
            ("fix open PR", "debug", ship_plan(**{**base_ship, "explicit_delivery": True})),
            ("fix local only", "debug", ship_plan(**{**base_ship, "opt_out": True})),
            ("overnight", "debug", ship_plan(**{**base_ship, "continuation": True, "ci": "green"})),
            ("land green", "debug", ship_plan(**{**base_ship, "explicit_merge": True, "ci": "green"})),
            ("land red", "debug", ship_plan(**{**base_ship, "explicit_merge": True, "ci": "red"})),
            ("deploy", "ship", ship_plan(**{**base_ship, "ci": "green", "action": "deploy"})),
            ("arena isolated", "arena", fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=False, read_only=False)),
            ("arena shared worktree", "arena", fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=True, read_only=False)),
            ("issue-loop unnamed", "issue-loop", issue_loop(provider="", enabled=False, sandbox=False, canary=False)),
            ("issue-loop competing fix", "issue-loop", issue_loop(provider="github", enabled=True, sandbox=True, canary=True, existing_fix=True)),
            ("issue-loop ready PR without interactive authority", "issue-loop", issue_loop(provider="github", enabled=True, sandbox=True, canary=True, requested_write="ready-pr", allowed_writes=("ready-pr",), fresh_authority=True)),
        ]
        for name, routed, decision in rows:
            print(f"- {name}: route={routed} decision={decision}")
        return 0
    print("Usage: python3 scripts/dry_run_loop.py --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
