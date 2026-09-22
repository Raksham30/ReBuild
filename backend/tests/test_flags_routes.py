"""
Step 3 integration test for the contradiction flags API.

Tests:
  a) Route GET /flags returns the correct shape
  b) Route PATCH /flags/{id} updates status and GET afterwards reflects it
  c) include_dismissed=true shows dismissed flags; default hides them

Run with:
    cd backend
    python tests/test_flags_routes.py
"""
import sys, os, json, time, uuid, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---- Patch settings so tests use local JSON, not Cosmos ----
import app.config as _cfg
from app.config import Settings

_test_metadata = os.path.join(os.path.dirname(__file__), "_test_metadata.json")

from pydantic import ConfigDict

class _TestSettings(Settings):
    cosmos_db_uri: str | None = None
    cosmos_db_key: str | None = None
    firebase_service_account_path: str | None = None  # dev-mode: token = uid
    local_metadata_path: str = _test_metadata
    model_config = ConfigDict(extra="ignore")

import functools
_cfg.get_settings = functools.lru_cache(maxsize=1)(lambda: _TestSettings())

# ---- Clean up test file before starting ----
if os.path.exists(_test_metadata):
    os.remove(_test_metadata)

from fastapi.testclient import TestClient
from app.main import app
from app.auth import get_current_uid
from app.services import storage
from app.schemas import Flag

TEST_UID = "test-user-flags"
app.dependency_overrides[get_current_uid] = lambda: TEST_UID

client = TestClient(app, raise_server_exceptions=True)
AUTH = {"Authorization": f"Bearer {TEST_UID}"}
PASS = "[PASS]"
FAIL = "[FAIL]"

errors = []

def check(label, condition, detail=""):
    if condition:
        print(f"  {PASS} {label}")
    else:
        print(f"  {FAIL} {label}  {detail}")
        errors.append(label)

# ---------------------------------------------------------------
# 0. Create workspace via API
# ---------------------------------------------------------------
print("\n-- 0. Create test workspace --")
r = client.post("/workspaces", json={"name": "Flag Test WS"}, headers=AUTH)
check(f"POST /workspaces returns 200 (got {r.status_code}: {r.text})", r.status_code == 200)
ws = r.json()
if r.status_code != 200:
    print("Response detail:", r.text)
    sys.exit(1)
WS_ID = ws["workspace_id"]
print(f"     workspace_id: {WS_ID}")

# ---------------------------------------------------------------
# 1. Seed two papers so storage.get_paper returns real titles
# ---------------------------------------------------------------
print("\n-- 1. Seed paper records --")
from app.schemas import Paper

paper_a = Paper(paper_id="papera001", workspace_id=WS_ID,
                filename="attention_is_all_you_need.pdf",
                title="Attention Is All You Need", status="indexed")
paper_b = Paper(paper_id="paperb002", workspace_id=WS_ID,
                filename="bert_paper.pdf",
                title="BERT: Pre-training of Deep Bidirectional Transformers",
                status="indexed")
storage.save_paper(paper_a)
storage.save_paper(paper_b)
print(f"     Seeded: {paper_a.title}")
print(f"     Seeded: {paper_b.title}")

# ---------------------------------------------------------------
# 2. Directly save a contradiction flag (simulates background task)
# ---------------------------------------------------------------
print("\n-- 2. Inject a contradiction flag (simulating background detection) --")
flag_payload = {
    "paper_a_id": "papera001",
    "paper_a_title": "Attention Is All You Need",
    "claim_a": "The Transformer outperforms all previously reported ensembles on BLEU by over 2 points.",
    "paper_a_citation": {
        "paper_id": "papera001",
        "paper_title": "Attention Is All You Need",
        "section_type": "results",
        "page_start": 8,
        "page_end": 8,
        "snippet": "The Transformer outperforms all previously reported ensembles on BLEU by over 2 points.",
    },
    "paper_b_id": "paperb002",
    "paper_b_title": "BERT: Pre-training of Deep Bidirectional Transformers",
    "claim_b": "BERT achieves better BLEU scores than single-model Transformers on WMT translation tasks.",
    "paper_b_citation": {
        "paper_id": "paperb002",
        "paper_title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "section_type": "results",
        "page_start": 11,
        "page_end": 11,
        "snippet": "BERT achieves better BLEU scores than single-model Transformers on WMT translation tasks.",
    },
    "explanation": "Paper A claims Transformer sets the best BLEU record; Paper B claims BERT surpasses it.",
}
flag_record = {
    "type": "contradiction",
    "paper_ids_involved": ["papera001", "paperb002"],
    "payload": flag_payload,
}
storage.save_flag(WS_ID, flag_record)
print("     Flag saved via storage.save_flag()")

