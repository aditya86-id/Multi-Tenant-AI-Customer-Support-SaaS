#!/usr/bin/env python3
"""
Runs the eval cases in dataset.py against a live backend.

Usage:
    python3 run_evals.py

Env vars:
    BACKEND_URL   default http://localhost:8000

What it does, in order:
    1. Creates (or logs into, if it already exists) a fixed "acme-eval"
       tenant -- this is a throwaway tenant that exists only for evals,
       never real data.
    2. Uploads the two sample KB docs if they aren't already ingested,
       and polls until they're "ready".
    3. Runs every case in EVAL_CASES against POST /api/v1/query and checks:
       - for kb_covered cases: the answer contains at least one expected
         keyword, AND it did not escalate
       - for explicit_human / out_of_scope cases: it escalated
    4. Prints a pass/fail table and exits non-zero if anything failed, so
       this can be wired into CI later without changes.

No third-party dependencies on purpose -- stdlib only (urllib), so this
runs anywhere Python 3 does, with nothing to install first.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib import error, request

from dataset import EVAL_CASES

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
TENANT_SLUG = "acme-eval"
TENANT_NAME = "Acme Eval Co"
ADMIN_EMAIL = "eval-admin@example.com"
ADMIN_PASSWORD = "EvalPassword123!"
SAMPLE_KB_DIR = Path(__file__).parent / "sample_kb"
INGEST_TIMEOUT_SECONDS = 60


def _request(method: str, path: str, token: str | None = None, json_body: dict | None = None):
    url = f"{BACKEND_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(json_body).encode() if json_body is not None else None
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"detail": body}


def _upload_file(path: Path, token: str):
    boundary = uuid.uuid4().hex
    filename = path.name
    content = path.read_bytes()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

    req = request.Request(
        f"{BACKEND_URL}/api/v1/documents",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_or_create_eval_tenant() -> str:
    """Returns an admin access token for the eval tenant, creating it if needed."""
    status, body = _request(
        "POST",
        "/api/v1/auth/signup",
        json_body={
            "tenant_name": TENANT_NAME,
            "tenant_slug": TENANT_SLUG,
            "admin_email": ADMIN_EMAIL,
            "admin_password": ADMIN_PASSWORD,
        },
    )
    if status == 201:
        print(f"Created eval tenant '{TENANT_SLUG}'")
        return body["access_token"]

    # Already exists -- log in instead.
    status, body = _request(
        "POST",
        "/api/v1/auth/login",
        json_body={"tenant_slug": TENANT_SLUG, "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if status != 200:
        print(f"FATAL: could not create or log into eval tenant: {body}", file=sys.stderr)
        sys.exit(2)
    print(f"Reusing existing eval tenant '{TENANT_SLUG}'")
    return body["access_token"]


def ensure_kb_ingested(token: str) -> None:
    status, docs = _request("GET", "/api/v1/documents", token=token)
    existing_filenames = {d["filename"] for d in docs} if status == 200 else set()

    sample_files = sorted(SAMPLE_KB_DIR.glob("*.md"))
    uploaded_any = False
    for f in sample_files:
        if f.name in existing_filenames:
            continue
        print(f"Uploading {f.name}...")
        _upload_file(f, token)
        uploaded_any = True

    if not uploaded_any:
        print("Sample KB already ingested, skipping upload.")

    print("Waiting for ingestion to reach 'ready'...")
    deadline = time.time() + INGEST_TIMEOUT_SECONDS
    while time.time() < deadline:
        status, docs = _request("GET", "/api/v1/documents", token=token)
        statuses = {d["filename"]: d["status"] for d in docs}
        if all(statuses.get(f.name) == "ready" for f in sample_files):
            print("All sample KB documents are ready.")
            return
        failed = {name: s for name, s in statuses.items() if s == "failed"}
        if failed:
            print(f"FATAL: ingestion failed for: {failed}", file=sys.stderr)
            sys.exit(2)
        time.sleep(2)

    print("FATAL: timed out waiting for KB ingestion", file=sys.stderr)
    sys.exit(2)


def run_case(case: dict) -> tuple[bool, str]:
    status, body = _request(
        "POST",
        "/api/v1/query",
        json_body={"tenant_slug": TENANT_SLUG, "message": case["question"]},
    )
    if status != 200:
        return False, f"request failed ({status}): {body}"

    answer = body.get("answer", "")
    escalated = body.get("escalated", False)
    notes = []
    ok = True

    if escalated != case["expect_escalate"]:
        ok = False
        notes.append(f"escalation mismatch (expected {case['expect_escalate']}, got {escalated})")

    if case["expect_keywords"]:
        answer_lower = answer.lower()
        if not any(kw.lower() in answer_lower for kw in case["expect_keywords"]):
            ok = False
            notes.append(f"none of expected keywords {case['expect_keywords']} found in answer")

    detail = "; ".join(notes) if notes else f"answer: {answer[:80]}..."
    return ok, detail


def main() -> None:
    token = get_or_create_eval_tenant()
    ensure_kb_ingested(token)

    print("\nRunning eval cases...\n")
    results = []
    for case in EVAL_CASES:
        ok, detail = run_case(case)
        results.append((case["id"], case["category"], ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {case['id']} ({case['category']}) -- {detail}")

    passed = sum(1 for _, _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
