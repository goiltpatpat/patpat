#!/usr/bin/env python3
"""Render validated Patpat diagram JSON as standalone SVG and HTML."""

from __future__ import annotations

import argparse
import base64
import datetime
import errno
import hashlib
import html
import http.client
import http.server
import json
import math
import multiprocessing
import os
import re
import shutil
import socket
import subprocess
import stat
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zlib
from collections import defaultdict, deque
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator

from model import MAX_SOURCE_JSON_BYTES, DiagramError, git_context, load_json, parse_json, validate_spec
from delta import compare_architecture

TOOL_VERSION = "2.0.0"
OUTPUT_LOCK_NAME = ".patpat-diagram.lock"
_OUTPUT_LOCKS: dict[str, threading.Lock] = {}
_OUTPUT_LOCKS_GUARD = threading.Lock()
MIN_CANVAS_WIDTH = 1200.0
DESKTOP_READER_WIDTH = 960.0
DESKTOP_READER_CHROME = 40.0
MIN_PROJECTED_NODE_TEXT_PX = 6.0
BLOCKING_GEOMETRY_PREFIXES = (
    "node overlap:", "node outside canvas:", "node overlaps diagram header:",
    "node layer order:", "node layer reading order:", "edge self-crossing:",
    "edge label overlaps node:", "edge label overlap:", "boundary overlap",
    "boundary overlaps unrelated node:", "boundary outside canvas:", "boundary overlaps diagram header:",
    "edge label overlaps diagram header:", "edge label outside canvas:", "edge outside canvas:",
    "edge crosses diagram header:",
    "edge endpoint outside node port:", "edge crosses node:", "edge crossing:",
    "edge route reenters hinted endpoint:", "edge route overlaps relationship label:",
)
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class _FinalizeGateError(DiagramError):
    def __init__(self, message: str, stage: str, gates: dict[str, str]) -> None:
        super().__init__(message)
        self.stage = stage
        self.gates = gates

UI_TEXT = {
    "en": {
        "type": {"architecture": "Architecture", "workflow": "Workflow", "sequence": "Sequence", "dataflow": "Data flow", "lifecycle": "Lifecycle"},
        "working_dirty": "working tree contains changes",
        "working_clean": "clean working tree",
        "repo_dirty": "working tree dirty",
        "repo_clean": "clean",
        "confidence": "EVIDENCE CONFIDENCE",
        "confirmed": "Confirmed",
        "inferred": "Inferred",
        "unknown": "Unknown",
        "line_styles": "Solid: direct flow  ·  dashed: return/loop  ·  dotted: async/event",
        "diagram": "diagram",
        "pan_hint": "Scroll sideways to follow the full diagram.",
        "outline": "Text outline",
        "outline_help": "This table exposes each visual element and its evidence status in reading order. Scroll horizontally on narrow screens.",
        "entities": "Entities and states",
        "relationships": "Relationships and transitions",
        "boundaries": "Boundaries and lanes",
        "id": "ID",
        "label": "Label",
        "kind": "Kind",
        "evidence_status": "Evidence status",
        "source_refs": "Source refs",
        "direction": "Direction",
        "members": "Members",
        "no_anchor": "no source anchor",
        "source_evidence": "Evidence and origins",
        "claim": "Claim basis",
        "repository_location": "Repository location",
        "source_snapshot": "Evidence bytes",
        "source_permalink": "Open this committed range on GitHub",
        "committed_snapshot": "Committed at HEAD",
        "working_snapshot": "Working tree differs from HEAD",
        "not_committed": "Not present at HEAD",
        "committed_digest": "HEAD file digest",
        "line_digest": "Line digest",
        "brief_evidence": "Provided brief · claim digest",
        "brief_snapshot": "Brief claim · not code-verified",
        "brief_source": "BRIEF · NOT CODE-VERIFIED",
        "provenance": "Diagram source provenance",
        "origin": "Sanitized origin",
        "changed_paths": "Changed paths at render",
        "footer": "Generated from editable Patpat diagram JSON. The SVG and evidence table are embedded; this artifact works offline. Live refresh runs only on Patpat's explicit loopback preview URL.",
    },
    "th": {
        "type": {"architecture": "สถาปัตยกรรม", "workflow": "เวิร์กโฟลว์", "sequence": "ลำดับการสื่อสาร", "dataflow": "การไหลของข้อมูล", "lifecycle": "วงจรสถานะ"},
        "working_dirty": "working tree มีการเปลี่ยนแปลง",
        "working_clean": "working tree สะอาด",
        "repo_dirty": "working tree มีการเปลี่ยนแปลง",
        "repo_clean": "สะอาด",
        "confidence": "หลักฐาน",
        "confirmed": "ยืนยัน",
        "inferred": "อนุมาน",
        "unknown": "ไม่ทราบ",
        "line_styles": "ทึบ: ลำดับหลัก  ·  ประ: ย้อนกลับ/วนซ้ำ  ·  จุด: async/event",
        "diagram": "แผนภาพ",
        "pan_hint": "เลื่อนแนวนอนเพื่อดูแผนภาพเต็ม",
        "outline": "รายละเอียดแบบข้อความ",
        "outline_help": "ตารางนี้แสดงองค์ประกอบในภาพและสถานะของหลักฐานตามลำดับการอ่าน บนจอแคบให้เลื่อนตารางในแนวนอน",
        "entities": "องค์ประกอบและสถานะ",
        "relationships": "ความสัมพันธ์และการเปลี่ยนผ่าน",
        "boundaries": "ขอบเขตและ lane",
        "id": "รหัส",
        "label": "ชื่อ",
        "kind": "ชนิด",
        "evidence_status": "สถานะหลักฐาน",
        "source_refs": "หลักฐานอ้างอิง",
        "direction": "ทิศทาง",
        "members": "สมาชิก",
        "no_anchor": "ไม่มีจุดอ้างอิงใน source",
        "source_evidence": "หลักฐานและแหล่งที่มา",
        "claim": "ฐานของข้อกล่าวอ้าง",
        "repository_location": "ตำแหน่งใน repository",
        "source_snapshot": "แหล่งข้อมูลหลักฐาน",
        "source_permalink": "เปิดช่วงบรรทัดนี้บน GitHub",
        "committed_snapshot": "ตรงกับ commit ที่ HEAD",
        "working_snapshot": "working tree ต่างจาก HEAD",
        "not_committed": "ยังไม่มีใน HEAD",
        "committed_digest": "digest ไฟล์ใน HEAD",
        "line_digest": "digest ของบรรทัด",
        "brief_evidence": "คำบรรยายที่ให้มา · digest ของข้อกล่าวอ้าง",
        "brief_snapshot": "ข้อกล่าวอ้างจากคำบรรยาย · ไม่ได้ยืนยันจากโค้ด",
        "brief_source": "คำบรรยาย · ไม่ยืนยันด้วยโค้ด",
        "provenance": "แหล่งที่มาของแผนภาพ",
        "origin": "origin ที่ตัดข้อมูลรับรองออกแล้ว",
        "changed_paths": "ไฟล์ที่เปลี่ยนเมื่อ render",
        "footer": "สร้างจาก JSON แผนภาพ Patpat ที่แก้ไขได้ โดยฝัง SVG และตารางหลักฐานไว้ในไฟล์ เปิดแบบออฟไลน์ได้; จะตรวจอัปเดตเฉพาะผ่านลิงก์พรีวิวในเครื่องของ Patpat",
    },
}

VIEWER_TEXT = {
    "en": {
        "tools": "Explore diagram",
        "search": "Find a component or relationship",
        "search_results": "Search results",
        "search_result_count": "{count} matches. Use the arrow keys to choose a result.",
        "search_result_empty": "No matching component or relationship found.",
        "search_choose_result": "Choose a result with the arrow keys, then press Enter.",
        "focus": "Focus component",
        "focus_one": "Focus",
        "upstream": "Upstream reach",
        "downstream": "Downstream reach",
        "clear": "Clear focus",
        "lens": "Semantic lens",
        "certainty_lens": "Evidence certainty",
        "all": "All evidence",
        "all_kinds": "All component and relationship kinds",
        "component_kind": "Component kind",
        "relationship_kind": "Relationship kind",
        "role_compare": "Compare component roles",
        "role_a": "First component kind",
        "role_b": "Second component kind",
        "role_compare_clear": "Clear comparison",
        "role_select_two": "Choose two different component kinds.",
        "role_summary": "{from} → {to}: {forward} relationships · {to} → {from}: {reverse} relationships. Direct cross-kind links only.",
        "story": "Guided story",
        "story_view": "Story view",
        "story_choose": "Choose a story",
        "story_start": "Start story",
        "story_previous": "Previous beat",
        "story_next": "Next beat",
        "story_clear": "Clear story",
        "story_status": "{label} · beat {step} of {total}: {beat}",
        "story_note": " · {note}",
        "guide_story": "Choose an authored guided view to follow its stable node and relationship IDs in order. Each beat highlights direct context only; the share link restores the exact beat.",
        "guide": "Diagram guide",
        "guide_search": "Search labels, stable IDs, kinds, evidence IDs, or relationship endpoints. Use arrow keys to select a result and press Enter.",
        "guide_focus": "Select a component or relationship for its semantic passport; hover or focus to preview its direct intent.",
        "guide_reach": "Use upstream or downstream reach to follow authored directed relationships.",
        "guide_route": "Choose two endpoints to probe an exact directed route; geometry never creates a route.",
        "guide_roles": "Compare two component kinds to highlight direct cross-kind relationships and show both directions.",
        "guide_keys": "Keyboard: / search · Enter or Space activate · S style · T theme · E export · R route · L semantic lens · M overview · F presentation · + and − zoom · 0 reset · ? guide · Escape close.",
        "passport": "Semantic passport",
        "passport_close": "Close passport",
        "passport_copy": "Copy deep link",
        "passport_copied": "Deep link copied.",
        "passport_copy_manual": "Clipboard access is unavailable; copy the link from the address bar.",
        "direct_relationships": "Direct relationships",
        "evidence_ids": "Evidence IDs",
        "map_depth": "MAP · stable IDs",
        "read_depth": "READ · labels and evidence",
        "full_depth": "FULL · complete authored facts",
        "kind_count": "matching elements",
        "component": "Component",
        "relationship_kind_label": "Relationship",
        "map_mode": "MAP · stable IDs only",
        "read_mode": "READ · labels and evidence",
        "full_mode": "FULL · exact authored facts",
        "depth_auto_status": "Auto · {depth}",
        "no_route_same_node": "Choose two different components for an authored route.",
        "route_steps": "Route steps",
        "previous_step": "Previous step",
        "next_step": "Next step",
        "stop_trace": "Stop trace",
        "route_card_title": "EXACT AUTHORED ROUTE",
        "reach_upstream_title": "AUTHORED UPSTREAM REACH",
        "reach_downstream_title": "AUTHORED DOWNSTREAM REACH",
        "no_reach": "No other component is reachable in that direction.",
        "presentation_exit": "Exit presentation",
        "presentation_fallback": "Presentation mode · use Escape or the exit button to return.",
        "pin_conflict": "This relationship has conflicting or incomplete identity data and cannot be opened.",
        "focus_node": "Focused component",
        "focus_edge": "Pinned relationship",
        "overview": "Diagram map · select a labeled node to focus or drag to pan",
        "confirmed": "Confirmed",
        "inferred": "Inferred",
        "unknown": "Unknown",
        "from": "From",
        "to": "To",
        "probe": "Probe exact route",
        "context": "Relationship context",
        "theme": "Dark theme",
        "visual_preset": "Visual style · Balanced",
        "visual_preset_status": "Visual style · {preset}",
        "preset_names": {"balanced": "Balanced", "signal": "Signal", "mono": "Monochrome"},
        "route_nodes_omitted": "+{count} components omitted",
        "route_edges_omitted": "+{count} relationships omitted",
        "components_count": "components",
        "contrast": "High contrast",
        "presentation": "Presentation",
        "trace": "Trace route",
        "zoom_in": "Zoom in",
        "zoom_out": "Zoom out",
        "zoom_reset": "Reset zoom",
        "export": "Export canonical diagram",
        "png": "PNG",
        "png_copy": "Copy PNG",
        "png_copied": "PNG copied to clipboard.",
        "png_copy_unavailable": "PNG clipboard access is unavailable; the image was downloaded instead.",
        "png_copy_failed": "Clipboard copy failed; the image was downloaded instead.",
        "jpeg": "JPEG",
        "webp": "WebP",
        "svg_pair": "Light and dark SVG",
        "svg_auto": "Adaptive SVG",
        "webm": "Finite WebM trace",
        "route_card": "Exact route card",
        "reach_card": "Reach card",
        "status": "Choose a component or an authored route to inspect.",
        "preview": "Live preview",
        "preview_current": "Live preview · current",
        "preview_last_good": "Live preview · showing last good build",
        "preview_reconnecting": "Live preview · reconnecting",
        "noscript": "Interactive controls need JavaScript. The SVG, text outline, and evidence remain available below.",
        "no_match": "No matching component found.",
        "no_route": "No authored directed route exists between those components.",
        "choose_component": "Choose a component first.",
        "choose_route": "Choose a component or an authored route to inspect.",
        "all_visible": "All diagram elements are visible.",
        "incoming": "Incoming",
        "outgoing": "Outgoing",
        "confirmed_relationships": "Confirmed relationships",
        "uncertain_relationships": "Inferred or unknown relationships",
        "radar_in": "UPSTREAM",
        "radar_out": "DOWNSTREAM",
        "exact_route": "Exact authored route",
        "relationships_count": "authored relationships",
        "relation": "Relationship",
        "trace": "Route trace",
        "trace_complete": "Route trace complete.",
        "no_route_card": "Choose a route that exists in authored relationships first.",
        "no_reach_card": "Choose a component before exporting its reach card.",
        "exported": "exported from the canonical diagram.",
        "route_card_exported": "Exact route card exported from authored relationships.",
        "reach_card_exported": "Exact reach card exported from authored relationships.",
        "reach_components_heading": "Reachable components · {count}",
        "reach_relationships_heading": "Authored relationships · {count}",
        "reach_components_omitted": "+{count} components omitted",
        "reach_relationships_omitted": "+{count} relationships omitted",
        "passport_upstream": "Upstream · {direct} direct, {reachable} reachable",
        "passport_downstream": "Downstream · {direct} direct, {reachable} reachable",
        "reduced_motion": "Reduced motion is enabled; the exact route is highlighted without animation.",
        "export_unavailable": "This browser does not support that export.",
        "webm_unavailable": "WebM export is unavailable in this browser.",
        "recording_failed": "WebM recording failed.",
        "webm_trace": "Finite WebM trace",
        "upstream_status": "components and authored upstream relationships",
        "downstream_status": "components and authored downstream relationships",
        "export_failed": "Export failed.",
    },
    "th": {
        "tools": "สำรวจ",
        "search": "ค้นหาองค์ประกอบหรือความสัมพันธ์",
        "search_results": "ผลการค้นหา",
        "search_result_count": "พบ {count} รายการ ใช้ปุ่มลูกศรเลือกผลลัพธ์",
        "search_result_empty": "ไม่พบองค์ประกอบหรือความสัมพันธ์ที่ตรงกัน",
        "search_choose_result": "ใช้ปุ่มลูกศรเลือกผลลัพธ์ แล้วกด Enter",
        "focus": "โฟกัสองค์ประกอบ",
        "focus_one": "โฟกัส",
        "upstream": "ดูเส้นทางขาเข้า",
        "downstream": "ดูเส้นทางขาออก",
        "clear": "ล้างโฟกัส",
        "lens": "เลนส์ความหมาย",
        "certainty_lens": "ระดับความเชื่อมั่นของหลักฐาน",
        "all": "หลักฐานทั้งหมด",
        "all_kinds": "องค์ประกอบและความสัมพันธ์ทุกชนิด",
        "component_kind": "ชนิดองค์ประกอบ",
        "relationship_kind": "ชนิดความสัมพันธ์",
        "role_compare": "เทียบบทบาทองค์ประกอบ",
        "role_a": "ชนิดองค์ประกอบแรก",
        "role_b": "ชนิดองค์ประกอบที่สอง",
        "role_compare_clear": "ล้างการเปรียบเทียบ",
        "role_select_two": "เลือกชนิดองค์ประกอบสองชนิดที่ต่างกัน",
        "role_summary": "{from} → {to}: {forward} ความสัมพันธ์ · {to} → {from}: {reverse} ความสัมพันธ์ · เน้นเฉพาะเส้นตรงข้ามชนิด",
        "story": "เรื่องราวแบบนำทาง",
        "story_view": "มุมมองเรื่องราว",
        "story_choose": "เลือกเรื่องราว",
        "story_start": "เริ่มเรื่องราว",
        "story_previous": "ขั้นก่อนหน้า",
        "story_next": "ขั้นถัดไป",
        "story_clear": "ล้างเรื่องราว",
        "story_status": "{label} · ขั้น {step} จาก {total}: {beat}",
        "story_note": " · {note}",
        "guide_story": "เลือกมุมมองที่ผู้เขียนเรียงไว้ เพื่อตามรหัสองค์ประกอบและความสัมพันธ์ทีละขั้น แต่ละขั้นเน้นเฉพาะบริบทโดยตรงและแชร์ลิงก์กลับมายังขั้นเดิมได้",
        "guide": "คู่มือแผนภาพ",
        "guide_search": "ค้นหาด้วยชื่อ รหัส ชนิด หลักฐาน หรือปลายทางของความสัมพันธ์ ใช้ปุ่มลูกศรเลือกแล้วกด Enter",
        "guide_focus": "เลือกองค์ประกอบหรือความสัมพันธ์เพื่อดูข้อมูลความหมาย; ชี้หรือโฟกัสเพื่อดูความเชื่อมโยงโดยตรง",
        "guide_reach": "ใช้เส้นทางขาเข้าและขาออกเพื่อตามความสัมพันธ์แบบมีทิศทางที่ผู้เขียนระบุ",
        "guide_route": "เลือกจุดเริ่มและจุดหมายเพื่อตรวจเส้นทางจริง โดยไม่อนุมานจากตำแหน่งภาพ",
        "guide_roles": "เทียบชนิดองค์ประกอบสองชนิดเพื่อเน้นความสัมพันธ์ข้ามชนิดโดยตรง พร้อมนับแยกตามทิศทาง",
        "guide_keys": "แป้นพิมพ์: / ค้นหา · Enter หรือ Space เลือก · S เปลี่ยนรูปแบบ · T เปลี่ยนธีม · E ส่งออก · R ตรวจเส้นทาง · L เลนส์ความหมาย · M ภาพรวม · F โหมดนำเสนอ · + และ − ขยาย/ย่อ · 0 คืนค่า · ? คู่มือ · Escape ปิด",
        "passport": "ข้อมูลความหมาย",
        "passport_close": "ปิดข้อมูล",
        "passport_copy": "คัดลอกลิงก์ตรง",
        "passport_copied": "คัดลอกลิงก์แล้ว",
        "passport_copy_manual": "เบราว์เซอร์ไม่อนุญาตคลิปบอร์ด ให้คัดลอกจากแถบที่อยู่",
        "direct_relationships": "ความสัมพันธ์โดยตรง",
        "evidence_ids": "รหัสหลักฐาน",
        "map_depth": "แผนที่ · รหัสองค์ประกอบ",
        "read_depth": "อ่าน · ชื่อและหลักฐาน",
        "full_depth": "เต็ม · ข้อเท็จจริงที่ผู้เขียนระบุ",
        "kind_count": "องค์ประกอบที่ตรงกัน",
        "component": "องค์ประกอบ",
        "relationship_kind_label": "ความสัมพันธ์",
        "map_mode": "แผนที่ · แสดงเฉพาะรหัส",
        "read_mode": "อ่าน · ชื่อและหลักฐาน",
        "full_mode": "เต็ม · ข้อเท็จจริงที่ระบุไว้",
        "depth_auto_status": "อัตโนมัติ · {depth}",
        "no_route_same_node": "เลือกองค์ประกอบต้นทางและปลายทางคนละรายการ",
        "route_steps": "ลำดับเส้นทาง",
        "previous_step": "ขั้นก่อนหน้า",
        "next_step": "ขั้นถัดไป",
        "stop_trace": "หยุดไล่เส้นทาง",
        "route_card_title": "เส้นทางตรงตามที่ระบุ",
        "reach_upstream_title": "เส้นทางขาเข้าตามที่ระบุ",
        "reach_downstream_title": "เส้นทางขาออกตามที่ระบุ",
        "no_reach": "ไม่มีองค์ประกอบอื่นที่ไปถึงได้ในทิศทางนี้",
        "presentation_exit": "ออกจากโหมดนำเสนอ",
        "presentation_fallback": "โหมดนำเสนอ · กด Escape หรือปุ่มออกเพื่อกลับ",
        "pin_conflict": "ข้อมูลประจำความสัมพันธ์ขัดแย้งหรือไม่ครบ จึงเปิดดูไม่ได้",
        "focus_node": "องค์ประกอบที่เลือก",
        "focus_edge": "ความสัมพันธ์ที่ปักหมุด",
        "overview": "แผนที่นำทาง · เลือกจุดที่มีรหัสเพื่อโฟกัส หรือลากเพื่อเลื่อนแผนภาพ",
        "confirmed": "ยืนยัน",
        "inferred": "อนุมาน",
        "unknown": "ไม่ทราบ",
        "from": "จาก",
        "to": "ถึง",
        "probe": "ตรวจเส้นทางจริง",
        "context": "บริบทความสัมพันธ์",
        "theme": "สลับธีม",
        "visual_preset": "สไตล์",
        "visual_preset_status": "รูปแบบภาพ · {preset}",
        "preset_names": {"balanced": "สมดุล", "signal": "สัญญาณ", "mono": "ขาวดำ"},
        "route_nodes_omitted": "ตัดองค์ประกอบออก {count} รายการ",
        "route_edges_omitted": "ตัดความสัมพันธ์ออก {count} รายการ",
        "components_count": "องค์ประกอบ",
        "contrast": "คอนทราสต์สูง",
        "presentation": "นำเสนอ",
        "trace": "ไล่เส้นทาง",
        "zoom_in": "ขยาย",
        "zoom_out": "ย่อ",
        "zoom_reset": "คืนค่าขนาด",
        "export": "ส่งออก",
        "png": "PNG",
        "png_copy": "คัดลอก PNG",
        "png_copied": "คัดลอก PNG ไปคลิปบอร์ดแล้ว",
        "png_copy_unavailable": "เบราว์เซอร์ไม่อนุญาตคลิปบอร์ด PNG จึงดาวน์โหลดรูปแทนแล้ว",
        "png_copy_failed": "คัดลอกคลิปบอร์ดไม่สำเร็จ จึงดาวน์โหลดรูปแทนแล้ว",
        "jpeg": "JPEG",
        "webp": "WebP",
        "svg_pair": "SVG ธีมสว่างและมืด",
        "svg_auto": "SVG ปรับตามธีม",
        "webm": "WebM ไล่เส้นทาง",
        "route_card": "การ์ดเส้นทางจริง",
        "reach_card": "การ์ดเส้นทางเชื่อมโยง",
        "status": "เลือกองค์ประกอบหรือเส้นทางที่ระบุไว้เพื่อสำรวจ",
        "preview": "พรีวิวสด",
        "preview_current": "พรีวิวสด · ปัจจุบัน",
        "preview_last_good": "พรีวิวสด · กำลังแสดงฉบับล่าสุดที่ผ่าน",
        "preview_reconnecting": "พรีวิวสด · กำลังเชื่อมต่อใหม่",
        "noscript": "ส่วนควบคุมต้องใช้ JavaScript แต่ SVG ตารางข้อความ และหลักฐานยังอ่านได้ด้านล่าง",
        "no_match": "ไม่พบองค์ประกอบที่ค้นหา",
        "no_route": "ไม่พบเส้นทางตามทิศทางความสัมพันธ์ที่ผู้เขียนระบุ",
        "choose_component": "เลือกองค์ประกอบก่อน",
        "choose_route": "เลือกองค์ประกอบหรือเส้นทางที่ระบุไว้เพื่อสำรวจ",
        "all_visible": "แสดงองค์ประกอบทั้งหมดแล้ว",
        "incoming": "ขาเข้า",
        "outgoing": "ขาออก",
        "confirmed_relationships": "ความสัมพันธ์ที่ยืนยัน",
        "uncertain_relationships": "ความสัมพันธ์ที่อนุมานหรือไม่ทราบ",
        "radar_in": "ขาเข้า",
        "radar_out": "ขาออก",
        "exact_route": "เส้นทางตรงตามที่ระบุ",
        "relationships_count": "ความสัมพันธ์ที่ระบุ",
        "relation": "ความสัมพันธ์",
        "trace": "ไล่เส้นทาง",
        "trace_complete": "ไล่เส้นทางครบแล้ว",
        "no_route_card": "เลือกเส้นทางที่มีอยู่ในความสัมพันธ์ก่อน",
        "no_reach_card": "เลือกองค์ประกอบก่อนส่งออกการ์ดเส้นทางเชื่อมโยง",
        "exported": "ส่งออกจากแผนภาพต้นฉบับแล้ว",
        "route_card_exported": "ส่งออกการ์ดเส้นทางตามความสัมพันธ์ที่ระบุแล้ว",
        "reach_card_exported": "ส่งออกการ์ดเส้นทางเชื่อมโยงตามความสัมพันธ์ที่ระบุแล้ว",
        "reach_components_heading": "องค์ประกอบที่ไปถึงได้ · {count}",
        "reach_relationships_heading": "ความสัมพันธ์ที่ระบุ · {count}",
        "reach_components_omitted": "ตัดองค์ประกอบออก {count} รายการ",
        "reach_relationships_omitted": "ตัดความสัมพันธ์ออก {count} รายการ",
        "passport_upstream": "ขาเข้า · โดยตรง {direct} รายการ ไปถึงได้ {reachable} รายการ",
        "passport_downstream": "ขาออก · โดยตรง {direct} รายการ ไปถึงได้ {reachable} รายการ",
        "reduced_motion": "เปิดการลดการเคลื่อนไหว จึงไฮไลต์เส้นทางโดยไม่เล่นภาพเคลื่อนไหว",
        "export_unavailable": "เบราว์เซอร์นี้ไม่รองรับการส่งออกรูปแบบดังกล่าว",
        "webm_unavailable": "เบราว์เซอร์นี้ไม่รองรับการส่งออก WebM",
        "recording_failed": "บันทึก WebM ไม่สำเร็จ",
        "webm_trace": "WebM ไล่เส้นทางแบบจำกัดเวลา",
        "upstream_status": "องค์ประกอบและความสัมพันธ์ขาเข้าที่ระบุไว้",
        "downstream_status": "องค์ประกอบและความสัมพันธ์ขาออกที่ระบุไว้",
        "export_failed": "ส่งออกไม่สำเร็จ",
    },
}

SVG_CSS = """
text{font-family:Inter,'Segoe UI',Tahoma,Arial,sans-serif;fill:#18222e}
.canvas{fill:#f2f4f6}.paper{fill:#fff;stroke:#d7dee6;stroke-width:1.2}
.header-kicker{font-size:12px;font-weight:700;letter-spacing:1.8px;fill:#087f8c}
.title{font-size:28px;font-weight:720}.summary{font-size:14px;fill:#596878}
.provenance{font-size:11px;fill:#596878;font-family:ui-monospace,Consolas,monospace}
.group-box{fill:#f8fafb;stroke:#8190a3;stroke-width:1.3;stroke-dasharray:7 5}
.group-inferred{stroke-dasharray:2 4}.group-unknown{stroke:#a34e3d;stroke-dasharray:2 4}.group-title{font-size:13px;font-weight:700;fill:#344457}
.node-shape{stroke:#526174;stroke-width:1.7}.node-service{fill:#e5f3f5;stroke:#147b87}.node-data{fill:#e8f5ed;stroke:#287a55}
.node-external{fill:#edf0f4;stroke:#596779;stroke-dasharray:7 4}.node-decision{fill:#fff2d8;stroke:#9a6510}
.node-unknown{fill:#fff0ec;stroke:#a34e3d;stroke-dasharray:2 4;stroke-width:2}
.node-inferred{stroke-dasharray:7 4}.node-id{font-size:10px;font-weight:700;fill:#596878;font-family:ui-monospace,Consolas,monospace}
.node-label{font-size:16px;font-weight:650;text-anchor:middle}
.certainty-mark{font-size:10px;font-weight:800;fill:#596878}.unknown-mark{fill:#a34e3d}
.edge{fill:none;stroke:#596878;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;marker-end:url(#arrow)}
.edge-data{stroke:#087f8c;stroke-width:2.1}.edge-event,.edge-async{stroke-dasharray:2 5}.edge-return,.edge-feedback{stroke-dasharray:7 5}
.edge-affirmative{stroke:#16705c;stroke-width:2.4}.edge-alternative{stroke:#a86407;stroke-width:2.2;stroke-dasharray:7 4}.edge-error{stroke:#a34e3d;stroke-width:2.2;stroke-dasharray:2 4}
.edge-inferred{stroke-dasharray:8 4}.edge-unknown{stroke:#a34e3d;stroke-dasharray:2 4;stroke-width:2}
.edge-label-bg{fill:#fff;stroke:#d7dee6;stroke-width:1}.edge-label{font-size:13px;font-weight:560;text-anchor:middle}
.lifeline{stroke:#9aabc1;stroke-width:1.3;stroke-dasharray:5 6}
.participant{fill:#edf3ff;stroke:#45617f;stroke-width:1.6}.participant-unknown{fill:#fff2e9;stroke:#8a4921;stroke-dasharray:2 4}
.legend{font-size:12px;fill:#596878}.legend-title{font-size:12px;font-weight:700;fill:#344457}
.legend-line{stroke:#596878;stroke-width:1.8}.legend-dash{stroke-dasharray:7 5}.legend-dot{stroke-dasharray:2 4}
.flow-arrow{fill:#596878}.terminal-dot{fill:#087f8c}
""".strip()

HTML_CSS = """
:root{color-scheme:light;--ink:#17253c;--muted:#52637d;--line:#dbe3ef;--paper:#fff;--canvas:#f6f8fc;--accent:#2455d6}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--ink);font:16px/1.55 Inter,'Segoe UI',Tahoma,Arial,sans-serif}
main{max-width:1440px;margin:0 auto;padding:32px clamp(16px,4vw,56px) 48px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.provenance{font:12px/1.5 ui-monospace,Consolas,monospace}
figure{margin:0 auto 26px;max-width:1280px;padding:10px;border:1px solid var(--line);border-radius:18px;background:#fff;box-shadow:0 14px 38px rgba(26,48,82,.08);overflow:auto}
figure svg{display:block;width:100%;height:auto;min-width:700px}section{max-width:1180px;margin:22px auto 0}h2{font-size:18px;margin:0 0 10px}.alt-table,.evidence-table{width:100%;border-collapse:collapse;background:var(--paper);border:1px solid var(--line);font-size:14px}
th,td{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;background:#f8faff}.table-wrap{max-width:100%;overflow:auto;overscroll-behavior-x:contain;margin:12px 0}.table-wrap>.alt-table,.table-wrap>.evidence-table{min-width:680px}.table-wrap caption{text-align:left;padding:8px 12px;color:var(--muted);font-weight:650}.table-wrap:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
code{font:12px ui-monospace,Consolas,monospace;overflow-wrap:anywhere}.certainty{font-weight:700}.unknown{color:#7a3f1f}.inferred{color:#334f82}.confirmed{color:#27614f}
details{max-width:1180px;margin:24px auto 0;border:1px solid var(--line);border-radius:12px;background:#fff}summary{padding:14px 16px;font-weight:700;cursor:pointer}details .table-wrap{padding:0 16px 16px;overflow:auto}
footer{max-width:1180px;margin:30px auto 0;color:var(--muted);font-size:12px}
@media print{body{background:#fff}main{max-width:none;padding:0}.diagram-tools,.export-tools,#presentation-exit{display:none!important}figure{border:0;box-shadow:none;padding:0;overflow:visible;break-inside:avoid}figure svg{min-width:0}figure svg .is-muted,figure svg .is-highlighted,figure svg .is-intent-preview{opacity:1!important;filter:none!important}figure svg .is-highlighted .node-shape{stroke:#45617f!important;stroke-width:1.7!important}figure svg .is-highlighted path.edge{stroke:#52637d!important;stroke-width:1.8!important}#diagram-body[data-depth="map"] figure svg .node-label,#diagram-body[data-depth="map"] figure svg .edge-label,#diagram-body[data-depth="map"] figure svg .edge-label-bg,#diagram-body[data-depth="map"] figure svg .certainty-mark{display:revert!important;visibility:visible!important}details{break-before:page}details:not([open])>*:not(summary){display:block}footer{display:none}}
.diagram-tools{max-width:1280px;margin:0 auto 18px;padding:16px 18px;border:1px solid var(--line);border-radius:14px;background:var(--paper);box-shadow:0 4px 14px rgba(26,48,82,.05)}
.tool-row{display:flex;flex-wrap:wrap;align-items:end;gap:10px;margin:8px 0}.tool-field{display:grid;gap:4px;min-width:150px;flex:1}.tool-field label,.tool-caption{font-size:12px;font-weight:700;color:var(--muted)}.tool-field input,.tool-field select{width:100%;min-width:0;max-width:100%}.search-field{position:relative}.search-results{position:absolute;z-index:20;top:100%;left:0;right:0;max-height:min(360px,60vh);overflow:auto;border:1px solid var(--line);border-radius:8px;background:var(--paper);box-shadow:0 10px 24px rgba(26,48,82,.18)}.search-results[hidden]{display:none}.search-result{padding:8px 10px;border-bottom:1px solid var(--line);font-size:12px;cursor:pointer}.search-result:last-child{border-bottom:0}.search-result[aria-selected="true"],.search-result:hover{background:rgba(36,85,214,.12)}
input,select,button{min-height:38px;border:1px solid #a8b5c8;border-radius:8px;padding:7px 10px;background:var(--paper);color:var(--ink);font:inherit}
button{cursor:pointer;font-size:13px;font-weight:650}button:hover{border-color:var(--accent);background:#eef3ff}button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #7aa2ff;outline-offset:2px}
button:disabled{cursor:not-allowed;opacity:.55}
.tool-status{display:block;min-height:1.6em;margin:8px 0 0;color:var(--muted);font-size:13px}.preview-status{float:right;color:#28644f;font-size:12px;font-weight:700}
.relationship-context{display:flex;flex-wrap:wrap;align-items:start;gap:7px;margin-top:6px;min-width:0}.context-metric{border:1px solid var(--line);border-radius:999px;padding:3px 9px;color:var(--muted);font-size:12px}
.relationship-context svg{display:block;width:min(100%,560px);height:auto;border:1px solid var(--line);border-radius:9px;background:var(--canvas)}.radar-line{stroke:#b5c1d1;stroke-width:1.4}.radar-hub-line{stroke:#52637d;stroke-width:2}.radar-up{fill:#e3ecff;stroke:#2455d6;stroke-width:1.4}.radar-down{fill:#e5f4ee;stroke:#26725b;stroke-width:1.4}.radar-hub{fill:#17253c;stroke:#2455d6;stroke-width:2}.radar-node-index{font:700 8px ui-monospace,Consolas,monospace;fill:#17253c}.radar-label{font:9px 'Segoe UI',Arial,sans-serif;fill:#52637d;font-weight:700;letter-spacing:.07em}
.context-neighbors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 12px;width:min(100%,560px);min-width:0}.context-neighbor-group{min-width:0}.context-neighbor-heading{display:block;margin-bottom:3px;color:var(--muted);font-size:11px}.context-neighbor-list{display:flex;flex-wrap:wrap;gap:4px;min-width:0}.context-neighbor{display:inline-flex;align-items:flex-start;gap:4px;max-width:100%;min-width:0;border:1px solid var(--line);border-radius:6px;padding:2px 5px;color:var(--ink);font-size:11px}.context-neighbor-index{flex:0 0 auto;color:var(--accent);font-weight:700}.context-neighbor code{min-width:0;white-space:normal;overflow-wrap:anywhere;font-size:10px}.context-neighbor-more{align-self:center;color:var(--muted);font-size:11px}
.diagram-overview{margin-top:8px;max-width:620px}.diagram-overview svg{display:block;width:100%;height:150px;border:1px solid var(--line);border-radius:9px;background:var(--canvas);touch-action:none;cursor:grab}.diagram-overview svg:active{cursor:grabbing}.overview-edge{stroke:var(--muted);stroke-opacity:.42;stroke-width:1.5}.overview-node{cursor:pointer}.overview-hit{fill:transparent;pointer-events:all}.overview-marker{stroke-width:1.7;vector-effect:non-scaling-stroke}.overview-node-action .overview-marker{fill:var(--paper);stroke:#637085}.overview-node-start .overview-marker{fill:#e3efff;stroke:#2455d6}.overview-node-decision .overview-marker{fill:#fff0cf;stroke:#a86407}.overview-node-terminal .overview-marker{fill:#dff5ee;stroke:#16705c}.overview-node:focus .overview-marker{stroke:#b45309;stroke-width:3.2}.overview-node-id{font:9px ui-monospace,Consolas,monospace;font-weight:650;fill:var(--ink);paint-order:stroke;stroke:var(--canvas);stroke-width:3px;stroke-linejoin:round;pointer-events:none}.overview-viewport{fill:var(--accent-soft);fill-opacity:.55;stroke:var(--accent);stroke-width:2.5;pointer-events:none}.overview-caption{margin:4px 0;color:var(--muted);font-size:12px}
.diagram-tools .overview-drawer{margin:8px 0 12px;border:0;background:transparent}
.diagram-tools .overview-drawer>summary{display:inline-flex;min-height:34px;align-items:center;gap:7px;border:1px solid var(--line);border-radius:7px;padding:5px 10px;background:var(--paper);font-size:12px;list-style:none}.diagram-tools .overview-drawer>summary::-webkit-details-marker{display:none}.diagram-tools .overview-drawer>summary::before{content:"＋";color:var(--muted);font-weight:800}.diagram-tools .overview-drawer[open]>summary::before{content:"−";color:var(--accent)}
.diagram-tools .overview-drawer[open] .diagram-overview{max-width:480px;margin:8px 0 0}
.semantic-passport{margin:12px 0 4px;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--canvas)}.passport-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.passport-heading h3{margin:0;font-size:15px}.passport-heading div{display:flex;gap:8px;flex-wrap:wrap}.passport-facts{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}.passport-fact{border:1px solid var(--line);border-radius:7px;padding:5px 8px;color:var(--muted);font-size:12px}.passport-relationships{margin:8px 0;padding-left:22px}.passport-relationships li{margin:4px 0}.route-details{margin:10px 0;padding:10px 12px;border-left:3px solid var(--accent);background:var(--canvas)}.route-details ol{margin:6px 0;padding-left:22px}.viewer-guide{margin:10px 0;border:1px solid var(--line);border-radius:9px;background:var(--canvas)}.viewer-guide summary{padding:7px 10px;font-size:13px}.viewer-guide ul{margin:0;padding:0 30px 12px}.viewer-guide li{margin:5px 0;font-size:13px}
.route-journey{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px}.route-journey output{color:var(--muted);font-size:13px}#route-journey[hidden]{display:none}#diagram-depth button[aria-pressed="true"]{border-color:var(--accent);background:var(--accent-soft)}figure svg [tabindex="0"]:focus{outline:none;filter:drop-shadow(0 0 3px rgba(36,85,214,.75))}.passport-evidence{margin:3px 0}.passport-evidence a{font-family:ui-monospace,Consolas,monospace}#diagram-body[data-depth="map"] figure svg .node-label,#diagram-body[data-depth="map"] figure svg .edge-label,#diagram-body[data-depth="map"] figure svg .edge-label-bg,#diagram-body[data-depth="map"] figure svg .certainty-mark{display:none}#diagram-body[data-depth="full"] figure svg .node-label,#diagram-body[data-depth="full"] figure svg .edge-label{font-weight:700}
.export-tools{max-width:1280px;margin:0 auto 18px;border:1px solid var(--line);border-radius:12px;background:var(--paper)}.export-tools summary{padding:11px 14px;font-size:14px}.export-grid{display:flex;flex-wrap:wrap;gap:8px;padding:0 14px 14px}
figure svg .is-muted{opacity:.13}figure svg .is-highlighted{opacity:1!important}figure svg .is-highlighted .node-shape{stroke:#b45309;stroke-width:3.2}figure svg .is-highlighted path.edge{stroke:#b45309;stroke-width:3.2}figure svg .is-intent-preview{opacity:1!important;filter:drop-shadow(0 1px 3px rgba(180,83,9,.65))}
body[data-depth="map"] figure svg .node-label,body[data-depth="map"] figure svg .edge-label,body[data-depth="map"] figure svg .edge-label-bg,body[data-depth="map"] figure svg .certainty-mark{visibility:hidden}body[data-depth="map"] figure svg [data-node-id].is-highlighted .node-label,body[data-depth="map"] figure svg [data-edge-id].is-highlighted .edge-label,body[data-depth="map"] figure svg [data-edge-id].is-highlighted .edge-label-bg{visibility:visible}body[data-depth="full"] figure svg .node-label{font-size:18px}body[data-depth="full"] figure svg .edge-label{font-size:15px}
body[data-theme="dark"]{color-scheme:dark;--ink:#e8edf6;--muted:#b1bfd3;--line:#52647c;--paper:#172235;--canvas:#101827;--accent:#8db0ff}
body[data-theme="dark"] figure,body[data-theme="dark"] details{background:#172235;border-color:#52647c}body[data-theme="dark"] th{background:#202d42;color:#b1bfd3}body[data-theme="dark"] .unknown{color:#ffb58c}
body[data-theme="dark"] figure svg .canvas{fill:#101827}body[data-theme="dark"] figure svg .paper{fill:#172235;stroke:#52647c}body[data-theme="dark"] figure svg text{fill:#e8edf6}body[data-theme="dark"] figure svg .header-kicker{fill:#8db0ff}body[data-theme="dark"] figure svg .summary,body[data-theme="dark"] figure svg .provenance,body[data-theme="dark"] figure svg .legend,body[data-theme="dark"] figure svg .node-id,body[data-theme="dark"] figure svg .certainty-mark,body[data-theme="dark"] figure svg .group-title{fill:#c0ccdd}
body[data-theme="dark"] figure svg .node-service,body[data-theme="dark"] figure svg .participant{fill:#263753}body[data-theme="dark"] figure svg .node-data{fill:#183b3d}body[data-theme="dark"] figure svg .node-external{fill:#303746}body[data-theme="dark"] figure svg .node-decision{fill:#4b3a1b}body[data-theme="dark"] figure svg .node-unknown,body[data-theme="dark"] figure svg .participant-unknown{fill:#482e24}body[data-theme="dark"] figure svg .edge-label-bg{fill:#172235;stroke:#52647c}body[data-theme="dark"] figure svg .group-box{fill:#202d42;stroke:#8798b2}body[data-theme="dark"] figure svg .lifeline{stroke:#77879e}
body[data-theme="dark"] figure svg .edge,body[data-theme="dark"] figure svg .legend-line{stroke:#c0ccdd}body[data-theme="dark"] figure svg .flow-arrow{fill:#c0ccdd}
body[data-theme="dark"] .radar-line{stroke:#667991}body[data-theme="dark"] .radar-hub{fill:#273752}body[data-theme="dark"] .radar-node-id{fill:#e8edf6}body[data-theme="dark"] .radar-label{fill:#c0ccdd}
body[data-visual-preset="signal"] figure svg .node-service,body[data-visual-preset="signal"] figure svg .participant{fill:#e3efff;stroke:#2455d6}body[data-visual-preset="signal"] figure svg .node-data{fill:#dff5ee;stroke:#16705c}body[data-visual-preset="signal"] figure svg .node-external{fill:#eef1f5;stroke:#637085}body[data-visual-preset="signal"] figure svg .node-decision{fill:#fff0cf;stroke:#a86407}body[data-visual-preset="signal"] figure svg .edge-data,body[data-visual-preset="signal"] figure svg .terminal-dot{stroke:#0f7aa3;fill:#0f7aa3}body[data-visual-preset="signal"] figure svg .header-kicker{fill:#0f7aa3}
body[data-theme="dark"][data-visual-preset="signal"] figure svg .node-service,body[data-theme="dark"][data-visual-preset="signal"] figure svg .participant{fill:#233e61;stroke:#8db0ff}body[data-theme="dark"][data-visual-preset="signal"] figure svg .node-data{fill:#19433d;stroke:#70d3b3}body[data-theme="dark"][data-visual-preset="signal"] figure svg .node-external{fill:#323b49;stroke:#a7b4c8}body[data-theme="dark"][data-visual-preset="signal"] figure svg .node-decision{fill:#4e3d21;stroke:#f0bd63}body[data-theme="dark"][data-visual-preset="signal"] figure svg .edge-data,body[data-theme="dark"][data-visual-preset="signal"] figure svg .terminal-dot{stroke:#66c6e6;fill:#66c6e6}body[data-theme="dark"][data-visual-preset="signal"] figure svg .header-kicker{fill:#66c6e6}
body[data-visual-preset="mono"] figure svg .node-shape,body[data-visual-preset="mono"] figure svg .participant,body[data-visual-preset="mono"] figure svg .group-box{fill:#eceff3;stroke:#364152}body[data-visual-preset="mono"] figure svg .edge,body[data-visual-preset="mono"] figure svg .legend-line{stroke:#364152}body[data-visual-preset="mono"] figure svg .flow-arrow,body[data-visual-preset="mono"] figure svg .terminal-dot{fill:#364152}body[data-visual-preset="mono"] figure svg .header-kicker{fill:#364152}
body[data-theme="dark"][data-visual-preset="mono"] figure svg .node-shape,body[data-theme="dark"][data-visual-preset="mono"] figure svg .participant,body[data-theme="dark"][data-visual-preset="mono"] figure svg .group-box{fill:#27313c;stroke:#cbd5e1}body[data-theme="dark"][data-visual-preset="mono"] figure svg .edge,body[data-theme="dark"][data-visual-preset="mono"] figure svg .legend-line{stroke:#cbd5e1}body[data-theme="dark"][data-visual-preset="mono"] figure svg .flow-arrow,body[data-theme="dark"][data-visual-preset="mono"] figure svg .terminal-dot{fill:#cbd5e1}body[data-theme="dark"][data-visual-preset="mono"] figure svg .header-kicker{fill:#cbd5e1}
body.high-contrast figure svg .node-shape,body.high-contrast figure svg .edge,body.high-contrast figure svg .group-box{stroke-width:2.8}body.high-contrast .tool-status{font-weight:700}
body.presentation main{max-width:none;padding:8px}body.presentation .diagram-tools,body.presentation .export-tools,body.presentation section,body.presentation details,body.presentation footer{display:none}body.presentation section.diagram-tools{display:block!important;position:static;margin:0;padding:0;border:0;background:transparent;box-shadow:none}body.presentation .diagram-tools>:not(#presentation-exit){display:none!important}body.presentation figure{max-width:none;margin:0;padding:0;border:0;box-shadow:none;border-radius:0}body.presentation figure svg{min-width:0;width:100%!important;height:auto!important}body.presentation figure svg .header-kicker,body.presentation figure svg .title,body.presentation figure svg .summary,body.presentation figure svg .provenance{display:revert!important}#presentation-exit{display:none;position:fixed;z-index:10;right:16px;top:16px}body.presentation #presentation-exit{display:block}
@media(max-width:700px){.diagram-tools{padding:12px}.tool-row{min-width:0}.tool-field{min-width:0;width:100%;flex:1 1 100%}.tool-row>button{max-width:100%;white-space:normal;overflow-wrap:anywhere}.preview-status{float:none;display:block}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;transition-duration:.01ms!important}}
""".strip()

ZOOM_CSS_STEPS = tuple(range(60, 251, 5))
HTML_CSS += "\n" + "".join(
    f'figure[data-zoom="{step}"] svg{{width:max({step}%,{step * 7}px);min-width:0}}'
    for step in ZOOM_CSS_STEPS
)

HTML_CSS += """
:root{color-scheme:light;--ink:#18222e;--muted:#596878;--line:#d7dee6;--paper:#fff;--canvas:#eef1f4;--accent:#087f8c;--accent-soft:#d8eef0}
body{background:var(--canvas);color:var(--ink)}main{max-width:1680px;padding:12px clamp(12px,2vw,28px) 32px}
.diagram-tools{max-width:none;margin:0 auto 10px;padding:8px;border-radius:12px;background:var(--paper);box-shadow:none}
.primary-toolbar{display:flex;align-items:center;gap:8px}.primary-toolbar .search-field{flex:1 1 auto;max-width:660px;min-width:210px}.primary-toolbar .search-field input{min-height:42px}
.primary-actions{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap}.primary-actions>button,.primary-actions>.export-tools>summary{min-height:36px;padding:6px 10px;font-size:12px}
button{border-color:var(--line);border-radius:7px;font-size:12px;letter-spacing:.005em}button:hover{border-color:var(--accent);background:var(--accent-soft)}
.explore-tools{max-width:none;margin:4px 0 0;border:0;background:transparent}.explore-tools>summary{display:inline-flex;align-items:center;gap:6px;padding:4px 7px;color:var(--muted);font-size:12px;list-style:none}.explore-tools>summary::-webkit-details-marker{display:none}.explore-tools>summary::before{content:"＋";font-weight:800}.explore-tools[open]>summary::before{content:"−";color:var(--accent)}.advanced-tools{padding:4px 8px 2px;border-top:1px solid var(--line)}
.advanced-tools .tool-row{margin:8px 0}.advanced-tools .tool-field{max-width:360px}.advanced-tools .tool-status{margin:4px 0}
.story-explorer{display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap;margin:10px 0;padding:10px 0;border-top:1px solid var(--line)}.story-explorer .tool-field{flex:1 1 220px}.story-explorer .tool-status{flex:1 1 100%;margin:0;color:var(--ink)}
.export-tools{position:relative;max-width:none;margin:0;border:1px solid var(--line);border-radius:7px;background:var(--paper)}.export-tools summary{padding:6px 10px;font-size:12px}.export-tools[open] .export-grid{position:absolute;z-index:15;right:0;top:calc(100% + 6px);width:min(420px,90vw);padding:10px;border:1px solid var(--line);border-radius:10px;background:var(--paper);box-shadow:0 12px 32px rgba(10,18,30,.2)}
figure{max-width:none;margin:0 auto 18px;padding:4px;border:1px solid var(--line);border-radius:12px;background:var(--paper);box-shadow:0 12px 40px rgba(18,32,48,.08)}figure svg{width:100%;height:auto;min-width:850px}
.provenance-details,.viewer-guide{border-color:var(--line);background:var(--paper)}.provenance-details{margin-top:16px}.provenance-details p,.provenance-details ul{padding:0 16px}.provenance-details summary{font-size:13px}
body[data-theme="dark"]{color-scheme:dark;--ink:#e5eaf0;--muted:#a3afbd;--line:#2d3744;--paper:#121821;--canvas:#0b0e14;--accent:#62d4df;--accent-soft:#18343b}
body[data-theme="dark"] figure,body[data-theme="dark"] details,body[data-theme="dark"] .diagram-tools{background:var(--paper);border-color:var(--line)}
body[data-theme="dark"] button,body[data-theme="dark"] input,body[data-theme="dark"] select{background:#171e28;color:var(--ink);border-color:#354252}
body[data-theme="dark"] button:hover{background:#1a333b;border-color:var(--accent)}body[data-theme="dark"] th{background:#171e28;color:var(--muted)}
body[data-theme="dark"] figure svg .canvas{fill:#0b0e14}body[data-theme="dark"] figure svg .paper{fill:#121821;stroke:#2d3744}
body[data-theme="dark"] figure svg text{fill:#e5eaf0}body[data-theme="dark"] figure svg .header-kicker{fill:#62d4df}
body[data-theme="dark"] figure svg .summary,body[data-theme="dark"] figure svg .provenance,body[data-theme="dark"] figure svg .legend,body[data-theme="dark"] figure svg .node-id,body[data-theme="dark"] figure svg .certainty-mark,body[data-theme="dark"] figure svg .group-title{fill:#a3afbd}
body[data-theme="dark"] figure svg .group-box{fill:#171e28;stroke:#738196}body[data-theme="dark"] figure svg .node-service,body[data-theme="dark"] figure svg .participant{fill:#182b39;stroke:#53c4d5}
body[data-theme="dark"] figure svg .node-data{fill:#16342c;stroke:#56d09b}body[data-theme="dark"] figure svg .node-external{fill:#222a35;stroke:#a7b1c0}
body[data-theme="dark"] figure svg .node-decision{fill:#382d1a;stroke:#e4b65d}body[data-theme="dark"] figure svg .node-unknown,body[data-theme="dark"] figure svg .participant-unknown{fill:#3a2422;stroke:#f19a86}
body[data-theme="dark"] figure svg .edge,body[data-theme="dark"] figure svg .legend-line{stroke:#a9b7c8}body[data-theme="dark"] figure svg .edge-data{stroke:#53c4d5}
body[data-theme="dark"] figure svg .edge-affirmative{stroke:#70d3b3}body[data-theme="dark"] figure svg .edge-alternative{stroke:#f0bd63}body[data-theme="dark"] figure svg .edge-error{stroke:#f19a86}
body[data-theme="dark"] figure svg .edge-label-bg{fill:#121821;stroke:#384554}body[data-theme="dark"] figure svg .lifeline{stroke:#647387}body[data-theme="dark"] figure svg .flow-arrow{fill:#a9b7c8}
body[data-theme="dark"] .overview-node-action .overview-marker{fill:#222a35;stroke:#a7b1c0}body[data-theme="dark"] .overview-node-start .overview-marker{fill:#182b39;stroke:#8db0ff}body[data-theme="dark"] .overview-node-decision .overview-marker{fill:#382d1a;stroke:#f0bd63}body[data-theme="dark"] .overview-node-terminal .overview-marker{fill:#16342c;stroke:#70d3b3}
body[data-theme="dark"] .search-results{background:#121821;border-color:#354252}body[data-theme="dark"] .search-result[aria-selected="true"],body[data-theme="dark"] .search-result:hover{background:#1a333b}
@media(max-width:760px){.primary-toolbar{align-items:stretch;flex-direction:column}.primary-toolbar .search-field{max-width:none;min-width:0}.primary-actions{justify-content:flex-start}.primary-actions .export-tools{position:static}.export-tools[open] .export-grid{left:0;right:auto}.diagram-tools{padding:7px}.advanced-tools .tool-field{max-width:none}}
#explore-tools[open] .advanced-tools{max-height:min(55vh,520px);overflow-y:auto;overscroll-behavior:contain;scrollbar-gutter:stable}
.diagram-pan-hint{display:none;margin:0 4px 8px;padding:7px 10px;border-inline-start:3px solid var(--accent);background:var(--paper);color:var(--muted);font-size:12px;line-height:1.4}
@media(max-width:760px){.diagram-pan-hint{display:block}figure{scrollbar-width:thin;scrollbar-color:var(--accent) var(--line)}}
.mobile-diagram-intro{display:none}
@media(max-width:760px){.mobile-diagram-intro{display:block;margin:10px 4px 8px}.mobile-diagram-intro h2{margin:0;font-size:17px;line-height:1.3}.mobile-diagram-intro p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.45}figure svg{margin-top:-124px;min-width:1000px}figure svg .header-kicker,figure svg .title,figure svg .summary,figure svg .provenance{display:none}}
@media(max-width:760px){.mobile-diagram-intro p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.45;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}}
@media(max-width:760px){.diagram-tools{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 8px}.primary-toolbar{grid-column:1/-1}.primary-actions{flex-wrap:nowrap;overflow-x:auto}.primary-actions>*{flex:0 0 auto;white-space:nowrap}.diagram-tools>.overview-drawer,.diagram-tools>.explore-tools{min-width:0;margin:0}.diagram-tools>.overview-drawer[open],.diagram-tools>.explore-tools[open]{grid-column:1/-1}}
@media(max-width:760px){body.presentation .mobile-diagram-intro,body.presentation .diagram-pan-hint{display:none!important}body.presentation figure{overflow:auto}body.presentation figure svg{margin-top:-124px;min-width:1000px!important}body.presentation #presentation-exit{top:108px}}
@media(max-width:760px){body.presentation .mobile-diagram-intro{display:block!important;margin:10px 4px 8px;padding-right:148px}body.presentation figure svg .header-kicker,body.presentation figure svg .title,body.presentation figure svg .summary,body.presentation figure svg .provenance{display:none!important}body.presentation #presentation-exit{top:16px}}
figure svg [data-node-id].is-role-a .node-shape{stroke:#087f8c!important;stroke-width:3.2!important}
figure svg [data-node-id].is-role-b .node-shape{stroke:#a64b00!important;stroke-width:3.2!important;stroke-dasharray:6 3!important}
figure svg [data-edge-id].is-role-forward path.edge{stroke:#087f8c!important;stroke-width:3.2!important}
figure svg [data-edge-id].is-role-reverse path.edge{stroke:#a64b00!important;stroke-width:3.2!important;stroke-dasharray:7 4!important}
body[data-theme="dark"] figure svg [data-node-id].is-role-a .node-shape,body[data-theme="dark"] figure svg [data-edge-id].is-role-forward path.edge{stroke:#62d4df!important}
body[data-theme="dark"] figure svg [data-node-id].is-role-b .node-shape,body[data-theme="dark"] figure svg [data-edge-id].is-role-reverse path.edge{stroke:#ffb462!important}
figure svg [data-node-id].is-story-beat .node-shape,figure svg [data-edge-id].is-story-beat path.edge{stroke:#7047c7!important;stroke-width:4!important}
figure svg [data-node-id].is-story-context .node-shape{stroke:#087f8c!important;stroke-width:2.8!important;stroke-dasharray:5 3!important}
figure svg [data-edge-id].is-story-context path.edge{stroke:#087f8c!important;stroke-width:2.8!important;stroke-dasharray:6 4!important}
body[data-theme="dark"] figure svg [data-node-id].is-story-beat .node-shape,body[data-theme="dark"] figure svg [data-edge-id].is-story-beat path.edge{stroke:#c4a8ff!important}
body[data-theme="dark"] figure svg [data-node-id].is-story-context .node-shape,body[data-theme="dark"] figure svg [data-edge-id].is-story-context path.edge{stroke:#62d4df!important}
@media(max-width:760px){main{padding:16px 12px 28px}.diagram-tools{padding:7px;margin-bottom:8px}.primary-toolbar .search-field input{min-height:36px;padding:5px 8px}.primary-actions{gap:4px}.primary-actions>button,.primary-actions>.export-tools>summary,.diagram-tools .overview-drawer>summary{min-height:34px;padding:4px 7px;font-size:12px}.diagram-tools .overview-drawer{margin:4px 0 6px}.mobile-diagram-intro{margin:6px 4px}.diagram-pan-hint{margin:0 4px 6px;padding:5px 8px}}
""".strip()

DELTA_CSS = """
body{margin:0;background:#f5f7fb;color:#17253c;font:15px/1.55 'Segoe UI',Arial,sans-serif}
main{max-width:1440px;margin:0 auto;padding:32px 20px}
header,.panel{background:white;border:1px solid #dbe3ef;border-radius:12px;padding:18px;margin:12px 0}
h1{margin:0}.snapshots{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.changes-panel{grid-column:1/-1}
.panel h2{margin:0 0 8px;font-size:17px}.summary{color:#52637d;font-size:13px}.snapshot-hint{margin:8px 0;color:#52637d;font-size:12px}.snapshot-figure{margin:12px 0;border:1px solid #dbe3ef;border-radius:9px;background:#f6f8fc;overflow:auto;overscroll-behavior-x:contain}.snapshot-figure:focus-visible{outline:3px solid #2455d6;outline-offset:2px}.snapshot-figure svg{display:block;width:auto;height:auto;max-width:none;max-height:none}.snapshot-figure [data-snapshot="before"] .edge{marker-end:url(#before-arrow)}.snapshot-figure [data-snapshot="after"] .edge{marker-end:url(#after-arrow)}
table{width:100%;border-collapse:collapse;background:white}th,td{padding:8px;border-bottom:1px solid #dbe3ef;text-align:left;vertical-align:top}
th{color:#52637d;font-size:12px}.delta-table-wrap{overflow:auto}code{font:12px ui-monospace,Consolas,monospace;overflow-wrap:anywhere}
small{color:#52637d}details{margin:8px 0}li{margin:5px 0}
@media(max-width:900px){.snapshots{grid-template-columns:1fr}.changes-panel{grid-column:auto}main{padding:18px 12px}}
""".strip()


def _tag(name: str) -> str:
    return f"{{{SVG_NS}}}{name}"


def _svg(parent: ET.Element, name: str, attrs: dict[str, Any] | None = None, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, _tag(name), {key: str(value) for key, value in (attrs or {}).items()})
    if text is not None:
        element.text = text
    return element


def _plain_tag(parent: ET.Element, name: str, attrs: dict[str, Any] | None = None, text: str | None = None) -> ET.Element:
    element = ET.SubElement(parent, name, {key: str(value) for key, value in (attrs or {}).items()})
    if text is not None:
        element.text = text
    return element


def _text_width(value: str) -> float:
    import unicodedata

    width = 0.0
    for char in value:
        code = ord(char)
        if unicodedata.category(char) in {"Mn", "Me"}:
            continue
        width += 16 if unicodedata.east_asian_width(char) in {"F", "W"} or 0x0E00 <= code <= 0x0E7F else 8
    return width


def _wrap(value: str, max_width: float) -> list[str]:
    words = value.split()
    lines: list[str] = []
    current = ""
    for word in words:
        pieces = []
        while _text_width(word) > max_width:
            cut = 1
            while cut < len(word) and _text_width(word[: cut + 1]) <= max_width:
                cut += 1
            pieces.append(word[:cut])
            word = word[cut:]
        if word:
            pieces.append(word)
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if current and _text_width(candidate) > max_width:
                lines.append(current)
                current = piece
            else:
                current = candidate
    if current:
        lines.append(current)
    if not lines:
        return [""]
    return lines


def _node_size(entity: dict[str, Any]) -> tuple[float, float, list[str]]:
    lines = _wrap(entity["label"], 176)
    extra = 60 if entity["kind"] == "initial" else 36
    width = max(164.0, min(260.0, max(_text_width(line) for line in lines) + extra))
    height = 62.0 + max(0, len(lines) - 1) * 18.0
    return width, height, lines


def _edge_label_geometry(edge: dict[str, Any]) -> tuple[list[str], float, float]:
    lines = _wrap(edge["label"], 172.0)
    box_width = min(202.0, max(72.0, max(_text_width(line) for line in lines) + 20.0))
    box_height = len(lines) * 15.0 + 8.0
    return lines, box_width, box_height


def _header_height(spec: dict[str, Any]) -> float:
    title_lines = _wrap(spec["title"], 950)
    summary_lines = _wrap(spec["summary"], 1100)
    summary_y = 119.0 + (len(title_lines) - 1) * 31.0
    provenance_y = summary_y + len(summary_lines) * 17.0 + 3.0
    return max(176.0, provenance_y + 37.0)


def _topological_layers(entities: list[dict[str, Any]], edges: list[dict[str, Any]], authored: list[list[str]] | None) -> list[list[str]]:
    entity_ids = {item["id"] for item in entities}
    if authored is not None:
        flat = [identifier for layer in authored for identifier in layer]
        if len(flat) != len(set(flat)) or set(flat) != entity_ids:
            raise DiagramError("layout.layers must contain every diagram entity exactly once")
        return authored
    adjacency: dict[str, list[str]] = {identifier: [] for identifier in entity_ids}
    indegree = {identifier: 0 for identifier in entity_ids}
    for edge in edges:
        if edge["feedback"]:
            continue
        adjacency[edge["source"]].append(edge["target"])
        indegree[edge["target"]] += 1
    ready = deque(sorted(identifier for identifier, degree in indegree.items() if degree == 0))
    rank = {identifier: 0 for identifier in entity_ids}
    visited = 0
    while ready:
        source = ready.popleft()
        visited += 1
        for target in adjacency[source]:
            rank[target] = max(rank[target], rank[source] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if visited != len(entity_ids):
        raise DiagramError("unmarked graph cycle; mark a loop-closing edge feedback=true")
    layers = [[] for _ in range(max(rank.values(), default=0) + 1)]
    for identifier in sorted(entity_ids):
        layers[rank[identifier]].append(identifier)
    index = {identifier: position for layer in layers for position, identifier in enumerate(layer)}
    previous: dict[str, list[str]] = defaultdict(list)
    following: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if not edge["feedback"]:
            previous[edge["target"]].append(edge["source"])
            following[edge["source"]].append(edge["target"])

    for _ in range(4):
        for layer_index in range(1, len(layers)):
            old = {identifier: i for i, identifier in enumerate(layers[layer_index])}
            layers[layer_index].sort(
                key=lambda identifier: (
                    sum(index[item] for item in previous[identifier]) / len(previous[identifier])
                    if previous[identifier] else old[identifier],
                    old[identifier],
                )
            )
            index.update({identifier: i for i, identifier in enumerate(layers[layer_index])})
        for layer_index in range(len(layers) - 2, -1, -1):
            old = {identifier: i for i, identifier in enumerate(layers[layer_index])}
            layers[layer_index].sort(
                key=lambda identifier: (
                    sum(index[item] for item in following[identifier]) / len(following[identifier])
                    if following[identifier] else old[identifier],
                    old[identifier],
                )
            )
            index.update({identifier: i for i, identifier in enumerate(layers[layer_index])})
    return layers


def _centered_port_spacing(height: float, count: int) -> float:
    spread = (count - 1) / 2
    if spread <= 0:
        return 0.0
    return min(12.0, max(0.0, height / 2 - 8.0) / spread)


def _label_clearance_lanes(edges: list[dict[str, Any]], anchor: float, outward: float) -> dict[str, float]:
    if not edges:
        return {}
    lanes = {edges[-1]["id"]: anchor}
    for index in range(len(edges) - 2, -1, -1):
        current, inner = edges[index], edges[index + 1]
        _, current_width, _ = _edge_label_geometry(current)
        _, inner_width, _ = _edge_label_geometry(inner)
        separation = max(current_width, inner_width) + 12.0
        lanes[current["id"]] = lanes[inner["id"]] + outward * separation
    return lanes


def _side_anchor(rect: dict[str, float], side: str) -> tuple[float, float]:
    if side == "top":
        return rect["x"] + rect["w"] / 2, rect["y"]
    if side == "right":
        return rect["x"] + rect["w"], rect["y"] + rect["h"] / 2
    if side == "bottom":
        return rect["x"] + rect["w"] / 2, rect["y"] + rect["h"]
    return rect["x"], rect["y"] + rect["h"] / 2


def _side_lead(anchor: tuple[float, float], side: str, distance: float = 12.0) -> tuple[float, float]:
    dx, dy = {
        "top": (0.0, -distance),
        "right": (distance, 0.0),
        "bottom": (0.0, distance),
        "left": (-distance, 0.0),
    }[side]
    return anchor[0] + dx, anchor[1] + dy


def _outward_segment(first: tuple[float, float], second: tuple[float, float], side: str) -> bool:
    dx, dy = second[0] - first[0], second[1] - first[1]
    epsilon = 1e-6
    if side == "top":
        return dy < -epsilon and abs(dx) <= epsilon
    if side == "right":
        return dx > epsilon and abs(dy) <= epsilon
    if side == "bottom":
        return dy > epsilon and abs(dx) <= epsilon
    return dx < -epsilon and abs(dy) <= epsilon


def _apply_edge_hints(
    spec: dict[str, Any],
    positions: dict[str, dict[str, Any]],
    paths: list[dict[str, Any]],
    labels: list[dict[str, Any]],
) -> None:
    edge_hints = spec["layout"].get("edge_hints", {})
    if not edge_hints:
        return
    path_by_id = {path["edge"]["id"]: path for path in paths}
    label_by_id = {label["id"]: label for label in labels}
    for identifier, hint in edge_hints.items():
        path = path_by_id[identifier]
        points = list(path["points"])
        source_side = hint.get("source_side")
        target_side = hint.get("target_side")
        if "source_side" in hint:
            points[0] = _side_anchor(positions[path["edge"]["source"]], hint["source_side"])
        if "target_side" in hint:
            points[-1] = _side_anchor(positions[path["edge"]["target"]], hint["target_side"])
        if "waypoints" in hint:
            points = [
                points[0],
                *((point["x"], point["y"]) for point in hint["waypoints"]),
                points[-1],
            ]
        if source_side and len(points) > 1 and not _outward_segment(points[0], points[1], source_side):
            points.insert(1, _side_lead(points[0], source_side))
        if target_side and len(points) > 1 and not _outward_segment(points[-1], points[-2], target_side):
            points.insert(-1, _side_lead(points[-1], target_side))
        if any(start == end for start, end in zip(points, points[1:])):
            raise DiagramError(f"layout.edge_hints.{identifier} creates a zero-length route segment")
        path["points"] = points
        path["side_hints"] = {key: hint[key] for key in ("source_side", "target_side") if key in hint}
        label_hint = hint.get("label")
        if label_hint:
            segment = label_hint["segment"]
            if segment >= len(points) - 1:
                raise DiagramError(
                    f"layout.edge_hints.{identifier}.label.segment {segment} is outside the authored route "
                    f"(valid range 0 to {len(points) - 2})"
                )
            first, second = points[segment : segment + 2]
            offset = label_hint["offset"]
            label = label_by_id[identifier]
            label["x"] = (first[0] + second[0]) / 2 + offset["x"]
            label["y"] = (first[1] + second[1]) / 2 + offset["y"]
        elif any(key in hint for key in ("source_side", "target_side", "waypoints")):
            segment = max(
                range(len(points) - 1),
                key=lambda index: math.hypot(
                    points[index + 1][0] - points[index][0],
                    points[index + 1][1] - points[index][1],
                ),
            )
            first, second = points[segment : segment + 2]
            label = label_by_id[identifier]
            label["x"] = (first[0] + second[0]) / 2
            label["y"] = (first[1] + second[1]) / 2


def _authored_position_warnings(
    direction: str,
    layers: list[list[str]],
    positions: dict[str, dict[str, Any]],
) -> list[str]:
    primary = "y" if direction == "TB" else "x"
    secondary = "x" if direction == "TB" else "y"
    progress = "downward" if direction == "TB" else "rightward"
    reading = "left-to-right" if direction == "TB" else "top-to-bottom"

    def center(identifier: str, axis: str) -> float:
        rect = positions[identifier]
        return rect[axis] + rect["h" if axis == "y" else "w"] / 2.0

    warnings: list[str] = []
    for layer_index, layer in enumerate(layers):
        for first_id, second_id in zip(layer, layer[1:]):
            if center(first_id, secondary) >= center(second_id, secondary) - 0.01:
                warnings.append(
                    f"node layer reading order: {direction} layer {layer_index} must progress {reading} "
                    f"({first_id} before {second_id})"
                )
    for rank, (previous, following) in enumerate(zip(layers, layers[1:])):
        previous_id = max(previous, key=lambda identifier: (center(identifier, primary), identifier))
        following_id = min(following, key=lambda identifier: (center(identifier, primary), identifier))
        if center(previous_id, primary) >= center(following_id, primary) - 0.01:
            warnings.append(
                f"node layer order: {direction} layers {rank}->{rank + 1} must progress {progress} "
                f"({previous_id} before {following_id})"
            )
    return warnings


def _graph_layout(spec: dict[str, Any]) -> dict[str, Any]:
    entities = spec["entities"]
    edges = spec["edges"]
    layers = _topological_layers(entities, edges, spec["layout"]["layers"])
    by_id = {item["id"]: item for item in entities}
    direction = spec["layout"]["direction"]
    rank_of = {identifier: index for index, layer in enumerate(layers) for identifier in layer}
    self_loops: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        if edge["source"] == edge["target"]:
            self_loops[edge["source"]].append(edge)
    loop_sides: dict[str, str] = {}
    if direction == "LR":
        for identifier in self_loops:
            layer = layers[rank_of[identifier]]
            index = layer.index(identifier)
            if len(layer) == 1 or index == 0:
                loop_sides[identifier] = "top"
            elif index == len(layer) - 1:
                loop_sides[identifier] = "bottom"
            else:
                raise DiagramError(
                    f"LR self-loop on middle peer {identifier} cannot clear nodes above and below; "
                    "use TB direction or place this entity at the top or bottom of its authored layer"
                )
    loop_port_offsets: dict[str, list[float]] = {}
    sizes = {}
    for identifier in by_id:
        node_width, node_height, lines = _node_size(by_id[identifier])
        node_loops = self_loops[identifier]
        loop_count = len(node_loops)
        if direction == "LR" and loop_count:
            offsets = [0.0] * loop_count
            for index in range(loop_count - 1, -1, -1):
                _, label_width, _ = _edge_label_geometry(node_loops[index])
                clear_label = max(0.0, label_width / 2.0 - 10.0)
                nested_port = offsets[index + 1] + 8.0 if index + 1 < loop_count else 0.0
                offsets[index] = max(clear_label, nested_port)
            loop_port_offsets[identifier] = offsets
            node_width = max(node_width, 2.0 * (30.0 + offsets[0]))
        elif direction == "TB" and loop_count:
            node_height = max(node_height, 16.0 + 12.0 * loop_count)
        sizes[identifier] = (node_width, node_height, lines)
    route_edges = [
        edge for edge in edges
        if edge["feedback"] or abs(rank_of[edge["target"]] - rank_of[edge["source"]]) > 1
        if not (
            direction == "LR"
            and edge["source"] == edge["target"]
            and loop_sides.get(edge["source"]) == "bottom"
        )
    ]
    lane_count = sum(
        1 for edge in route_edges
        if direction == "LR" or (edge["source"] != edge["target"] and not edge["feedback"])
    )
    header_height = _header_height(spec)
    lane_positions: dict[str, tuple[float, float]] = {}
    if direction == "LR":
        lane_cursor = header_height + 22.0
        for edge in route_edges:
            _, _, label_height = _edge_label_geometry(edge)
            lane_y = lane_cursor + label_height + 6.0
            label_y = lane_cursor + label_height / 2.0
            lane_positions[edge["id"]] = (lane_y, label_y)
            lane_cursor = lane_y + 8.0
        content_top = max(
            header_height + 38.0,
            (lane_cursor - 8.0 + 12.0) if lane_positions else header_height + 38.0,
        )
        layer_label_spans: list[float] = []
        normal_label_budgets: dict[int, float] = {}
    else:
        loop_label_widths: dict[str, float] = {}
        loop_label_spans: dict[str, float] = {}
        for identifier, node_edges in self_loops.items():
            label_heights = []
            for edge in node_edges:
                _, box_width, box_height = _edge_label_geometry(edge)
                loop_label_widths[identifier] = max(loop_label_widths.get(identifier, 0.0), box_width)
                label_heights.append(box_height)
            loop_label_spans[identifier] = 8.0 + sum(label_heights) + 8.0 * max(0, len(label_heights) - 1)
        layer_label_spans = [
            max((loop_label_spans.get(identifier, 0.0) for identifier in layer), default=0.0)
            for layer in layers
        ]
        incoming_labels: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            if not edge["feedback"] and rank_of[edge["target"]] - rank_of[edge["source"]] == 1:
                incoming_labels[rank_of[edge["target"]]].append(edge)
        normal_label_budgets = {
            rank: sum(_edge_label_geometry(edge)[2] + 14.0 for edge in grouped) + 28.0
            for rank, grouped in incoming_labels.items()
        }
        content_top = header_height + max(38.0, 36.0 + layer_label_spans[0])
    positions: dict[str, dict[str, float]] = {}

    if direction == "LR":
        rank_widths = [max(sizes[identifier][0] for identifier in layer) for layer in layers]
        rank_heights = [sum(sizes[identifier][1] for identifier in layer) + max(0, len(layer) - 1) * 34 for layer in layers]
        content_height = max(rank_heights, default=80)
        x_by_rank: list[float] = []
        x = 86.0
        for width in rank_widths:
            x_by_rank.append(x)
            x += width + 224.0
        for layer_index, layer in enumerate(layers):
            y = content_top + (content_height - rank_heights[layer_index]) / 2
            for identifier in layer:
                width, height, lines = sizes[identifier]
                positions[identifier] = {"x": x_by_rank[layer_index], "y": y, "w": width, "h": height, "rank": layer_index, "lines": lines}
                y += height + 34.0
        width = x_by_rank[-1] + rank_widths[-1] + 86.0
        height = content_top + content_height + 124.0
    else:
        rank_heights = [max(sizes[identifier][1] for identifier in layer) for layer in layers]
        rank_widths = []
        left_loop_reserves = []
        inter_node_gaps: list[list[float]] = []
        for layer in layers:
            first, last = layer[0], layer[-1]
            left_reserve = 12.0 * len(self_loops[first])
            right_reserve = 12.0 * len(self_loops[last])
            gaps = []
            for left, right in zip(layer, layer[1:]):
                left_width, _, _ = sizes[left]
                right_width, _, _ = sizes[right]
                label_width = (
                    loop_label_widths.get(left, 0.0) + loop_label_widths.get(right, 0.0)
                ) / 2.0 - (left_width + right_width) / 2.0 + 12.0
                route_width = 38.0 + 12.0 * max(len(self_loops[left]), len(self_loops[right]))
                gaps.append(max(route_width, label_width))
            inter_node_gaps.append(gaps)
            left_loop_reserves.append(left_reserve)
            rank_widths.append(
                left_reserve
                + sum(sizes[identifier][0] for identifier in layer)
                + sum(gaps)
                + right_reserve
            )
        content_width = max(rank_widths, default=100)
        y_by_rank: list[float] = []
        y = content_top
        for layer_index, layer_height in enumerate(rank_heights):
            y_by_rank.append(y)
            y += layer_height
            if layer_index + 1 < len(rank_heights):
                target_rank = layer_index + 1
                y += max(
                    112.0,
                    layer_label_spans[target_rank] + normal_label_budgets.get(target_rank, 0.0),
                )
        for layer_index, layer in enumerate(layers):
            x = 86.0 + (content_width - rank_widths[layer_index]) / 2 + left_loop_reserves[layer_index]
            for index, identifier in enumerate(layer):
                node_width, node_height, lines = sizes[identifier]
                positions[identifier] = {"x": x, "y": y_by_rank[layer_index], "w": node_width, "h": node_height, "rank": layer_index, "lines": lines}
                x += node_width
                if index < len(inter_node_gaps[layer_index]):
                    x += inter_node_gaps[layer_index][index]
        width = 172.0 + content_width + lane_count * 36.0 + 48.0
        height = y_by_rank[-1] + rank_heights[-1] + 124.0

    authored_positions = spec["layout"].get("positions")
    if authored_positions:
        for identifier, point in authored_positions.items():
            positions[identifier].update(x=point["x"], y=point["y"])

    bottom_loop_positions: dict[str, tuple[float, float]] = {}
    if direction == "LR":
        bottom_loop_end = 0.0
        for identifier, side in loop_sides.items():
            if side != "bottom":
                continue
            node_edges = self_loops[identifier]
            cursor = positions[identifier]["y"] + positions[identifier]["h"] + 18.0
            for index in range(len(node_edges) - 1, -1, -1):
                edge = node_edges[index]
                _, _, label_height = _edge_label_geometry(edge)
                lane_y = cursor
                label_y = lane_y + 6.0 + label_height / 2.0
                bottom_loop_positions[edge["id"]] = (lane_y, label_y)
                cursor = lane_y + label_height + 14.0
            bottom_loop_end = max(bottom_loop_end, cursor)
        if bottom_loop_positions:
            height = max(height, bottom_loop_end + 124.0)

    width = max(width, MIN_CANVAS_WIDTH)
    paths, labels = _graph_routes(
        spec, layers, positions, rank_of, width, lane_count, lane_positions, loop_port_offsets,
        layer_label_spans, loop_sides, bottom_loop_positions,
    )
    _apply_edge_hints(spec, positions, paths, labels)
    group_boxes = []
    for group in spec["groups"]:
        members = [positions[identifier] for identifier in group["members"]]
        pad_x, pad_y = 20.0, 28.0
        left = min(item["x"] for item in members) - pad_x
        top = min(item["y"] for item in members) - pad_y
        right = max(item["x"] + item["w"] for item in members) + pad_x
        bottom = max(item["y"] + item["h"] for item in members) + pad_y
        group_boxes.append({**group, "x": left, "y": top, "w": right - left, "h": bottom - top})

    if authored_positions:
        x_extents = [coordinate for item in positions.values() for coordinate in (item["x"], item["x"] + item["w"])]
        x_extents.extend(coordinate for path in paths for coordinate, _ in path["points"])
        x_extents.extend(coordinate for label in labels for coordinate in (label["x"] - label["w"] / 2, label["x"] + label["w"] / 2))
        x_extents.extend(coordinate for group in group_boxes for coordinate in (group["x"], group["x"] + group["w"]))
        y_extents = [coordinate for item in positions.values() for coordinate in (item["y"], item["y"] + item["h"])]
        y_extents.extend(y for path in paths for _, y in path["points"])
        y_extents.extend(coordinate for label in labels for coordinate in (label["y"] - label["h"] / 2, label["y"] + label["h"] / 2))
        y_extents.extend(coordinate for group in group_boxes for coordinate in (group["y"], group["y"] + group["h"]))
        width = max(MIN_CANVAS_WIDTH, max(x_extents, default=0.0) + 80.0)
        height = max(_header_height(spec) + 100.0, max(y_extents, default=0.0) + 80.0)

    if direction == "TB":
        horizontal_extents = [
            coordinate
            for item in positions.values()
            for coordinate in (item["x"], item["x"] + item["w"])
        ]
        horizontal_extents.extend(
            coordinate
            for path in paths
            for coordinate, _ in path["points"]
        )
        horizontal_extents.extend(
            coordinate
            for label in labels
            for coordinate in (label["x"] - label["w"] / 2.0, label["x"] + label["w"] / 2.0)
        )
        horizontal_extents.extend(
            coordinate
            for group in group_boxes
            for coordinate in (group["x"], group["x"] + group["w"])
        )
        if horizontal_extents and authored_positions is None:
            left, right = min(horizontal_extents), max(horizontal_extents)
            width = max(width, right - left + 160.0)
            offset = width / 2.0 - (left + right) / 2.0
            if abs(offset) > 0.01:
                positions = {
                    identifier: {**item, "x": item["x"] + offset}
                    for identifier, item in positions.items()
                }
                paths = [
                    {**path, "points": [(x + offset, y) for x, y in path["points"]]}
                    for path in paths
                ]
                labels = [{**label, "x": label["x"] + offset} for label in labels]
                group_boxes = [{**group, "x": group["x"] + offset} for group in group_boxes]

    warnings = _geometry_warnings(
        positions, paths, labels, group_boxes, width, height, header_bottom=_header_height(spec),
    )
    if authored_positions:
        warnings.extend(_authored_position_warnings(direction, layers, positions))
        content_top = _header_height(spec) + 38.0
        warnings.extend(
            f"node overlaps diagram header: {identifier}"
            for identifier, rect in positions.items()
            if rect["y"] < content_top
        )
    return {
        "positions": positions,
        "paths": paths,
        "labels": labels,
        "groups": group_boxes,
        "width": width,
        "height": height,
        "layers": layers,
        "warnings": warnings,
    }


def _graph_routes(
    spec: dict[str, Any],
    layers: list[list[str]],
    positions: dict[str, dict[str, Any]],
    rank_of: dict[str, int],
    width: float,
    lane_count: int,
    lane_positions: dict[str, tuple[float, float]],
    loop_port_offsets: dict[str, list[float]],
    layer_label_spans: list[float],
    loop_sides: dict[str, str],
    bottom_loop_positions: dict[str, tuple[float, float]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    direction = spec["layout"]["direction"]
    normal = [edge for edge in spec["edges"] if not edge["feedback"] and rank_of[edge["target"]] - rank_of[edge["source"]] == 1]
    source_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    target_edges: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in normal:
        source_edges[edge["source"]].append(edge)
        target_edges[edge["target"]].append(edge)
    if direction == "TB":
        for group in source_edges.values():
            group.sort(key=lambda edge: positions[edge["target"]]["x"] + positions[edge["target"]]["w"] / 2)
        for group in target_edges.values():
            group.sort(key=lambda edge: positions[edge["source"]]["x"] + positions[edge["source"]]["w"] / 2)
    branched_edge_ids = {
        edge["id"] for edge in normal
        if len(source_edges[edge["source"]]) > 1 or len(target_edges[edge["target"]]) > 1
    }
    normal_tracks: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for edge in normal:
        normal_tracks[(rank_of[edge["source"]], rank_of[edge["target"]])].append(edge)
    track_x: dict[str, float] = {}
    for (source_rank, target_rank), group in normal_tracks.items():
        if direction == "LR":
            start = positions[layers[source_rank][0]]["x"] + max(positions[item]["w"] for item in layers[source_rank])
            end = positions[layers[target_rank][0]]["x"]
            for index, edge in enumerate(group):
                track_x[edge["id"]] = start + (end - start) * (index + 1) / (len(group) + 1)
        else:
            start = positions[layers[source_rank][0]]["y"] + max(positions[item]["h"] for item in layers[source_rank])
            end = positions[layers[target_rank][0]]["y"] - layer_label_spans[target_rank]
            lane_height = sum(_edge_label_geometry(edge)[2] + 14.0 for edge in group)
            cursor = start + max(0.0, (end - start - lane_height) / 2.0)
            for edge in group:
                label_height = _edge_label_geometry(edge)[2]
                track_x[edge["id"]] = cursor + label_height / 2.0
                cursor += label_height + 14.0

    paths: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    loop_counts: dict[str, int] = defaultdict(int)
    loop_label_heights_used: dict[str, float] = defaultdict(float)
    rightmost_node = max((rect["x"] + rect["w"] for rect in positions.values()), default=0.0)
    routed_edges = [
        edge for edge in spec["edges"]
        if edge["source"] != edge["target"]
        and (edge["feedback"] or abs(rank_of[edge["target"]] - rank_of[edge["source"]]) > 1)
    ]
    feedback_edges = [edge for edge in routed_edges if edge["feedback"]]
    right_route_edges = [edge for edge in routed_edges if not edge["feedback"]]
    right_lanes: dict[str, float] = {}
    leftmost_node = min((rect["x"] for rect in positions.values()), default=0.0)
    feedback_lanes: dict[str, float] = {}
    feedback_source_ports: dict[str, float] = {}
    feedback_target_ports: dict[str, float] = {}
    right_source_ports: dict[str, float] = {}
    right_target_ports: dict[str, float] = {}
    if direction == "TB" and right_route_edges:
        right_route_edges.sort(key=lambda edge: (
            positions[edge["source"]]["y"], positions[edge["source"]]["x"],
            positions[edge["target"]]["y"], positions[edge["target"]]["x"], edge["source"], edge["target"], edge["id"],
        ))
        right_lanes = _label_clearance_lanes(right_route_edges, rightmost_node + 50.0, 1.0)
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in right_route_edges:
            by_source[edge["source"]].append(edge)
            by_target[edge["target"]].append(edge)
        for identifier, group in by_source.items():
            group.sort(key=lambda edge: (positions[edge["target"]]["y"], positions[edge["target"]]["x"], edge["target"], edge["id"]))
            delta = (len(group) - 1) / 2
            spacing = _centered_port_spacing(positions[identifier]["h"], len(group))
            for index, edge in enumerate(group):
                right_source_ports[edge["id"]] = (index - delta) * spacing
        for identifier, group in by_target.items():
            group.sort(key=lambda edge: (positions[edge["source"]]["y"], positions[edge["source"]]["x"], edge["source"], edge["id"]))
            delta = (len(group) - 1) / 2
            spacing = _centered_port_spacing(positions[identifier]["h"], len(group))
            for index, edge in enumerate(group):
                right_target_ports[edge["id"]] = (index - delta) * spacing
    if direction == "TB" and feedback_edges:
        feedback_edges.sort(key=lambda edge: (
            positions[edge["target"]]["y"], positions[edge["target"]]["x"],
            -positions[edge["source"]]["y"], -positions[edge["source"]]["x"], edge["source"], edge["target"], edge["id"],
        ))
        feedback_lanes = _label_clearance_lanes(feedback_edges, leftmost_node - 50.0, -1.0)
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in feedback_edges:
            by_source[edge["source"]].append(edge)
            by_target[edge["target"]].append(edge)
        for identifier, group in by_source.items():
            group.sort(key=lambda edge: (positions[edge["target"]]["y"], positions[edge["target"]]["x"], edge["target"], edge["id"]))
            spacing = min(12.0, max(0.0, positions[identifier]["h"] / 2.0 - 8.0) / len(group))
            for index, edge in enumerate(group):
                feedback_source_ports[edge["id"]] = -(index + 1) * spacing
        for identifier, group in by_target.items():
            group.sort(key=lambda edge: (-positions[edge["source"]]["y"], -positions[edge["source"]]["x"], edge["source"], edge["id"]))
            delta = (len(group) - 1) / 2
            spacing = _centered_port_spacing(positions[identifier]["h"], len(group))
            for index, edge in enumerate(group):
                feedback_target_ports[edge["id"]] = (index - delta) * spacing
    for edge in spec["edges"]:
        lines, box_width, box_height = _edge_label_geometry(edge)
        source = positions[edge["source"]]
        target = positions[edge["target"]]
        source_center = {"x": source["x"] + source["w"] / 2, "y": source["y"] + source["h"] / 2}
        target_center = {"x": target["x"] + target["w"] / 2, "y": target["y"] + target["h"] / 2}
        outgoing = source_edges[edge["source"]]
        incoming = target_edges[edge["target"]]
        source_offset = 0.0
        target_offset = 0.0
        if edge in outgoing:
            delta = (len(outgoing) - 1) / 2
            source_offset = (outgoing.index(edge) - delta) * min(13.0, (source["h"] - 24.0) / len(outgoing))
        if edge in incoming:
            target_delta = (len(incoming) - 1) / 2
            target_offset = (incoming.index(edge) - target_delta) * min(13.0, (target["h"] - 24.0) / len(incoming))
        route_around = edge["feedback"] or abs(rank_of[edge["target"]] - rank_of[edge["source"]]) > 1
        if edge["source"] == edge["target"]:
            loop_index = loop_counts[edge["source"]]
            loop_counts[edge["source"]] += 1
            if direction == "LR":
                port_offset = loop_port_offsets[edge["source"]][loop_index]
                left_x = source_center["x"] - 14.0 - port_offset
                right_x = source_center["x"] + 14.0 + port_offset
                if loop_sides[edge["source"]] == "bottom":
                    lane_y, label_y = bottom_loop_positions[edge["id"]]
                    bottom_y = source["y"] + source["h"]
                    points = [(left_x, bottom_y), (left_x, lane_y), (right_x, lane_y), (right_x, bottom_y)]
                else:
                    lane_y, label_y = lane_positions[edge["id"]]
                    points = [(left_x, source["y"]), (left_x, lane_y), (right_x, lane_y), (right_x, source["y"])]
            else:
                same_layer = [positions[identifier] for identifier in layers[rank_of[edge["source"]]]]
                left_siblings = [item for item in same_layer if item["x"] < source["x"]]
                right_siblings = [item for item in same_layer if item["x"] > source["x"]]
                left_gap = source["x"] - max((item["x"] + item["w"] for item in left_siblings), default=0.0)
                right_gap = min((item["x"] for item in right_siblings), default=width) - (source["x"] + source["w"])
                port_offset = loop_index * 6.0
                start_y = source_center["y"] - 12.0 - port_offset
                end_y = source_center["y"] + 12.0 + port_offset
                if right_gap >= left_gap:
                    base_offset = min(24.0, max(8.0, right_gap / 2.0 - 1.0))
                    loop_offset = min(base_offset + loop_index * 12.0, max(base_offset, right_gap - 4.0))
                    loop_x = source["x"] + source["w"] + loop_offset
                    points = [(source["x"] + source["w"], start_y), (loop_x, start_y), (loop_x, end_y), (source["x"] + source["w"], end_y)]
                else:
                    base_offset = min(24.0, max(8.0, left_gap / 2.0 - 1.0))
                    loop_offset = min(base_offset + loop_index * 12.0, max(base_offset, left_gap - 4.0))
                    loop_x = source["x"] - loop_offset
                    points = [(source["x"], start_y), (loop_x, start_y), (loop_x, end_y), (source["x"], end_y)]
                label_y = source["y"] - 8.0 - loop_label_heights_used[edge["source"]] - box_height / 2.0
                loop_label_heights_used[edge["source"]] += box_height + 8.0
            label_x = source_center["x"] if direction == "LR" else loop_x
        elif direction == "LR":
            sx = source["x"] + source["w"]
            tx = target["x"]
            sy = source_center["y"] + source_offset
            ty = target_center["y"] + target_offset
            if route_around:
                lane_y, label_y = lane_positions[edge["id"]]
                points = [(source_center["x"], source["y"]), (source_center["x"], lane_y), (target_center["x"], lane_y), (target_center["x"], target["y"])]
                label_x = (source_center["x"] + target_center["x"]) / 2
            else:
                channel_x = track_x[edge["id"]]
                points = [(sx, sy), (channel_x, sy), (channel_x, ty), (tx, ty)]
                label_x, label_y = (sx + tx) / 2, (sy + ty) / 2
        else:
            sx = source_center["x"] + source_offset
            tx = target_center["x"] + target_offset
            sy = source["y"] + source["h"]
            ty = target["y"]
            if route_around:
                if edge["feedback"]:
                    lane_x = feedback_lanes.get(edge["id"], leftmost_node - 50.0)
                    source_y = source_center["y"] + feedback_source_ports.get(edge["id"], 0.0)
                    target_y = target_center["y"] + feedback_target_ports.get(edge["id"], 0.0)
                    points = [(source["x"], source_y), (lane_x, source_y), (lane_x, target_y), (target["x"], target_y)]
                    label_x, label_y = lane_x - 8.0, (source_y + target_y) / 2
                else:
                    lane_x = right_lanes[edge["id"]]
                    source_y = source_center["y"] + right_source_ports.get(edge["id"], 0.0)
                    target_y = target_center["y"] + right_target_ports.get(edge["id"], 0.0)
                    points = [(source["x"] + source["w"], source_y), (lane_x, source_y), (lane_x, target_y), (target["x"] + target["w"], target_y)]
                    label_x, label_y = lane_x + 8.0, (source_y + target_y) / 2
            elif edge["id"] in branched_edge_ids:
                points = [(sx, sy), (tx, ty)]
                label_x, label_y = (sx + tx) / 2, track_x[edge["id"]]
            else:
                track_y = track_x[edge["id"]]
                points = [(sx, sy), (sx, track_y), (tx, track_y), (tx, ty)]
                label_x, label_y = (sx + tx) / 2, track_y
        paths.append({"edge": edge, "points": points})
        label_text = edge["label"]
        labels.append({"id": edge["id"], "text": label_text, "lines": lines, "x": label_x, "y": label_y, "w": box_width, "h": box_height, "certainty": edge["certainty"]})
    return paths, labels


def _geometry_warnings(
    positions: dict[str, dict[str, Any]],
    paths: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    width: float,
    height: float,
    *,
    header_bottom: float | None = None,
) -> list[str]:
    warnings: list[str] = []
    rects = list(positions.items())
    for identifier, rect in rects:
        if rect["x"] < 0 or rect["y"] < 0 or rect["x"] + rect["w"] > width or rect["y"] + rect["h"] > height:
            warnings.append(f"node outside canvas: {identifier}")
    for index, (first_id, first) in enumerate(rects):
        for second_id, second in rects[index + 1 :]:
            if _rects_overlap(first, second, 2.0):
                warnings.append(f"node overlap: {first_id}/{second_id}")
    for label in labels:
        box = {"x": label["x"] - label["w"] / 2, "y": label["y"] - label["h"] / 2, "w": label["w"], "h": label["h"]}
        if box["x"] < 0 or box["y"] < 0 or box["x"] + box["w"] > width or box["y"] + box["h"] > height:
            warnings.append(f"edge label outside canvas: {label['id']}")
        if header_bottom is not None and _rects_overlap(box, {"x": 0.0, "y": 0.0, "w": width, "h": header_bottom}, 0.0):
            warnings.append(f"edge label overlaps diagram header: {label['id']}")
        for identifier, rect in positions.items():
            if _rects_overlap(box, rect, 1.0):
                warnings.append(f"edge label overlaps node: {label['id']}/{identifier}")
        route_clearance = 2.0
        for path in paths:
            if path["edge"]["id"] == label["id"]:
                continue
            for segment_index, (first, second) in enumerate(zip(path["points"], path["points"][1:])):
                distance = _segment_rect_distance(first, second, box)
                if distance < route_clearance:
                    measurement = {
                        "distance_svg": round(distance, 6),
                        "required_clearance_svg": route_clearance,
                        "label_bounds_svg": {key: round(float(box[key]), 2) for key in ("x", "y", "w", "h")},
                        "segment_svg": {
                            "from": [round(float(first[0]), 2), round(float(first[1]), 2)],
                            "to": [round(float(second[0]), 2), round(float(second[1]), 2)],
                        },
                    }
                    warnings.append(
                        f"edge route overlaps relationship label: {label['id']}/{path['edge']['id']}/segment:{segment_index}; "
                        f"measurement={json.dumps(measurement, sort_keys=True, separators=(',', ':'))}"
                    )
    for index, first in enumerate(labels):
        first_box = {"x": first["x"] - first["w"] / 2, "y": first["y"] - first["h"] / 2, "w": first["w"], "h": first["h"]}
        for second in labels[index + 1 :]:
            second_box = {"x": second["x"] - second["w"] / 2, "y": second["y"] - second["h"] / 2, "w": second["w"], "h": second["h"]}
            if _rects_overlap(first_box, second_box, 2.0):
                warnings.append(f"edge label overlap: {first['id']}/{second['id']}")
    for index, group in enumerate(groups):
        if group["x"] < 0 or group["y"] < 0 or group["x"] + group["w"] > width or group["y"] + group["h"] > height:
            warnings.append(f"boundary outside canvas: {group['id']}")
        if header_bottom is not None and _rects_overlap(group, {"x": 0.0, "y": 0.0, "w": width, "h": header_bottom}, 0.0):
            warnings.append(f"boundary overlaps diagram header: {group['id']}")
        for identifier, rect in positions.items():
            if identifier not in group["members"] and _rects_overlap(group, rect, 0):
                warnings.append(f"boundary overlaps unrelated node: {group['id']}/{identifier}")
        for other in groups[index + 1 :]:
            if _rects_overlap(group, other, 0):
                warnings.append(f"boundary overlap: {group['id']}/{other['id']}")
    for path in paths:
        for x, y in path["points"]:
            if x < 0 or y < 0 or x > width or y > height:
                warnings.append(f"edge outside canvas: {path['edge']['id']}")
        points: list[tuple[float, float]] = []
        for point in path["points"]:
            if not points or point != points[-1]:
                points.append(point)
        edge = path["edge"]
        for first_index in range(max(0, len(points) - 1)):
            for second_index in range(first_index + 2, len(points) - 1):
                if (
                    edge["source"] == edge["target"]
                    and first_index == 0
                    and second_index == len(points) - 2
                    and points[0] == points[-1]
                ):
                    continue
                intersections = _segment_intersections(
                    points[first_index], points[first_index + 1],
                    points[second_index], points[second_index + 1],
                )
                if not intersections:
                    continue
                endpoint_ids = {edge["source"], edge["target"]}
                if endpoint_ids and positions and all(
                    any(_point_in_rect(point, positions[identifier]) for identifier in endpoint_ids if identifier in positions)
                    for point in intersections
                ):
                    continue
                warnings.append(
                    f"edge self-crossing: {edge['id']}/segment:{first_index}/segment:{second_index}; adjust the authored route"
                )
                break
        if path["edge"].get("feedback"):
            for identifier, (x, y) in ((path["edge"]["source"], path["points"][0]), (path["edge"]["target"], path["points"][-1])):
                rect = positions[identifier]
                on_vertical = abs(x - rect["x"]) < 0.01 or abs(x - (rect["x"] + rect["w"])) < 0.01
                on_horizontal = abs(y - rect["y"]) < 0.01 or abs(y - (rect["y"] + rect["h"])) < 0.01
                within_vertical = rect["y"] - 0.01 <= y <= rect["y"] + rect["h"] + 0.01
                within_horizontal = rect["x"] - 0.01 <= x <= rect["x"] + rect["w"] + 0.01
                if not (on_vertical and within_vertical) and not (on_horizontal and within_horizontal):
                    warnings.append(f"edge endpoint outside node port: {path['edge']['id']}/{identifier}")
        if header_bottom is not None:
            header = {"x": 0.0, "y": 0.0, "w": width, "h": header_bottom}
            if any(_segment_crosses_rect(first, second, header) for first, second in zip(path["points"], path["points"][1:])):
                warnings.append(f"edge crosses diagram header: {path['edge']['id']}")
        endpoints = {path["edge"]["source"], path["edge"]["target"]}
        side_hints = path.get("side_hints", {})
        if side_hints:
            for endpoint_key, endpoint_id, allowed_segment in (
                ("source_side", path["edge"]["source"], 0),
                ("target_side", path["edge"]["target"], len(path["points"]) - 2),
            ):
                if endpoint_key not in side_hints:
                    continue
                rect = positions[endpoint_id]
                for segment_index, (first, second) in enumerate(zip(path["points"], path["points"][1:])):
                    if segment_index != allowed_segment and _segment_crosses_rect(first, second, rect):
                        warnings.append(
                            f"edge route reenters hinted endpoint: {path['edge']['id']}/{endpoint_id}/segment:{segment_index}"
                        )
        for identifier, rect in positions.items():
            if identifier in endpoints:
                continue
            if any(
                _segment_crosses_rect(first, second, rect)
                for first, second in zip(path["points"], path["points"][1:])
            ):
                warnings.append(f"edge crosses node: {path['edge']['id']}/{identifier}; adjust layer order or route")
    for index, first in enumerate(paths):
        first_ends = {first["edge"]["source"], first["edge"]["target"]}
        for second in paths[index + 1 :]:
            shared_nodes = first_ends & {second["edge"]["source"], second["edge"]["target"]}
            crossed = False
            for a, b in zip(first["points"], first["points"][1:]):
                for c, d in zip(second["points"], second["points"][1:]):
                    intersections = _segment_intersections(a, b, c, d)
                    if not intersections:
                        continue
                    if shared_nodes and all(
                        any(_point_in_rect(point, positions[node_id]) for node_id in shared_nodes if node_id in positions)
                        for point in intersections
                    ):
                        continue
                    crossed = True
                    break
                if crossed:
                    break
            if crossed:
                warnings.append(f"edge crossing: {first['edge']['id']}/{second['edge']['id']}; adjust layer order or route")
    return sorted(set(warnings))


def _rects_overlap(first: dict[str, float], second: dict[str, float], gap: float) -> bool:
    return not (
        first["x"] + first["w"] + gap <= second["x"]
        or second["x"] + second["w"] + gap <= first["x"]
        or first["y"] + first["h"] + gap <= second["y"]
        or second["y"] + second["h"] + gap <= first["y"]
    )


def _segment_crosses_rect(
    first: tuple[float, float],
    second: tuple[float, float],
    rect: dict[str, float],
) -> bool:
    x1, y1 = first
    x2, y2 = second
    dx, dy = x2 - x1, y2 - y1
    lower, upper = 0.0, 1.0
    bounds = (
        (-dx, x1 - rect["x"]),
        (dx, rect["x"] + rect["w"] - x1),
        (-dy, y1 - rect["y"]),
        (dy, rect["y"] + rect["h"] - y1),
    )
    for direction, distance in bounds:
        if abs(direction) < 1e-12:
            if distance <= 0:
                return False
            continue
        fraction = distance / direction
        if direction < 0:
            lower = max(lower, fraction)
        else:
            upper = min(upper, fraction)
        if lower >= upper:
            return False
    middle = (lower + upper) / 2
    x, y = x1 + middle * dx, y1 + middle * dy
    return rect["x"] < x < rect["x"] + rect["w"] and rect["y"] < y < rect["y"] + rect["h"]


def _point_rect_distance(point: tuple[float, float], rect: dict[str, float]) -> float:
    x, y = point
    dx = max(rect["x"] - x, 0.0, x - (rect["x"] + rect["w"]))
    dy = max(rect["y"] - y, 0.0, y - (rect["y"] + rect["h"]))
    return math.hypot(dx, dy)


def _point_segment_distance(point: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> float:
    dx, dy = second[0] - first[0], second[1] - first[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-12:
        return math.hypot(point[0] - first[0], point[1] - first[1])
    fraction = max(0.0, min(1.0, ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / length_squared))
    closest = (first[0] + fraction * dx, first[1] + fraction * dy)
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def _segment_rect_distance(first: tuple[float, float], second: tuple[float, float], rect: dict[str, float]) -> float:
    corners = (
        (rect["x"], rect["y"]),
        (rect["x"] + rect["w"], rect["y"]),
        (rect["x"] + rect["w"], rect["y"] + rect["h"]),
        (rect["x"], rect["y"] + rect["h"]),
    )
    if any(_segments_intersect(first, second, corners[index], corners[(index + 1) % 4]) for index in range(4)):
        return 0.0
    return min(
        _point_rect_distance(first, rect),
        _point_rect_distance(second, rect),
        *(_point_segment_distance(corner, first, second) for corner in corners),
    )


def _segments_intersect(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> bool:
    return bool(_segment_intersections(a, b, c, d))


def _segment_intersections(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
) -> list[tuple[float, float]]:
    def cross(first: tuple[float, float], second: tuple[float, float]) -> float:
        return first[0] * second[1] - first[1] * second[0]

    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    q_minus_p = (c[0] - a[0], c[1] - a[1])
    denominator = cross(r, s)
    epsilon = 1e-9
    if abs(denominator) < epsilon:
        if abs(cross(q_minus_p, r)) >= epsilon:
            return []
        length_squared = r[0] * r[0] + r[1] * r[1]
        if length_squared < epsilon:
            return [a] if _point_on_segment(a, c, d) else []
        start = (q_minus_p[0] * r[0] + q_minus_p[1] * r[1]) / length_squared
        end_vector = (d[0] - a[0], d[1] - a[1])
        end = (end_vector[0] * r[0] + end_vector[1] * r[1]) / length_squared
        low, high = max(0.0, min(start, end)), min(1.0, max(start, end))
        if low > high + epsilon:
            return []
        first = (a[0] + low * r[0], a[1] + low * r[1])
        if abs(high - low) < epsilon:
            return [first]
        second = (a[0] + high * r[0], a[1] + high * r[1])
        return [first, second]
    along_first = cross(q_minus_p, s) / denominator
    along_second = cross(q_minus_p, r) / denominator
    if -epsilon <= along_first <= 1 + epsilon and -epsilon <= along_second <= 1 + epsilon:
        return [(a[0] + along_first * r[0], a[1] + along_first * r[1])]
    return []


def _point_on_segment(point: tuple[float, float], first: tuple[float, float], second: tuple[float, float]) -> bool:
    cross = (point[0] - first[0]) * (second[1] - first[1]) - (point[1] - first[1]) * (second[0] - first[0])
    if abs(cross) > 1e-9:
        return False
    return (
        min(first[0], second[0]) - 1e-9 <= point[0] <= max(first[0], second[0]) + 1e-9
        and min(first[1], second[1]) - 1e-9 <= point[1] <= max(first[1], second[1]) + 1e-9
    )


def _point_in_rect(point: tuple[float, float], rect: dict[str, float]) -> bool:
    x, y = point
    return rect["x"] <= x <= rect["x"] + rect["w"] and rect["y"] <= y <= rect["y"] + rect["h"]


def _sequence_layout(spec: dict[str, Any]) -> dict[str, Any]:
    participants = spec["entities"]
    edges = sorted(spec["edges"], key=lambda edge: edge["order"])
    x_step = 248.0
    positions: dict[str, dict[str, Any]] = {}
    participant_top = max(188.0, _header_height(spec) + 12.0)
    for index, entity in enumerate(participants):
        width, height, lines = _node_size(entity)
        positions[entity["id"]] = {"x": 92.0 + index * x_step, "y": participant_top, "w": width, "h": height, "lines": lines}
    row_heights = {edge["id"]: max(58.0, len(_wrap(edge["label"], 204.0)) * 18.0 + 25.0) for edge in edges}
    total_height = sum(row_heights.values())
    height = participant_top + 88.0 + total_height + 82.0
    width = max(MIN_CANVAS_WIDTH, 92.0 + max(0, len(participants) - 1) * x_step + 236.0)
    paths = []
    labels = []
    y = participant_top + 88.0
    for edge in edges:
        source = positions[edge["source"]]
        target = positions[edge["target"]]
        source_x = source["x"] + source["w"] / 2
        target_x = target["x"] + target["w"] / 2
        row_y = y + row_heights[edge["id"]] / 2
        if edge["source"] == edge["target"]:
            points = [(source_x, row_y - 8), (source_x + 36, row_y - 8), (source_x + 36, row_y + 12), (source_x, row_y + 12)]
            label_x, label_y = source_x + 82, row_y
        else:
            points = [(source_x, row_y), (target_x, row_y)]
            label_x, label_y = (source_x + target_x) / 2, row_y - 17
        paths.append({"edge": edge, "points": points})
        lines = _wrap(edge["label"], 210.0)
        box_width = min(232.0, max(88.0, max(_text_width(line) for line in lines) + 18.0))
        box_height = len(lines) * 16.0 + 7.0
        labels.append({"id": edge["id"], "text": edge["label"], "lines": lines, "x": label_x, "y": label_y, "w": box_width, "h": box_height, "certainty": edge["certainty"]})
        y += row_heights[edge["id"]]
    warnings = _geometry_warnings(positions, paths, labels, [], width, height, header_bottom=_header_height(spec))
    return {"positions": positions, "paths": paths, "labels": labels, "groups": [], "width": width, "height": height, "warnings": warnings}


def _line_path(points: list[tuple[float, float]]) -> str:
    commands = [f"M {points[0][0]:.1f} {points[0][1]:.1f}"]
    for x, y in points[1:]:
        commands.append(f"L {x:.1f} {y:.1f}")
    return " ".join(commands)


def _draw_text(parent: ET.Element, x: float, y: float, lines: list[str], *, class_name: str, anchor: str = "middle", line_height: float = 17.0) -> None:
    text_node = _svg(parent, "text", {"x": f"{x:.1f}", "y": f"{y:.1f}", "class": class_name, "text-anchor": anchor})
    for index, line in enumerate(lines):
        _svg(text_node, "tspan", {"x": f"{x:.1f}", "dy": "0" if index == 0 else f"{line_height:.1f}"}, line)


def _certainty_class(certainty: str) -> str:
    return "node-unknown" if certainty == "unknown" else ("node-inferred" if certainty == "inferred" else "")


def _ui(spec: dict[str, Any]) -> dict[str, Any]:
    return UI_TEXT[spec["language"]]


def _draw_group(svg: ET.Element, group: dict[str, Any]) -> None:
    ui = UI_TEXT[svg.attrib.get("data-language", "en")]
    detail = f"; {group['reason']}" if group["certainty"] == "unknown" else ""
    group_node = _svg(svg, "g", {"data-boundary-id": group["id"], "role": "group", "aria-label": f"{group['label']}; {ui[group['certainty']]}{detail}"})
    classes = "group-box group-unknown" if group["certainty"] == "unknown" else "group-box group-inferred" if group["certainty"] == "inferred" else "group-box"
    _svg(group_node, "rect", {"x": group["x"], "y": group["y"], "width": group["w"], "height": group["h"], "rx": 13, "class": classes})
    _svg(group_node, "text", {"x": group["x"] + 13, "y": group["y"] + 17, "class": "group-title"}, group["label"])


def _certainty_symbol(certainty: str) -> str:
    return {"inferred": "~", "unknown": "?"}.get(certainty, "")


def _draw_graph_node(svg: ET.Element, entity: dict[str, Any], rect: dict[str, Any]) -> None:
    x, y, width, height = rect["x"], rect["y"], rect["w"], rect["h"]
    ui = UI_TEXT[svg.attrib.get("data-language", "en")]
    group = _svg(svg, "g", {
        "data-node-id": entity["id"], "data-label": entity["label"], "data-kind": entity["kind"],
        "data-certainty": entity["certainty"], "data-evidence": ",".join(entity["evidence_ids"]),
        "data-reason": entity.get("reason") or "",
        "role": "group", "aria-label": f"{entity['label']}; {entity['kind']}; {ui[entity['certainty']]}"})
    _svg(group, "title", text=f"{entity['id']}: {entity['label']} ({ui[entity['certainty']]})")
    fill_class = "node-data" if entity["kind"] in {"database", "cache", "queue", "store", "source", "sink"} else "node-external" if entity["kind"] in {"external", "actor", "client"} else "node-decision" if entity["kind"] in {"decision", "gate"} else "node-service"
    certainty_class = _certainty_class(entity["certainty"])
    shape_class = "node-shape " + fill_class + (f" {certainty_class}" if certainty_class else "")
    kind = entity["kind"]
    if kind in {"initial"}:
        _svg(group, "rect", {"x": x, "y": y, "width": width, "height": height, "rx": 11, "class": shape_class})
        _svg(group, "circle", {"cx": x + 23, "cy": y + height / 2, "r": 8, "class": "terminal-dot"})
    elif kind in {"terminal", "start"}:
        _svg(group, "rect", {"x": x, "y": y + 7, "width": width, "height": height - 14, "rx": (height - 14) / 2, "class": shape_class})
    elif kind in {"decision", "gate"}:
        points = f"{x + width / 2},{y} {x + width},{y + height / 2} {x + width / 2},{y + height} {x},{y + height / 2}"
        _svg(group, "polygon", {"points": points, "class": shape_class})
    elif kind in {"database", "store"}:
        curve = 10.0
        d = f"M {x:.1f} {y + curve:.1f} C {x:.1f} {y + 2:.1f} {x + width:.1f} {y + 2:.1f} {x + width:.1f} {y + curve:.1f} L {x + width:.1f} {y + height - curve:.1f} C {x + width:.1f} {y + height - 2:.1f} {x:.1f} {y + height - 2:.1f} {x:.1f} {y + height - curve:.1f} Z"
        _svg(group, "path", {"d": d, "class": shape_class})
        _svg(group, "path", {"d": f"M {x:.1f} {y + curve:.1f} C {x:.1f} {y + curve + 12:.1f} {x + width:.1f} {y + curve + 12:.1f} {x + width:.1f} {y + curve:.1f}", "fill": "none", "stroke": "#45617f", "stroke-width": "1.2"})
    else:
        rx = 19 if kind == "external" else 11
        _svg(group, "rect", {"x": x, "y": y, "width": width, "height": height, "rx": rx, "class": shape_class})
    if kind == "initial":
        _svg(group, "text", {"x": x + 12, "y": y + 15, "class": "node-id"}, entity["id"])
        marker = _certainty_symbol(entity["certainty"])
        if marker:
            _svg(group, "text", {"x": x + width - 11, "y": y + 15, "class": "certainty-mark" + (" unknown-mark" if marker == "?" else ""), "text-anchor": "end"}, marker)
        _draw_text(group, x + width / 2 + 19, y + height / 2 + 5, rect["lines"], class_name="node-label")
    else:
        corner_inset = 30 if kind in {"start", "terminal"} else 12
        _svg(group, "text", {"x": x + corner_inset, "y": y + 15, "class": "node-id"}, entity["id"])
        marker = _certainty_symbol(entity["certainty"])
        if marker:
            _svg(group, "text", {"x": x + width - corner_inset, "y": y + 15, "class": "certainty-mark" + (" unknown-mark" if marker == "?" else ""), "text-anchor": "end"}, marker)
        line_height = 17.0
        total = len(rect["lines"]) * line_height
        first_y = y + height / 2 - total / 2 + 13
        _draw_text(group, x + width / 2, first_y, rect["lines"], class_name="node-label")


def _draw_sequence_participant(svg: ET.Element, entity: dict[str, Any], rect: dict[str, Any], height: float) -> None:
    x, y, width, node_height = rect["x"], rect["y"], rect["w"], rect["h"]
    cx = x + width / 2
    top = y + node_height
    _svg(svg, "line", {"x1": cx, "y1": top + 10, "x2": cx, "y2": height - 54, "class": "lifeline", "data-lifeline-for": entity["id"]})
    ui = UI_TEXT[svg.attrib.get("data-language", "en")]
    node = _svg(svg, "g", {
        "data-node-id": entity["id"], "data-label": entity["label"], "data-kind": entity["kind"],
        "data-certainty": entity["certainty"], "data-evidence": ",".join(entity["evidence_ids"]),
        "data-reason": entity.get("reason") or "",
        "role": "group", "aria-label": f"{entity['label']}; {entity['kind']}; {ui[entity['certainty']]}"})
    _svg(node, "title", text=f"{entity['id']}: {entity['label']} ({ui[entity['certainty']]})")
    shape_class = "participant" + (" participant-unknown" if entity["certainty"] == "unknown" else "")
    _svg(node, "rect", {"x": x, "y": y, "width": width, "height": node_height, "rx": 11, "class": shape_class})
    _svg(node, "text", {"x": x + 12, "y": y + 15, "class": "node-id"}, entity["id"])
    marker = _certainty_symbol(entity["certainty"])
    if marker:
        _svg(node, "text", {"x": x + width - 11, "y": y + 15, "class": "certainty-mark" + (" unknown-mark" if marker == "?" else ""), "text-anchor": "end"}, marker)
    _draw_text(node, cx, y + node_height / 2 + 5, rect["lines"], class_name="node-label")


def _draw_edge(svg: ET.Element, route: dict[str, Any], label: dict[str, Any]) -> None:
    edge = route["edge"]
    ui = UI_TEXT[svg.attrib.get("data-language", "en")]
    group = _svg(svg, "g", {
        "data-edge-id": edge["id"], "data-source": edge["source"], "data-target": edge["target"],
        "data-label": edge["label"], "data-kind": edge["kind"], "data-certainty": edge["certainty"],
        "data-evidence": ",".join(edge["evidence_ids"]), "data-reason": edge.get("reason") or "",
        "data-order": edge.get("order", ""), "data-feedback": str(edge["feedback"]).lower(), "role": "group",
        "aria-label": f"{edge['label']}; {edge['kind']}; {ui[edge['certainty']]}"})
    _svg(group, "title", text=f"{edge['id']}: {edge['label']} ({ui[edge['certainty']]})")
    kind_class = "edge"
    if edge["kind"] in {"yes", "approval"}:
        kind_class += " edge-affirmative"
    elif edge["kind"] in {"no", "cancel"}:
        kind_class += " edge-alternative"
    elif edge["kind"] == "error":
        kind_class += " edge-error"
    if edge["kind"] in {"data", "stream", "snapshot"}:
        kind_class += " edge-data"
    if edge["kind"] in {"event", "async", "retry", "timeout"}:
        kind_class += " edge-event"
    if edge["kind"] == "return":
        kind_class += " edge-return"
    if edge["feedback"]:
        kind_class += " edge-feedback"
    if edge["certainty"] == "inferred":
        kind_class += " edge-inferred"
    elif edge["certainty"] == "unknown":
        kind_class += " edge-unknown"
    _svg(group, "path", {"d": _line_path(route["points"]), "class": kind_class})
    box_x = label["x"] - label["w"] / 2
    box_y = label["y"] - label["h"] / 2
    _svg(group, "rect", {"x": f"{box_x:.1f}", "y": f"{box_y:.1f}", "width": f"{label['w']:.1f}", "height": f"{label['h']:.1f}", "rx": 5, "class": "edge-label-bg"})
    _draw_text(group, label["x"], label["y"] - (len(label["lines"]) - 1) * 7.0 + 4, label["lines"], class_name="edge-label", line_height=15)


def _draw_header(svg: ET.Element, spec: dict[str, Any], git: dict[str, Any]) -> None:
    ui = _ui(spec)
    type_label = ui["type"][spec["type"]]
    _svg(svg, "text", {"x": 72, "y": 44, "class": "header-kicker"}, f"PATPAT  /  {type_label.upper()}")
    title_lines = _wrap(spec["title"], 950)
    _draw_text(svg, 72, 82, title_lines, class_name="title", anchor="start", line_height=31)
    summary_y = 119 + (len(title_lines) - 1) * 31
    summary_lines = _wrap(spec["summary"], 1100)
    _draw_text(svg, 72, summary_y, summary_lines, class_name="summary", anchor="start", line_height=19)
    revision = (
        f"{git['name']}  ·  {git['revision'][:12]}  ·  {ui['repo_dirty'] if git['dirty'] else ui['repo_clean']}"
        if git.get("revision")
        else ui["brief_source"]
    )
    _svg(svg, "text", {"x": 72, "y": summary_y + len(summary_lines) * 17 + 3, "class": "provenance"}, revision)


def _draw_legend(svg: ET.Element, top: float, width: float, spec: dict[str, Any]) -> None:
    ui = _ui(spec)
    y = top
    _svg(svg, "text", {"x": 72, "y": y, "class": "legend-title"}, ui["confidence"])
    cursor = 230.0
    for key, dash in (("confirmed", ""), ("inferred", "legend-dash"), ("unknown", "legend-dot")):
        _svg(svg, "line", {"x1": cursor, "y1": y - 4, "x2": cursor + 30, "y2": y - 4, "class": "legend-line " + dash})
        symbol = _certainty_symbol(key)
        if symbol:
            _svg(svg, "text", {"x": cursor + 15, "y": y - 8, "class": "legend", "text-anchor": "middle"}, symbol)
        _svg(svg, "text", {"x": cursor + 38, "y": y, "class": "legend"}, ui[key])
        cursor += 142
    _svg(svg, "text", {"x": width - 72, "y": y, "class": "legend", "text-anchor": "end"}, ui["line_styles"])


def _svg_document(spec: dict[str, Any], git: dict[str, Any], layout: dict[str, Any]) -> bytes:
    width, height = layout["width"], layout["height"]
    root = ET.Element(_tag("svg"), {
        "viewBox": f"0 0 {width:.0f} {height:.0f}",
        "width": f"{width:.0f}",
        "height": f"{height:.0f}",
        "data-language": spec["language"],
        "data-diagram-type": spec["type"],
        "lang": spec["language"],
        "role": "img",
        "aria-labelledby": "diagram-title diagram-description",
        "focusable": "false",
        "version": "1.1",
    })
    title = _svg(root, "title", {"id": "diagram-title"}, spec["title"])
    del title
    ui = _ui(spec)
    if spec["language"] == "th":
        description = f"{spec['summary']} มีองค์ประกอบ {len(spec['entities'])} รายการ และความสัมพันธ์ {len(spec['edges'])} รายการ ดูหลักฐานได้ในไฟล์ HTML"
    else:
        description = f"{spec['summary']}. {len(spec['entities'])} elements and {len(spec['edges'])} relationships. Source evidence is listed in the accompanying HTML file."
    _svg(root, "desc", {"id": "diagram-description"}, description)
    defs = _svg(root, "defs")
    marker = _svg(defs, "marker", {"id": "arrow", "viewBox": "0 0 10 10", "refX": 9, "refY": 5, "markerWidth": 7, "markerHeight": 7, "orient": "auto-start-reverse"})
    _svg(marker, "path", {"d": "M 0 0 L 10 5 L 0 10 z", "class": "flow-arrow"})
    _svg(defs, "style", text=SVG_CSS)
    _svg(root, "rect", {"x": 0, "y": 0, "width": width, "height": height, "class": "canvas"})
    _svg(root, "rect", {"x": 18, "y": 18, "width": width - 36, "height": height - 36, "rx": 18, "class": "paper"})
    _draw_header(root, spec, git)
    if spec["type"] == "sequence":
        for entity in spec["entities"]:
            _draw_sequence_participant(root, entity, layout["positions"][entity["id"]], height)
    else:
        for group in layout["groups"]:
            _draw_group(root, group)
    for route, label in zip(layout["paths"], layout["labels"], strict=True):
        _draw_edge(root, route, label)
    if spec["type"] != "sequence":
        for entity in spec["entities"]:
            _draw_graph_node(root, entity, layout["positions"][entity["id"]])
    _draw_legend(root, height - 52, width, spec)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _viewer_script() -> str:
    script_path = Path(__file__).with_name("viewer.js")
    try:
        source = script_path.read_text(encoding="utf-8")
    except OSError as error:
        raise DiagramError("trusted viewer source is unavailable") from error
    if len(source.encode("utf-8")) > 100_000 or "</script" in source.lower():
        raise DiagramError("trusted viewer source failed its integrity boundary")
    return source


def _content_security_policy(style: str, script: str) -> str:
    style_hashes = [
        "'sha256-" + base64.b64encode(hashlib.sha256(value.encode("utf-8")).digest()).decode("ascii") + "'"
        for value in (style, SVG_CSS)
    ]
    script_source = "'none'" if not script else "'sha256-" + base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii") + "'"
    connect_source = "'self'" if script else "'none'"
    return (
        "default-src 'none'; base-uri 'none'; form-action 'none'; img-src data: blob:; media-src blob:; "
        f"style-src {' '.join(style_hashes)}; script-src {script_source}; connect-src {connect_source}; "
        "object-src 'none'; frame-src 'none'; font-src 'none'"
    )


def _viewer_controls(language: str, views: list[dict[str, Any]] | None = None) -> str:
    labels = VIEWER_TEXT[language]
    story_guide = f"<li>{html.escape(labels['guide_story'])}</li>" if views else ""
    explore_title = labels["tools"] + (f" · {labels['story']}" if views else "")
    return f"""<section class="diagram-tools" aria-label="{html.escape(labels['tools'])}">
<div class="primary-toolbar">
<div class="tool-field search-field"><label class="sr-only" for="diagram-search">{html.escape(labels['search'])}</label><input id="diagram-search" type="search" autocomplete="off" placeholder="{html.escape(labels['search'])}" role="combobox" aria-autocomplete="list" aria-haspopup="listbox" aria-controls="diagram-search-results" aria-expanded="false"><div id="diagram-search-results" class="search-results" role="listbox" aria-label="{html.escape(labels['search_results'])}" hidden></div></div>
<div class="primary-actions" role="group" aria-label="{html.escape(labels['tools'])}">
<button id="theme-toggle" type="button" aria-pressed="true" aria-keyshortcuts="T">{html.escape(labels['theme'])}</button><button id="visual-preset" type="button" aria-keyshortcuts="S">{html.escape(labels['visual_preset'])}</button><button id="presentation-toggle" type="button" aria-keyshortcuts="F">{html.escape(labels['presentation'])}</button>
<details id="export-tools" class="export-tools"><summary>{html.escape(labels['export'])}</summary><div class="export-grid">
<button type="button" data-export="png">{html.escape(labels['png'])}</button><button type="button" data-export="png-copy">{html.escape(labels['png_copy'])}</button><button type="button" data-export="jpeg">{html.escape(labels['jpeg'])}</button><button type="button" data-export="webp">{html.escape(labels['webp'])}</button>
<button type="button" data-export="svg-auto">{html.escape(labels['svg_auto'])}</button><button type="button" data-export="svg-pair">{html.escape(labels['svg_pair'])}</button><button type="button" data-export="webm">{html.escape(labels['webm'])}</button>
<button id="route-share" type="button" disabled>{html.escape(labels['route_card'])}</button><button id="reach-share" type="button" disabled>{html.escape(labels['reach_card'])}</button>
</div></details>
<span id="preview-status" class="preview-status" hidden></span>
</div>
</div>
<details class="overview-drawer"><summary>{html.escape(labels['overview'].split(' · ', 1)[0])}</summary><div class="diagram-overview" role="group" aria-label="{html.escape(labels['overview'])}"><p class="overview-caption">{html.escape(labels['overview'])}</p><div id="diagram-overview"></div></div></details>
<details id="explore-tools" class="explore-tools"><summary>{html.escape(explore_title)}</summary><div class="advanced-tools">
<div class="tool-row">
<div class="tool-field"><label for="focus-node">{html.escape(labels['focus'])}</label><select id="focus-node"></select></div>
<div class="tool-field"><label for="semantic-lens">{html.escape(labels['lens'])}</label><select id="semantic-lens"><option value="all">{html.escape(labels['all_kinds'])}</option></select></div>
<div class="tool-field"><label for="evidence-lens">{html.escape(labels['certainty_lens'])}</label><select id="evidence-lens"><option value="all">{html.escape(labels['all'])}</option><option value="confirmed">{html.escape(labels['confirmed'])}</option><option value="inferred">{html.escape(labels['inferred'])}</option><option value="unknown">{html.escape(labels['unknown'])}</option></select></div>
</div>
{f'''<div class="story-explorer" role="group" aria-label="{html.escape(labels['story'])}">
<div class="tool-field"><label for="story-view">{html.escape(labels['story_view'])}</label><select id="story-view"><option value="">{html.escape(labels['story_choose'])}</option></select></div>
<button id="story-start" type="button">{html.escape(labels['story_start'])}</button><button id="story-previous" type="button" disabled>{html.escape(labels['story_previous'])}</button><button id="story-next" type="button" disabled>{html.escape(labels['story_next'])}</button><button id="story-clear" type="button" disabled>{html.escape(labels['story_clear'])}</button>
<output id="story-status" class="tool-status" aria-live="polite"></output>
</div>''' if views else ''}
<div class="tool-row role-comparison" role="group" aria-label="{html.escape(labels['role_compare'])}">
<div class="tool-field"><label for="role-kind-a">{html.escape(labels['role_a'])}</label><select id="role-kind-a"></select></div>
<div class="tool-field"><label for="role-kind-b">{html.escape(labels['role_b'])}</label><select id="role-kind-b"></select></div>
<button id="role-compare" type="button">{html.escape(labels['role_compare'])}</button><button id="role-compare-clear" type="button" disabled>{html.escape(labels['role_compare_clear'])}</button>
</div><output id="role-comparison-status" class="tool-status" aria-live="polite"></output>
<div class="tool-row" role="group" aria-label="{html.escape(labels['focus'])}"><button id="focus-upstream" type="button">{html.escape(labels['upstream'])}</button><button id="focus-downstream" type="button">{html.escape(labels['downstream'])}</button><button id="focus-clear" type="button">{html.escape(labels['clear'])}</button><button id="contrast-toggle" type="button" aria-pressed="false">{html.escape(labels['contrast'])}</button></div>
<div class="tool-row">
<div class="tool-field"><label for="route-from">{html.escape(labels['from'])}</label><select id="route-from"></select></div>
<div class="tool-field"><label for="route-to">{html.escape(labels['to'])}</label><select id="route-to"></select></div>
<button id="route-probe" type="button">{html.escape(labels['probe'])}</button><button id="motion-trace" type="button">{html.escape(labels['trace'])}</button>
<button id="zoom-out" type="button" aria-label="{html.escape(labels['zoom_out'])}">−</button><button id="zoom-reset" type="button" aria-label="{html.escape(labels['zoom_reset'])}">100%</button><button id="zoom-in" type="button" aria-label="{html.escape(labels['zoom_in'])}">+</button>
</div>
<div id="diagram-depth" class="tool-row" role="group" aria-label="{html.escape(labels['read_depth'])}"><button id="depth-auto" type="button" data-depth-mode="auto" aria-pressed="true">{html.escape(labels['depth_auto_status'].replace('{depth}', labels['read_mode']))}</button><button type="button" data-depth="map">{html.escape(labels['map_mode'])}</button><button type="button" data-depth="read">{html.escape(labels['read_mode'])}</button><button type="button" data-depth="full">{html.escape(labels['full_mode'])}</button></div>
<output id="viewer-status" class="tool-status" aria-live="polite">{html.escape(labels['status'])}</output>
<div id="route-details" class="route-details" hidden><strong id="route-title"></strong><ol id="route-step-list"></ol><div id="route-journey" class="route-journey" hidden><button id="route-previous" type="button">{html.escape(labels['previous_step'])}</button><output id="route-step-status"></output><button id="route-next" type="button">{html.escape(labels['next_step'])}</button><button id="route-stop" type="button">{html.escape(labels['stop_trace'])}</button></div></div>
<p class="tool-caption">{html.escape(labels['context'])}</p><div id="relationship-context" class="relationship-context" role="group" aria-label="{html.escape(labels['context'])}"></div>
<section id="semantic-passport" class="semantic-passport" aria-labelledby="passport-title" hidden>
<div class="passport-heading"><h3 id="passport-title">{html.escape(labels['passport'])}</h3><div><button id="passport-copy" type="button">{html.escape(labels['passport_copy'])}</button><button id="passport-close" type="button">{html.escape(labels['passport_close'])}</button></div></div>
<div id="passport-body"></div><output id="passport-status" class="tool-status" aria-live="polite"></output>
</section>
<details class="viewer-guide"><summary>{html.escape(labels['guide'])}</summary><ul><li>{html.escape(labels['guide_search'])}</li><li>{html.escape(labels['guide_focus'])}</li><li>{html.escape(labels['guide_reach'])}</li><li>{html.escape(labels['guide_route'])}</li><li>{html.escape(labels['guide_roles'])}</li>{story_guide}<li>{html.escape(labels['guide_keys'])}</li></ul></details>
<noscript><p>{html.escape(labels['noscript'])}</p></noscript>
</div></details>
<button id="presentation-exit" type="button">{html.escape(labels['presentation_exit'])}</button>
</section>"""


def _github_source_identity(repository: dict[str, Any] | None) -> tuple[str, str, str] | None:
    if not isinstance(repository, dict):
        return None
    origin = repository.get("origin")
    revision = repository.get("revision")
    if not isinstance(origin, str) or not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        return None
    normalized_origin = origin.removesuffix(".git")
    match = re.fullmatch(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+)", normalized_origin, re.IGNORECASE)
    if not match:
        return None
    owner, repository_name = match.groups()
    return owner, repository_name, revision


class _GithubApiRedirectPolicy(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        parsed = urllib.parse.urlsplit(new_url)
        if parsed.scheme != "https" or parsed.hostname != "api.github.com" or parsed.username or parsed.password or parsed.port is not None:
            return None
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _github_api_json(opener: urllib.request.OpenerDirector, url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "patpat-repository-diagram",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with opener.open(request, timeout=5) as response:
        final_url = urllib.parse.urlsplit(response.geturl())
        if final_url.scheme != "https" or final_url.hostname != "api.github.com" or final_url.username or final_url.password or final_url.port is not None:
            raise ValueError("GitHub API redirected outside its trusted host")
        if response.status != 200:
            raise ValueError("GitHub API did not confirm the public resource")
        payload = response.read(1_000_001)
    if len(payload) > 1_000_000:
        raise ValueError("GitHub API response exceeded its size limit")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("GitHub API returned an unexpected response")
    return data


def _verify_public_github_source(repository: dict[str, Any] | None, evidence: Any) -> dict[str, Any]:
    """Check public visibility and commit reachability without credentials or configured proxies."""
    identity = _github_source_identity(repository)
    checked_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if identity is None:
        return {"status": "unavailable", "reason": "unsupported-origin", "checked_at": checked_at}
    owner, repository_name, revision = identity
    committed_evidence = [
        item for item in evidence if isinstance(item, dict)
        and item.get("origin", "repository") == "repository"
        and item.get("snapshot") == "committed"
        and item.get("file_sha256") == item.get("committed_file_sha256")
    ] if isinstance(evidence, list) else []
    if not committed_evidence:
        return {"status": "unavailable", "reason": "no-committed-evidence", "checked_at": checked_at}
    api_root = f"https://api.github.com/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(repository_name, safe='')}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _GithubApiRedirectPolicy())
    try:
        public_repo = _github_api_json(opener, api_root)
        if public_repo.get("private") is not False or public_repo.get("full_name", "").casefold() != f"{owner}/{repository_name}".casefold():
            return {"status": "unavailable", "reason": "repository-not-public", "checked_at": checked_at}
        public_commit = _github_api_json(opener, f"{api_root}/commits/{revision}")
        if public_commit.get("sha", "").lower() != revision:
            return {"status": "unavailable", "reason": "commit-not-public", "checked_at": checked_at}
    except (OSError, TimeoutError, ValueError, urllib.error.URLError, http.client.HTTPException, json.JSONDecodeError):
        return {"status": "unavailable", "reason": "anonymous-verification-failed", "checked_at": checked_at}
    return {
        "status": "verified",
        "provider": "api.github.com",
        "repository": f"{owner}/{repository_name}",
        "revision": revision,
        "checked_at": checked_at,
        "credential_free": True,
    }


def _github_source_permalinks(
    repository: dict[str, Any] | None,
    evidence: Any,
    verification: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build immutable links only after anonymous public-repository verification."""
    identity = _github_source_identity(repository)
    if (
        identity is None
        or not isinstance(verification, dict)
        or verification.get("status") != "verified"
        or verification.get("provider") != "api.github.com"
        or verification.get("credential_free") is not True
    ):
        return {}
    owner, repository_name, revision = identity
    verified_repository = verification.get("repository")
    if not isinstance(verified_repository, str) or verified_repository.casefold() != f"{owner}/{repository_name}".casefold() or verification.get("revision") != revision:
        return {}
    if not isinstance(evidence, list):
        return {}
    links: dict[str, str] = {}
    for item in evidence:
        if not isinstance(item, dict) or item.get("origin", "repository") != "repository":
            continue
        if item.get("snapshot") != "committed" or not item.get("file_sha256") or item.get("file_sha256") != item.get("committed_file_sha256"):
            continue
        identifier, path = item.get("id"), item.get("path")
        start, end = item.get("start_line"), item.get("end_line")
        if not isinstance(identifier, str) or not isinstance(path, str):
            continue
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            continue
        normalized_path = PurePosixPath(path)
        if normalized_path.is_absolute() or not normalized_path.parts or any(part in {".", ".."} for part in normalized_path.parts):
            continue
        encoded_path = urllib.parse.quote(normalized_path.as_posix(), safe="/-._~")
        links[identifier] = (
            f"https://github.com/{owner}/{repository_name}/blob/{revision}/{encoded_path}"
            f"#L{start}-L{end}"
        )
    return links


def _html_document(spec: dict[str, Any], git: dict[str, Any], svg: bytes, source_links: dict[str, str] | None = None) -> bytes:
    ui = _ui(spec)
    language = spec["language"]
    svg_text = svg.decode("utf-8")
    interactive = spec["schema_version"] == 2
    page_css = HTML_CSS
    script = _viewer_script() if interactive else ""
    viewer_labels = (
        '<meta name="patpat-viewer-labels" content="' + html.escape(json.dumps(VIEWER_TEXT[language], ensure_ascii=False), quote=True) + '">'
        if interactive else ""
    )
    viewer_views = (
        '<meta name="patpat-viewer-views" content="' + html.escape(json.dumps(spec["views"], ensure_ascii=False, separators=(",", ":")), quote=True) + '">'
        if interactive and spec.get("views") else ""
    )
    security_meta = (
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(_content_security_policy(page_css, script), quote=True)}">'
    )
    type_label = ui["type"][spec["type"]]
    nodes = []
    for entity in spec["entities"]:
        evidence = ", ".join(entity["evidence_ids"]) or ui["no_anchor"]
        nodes.append(
            "<tr>"
            f"<th scope=\"row\"><code>{html.escape(entity['id'])}</code></th>"
            f"<td>{html.escape(entity['label'])}</td><td>{html.escape(entity['kind'])}</td>"
            f"<td class=\"certainty {entity['certainty']}\">{html.escape(ui[entity['certainty']])}</td>"
            f"<td><code>{html.escape(evidence)}</code>{html.escape(': ' + entity['reason']) if entity['reason'] else ''}</td>"
            "</tr>"
        )
    relations = []
    for edge in sorted(spec["edges"], key=lambda item: item.get("order", 0)):
        evidence = ", ".join(edge["evidence_ids"]) or ui["no_anchor"]
        relations.append(
            "<tr>"
            f"<th scope=\"row\"><code>{html.escape(edge['id'])}</code></th>"
            f"<td><code>{html.escape(edge['source'])}</code> → <code>{html.escape(edge['target'])}</code></td>"
            f"<td>{html.escape(edge['label'])}</td><td>{html.escape(edge['kind'])}</td>"
            f"<td class=\"certainty {edge['certainty']}\">{html.escape(ui[edge['certainty']])}</td>"
            f"<td><code>{html.escape(evidence)}</code>{html.escape(': ' + edge['reason']) if edge['reason'] else ''}</td>"
            "</tr>"
        )
    evidence_rows = []
    for evidence_id, item in spec["snapshots"].items():
        if item.get("origin", "repository") == "brief":
            location = ui["brief_evidence"]
            snapshot_label = ui["brief_snapshot"]
            committed_digest = ui["not_committed"]
        else:
            location = f"{item['path']}:L{item['start_line']}-L{item['end_line']}"
            snapshot_label = ui["committed_snapshot"] if item["snapshot"] == "committed" else ui["working_snapshot"]
            committed_digest = item["committed_file_sha256"][:16] if item["committed_file_sha256"] else ui["not_committed"]
        permalink = (source_links or {}).get(evidence_id)
        location_cell = (
            f'<a data-source-link-id="{html.escape(evidence_id, quote=True)}" href="{html.escape(permalink, quote=True)}" '
            f'target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" title="{html.escape(ui["source_permalink"], quote=True)}">'
            f"<code>{html.escape(location)}</code></a>"
            if permalink else f"<code>{html.escape(location)}</code>"
        )
        evidence_rows.append(
            "<tr>"
            f"<th id=\"evidence-{html.escape(evidence_id, quote=True)}\" scope=\"row\"><code>{html.escape(evidence_id)}</code></th>"
            f"<td>{html.escape(item['claim'])}</td>"
            f"<td>{location_cell}</td>"
            f"<td>{html.escape(snapshot_label)}</td>"
            f"<td><code>{item['sha256'][:16]}</code></td><td><code>{html.escape(committed_digest)}</code></td>"
            "</tr>"
        )
    group_rows = []
    for group in spec["groups"]:
        evidence = ", ".join(group["evidence_ids"]) or ui["no_anchor"]
        group_rows.append(
            "<tr>"
            f"<th scope=\"row\"><code>{html.escape(group['id'])}</code></th>"
            f"<td>{html.escape(group['label'])}</td>"
            f"<td><code>{html.escape(', '.join(group['members']))}</code></td>"
            f"<td class=\"certainty {group['certainty']}\">{html.escape(ui[group['certainty']])}</td>"
            f"<td><code>{html.escape(evidence)}</code>{html.escape(': ' + group['reason']) if group['reason'] else ''}</td>"
            "</tr>"
        )
    changed_path_items = git.get("changed_paths", [])
    changed_paths = "".join(f"<li><code>{html.escape(path)}</code></li>" for path in changed_path_items)
    if git.get("revision"):
        provenance = (
            f"<details class=\"provenance-details\"><summary>{html.escape(ui['provenance'])}</summary>"
            f"<p><code>{html.escape(git['name'])}</code> · <code>{html.escape(git['revision'])}</code> · "
            f"{html.escape(ui['working_dirty'] if git['dirty'] else ui['working_clean'])}</p>"
            f"<p>{html.escape(ui['origin'])}: <code>{html.escape(git.get('origin') or 'unavailable')}</code></p>"
            f"<p>{html.escape(ui['changed_paths'])}</p><ul>{changed_paths}</ul>"
            f"{'<p>Changed path list truncated at 500 entries.</p>' if git.get('changed_paths_truncated', False) else ''}</details>"
        )
    else:
        provenance = (
            f"<details class=\"provenance-details\"><summary>{html.escape(ui['provenance'])}</summary>"
            f"<p>{html.escape(ui['brief_source'])}</p></details>"
        )
    html_text = f"""<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="patpat-diagram-version" content="{TOOL_VERSION}">
<meta name="patpat-diagram-revision" content="{html.escape(git.get('revision') or '', quote=True)}">
<meta name="patpat-diagram-schema" content="{spec['schema_version']}">
{security_meta}
{viewer_labels}
{viewer_views}
<title>{html.escape(spec['title'])} · Patpat {html.escape(type_label)} {html.escape(ui['diagram'])}</title>
<style>{page_css}</style>
</head>
<body id="diagram-body" data-theme="dark" data-depth="read" data-depth-mode="auto" data-visual-preset="balanced">
<main>
<h1 class="sr-only">{html.escape(spec['title'])}</h1>
<div class="mobile-diagram-intro"><h2>{html.escape(spec['title'])}</h2><p>{html.escape(spec['summary'])}</p></div>
{_viewer_controls(language, spec.get('views', [])) if interactive else ''}
<p class="diagram-pan-hint">{html.escape(ui['pan_hint'])}</p>
<figure role="region" tabindex="0" aria-label="{html.escape(spec['title'])}">
{svg_text}
</figure>
<section aria-labelledby="outline-heading">
<h2 id="outline-heading">{html.escape(ui['outline'])}</h2>
<p>{html.escape(ui['outline_help'])}</p>
<div class="table-wrap" role="region" tabindex="0" aria-label="{html.escape(ui['entities'])}"><table class="alt-table">
<caption>{html.escape(ui['entities'])}</caption><thead><tr><th scope="col">{html.escape(ui['id'])}</th><th scope="col">{html.escape(ui['label'])}</th><th scope="col">{html.escape(ui['kind'])}</th><th scope="col">{html.escape(ui['evidence_status'])}</th><th scope="col">{html.escape(ui['source_refs'])}</th></tr></thead>
<tbody>{''.join(nodes)}</tbody></table></div>
<div class="table-wrap" role="region" tabindex="0" aria-label="{html.escape(ui['relationships'])}"><table class="alt-table">
<caption>{html.escape(ui['relationships'])}</caption><thead><tr><th scope="col">{html.escape(ui['id'])}</th><th scope="col">{html.escape(ui['direction'])}</th><th scope="col">{html.escape(ui['label'])}</th><th scope="col">{html.escape(ui['kind'])}</th><th scope="col">{html.escape(ui['evidence_status'])}</th><th scope="col">{html.escape(ui['source_refs'])}</th></tr></thead>
<tbody>{''.join(relations)}</tbody></table></div>
{'<div class="table-wrap" role="region" tabindex="0" aria-label="' + html.escape(ui['boundaries'], quote=True) + '"><table class="alt-table"><caption>' + html.escape(ui['boundaries']) + '</caption><thead><tr><th scope="col">' + html.escape(ui['id']) + '</th><th scope="col">' + html.escape(ui['label']) + '</th><th scope="col">' + html.escape(ui['members']) + '</th><th scope="col">' + html.escape(ui['evidence_status']) + '</th><th scope="col">' + html.escape(ui['source_refs']) + '</th></tr></thead><tbody>' + ''.join(group_rows) + '</tbody></table></div>' if group_rows else ''}
</section>
<details>
<summary>{html.escape(ui['source_evidence'])} ({len(evidence_rows)})</summary>
<div class="table-wrap" role="region" tabindex="0" aria-label="{html.escape(ui['source_evidence'])}"><table class="evidence-table">
<thead><tr><th scope="col">{html.escape(ui['id'])}</th><th scope="col">{html.escape(ui['claim'])}</th><th scope="col">{html.escape(ui['repository_location'])}</th><th scope="col">{html.escape(ui['source_snapshot'])}</th><th scope="col">{html.escape(ui['line_digest'])}</th><th scope="col">{html.escape(ui['committed_digest'])}</th></tr></thead>
<tbody>{''.join(evidence_rows)}</tbody></table></div>
</details>
{provenance}
<footer>{html.escape(ui['footer'])}</footer>
</main>
{f'<script>{script}</script>' if interactive else ''}
</body>
</html>
"""
    return html_text.encode("utf-8")


def _make_layout(spec: dict[str, Any]) -> dict[str, Any]:
    if spec["type"] == "sequence":
        layout = _sequence_layout(spec)
        # Lifelines are drawn by the sequence participant renderer. Messages use ordered rows.
        return layout
    return _graph_layout(spec)


def _projected_readability(layout: dict[str, Any]) -> dict[str, Any]:
    """Project authored node labels onto a conservative desktop reader width."""
    viewbox_width = float(layout["width"])
    diagram_width = DESKTOP_READER_WIDTH - DESKTOP_READER_CHROME
    source_font_px = 16.0
    scale = min(1.0, diagram_width / viewbox_width) if viewbox_width > 0 else 0.0
    projected = source_font_px * scale
    return {
        "viewport_width_px": 1440,
        "reader_width_px": int(DESKTOP_READER_WIDTH),
        "diagram_width_px": int(diagram_width),
        "viewbox_width": int(viewbox_width),
        "source_node_text_px": source_font_px,
        "minimum_projected_node_text_px": round(projected, 2),
        "minimum_required_px": MIN_PROJECTED_NODE_TEXT_PX,
        "passed": projected >= MIN_PROJECTED_NODE_TEXT_PX,
    }


def _has_blocking_geometry_warnings(warnings: list[str]) -> bool:
    return any(warning.startswith(BLOCKING_GEOMETRY_PREFIXES) for warning in warnings)


def _valid_html_and_svg(html_bytes: bytes, svg_bytes: bytes, source_links: dict[str, str] | None = None) -> None:
    html_text = html_bytes.decode("utf-8")
    if any(token in html_text.lower() for token in ("<iframe", "<object", "<embed", "<link ", "<base ")):
        raise DiagramError("HTML contains a forbidden active element or external dependency")
    allowed_links = source_links or {}
    parser = _ArtifactParser(allowed_links)
    parser.feed(html_text)
    parser.close()
    if not parser.has_svg or parser.external_resources or parser.source_links != allowed_links:
        raise DiagramError("HTML must embed its SVG and cannot reference external resources")
    if parser.scripts:
        trusted = _viewer_script()
        if parser.scripts != [trusted]:
            raise DiagramError("HTML script differs from the versioned trusted viewer")
        if parser.styles.count(HTML_CSS) != 1 or parser.styles.count(SVG_CSS) != 1 or parser.csp is None:
            raise DiagramError("interactive HTML needs one hashed style block and a restrictive content security policy")
        style_hashes = [
            "'sha256-" + base64.b64encode(hashlib.sha256(value.encode("utf-8")).digest()).decode("ascii") + "'"
            for value in (HTML_CSS, SVG_CSS)
        ]
        script_hash = "'sha256-" + base64.b64encode(hashlib.sha256(trusted.encode("utf-8")).digest()).decode("ascii") + "'"
        expected = {
            "default-src": ["'none'"], "base-uri": ["'none'"], "form-action": ["'none'"],
            "img-src": ["data:", "blob:"], "media-src": ["blob:"], "style-src": style_hashes,
            "script-src": [script_hash], "connect-src": ["'self'"], "object-src": ["'none'"],
            "frame-src": ["'none'"], "font-src": ["'none'"],
        }
        if _csp_directives(parser.csp) != expected:
            raise DiagramError("interactive HTML content security policy is not restrictive")
    elif parser.script_tags:
        raise DiagramError("empty or non-executable script tags are forbidden")
    else:
        if parser.styles.count(HTML_CSS) != 1 or parser.styles.count(SVG_CSS) != 1 or parser.csp is None:
            raise DiagramError("static HTML needs its exact local styles and restrictive content security policy")
        style_hashes = [
            "'sha256-" + base64.b64encode(hashlib.sha256(value.encode("utf-8")).digest()).decode("ascii") + "'"
            for value in (HTML_CSS, SVG_CSS)
        ]
        expected = {
            "default-src": ["'none'"], "base-uri": ["'none'"], "form-action": ["'none'"],
            "img-src": ["data:", "blob:"], "media-src": ["blob:"], "style-src": style_hashes,
            "script-src": ["'none'"], "connect-src": ["'none'"], "object-src": ["'none'"],
            "frame-src": ["'none'"], "font-src": ["'none'"],
        }
        if _csp_directives(parser.csp) != expected:
            raise DiagramError("static HTML content security policy is not restrictive")
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as error:
        raise DiagramError(f"SVG is not well-formed XML: {error}") from error
    if root.tag != _tag("svg") or root.attrib.get("role") != "img":
        raise DiagramError("SVG must be a named accessible image")
    if root.find(_tag("title")) is None or root.find(_tag("desc")) is None:
        raise DiagramError("SVG must contain title and description text")
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1]
        if local in {"script", "foreignObject", "iframe", "image"}:
            raise DiagramError(f"SVG contains unsupported active or external element: {local}")
        if any(key.lower().startswith("on") for key in element.attrib):
            raise DiagramError("SVG event-handler attributes are forbidden")


def _csp_directives(policy: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for directive in policy.split(";"):
        pieces = directive.strip().split()
        if not pieces or pieces[0] in directives:
            raise DiagramError("HTML content security policy is empty or repeats a directive")
        directives[pieces[0]] = pieces[1:]
    return directives


class _ArtifactParser(HTMLParser):
    def __init__(self, allowed_source_links: dict[str, str] | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.allowed_source_links = allowed_source_links or {}
        self.source_links: dict[str, str] = {}
        self.has_svg = False
        self.external_resources = False
        self.scripts: list[str] = []
        self.script_tags = 0
        self.styles: list[str] = []
        self.csp: str | None = None
        self._active_text: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if len(values) != len(attrs):
            self.external_resources = True
        source_link_id = values.get("data-source-link-id")
        is_source_link = (
            tag == "a"
            and isinstance(source_link_id, str)
            and source_link_id in self.allowed_source_links
            and values.get("href") == self.allowed_source_links[source_link_id]
            and values.get("target") == "_blank"
            and set((values.get("rel") or "").lower().split()) == {"noopener", "noreferrer"}
            and values.get("referrerpolicy") == "no-referrer"
            and source_link_id not in self.source_links
        )
        if source_link_id is not None and not is_source_link:
            self.external_resources = True
        if is_source_link:
            self.source_links[source_link_id] = values["href"]
        if tag == "svg":
            self.has_svg = True
        if tag == "script":
            self.script_tags += 1
            if values.get("src") is not None or values.get("type") is not None:
                self.external_resources = True
            self._active_text = "script"
            self._buffer = []
        elif tag == "style":
            self._active_text = "style"
            self._buffer = []
        if tag == "meta":
            http_equiv = (values.get("http-equiv") or "").strip().lower()
            if http_equiv and http_equiv != "content-security-policy":
                self.external_resources = True
            if http_equiv == "content-security-policy":
                if self.csp is not None:
                    self.external_resources = True
                self.csp = values.get("content")
        for name, value in attrs:
            if name.lower() in {"src", "href", "poster", "srcset", "action", "formaction", "xlink:href"} and value and not value.startswith("#") and not (name.lower() == "href" and is_source_link):
                self.external_resources = True
            if name.lower().startswith("on"):
                self.external_resources = True
            if name.lower() == "style":
                self.external_resources = True

    def handle_data(self, data: str) -> None:
        if self._active_text:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != self._active_text:
            return
        value = "".join(self._buffer)
        if tag == "script":
            self.scripts.append(value)
        elif tag == "style":
            self.styles.append(value)
        self._active_text = None
        self._buffer = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _valid_static_page(page_bytes: bytes, expected_css: str) -> None:
    page_text = page_bytes.decode("utf-8")
    if any(token in page_text.lower() for token in ("<script", "<iframe", "<object", "<embed", "<link ", "<base ")):
        raise DiagramError("static page contains active content or an external dependency")
    parser = _ArtifactParser()
    parser.feed(page_text)
    parser.close()
    if parser.scripts or parser.script_tags or parser.external_resources or parser.styles != [expected_css] or not parser.csp:
        raise DiagramError("static page must use one trusted local stylesheet and no executable or external content")
    css_hash = "'sha256-" + base64.b64encode(hashlib.sha256(expected_css.encode("utf-8")).digest()).decode("ascii") + "'"
    if _csp_directives(parser.csp) != {
        "default-src": ["'none'"], "base-uri": ["'none'"], "form-action": ["'none'"], "style-src": [css_hash],
    }:
        raise DiagramError("static page content security policy is not restrictive")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_transaction(path: Path, transaction: dict[str, Any]) -> None:
    temporary = path.with_suffix(".next")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write((json.dumps(transaction, sort_keys=True) + "\n").encode("utf-8"))
        output.flush()
        os.fsync(output.fileno())
    if os.name == "posix":
        os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _validate_private_staging(staging: Path) -> None:
    if os.name != "posix" or not hasattr(os, "geteuid"):
        raise DiagramError("cannot prove interrupted transaction ownership on this platform; inspect it manually")
    try:
        directory = staging.lstat()
        journal = (staging / "transaction.json").lstat()
    except OSError as error:
        raise DiagramError(f"cannot inspect interrupted transaction permissions: {staging.name}") from error
    owner = os.geteuid()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != owner or stat.S_IMODE(directory.st_mode) != 0o700:
        raise DiagramError(f"refusing recovery from a transaction directory that is not private and user-owned: {staging.name}")
    if (
        not stat.S_ISREG(journal.st_mode)
        or journal.st_uid != owner
        or stat.S_IMODE(journal.st_mode) != 0o600
        or journal.st_nlink != 1
    ):
        raise DiagramError(f"refusing recovery from a transaction journal that is not private and user-owned: {staging.name}")


def _transaction_names(kind: str, slug: str) -> set[str]:
    if not isinstance(kind, str) or not isinstance(slug, str) or not SLUG_PATTERN.fullmatch(slug):
        raise DiagramError("interrupted output transaction has an invalid artifact slug")
    if kind == "diagram":
        return {f"{slug}.diagram.json", f"{slug}.svg", f"{slug}.html", f"{slug}.receipt.json"}
    if kind == "delta":
        return {f"{slug}.delta.json", f"{slug}.delta.html", f"{slug}.delta.receipt.json"}
    if kind == "browser":
        return {f"{slug}.browser.png", f"{slug}.browser.receipt.json"}
    if kind == "browser-showcase":
        captures = {f"{slug}.showcase-{view}-{theme}.png" for view in ("desktop", "tablet", "mobile") for theme in ("light", "dark")}
        captures.remove(f"{slug}.showcase-desktop-light.png")
        return {f"{slug}.browser.png", f"{slug}.browser.receipt.json", f"{slug}.showcase-contact.svg", *captures}
    if kind == "finalize":
        return _transaction_names("diagram", slug) | _transaction_names("browser", slug)
    if kind == "finalize-showcase":
        return _transaction_names("diagram", slug) | _transaction_names("browser-showcase", slug)
    raise DiagramError("interrupted output transaction has an unsupported output kind")


def _validate_transaction(transaction: Any, staging: Path) -> list[dict[str, Any]]:
    if not isinstance(transaction, dict) or set(transaction) != {"tool", "schema_version", "owner_pid", "phase", "kind", "slug", "entries"}:
        raise DiagramError(f"interrupted output transaction has an unsupported journal: {staging.name}")
    if transaction.get("tool") != "patpat-repository-diagram" or transaction.get("schema_version") != 1 or transaction.get("phase") not in {"staging", "prepared", "committed"}:
        raise DiagramError(f"interrupted output transaction has an unsupported journal: {staging.name}")
    owner = transaction.get("owner_pid")
    if isinstance(owner, bool) or not isinstance(owner, int) or owner < 1:
        raise DiagramError(f"interrupted output transaction has an invalid owner: {staging.name}")
    expected = _transaction_names(transaction.get("kind"), transaction.get("slug"))
    entries = transaction.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > len(expected):
        raise DiagramError(f"interrupted output transaction has an incomplete file set: {staging.name}")
    seen: set[str] = set()
    normalized = []
    digest_pattern = re.compile(r"^[0-9a-f]{64}$")
    for index, entry in enumerate(entries):
        required = {"name", "staged", "backup", "had_existing", "old_sha256", "new_sha256"}
        if not isinstance(entry, dict) or set(entry) != required:
            raise DiagramError(f"interrupted output transaction has an invalid entry: {staging.name}")
        name = entry.get("name")
        if not isinstance(name, str) or name not in expected or name in seen:
            raise DiagramError(f"interrupted output transaction targets an unsupported file: {staging.name}")
        seen.add(name)
        if entry.get("staged") != f"new-{index}" or entry.get("backup") != f"old-{index}":
            raise DiagramError(f"interrupted output transaction has an unsafe staging path: {staging.name}")
        had_existing = entry.get("had_existing")
        old_digest, new_digest = entry.get("old_sha256"), entry.get("new_sha256")
        if not isinstance(had_existing, bool) or not isinstance(new_digest, str) or not digest_pattern.fullmatch(new_digest):
            raise DiagramError(f"interrupted output transaction has an invalid digest: {staging.name}")
        if had_existing:
            if not isinstance(old_digest, str) or not digest_pattern.fullmatch(old_digest):
                raise DiagramError(f"interrupted output transaction has no valid previous digest: {staging.name}")
        elif old_digest is not None:
            raise DiagramError(f"interrupted output transaction has an unexpected previous digest: {staging.name}")
        normalized.append(entry)
    if kind := transaction.get("kind"):
        complete = seen.issubset(expected) and bool(seen) if kind == "browser" else seen == expected
    else:
        complete = False
    if not complete:
        raise DiagramError(f"interrupted output transaction does not match its artifact set: {staging.name}")
    return normalized


def _staging_files(staging: Path, entries: list[dict[str, Any]]) -> set[str]:
    allowed = {"transaction.json", "transaction.next"}
    for entry in entries:
        allowed.update({entry["staged"], entry["backup"]})
    for child in staging.iterdir():
        if child.name not in allowed or child.is_symlink() or not child.is_file():
            raise DiagramError(f"interrupted output transaction contains an unsafe staging entry: {staging.name}/{child.name}")
        if child.stat().st_nlink != 1:
            raise DiagramError(f"interrupted output transaction contains a hard-linked staging entry: {staging.name}/{child.name}")
    return {child.name for child in staging.iterdir()}


def _remove_staging(staging: Path, allowed_files: set[str]) -> None:
    if staging.is_symlink() or not staging.is_dir():
        raise DiagramError(f"interrupted output transaction staging directory changed: {staging.name}")
    for child in staging.iterdir():
        if child.name not in allowed_files or child.is_symlink() or not child.is_file() or child.stat().st_nlink != 1:
            raise DiagramError(f"refusing to remove an unknown transaction entry: {staging.name}/{child.name}")
        child.unlink()
    staging.rmdir()


def _recover_transaction(
    staging: Path,
    output_dir: Path,
    transaction: dict[str, Any] | None = None,
    *,
    trusted_current: bool = False,
) -> None:
    journal_path = staging / "transaction.json"
    if not trusted_current:
        _validate_private_staging(staging)
    if transaction is None:
        try:
            if journal_path.is_symlink() or not journal_path.is_file():
                raise DiagramError(f"interrupted output transaction has no regular recovery journal: {staging.name}")
            transaction = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DiagramError(f"interrupted output transaction has no valid recovery journal: {staging.name}") from error
    entries = _validate_transaction(transaction, staging)
    present = _staging_files(staging, entries)
    allowed_files = {"transaction.json", "transaction.next"}
    for entry in entries:
        allowed_files.update({entry["staged"], entry["backup"]})
    phase = transaction["phase"]
    if phase == "staging":
        # Targets are untouched until the prepared journal is durable.
        _remove_staging(staging, allowed_files)
        return
    if phase == "committed":
        for entry in entries:
            target = output_dir / entry["name"]
            if target.is_symlink() or not target.is_file() or target.stat().st_nlink != 1 or _file_sha256(target) != entry["new_sha256"]:
                raise DiagramError(f"committed output does not match its transaction journal: {entry['name']}")
        for entry in entries:
            backup = staging / entry["backup"]
            if backup.name in present and (not entry["had_existing"] or _file_sha256(backup) != entry["old_sha256"]):
                raise DiagramError(f"committed transaction backup failed integrity check: {entry['name']}")
        _remove_staging(staging, allowed_files)
        return

    # Verify the entire recovery set before replacing or removing any public path.
    for entry in entries:
        target = output_dir / entry["name"]
        staged = staging / entry["staged"]
        backup = staging / entry["backup"]
        if staged.name in present and _file_sha256(staged) != entry["new_sha256"]:
            raise DiagramError(f"staged output failed integrity check during recovery: {entry['name']}")
        if entry["had_existing"]:
            if backup.name not in present or _file_sha256(backup) != entry["old_sha256"]:
                raise DiagramError(f"previous output backup failed integrity check: {entry['name']}")
            if target.is_symlink() or target.exists() and (not target.is_file() or target.stat().st_nlink != 1 or _file_sha256(target) not in {entry["old_sha256"], entry["new_sha256"]}):
                raise DiagramError(f"refusing to overwrite a concurrent change during recovery: {entry['name']}")
        else:
            if backup.name in present:
                raise DiagramError(f"unexpected recovery backup for new output: {entry['name']}")
            if target.is_symlink() or target.exists() and (not target.is_file() or target.stat().st_nlink != 1 or _file_sha256(target) != entry["new_sha256"]):
                raise DiagramError(f"refusing to remove a concurrent change during recovery: {entry['name']}")
            if staged.name not in present and not target.is_file():
                raise DiagramError(f"new output and staged candidate are both missing: {entry['name']}")

    for entry in reversed(entries):
        target = output_dir / entry["name"]
        backup = staging / entry["backup"]
        if entry["had_existing"]:
            os.replace(backup, target)
        elif target.exists():
            target.unlink()
    _remove_staging(staging, allowed_files)


def _recover_output_sets(output_dir: Path) -> None:
    for staging in sorted(output_dir.glob(".patpat-diagram-tx-*")):
        if not staging.is_dir() or staging.is_symlink():
            continue
        _validate_private_staging(staging)
        journal = staging / "transaction.json"
        if journal.is_symlink() or not journal.is_file():
            continue
        try:
            transaction = json.loads(journal.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise DiagramError(f"could not inspect interrupted output transaction {staging.name}") from error
        entries = _validate_transaction(transaction, staging)
        _staging_files(staging, entries)
        owner = transaction["owner_pid"]
        if owner == os.getpid():
            raise DiagramError("another output transaction in this process is active")
        try:
            os.kill(owner, 0)
        except ProcessLookupError:
            pass
        except OSError as error:
            if error.errno == errno.ESRCH:
                pass
            else:
                raise DiagramError(f"cannot establish whether output transaction owner {owner} is still active") from error
        else:
            raise DiagramError("another diagram output transaction is active")
        _recover_transaction(staging, output_dir, transaction)


@contextmanager
def _output_transaction_lock(output_dir: Path) -> Iterator[None]:
    resolved_output = output_dir.resolve()
    key = os.path.normcase(str(resolved_output))
    with _OUTPUT_LOCKS_GUARD:
        thread_lock = _OUTPUT_LOCKS.setdefault(key, threading.Lock())

    with thread_lock:
        lock_path = resolved_output / OUTPUT_LOCK_NAME
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as error:
            raise DiagramError(f"cannot open output transaction lock: {lock_path.name}") from error

        locked_by: str | None = None
        try:
            opened = os.fstat(descriptor)
            try:
                linked = lock_path.lstat()
            except OSError as error:
                raise DiagramError(f"cannot verify output transaction lock: {lock_path.name}") from error
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or stat.S_ISLNK(linked.st_mode)
                or (opened.st_dev, opened.st_ino) != (linked.st_dev, linked.st_ino)
            ):
                raise DiagramError("output transaction lock must be a regular, unlinked file in the output directory")
            if os.name == "posix":
                if not hasattr(os, "geteuid") or opened.st_uid != os.geteuid():
                    raise DiagramError("output transaction lock is not owned by the current user")
                if stat.S_IMODE(opened.st_mode) != 0o600:
                    os.fchmod(descriptor, 0o600)

            if opened.st_size not in {0, 1}:
                raise DiagramError("output transaction lock has an unexpected size")
            os.lseek(descriptor, 0, os.SEEK_SET)

            try:
                if os.name == "posix":
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                    locked_by = "posix"
                elif os.name == "nt":
                    import msvcrt

                    _acquire_windows_output_lock(descriptor, msvcrt.locking, msvcrt.LK_NBLCK)
                    locked_by = "windows"
                else:
                    raise DiagramError("safe output transaction locking is unsupported on this platform")
            except OSError as error:
                raise DiagramError("cannot acquire output transaction lock") from error

            try:
                current = lock_path.lstat()
            except OSError as error:
                raise DiagramError("output transaction lock changed while waiting") from error
            if stat.S_ISLNK(current.st_mode) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                raise DiagramError("output transaction lock changed while waiting")
            locked_file = os.fstat(descriptor)
            if locked_file.st_size == 0:
                os.lseek(descriptor, 0, os.SEEK_SET)
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            elif locked_file.st_size != 1:
                raise DiagramError("output transaction lock has an unexpected size")
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.read(descriptor, 1) != b"\0":
                raise DiagramError("output transaction lock has unexpected contents")
            yield
        finally:
            try:
                if locked_by == "posix":
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                elif locked_by == "windows":
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            finally:
                os.close(descriptor)


def _acquire_windows_output_lock(
    descriptor: int,
    locking: Callable[[int, int, int], Any],
    lock_mode: int,
    pause: Callable[[float], None] = time.sleep,
) -> None:
    while True:
        try:
            locking(descriptor, lock_mode, 1)
        except OSError as error:
            if error.errno != errno.EACCES:
                raise
            pause(0.05)
        else:
            return


def _assert_windows_output_lock_retry() -> None:
    attempts = 0
    pauses: list[float] = []

    def contend_then_acquire(descriptor: int, mode: int, byte_count: int) -> None:
        nonlocal attempts
        attempts += 1
        if (descriptor, mode, byte_count) != (7, 3, 1):
            raise AssertionError("Windows output locking used the wrong descriptor, mode, or byte range")
        if attempts < 4:
            raise OSError(errno.EACCES, "lock is held")

    _acquire_windows_output_lock(7, contend_then_acquire, 3, pauses.append)
    if attempts != 4 or pauses != [0.05, 0.05, 0.05]:
        raise AssertionError("Windows output locking did not wait through contention and acquire the released lock")

    def fail_closed(descriptor: int, mode: int, byte_count: int) -> None:
        raise OSError(errno.EBADF, "invalid lock descriptor")

    try:
        _acquire_windows_output_lock(7, fail_closed, 3, pauses.append)
    except OSError as error:
        if error.errno != errno.EBADF:
            raise AssertionError("Windows output locking masked a non-contention failure") from error
    else:
        raise AssertionError("Windows output locking retried or ignored a non-contention failure")


def _hold_output_lock_for_self_test(output_dir: str, attempted: Any, acquired: Any, release: Any) -> None:
    attempted.set()
    with _output_transaction_lock(Path(output_dir)):
        acquired.set()
        if not release.wait(10):
            raise RuntimeError("self-test did not release the output lock")


def _assert_cross_process_output_lock(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    context = multiprocessing.get_context("spawn")
    first_attempted, first_acquired, first_release = context.Event(), context.Event(), context.Event()
    second_attempted, second_acquired, second_release = context.Event(), context.Event(), context.Event()
    first = context.Process(
        target=_hold_output_lock_for_self_test,
        args=(str(output_dir), first_attempted, first_acquired, first_release),
    )
    second = context.Process(
        target=_hold_output_lock_for_self_test,
        args=(str(output_dir), second_attempted, second_acquired, second_release),
    )
    processes = (first, second)
    try:
        first.start()
        if not first_attempted.wait(10):
            raise AssertionError("first process did not attempt the output transaction lock")
        if not first_acquired.wait(10):
            raise AssertionError("first process did not acquire the output transaction lock")
        second.start()
        if not second_attempted.wait(10):
            raise AssertionError("second process did not attempt the output transaction lock")
        if second_acquired.wait(1.0):
            raise AssertionError("two processes entered one output transaction at the same time")
        first_release.set()
        if not second_acquired.wait(10):
            raise AssertionError("second process did not acquire the released output transaction lock")
        second_release.set()
        for process in processes:
            process.join(10)
            if process.is_alive() or process.exitcode != 0:
                raise AssertionError("output transaction lock process did not exit cleanly")
    finally:
        first_release.set()
        second_release.set()
        for process in processes:
            if process.pid is not None:
                process.join(1)
                if process.is_alive():
                    process.terminate()
                    process.join(2)


def _assert_same_output_serialization(output_dir: Path) -> None:
    global _write_transaction
    race_dir = output_dir / "same-output-race"
    race_dir.mkdir()
    files = {
        "race.diagram.json": b"same spec\n",
        "race.svg": b"same svg\n",
        "race.html": b"same html\n",
        "race.receipt.json": b"same receipt\n",
    }
    original_write = _write_transaction
    first_staged = threading.Event()
    release_first = threading.Event()
    second_attempted = threading.Event()
    arrivals = 0
    arrivals_lock = threading.Lock()
    outcomes: dict[str, tuple[str, str]] = {}

    def gated_write(path: Path, transaction: dict[str, Any]) -> None:
        nonlocal arrivals
        original_write(path, transaction)
        if transaction.get("slug") != "race" or transaction.get("phase") != "staging":
            return
        with arrivals_lock:
            arrivals += 1
            arrival = arrivals
        if arrival == 1:
            first_staged.set()
            if not release_first.wait(10):
                raise AssertionError("self-test did not release the first output transaction")

    def write(label: str) -> None:
        if label == "second":
            second_attempted.set()
        try:
            _atomic_set(race_dir, files, False, "diagram", "race")
        except DiagramError as error:
            outcomes[label] = ("error", str(error))
        except Exception as error:
            outcomes[label] = ("exception", repr(error))
        else:
            outcomes[label] = ("passed", "")

    _write_transaction = gated_write
    first = threading.Thread(target=write, args=("first",), daemon=True)
    second = threading.Thread(target=write, args=("second",), daemon=True)
    try:
        first.start()
        if not first_staged.wait(10):
            raise AssertionError("first same-output transaction did not reach its staging journal")
        second.start()
        if not second_attempted.wait(10):
            raise AssertionError("second same-output transaction did not start")
        time.sleep(0.2)
        with arrivals_lock:
            simultaneous_stages = arrivals
        if simultaneous_stages != 1:
            raise AssertionError("same-output calls staged concurrently before either output existed")
        release_first.set()
        first.join(10)
        second.join(10)
        if first.is_alive() or second.is_alive():
            raise AssertionError("same-output transaction workers did not finish")
    finally:
        release_first.set()
        for thread in (first, second):
            if thread.ident is not None:
                thread.join(2)
        _write_transaction = original_write

    if outcomes.get("first", (None, None))[0] != "passed":
        raise AssertionError(f"first same-output transaction did not complete: {outcomes}")
    if outcomes.get("second", (None, None))[0] != "error" or "output already exists" not in outcomes["second"][1]:
        raise AssertionError(f"second same-output transaction did not fail without replacement: {outcomes}")
    if set(files) != {path.name for path in race_dir.iterdir() if path.name != OUTPUT_LOCK_NAME}:
        raise AssertionError("concurrent same-output calls left an incomplete artifact set")
    if any((race_dir / name).read_bytes() != content for name, content in files.items()):
        raise AssertionError("concurrent same-output calls removed or changed the successful artifact set")
    if not (race_dir / OUTPUT_LOCK_NAME).is_file():
        raise AssertionError("output transaction coordination file was not retained")


def _atomic_set(output_dir: Path, files: dict[str, bytes], overwrite: bool, kind: str, slug: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_output = output_dir.resolve()
    with _output_transaction_lock(resolved_output):
        _atomic_set_locked(resolved_output, files, overwrite, kind, slug)


def _atomic_set_locked(output_dir: Path, files: dict[str, bytes], overwrite: bool, kind: str, slug: str) -> None:
    expected = _transaction_names(kind, slug)
    if not files or (set(files) - expected) or (kind != "browser" and set(files) != expected):
        raise DiagramError("output set does not match its declared transaction kind and slug")
    _recover_output_sets(output_dir)
    for name in files:
        if not name or Path(name).name != name or name in {".", ".."}:
            raise DiagramError("output names must be plain filenames")
    targets = {name: output_dir / name for name in files}
    existing = {}
    for name, target in targets.items():
        if target.is_symlink():
            raise DiagramError(f"refusing to replace symlink output: {target.name}")
        if target.exists() and not overwrite:
            raise DiagramError(f"output already exists: {target.name}; choose a new name or request overwrite")
        if target.exists() and not target.is_file():
            raise DiagramError(f"output target is not a regular file: {target.name}")
        existing[name] = _file_sha256(target) if target.exists() else None
    staging = Path(tempfile.mkdtemp(prefix=".patpat-diagram-tx-", dir=output_dir))
    entries = [
        {
            "name": name,
            "staged": f"new-{index}",
            "backup": f"old-{index}",
            "had_existing": existing[name] is not None,
            "old_sha256": existing[name],
            "new_sha256": hashlib.sha256(data).hexdigest(),
        }
        for index, (name, data) in enumerate(files.items())
    ]
    transaction = {"tool": "patpat-repository-diagram", "schema_version": 1, "owner_pid": os.getpid(), "phase": "staging", "kind": kind, "slug": slug, "entries": entries}
    journal = staging / "transaction.json"
    _write_transaction(journal, transaction)
    try:
        for entry in entries:
            name = entry["name"]
            staged = staging / entry["staged"]
            with staged.open("wb") as output:
                output.write(files[name])
                output.flush()
                os.fsync(output.fileno())
        for entry in entries:
            if entry["had_existing"]:
                shutil.copyfile(targets[entry["name"]], staging / entry["backup"])
                if _file_sha256(staging / entry["backup"]) != entry["old_sha256"]:
                    raise DiagramError(f"output changed while a replacement was staged: {entry['name']}")
        transaction["phase"] = "prepared"
        _write_transaction(journal, transaction)
        for entry in entries:
            name = entry["name"]
            target = targets[name]
            if entry["had_existing"]:
                os.replace(target, staging / entry["backup"])
            elif target.exists():
                raise DiagramError(f"output appeared during the transaction: {name}")
            os.replace(staging / entry["staged"], target)
        transaction["phase"] = "committed"
        _write_transaction(journal, transaction)
        shutil.rmtree(staging)
    except Exception as error:
        if staging.exists():
            _recover_transaction(staging, output_dir, transaction, trusted_current=True)
        if isinstance(error, DiagramError):
            raise
        raise DiagramError(f"could not finish output set: {error}") from error


def _render(
    spec_path: Path,
    repo_root: Path | None,
    output_dir: Path,
    name: str,
    overwrite: bool,
    public_source_links: bool = False,
) -> dict[str, Any]:
    if not SLUG_PATTERN.fullmatch(name):
        raise DiagramError("name must be a lowercase hyphenated slug")
    raw, source_spec_bytes = load_json(spec_path)
    repo_before = git_context(repo_root)
    spec = validate_spec(raw, repo_root, require_repository_sources=True)
    layout = _make_layout(spec)
    readability = _projected_readability(layout)
    if readability["minimum_projected_node_text_px"] < MIN_PROJECTED_NODE_TEXT_PX:
        raise DiagramError(
            "diagram node text projects below the desktop readability floor "
            f"({readability['minimum_projected_node_text_px']:.1f}px < {MIN_PROJECTED_NODE_TEXT_PX:.1f}px); "
            "reduce canvas width or split the story into a narrower diagram"
        )
    svg_bytes = _svg_document(spec, repo_before, layout)
    link_verification = _verify_public_github_source(repo_before, list(spec["snapshots"].values())) if public_source_links else {"status": "not-requested"}
    source_links = _github_source_permalinks(repo_before, list(spec["snapshots"].values()), link_verification)
    html_bytes = _html_document(spec, repo_before, svg_bytes, source_links)
    _valid_html_and_svg(html_bytes, svg_bytes, source_links)
    if _has_blocking_geometry_warnings(layout["warnings"]):
        raise DiagramError("layout has blocking geometry warnings: " + "; ".join(layout["warnings"]))
    repo_after = git_context(repo_root)
    if repo_before != repo_after:
        raise DiagramError("repository provenance changed while the diagram was rendered")
    fresh_spec = validate_spec(raw, repo_root)
    if spec["snapshots"] != fresh_spec["snapshots"]:
        raise DiagramError("source files changed while the diagram was rendered")
    stem = name
    output_names = {
        "source": f"{stem}.diagram.json",
        "html": f"{stem}.html",
        "svg": f"{stem}.svg",
        "receipt": f"{stem}.receipt.json",
    }
    resolved_output = output_dir.resolve()
    protected = {spec_path.resolve()}
    if repo_root is not None:
        protected.update(
            (repo_root.resolve() / Path(*PurePosixPath(item["path"]).parts)).resolve()
            for item in spec["evidence"]
            if item.get("origin", "repository") == "repository"
        )
    if any((resolved_output / filename).resolve(strict=False) in protected for filename in output_names.values()):
        raise DiagramError("output would overwrite the diagram source or a cited repository file")
    files = {
        output_names["source"]: source_spec_bytes,
        output_names["html"]: html_bytes,
        output_names["svg"]: svg_bytes,
    }
    receipt = {
        "schema_version": 2,
        "tool": "patpat-repository-diagram",
        "tool_version": TOOL_VERSION,
        "repository": repo_before,
        "diagram_schema_version": spec["schema_version"],
        "profile": spec["profile"],
        "source": {"name": output_names["source"], "sha256": hashlib.sha256(source_spec_bytes).hexdigest()},
        "evidence": [spec["snapshots"][key] for key in sorted(spec["snapshots"])],
        "source_links": {
            "requested": public_source_links,
            "verification": link_verification,
            "links": source_links,
        },
        "layout": {
            "diagram_type": spec["type"],
            "width": layout["width"],
            "height": layout["height"],
            "entities": len(spec["entities"]),
            "relationships": len(spec["edges"]),
            "warnings": layout["warnings"],
            "readability": readability,
        },
        "outputs": {
            output_names["html"]: hashlib.sha256(html_bytes).hexdigest(),
            output_names["svg"]: hashlib.sha256(svg_bytes).hexdigest(),
        },
    }
    files[output_names["receipt"]] = (json.dumps(receipt, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    _atomic_set(resolved_output, files, overwrite, "diagram", name)
    return {"output_dir": str(resolved_output), "files": output_names, "receipt": receipt, "warnings": layout["warnings"]}


def _collect_browser_artifacts(staged_browser: Path, name: str, profile: str) -> dict[str, bytes]:
    if profile not in {"standard", "showcase"}:
        raise DiagramError("browser quality profile must be standard or showcase")
    expected = _transaction_names("browser-showcase" if profile == "showcase" else "browser", name)
    entries = list(staged_browser.iterdir())
    lock_path = staged_browser / OUTPUT_LOCK_NAME
    if (
        lock_path.is_symlink()
        or not lock_path.is_file()
        or lock_path.stat().st_nlink != 1
        or lock_path.read_bytes() != b"\0"
    ):
        raise DiagramError("browser staging directory has no valid output coordination file")
    actual = {path.name for path in entries if path.name != OUTPUT_LOCK_NAME}
    if actual != expected:
        raise DiagramError("browser staging directory does not match its declared artifact set")
    result: dict[str, bytes] = {}
    for filename in sorted(expected):
        path = staged_browser / filename
        if path.is_symlink() or not path.is_file():
            raise DiagramError(f"browser staging artifact is not a regular file: {filename}")
        result[filename] = path.read_bytes()
    return result


def _assert_browser_artifact_collection(output_dir: Path) -> None:
    for profile in ("standard", "showcase"):
        staging = output_dir / profile
        staging.mkdir(parents=True, exist_ok=True)
        expected = _transaction_names("browser-showcase" if profile == "showcase" else "browser", "collection")
        for filename in expected:
            (staging / filename).write_bytes(filename.encode("utf-8"))
        (staging / OUTPUT_LOCK_NAME).write_bytes(b"\0")
        collected = _collect_browser_artifacts(staging, "collection", profile)
        if set(collected) != expected or OUTPUT_LOCK_NAME in collected:
            raise AssertionError(f"{profile} browser collection included transaction metadata or omitted artifacts")
        if any(collected[name] != name.encode("utf-8") for name in expected):
            raise AssertionError(f"{profile} browser collection changed artifact bytes")
        unexpected = staging / "unexpected.bin"
        unexpected.write_bytes(b"not part of the declared browser output")
        try:
            _collect_browser_artifacts(staging, "collection", profile)
        except DiagramError:
            pass
        else:
            raise AssertionError(f"{profile} browser collection accepted an undeclared artifact")


def _finalize(
    spec_path: Path,
    repo_root: Path | None,
    output_dir: Path,
    name: str,
    overwrite: bool,
    browser: str | None,
    browser_profile: str,
    browser_gate: bool = True,
    public_source_links: bool = False,
) -> dict[str, Any]:
    """Gate a complete artifact set before replacing any last-good output."""
    if not SLUG_PATTERN.fullmatch(name):
        raise DiagramError("name must be a lowercase hyphenated slug")
    if browser_profile not in {"standard", "showcase"}:
        raise DiagramError("browser quality profile must be standard or showcase")
    if not browser_gate and (browser is not None or browser_profile != "standard"):
        raise DiagramError("--browser and --browser-profile require the browser gate")

    spec_path = spec_path.resolve(strict=True)
    source_raw, source_bytes = load_json(spec_path)
    validated_spec = validate_spec(source_raw, repo_root, require_repository_sources=True)
    output_names = {
        "source": f"{name}.diagram.json",
        "html": f"{name}.html",
        "svg": f"{name}.svg",
        "receipt": f"{name}.receipt.json",
    }

    with tempfile.TemporaryDirectory(prefix="patpat-diagram-finalize-") as temporary_name:
        temporary = Path(temporary_name)
        staged_artifacts = temporary / "artifacts"
        try:
            rendered = _render(spec_path, repo_root, staged_artifacts, name, False, public_source_links)
        except (DiagramError, OSError) as error:
            raise _FinalizeGateError(str(error), "render", {"render": "failed", "check": "not-run", "browser-check": "not-run"}) from error
        html_path = staged_artifacts / output_names["html"]
        try:
            checked = _check(html_path, repo_root)
        except (DiagramError, OSError) as error:
            raise _FinalizeGateError(str(error), "check", {"render": "passed", "check": "failed", "browser-check": "not-run"}) from error

        browser_result = None
        staged_browser = None
        if browser_gate:
            staged_browser = temporary / "browser"
            screenshot = staged_browser / f"{name}.browser.png"
            browser_receipt = staged_browser / f"{name}.browser.receipt.json"
            try:
                browser_result = _browser_check(
                    html_path, repo_root, screenshot, browser, browser_receipt, browser_profile
                )
            except (DiagramError, OSError) as error:
                raise _FinalizeGateError(str(error), "browser-check", {"render": "passed", "check": "passed", "browser-check": "failed"}) from error
            try:
                checked = _check(html_path, repo_root)
            except (DiagramError, OSError) as error:
                raise _FinalizeGateError(str(error), "check", {"render": "passed", "check": "failed-after-browser", "browser-check": "passed"}) from error

        _, receipt, raw, packaged_files = _verified_packaged_artifact(html_path)
        if source_bytes != packaged_files["source"]:
            raise DiagramError("diagram source JSON changed during finalization")
        _verify_artifact_repository_evidence(raw, receipt, packaged_files, repo_root)
        current_raw, current_source_bytes = load_json(spec_path)
        current_spec = validate_spec(current_raw, repo_root, require_repository_sources=True)
        if current_source_bytes != source_bytes or current_spec["snapshots"] != validated_spec["snapshots"]:
            raise DiagramError("diagram source or cited repository evidence changed during finalization")

        files: dict[str, bytes] = {
            output_names[kind]: (staged_artifacts / output_names[kind]).read_bytes()
            for kind in ("source", "html", "svg", "receipt")
        }
        transaction_kind = "diagram"
        if browser_gate:
            if staged_browser is None:
                raise DiagramError("browser gate did not produce a staging directory")
            browser_files = _collect_browser_artifacts(staged_browser, name, browser_profile)
            if f"{name}.browser.receipt.json" not in browser_files:
                raise DiagramError("browser gate did not produce its quality receipt")
            browser_record = json.loads(browser_files[f"{name}.browser.receipt.json"])
            if browser_record.get("html_sha256") != hashlib.sha256(files[output_names["html"]]).hexdigest():
                raise DiagramError("browser receipt is not bound to the finalized HTML")
            files.update(browser_files)
            transaction_kind = "finalize-showcase" if browser_profile == "showcase" else "finalize"

        final_directory = output_dir.resolve()
        protected_paths = {spec_path}
        if repo_root is not None:
            root = repo_root.resolve(strict=True)
            protected_paths.update(
                (root / Path(*PurePosixPath(item["path"]).parts)).resolve()
                for item in validated_spec["evidence"]
                if item.get("origin", "repository") == "repository"
            )
        if any((final_directory / filename).resolve(strict=False) in protected_paths for filename in files):
            raise DiagramError("output would overwrite the diagram source or a cited repository file")

        _atomic_set(final_directory, files, overwrite, transaction_kind, name)
        return {
            "output_dir": str(final_directory),
            "files": sorted(files),
            "strict_check": checked,
            "browser": browser_result,
            "warnings": rendered["warnings"],
            "published": True,
        }


def _check(html_path: Path, repo_root: Path | None = None) -> dict[str, Any]:
    if Path(html_path).suffix.lower() != ".html":
        raise DiagramError("check expects an .html output path")
    html_path = Path(html_path).resolve(strict=True)
    spec, receipt, raw, files = _verified_packaged_artifact(html_path)
    _verify_artifact_repository_evidence(raw, receipt, files, repo_root)
    return {
        "status": "passed",
        "html": html_path.name,
        "svg": Path(html_path).with_suffix(".svg").name,
        "receipt": Path(html_path).with_suffix(".receipt.json").name,
        "diagram_type": receipt.get("layout", {}).get("diagram_type"),
    }


def _verify_artifact_repository_evidence(
    raw: dict[str, Any],
    receipt: dict[str, Any],
    files: dict[str, bytes],
    repo_root: Path | None,
) -> None:
    repository_evidence = [
        item for item in raw.get("evidence", [])
        if isinstance(item, dict) and item.get("origin", "repository") == "repository"
    ]
    if repository_evidence and repo_root is None:
        raise DiagramError("repository-backed artifact checking requires --repo-root")
    receipt_repository = receipt.get("repository", {})
    if repo_root is not None:
        current_repo = git_context(repo_root)
        if receipt_repository.get("revision") is not None and receipt_repository.get("revision") != current_repo["revision"]:
            raise DiagramError("artifact receipt refers to a different Git revision")
        if repository_evidence and receipt_repository.get("revision") != current_repo["revision"]:
            raise DiagramError("artifact receipt refers to a different Git revision")
    elif repository_evidence and receipt_repository.get("revision") is not None:
        raise DiagramError("artifact was rendered with repository provenance; check it with --repo-root")
    current_spec = validate_spec(raw, repo_root, require_repository_sources=True)
    expected_evidence = receipt.get("evidence", [])
    actual_evidence = [current_spec["snapshots"][key] for key in sorted(current_spec["snapshots"])]
    if expected_evidence != actual_evidence:
        raise DiagramError("repository evidence changed after rendering")
    if hashlib.sha256(files["source"]).hexdigest() != receipt.get("source", {}).get("sha256"):
        raise DiagramError("diagram JSON digest does not match the receipt")


def _verified_packaged_artifact(html_path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, bytes]]:
    if Path(html_path).suffix.lower() != ".html":
        raise DiagramError("artifact source must be an .html diagram output")
    html_path = html_path.resolve(strict=True)
    directory, stem = html_path.parent, html_path.stem
    source_path, svg_path, receipt_path = (
        directory / f"{stem}.diagram.json",
        directory / f"{stem}.svg",
        directory / f"{stem}.receipt.json",
    )
    paths = {"html": html_path, "source": source_path, "svg": svg_path, "receipt": receipt_path}
    for path in paths.values():
        if path.is_symlink() or not path.is_file():
            raise DiagramError(f"diagram artifact set is incomplete or unsafe: {path.name}")
    artifact_bytes = {kind: path.read_bytes() for kind, path in paths.items()}
    raw = parse_json(artifact_bytes["source"])
    source_bytes = artifact_bytes["source"]
    if len(source_bytes) > 1_000_000:
        raise DiagramError("diagram source JSON exceeds the 1 MB limit")
    receipt = parse_json(artifact_bytes["receipt"])
    spec = validate_spec(raw, None)
    if receipt.get("tool") != "patpat-repository-diagram" or receipt.get("schema_version") not in {1, 2}:
        raise DiagramError("diagram receipt uses an unsupported contract")
    if receipt.get("diagram_schema_version", spec["schema_version"]) != spec["schema_version"]:
        raise DiagramError("diagram receipt and source schema versions differ")
    if receipt.get("source", {}).get("sha256") != hashlib.sha256(source_bytes).hexdigest():
        raise DiagramError("diagram source digest does not match its receipt")
    expected_outputs = receipt.get("outputs", {})
    for kind in ("html", "svg"):
        if expected_outputs.get(paths[kind].name) != hashlib.sha256(artifact_bytes[kind]).hexdigest():
            raise DiagramError(f"{kind.upper()} digest does not match its receipt")
    repository = receipt.get("repository")
    if not isinstance(repository, dict):
        raise DiagramError("diagram receipt has no valid provenance record")
    repository_evidence = any(item.get("origin", "repository") == "repository" for item in spec["evidence"])
    revision = repository.get("revision")
    if repository_evidence and not re.fullmatch(r"[0-9a-f]{40,64}", str(revision or "")):
        raise DiagramError("repository-backed evidence has no valid Git revision")
    if revision is not None and not re.fullmatch(r"[0-9a-f]{40,64}", str(revision)):
        raise DiagramError("diagram receipt has an invalid Git revision")
    origin = repository.get("origin")
    if origin is not None and (not isinstance(origin, str) or any(char in origin for char in "@?#\\") or "://" in origin):
        raise DiagramError("diagram receipt origin is not sanitized")
    snapshots = receipt.get("evidence")
    if not isinstance(snapshots, list) or len(snapshots) != len(spec["evidence"]):
        raise DiagramError("diagram receipt evidence does not match its source model")
    expected_by_id = {item["id"]: item for item in spec["evidence"]}
    snapshot_ids = [snapshot.get("id") for snapshot in snapshots if isinstance(snapshot, dict)]
    if len(snapshot_ids) != len(snapshots) or set(snapshot_ids) != set(expected_by_id) or len(set(snapshot_ids)) != len(snapshot_ids):
        raise DiagramError("diagram receipt evidence IDs do not match its source model")
    for snapshot in snapshots:
        if not isinstance(snapshot, dict) or snapshot.get("id") not in expected_by_id:
            raise DiagramError("diagram receipt has an unknown evidence entry")
        expected = expected_by_id[snapshot["id"]]
        origin = expected.get("origin", "repository")
        identity_keys = ("origin", "claim") if origin == "brief" else ("path", "start_line", "end_line", "claim")
        if "origin" in expected and origin == "repository":
            identity_keys = ("origin",) + identity_keys
        if any(snapshot.get(key) != expected[key] for key in identity_keys if key in expected):
            raise DiagramError(f"diagram receipt evidence identity changed: {snapshot['id']}")
        if origin == "brief":
            if snapshot.get("origin") != "brief" or snapshot.get("sha256") != hashlib.sha256(expected["claim"].encode("utf-8")).hexdigest():
                raise DiagramError(f"diagram receipt brief evidence digest is invalid: {snapshot['id']}")
            continue
        for key in ("sha256", "file_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(snapshot.get(key, ""))):
                raise DiagramError(f"diagram receipt has an invalid {key}: {snapshot['id']}")
        if "snapshot" in snapshot and snapshot["snapshot"] not in {"committed", "working-tree"}:
            raise DiagramError(f"diagram receipt has an invalid snapshot type: {snapshot['id']}")
    source_link_record = receipt.get("source_links", {
        "requested": False, "verification": {"status": "not-requested"}, "links": {},
    })
    if not isinstance(source_link_record, dict) or set(source_link_record) != {"requested", "verification", "links"}:
        raise DiagramError("diagram receipt has an invalid source-link record")
    requested = source_link_record.get("requested")
    verification = source_link_record.get("verification")
    source_links = source_link_record.get("links")
    if not isinstance(requested, bool) or not isinstance(verification, dict) or not isinstance(source_links, dict):
        raise DiagramError("diagram receipt has an invalid source-link record")
    verification_status = verification.get("status")
    if not requested:
        if verification_status != "not-requested" or source_links:
            raise DiagramError("diagram receipt includes unrequested source links")
    elif verification_status == "verified":
        identity = _github_source_identity(repository)
        if (
            identity is None
            or verification.get("provider") != "api.github.com"
            or verification.get("credential_free") is not True
            or verification.get("revision") != identity[2]
            or not isinstance(verification.get("repository"), str)
            or verification.get("repository").casefold() != f"{identity[0]}/{identity[1]}".casefold()
            or not isinstance(verification.get("checked_at"), str)
        ):
            raise DiagramError("diagram receipt has invalid anonymous GitHub verification")
    elif verification_status == "unavailable":
        if verification.get("reason") not in {
            "unsupported-origin", "no-committed-evidence", "repository-not-public",
            "commit-not-public", "anonymous-verification-failed",
        } or not isinstance(verification.get("checked_at"), str):
            raise DiagramError("diagram receipt has invalid unavailable source-link verification")
    else:
        raise DiagramError("diagram receipt has an unsupported source-link verification status")
    expected_links = _github_source_permalinks(repository, snapshots, verification)
    if source_links != expected_links:
        raise DiagramError("diagram source links do not match the verified committed evidence")
    _valid_html_and_svg(artifact_bytes["html"], artifact_bytes["svg"], expected_links)
    return spec, receipt, raw, artifact_bytes


def _comparison_svg(spec: dict[str, Any], repository: dict[str, Any], snapshot: str) -> str:
    root = ET.fromstring(_svg_document(spec, repository, _make_layout(spec)))
    root.set("data-snapshot", snapshot)
    definitions = root.find(_tag("defs"))
    if definitions is not None:
        for child in list(definitions):
            if child.tag == _tag("style"):
                definitions.remove(child)
    identifiers = {
        element.attrib["id"]: f"{snapshot}-{element.attrib['id']}"
        for element in root.iter()
        if "id" in element.attrib
    }
    for element in root.iter():
        for key, value in list(element.attrib.items()):
            if key == "id":
                element.set(key, identifiers[value])
            elif key == "aria-labelledby":
                element.set(key, " ".join(identifiers.get(item, item) for item in value.split()))
            else:
                element.set(key, re.sub(r"url\(#([^)]+)\)", lambda match: f"url(#{identifiers.get(match.group(1), match.group(1))})", value))
    return ET.tostring(root, encoding="unicode")


def _delta_html(
    delta: dict[str, Any],
    base_spec: dict[str, Any],
    head_spec: dict[str, Any],
    language: str,
    base_repository: dict[str, Any] | None = None,
    head_repository: dict[str, Any] | None = None,
) -> bytes:
    if language == "th":
        labels = {"title": "เปรียบเทียบสถาปัตยกรรม", "before": "ก่อน", "changes": "การเปลี่ยนแปลง", "after": "หลัง", "category": "ชนิด", "element": "องค์ประกอบ", "details": "รายละเอียด", "limits": "ขอบเขตการเปรียบเทียบ", "snapshot_hint": "เลื่อนแนวนอนเพื่อดูภาพแผนภาพเต็มความกว้าง"}
    else:
        labels = {"title": "Architecture comparison", "before": "Before", "changes": "Changes", "after": "After", "category": "Change", "element": "Element", "details": "Authored differences", "limits": "Comparison limits", "snapshot_hint": "Scroll horizontally to inspect the full-width diagram snapshot."}
    rows = []
    for item in delta["changes"]:
        before = item.get("before", "—")
        after = item.get("after", "—")
        if item["category"] == "moved":
            if "before_layer" in item:
                before = f"layer {item['before_layer']}, position {item['before_position']}"
                after = f"layer {item['after_layer']}, position {item['after_position']}"
            if "before_geometry" in item:
                before = f"{before}; x={item['before_geometry']['x']:g}, y={item['before_geometry']['y']:g}" if "before_layer" in item else item["before_geometry"]
                after = f"{after}; x={item['after_geometry']['x']:g}, y={item['after_geometry']['y']:g}" if "after_layer" in item else item["after_geometry"]
        rows.append(
            "<tr>"
            f"<td>{html.escape(item['category'])}</td><td><code>{html.escape(item['kind'])} / {html.escape(item['id'])}</code></td>"
            f"<td><code>{html.escape(json.dumps(before, ensure_ascii=False, sort_keys=True))}</code></td>"
            f"<td><code>{html.escape(json.dumps(after, ensure_ascii=False, sort_keys=True))}</code></td></tr>"
        )
    counts = " · ".join(f"{html.escape(name)} {count}" for name, count in delta["counts"].items())
    limits = "".join(f"<li>{html.escape(item)}</li>" for item in delta["limits"])
    def snapshot_items(spec: dict[str, Any]) -> str:
        positions = {
            identifier: (layer_index, position_index)
            for layer_index, layer in enumerate(spec["layout"]["layers"] or [])
            for position_index, identifier in enumerate(layer)
        }
        component_rows = []
        for item in spec["entities"]:
            location = ""
            if item["id"] in positions:
                layer, position = positions[item["id"]]
                location = f" / layer {layer}, position {position}"
            component_rows.append(
                f"<li><code>{html.escape(item['id'])}</code> · {html.escape(item['label'])} "
                f"<small>{html.escape(item['kind'])} / {html.escape(item['certainty'])}{html.escape(location)}</small></li>"
            )
        components = "".join(component_rows)
        relationships = "".join(
            f"<li><code>{html.escape(item['id'])}</code> · {html.escape(item['source'])} → {html.escape(item['target'])} · {html.escape(item['label'])}</li>"
            for item in spec["edges"]
        )
        return (
            f"<details><summary>{len(spec['entities'])} components</summary><ul>{components}</ul></details>"
            f"<details><summary>{len(spec['edges'])} relationships</summary><ul>{relationships}</ul></details>"
        )

    if base_repository is None:
        base_repository = {"name": "repository", "revision": delta["base"]["revision"], "dirty": False}
    if head_repository is None:
        head_repository = {"name": "repository", "revision": delta["head"]["revision"], "dirty": False}
    before_svg = _comparison_svg(base_spec, base_repository, "before")
    after_svg = _comparison_svg(head_spec, head_repository, "after")
    combined_css = DELTA_CSS + "\n" + SVG_CSS
    css_hash = base64.b64encode(hashlib.sha256(combined_css.encode("utf-8")).digest()).decode("ascii")
    table_class = "delta-table-wrap"
    page = f"""<!doctype html><html lang="{language}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src &#x27;none&#x27;; base-uri &#x27;none&#x27;; form-action &#x27;none&#x27;; style-src &#x27;sha256-{css_hash}&#x27;"><title>{html.escape(labels['title'])}</title><style>{combined_css}</style></head><body><main><header><h1>{html.escape(labels['title'])}</h1><p class="summary">{html.escape(delta['base']['title'])} · {html.escape(delta['base']['revision'] or '')} → {html.escape(delta['head']['title'])} · {html.escape(delta['head']['revision'] or '')}</p><p>{counts or 'No authored changes'}</p></header><div class="snapshots"><section class="panel"><h2>{html.escape(labels['before'])}</h2><p>{html.escape(delta['base']['title'])}</p><code>{html.escape(delta['base']['revision'] or '')}</code><p class="snapshot-hint">{html.escape(labels['snapshot_hint'])}</p><div class="snapshot-figure" role="region" aria-label="{html.escape(labels['before'])} diagram" tabindex="0">{before_svg}</div>{snapshot_items(base_spec)}</section><section class="panel"><h2>{html.escape(labels['after'])}</h2><p>{html.escape(delta['head']['title'])}</p><code>{html.escape(delta['head']['revision'] or '')}</code><p class="snapshot-hint">{html.escape(labels['snapshot_hint'])}</p><div class="snapshot-figure" role="region" aria-label="{html.escape(labels['after'])} diagram" tabindex="0">{after_svg}</div>{snapshot_items(head_spec)}</section><section class="panel changes-panel"><h2>{html.escape(labels['changes'])}</h2><div class="{table_class}"><table><thead><tr><th>{html.escape(labels['category'])}</th><th>{html.escape(labels['element'])}</th><th>Before</th><th>After</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section></div><section class="panel"><h2>{html.escape(labels['limits'])}</h2><ul>{limits}</ul></section></main></body></html>"""
    return page.encode("utf-8")


def _compare(base_html: Path, head_html: Path, repo_root: Path, output_dir: Path, name: str, overwrite: bool) -> dict[str, Any]:
    if not SLUG_PATTERN.fullmatch(name):
        raise DiagramError("name must be a lowercase hyphenated slug")
    base, base_receipt, _base_raw, base_files = _verified_packaged_artifact(base_html)
    head, head_receipt, head_raw, head_files = _verified_packaged_artifact(head_html)
    _verify_artifact_repository_evidence(head_raw, head_receipt, head_files, repo_root)
    delta = compare_architecture(base, head, base_receipt, head_receipt)
    html_bytes = _delta_html(delta, base, head, head["language"], base_receipt["repository"], head_receipt["repository"])
    _valid_static_page(html_bytes, DELTA_CSS + "\n" + SVG_CSS)
    output_names = {
        "delta": f"{name}.delta.json",
        "html": f"{name}.delta.html",
        "receipt": f"{name}.delta.receipt.json",
    }
    targets = {output_dir.resolve() / value for value in output_names.values()}
    protected = {Path(base_html).resolve(), Path(head_html).resolve()}
    for source_path in (Path(base_html).with_suffix(".diagram.json"), Path(head_html).with_suffix(".diagram.json"), Path(base_html).with_suffix(".receipt.json"), Path(head_html).with_suffix(".receipt.json")):
        protected.add(source_path.resolve())
    if targets & protected:
        raise DiagramError("comparison output would overwrite one of its input artifacts")
    delta_bytes = (json.dumps(delta, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    receipt = {
        "schema_version": 1,
        "tool": "patpat-repository-diagram",
        "kind": "architecture-delta",
        "base": {"html_sha256": hashlib.sha256(base_files["html"]).hexdigest(), "receipt_sha256": hashlib.sha256(base_files["receipt"]).hexdigest()},
        "head": {"html_sha256": hashlib.sha256(head_files["html"]).hexdigest(), "receipt_sha256": hashlib.sha256(head_files["receipt"]).hexdigest()},
        "outputs": {
            output_names["delta"]: hashlib.sha256(delta_bytes).hexdigest(),
            output_names["html"]: hashlib.sha256(html_bytes).hexdigest(),
        },
    }
    files = {
        output_names["delta"]: delta_bytes,
        output_names["html"]: html_bytes,
        output_names["receipt"]: (json.dumps(receipt, indent=2) + "\n").encode("utf-8"),
    }
    _atomic_set(output_dir.resolve(), files, overwrite, "delta", name)
    return {"status": "passed", "output_dir": str(output_dir.resolve()), "files": output_names, "counts": delta["counts"], "receipt": receipt}


def _preview_fingerprint(source_path: Path, repo_root: Path | None) -> tuple[str, str | None]:
    context = git_context(repo_root)
    try:
        raw, source_bytes = load_json(source_path)
        spec = validate_spec(raw, repo_root, require_repository_sources=True)
        material = {
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "repository": context,
            "evidence": spec["snapshots"],
        }
        error = None
    except (DiagramError, OSError) as failure:
        source_bytes = source_path.read_bytes() if source_path.is_file() else b"<missing>"
        material = {
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "repository": context,
            "invalid": str(failure),
        }
        error = str(failure)
    payload = json.dumps(material, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), error


def _preview_route(request_target: str, host: str, expected_host: str, name: str) -> tuple[int, str | None]:
    if host.lower() != expected_host.lower():
        return 403, None
    try:
        parsed = urllib.parse.urlsplit(request_target)
    except ValueError:
        return 400, None
    if parsed.scheme or parsed.netloc or parsed.path not in {"/status", f"/{name}.html"}:
        return 404, None
    return 200, parsed.path


def _preview(source_path: Path, repo_root: Path | None, name: str) -> int:
    if not SLUG_PATTERN.fullmatch(name):
        raise DiagramError("name must be a lowercase hyphenated slug")
    source_path = source_path.resolve(strict=False)
    if repo_root is not None:
        repo_root = repo_root.resolve(strict=True)
    state_lock = threading.RLock()
    state: dict[str, Any] = {
        "status": "invalid",
        "generation": "",
        "message": "No validated diagram has been built yet.",
        "files": {},
        "host": "",
    }

    class PreviewHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def do_GET(self) -> None:
            with state_lock:
                status = state["status"]
                generation = state["generation"]
                files = state["files"]
                expected_host = state["host"]
            response, path = _preview_route(self.path, self.headers.get("Host", ""), expected_host, name)
            if response != 200:
                self.send_error(response)
                return
            if path == "/status":
                body = (json.dumps({"status": status, "generation": generation}, separators=(",", ":")) + "\n").encode("utf-8")
                content_type = "application/json; charset=utf-8"
                response = 200
            else:
                filename = path[1:]
                body = files.get(filename)
                content_type = "text/html; charset=utf-8"
                response = 200 if body is not None else 503 if status != "ready" else 404
                if body is None:
                    body = b"Preview has no validated artifact yet. Check the terminal for the diagnostic.\n" if response == 503 else b"Not found\n"
                    content_type = "text/plain; charset=utf-8"
            self.send_response(response)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            self.send_error(405)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler)
    server.daemon_threads = True
    server.timeout = 0.25
    if server.server_address[0] != "127.0.0.1":
        server.server_close()
        raise DiagramError("preview server did not bind to loopback")
    with state_lock:
        state["host"] = f"127.0.0.1:{server.server_address[1]}"
    serve_thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True)
    serve_thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/{name}.html?patpat-preview=1"
    print(f"Preview: {url}", flush=True)
    print("Preview is loopback-only. Press Ctrl-C to stop and remove its temporary files.", flush=True)
    last_fingerprint = None
    last_error = None
    counter = 0
    try:
        while True:
            fingerprint, fingerprint_error = _preview_fingerprint(source_path, repo_root)
            if fingerprint != last_fingerprint:
                last_fingerprint = fingerprint
                counter += 1
                try:
                    if fingerprint_error:
                        raise DiagramError(fingerprint_error)
                    build_root = Path(tempfile.mkdtemp(prefix=f"build-{counter}-"))
                    try:
                        _render(source_path.resolve(strict=True), repo_root, build_root, name, False)
                        _check(build_root / f"{name}.html", repo_root)
                        candidate = {
                            f"{name}.html": (build_root / f"{name}.html").read_bytes()
                        }
                    finally:
                        shutil.rmtree(build_root, ignore_errors=True)
                    current_fingerprint, _current_error = _preview_fingerprint(source_path, repo_root)
                    if current_fingerprint != fingerprint:
                        last_fingerprint = None
                        print("Preview discarded a superseded candidate.", file=sys.stderr, flush=True)
                        continue
                    with state_lock:
                        state.update({"status": "ready", "generation": fingerprint, "message": "validated", "files": candidate})
                    last_error = None
                    print(f"Preview updated: {fingerprint[:12]}", flush=True)
                except (DiagramError, OSError) as error:
                    with state_lock:
                        state.update({"status": "invalid", "message": str(error)})
                    if str(error) != last_error:
                        print(f"Preview keeps its last good build: {error}", file=sys.stderr, flush=True)
                        last_error = str(error)
            time.sleep(0.5)
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
        server.server_close()
        serve_thread.join(timeout=3)
        print("Preview stopped; temporary artifacts removed.", flush=True)


DIAGRAM_GUIDE = {
    "architecture": {"body": ["components", "relationships"], "optional": ["boundaries"], "focus": "ownership, calls, stores, and evidenced boundaries"},
    "workflow": {"body": ["steps", "transitions"], "optional": ["lanes"], "focus": "ordered work, gates, branches, retries, and outcomes"},
    "sequence": {"body": ["participants", "messages"], "focus": "calls, returns, and async messages over time"},
    "dataflow": {"body": ["entities", "flows"], "focus": "sources, transformations, stores, and consumers"},
    "lifecycle": {"body": ["states", "transitions"], "focus": "states, retries, cancellation, and terminal outcomes"},
}


def _guide(diagram_type: str | None = None, output_format: str = "json") -> str:
    if diagram_type and diagram_type not in DIAGRAM_GUIDE:
        raise DiagramError("guide type must be one of: " + ", ".join(sorted(DIAGRAM_GUIDE)))
    guide = {
        "schema_versions": {
            "1": "Offline static HTML/SVG. It never executes viewer JavaScript.",
            "2": "Same typed model plus Patpat's versioned inline viewer, strict CSP hashes, and offline exports.",
        },
        "types": {diagram_type: DIAGRAM_GUIDE[diagram_type]} if diagram_type else DIAGRAM_GUIDE,
        "limits": {"entities": 80, "relationships": 160, "evidence": 240, "source_json_bytes": MAX_SOURCE_JSON_BYTES},
        "profiles": {
            "deployment-ownership": "schema_version 2 architecture only; every component must belong to one source-confirmed boundary.",
        },
        "browser_quality_profiles": {
            "standard": "one 1440x1100 light-theme Chromium capture bound to the exact HTML bytes.",
            "showcase": "schema 2 only; desktop, tablet, and mobile captures in light and dark themes, a contact sheet, and one recoverable receipt-bound output transaction.",
        },
        "authoring": {
            "evidence": "Brief claims use {origin: brief, id, claim} and are digest-bound but not code-verified. Repository claims use {origin: repository, id, path, start_line, end_line, claim}; origin may be omitted for compatibility. Confirmed and inferred claims need evidence IDs; unknown claims need a reason and no evidence IDs.",
            "sources": "Use brief evidence without --repo-root. Repository evidence requires the exact Git root; mixed diagrams verify repository lines and keep brief claims separately identified.",
            "mermaid": "Mermaid or prose may guide the author, but must be converted into and validated as Patpat typed JSON. There is no Mermaid parser.",
            "view_state": "Focus, search, zoom, and current route are transient. Diagram exports exclude focus and filters; raster and video use the selected theme, and SVG exports name their theme.",
        },
        "commands": ["validate", "finalize", "check", "browser-check", "preview", "compare", "guide"],
    }
    if output_format == "json":
        return json.dumps(guide, indent=2, ensure_ascii=False)
    body = [f"Patpat repository-diagram schema: {', '.join(guide['schema_versions'])}"]
    for key, item in guide["types"].items():
        body.append(f"{key}: {item['focus']}; body fields: {', '.join(item['body'])}")
    body.extend((guide["authoring"]["evidence"], guide["authoring"]["sources"], guide["authoring"]["mermaid"], "Commands: " + ", ".join(guide["commands"])))
    return "\n".join(body)


def _stable_diagnostic(error: Exception, stage: str) -> dict[str, Any]:
    message = str(error)
    lowered = message.lower()
    subject = None
    measurement = None
    if isinstance(error, FileNotFoundError):
        code, fixes = "input.missing", ["Confirm the source file path and retry.", "Run guide to inspect the supported command contract."]
        subject = Path(error.filename).name if error.filename else None
    elif "edge self-crossing:" in lowered:
        code = "layout.route-self-crossing"
        fixes = ["Reroute the named relationship so non-adjacent segments do not intersect.", "Rerun validate, finalize, and inspect the rendered view."]
        match = re.search(r"edge self-crossing:\s*([^/\s;]+)", message, re.IGNORECASE)
        subject = match.group(1) if match else None
    elif "node layer reading order:" in lowered:
        code = "layout.layer-reading-order"
        fixes = ["Move the authored nodes to match their declared within-layer reading order.", "Rerun validate and inspect the rendered view."]
        match = re.search(r"node layer reading order:\s*[^()]+\(([^\s]+)", message, re.IGNORECASE)
        subject = match.group(1) if match else None
    elif "node layer order:" in lowered:
        code = "layout.rank-direction"
        fixes = ["Move the authored node ranks forward along the declared layout direction.", "Rerun validate and inspect the rendered view."]
        match = re.search(r"node layer order:\s*[^()]+\(([^\s]+)", message, re.IGNORECASE)
        subject = match.group(1) if match else None
    elif "edge route overlaps relationship label:" in lowered:
        code = "layout.label-route-clearance"
        fixes = ["Move the relationship label or reroute the named relationship segment without changing its meaning.", "Rerun validate, finalize, and inspect the rendered view."]
        match = re.search(r"edge route overlaps relationship label:\s*([^/\s;]+)", message, re.IGNORECASE)
        subject = match.group(1) if match else None
        marker = message.find("measurement=")
        if marker >= 0:
            try:
                measurement, _ = json.JSONDecoder().raw_decode(message[marker + len("measurement="):].lstrip())
            except json.JSONDecodeError:
                measurement = None
    elif "edge route reenters hinted endpoint:" in lowered:
        code = "layout.port-side"
        fixes = ["Keep route segments outside the hinted endpoint after the side-aligned port lead.", "Adjust the relationship waypoints, then rerun validate before finalizing."]
        match = re.search(r"edge route reenters hinted endpoint:\s*([^/\s;]+)", message, re.IGNORECASE)
        subject = match.group(1) if match else None
    elif stage == "browser-check" or "browser" in lowered:
        code, fixes = "browser.render", ["Install or select a supported local Chromium executable.", "Keep browser sandboxing enabled and rerun browser-check."]
    elif any(token in lowered for token in ("evidence", "source path", "line range", "repository root", "git metadata", "git source")):
        code, fixes = "evidence.snapshot", ["Reopen the cited source path and inclusive line range.", "Update the claim or keep it unknown when repository bytes cannot confirm it."]
    elif "readability" in lowered:
        code, fixes = "layout.readability", ["Reduce canvas width or separate distinct chapters without dropping required facts.", "Rerun validate and inspect the rendered desktop view."]
    elif any(token in lowered for token in ("layout", "overlap", "crossing", "geometry", "layer", "outside canvas")):
        code, fixes = "layout.geometry", ["Change authored layers or direction; do not silently reverse or reorder a relationship.", "Rerun validate before finalizing."]
    elif any(token in lowered for token in ("script", "csp", "active content", "external", "credential", "unsafe", "symlink")):
        code, fixes = "security.content", ["Remove external or user-authored active content.", "Use only the versioned Patpat renderer and trusted viewer."]
    elif any(token in lowered for token in ("receipt", "digest", "output set", "artifact", "transaction", "overwrite")):
        code, fixes = "artifact.integrity", ["Preserve the current artifact set and inspect the receipt.", "Render under a new slug, then run check."]
    elif any(token in lowered for token in ("json", "utf-8", "object key")):
        code, fixes = "input.json", ["Repair the JSON syntax and remove duplicate object keys.", "Run guide, then validate the typed source again."]
    else:
        code, fixes = "model.invalid", ["Run guide and correct the reported typed field.", "Revalidate before rendering; stop after two correction rounds if the contract remains unclear."]
    diagnostic = {
        "schema_version": 1,
        "status": "error",
        "code": code,
        "stage": stage,
        "subject": subject,
        "observed": message,
        "supported_fixes": fixes,
        "correction_round_limit": 2,
    }
    if measurement is not None:
        diagnostic["measurement"] = measurement
    return diagnostic


def _png_decode(png_bytes: bytes, expected_dimensions: tuple[int, int] | None = None) -> tuple[list[tuple[bytes, bytes]], bytes, int, int, bytes, int | None]:
    signature = b"\x89PNG\r\n\x1a\n"
    if not png_bytes.startswith(signature):
        raise DiagramError("browser screenshot is not a PNG")
    chunks: list[tuple[bytes, bytes]] = []
    offset = len(signature)
    image_data_started = False
    image_data_ended = False
    ended = False
    while offset < len(png_bytes):
        if offset + 12 > len(png_bytes):
            raise DiagramError("browser screenshot has a truncated PNG chunk")
        size = int.from_bytes(png_bytes[offset:offset + 4], "big")
        kind = png_bytes[offset + 4:offset + 8]
        if any(not (65 <= byte <= 90 or 97 <= byte <= 122) for byte in kind) or kind[2] & 0x20:
            raise DiagramError("browser screenshot PNG has an invalid chunk type")
        end = offset + 12 + size
        if end > len(png_bytes):
            raise DiagramError("browser screenshot has a truncated PNG chunk")
        if not chunks and kind != b"IHDR":
            raise DiagramError("browser screenshot PNG does not start with its header")
        if kind == b"IHDR" and chunks:
            raise DiagramError("browser screenshot PNG has multiple headers")
        if kind == b"IDAT":
            if image_data_ended:
                raise DiagramError("browser screenshot PNG image data is not contiguous")
            image_data_started = True
        elif image_data_started and kind != b"IEND":
            image_data_ended = True
        if kind == b"PLTE" and (image_data_started or any(existing == b"PLTE" for existing, _ in chunks)):
            raise DiagramError("browser screenshot PNG has a misplaced or repeated palette")
        if kind == b"IEND" and size != 0:
            raise DiagramError("browser screenshot PNG has an invalid end chunk")
        if kind not in {b"IHDR", b"PLTE", b"IDAT", b"IEND"} and kind[0] & 0x20 == 0:
            raise DiagramError("browser screenshot PNG contains an unsupported critical chunk")
        payload = png_bytes[offset + 8:offset + 8 + size]
        checksum = int.from_bytes(png_bytes[offset + 8 + size:end], "big")
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != checksum:
            raise DiagramError("browser screenshot has an invalid PNG checksum")
        chunks.append((kind, payload))
        offset = end
        if kind == b"IEND":
            if offset != len(png_bytes):
                raise DiagramError("browser screenshot PNG has data after its end chunk")
            ended = True
            break
    if not ended or not image_data_started:
        raise DiagramError("browser screenshot PNG is missing image data or its end chunk")
    header = next((payload for kind, payload in chunks if kind == b"IHDR"), None)
    if header is None or len(header) != 13:
        raise DiagramError("browser screenshot is missing a valid PNG header")
    width, source_height = int.from_bytes(header[:4], "big"), int.from_bytes(header[4:8], "big")
    bit_depth, color_type, compression, filter_method, interlace = header[8:13]
    channels_by_type = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
    valid_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
    if (
        width < 1 or source_height < 1 or color_type not in channels_by_type
        or bit_depth not in valid_depths.get(color_type, set())
        or compression != 0 or filter_method != 0 or interlace not in {0, 1}
    ):
        raise DiagramError("browser screenshot uses an invalid PNG image layout")
    if width * source_height > 16_000_000:
        raise DiagramError("browser screenshot PNG dimensions exceed the capture limit")
    if expected_dimensions is not None and (width, source_height) != expected_dimensions:
        raise DiagramError("browser screenshot PNG dimensions do not match the measured capture")
    if color_type == 3 and not any(kind == b"PLTE" for kind, _ in chunks):
        raise DiagramError("browser screenshot indexed PNG has no palette")
    palette = next((payload for kind, payload in chunks if kind == b"PLTE"), None)
    if palette is not None and (
        color_type not in {2, 3, 6} or not palette or len(palette) % 3 != 0
        or len(palette) > 768 or (color_type == 3 and len(palette) // 3 > 2 ** bit_depth)
    ):
        raise DiagramError("browser screenshot PNG has an invalid palette")
    idat_indexes = [index for index, (kind, _) in enumerate(chunks) if kind == b"IDAT"]
    if not idat_indexes or idat_indexes != list(range(idat_indexes[0], idat_indexes[-1] + 1)):
        raise DiagramError("browser screenshot has no contiguous PNG image data")
    compressed = b"".join(chunks[index][1] for index in idat_indexes)
    bits_per_pixel = channels_by_type[color_type] * bit_depth
    passes = ((0, 0, 1, 1),) if interlace == 0 else (
        (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8),
        (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2),
    )
    scanline_layout: list[tuple[int, int]] = []
    for start_x, start_y, step_x, step_y in passes:
        pass_width = max(0, (width - start_x + step_x - 1) // step_x)
        pass_height = max(0, (source_height - start_y + step_y - 1) // step_y)
        if pass_width and pass_height:
            scanline_layout.append(((pass_width * bits_per_pixel + 7) // 8, pass_height))
    expected_data_size = sum((row_size + 1) * rows for row_size, rows in scanline_layout)
    if expected_data_size > 128_000_000:
        raise DiagramError("browser screenshot PNG data exceeds the capture limit")
    decoder = zlib.decompressobj()
    try:
        scanlines = decoder.decompress(compressed, expected_data_size + 1)
    except zlib.error as error:
        raise DiagramError("browser screenshot has invalid compressed PNG data") from error
    if (
        len(scanlines) != expected_data_size or not decoder.eof
        or decoder.unused_data or decoder.unconsumed_tail
    ):
        raise DiagramError("browser screenshot PNG image data is incomplete or has trailing compressed bytes")
    offset = 0
    for row_size, rows in scanline_layout:
        for _ in range(rows):
            if scanlines[offset] > 4:
                raise DiagramError("browser screenshot PNG has an invalid scanline filter")
            offset += row_size + 1
    row_size = 1 + (width * bits_per_pixel + 7) // 8 if interlace == 0 else None
    return chunks, header, width, source_height, scanlines, row_size


def _png_crop_bottom(png_bytes: bytes, target_height: int) -> bytes:
    if target_height < 1:
        raise DiagramError("browser screenshot crop height is invalid")
    chunks, header, width, source_height, scanlines, row_size = _png_decode(png_bytes)
    if target_height > source_height:
        raise DiagramError("browser screenshot is shorter than its requested viewport")
    if target_height == source_height:
        return png_bytes
    if row_size is None:
        raise DiagramError("browser screenshot uses interlacing that cannot be viewport-cropped")
    cropped = zlib.compress(scanlines[:row_size * target_height], level=9)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return len(payload).to_bytes(4, "big") + kind + payload + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big")

    output = bytearray(b"\x89PNG\r\n\x1a\n")
    inserted_image_data = False
    for index, (kind, payload) in enumerate(chunks):
        if kind == b"IHDR":
            payload = payload[:4] + target_height.to_bytes(4, "big") + payload[8:]
            output.extend(chunk(kind, payload))
        elif kind == b"IDAT":
            if not inserted_image_data:
                output.extend(chunk(b"IDAT", cropped))
                inserted_image_data = True
        else:
            output.extend(chunk(kind, payload))
    cropped_png = bytes(output)
    _png_decode(cropped_png, (width, target_height))
    return cropped_png


def _browser_capture_wrapper(page_html: str, width: int, height: int, theme: str) -> str:
    if width < 1 or height < 1 or theme not in {"light", "dark"}:
        raise DiagramError("browser capture viewport or theme is invalid")
    head_end = re.search(r"</head\s*>", page_html, re.IGNORECASE)
    if head_end is None:
        raise DiagramError("browser capture requires a complete HTML head")
    child_html = (
        page_html[:head_end.start()]
        + f'<meta name="patpat-browser-check" content="1"><meta name="patpat-browser-check-theme" content="{theme}">'
        + page_html[head_end.start():]
    )
    srcdoc = html.escape(child_html, quote=True)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Patpat browser capture</title>
<style>html,body{{margin:0;padding:0;background:#fff}}iframe{{display:block;width:{width}px;height:{height}px;border:0}}</style></head>
<body><iframe id="diagram-frame" title="Diagram browser capture" srcdoc="{srcdoc}"></iframe>
<script>(()=>{{const frame=document.getElementById("diagram-frame");let completed=false;const mark=()=>{{if(completed)return;try{{const doc=frame.contentDocument;if(!doc||!doc.querySelector("svg")){{setTimeout(mark,25);return}}const svg=[...doc.querySelectorAll("svg")].find(candidate=>candidate.querySelector("#diagram-title"));const title=svg?.querySelector("#diagram-title");const root=doc.documentElement;const body=document.body;const interactive=Boolean(doc.querySelector('meta[name="patpat-diagram-schema"][content="2"]'));if(!interactive&&doc.body)doc.body.dataset.theme="{theme}";const viewerReady=doc.body?.dataset.viewerReady==="true";body.dataset.patpatBrowserSvg=String(Boolean(svg));body.dataset.patpatBrowserTitle=String(Boolean(title));body.dataset.patpatBrowserReady=viewerReady?"true":interactive?"false":"static";body.dataset.patpatBrowserTheme=doc.body?.dataset.theme||"";body.dataset.patpatBrowserViewport=String(doc.defaultView?.innerWidth||root.dataset.patpatBrowserViewport||"");body.dataset.patpatBrowserViewportHeight=String(doc.defaultView?.innerHeight||root.dataset.patpatBrowserViewportHeight||"");body.dataset.patpatBrowserScrollWidth=String(root.scrollWidth||root.dataset.patpatBrowserScrollWidth||"");body.dataset.patpatBrowserCaptureInset=String(Math.max(0,window.outerHeight-window.innerHeight));const pageBackground=doc.defaultView?.getComputedStyle(doc.body).backgroundColor;if(pageBackground&&pageBackground!=="rgba(0, 0, 0, 0)"){{document.documentElement.style.backgroundColor=pageBackground;body.style.backgroundColor=pageBackground}}if(interactive&&!viewerReady){{setTimeout(mark,25);return}}completed=true}}catch(error){{document.body.dataset.patpatBrowserError=String(error).slice(0,120);setTimeout(mark,25)}}}};frame.addEventListener("load",mark,{{once:true}});setTimeout(mark,0);setTimeout(()=>{{if(!completed){{document.body.dataset.patpatBrowserFailure="viewer-not-ready";completed=true}}}},5000)}})();</script></body></html>'''


def _browser_check(
    html_path: Path,
    repo_root: Path | None,
    screenshot: Path | None,
    browser: str | None,
    receipt_path: Path | None = None,
    profile: str = "standard",
) -> dict[str, Any]:
    if profile not in {"standard", "showcase"}:
        raise DiagramError("browser quality profile must be standard or showcase")
    html_path = html_path.resolve(strict=True)
    _check(html_path, repo_root)
    html_bytes = html_path.read_bytes()
    _check(html_path, repo_root)
    if html_path.read_bytes() != html_bytes:
        raise DiagramError("HTML changed while browser evidence was being prepared")
    browser_path = Path(browser).resolve() if browser else None
    if browser_path is None:
        candidates = ("google-chrome", "google-chrome-stable", "chrome", "msedge", "chromium", "chromium-browser")
        for candidate in candidates:
            found = shutil.which(candidate)
            if found is None:
                continue
            resolved = Path(found).resolve()
            if resolved.name.lower() in {"snap", "flatpak"}:
                continue
            browser_path = resolved
            break
        if browser_path is None:
            raise DiagramError("no supported Chromium browser found; browser render was not performed")
    if not browser_path.is_file():
        raise DiagramError("browser path does not identify a file")
    if browser_path.name.lower() in {"snap", "flatpak"}:
        raise DiagramError("browser path resolves to a package-manager wrapper, not a browser executable")

    browser_slug = None
    if screenshot is not None:
        screenshot = Path(screenshot)
        if screenshot.is_symlink() or screenshot.exists():
            raise DiagramError("screenshot output already exists or is a symlink")
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot = screenshot.parent.resolve(strict=True) / screenshot.name
        match = re.fullmatch(r"([a-z0-9]+(?:-[a-z0-9]+)*)\.browser\.png", screenshot.name)
        if not match:
            raise DiagramError("browser screenshot filename must be <slug>.browser.png")
        browser_slug = match.group(1)
    if receipt_path is not None:
        receipt_path = Path(receipt_path)
        if receipt_path.exists() or receipt_path.is_symlink():
            raise DiagramError("browser receipt output already exists")
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_path.parent.resolve(strict=True) / receipt_path.name
        match = re.fullmatch(r"([a-z0-9]+(?:-[a-z0-9]+)*)\.browser\.receipt\.json", receipt_path.name)
        if not match:
            raise DiagramError("browser receipt filename must be <slug>.browser.receipt.json")
        if browser_slug is not None and browser_slug != match.group(1):
            raise DiagramError("browser screenshot and receipt must use the same artifact slug")
        browser_slug = match.group(1)
        if screenshot is not None and screenshot.parent != receipt_path.parent:
            raise DiagramError("browser screenshot and receipt must share one output directory")
    if profile == "showcase" and (screenshot is None or receipt_path is None):
        raise DiagramError("showcase capture requires both <slug>.browser.png and <slug>.browser.receipt.json outputs")
    if profile == "showcase" and b'name="patpat-diagram-schema" content="2"' not in html_bytes:
        raise DiagramError("showcase profile requires the interactive schema 2 viewer so both themes can be captured")

    layouts = {"desktop": (1440, 1100), "tablet": (1024, 768), "mobile": (390, 844)}
    themes = ("light", "dark") if profile == "showcase" else ("light",)
    capture_records: list[dict[str, Any]] = []
    capture_bytes: dict[str, bytes] = {}
    page_html = html_bytes.decode("utf-8")
    interactive = b'name="patpat-diagram-schema" content="2"' in html_bytes
    with tempfile.TemporaryDirectory(prefix="patpat-diagram-browser-") as temp_name:
        temp_dir = Path(temp_name)
        chromium_inset: int | None = None

        def capture_browser_page(snapshot_path: Path, view: str, theme: str, viewport: tuple[int, int], window_height: int, suffix: str) -> tuple[subprocess.CompletedProcess[str], Path]:
            capture_path = temp_dir / f"{view}-{theme}-{suffix}.png"
            args = [
                str(browser_path), "--headless", "--disable-gpu", "--disable-dev-shm-usage",
                "--disable-extensions", "--disable-background-networking", "--disable-sync", "--no-first-run",
                "--hide-scrollbars", f"--window-size={viewport[0]},{window_height}",
                "--run-all-compositor-stages-before-draw", f"--user-data-dir={temp_dir / ('profile-' + view + '-' + theme + '-' + suffix)}",
                f"--screenshot={capture_path}", "--dump-dom", snapshot_path.as_uri(),
            ]
            try:
                result = subprocess.run(args, capture_output=True, text=True, timeout=45, check=False)
            except (OSError, subprocess.TimeoutExpired) as error:
                raise DiagramError(f"browser render failed at {view}/{theme}: {error}") from error
            if result.returncode != 0 or not capture_path.is_file():
                detail = result.stderr[-1200:].strip()
                raise DiagramError(f"browser did not produce a screenshot at {view}/{theme}" + (f": {detail}" if detail else ""))
            return result, capture_path

        for view, viewport in layouts.items():
            if profile == "standard" and view != "desktop":
                continue
            for theme in themes:
                capture_name = f"{view}-{theme}"
                wrapper = _browser_capture_wrapper(page_html, viewport[0], viewport[1], theme)
                snapshot_path = temp_dir / f"{capture_name}.html"
                with snapshot_path.open("xb") as snapshot:
                    snapshot.write(wrapper.encode("utf-8"))
                    snapshot.flush()
                    os.fsync(snapshot.fileno())
                if chromium_inset is None:
                    result, probe_path = capture_browser_page(snapshot_path, view, theme, viewport, viewport[1], "probe")
                    inset_match = re.search(r'data-patpat-browser-capture-inset="(\d+)"', result.stdout)
                    if inset_match is None:
                        raise DiagramError(f"browser did not report its screenshot viewport inset at {view}/{theme}")
                    chromium_inset = int(inset_match.group(1))
                    if chromium_inset:
                        result, capture_path = capture_browser_page(
                            snapshot_path, view, theme, viewport, viewport[1] + chromium_inset, "capture"
                        )
                    else:
                        result, capture_path = result, probe_path
                else:
                    result, capture_path = capture_browser_page(
                        snapshot_path, view, theme, viewport, viewport[1] + chromium_inset, "capture"
                    )
                if 'data-patpat-browser-svg="true"' not in result.stdout or 'data-patpat-browser-title="true"' not in result.stdout:
                    names = ("svg", "title", "ready", "theme", "viewport", "viewport-height", "scroll-width", "capture-inset", "error", "failure")
                    observed = {
                        key: (match.group(1) if (match := re.search(rf'data-patpat-browser-{re.escape(key)}="([^"]*)"', result.stdout)) else "missing")
                        for key in names
                    }
                    detail = ", ".join(f"{key}={value}" for key, value in observed.items())
                    raise DiagramError(f"browser DOM did not expose the embedded SVG and accessible title at {view}/{theme} ({detail})")
                inset_match = re.search(r'data-patpat-browser-capture-inset="(\d+)"', result.stdout)
                if inset_match is None or int(inset_match.group(1)) != chromium_inset:
                    raise DiagramError(f"browser screenshot inset changed during {view}/{theme} capture")
                if interactive and 'data-patpat-browser-ready="true"' not in result.stdout:
                    raise DiagramError(f"browser did not initialize the trusted diagram viewer at {view}/{theme}")
                if f'data-patpat-browser-theme="{theme}"' not in result.stdout:
                    raise DiagramError(f"browser did not apply the requested {theme} theme at {view}/{theme}")
                viewport_match = re.search(r'data-patpat-browser-viewport="(\d+)"', result.stdout)
                height_match = re.search(r'data-patpat-browser-viewport-height="(\d+)"', result.stdout)
                scroll_match = re.search(r'data-patpat-browser-scroll-width="(\d+)"', result.stdout)
                if viewport_match is None or height_match is None or scroll_match is None:
                    raise DiagramError(f"browser did not report the embedded CSS viewport at {view}/{theme}")
                css_width, css_height, scroll_width = int(viewport_match.group(1)), int(height_match.group(1)), int(scroll_match.group(1))
                if [css_width, css_height] != list(viewport):
                    raise DiagramError(f"browser CSS viewport is {css_width}×{css_height}px, expected {viewport[0]}×{viewport[1]}px at {view}/{theme}")
                if scroll_width > css_width:
                    raise DiagramError(f"document overflows horizontally by {scroll_width - css_width}px at {view}/{theme}")
                png = capture_path.read_bytes()
                _, _, width, height, _, _ = _png_decode(
                    png, (viewport[0], viewport[1] + chromium_inset)
                )
                if chromium_inset:
                    png = _png_crop_bottom(png, viewport[1])
                _, _, width, height, _, _ = _png_decode(png, viewport)
                capture_bytes[capture_name] = png
                filename = f"{browser_slug}.browser.png" if view == "desktop" and theme == "light" and browser_slug else f"{browser_slug}.showcase-{capture_name}.png" if browser_slug else None
                capture_records.append({
                    "viewport_name": view, "viewport": list(viewport), "theme": theme,
                    "file": filename, "sha256": hashlib.sha256(png).hexdigest(),
                    "bytes": len(png), "image_size": [width, height],
                })

        _check(html_path, repo_root)
        if html_path.read_bytes() != html_bytes:
            raise DiagramError("HTML changed during browser evidence capture")
        primary = capture_bytes["desktop-light"]
        primary_record = next(item for item in capture_records if item["viewport_name"] == "desktop" and item["theme"] == "light")
        result_receipt: dict[str, Any] = {
            "schema_version": 1,
            "status": "passed",
            "quality_profile": profile,
            "html": html_path.name,
            "html_sha256": hashlib.sha256(html_bytes).hexdigest(),
            "browser": browser_path.name,
            "viewport": [1440, 1100],
            "theme": "light",
            "screenshot": screenshot.name if screenshot else None,
            "screenshot_sha256": hashlib.sha256(primary).hexdigest(),
            "screenshot_bytes": len(primary),
            "image_size": primary_record["image_size"],
        }
        files: dict[str, bytes] = {}
        if profile == "showcase":
            if browser_slug is None or screenshot is None or receipt_path is None:
                raise DiagramError("showcase capture outputs do not identify an artifact slug")
            for record in capture_records:
                if record["file"]:
                    files[record["file"]] = capture_bytes[f"{record['viewport_name']}-{record['theme']}"]
            contact = _browser_contact_sheet(capture_records, capture_bytes)
            contact_name = f"{browser_slug}.showcase-contact.svg"
            files[contact_name] = contact
            result_receipt["captures"] = capture_records
            result_receipt["contact_sheet"] = {"file": contact_name, "sha256": hashlib.sha256(contact).hexdigest(), "bytes": len(contact)}
        else:
            if screenshot is not None:
                files[screenshot.name] = primary
        if receipt_path is not None:
            files[receipt_path.name] = (json.dumps(result_receipt, indent=2) + "\n").encode("utf-8")
        if files:
            destination = screenshot.parent if screenshot is not None else receipt_path.parent
            _atomic_set(destination, files, False, "browser-showcase" if profile == "showcase" else "browser", browser_slug)
        return result_receipt


def _browser_contact_sheet(records: list[dict[str, Any]], images: dict[str, bytes]) -> bytes:
    namespace = "http://www.w3.org/2000/svg"
    root = ET.Element(f"{{{namespace}}}svg", {"width": "1800", "height": "900", "viewBox": "0 0 1800 900", "role": "img"})
    ET.SubElement(root, f"{{{namespace}}}title").text = "Patpat diagram multi-viewport and theme contact sheet"
    ET.SubElement(root, f"{{{namespace}}}rect", {"width": "1800", "height": "900", "fill": "#eef2f8"})
    for index, record in enumerate(records):
        row, column = divmod(index, 3)
        x, y = 18 + column * 594, 20 + row * 438
        label = f"{record['viewport_name']} · {record['viewport'][0]}x{record['viewport'][1]} · {record['theme']}"
        ET.SubElement(root, f"{{{namespace}}}text", {"x": str(x + 8), "y": str(y + 22), "font-family": "Arial, sans-serif", "font-size": "16", "font-weight": "700", "fill": "#263753"}).text = label
        ET.SubElement(root, f"{{{namespace}}}rect", {"x": str(x), "y": str(y + 34), "width": "574", "height": "390", "rx": "10", "fill": "#fff", "stroke": "#94a3b8", "stroke-width": "1"})
        image = images[f"{record['viewport_name']}-{record['theme']}"]
        encoded = base64.b64encode(image).decode("ascii")
        ET.SubElement(root, f"{{{namespace}}}image", {
            "x": str(x + 8), "y": str(y + 42), "width": "558", "height": "374",
            "preserveAspectRatio": "xMidYMid meet", "href": f"data:image/png;base64,{encoded}",
        })
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

def _sample_spec(diagram_type: str, title: str) -> dict[str, Any]:
    evidence = [{"id": "S1", "path": "source.txt", "start_line": 1, "end_line": 3, "claim": "Sample source call path"}]
    def item(identifier: str, label: str, kind: str) -> dict[str, Any]:
        return {"id": identifier, "label": label, "kind": kind, "certainty": "confirmed", "evidence_ids": ["S1"]}
    def edge(identifier: str, source: str, target: str, label: str, kind: str, **extra: Any) -> dict[str, Any]:
        return {"id": identifier, "source": source, "target": target, "label": label, "kind": kind, "certainty": "confirmed", "evidence_ids": ["S1"], **extra}
    if diagram_type == "architecture":
        body = {"components": [item("N1", "Browser client", "actor"), item("N2", "Request service", "service"), item("N3", "Records database", "database")], "relationships": [edge("E1", "N1", "N2", "HTTP request", "call"), edge("E2", "N2", "N3", "parameterized query", "data")]}
    elif diagram_type == "workflow":
        body = {"steps": [item("N1", "Request received", "start"), item("N2", "Check authorization", "gate"), item("N3", "Process request", "action"), item("N4", "Reject request", "action"), item("N5", "Return response", "terminal")], "transitions": [edge("E1", "N1", "N2", "check policy", "next"), edge("E2", "N2", "N3", "authorized", "yes"), edge("E3", "N2", "N4", "denied", "no"), edge("E4", "N3", "N5", "processed", "next"), edge("E5", "N4", "N5", "rejected", "next")]}
    elif diagram_type == "sequence":
        body = {"participants": [item("N1", "Browser client", "client"), item("N2", "Request service", "service"), item("N3", "Records database", "database")], "messages": [edge("E1", "N1", "N2", "POST /records", "call", order=1), edge("E2", "N2", "N3", "INSERT record", "async", order=2), edge("E3", "N2", "N1", "201 response", "return", order=3)]}
    elif diagram_type == "dataflow":
        body = {"entities": [item("N1", "Request body", "source"), item("N2", "Validate fields", "transform"), item("N3", "Records database", "store")], "flows": [edge("E1", "N1", "N2", "validated payload", "data"), edge("E2", "N2", "N3", "parameterized values", "snapshot")]}
    else:
        body = {"states": [item("N1", "Received", "initial"), item("N2", "Stored", "state"), item("N3", "Rejected", "terminal")], "transitions": [edge("E1", "N1", "N2", "authorization passed", "transition"), edge("E2", "N1", "N3", "authorization failed", "error")]}
    return {"schema_version": 1, "type": diagram_type, "title": title, "summary": "A short source-backed request path", "evidence": evidence, "body": body}


def self_test() -> None:
    global _browser_check
    viewer_source = _viewer_script()
    if (
        "patpat-browser-check" not in viewer_source
        or "dataset.patpatBrowserViewport" not in viewer_source
        or "dataset.patpatBrowserViewportHeight" not in viewer_source
        or 'meta[name="patpat-browser-check-theme"]' not in viewer_source
    ):
        raise AssertionError("browser check must expose the actual CSS viewport for schema v2")
    capture_wrapper = _browser_capture_wrapper(
        '<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',
        390, 844, "dark",
    )
    if (
        "width:390px;height:844px" not in capture_wrapper
        or "overflow:hidden" in capture_wrapper
        or "patpatBrowserViewport" not in capture_wrapper
        or "patpatBrowserViewportHeight" not in capture_wrapper
        or "patpatBrowserCaptureInset" not in capture_wrapper
        or "if(!interactive&&doc.body)doc.body.dataset.theme=\"dark\"" not in capture_wrapper
        or "interactive&&!viewerReady" not in capture_wrapper
        or '&lt;meta name=&quot;patpat-browser-check-theme&quot; content=&quot;dark&quot;&gt;' not in capture_wrapper
    ):
        raise AssertionError("browser capture wrapper must enforce the selected viewport and theme inside the real viewer")

    def png_chunk(kind: bytes, payload: bytes) -> bytes:
        return len(payload).to_bytes(4, "big") + kind + payload + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big")

    sample_png = b"\x89PNG\r\n\x1a\n" + png_chunk(
        b"IHDR", (2).to_bytes(4, "big") + (2).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    ) + png_chunk(b"IDAT", zlib.compress(b"\x00\x01\x02\x03\x04\x05\x06\x00\x07\x08\x09\x0a\x0b\x0c")) + png_chunk(b"IEND", b"")
    if _png_decode(sample_png, (2, 2))[2:4] != (2, 2):
        raise AssertionError("browser screenshot PNG verification must bind decoded pixels to expected dimensions")
    cropped_png = _png_crop_bottom(sample_png, 1)
    decoded_crop = _png_decode(cropped_png, (2, 1))
    if decoded_crop[4] != b"\x00\x01\x02\x03\x04\x05\x06":
        raise AssertionError("browser screenshot crop must preserve PNG scanlines and update the viewport dimensions")
    truncated_image = b"\x89PNG\r\n\x1a\n" + png_chunk(
        b"IHDR", (2).to_bytes(4, "big") + (2).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    ) + png_chunk(b"IDAT", zlib.compress(b"\x00\x01\x02\x03\x04\x05\x06\x00\x07\x08\x09\x0a\x0b\x0c")[:-1]) + png_chunk(b"IEND", b"")
    bad_chunk_type = b"\x89PNG\r\n\x1a\n" + png_chunk(
        b"IHDR", (2).to_bytes(4, "big") + (2).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    ) + png_chunk(b"aBca", b"") + png_chunk(
        b"IDAT", zlib.compress(b"\x00\x01\x02\x03\x04\x05\x06\x00\x07\x08\x09\x0a\x0b\x0c")
    ) + png_chunk(b"IEND", b"")
    invalid_palette = b"\x89PNG\r\n\x1a\n" + png_chunk(
        b"IHDR", (2).to_bytes(4, "big") + (2).to_bytes(4, "big") + bytes([8, 2, 0, 0, 0])
    ) + png_chunk(b"PLTE", b"") + png_chunk(
        b"IDAT", zlib.compress(b"\x00\x01\x02\x03\x04\x05\x06\x00\x07\x08\x09\x0a\x0b\x0c")
    ) + png_chunk(b"IEND", b"")
    for malformed in (sample_png[:-12], truncated_image, bad_chunk_type, invalid_palette):
        try:
            _png_decode(malformed)
        except DiagramError:
            continue
        raise AssertionError("browser screenshot receipts must reject incomplete PNG chunks and image streams")
    if (
        "centerMobileCanvas" not in viewer_source
        or 'const firstNode = figure.querySelector("[data-node-id]");' not in viewer_source
        or "nodeCenter - figure.clientWidth / 2" not in viewer_source
        or "figure.scrollLeft" not in viewer_source
    ):
        raise AssertionError("mobile viewers must initially center the first authored node within their pan region")
    if "overview-node-${markerKind}" not in viewer_source or "overview-node-id" not in viewer_source or "markerBounds" not in viewer_source:
        raise AssertionError("overview maps must identify nodes and distinguish workflow start, decision, and terminal states")
    if 'const candidates = [...horizontalCandidates, "above", "below"]' not in viewer_source or "box.bottom > height - 4" not in viewer_source:
        raise AssertionError("overview maps must place labels around crowded nodes without clipping them")
    mobile_controls = (
        ".tool-field{min-width:0;width:100%;flex:1 1 100%}",
        ".tool-field input,.tool-field select{width:100%;min-width:0;max-width:100%}",
        ".tool-row>button{max-width:100%;white-space:normal;overflow-wrap:anywhere}",
    )
    if any(rule not in HTML_CSS for rule in mobile_controls):
        raise AssertionError("mobile viewer controls must fit the viewport and wrap without horizontal overflow")
    if ".tool-field input,.tool-field select{width:100%;min-width:0;max-width:100%}" not in HTML_CSS:
        raise AssertionError("long native option labels must stay inside their viewer field at every viewport")
    if (
        ".context-neighbors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" not in HTML_CSS
        or ".context-neighbor code{min-width:0;white-space:normal;overflow-wrap:anywhere" not in HTML_CSS
        or 'class: "radar-node-index"' not in viewer_source
        or "const x = 286 + index * 37;" not in viewer_source
        or 'className = "context-neighbors"' not in viewer_source
    ):
        raise AssertionError("relationship context must keep node identities readable without overlapping radar labels")
    if (
        ".diagram-tools{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px 8px}" not in HTML_CSS
        or ".diagram-tools>.overview-drawer[open],.diagram-tools>.explore-tools[open]{grid-column:1/-1}" not in HTML_CSS
        or ".primary-actions{flex-wrap:nowrap;overflow-x:auto}" not in HTML_CSS
    ):
        raise AssertionError("mobile controls must keep primary actions compact and let expanded disclosures use the full row")
    if ".diagram-tools{position:sticky" in HTML_CSS or "#explore-tools[open] .advanced-tools{max-height:" not in HTML_CSS:
        raise AssertionError("expanded diagram controls must not stick over the canvas")
    if ".diagram-pan-hint{display:block}" not in HTML_CSS or "pan_hint" not in UI_TEXT["th"]:
        raise AssertionError("mobile diagrams must include a localized horizontal-pan cue")
    if ".mobile-diagram-intro{display:none}" not in HTML_CSS or "figure svg{margin-top:-124px;min-width:1000px}" not in HTML_CSS:
        raise AssertionError("mobile diagrams must expose a responsive title and reclaim the hidden SVG header space")
    if ".mobile-diagram-intro p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.45;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}" not in HTML_CSS:
        raise AssertionError("mobile diagrams must keep the summary readable without pushing the canvas below the first viewport")
    if '.explore-tools>summary::before{content:"＋"' not in HTML_CSS or '.explore-tools[open]>summary::before{content:"−"' not in HTML_CSS:
        raise AssertionError("guided story disclosure must expose its open and closed state")
    if '.explore-tools>summary::before{content:"＋"' not in HTML_CSS or '.explore-tools[open]>summary::before{content:"−"' not in HTML_CSS:
        raise AssertionError("guided story disclosure must expose its open and closed state")
    if ".diagram-tools .overview-drawer>summary::before{content:\"＋\"" not in HTML_CSS or "overview-node-decision .overview-marker" not in HTML_CSS:
        raise AssertionError("overview map disclosure and semantic markers must be visible without relying on color alone")
    if "body.presentation section.diagram-tools{display:block!important" not in HTML_CSS or "body.presentation .diagram-tools>:not(#presentation-exit)" not in HTML_CSS:
        raise AssertionError("presentation mode must retain its visible keyboard and pointer exit control")
    if (
        "body.presentation .diagram-pan-hint{display:none!important}" not in HTML_CSS
        or "body.presentation .mobile-diagram-intro{display:block!important;margin:10px 4px 8px;padding-right:148px}" not in HTML_CSS
        or "body.presentation figure svg{margin-top:-124px;min-width:1000px!important}" not in HTML_CSS
        or "body.presentation #presentation-exit{top:16px}" not in HTML_CSS
        or "body.presentation figure svg .header-kicker,body.presentation figure svg .title,body.presentation figure svg .summary,body.presentation figure svg .provenance{display:none!important}" not in HTML_CSS
    ):
        raise AssertionError("mobile presentation must pin its title outside the pannable canvas and keep a clear exit control")
    if "body.presentation figure svg{min-width:0;width:100%!important;height:auto!important}" not in HTML_CSS or "body.presentation figure svg .title,body.presentation figure svg .summary" not in HTML_CSS:
        raise AssertionError("presentation mode must preserve diagram context and scale the full diagram without viewport-height shrinking")
    presentation_script = _viewer_script()
    if (
        'const focusWithoutScroll = (controlId) => requestAnimationFrame' not in presentation_script
        or 'let presentationGeneration = 0;' not in presentation_script
        or 'presentationScrollLeft = figure?.scrollLeft ?? null;' not in presentation_script
        or 'if (figure && scrollLeft !== null) figure.scrollLeft = scrollLeft;' not in presentation_script
        or 'focusWithoutScroll("presentation-exit");' not in presentation_script
        or 'controls("presentation-toggle")?.focus({ preventScroll: true });' not in presentation_script
        or 'generation !== presentationGeneration && !document.body.classList.contains("presentation")' not in presentation_script
        or 'let programmaticFullscreenExit = null;' not in presentation_script
        or 'let presentationScrollProgress = null;' not in presentation_script
        or 'presentationScrollProgress = figure?.scrollWidth' not in presentation_script
        or 'figure.scrollWidth * presentationScrollProgress - figure.clientWidth / 2' not in presentation_script
        or 'const exitFullscreen = () =>' not in presentation_script
        or 'await exitFullscreen();' not in presentation_script
        or 'if (programmaticFullscreenExit) {\n        programmaticFullscreenExit = null;\n        return;\n      }' not in presentation_script
    ):
        raise AssertionError("presentation mode must retain mobile position, return focus, and reconcile fullscreen transitions without stale exit events")
    role_controls = _viewer_controls("en")
    compact_thai_controls = _viewer_controls("th")
    if (
        any(f'id="{control}"' not in role_controls for control in ("role-kind-a", "role-kind-b", "role-compare", "role-compare-clear", "role-comparison-status"))
        or "function roleComparisonDirection(edge)" not in presentation_script
        or "roles\\/([A-Za-z]" not in presentation_script
        or "function roleComparisonHash()" not in presentation_script
        or "preserveCertainty: true" not in presentation_script
        or "if (hash && location.hash.startsWith(\"#roles/\"))" not in presentation_script
        or "return `roles/${encodeURIComponent(roleComparison.from)}/${encodeURIComponent(roleComparison.to)}${suffix}`;" not in presentation_script
        or "clearRoleComparison({ hash: false, apply: false });\n      clearStory({ hash: false, apply: false });\n      params.certainty.value = match[1];" not in presentation_script
        or "role_summary" not in presentation_script
        or "is-role-forward" not in HTML_CSS
        or "is-role-reverse" not in HTML_CSS
    ):
        raise AssertionError("interactive viewers must compare two component kinds, show direct cross-kind direction counts, and restore that view from a deep link")
    if any(label not in compact_thai_controls for label in ("สลับธีม", "สไตล์", "นำเสนอ", "ส่งออก")):
        raise AssertionError("Thai primary controls must use concise labels that fit the mobile toolbar")
    story_spec = _sample_spec("workflow", "Guided workflow")
    story_spec["schema_version"] = 2
    story_spec["views"] = [{"id": "request-path", "label": "Request path", "focus": ["N1", "E1", "N2"], "note": "Follow the authorization check."}]
    normalized_story = validate_spec(story_spec, None)
    story_controls = _viewer_controls("en", normalized_story["views"])
    story_html = _html_document(normalized_story, git_context(None), b'<svg xmlns="http://www.w3.org/2000/svg"><title id="diagram-title">Guided workflow</title></svg>').decode("utf-8")
    if (
        normalized_story["views"] != story_spec["views"]
        or any(f'id="{control}"' not in story_controls for control in ("story-view", "story-start", "story-previous", "story-next", "story-clear", "story-status"))
        or 'name="patpat-viewer-views"' not in story_html
        or "storyStatusText" not in presentation_script
        or "function applyStoryBeat(viewId, beatId" not in presentation_script
        or "story/${encodeURIComponent(view.id)}" not in presentation_script
        or "is-story-beat" not in HTML_CSS
        or "Choose an authored guided view" not in story_controls
        or 'value="request-path"' in story_controls
        or "for (const view of storyViews) option(params.storyView, view.id, view.label);" not in presentation_script
    ):
        raise AssertionError("schema 2 authored story views must render navigable, styled, shareable beats")
    invalid_stories = []
    schema_one_story = _sample_spec("workflow", "Schema one cannot author stories")
    schema_one_story["views"] = story_spec["views"]
    invalid_stories.append(schema_one_story)
    for invalid_view in (
        {"id": "broken", "label": "Unknown element", "focus": ["N404"]},
        {"id": "broken", "label": "Repeated beat", "focus": ["N1", "N1"]},
        {"id": "broken", "label": "Unsupported field", "focus": ["N1"], "script": "ignored"},
    ):
        invalid = json.loads(json.dumps(story_spec))
        invalid["views"] = [invalid_view]
        invalid_stories.append(invalid)
    invalid = json.loads(json.dumps(story_spec))
    invalid["views"] = []
    invalid_stories.append(invalid)
    for invalid in invalid_stories:
        try:
            validate_spec(invalid, None)
        except DiagramError:
            continue
        raise AssertionError("invalid or legacy-authored story views must fail closed")
    link_repository = {"origin": "github.com/owner/repo.git", "revision": "a" * 40}
    link_verification = {
        "status": "verified", "provider": "api.github.com", "repository": "owner/repo",
        "revision": "a" * 40, "checked_at": "2026-10-05T00:00:00Z", "credential_free": True,
    }
    link_evidence = [
        {"id": "S1", "path": "docs/A #1? 100%.md", "start_line": 2, "end_line": 4, "origin": "repository", "snapshot": "committed", "file_sha256": "b" * 64, "committed_file_sha256": "b" * 64},
        {"id": "S2", "path": "working.txt", "start_line": 1, "end_line": 1, "origin": "repository", "snapshot": "working-tree", "file_sha256": "c" * 64, "committed_file_sha256": "d" * 64},
        {"id": "B1", "origin": "brief", "claim": "A user-provided claim", "sha256": "e" * 64},
    ]
    source_permalinks = _github_source_permalinks(link_repository, link_evidence, link_verification)
    if source_permalinks != {"S1": "https://github.com/owner/repo/blob/" + "a" * 40 + "/docs/A%20%231%3F%20100%25.md#L2-L4"}:
        raise AssertionError(f"GitHub links did not encode an immutable committed line range safely: {source_permalinks}")
    if _github_source_permalinks(link_repository, link_evidence, {"status": "unavailable"}):
        raise AssertionError("unverified public source evidence received GitHub links")
    class _IncompleteGithubResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://api.github.com/repos/owner/repo"

        def read(self, _limit):
            raise http.client.IncompleteRead(b'{"private":')

    class _IncompleteGithubOpener:
        def open(self, _request, timeout):
            if timeout != 5:
                raise AssertionError("public source verification changed its bounded request timeout")
            return _IncompleteGithubResponse()

    original_build_opener = urllib.request.build_opener
    try:
        urllib.request.build_opener = lambda *_handlers: _IncompleteGithubOpener()
        truncated_verification = _verify_public_github_source(link_repository, link_evidence)
    finally:
        urllib.request.build_opener = original_build_opener
    if truncated_verification.get("status") != "unavailable" or truncated_verification.get("reason") != "anonymous-verification-failed":
        raise AssertionError("truncated GitHub API responses must fail closed without aborting diagram finalization")
    if _github_source_permalinks({**link_repository, "origin": "github.com.evil/owner/repo"}, link_evidence, link_verification):
        raise AssertionError("a lookalike GitHub hostname received source links")
    linked_spec = validate_spec(_sample_spec("architecture", "Linked evidence"), None)
    linked_spec["snapshots"] = {"S1": {**link_evidence[0], "claim": "A committed repository claim", "sha256": "f" * 64}}
    linked_svg = _svg_document(linked_spec, {"name": "repo", "revision": "a" * 40, "dirty": False, "changed_paths": [], "origin": "github.com/owner/repo"}, _make_layout(linked_spec))
    linked_html = _html_document(linked_spec, {"name": "repo", "revision": "a" * 40, "dirty": False, "changed_paths": [], "origin": "github.com/owner/repo"}, linked_svg, source_permalinks)
    _valid_html_and_svg(linked_html, linked_svg, source_permalinks)
    tampered_link_html = linked_html.replace(source_permalinks["S1"].encode("utf-8"), b"https://github.com.evil/owner/repo/blob/" + b"a" * 40 + b"/docs/A%20%231%3F%20100%25.md#L2-L4")
    try:
        _valid_html_and_svg(tampered_link_html, linked_svg, source_permalinks)
    except DiagramError:
        pass
    else:
        raise AssertionError("HTML with a source link outside the receipt allowlist was accepted")
    for warning in (
        "edge endpoint outside node port: E1/N1",
        "edge crosses diagram header: E1",
        "edge label overlaps diagram header: E1",
        "boundary outside canvas: B1",
        "edge route reenters hinted endpoint: E1/N1/segment:1",
        "edge route overlaps relationship label: E1/E2/segment:0",
    ):
        if not _has_blocking_geometry_warnings([warning]):
            raise AssertionError(f"geometry warning must block finalization by itself: {warning}")
    if not _segment_intersections((0, 0), (10, 10), (0, 10), (10, 0)):
        raise AssertionError("diagonal edge intersections are not detected")
    if _segment_intersections((0, 0), (5, 5), (6, 6), (10, 10)):
        raise AssertionError("disjoint collinear edges were treated as crossing")
    if not _segment_crosses_rect((0, 0), (10, 10), {"x": 4, "y": 4, "w": 2, "h": 2}):
        raise AssertionError("diagonal edge collision with a node was not detected")
    dense_spacing = _centered_port_spacing(62.0, 18)
    if dense_spacing * 8.5 > 23.0 or _centered_port_spacing(62.0, 18) >= 4.0:
        raise AssertionError("dense relationship fan-in must remain inside a bounded node port span")
    if _segment_crosses_rect((0, 0), (4, 4), {"x": 4, "y": 0, "w": 2, "h": 4}):
        raise AssertionError("edge tangent to a node boundary was treated as an interior collision")
    label_route_warnings = _geometry_warnings(
        {},
        [
            {"edge": {"id": "E1", "source": "N1", "target": "N2"}, "points": [(100, 100), (300, 100)]},
            {"edge": {"id": "E2", "source": "N3", "target": "N4"}, "points": [(200, 110), (200, 150)]},
        ],
        [{"id": "E1", "x": 200, "y": 130, "w": 100, "h": 20}],
        [], 400, 700,
    )
    if not any(item.startswith("edge route overlaps relationship label: E1/E2/segment:0") for item in label_route_warnings):
        raise AssertionError(f"a foreign route passing behind a relationship label was missed: {label_route_warnings}")
    collision_warning = next(item for item in label_route_warnings if item.startswith("edge route overlaps relationship label:"))
    collision_diagnostic = _stable_diagnostic(
        DiagramError("layout has blocking geometry warnings: " + collision_warning), "finalize"
    )
    expected_measurement = {
        "distance_svg": 0.0,
        "required_clearance_svg": 2.0,
        "label_bounds_svg": {"x": 150.0, "y": 120.0, "w": 100.0, "h": 20.0},
        "segment_svg": {"from": [200.0, 110.0], "to": [200.0, 150.0]},
    }
    if collision_diagnostic.get("measurement") != expected_measurement:
        raise AssertionError(f"label-route diagnostics omitted exact collision geometry: {collision_diagnostic}")
    near_clearance = _geometry_warnings(
        {},
        [{"edge": {"id": "E2", "source": "N3", "target": "N4"}, "points": [(200, 100), (200, 119.5)]}],
        [{"id": "E1", "x": 200, "y": 130, "w": 100, "h": 20}],
        [], 400, 700,
    )
    near_warning = next((item for item in near_clearance if item.startswith("edge route overlaps relationship label:")), None)
    if near_warning is None:
        raise AssertionError("a route closer than the required label clearance was missed")
    near_diagnostic = _stable_diagnostic(DiagramError("layout has blocking geometry warnings: " + near_warning), "validate")
    if near_diagnostic.get("measurement", {}).get("distance_svg") != 0.5:
        raise AssertionError(f"near-clearance diagnostic did not report its measured distance: {near_diagnostic}")
    threshold_clearance = _geometry_warnings(
        {},
        [{"edge": {"id": "E2", "source": "N3", "target": "N4"}, "points": [(200, 100), (200, 118)]}],
        [{"id": "E1", "x": 200, "y": 130, "w": 100, "h": 20}],
        [], 400, 700,
    )
    if any(item.startswith("edge route overlaps relationship label:") for item in threshold_clearance):
        raise AssertionError(f"a route exactly at the required label clearance was rejected: {threshold_clearance}")
    near_corner_clearance = _geometry_warnings(
        {},
        [{"edge": {"id": "E2", "source": "N3", "target": "N4"}, "points": [(148.5, 118.5), (148.9, 118.9)]}],
        [{"id": "E1", "x": 200, "y": 130, "w": 100, "h": 20}],
        [], 400, 700,
    )
    near_corner_warning = next((item for item in near_corner_clearance if item.startswith("edge route overlaps relationship label:")), None)
    if near_corner_warning is None:
        raise AssertionError("a diagonal route closer than the Euclidean corner clearance was missed")
    near_corner_measurement = _stable_diagnostic(
        DiagramError("layout has blocking geometry warnings: " + near_corner_warning), "validate"
    ).get("measurement", {})
    if abs(near_corner_measurement.get("distance_svg", math.inf) - math.sqrt(2.42)) > 1e-5:
        raise AssertionError(f"diagonal corner clearance did not report its Euclidean distance: {near_corner_measurement}")
    far_corner_clearance = _geometry_warnings(
        {},
        [{"edge": {"id": "E2", "source": "N3", "target": "N4"}, "points": [(148.1, 118.1), (148.5, 118.5)]}],
        [{"id": "E1", "x": 200, "y": 130, "w": 100, "h": 20}],
        [], 400, 700,
    )
    if any(item.startswith("edge route overlaps relationship label:") for item in far_corner_clearance):
        raise AssertionError(f"a diagonal route beyond the Euclidean clearance was falsely blocked: {far_corner_clearance}")
    owner_label_warnings = _geometry_warnings(
        {},
        [{"edge": {"id": "E1", "source": "N1", "target": "N2"}, "points": [(100, 100), (300, 100)]}],
        [{"id": "E1", "x": 200, "y": 100, "w": 100, "h": 20}],
        [], 400, 700,
    )
    if any(warning.startswith("edge route overlaps relationship label:") for warning in owner_label_warnings):
        raise AssertionError("a relationship label was incorrectly rejected for resting on its own route")
    for message, expected_code in (
        ("layout has blocking geometry warnings: edge route overlaps relationship label: E1/E2/segment:0", "layout.label-route-clearance"),
        ("layout has blocking geometry warnings: edge route reenters hinted endpoint: E1/N1/segment:1", "layout.port-side"),
        ("layout has blocking geometry warnings: edge route overlaps relationship label: E1/BrowserEdge/segment:0", "layout.label-route-clearance"),
        ("layout has blocking geometry warnings: edge route reenters hinted endpoint: EvidenceEdge/N1/segment:1", "layout.port-side"),
    ):
        diagnostic = _stable_diagnostic(DiagramError(message), "finalize")
        expected_subject = "EvidenceEdge" if "EvidenceEdge" in message else "E1"
        if diagnostic["code"] != expected_code or diagnostic["subject"] != expected_subject:
            raise AssertionError(f"geometry diagnostics lost their stable rule or subject: {diagnostic}")
    capsule = ET.Element(_tag("g"))
    _draw_graph_node(capsule, {"id": "START", "label": "Start", "kind": "start", "certainty": "confirmed", "evidence_ids": [], "reason": ""},
                     {"x": 100.0, "y": 20.0, "w": 188.0, "h": 66.0, "lines": ["Start"]})
    capsule_group = capsule.find(_tag("g"))
    capsule_texts = capsule_group.findall(_tag("text")) if capsule_group is not None else []
    if len(capsule_texts) < 2 or float(capsule_texts[0].attrib["x"]) < 125 or float(capsule_texts[1].attrib["x"]) > 263:
        raise AssertionError("start and terminal metadata must stay inside rounded capsule shapes")
    for step in ZOOM_CSS_STEPS:
        rule = f'figure[data-zoom="{step}"] svg{{width:max({step}%,{step * 7}px);min-width:0}}'
        if rule not in HTML_CSS:
            raise AssertionError(f"zoom {step}% has no responsive sizing rule")
    with tempfile.TemporaryDirectory(prefix="patpat-diagram-self-test-") as temp_name:
        root = Path(temp_name) / "repo"
        root.mkdir()
        (root / "source.txt").write_text("line one\nline two\nline three\n", encoding="utf-8")
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "core.autocrlf", "false"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Patpat Test", "-c", "user.email=patpat-test@example.invalid", "commit", "--quiet", "-m", "fixture"], check=True)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "https://user:secret@example.invalid/owner/repo.git?token=secret"], check=True)
        specs_dir = root.parent / "specs"
        specs_dir.mkdir()
        oversized_path = specs_dir / "oversized.json"
        oversized_path.write_bytes(b" " * (MAX_SOURCE_JSON_BYTES + 1))
        try:
            load_json(oversized_path)
        except DiagramError as error:
            if "1 MB" not in str(error):
                raise AssertionError("oversized JSON input did not report the source limit") from error
        else:
            raise AssertionError("oversized JSON input was read and parsed past the byte limit")
        outputs_dir = root.parent / "outputs"
        outputs_dir.mkdir()
        _assert_windows_output_lock_retry()
        _assert_cross_process_output_lock(outputs_dir / "cross-process-lock")
        _assert_same_output_serialization(outputs_dir)
        _assert_browser_artifact_collection(outputs_dir / "browser-collection")
        expected = {"architecture", "workflow", "sequence", "dataflow", "lifecycle"}
        authored_geometry = _sample_spec("architecture", "Authored geometry contract")
        authored_geometry["layout"] = {
            "direction": "LR",
            "layers": [["N1"], ["N2"], ["N3"]],
            "positions": {
                "N1": {"x": 86, "y": 500},
                "N2": {"x": 380, "y": 500},
                "N3": {"x": 700, "y": 700},
            },
            "edge_hints": {
                "E1": {
                    "source_side": "right",
                    "target_side": "left",
                    "waypoints": [{"x": 300, "y": 420}],
                    "label": {"segment": 1, "offset": {"x": 0, "y": -14}},
                },
            },
        }
        authored_geometry_spec = validate_spec(authored_geometry, root)
        legacy_geometry = _make_layout(validate_spec(_sample_spec("architecture", "Automatic geometry"), root))
        authored_geometry_layout = _make_layout(authored_geometry_spec)
        for identifier, point in authored_geometry["layout"]["positions"].items():
            actual = authored_geometry_layout["positions"][identifier]
            if (actual["x"], actual["y"]) != (point["x"], point["y"]):
                raise AssertionError(f"authored node position was not preserved for {identifier}: {actual}")
        hinted_route = next(path for path in authored_geometry_layout["paths"] if path["edge"]["id"] == "E1")
        source_rect = authored_geometry_layout["positions"]["N1"]
        target_rect = authored_geometry_layout["positions"]["N2"]
        expected_route = [
            (source_rect["x"] + source_rect["w"], source_rect["y"] + source_rect["h"] / 2),
            (source_rect["x"] + source_rect["w"] + 12.0, source_rect["y"] + source_rect["h"] / 2),
            (300.0, 420.0),
            (target_rect["x"] - 12.0, target_rect["y"] + target_rect["h"] / 2),
            (target_rect["x"], target_rect["y"] + target_rect["h"] / 2),
        ]
        if hinted_route["points"] != expected_route or authored_geometry_layout["warnings"]:
            raise AssertionError(f"authored edge route did not render cleanly: {hinted_route['points']} {authored_geometry_layout['warnings']}")
        hinted_label = next(label for label in authored_geometry_layout["labels"] if label["id"] == "E1")
        expected_label = ((expected_route[1][0] + expected_route[2][0]) / 2, (expected_route[1][1] + expected_route[2][1]) / 2 - 14.0)
        if (hinted_label["x"], hinted_label["y"]) != expected_label:
            raise AssertionError(f"authored edge label did not follow its selected segment: {hinted_label}")
        auto_label_geometry = json.loads(json.dumps(authored_geometry))
        auto_label_geometry["layout"]["edge_hints"]["E1"].pop("label")
        auto_label_spec = validate_spec(auto_label_geometry, root)
        auto_label_layout = _make_layout(auto_label_spec)
        auto_label_route = next(path for path in auto_label_layout["paths"] if path["edge"]["id"] == "E1")["points"]
        auto_label = next(label for label in auto_label_layout["labels"] if label["id"] == "E1")
        auto_label_segment = max(
            range(len(auto_label_route) - 1),
            key=lambda index: math.hypot(
                auto_label_route[index + 1][0] - auto_label_route[index][0],
                auto_label_route[index + 1][1] - auto_label_route[index][1],
            ),
        )
        auto_first, auto_second = auto_label_route[auto_label_segment : auto_label_segment + 2]
        if (auto_label["x"], auto_label["y"]) != (
            (auto_first[0] + auto_second[0]) / 2,
            (auto_first[1] + auto_second[1]) / 2,
        ):
            raise AssertionError("automatic relationship labels must follow a changed authored route")
        if auto_label_layout["warnings"]:
            raise AssertionError(f"automatic label placement on an authored route caused geometry warnings: {auto_label_layout['warnings']}")
        if legacy_geometry["warnings"] or len(legacy_geometry["positions"]) != 3:
            raise AssertionError("legacy automatic architecture layout changed under the optional geometry contract")
        direction_mismatch = _sample_spec("architecture", "Authored rank direction")
        direction_mismatch["layout"] = {
            "direction": "TB",
            "layers": [["N1"], ["N2"], ["N3"]],
            "positions": {
                "N1": {"x": 250, "y": 700},
                "N2": {"x": 250, "y": 450},
                "N3": {"x": 250, "y": 1000},
            },
        }
        direction_warnings = _make_layout(validate_spec(direction_mismatch, root))["warnings"]
        if not any(warning.startswith("node layer order:") for warning in direction_warnings):
            raise AssertionError(f"authored positions reversed TB layer progression without a blocking diagnostic: {direction_warnings}")
        reading_mismatch = _sample_spec("architecture", "Authored peer reading order")
        reading_mismatch["body"]["relationships"] = reading_mismatch["body"]["relationships"][:1]
        reading_mismatch["layout"] = {
            "direction": "TB",
            "layers": [["N1"], ["N2", "N3"]],
            "positions": {
                "N1": {"x": 450, "y": 240},
                "N2": {"x": 720, "y": 500},
                "N3": {"x": 340, "y": 500},
            },
        }
        reading_warnings = _make_layout(validate_spec(reading_mismatch, root))["warnings"]
        if not any(warning.startswith("node layer reading order:") for warning in reading_warnings):
            raise AssertionError(f"authored positions contradicted TB peer reading order without a blocking diagnostic: {reading_warnings}")
        self_crossing_path = {
            "edge": {"id": "E1", "source": "N1", "target": "N2"},
            "points": [(100, 100), (300, 100), (300, 300), (100, 300), (300, 100)],
        }
        self_crossing_warnings = _geometry_warnings({}, [self_crossing_path], [], [], 400, 400)
        if not any(warning.startswith("edge self-crossing: E1") for warning in self_crossing_warnings):
            raise AssertionError(f"a relationship route crossing itself was not diagnosed: {self_crossing_warnings}")
        if not _has_blocking_geometry_warnings(self_crossing_warnings):
            raise AssertionError("a relationship route crossing itself must block finalization")
        for diagram_type in ("workflow", "dataflow", "lifecycle"):
            graph_geometry = _sample_spec(diagram_type, f"Authored {diagram_type} geometry")
            entity_key = {"workflow": "steps", "dataflow": "entities", "lifecycle": "states"}[diagram_type]
            graph_positions = {
                item["id"]: {"x": 86 + index * 280, "y": 500 + index * 80}
                for index, item in enumerate(graph_geometry["body"][entity_key])
            }
            graph_geometry["layout"] = {
                "direction": "LR",
                "positions": graph_positions,
            }
            graph_layout = _make_layout(validate_spec(graph_geometry, root))
            if graph_layout["positions"]["N1"]["x"] != 86.0:
                raise AssertionError(f"{diagram_type} did not preserve its authored graph positions")
        invalid_graph_route = _sample_spec("workflow", "Invalid hinted endpoint")
        invalid_graph_positions = {
            item["id"]: {"x": 86 + index * 280, "y": 500 + index * 80}
            for index, item in enumerate(invalid_graph_route["body"]["steps"])
        }
        invalid_graph_route["layout"] = {
            "positions": invalid_graph_positions,
            "edge_hints": {"E1": {"source_side": "right", "target_side": "left", "waypoints": [{"x": 200, "y": 531}] }},
        }
        invalid_graph_layout = _make_layout(validate_spec(invalid_graph_route, root))
        if "edge route reenters hinted endpoint: E1/N1/segment:1" not in invalid_graph_layout["warnings"]:
            raise AssertionError(f"a route that reenters a hinted source node was accepted: {invalid_graph_layout['warnings']}")
        header_crossing_geometry = json.loads(json.dumps(authored_geometry))
        header_crossing_geometry["layout"]["edge_hints"]["E1"]["waypoints"] = [{"x": 100, "y": 0}]
        header_crossing_layout = _make_layout(validate_spec(header_crossing_geometry, root))
        if "edge crosses diagram header: E1" not in header_crossing_layout["warnings"]:
            raise AssertionError("an authored route crossing the shared header was not diagnosed")
        boundary_geometry = json.loads(json.dumps(authored_geometry))
        boundary_geometry["layout"]["positions"]["N1"]["x"] = 0
        boundary_geometry["body"]["boundaries"] = [{
            "id": "B1", "label": "Client boundary", "component_ids": ["N1"],
            "certainty": "confirmed", "evidence_ids": ["S1"],
        }]
        boundary_layout = _make_layout(validate_spec(boundary_geometry, root))
        if "boundary outside canvas: B1" not in boundary_layout["warnings"]:
            raise AssertionError("an authored boundary clipped beyond the canvas was not diagnosed")
        invalid_geometry = json.loads(json.dumps(authored_geometry))
        invalid_geometry["layout"]["positions"].pop("N3")
        try:
            validate_spec(invalid_geometry, root)
        except DiagramError as error:
            if "cover every graph entity" not in str(error):
                raise
        else:
            raise AssertionError("partial authored positions were accepted")
        invalid_geometry = json.loads(json.dumps(authored_geometry))
        invalid_geometry["layout"]["positions"]["N1"]["x"] = float("nan")
        try:
            validate_spec(invalid_geometry, root)
        except DiagramError as error:
            if "finite number" not in str(error):
                raise
        else:
            raise AssertionError("non-finite authored coordinates were accepted")
        invalid_geometry = json.loads(json.dumps(authored_geometry))
        invalid_geometry["layout"]["edge_hints"]["MISSING"] = {"waypoints": [{"x": 240, "y": 420}]}
        try:
            validate_spec(invalid_geometry, root)
        except DiagramError as error:
            if "unknown relationship" not in str(error):
                raise
        else:
            raise AssertionError("an edge hint referencing an unknown relationship was accepted")
        invalid_geometry = json.loads(json.dumps(authored_geometry))
        invalid_geometry["layout"]["edge_hints"]["E1"]["label"]["segment"] = 12
        try:
            _make_layout(validate_spec(invalid_geometry, root))
        except DiagramError as error:
            if "outside the authored route" not in str(error):
                raise
        else:
            raise AssertionError("an edge label hint outside its route was accepted")
        geometry_path = specs_dir / "authored-geometry.json"
        geometry_path.write_text(json.dumps(authored_geometry, ensure_ascii=False), encoding="utf-8")
        geometry_output = _render(geometry_path, root, outputs_dir, "authored-geometry", False)
        checked_geometry = _check(outputs_dir / "authored-geometry.html", root)
        if checked_geometry["status"] != "passed" or geometry_output["receipt"]["layout"]["warnings"]:
            raise AssertionError("authored geometry did not survive finalization and receipt validation")
        overlapping_geometry = json.loads(json.dumps(authored_geometry))
        overlapping_geometry["layout"]["positions"]["N3"] = dict(overlapping_geometry["layout"]["positions"]["N2"])
        overlapping_path = specs_dir / "overlapping-geometry.json"
        overlapping_path.write_text(json.dumps(overlapping_geometry, ensure_ascii=False), encoding="utf-8")
        try:
            _render(overlapping_path, root, outputs_dir, "overlapping-geometry", False)
        except DiagramError as error:
            if "node overlap:" not in str(error):
                raise
        else:
            raise AssertionError("finalization accepted overlapping authored components")
        if any((outputs_dir / f"overlapping-geometry.{suffix}").exists() for suffix in ("diagram.json", "svg", "html", "receipt.json")):
            raise AssertionError("failed authored geometry left a partial artifact set")
        invalid_workflows = []
        one_exit = _sample_spec("workflow", "Decision needs two outcomes")
        one_exit["body"]["transitions"] = [edge for edge in one_exit["body"]["transitions"] if edge["id"] != "E3"]
        invalid_workflows.append((one_exit, "decision step N2 must have at least two outgoing transitions"))
        terminal_exit = _sample_spec("workflow", "Terminal cannot continue")
        terminal_exit["body"]["transitions"].append({
            "id": "E6", "source": "N5", "target": "N2", "label": "continue after terminal", "kind": "retry",
            "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        invalid_workflows.append((terminal_exit, "terminal step N5 cannot have outgoing transitions"))
        dead_end = _sample_spec("workflow", "Every path needs an outcome")
        dead_end["body"]["steps"].append({
            "id": "N6", "label": "Unfinished side path", "kind": "action", "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        dead_end["body"]["transitions"].append({
            "id": "E6", "source": "N1", "target": "N6", "label": "side path", "kind": "next",
            "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        invalid_workflows.append((dead_end, "workflow step N6 cannot reach a terminal step"))
        for invalid_workflow, expected_error in invalid_workflows:
            try:
                validate_spec(invalid_workflow, root)
            except DiagramError as error:
                if expected_error not in str(error):
                    raise AssertionError(f"invalid workflow failed for the wrong reason: expected {expected_error!r}, got {error}") from error
            else:
                raise AssertionError(f"invalid workflow was accepted without enforcing {expected_error}")
        for diagram_type in sorted(expected):
            raw = _sample_spec(diagram_type, "A <safe> </title><script>alert(1)</script> & readable diagram")
            if diagram_type == "workflow":
                raw.update({"language": "th", "title": "ตรวจสิทธิ์ <safe> </title><script>alert(1)</script> & คืนผลลัพธ์", "summary": "แผนภาพคำขอที่ตรวจหลักฐานจาก source แล้ว"})
                raw["body"]["steps"][0]["label"] = "รับคำขอ"
                raw["body"]["steps"][1]["label"] = "ตรวจสิทธิ์"
                raw["body"]["steps"][2]["label"] = "ประมวลผลคำขอ"
                raw["body"]["steps"][3]["label"] = "ปฏิเสธคำขอ"
                raw["body"]["steps"][4]["label"] = "ส่งผลลัพธ์"
                raw["body"]["transitions"][0]["label"] = "ดำเนินต่อ"
                raw["body"]["transitions"][1]["label"] = "อนุญาต"
                raw["body"]["transitions"][2]["label"] = "ปฏิเสธ"
                raw["body"]["transitions"][3]["label"] = "ประมวลผลแล้ว"
                raw["body"]["transitions"][4]["label"] = "ปฏิเสธแล้ว"
                raw["layout"] = {"direction": "TB", "layers": [["N1"], ["N2"], ["N3", "N4"], ["N5"]]}
            if diagram_type == "sequence":
                long_label = "persist request metadata using the validated scope and normalized owner fields"
                raw["body"]["messages"][0]["label"] = long_label
            spec = validate_spec(raw, root)
            layout = _make_layout(spec)
            if diagram_type == "sequence":
                if " ".join(layout["labels"][0]["lines"]) != long_label or "…" in "".join(layout["labels"][0]["lines"]):
                    raise AssertionError("a long sequence label was silently truncated")
            git = {"name": "fixture", "revision": "0123456789abcdef", "dirty": False}
            svg = _svg_document(spec, git, layout)
            if "✓" in svg.decode("utf-8"):
                raise AssertionError("confirmed evidence must not be decorated as a passed or completed state")
            if diagram_type == "architecture":
                mixed_certainty = _sample_spec("architecture", "Certainty markers")
                mixed_certainty["body"]["components"][0]["certainty"] = "inferred"
                mixed_certainty["body"]["components"][1].update(certainty="unknown", evidence_ids=[], reason="Ownership is not visible in this source slice")
                mixed_spec = validate_spec(mixed_certainty, root)
                mixed_svg = _svg_document(mixed_spec, git, _make_layout(mixed_spec))
                marks = [
                    item.text for item in ET.fromstring(mixed_svg).iter()
                    if "certainty-mark" in item.attrib.get("class", "")
                ]
                if "~" not in marks or "?" not in marks or "✓" in marks:
                    raise AssertionError(f"inferred and unknown evidence must remain distinct from confirmed claims: {marks}")
            if diagram_type == "workflow" and (b"edge-affirmative" not in svg or b"edge-alternative" not in svg):
                raise AssertionError("workflow outcomes must have distinct semantic line treatments")
            if diagram_type == "workflow" and any(
                len(path["points"]) != 2 for path in layout["paths"] if path["edge"]["id"] in {"E2", "E3", "E4", "E5"}
            ):
                raise AssertionError("top-down branch and merge edges must use direct non-crossing routes")
            document = _html_document(spec, git, svg)
            _valid_html_and_svg(document, svg)
            if layout["warnings"]:
                raise AssertionError(f"{diagram_type} layout warnings: {layout['warnings']}")
            text = document.decode("utf-8")
            if "<script" in text.lower() or "<safe>" in text or "&lt;safe&gt;" not in text:
                raise AssertionError(f"{diagram_type} did not safely encode source text")
            if diagram_type == "workflow" and ('<html lang="th">' not in text or "รายละเอียดแบบข้อความ" not in text or "สถานะหลักฐาน" not in text):
                raise AssertionError("Thai UI labels or language metadata were not rendered")
            source_path = specs_dir / f"{diagram_type}.json"
            source_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            output = _render(source_path, root, outputs_dir, diagram_type, False)
            result = _check(outputs_dir / f"{diagram_type}.html", root)
            if result["diagram_type"] != diagram_type or output["receipt"]["layout"]["warnings"]:
                raise AssertionError(f"{diagram_type} output did not pass its receipt check")
            if "<script" in (outputs_dir / f"{diagram_type}.html").read_text(encoding="utf-8").lower():
                raise AssertionError("schema v1 unexpectedly enabled executable viewer code")
            try:
                _render(source_path, root, outputs_dir, diagram_type, False)
            except DiagramError:
                pass
            else:
                raise AssertionError(f"{diagram_type} unexpectedly overwrote an existing artifact")
        if git_context(None)["revision"] is not None:
            raise AssertionError("brief-only diagrams unexpectedly acquired Git provenance")
        if _projected_readability({"width": 5000})["passed"]:
            raise AssertionError("the desktop text readability floor accepted an over-wide canvas")
        brief_outputs = root.parent / "brief-outputs"
        brief_outputs.mkdir()
        for diagram_type in sorted(expected):
            raw = _sample_spec(diagram_type, f"Interactive {diagram_type} from a brief")
            raw["schema_version"] = 2
            raw["summary"] = "A user-provided description, converted into an interactive visual"
            raw["evidence"] = [{
                "id": "B1",
                "origin": "brief",
                "claim": "The user describes a browser request reaching a service and returning a result.",
            }]
            for values in raw["body"].values():
                if isinstance(values, list):
                    for entry in values:
                        if isinstance(entry, dict) and "evidence_ids" in entry:
                            entry["evidence_ids"] = ["B1"]
            brief_spec = validate_spec(raw, None, require_repository_sources=True)
            if brief_spec["snapshots"]["B1"]["origin"] != "brief":
                raise AssertionError("brief evidence did not retain its declared origin")
            brief_path = specs_dir / f"brief-{diagram_type}.json"
            brief_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            brief_result = _render(brief_path, None, brief_outputs, f"brief-{diagram_type}", False)
            checked_brief = _check(brief_outputs / f"brief-{diagram_type}.html")
            if checked_brief["status"] != "passed" or brief_result["receipt"]["repository"]["revision"] is not None:
                raise AssertionError(f"{diagram_type} brief-only output required Git provenance")
            brief_html = (brief_outputs / f"brief-{diagram_type}.html").read_text(encoding="utf-8")
            if "NOT CODE-VERIFIED" not in brief_html or 'data-theme="dark"' not in brief_html or 'class="primary-toolbar"' not in brief_html:
                raise AssertionError("brief artifact did not disclose its evidence origin or render the primary viewer")
        try:
            validate_spec(_sample_spec("architecture", "Repository source needs a root"), None, require_repository_sources=True)
        except DiagramError as error:
            if "--repo-root" not in str(error):
                raise
        else:
            raise AssertionError("repository evidence was accepted without a Git root")
        if git_context(root)["origin"] != "example.invalid/owner/repo.git":
            raise AssertionError("repository provenance did not strip credentials and query values from origin")
        preview_host = "127.0.0.1:43127"
        showcase_outputs = _transaction_names("browser-showcase", "review")
        if len(showcase_outputs) != 8 or "review.browser.png" not in showcase_outputs or "review.showcase-contact.svg" not in showcase_outputs:
            raise AssertionError("showcase capture transaction does not whitelist its complete output set")
        capture_records = []
        capture_images = {}
        for view, viewport in {"desktop": [1440, 1100], "tablet": [1024, 768], "mobile": [390, 844]}.items():
            for theme in ("light", "dark"):
                key = f"{view}-{theme}"
                capture_images[key] = b"test-png"
                capture_records.append({"viewport_name": view, "viewport": viewport, "theme": theme})
        contact_sheet = ET.fromstring(_browser_contact_sheet(capture_records, capture_images))
        if len(contact_sheet.findall("{http://www.w3.org/2000/svg}image")) != 6:
            raise AssertionError("showcase contact sheet omitted a viewport/theme capture")
        if _preview_route("/status", preview_host, preview_host, "demo") != (200, "/status"):
            raise AssertionError("preview did not accept its exact loopback host and status route")
        if _preview_route("/demo.html?patpat-preview=1", preview_host, preview_host, "demo") != (200, "/demo.html"):
            raise AssertionError("preview mode URL did not resolve to its exact artifact route")
        if _preview_route("/demo.html", "attacker.example:43127", preview_host, "demo")[0] != 403:
            raise AssertionError("preview accepted a foreign Host header")
        if _preview_route("http://127.0.0.1:43127/demo.html", preview_host, preview_host, "demo")[0] != 404:
            raise AssertionError("preview accepted an absolute-form request target")
        committed = _sample_spec("architecture", "Interactive viewer")
        committed["schema_version"] = 2
        committed["body"]["boundaries"] = [{
            "id": "B1", "label": "Application boundary", "component_ids": ["N1", "N2", "N3"],
            "certainty": "confirmed", "evidence_ids": ["S1"],
        }]
        committed["layout"] = {"direction": "LR", "layers": [["N1"], ["N2"], ["N3"]]}
        committed["profile"] = {"type": "deployment-ownership"}
        if validate_spec(committed, root)["snapshots"]["S1"]["snapshot"] != "committed":
            raise AssertionError("committed evidence was not identified as committed bytes")
        original_head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        replacement_path = root / "source.txt"
        replacement_path.write_text("replacement one\nreplacement two\nreplacement three\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Patpat Test", "-c", "user.email=patpat-test@example.invalid", "commit", "--quiet", "-m", "replacement fixture"], check=True)
        replacement_head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(root), "reset", "--hard", "--quiet", original_head], check=True)
        subprocess.run(["git", "-C", str(root), "replace", original_head, replacement_head], check=True)
        try:
            replacement_snapshot = validate_spec(committed, root)["snapshots"]["S1"]
            if replacement_snapshot["snapshot"] != "committed" or replacement_snapshot["file_sha256"] != replacement_snapshot["committed_file_sha256"]:
                raise AssertionError("local replacement refs changed the committed source snapshot identity")
        finally:
            subprocess.run(["git", "-C", str(root), "replace", "-d", original_head], check=True, capture_output=True)
        if hashlib.sha256(replacement_path.read_bytes()).hexdigest() != replacement_snapshot["file_sha256"]:
            raise AssertionError("replacement-ref verification modified the checked-out source")
        interactive_path = specs_dir / "interactive.json"
        interactive_path.write_text(json.dumps(committed), encoding="utf-8")
        interactive = _render(interactive_path, root, outputs_dir, "interactive", False)
        interactive_html = outputs_dir / "interactive.html"
        interactive_svg = outputs_dir / "interactive.svg"
        _check(interactive_html, root)

        original_browser_check = _browser_check

        def fixture_browser_check(
            html_path: Path,
            _repo_root: Path | None,
            screenshot_path: Path,
            _browser: str | None,
            receipt_path: Path,
            profile: str,
        ) -> dict[str, str]:
            screenshot_bytes = b"browser-gate fixture screenshot"
            receipt_bytes = (
                json.dumps({"html_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(), "profile": profile}) + "\n"
            ).encode("utf-8")
            _atomic_set(
                screenshot_path.parent,
                {screenshot_path.name: screenshot_bytes, receipt_path.name: receipt_bytes},
                False,
                "browser",
                screenshot_path.name.removesuffix(".browser.png"),
            )
            return {"status": "passed", "profile": profile}

        _browser_check = fixture_browser_check
        try:
            finalized_dir = outputs_dir / "mocked-browser-finalize"
            finalized = _finalize(
                interactive_path,
                root,
                finalized_dir,
                "mocked-browser-finalize",
                False,
                None,
                "standard",
            )
        finally:
            _browser_check = original_browser_check
        finalized_expected = _transaction_names("finalize", "mocked-browser-finalize")
        finalized_disk = {path.name for path in finalized_dir.iterdir() if path.name != OUTPUT_LOCK_NAME}
        if set(finalized["files"]) != finalized_expected or finalized_disk != finalized_expected:
            raise AssertionError("browser-gated finalization published lock metadata or omitted a declared artifact")
        if not (finalized_dir / OUTPUT_LOCK_NAME).is_file():
            raise AssertionError("browser-gated finalization did not retain its output coordination file")
        if finalized["browser"].get("status") != "passed":
            raise AssertionError("browser-gated finalization lost its browser quality result")
        interactive_text = interactive_html.read_text(encoding="utf-8")
        if 'new URLSearchParams(location.search).get("patpat-preview") === "1"' not in interactive_text:
            raise AssertionError("viewer preview polling is not gated by the explicit Patpat preview URL")
        if (
            ".table-wrap>.alt-table,.table-wrap>.evidence-table{min-width:680px}" not in HTML_CSS
            or ".table-wrap caption{text-align:left" not in HTML_CSS
        ):
            raise AssertionError("text outline tables must preserve readable columns inside their own scroll area")
        if 'class="table-wrap" role="region" tabindex="0"' not in interactive_text:
            raise AssertionError("scrollable text tables must be keyboard reachable named regions")
        if 'data-export="webm"' not in interactive_text or 'data-export="png-copy"' not in interactive_text:
            raise AssertionError("schema v2 did not include the trusted interactive export controls")
        if (
            'role="listbox"' not in interactive_text
            or 'aria-autocomplete="list"' not in interactive_text
            or 'data-depth-mode="auto"' not in interactive_text
            or 'data-export="svg-auto"' not in interactive_text
        ):
            raise AssertionError("schema v2 omitted its navigable finder, automatic depth, or adaptive SVG action")
        if (
            'id="visual-preset"' not in interactive_text
            or 'aria-keyshortcuts="S"' not in interactive_text
            or 'data-visual-preset="balanced"' not in interactive_text
            or 'figure svg .is-muted,figure svg .is-highlighted' not in interactive_text
            or 'visibility:visible!important' not in interactive_text
        ):
            raise AssertionError("schema v2 omitted visual presets or full-state print recovery")
        if "script-src &#x27;sha256-" not in interactive_text or "connect-src &#x27;self&#x27;" not in interactive_text:
            raise AssertionError("schema v2 did not emit its restrictive hash-bound content security policy")
        try:
            _valid_html_and_svg(interactive_text.replace("textContent", "innerHTML", 1).encode("utf-8"), interactive_svg.read_bytes())
        except DiagramError:
            pass
        else:
            raise AssertionError("modified viewer code passed trusted-script validation")
        refresh_html = interactive_text.replace(
            "</head>",
            '<meta http-equiv="refresh" content="0;url=http://127.0.0.1:9/"></head>',
            1,
        ).encode("utf-8")
        try:
            _valid_html_and_svg(refresh_html, interactive_svg.read_bytes())
        except DiagramError:
            pass
        else:
            raise AssertionError("HTML with a meta refresh navigation passed artifact validation")
        try:
            weakened_csp = interactive_text.replace("img-src data: blob:", "img-src *", 1).encode("utf-8")
            _valid_html_and_svg(weakened_csp, interactive_svg.read_bytes())
        except DiagramError:
            pass
        else:
            raise AssertionError("HTML with a weakened image policy passed CSP validation")
        incomplete_profile = json.loads(json.dumps(committed))
        incomplete_profile["body"]["boundaries"][0]["component_ids"].remove("N3")
        try:
            validate_spec(incomplete_profile, root)
        except DiagramError as error:
            if "every component" not in str(error):
                raise
        else:
            raise AssertionError("deployment ownership accepted a component with no verified owner")
        brief_profile = json.loads(json.dumps(committed))
        brief_profile["evidence"] = [{"id": "S2", "origin": "brief", "claim": "User says all application parts belong to one boundary."}]
        for values in brief_profile["body"].values():
            if isinstance(values, list):
                for entry in values:
                    if isinstance(entry, dict) and "evidence_ids" in entry:
                        entry["evidence_ids"] = ["S2"]
        try:
            validate_spec(brief_profile, None, require_repository_sources=True)
        except DiagramError as error:
            if "brief-only evidence" not in str(error):
                raise
        else:
            raise AssertionError("deployment ownership accepted unverified brief claims")
        source_path = root / "source.txt"
        source_path.write_text("line one\nchanged evidence\nline three\n", encoding="utf-8")
        changed_snapshot = validate_spec(committed, root)["snapshots"]["S1"]
        if changed_snapshot["snapshot"] != "working-tree" or "source.txt" not in git_context(root)["changed_paths"]:
            raise AssertionError("changed evidence was not distinguished from committed source bytes")
        updated = json.loads(json.dumps(committed))
        updated["title"] = "Updated architecture"
        updated["body"]["components"].append({
            "id": "N4", "label": "New worker", "kind": "worker", "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        updated["body"]["relationships"][1]["target"] = "N4"
        updated["body"]["relationships"].append({
            "id": "E3", "source": "N4", "target": "N3", "label": "continue work", "kind": "call",
            "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        updated["body"]["boundaries"][0]["component_ids"].append("N4")
        updated["layout"]["layers"] = [["N1"], ["N2"], ["N4"], ["N3"]]
        updated_path = specs_dir / "interactive-head.json"
        updated_path.write_text(json.dumps(updated), encoding="utf-8")
        _render(updated_path, root, outputs_dir, "interactive-head", False)
        delta_dir = root.parent / "deltas"
        delta_result = _compare(interactive_html, outputs_dir / "interactive-head.html", root, delta_dir, "architecture-change", False)
        if delta_result["counts"]["added"] < 2 or delta_result["counts"]["rerouted"] != 1 or delta_result["counts"]["moved"] != 1:
            raise AssertionError(f"architecture comparison lost explicit change categories: {delta_result['counts']}")
        delta_page = (delta_dir / "architecture-change.delta.html").read_text(encoding="utf-8")
        if "Before" not in delta_page or "Changes" not in delta_page or "After" not in delta_page or "merge safety" not in delta_page:
            raise AssertionError("architecture delta output lacks triple-panel structure or explicit inference limits")
        comparison_receipt = {"repository": git_context(root), "outputs": {"html": "a" * 64}}
        direction_change = json.loads(json.dumps(committed))
        direction_change["layout"]["direction"] = "TB"
        direction_delta = compare_architecture(
            validate_spec(committed, root), validate_spec(direction_change, root), comparison_receipt, comparison_receipt,
        )
        if not any(item["kind"] == "layout" and item["id"] == "direction" for item in direction_delta["changes"]):
            raise AssertionError("architecture delta missed an authored layout direction change")
        ordered_before = json.loads(json.dumps(committed))
        ordered_before["body"]["components"].append({
            "id": "N4", "label": "Unused worker", "kind": "worker", "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        ordered_before["body"]["boundaries"][0]["component_ids"].append("N4")
        ordered_before["layout"]["layers"] = [["N1"], ["N2", "N4"], ["N3"]]
        ordered_after = json.loads(json.dumps(ordered_before))
        ordered_after["layout"]["layers"] = [["N1"], ["N4", "N2"], ["N3"]]
        ordered_before_spec, ordered_after_spec = validate_spec(ordered_before, root), validate_spec(ordered_after, root)
        order_delta = compare_architecture(ordered_before_spec, ordered_after_spec, comparison_receipt, comparison_receipt)
        if sum(item["category"] == "moved" for item in order_delta["changes"]) < 2:
            raise AssertionError("architecture delta missed a same-layer authored order change")
        order_page = _delta_html(order_delta, ordered_before_spec, ordered_after_spec, "en", comparison_receipt["repository"], comparison_receipt["repository"]).decode("utf-8")
        if "position 0" not in order_page or "position 1" not in order_page:
            raise AssertionError("architecture delta hid same-layer authored positions in its report")
        geometry_before = validate_spec(authored_geometry, root)
        geometry_after_raw = json.loads(json.dumps(authored_geometry))
        geometry_after_raw["layout"]["positions"]["N1"]["x"] += 18
        geometry_after_raw["layout"]["edge_hints"]["E1"]["waypoints"][0]["y"] += 12
        geometry_after_raw["layout"]["edge_hints"]["E1"]["label"]["offset"]["y"] -= 6
        geometry_after = validate_spec(geometry_after_raw, root)
        geometry_delta = compare_architecture(geometry_before, geometry_after, comparison_receipt, comparison_receipt)
        geometry_changes = {(item["category"], item["kind"], item["id"]) for item in geometry_delta["changes"]}
        if not {("moved", "component", "N1"), ("rerouted", "relationship", "E1"), ("changed", "label-layout", "E1")} <= geometry_changes:
            raise AssertionError(f"architecture delta missed authored geometry edits: {geometry_delta['changes']}")
        geometry_page = _delta_html(geometry_delta, geometry_before, geometry_after, "en", comparison_receipt["repository"], comparison_receipt["repository"]).decode("utf-8")
        if "&quot;x&quot;: 104.0" not in geometry_page or "label-layout / E1" not in geometry_page:
            raise AssertionError("architecture delta did not render authored positions and label adjustments")
        removed_geometry_raw = json.loads(json.dumps(authored_geometry))
        removed_geometry_raw["body"]["relationships"] = [
            edge for edge in removed_geometry_raw["body"]["relationships"] if edge["id"] != "E1"
        ]
        removed_geometry_raw["layout"]["edge_hints"].pop("E1")
        if not removed_geometry_raw["layout"]["edge_hints"]:
            removed_geometry_raw["layout"].pop("edge_hints")
        removed_geometry = validate_spec(removed_geometry_raw, root)
        removal_delta = compare_architecture(geometry_before, removed_geometry, comparison_receipt, comparison_receipt)
        removed_edge_changes = [item for item in removal_delta["changes"] if item["id"] == "E1"]
        if [(item["category"], item["kind"]) for item in removed_edge_changes] != [("removed", "relationship")]:
            raise AssertionError(f"architecture delta reported geometry changes for a removed relationship: {removed_edge_changes}")
        if len(re.findall(r"<svg\b[^>]*data-snapshot=\"before\"", order_page)) != 1 or len(re.findall(r"<svg\b[^>]*data-snapshot=\"after\"", order_page)) != 1:
            raise AssertionError("architecture delta omitted a rendered before/after diagram snapshot")
        if 'aria-labelledby="before-diagram-title before-diagram-description"' not in order_page or 'aria-labelledby="after-diagram-title after-diagram-description"' not in order_page:
            raise AssertionError("architecture delta reused accessibility identifiers across diagram snapshots")
        originless = {"repository": {"origin": None, "name": "repo"}, "outputs": {"html": "a" * 64}}
        try:
            compare_architecture(validate_spec(committed, root), validate_spec(committed, root), originless, originless)
        except DiagramError:
            pass
        else:
            raise AssertionError("architecture delta accepted snapshots without a repository origin")
        if os.name == "posix" and hasattr(os, "geteuid"):
            recovery_stage = Path(tempfile.mkdtemp(prefix=".patpat-diagram-tx-recovery-", dir=outputs_dir))
            recovery_files = [f"recovery.{suffix}" for suffix in ("diagram.json", "svg", "html", "receipt.json")]
            recovery_entries = []
            recovery_old = {}
            for index, filename in enumerate(recovery_files):
                old_bytes = f"old output {index}".encode()
                new_bytes = f"new output {index}".encode()
                target = outputs_dir / filename
                target.write_bytes(new_bytes if index == 0 else old_bytes)
                recovery_old[filename] = old_bytes
                if index > 0:
                    (recovery_stage / f"new-{index}").write_bytes(new_bytes)
                (recovery_stage / f"old-{index}").write_bytes(old_bytes)
                recovery_entries.append({
                    "name": filename, "staged": f"new-{index}", "backup": f"old-{index}", "had_existing": True,
                    "old_sha256": hashlib.sha256(old_bytes).hexdigest(),
                    "new_sha256": hashlib.sha256(new_bytes).hexdigest(),
                })
            transaction = {
                "tool": "patpat-repository-diagram", "schema_version": 1, "owner_pid": os.getpid(),
                "phase": "prepared", "kind": "diagram", "slug": "recovery", "entries": recovery_entries,
            }
            _write_transaction(recovery_stage / "transaction.json", transaction)
            _recover_transaction(recovery_stage, outputs_dir)
            if any((outputs_dir / filename).read_bytes() != value for filename, value in recovery_old.items()) or recovery_stage.exists():
                raise AssertionError("interrupted output replacement did not recover the previous complete file set")
            protected_target = outputs_dir / "README.md"
            protected_target.write_bytes(b"keep this unrelated file")
            attack_stage = Path(tempfile.mkdtemp(prefix=".patpat-diagram-tx-attack-", dir=outputs_dir))
            attack = json.loads(json.dumps(transaction))
            attack["slug"] = "attack"
            attack["entries"][0]["name"] = protected_target.name
            _write_transaction(attack_stage / "transaction.json", attack)
            try:
                _recover_transaction(attack_stage, outputs_dir)
            except DiagramError:
                pass
            else:
                raise AssertionError("recovery accepted a journal targeting an unrelated file")
            if protected_target.read_bytes() != b"keep this unrelated file":
                raise AssertionError("a rejected transaction changed an unrelated file")
            tamper_slug = "backup-check"
            tamper_stage = Path(tempfile.mkdtemp(prefix=".patpat-diagram-tx-backup-check-", dir=outputs_dir))
            tamper_entries = []
            tamper_targets = {}
            for index, suffix in enumerate(("diagram.json", "svg", "html", "receipt.json")):
                filename = f"{tamper_slug}.{suffix}"
                old_data, new_data = f"old {index}".encode(), f"new {index}".encode()
                target = outputs_dir / filename
                target.write_bytes(old_data)
                tamper_targets[filename] = old_data
                (tamper_stage / f"old-{index}").write_bytes(b"tampered backup" if index == 2 else old_data)
                (tamper_stage / f"new-{index}").write_bytes(new_data)
                tamper_entries.append({
                    "name": filename, "staged": f"new-{index}", "backup": f"old-{index}", "had_existing": True,
                    "old_sha256": hashlib.sha256(old_data).hexdigest(), "new_sha256": hashlib.sha256(new_data).hexdigest(),
                })
            tamper_journal = {
                "tool": "patpat-repository-diagram", "schema_version": 1, "owner_pid": os.getpid(),
                "phase": "prepared", "kind": "diagram", "slug": tamper_slug, "entries": tamper_entries,
            }
            _write_transaction(tamper_stage / "transaction.json", tamper_journal)
            try:
                _recover_transaction(tamper_stage, outputs_dir)
            except DiagramError:
                pass
            else:
                raise AssertionError("recovery trusted a backup whose bytes did not match its recorded digest")
            if any((outputs_dir / filename).read_bytes() != content for filename, content in tamper_targets.items()):
                raise AssertionError("rejected recovery changed an existing output target")

            forged_slug = "forged-recovery"
            forged_stage = outputs_dir / ".patpat-diagram-tx-forged-recovery"
            forged_stage.mkdir(mode=0o755)
            os.chmod(forged_stage, 0o755)
            forged_entries = []
            forged_current = {}
            for index, suffix in enumerate(("diagram.json", "svg", "html", "receipt.json")):
                filename = f"{forged_slug}.{suffix}"
                current = f"current allowed artifact {index}".encode()
                forged_backup = f"attacker replacement {index}".encode()
                (outputs_dir / filename).write_bytes(current)
                forged_current[filename] = current
                (forged_stage / f"old-{index}").write_bytes(forged_backup)
                forged_entries.append({
                    "name": filename, "staged": f"new-{index}", "backup": f"old-{index}", "had_existing": True,
                    "old_sha256": hashlib.sha256(forged_backup).hexdigest(),
                    "new_sha256": hashlib.sha256(current).hexdigest(),
                })
            forged_transaction = {
                "tool": "patpat-repository-diagram", "schema_version": 1, "owner_pid": os.getpid(),
                "phase": "prepared", "kind": "diagram", "slug": forged_slug, "entries": forged_entries,
            }
            _write_transaction(forged_stage / "transaction.json", forged_transaction)
            try:
                _recover_transaction(forged_stage, outputs_dir)
            except DiagramError:
                pass
            else:
                raise AssertionError("recovery trusted a forged private-looking transaction over a current artifact")
            if any((outputs_dir / filename).read_bytes() != content for filename, content in forged_current.items()):
                raise AssertionError("a rejected self-consistent journal changed a current artifact")
        else:
            recovery_target = outputs_dir / "recovery.html"
            recovery_target.write_bytes(b"keep output when transaction ownership is unverifiable")
            recovery_stage = outputs_dir / ".patpat-diagram-tx-recovery-unverifiable"
            recovery_stage.mkdir()
            try:
                _recover_transaction(recovery_stage, outputs_dir)
            except DiagramError:
                pass
            else:
                raise AssertionError("transaction recovery did not fail closed when private ownership could not be verified")
            if recovery_target.read_bytes() != b"keep output when transaction ownership is unverifiable":
                raise AssertionError("unverifiable transaction recovery changed an output target")
        cyclic = _sample_spec("architecture", "Feedback route")
        cyclic["body"]["relationships"].append({
            "id": "E3", "source": "N3", "target": "N2", "label": "retry loop", "kind": "call",
            "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        cyclic_spec = validate_spec(cyclic, root)
        try:
            _make_layout(cyclic_spec)
        except DiagramError:
            pass
        else:
            raise AssertionError("an unmarked graph cycle was silently laid out")
        cyclic["body"]["relationships"][-1]["feedback"] = True
        routed_cycle = _make_layout(validate_spec(cyclic, root))
        if routed_cycle["warnings"]:
            raise AssertionError(f"explicit feedback route emitted geometry warnings: {routed_cycle['warnings']}")
        feedback_fanout = _sample_spec("architecture", "Classified recovery fan-out")
        feedback_fanout["body"]["components"].append({
            "id": "N4", "label": "Final verifier", "kind": "service", "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        feedback_fanout["body"]["relationships"].append({
            "id": "E3", "source": "N3", "target": "N4", "label": "continue", "kind": "call",
            "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        for index, target in enumerate(("N1", "N2", "N3"), start=4):
            feedback_fanout["body"]["relationships"].append({
                "id": f"R{index}", "source": "N4", "target": target, "label": f"resume at {target}", "kind": "call",
                "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
            })
        feedback_fanout["layout"] = {"direction": "TB", "layers": [["N1"], ["N2"], ["N3"], ["N4"]]}
        feedback_fanout_layout = _make_layout(validate_spec(feedback_fanout, root))
        if feedback_fanout_layout["warnings"]:
            raise AssertionError(f"parallel TB recovery paths cross or collide: {feedback_fanout_layout['warnings']}")
        for path in (item for item in feedback_fanout_layout["paths"] if item["edge"]["id"].startswith("R")):
            source, target = path["edge"]["source"], path["edge"]["target"]
            if path["points"][0][0] != feedback_fanout_layout["positions"][source]["x"]:
                raise AssertionError("TB feedback route did not leave from the source's outer side")
            if path["points"][-1][0] != feedback_fanout_layout["positions"][target]["x"]:
                raise AssertionError("TB feedback route did not enter the target's outer side")
            target_rect = feedback_fanout_layout["positions"][target]
            if not target_rect["y"] <= path["points"][-1][1] <= target_rect["y"] + target_rect["h"]:
                raise AssertionError("TB feedback target port escaped the node boundary")
        feedback_fanin = _sample_spec("architecture", "Dense recovery fan-in")
        feedback_fanin["body"]["components"].extend({
            "id": f"N{index}", "label": f"Verifier {index}", "kind": "service", "certainty": "confirmed", "evidence_ids": ["S1"],
        } for index in range(4, 22))
        feedback_fanin["body"]["relationships"].extend({
            "id": f"R{index}", "source": f"N{index}", "target": "N1", "label": f"retry {index}", "kind": "call",
            "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
        } for index in range(4, 22))
        feedback_fanin["layout"] = {"direction": "TB", "layers": [["N1"], ["N2"], ["N3"], [f"N{index}" for index in range(4, 22)]]}
        feedback_fanin_layout = _make_layout(validate_spec(feedback_fanin, root))
        if any("edge endpoint outside node port:" in warning for warning in feedback_fanin_layout["warnings"]):
            raise AssertionError(f"dense TB feedback targets escaped node bounds: {feedback_fanin_layout['warnings']}")
        for path in feedback_fanin_layout["paths"]:
            if path["edge"]["id"].startswith("R"):
                target_rect = feedback_fanin_layout["positions"]["N1"]
                if not target_rect["y"] <= path["points"][-1][1] <= target_rect["y"] + target_rect["h"]:
                    raise AssertionError("dense TB feedback fan-in escaped its target port span")
        peer_ids = {f"N{index}" for index in range(4, 22)}
        feedback_edge_ids = {f"R{index}" for index in range(4, 22)}
        if not any(
            warning.startswith("edge crosses node:")
            and warning.partition(": ")[2].partition(";")[0].split("/", 1)[0] in feedback_edge_ids
            and warning.partition(": ")[2].partition(";")[0].rsplit("/", 1)[-1] in peer_ids
            for warning in feedback_fanin_layout["warnings"]
        ):
            raise AssertionError("dense same-layer feedback fan-in must diagnose feedback routes crossing peer nodes")
        feedback_fanin["layout"] = {
            "direction": "TB",
            "layers": [["N1"], ["N2"], ["N3"], *[[f"N{index}"] for index in range(4, 22)]],
        }
        separated_feedback_fanin = _make_layout(validate_spec(feedback_fanin, root))
        if separated_feedback_fanin["warnings"]:
            raise AssertionError(f"authored source layers did not clear dense feedback fan-in: {separated_feedback_fanin['warnings'][:8]}")
        if not _projected_readability(separated_feedback_fanin)["passed"]:
            raise AssertionError("ordered feedback layers fell below the projected label readability floor")
        self_loop = _sample_spec("architecture", "Self loop route")
        self_loop["body"]["relationships"].append({
            "id": "E3", "source": "N2", "target": "N2", "label": "retry same service", "kind": "call",
            "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
        })
        for direction in ("LR", "TB"):
            self_loop["layout"] = {"direction": direction}
            loop_layout = _make_layout(validate_spec(self_loop, root))
            loop_path = next(path for path in loop_layout["paths"] if path["edge"]["id"] == "E3")
            if len(set(loop_path["points"])) < 4 or loop_layout["warnings"]:
                raise AssertionError(f"{direction} self-loop was collapsed or collided: {loop_path['points']} {loop_layout['warnings']}")
        for index in range(4, 9):
            label = "retry after timeout and recover through the configured secondary path" if index == 8 else f"retry path {index}"
            self_loop["body"]["relationships"].append({
                "id": f"E{index}", "source": "N2", "target": "N2", "label": label, "kind": "call",
                "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
            })
        for direction in ("LR", "TB"):
            self_loop["layout"] = {"direction": direction}
            multi_loop = _make_layout(validate_spec(self_loop, root))
            loop_paths = [path["points"] for path in multi_loop["paths"] if path["edge"]["id"] in {"E3", "E4", "E5", "E6", "E7", "E8"}]
            if len(loop_paths) != 6 or len({tuple(tuple(point) for point in path) for path in loop_paths}) != 6 or multi_loop["warnings"]:
                raise AssertionError(f"same-node {direction} self-loops overlap or collide: {loop_paths} {multi_loop['warnings']}")
        neighboring_loops = _sample_spec("architecture", "Self loops beside a peer")
        neighboring_loops["body"]["components"].append({
            "id": "N4", "label": "Side worker", "kind": "worker", "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        neighboring_loops["layout"] = {"direction": "TB", "layers": [["N1"], ["N2", "N4"], ["N3"]]}
        for index in range(3, 9):
            neighboring_loops["body"]["relationships"].append({
                "id": f"L{index}", "source": "N2", "target": "N2", "label": f"loop {index}", "kind": "call",
                "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
            })
        neighbor_layout = _make_layout(validate_spec(neighboring_loops, root))
        if neighbor_layout["warnings"]:
            raise AssertionError(f"TB self-loops crossed a same-layer peer: {neighbor_layout['warnings']}")
        lr_neighboring_loops = _sample_spec("architecture", "LR loops below a peer")
        lr_neighboring_loops["body"]["components"].append({
            "id": "N4", "label": "Side worker", "kind": "worker", "certainty": "confirmed", "evidence_ids": ["S1"],
        })
        lr_neighboring_loops["layout"] = {"direction": "LR", "layers": [["N1"], ["N2", "N4"], ["N3"]]}
        lr_neighboring_loops["body"]["relationships"].append({
            "id": "LT", "source": "N2", "target": "N2", "label": "quick retry", "kind": "call",
            "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
        })
        for index in range(3, 9):
            label = "retry after timeout and recover through the configured secondary path" if index == 8 else f"loop {index}"
            lr_neighboring_loops["body"]["relationships"].append({
                "id": f"L{index}", "source": "N4", "target": "N4", "label": label, "kind": "call",
                "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
            })
        lr_neighbor_layout = _make_layout(validate_spec(lr_neighboring_loops, root))
        if lr_neighbor_layout["warnings"]:
            raise AssertionError(f"LR self-loops on layer peers collided: {lr_neighbor_layout['warnings']}")
        bottom_peer = lr_neighbor_layout["positions"]["N4"]
        if any(
            min(point[1] for point in path["points"]) < bottom_peer["y"] + bottom_peer["h"]
            for path in lr_neighbor_layout["paths"] if path["edge"]["source"] == "N4"
        ):
            raise AssertionError("bottom-peer LR self-loops did not route below the entity")
        middle_peer_loop = _sample_spec("architecture", "LR loop on a middle peer")
        for identifier, label in (("N4", "Middle worker"), ("N5", "Lower worker")):
            middle_peer_loop["body"]["components"].append({
                "id": identifier, "label": label, "kind": "worker", "certainty": "confirmed", "evidence_ids": ["S1"],
            })
        middle_peer_loop["layout"] = {"direction": "LR", "layers": [["N1"], ["N2", "N4", "N5"], ["N3"]]}
        middle_peer_loop["body"]["relationships"].append({
            "id": "LM", "source": "N4", "target": "N4", "label": "retry", "kind": "call",
            "certainty": "confirmed", "evidence_ids": ["S1"], "feedback": True,
        })
        try:
            _make_layout(validate_spec(middle_peer_loop, root))
        except DiagramError as error:
            if "use TB direction" not in str(error):
                raise AssertionError(f"middle-peer LR self-loop gave no actionable guidance: {error}") from error
        else:
            raise AssertionError("middle-peer LR self-loop was laid out through a sibling")
        narrow_tb = _sample_spec("architecture", "Narrow canvas")
        narrow_tb["layout"] = {"direction": "TB"}
        narrow_layout = _make_layout(validate_spec(narrow_tb, root))
        if narrow_layout["width"] < MIN_CANVAS_WIDTH or narrow_layout["warnings"]:
            raise AssertionError(f"narrow TB canvas clipped header or legend: {narrow_layout['width']} {narrow_layout['warnings']}")
        narrow_x = [
            coordinate
            for item in narrow_layout["positions"].values()
            for coordinate in (item["x"], item["x"] + item["w"])
        ]
        narrow_x.extend(coordinate for path in narrow_layout["paths"] for coordinate, _ in path["points"])
        narrow_x.extend(
            coordinate
            for label in narrow_layout["labels"]
            for coordinate in (label["x"] - label["w"] / 2.0, label["x"] + label["w"] / 2.0)
        )
        if abs((min(narrow_x) + max(narrow_x)) / 2.0 - narrow_layout["width"] / 2.0) > 0.5:
            raise AssertionError("TB graph content is not centered within its authored canvas")
        fanout = _sample_spec("architecture", "Shared source crossing")
        fanout["body"]["relationships"] = [
            {"id": "E1", "source": "N1", "target": "N3", "label": "lower branch", "kind": "call", "certainty": "confirmed", "evidence_ids": ["S1"]},
            {"id": "E2", "source": "N1", "target": "N2", "label": "upper branch", "kind": "call", "certainty": "confirmed", "evidence_ids": ["S1"]},
        ]
        fanout["layout"] = {"direction": "LR", "layers": [["N1"], ["N2", "N3"]]}
        fanout_layout = _make_layout(validate_spec(fanout, root))
        if not any(warning.startswith("edge crossing: E1/E2") for warning in fanout_layout["warnings"]):
            raise AssertionError(f"crossing fan-out paths sharing N1 were not diagnosed: {fanout_layout['warnings']}")
        sequence_tb = _sample_spec("sequence", "Unsupported sequence direction")
        sequence_tb["layout"] = {"direction": "TB"}
        try:
            validate_spec(sequence_tb, root)
        except DiagramError as error:
            if "temporal left-to-right" not in str(error):
                raise
        else:
            raise AssertionError("sequence direction TB was accepted but is not rendered")
        unknown_group = _sample_spec("architecture", "Unknown boundary reason")
        unknown_group["body"]["boundaries"] = [{
            "id": "B1", "label": "External area", "component_ids": ["N1"], "certainty": "unknown",
            "evidence_ids": [], "reason": "Ownership source is absent",
        }]
        group_spec = validate_spec(unknown_group, root)
        group_layout = _make_layout(group_spec)
        group_svg = _svg_document(group_spec, git, group_layout).decode("utf-8")
        group_html = _html_document(group_spec, git, group_svg.encode("utf-8")).decode("utf-8")
        if "External area; Unknown; Ownership source is absent" not in group_svg or "Ownership source is absent" not in group_html:
            raise AssertionError("unknown boundary reason was missing from visual accessibility or text outline")
        tall_header = _sample_spec("workflow", "Long Thai title")
        tall_header.update({
            "language": "th",
            "title": "ขั้นตอนตรวจสอบสิทธิ์และบันทึกผลสำหรับคำขอจากผู้ใช้ทุกกลุ่ม",
            "summary": "ระบบอ่านคำขอ ตรวจสิทธิ์ บันทึกผล และส่งคำตอบกลับพร้อมหลักฐานอ้างอิง " * 3,
        })
        tall_spec = validate_spec(tall_header, root)
        tall_layout = _make_layout(tall_spec)
        header_height = _header_height(tall_spec)
        if header_height <= 176.0 or min(rect["y"] for rect in tall_layout["positions"].values()) <= header_height:
            raise AssertionError("expanded title and summary do not reserve space before diagram content")
        crossing_paths = [
            {"edge": {"id": "E1", "source": "A", "target": "B"}, "points": [(10.0, 50.0), (90.0, 50.0)]},
            {"edge": {"id": "E2", "source": "C", "target": "D"}, "points": [(50.0, 10.0), (50.0, 90.0)]},
        ]
        edge_crossings = _geometry_warnings({}, crossing_paths, [], [], 100.0, 100.0)
        if not any(warning.startswith("edge crossing: E1/E2") for warning in edge_crossings):
            raise AssertionError("independent crossing edges were not diagnosed")
        node_crossings = _geometry_warnings(
            {"N": {"x": 45.0, "y": 45.0, "w": 10.0, "h": 10.0}},
            [crossing_paths[0]], [], [], 100.0, 100.0,
        )
        if not any(warning.startswith("edge crosses node: E1/N") for warning in node_crossings):
            raise AssertionError("an edge crossing an unrelated node was not diagnosed")
        svg_path = outputs_dir / "sequence.svg"
        good_svg = svg_path.read_bytes()
        svg_path.write_bytes(good_svg + b" ")
        try:
            _check(outputs_dir / "sequence.html", root)
        except DiagramError:
            pass
        else:
            raise AssertionError("modified SVG did not invalidate the output receipt")
        svg_path.write_bytes(good_svg)
        (root / "source.txt").write_text("line one\nchanged source\nline three\n", encoding="utf-8")
        try:
            _check(outputs_dir / "sequence.html", root)
        except DiagramError:
            pass
        else:
            raise AssertionError("changed source did not invalidate the evidence receipt")
        bad = _sample_spec("architecture", "bad")
        bad["body"]["relationships"][0]["target"] = "missing"
        try:
            validate_spec(bad, root)
        except DiagramError:
            pass
        else:
            raise AssertionError("unknown relationship target was accepted")
        bad = _sample_spec("architecture", "bad")
        bad["evidence"][0]["path"] = "../source.txt"
        try:
            validate_spec(bad, root)
        except DiagramError:
            pass
        else:
            raise AssertionError("path traversal evidence was accepted")
        print("Patpat diagram self-test passed: five typed layouts, source checks, accessible static output, escaping, and invalid-reference rejection")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-errors", action="store_true", help="write stable structured diagnostics to stderr")
    sub = parser.add_subparsers(dest="command", required=True)
    guide_parser = sub.add_parser("guide", help="show supported diagram types, profiles, and authoring rules")
    guide_parser.add_argument("type", nargs="?", choices=sorted(DIAGRAM_GUIDE))
    guide_parser.add_argument("--format", choices=("json", "text"), default="json")
    validate_parser = sub.add_parser("validate", help="validate typed JSON and repository evidence")
    validate_parser.add_argument("source", type=Path)
    validate_parser.add_argument("--repo-root", type=Path, help="Git root required only when evidence cites repository files")
    finalize_parser = sub.add_parser("finalize", help="strict-check and browser-gate the complete output set before journaled delivery")
    finalize_parser.add_argument("source", type=Path)
    finalize_parser.add_argument("--repo-root", type=Path, help="Git root required only when evidence cites repository files")
    finalize_parser.add_argument("--out-dir", type=Path, required=True)
    finalize_parser.add_argument("--name", required=True)
    finalize_parser.add_argument("--overwrite", action="store_true")
    finalize_parser.add_argument("--browser", help="supported local Chromium executable; discovered automatically when omitted")
    finalize_parser.add_argument("--browser-profile", choices=("standard", "showcase"), default="standard")
    finalize_parser.add_argument("--no-browser", action="store_true", help="skip visual runtime capture; strict artifact checks still run")
    finalize_parser.add_argument("--public-source-links", action="store_true", help="link only committed ranges after anonymous GitHub visibility and commit checks")
    check_parser = sub.add_parser("check", help="verify artifact structure and receipt digests")
    check_parser.add_argument("html", type=Path)
    check_parser.add_argument("--repo-root", type=Path, help="Git root required for repository-backed evidence")
    browser_parser = sub.add_parser("browser-check", help="open HTML in a local headless Chromium browser")
    browser_parser.add_argument("html", type=Path)
    browser_parser.add_argument("--repo-root", type=Path, help="Git root required for repository-backed evidence")
    browser_parser.add_argument("--browser")
    browser_parser.add_argument("--screenshot", type=Path)
    browser_parser.add_argument("--receipt", type=Path)
    browser_parser.add_argument("--profile", choices=("standard", "showcase"), default="standard")
    preview_parser = sub.add_parser("preview", help="watch one spec and serve the last validated build on loopback")
    preview_parser.add_argument("source", type=Path)
    preview_parser.add_argument("--repo-root", type=Path, help="Git root required only when evidence cites repository files")
    preview_parser.add_argument("--name", required=True)
    compare_parser = sub.add_parser("compare", aliases=["delta"], help="compare two architecture artifact snapshots")
    compare_parser.add_argument("base", type=Path, help="previous artifact HTML path")
    compare_parser.add_argument("head", type=Path, help="current artifact HTML path")
    compare_parser.add_argument("--repo-root", type=Path, required=True)
    compare_parser.add_argument("--out-dir", type=Path, required=True)
    compare_parser.add_argument("--name", required=True)
    compare_parser.add_argument("--overwrite", action="store_true")
    sub.add_parser("self-test", help="exercise all supported types and safety checks")
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            self_test()
            return 0
        if args.command == "guide":
            print(_guide(args.type, args.format))
            return 0
        if args.command == "validate":
            raw, data = load_json(args.source)
            context = git_context(args.repo_root)
            spec = validate_spec(raw, args.repo_root, require_repository_sources=True)
            _make_layout(spec)
            print(json.dumps({"status": "passed", "schema_version": spec["schema_version"], "type": spec["type"], "title": spec["title"], "revision": context["revision"], "dirty": context["dirty"], "evidence": len(spec["evidence"]), "evidence_origins": sorted({item.get("origin", "repository") for item in spec["evidence"]}), "evidence_snapshots": sorted({item.get("snapshot", "brief") for item in spec["snapshots"].values()})}, ensure_ascii=False))
            return 0
        if args.command == "finalize":
            result = _finalize(
                args.source, args.repo_root, args.out_dir, args.name, args.overwrite,
                args.browser, args.browser_profile, not args.no_browser, args.public_source_links,
            )
            print(json.dumps({"status": "passed", **result}, ensure_ascii=False))
            return 0
        if args.command == "check":
            print(json.dumps(_check(args.html.resolve(strict=True), args.repo_root), ensure_ascii=False))
            return 0
        if args.command == "browser-check":
            print(json.dumps(_browser_check(args.html, args.repo_root, args.screenshot, args.browser, args.receipt, args.profile), ensure_ascii=False))
            return 0
        if args.command in {"compare", "delta"}:
            print(json.dumps(_compare(args.base, args.head, args.repo_root, args.out_dir, args.name, args.overwrite), ensure_ascii=False))
            return 0
        if args.command == "preview":
            return _preview(args.source, args.repo_root, args.name)
        raise DiagramError("unknown command")
    except (DiagramError, OSError, json.JSONDecodeError) as error:
        diagnostic = _stable_diagnostic(error, getattr(error, "stage", getattr(args, "command", "startup")))
        if isinstance(error, _FinalizeGateError):
            diagnostic["gates"] = error.gates
            diagnostic["published"] = False
        if getattr(args, "json_errors", False):
            print(json.dumps(diagnostic, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"diagram error [{diagnostic['code']}] at {diagnostic['stage']}: {diagnostic['observed']}", file=sys.stderr)
            for fix in diagnostic["supported_fixes"]:
                print(f"  - {fix}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
