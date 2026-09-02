#!/usr/bin/env python3
"""Export one Feishu experiment-planning step with auditable source metadata."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path


def fetch(wiki_token: str) -> dict:
    completed = subprocess.run(
        [
            "lark-cli", "docs", "+fetch", "--api-version", "v2",
            "--doc", wiki_token, "--doc-format", "markdown",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(completed.stdout)
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload["data"]["document"]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", required=True)
    parser.add_argument("--plan-wiki", required=True)
    parser.add_argument("--report-wiki", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    exported_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    targets = [
        ("plan", args.plan_wiki, "PLAN.md"),
        ("experiment_report", args.report_wiki, "EXPERIMENT_REPORT.md"),
    ]
    step_dir = root / args.step
    step_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "SOURCE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"] = [
        item for item in manifest["documents"] if item.get("step") != args.step
    ]
    for kind, wiki_token, filename in targets:
        document = fetch(wiki_token)
        content = document["content"]
        document_token = document["document_id"]
        revision_id = int(document["revision_id"])
        url = f"https://icnbwz7kd1ui.feishu.cn/wiki/{wiki_token}"
        front_matter = (
            "---\n"
            f"feishu_url: {url}\n"
            f"wiki_node_token: {wiki_token}\n"
            f"document_token: {document_token}\n"
            f"revision_id: {revision_id}\n"
            f"exported_at_utc: {exported_at}\n"
            f"source_content_sha256: {sha256_text(content)}\n"
            "---\n\n"
        )
        (step_dir / filename).write_text(front_matter + content.rstrip() + "\n", encoding="utf-8")
        manifest["documents"].append({
            "document_token": document_token,
            "feishu_url": url,
            "kind": kind,
            "path": f"{args.step}/{filename}",
            "revision_id": revision_id,
            "source_character_count": len(content),
            "source_content_sha256": sha256_text(content),
            "step": args.step,
            "wiki_node_token": wiki_token,
        })
    manifest["document_count"] = len(manifest["documents"])
    manifest["exported_at_utc"] = exported_at
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checksum_path = root / "SHA256SUMS"
    files = sorted(path for path in root.rglob("*") if path.is_file() and path != checksum_path)
    lines = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}" for path in files]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