# ---------------------------------------------------------------
# 3a. GET /flags (default: exclude dismissed)
# ---------------------------------------------------------------
print("\n-- 3a. GET /flags (include_dismissed=false, default) --")
t0 = time.perf_counter()
r = client.get(f"/workspaces/{WS_ID}/flags", headers=AUTH)
elapsed = time.perf_counter() - t0
check("Status 200", r.status_code == 200, r.text)
flags_list = r.json()
check("Returns a list", isinstance(flags_list, list))
check("Contains 1 flag", len(flags_list) == 1, f"got {len(flags_list)}")
if flags_list:
    f = flags_list[0]
    check("flag_id present", bool(f.get("flag_id")), str(f))
    check("type = contradiction", f.get("type") == "contradiction")
    check("status = new", f.get("status") == "new")
    check("paper_ids_involved present", len(f.get("paper_ids_involved", [])) == 2)
    p = f.get("payload", {})
    check("payload.paper_a_title correct", p.get("paper_a_title") == "Attention Is All You Need", p.get("paper_a_title"))
    check("payload.claim_a non-empty", bool(p.get("claim_a")), p.get("claim_a"))
    check("payload.paper_b_title correct", "BERT" in p.get("paper_b_title",""), p.get("paper_b_title"))
    check("payload.claim_b non-empty", bool(p.get("claim_b")), p.get("claim_b"))
    check("payload.explanation non-empty", bool(p.get("explanation")))
    FLAG_ID = f["flag_id"]
    print(f"\n     Full flag response:\n{json.dumps(f, indent=4)}")
    print(f"\n     GET /flags response time: {elapsed*1000:.0f} ms")

# ---------------------------------------------------------------
# 3b. PATCH /flags/{id} -> dismiss
# ---------------------------------------------------------------
print("\n-- 3b. PATCH /flags/{flag_id} status=dismissed --")
r_patch = client.patch(
    f"/workspaces/{WS_ID}/flags/{FLAG_ID}",
    json={"status": "dismissed"},
    headers=AUTH,
)
check("PATCH returns 204", r_patch.status_code == 204, r_patch.text)

# ---------------------------------------------------------------
# 3c. GET /flags after dismiss -> should be empty
# ---------------------------------------------------------------
print("\n-- 3c. GET /flags after dismiss (should be empty) --")
r2 = client.get(f"/workspaces/{WS_ID}/flags", headers=AUTH)
check("Status 200", r2.status_code == 200)
after = r2.json()
check("List is now empty (flag hidden)", len(after) == 0, f"got {after}")

# ---------------------------------------------------------------
# 3d. GET /flags?include_dismissed=true -> shows the dismissed flag
# ---------------------------------------------------------------
print("\n-- 3d. GET /flags?include_dismissed=true --")
r3 = client.get(f"/workspaces/{WS_ID}/flags?include_dismissed=true", headers=AUTH)
check("Status 200", r3.status_code == 200)
with_dismissed = r3.json()
check("Dismissed flag returned", len(with_dismissed) == 1, f"got {with_dismissed}")
if with_dismissed:
    check("Status is dismissed", with_dismissed[0]["status"] == "dismissed")

# ---------------------------------------------------------------
# 3e. Wrong workspace -> 403
# ---------------------------------------------------------------
print("\n-- 3e. Wrong owner -> 403 --")
app.dependency_overrides[get_current_uid] = lambda: "other-user"
r4 = client.get(f"/workspaces/{WS_ID}/flags", headers={"Authorization": "Bearer other-user"})
check("Returns 403 for wrong owner", r4.status_code == 403, r4.text)
app.dependency_overrides[get_current_uid] = lambda: TEST_UID

# ---------------------------------------------------------------
# 4. Regression: existing routes still respond
# ---------------------------------------------------------------
print("\n-- 4. Regression: existing routes --")
r_papers = client.get(f"/workspaces/{WS_ID}/papers", headers=AUTH)
check("GET /papers still works (200)", r_papers.status_code == 200, r_papers.text)
r_health = client.get("/health")
check("GET /health still works (200)", r_health.status_code == 200)

# ---------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------
if os.path.exists(_test_metadata):
    os.remove(_test_metadata)

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
print()
if errors:
    print(f"FAILED -- {len(errors)} check(s) failed:")
    for e in errors:
        print(f"  * {e}")
    sys.exit(1)
else:
    print("All checks passed.")
