#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

PROJECT = Path.home() / "clova-note-copy"
sys.path.insert(0, str(PROJECT))

from asr.registry import build_default_registry
from asr.schema import CANONICAL_ASR_SCHEMA

errors = []
registry = build_default_registry(PROJECT / "asr" / "profiles" / "default.yaml")
snap = registry.snapshot()
slots = snap.get("profile", {}).get("slots", {})

for slot in ("preview", "committed", "adaptation"):
    if not (slots.get(slot) or {}).get("engine"):
        errors.append(f"missing slot: {slot}")
if snap.get("canonical_result_schema") != CANONICAL_ASR_SCHEMA:
    errors.append("canonical result schema mismatch")

live = None
try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/asr/registry", timeout=2) as r:
        live = json.loads(r.read().decode("utf-8"))
except Exception as exc:
    errors.append(f"live /api/asr/registry unavailable: {exc!r}")

if live:
    if live.get("migration_phase") != "interface_only":
        errors.append(f"unexpected migration_phase: {live.get('migration_phase')!r}")
    if live.get("production_execution") != "legacy_direct_until_v8.2-delta":
        errors.append("gamma must preserve legacy direct production execution")

print("Profile        :", snap.get("profile", {}).get("profile_id"))
print("Preview        :", (slots.get("preview") or {}).get("engine"))
print("Committed      :", (slots.get("committed") or {}).get("engine"))
print("Adaptation     :", (slots.get("adaptation") or {}).get("engine"))
print("Canonical      :", snap.get("canonical_result_schema"))
print("Live endpoint  :", "OK" if live else "FAIL")
print("Execution      :", (live or snap).get("production_execution"))
print("RESULT         :", "FAIL" if errors else "PASS")
if errors:
    for err in errors:
        print("  -", err)
    raise SystemExit(1)
