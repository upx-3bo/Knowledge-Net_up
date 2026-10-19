#!/usr/bin/env python3
"""人工初审后的结构化数据 → AI 二次质检 → 可选写入 Nebula。

推荐流程（蓝区开发 / 绿区导数据）:
  1) 用大模型对原始资料做第一轮筛选与技术点提取
  2) 人工审查，填入 research/templates 或自建 JSON（human_review.passed=true）
  3) 本脚本再跑一轮 AI 质检，输出报告与 revised JSON
  4) 确认无误后加 --commit 入库

用法:
  # 只审查，不写库（默认）
  python3 scripts/import_with_ai_review.py path/to/batch.json

  # 审查通过才写入
  python3 scripts/import_with_ai_review.py path/to/batch.json --commit

  # 强制写入（忽略 AI approved=false，仍会生成报告）
  python3 scripts/import_with_ai_review.py path/to/batch.json --commit --force

  # 跳过 LLM，仅规则检查（无 Key 时可用）
  python3 scripts/import_with_ai_review.py path/to/batch.json --rules-only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from backend.services.extractor import commit_extraction  # noqa: E402
from backend.services.import_review import (  # noqa: E402
    ai_review_extraction,
    collect_existing_names,
    load_batch_file,
    normalize_extraction,
    rule_check,
)
from backend.services.llm import LLMNotConfigured, llm_ready  # noqa: E402
from backend.store import GraphStore  # noqa: E402


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main() -> int:
    ap = argparse.ArgumentParser(description="AI 二次审查后导入知识图谱")
    ap.add_argument("input", type=Path, help="人工初审后的 JSON（单条 extract 或 batch.items）")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="审查报告输出目录（默认 research/import_runs/<时间戳>）",
    )
    ap.add_argument("--commit", action="store_true", help="审查通过后写入 Nebula")
    ap.add_argument("--force", action="store_true", help="即使 AI 未批准也写入（危险）")
    ap.add_argument("--rules-only", action="store_true", help="只做规则检查，不调用大模型")
    ap.add_argument("--no-graph-context", action="store_true", help="审查时不读取库内已有名称")
    args = ap.parse_args()

    if not args.input.is_file():
        print(f"ERROR: 文件不存在 {args.input}")
        return 2

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    items = load_batch_file(raw)
    if not items:
        print("ERROR: 没有可导入条目")
        return 2

    # human gate
    blocked = []
    for it in items:
        hr = it.get("human_review") or {}
        if hr and hr.get("passed") is False:
            blocked.append(it["id"])
    if blocked:
        print("ERROR: 以下条目人工标记未通过，拒绝导入:", ", ".join(blocked))
        return 1

    out_dir = args.out_dir or (ROOT / "research" / "import_runs" / _utc_stamp())
    out_dir.mkdir(parents=True, exist_ok=True)

    store = None
    existing = {"domain": [], "subdomain": [], "technology": [], "material": []}
    if args.commit or not args.no_graph_context:
        try:
            store = GraphStore()
            if not args.no_graph_context:
                existing = collect_existing_names(store)
        except Exception as exc:
            if args.commit:
                print(f"ERROR: 无法连接 Nebula: {exc}")
                return 1
            print(f"WARN: 无法读取图库上下文（继续审查）: {exc}")

    if not args.rules_only and not llm_ready():
        print("ERROR: LLM 未配置。请在 .env 填写 LLM_API_KEY / LLM_API_URL，或加 --rules-only")
        return 1

    run_report: dict = {
        "input": str(args.input),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "rules_only" if args.rules_only else "ai_review",
        "commit": bool(args.commit),
        "force": bool(args.force),
        "items": [],
    }

    all_ok = True
    for it in items:
        item_id = it["id"]
        print(f"\n=== 审查 {item_id} ===")
        extraction = normalize_extraction(it["extraction"])
        source = it.get("source") or {}

        if args.rules_only:
            issues = rule_check(extraction)
            approved = not any(i["severity"] == "error" for i in issues)
            review = {
                "approved": approved,
                "score": 100 if approved else 40,
                "summary": "仅规则检查" + ("：通过" if approved else "：存在错误"),
                "issues": issues,
                "revised": extraction,
                "rule_issues": issues,
                "original": extraction,
            }
        else:
            try:
                review = ai_review_extraction(
                    extraction,
                    source_meta=source,
                    existing_names=existing,
                )
            except LLMNotConfigured as exc:
                print(f"ERROR: {exc}")
                return 1
            except Exception as exc:
                print(f"ERROR: AI 审查失败 {item_id}: {exc}")
                all_ok = False
                run_report["items"].append({"id": item_id, "error": str(exc)})
                continue

        item_dir = out_dir / item_id
        item_dir.mkdir(parents=True, exist_ok=True)
        (item_dir / "original.json").write_text(
            json.dumps(review["original"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (item_dir / "revised.json").write_text(
            json.dumps(review["revised"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (item_dir / "review.json").write_text(
            json.dumps(
                {
                    "approved": review["approved"],
                    "score": review["score"],
                    "summary": review["summary"],
                    "issues": review["issues"],
                    "source": source,
                    "human_review": it.get("human_review") or {},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"approved={review['approved']} score={review['score']}")
        print(f"summary: {review['summary']}")
        for iss in review["issues"][:12]:
            print(f"  - [{iss.get('severity')}] {iss.get('field')}: {iss.get('message')}")
            if iss.get("suggestion"):
                print(f"      → {iss['suggestion']}")

        written = None
        should_commit = args.commit and (review["approved"] or args.force)
        if args.commit and not review["approved"] and not args.force:
            print("SKIP commit: AI 未批准（可用 --force 强制，或改 revised 后再导）")
            all_ok = False
        if should_commit:
            if store is None:
                store = GraphStore()
            written = commit_extraction(review["revised"], store=store)
            print(
                "COMMIT ok:",
                f"tech={len(written.get('technologies') or [])}",
                f"mat={len(written.get('materials') or [])}",
                f"supports={written.get('supports_links')}",
            )
            # refresh names for next item dedup
            if not args.no_graph_context:
                existing = collect_existing_names(store)

        run_report["items"].append(
            {
                "id": item_id,
                "approved": review["approved"],
                "score": review["score"],
                "summary": review["summary"],
                "issue_count": len(review["issues"]),
                "committed": bool(written),
                "paths": {
                    "original": str(item_dir / "original.json"),
                    "revised": str(item_dir / "revised.json"),
                    "review": str(item_dir / "review.json"),
                },
            }
        )

    report_path = out_dir / "run_report.json"
    report_path.write_text(json.dumps(run_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告目录: {out_dir}")
    print(f"汇总: {report_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
