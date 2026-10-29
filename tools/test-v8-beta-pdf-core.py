#!/usr/bin/env python3
"""Small dependency-free V8.0-beta.6 PDF state/schema invariant drill."""
import hashlib
import re

PDF_ID_RE = re.compile(r"^pdf_[0-9a-f]{16}$")

def pdf_id(data: bytes) -> str:
    return "pdf_" + hashlib.sha256(data).hexdigest()[:16]

def canonical(pid: str, page: int) -> str:
    assert PDF_ID_RE.fullmatch(pid)
    page = max(1, int(page))
    return f"clova://pdf/{pid}/page/{page}"

a = b"%PDF-1.7\nalpha"
b = b"%PDF-1.7\nbeta"
pa = pdf_id(a)
pb = pdf_id(b)
assert pa == pdf_id(a), "same PDF must dedupe to the same id"
assert pa != pb, "different PDF content must have different ids"
assert PDF_ID_RE.fullmatch(pa)
assert canonical(pa, 23).endswith("/page/23")
assert canonical(pa, 0).endswith("/page/1")
# Viewer state machine: reading is independent of the attached document list.
state = {"active_pdf_id": pa, "page": 23, "reading": False}
assert state["reading"] is False
state["reading"] = True
assert canonical(state["active_pdf_id"], state["page"]) == f"clova://pdf/{pa}/page/23"
state["reading"] = False
assert state["active_pdf_id"] == pa, "closing the viewer must not detach the PDF"
print("V8.0-beta.6 PDF core: PASS")
