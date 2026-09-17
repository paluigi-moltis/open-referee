#!/usr/bin/env python
"""Smoke test: boot the server with a test config, hit the pages, start a review
against the fake provider, wait for the run, check artifacts."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "src")
os.environ["OPEN_REFEREE_HOME"] = "/tmp/or-smoke"

import shutil

shutil.rmtree("/tmp/or-smoke", ignore_errors=True)
Path("/tmp/or-smoke").mkdir(exist_ok=True)

from fastapi.testclient import TestClient

from open_referee.config import Config, LLMConfig, ProviderConfig, RoleConfig, ProviderType, ModelRole, save_config
from open_referee.server.app import create_app

cfg = Config()
cfg.llm = LLMConfig(
    providers={"fake": ProviderConfig(type=ProviderType.FAKE)},
    roles={
        ModelRole.STRONG: RoleConfig(provider="fake", model="strong-fake"),
        ModelRole.SMALL: RoleConfig(provider="fake", model="small-fake"),
    },
)
cfg.review.max_cost_usd = 100.0
save_config(cfg, "/tmp/or-smoke/config.yaml")

app = create_app()
app.state.config_path = "/tmp/or-smoke/config.yaml"

import threading, time as _time
import uvicorn

config = uvicorn.Config(app, host="127.0.0.1", port=8477, log_level="warning")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
for _ in range(50):
    try:
        import urllib.request as _u
        _u.urlopen("http://127.0.0.1:8477/health", timeout=1)
        break
    except Exception:
        _time.sleep(0.2)

BASE = "http://127.0.0.1:8477"

def _get(url):
    import urllib.request
    return urllib.request.urlopen(BASE + url, timeout=10).read().decode()

def _post(url, data, content_type="application/json"):
    import urllib.request
    req = urllib.request.Request(BASE + url, data=data, method="POST",
                                 headers={"Content-Type": content_type})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

print("pages OK")

# 2. script the fake providers via the pipeline's RolePool
import open_referee.pipeline.orchestrator as orch

_orig_build = orch.ReviewPipeline._ensure_pool

async def _patched(self):
    pool = await _orig_build(self)
    strong = pool.providers[ModelRole.STRONG]
    small = pool.providers[ModelRole.SMALL]
    triage = json.dumps({"domain": "testing", "search_queries": [], "key_citations": []})
    survey = json.dumps({"selected": [], "state_of_the_art_notes": "", "missing_references": []})
    section_comment = json.dumps({"comments": [
        {"title": "Unproven claim", "paragraph_anchor": "Everything here is stable and true.",
         "quote": "Everything here is stable and true.", "message": "Prove or hedge.", "score": 0.7,
         "category": "math"}]})
    challenge = json.dumps({"validated": [
        {"title": "Unproven claim", "paragraph_anchor": "Everything here is stable and true.",
         "quote": "Everything here is stable and true.", "message": "Prove or hedge.", "score": 0.7,
         "category": "math", "verdict": "kept", "verdict_reason": "ok"}],
        "new_comments": []})
    bib = json.dumps({"entries": [], "missing_key_references": []})
    overall = json.dumps({"paper_summary": "A smoke paper.",
                          "overall_feedback": "## Claim\n\nUnproven.",
                          "comments": [{"title": "Unproven claim",
                                        "paragraph_anchor": "Everything here is stable and true.",
                                        "quote": "Everything here is stable and true.",
                                        "message": "Prove or hedge.", "score": 0.7, "category": "math"}]})
    final = json.dumps({"comments": [{"title": "Unproven claim",
                                      "paragraph_anchor": "Everything here is stable and true.",
                                      "quote": "Everything here is stable and true.",
                                      "message": "Prove or hedge.", "score": 0.7, "category": "math"}],
                        "overall_feedback": "## Claim\n\nUnproven (validated).",
                        "paper_summary": "A smoke paper.",
                        "validator_notes": "checked"})
    wp_verify = json.dumps({"comments": [
        {"title": "WP: intro overclaims", "paragraph_anchor": "Everything here is stable and true.",
         "quote": "Everything here is stable and true.", "message": "Intro asserts what the body never establishes.",
         "score": 0.6, "category": "consistency"}]})
    wp_challenge = json.dumps({"validated": [
        {"title": "WP: intro overclaims", "paragraph_anchor": "Everything here is stable and true.",
         "quote": "Everything here is stable and true.", "message": "Intro asserts what the body never establishes.",
         "score": 0.6, "category": "consistency", "verdict": "kept", "verdict_reason": "real"}],
        "new_comments": []})
    strong.queue(triage, challenge, challenge, wp_verify, wp_challenge, overall, final)
    small.queue(survey, section_comment, section_comment, bib)
    return pool

orch.ReviewPipeline._ensure_pool = _patched

# the paper
paper = Path("/tmp/or-smoke/paper.md")
paper.write_text("""# Smoke Test Paper

## 1. Introduction

Everything here is stable and true.

## 2. Method

We assume the result.

## References

[1] Someone, A. (2020). A title. Journal of Tests, 1(1), 1-2.
""")

import uuid as _uuid
boundary = "----smoke" + _uuid.uuid4().hex
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="paper"; filename="paper.md"\r\n'
    f"Content-Type: text/markdown\r\n\r\n"
).encode() + paper.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
resp_data = _post("/api/reviews", body, f"multipart/form-data; boundary={boundary}")
run_id = resp_data["run_id"]
print("run started:", run_id)

# 4. poll for completion
for _ in range(100):
    sf = Path(f"/tmp/or-smoke/runs/{run_id}/state.json")
    if sf.exists():
        st = json.loads(sf.read_text())
        if st["status"] in ("completed", "failed"):
            print("run ended:", st["status"], (st.get("error") or "")[:200])
            break
    time.sleep(0.3)
else:
    raise SystemExit("run did not finish")

assert st["status"] == "completed", "expected completed run"
report = json.loads(Path(f"/tmp/or-smoke/runs/{run_id}/report.json").read_text())
assert report["comments"] and report["comments"][0]["score"] >= 0.7
assert (Path(f"/tmp/or-smoke/runs/{run_id}") / "report.md").exists()
print("report.json + report.md present; comments:", len(report["comments"]))

# 5. report endpoints
assert json.loads(_get(f"/api/reviews/{run_id}/report"))["paper_title"].startswith("Smoke")
assert "Unproven claim" in _get(f"/api/reviews/{run_id}/report.md")
assert "Unproven claim" in _get(f"/review/{run_id}")
print("endpoints OK")
print("SMOKE OK")
