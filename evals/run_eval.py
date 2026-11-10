"""Model comparison evals for card summaries (Plane A) and chat (Plane B).

Compares the current Claude models against Amazon Nova on the app's REAL prompts
and tool schema (imported from `shared`, not copied), with objective checks plus
a BLIND side-by-side report for human grading (no LLM judge, by design).

    uv run evals/run_eval.py summaries [--n 30]   # RSS pull -> 3 models
    uv run evals/run_eval.py chat                 # 25 questions x 5 models
    uv run evals/run_eval.py report               # results/report.md + grades.csv
    uv run evals/run_eval.py score                # read grades.csv, reveal winners

Outputs go to evals/results/ (gitignored). Claude calls cost real money (Marketplace
billing is NOT covered by credits): a full run is roughly $0.30-0.60; Nova is credit-covered.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from botocore.exceptions import ClientError

from chat.retriever import DynamoCardRetriever
from shared.bedrock import CARD_TOOL, bedrock_client
from shared.bedrock import SYSTEM as SUMMARY_SYSTEM
from shared.chat import SYSTEM as CHAT_SYSTEM
from shared.chat import _context_block
from shared.config import (
    FEEDS,
    HAIKU_INPUT_USD_PER_1M,
    HAIKU_MODEL_ID,
    HAIKU_OUTPUT_USD_PER_1M,
    SONNET_MODEL_ID,
    TOP_K,
)
from shared.feeds import RawItem, discover

HERE = Path(__file__).parent
OUT = HERE / "results"
SEED = 7

# name -> (model id, USD per 1M input, USD per 1M output).
# Nova prices are the rates on this account's own Nov-2026 bill (Nova 2 Lite derived
# from usage-type quantities). Sonnet is Anthropic's list price (not verified here).
MODELS: dict[str, tuple[str, float, float]] = {
    "haiku-4.5": (HAIKU_MODEL_ID, HAIKU_INPUT_USD_PER_1M, HAIKU_OUTPUT_USD_PER_1M),
    "sonnet-4.6": (SONNET_MODEL_ID, 3.0, 15.0),
    "nova-lite": ("us.amazon.nova-lite-v1:0", 0.06, 0.24),
    "nova-2-lite": ("us.amazon.nova-2-lite-v1:0", 0.33, 2.75),
    "nova-pro": ("us.amazon.nova-pro-v1:0", 0.80, 3.20),
}
SUMMARY_MODELS = ["haiku-4.5", "nova-lite", "nova-2-lite"]
CHAT_MODELS = ["sonnet-4.6", "haiku-4.5", "nova-pro", "nova-2-lite", "nova-lite"]

REFUSAL = re.compile(
    r"(does not|doesn't|do not|don't|did not|didn't) (contain|include|have|cover|mention)|"
    r"no (information|mention|relevant)|not (covered|mentioned|in the (provided )?(context|cards))|"
    r"(cannot|can't|couldn't|could not|unable to) (find|answer|provide)|isn't (covered|in)",
    re.IGNORECASE,
)


def cost_usd(name: str, tin: int, tout: int) -> float:
    _, pin, pout = MODELS[name]
    return (tin * pin + tout * pout) / 1_000_000


def converse(name: str, system: str, user: str, max_tokens: int, tool: bool = False, temp: float = 0.2):
    kwargs = {
        "modelId": MODELS[name][0],
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": [{"text": user}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temp},
    }
    if tool:
        kwargs["toolConfig"] = {"tools": [CARD_TOOL], "toolChoice": {"tool": {"name": "emit_card"}}}
    for attempt in range(4):
        try:
            t0 = time.perf_counter()
            resp = bedrock_client().converse(**kwargs)
            return resp, time.perf_counter() - t0
        except ClientError as e:
            if e.response["Error"]["Code"] in ("ThrottlingException", "ModelTimeoutException") and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
    raise RuntimeError("unreachable")


def ungrounded_numbers(output: str, source: str) -> list[str]:
    """Figures in the output that never appear in the source: a cheap fabrication proxy."""
    def nums(s: str) -> set[str]:
        return {n.rstrip(".") for n in re.findall(r"\d+(?:[.,]\d+)*", s.replace(",", "")) if len(n) >= 2 or "." in n}
    return sorted(nums(output) - nums(source))


# ------------------------------------------------------------------ summaries

def summary_checks(card: dict, source_text: str) -> dict:
    summary = card.get("summary") or ""
    tags = card.get("tags")
    take = card.get("takeaways", [])
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", summary.strip()) if s]
    return {
        "required_fields": all(isinstance(card.get(k), t) for k, t in
                               (("title", str), ("summary", str), ("tags", list), ("type", str), ("relevance", int))),
        "sentences_2_4": 2 <= len(sentences) <= 4,
        "tags_3_6_lower": isinstance(tags, list) and 3 <= len(tags) <= 6
                          and all(isinstance(t, str) and t == t.lower() for t in tags),
        "type_valid": card.get("type") in ("news", "paper", "project", "concept", "release"),
        "relevance_1_10": isinstance(card.get("relevance"), int) and 1 <= card["relevance"] <= 10,
        "takeaways_0_3": isinstance(take, list) and len(take) <= 3,
        "no_ungrounded_numbers": not ungrounded_numbers(summary, source_text),
    }


def run_summaries(n: int) -> None:
    OUT.mkdir(exist_ok=True)
    items_path = OUT / "summary_items.json"
    if items_path.exists():
        items = [RawItem(**i) for i in json.loads(items_path.read_text())]
    else:
        pool = [i for i in discover(FEEDS, 10) if len(i.snippet) >= 200]
        random.Random(SEED).shuffle(pool)
        items = pool[:n]
        items_path.write_text(json.dumps([i.__dict__ for i in items], indent=2))
    print(f"{len(items)} items x {len(SUMMARY_MODELS)} models")
    rows = []
    for item in items:
        # Mirrors shared.bedrock.summarize_with_usage's user message.
        user = (f"Source: {item.source}\nOriginal title: {item.title}\nPublished: {item.published or 'unknown'}\n"
                f"URL: {item.url}\n\nContent snippet:\n{item.snippet or '(no snippet provided)'}")
        for name in SUMMARY_MODELS:
            row: dict = {"item_url": item.url, "model": name}
            try:
                resp, dt = converse(name, SUMMARY_SYSTEM, user, 700, tool=True)
                usage = resp.get("usage", {})
                card = next((b["toolUse"]["input"] for b in resp["output"]["message"]["content"] if "toolUse" in b), None)
                row.update(latency=dt, tokens_in=usage.get("inputTokens", 0), tokens_out=usage.get("outputTokens", 0))
                row["cost"] = cost_usd(name, row["tokens_in"], row["tokens_out"])
                if card is None:
                    row.update(card=None, error="no toolUse block")
                    row["checks"] = {}
                else:
                    row["card"] = card
                    row["checks"] = summary_checks(card, item.title + " " + item.snippet)
                    row["ungrounded"] = ungrounded_numbers(card.get("summary", ""), item.title + " " + item.snippet)
            except Exception as e:  # noqa: BLE001 - one bad call must not kill the run
                row.update(card=None, error=f"{type(e).__name__}: {str(e)[:160]}", checks={})
            rows.append(row)
        print(f"  done: {item.title[:60]}")
    (OUT / "summaries.json").write_text(json.dumps(rows, indent=2))


# ----------------------------------------------------------------------- chat

def chat_checks(q: dict, answer: str, hits: list[dict]) -> dict:
    cited = {int(c) for c in re.findall(r"\[(\d+)\]", answer)}
    valid = all(1 <= c <= len(hits) for c in cited)
    ctx = " ".join(h["title"] + " " + h["summary"] for h in hits)
    if q["answerable"]:
        cited_urls = {hits[c - 1]["url"] for c in cited if 1 <= c <= len(hits)}
        return {
            "has_citation": bool(cited),
            "citations_valid": valid,
            "cites_expected_card": bool(cited_urls & set(q["expect_urls"])),
            "no_ungrounded_numbers": not ungrounded_numbers(answer, ctx + " " + q["question"]),
            "not_a_refusal": not REFUSAL.search(answer),
        }
    return {"refuses": bool(REFUSAL.search(answer)), "no_citations": not cited,
            "no_ungrounded_numbers": not ungrounded_numbers(answer, ctx + " " + q["question"])}


def run_chat() -> None:
    OUT.mkdir(exist_ok=True)
    questions = json.loads((HERE / "chat_questions.json").read_text())
    retriever = DynamoCardRetriever()
    ctx_path = OUT / "chat_context.json"
    ctxs = json.loads(ctx_path.read_text()) if ctx_path.exists() else {}
    for q in questions:  # retrieve ONCE so every model sees identical context
        if q["id"] not in ctxs:
            ctxs[q["id"]] = [c for c, _ in retriever.search(q["question"], TOP_K)]
    ctx_path.write_text(json.dumps(ctxs, indent=2))
    rows = []
    for q in questions:
        hits = ctxs[q["id"]]
        recall = (not q["answerable"]) or bool({h["url"] for h in hits} & set(q["expect_urls"]))
        # Mirrors shared.chat.answer_question (minus the Bedrock cachePoint: the prompt is far
        # below Nova's 1K-token minimum, so it would be a no-op there).
        user = f"Context cards:\n\n{_context_block([(h, 0) for h in hits])}\n\nUser question: {q['question']}"
        for name in CHAT_MODELS:
            row: dict = {"qid": q["id"], "model": name, "retrieval_hit": recall}
            try:
                resp, dt = converse(name, CHAT_SYSTEM, user, 800, temp=0.3)
                answer = resp["output"]["message"]["content"][0]["text"]
                usage = resp.get("usage", {})
                row.update(answer=answer, latency=dt, tokens_in=usage.get("inputTokens", 0),
                           tokens_out=usage.get("outputTokens", 0), chars=len(answer))
                row["cost"] = cost_usd(name, row["tokens_in"], row["tokens_out"])
                row["checks"] = chat_checks(q, answer, hits)
            except Exception as e:  # noqa: BLE001
                row.update(answer=None, error=f"{type(e).__name__}: {str(e)[:160]}", checks={})
            rows.append(row)
        print(f"  done: {q['id']} {q['question'][:50]}")
    (OUT / "chat.json").write_text(json.dumps(rows, indent=2))


# --------------------------------------------------------------------- report

def aggregate(rows: list[dict], models: list[str]) -> list[str]:
    out = ["| model | n | errors | " + " | ".join(sorted({k for r in rows for k in r["checks"]})) +
           " | p50 s | p95 s | $/call | $/1k calls |", ]
    keys = sorted({k for r in rows for k in r["checks"]})
    out.append("|" + "---|" * (len(keys) + 7))
    for m in models:
        mine = [r for r in rows if r["model"] == m]
        ok = [r for r in mine if r["checks"]]
        lat = sorted(r["latency"] for r in mine if "latency" in r)
        cost = statistics.mean(r["cost"] for r in mine if "cost" in r) if any("cost" in r for r in mine) else 0
        pct = [f"{100 * sum(r['checks'].get(k, False) for r in ok if k in r['checks']) / max(1, sum(k in r['checks'] for r in ok)):.0f}%" for k in keys]
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else 0
        out.append(f"| {m} | {len(mine)} | {len(mine) - len(ok)} | " + " | ".join(pct) +
                   f" | {statistics.median(lat) if lat else 0:.1f} | {p95:.1f} | ${cost:.5f} | ${cost * 1000:.2f} |")
    return out


def run_report() -> None:
    rng = random.Random(SEED)
    key: dict[str, dict[str, str]] = {}
    lines = ["# Model eval report", "", ("Auto-check pass rates are objective but shallow; grade the blind outputs below "
             "in `grades.csv` (score 1-5 per item and label), then run `score`."), ""]
    grades = [("id", "label", "score")]
    chat_questions = {q["id"]: q for q in json.loads((HERE / "chat_questions.json").read_text())}

    sp, cp = OUT / "summaries.json", OUT / "chat.json"
    if sp.exists():
        rows = json.loads(sp.read_text())
        items = {i["url"]: i for i in json.loads((OUT / "summary_items.json").read_text())}
        lines += ["## Summaries - auto checks", "", *aggregate(rows, SUMMARY_MODELS), "", "## Summaries - blind side by side", ""]
        for url, item in items.items():
            outs = [r for r in rows if r["item_url"] == url and r.get("card")]
            rng.shuffle(outs)
            key[url] = {chr(65 + i): r["model"] for i, r in enumerate(outs)}
            lines += [f"### {item['title']}", f"*{item['source']}* - id: `{url}`", "", "> " + item["snippet"][:700].replace("\n", " "), ""]
            for i, r in enumerate(outs):
                c = r["card"]
                lines += [f"**{chr(65 + i)}** - {c.get('title')}", f"{c.get('summary')}",
                          f"- takeaways: {c.get('takeaways')}", f"- tags: {c.get('tags')} | type: {c.get('type')} | relevance: {c.get('relevance')}"]
                if r.get("ungrounded"):
                    lines.append(f"- numbers not in source: {r['ungrounded']}")
                lines.append("")
                grades.append((url, chr(65 + i), ""))
    if cp.exists():
        rows = json.loads(cp.read_text())
        ctxs = json.loads((OUT / "chat_context.json").read_text())
        recall = [r["retrieval_hit"] for r in rows if r["model"] == CHAT_MODELS[0] and chat_questions[r["qid"]]["answerable"]]
        lines += ["## Chat - auto checks", "", (f"Retrieval recall (expected card in top-{TOP_K}, model-independent): "
                  f"{100 * sum(recall) / max(1, len(recall)):.0f}%"), ""]
        ans = [r for r in rows if chat_questions[r["qid"]]["answerable"]]
        una = [r for r in rows if not chat_questions[r["qid"]]["answerable"]]
        lines += ["**Answerable questions**", "", *aggregate(ans, CHAT_MODELS), "", "**Unanswerable questions (should refuse, no citations)**", "",
                  *aggregate(una, CHAT_MODELS), "", "## Chat - blind side by side", ""]
        for qid, q in chat_questions.items():
            outs = [r for r in rows if r["qid"] == qid and r.get("answer")]
            rng.shuffle(outs)
            key[qid] = {chr(65 + i): r["model"] for i, r in enumerate(outs)}
            titles = "; ".join(f"[{i + 1}] {h['title'][:50]}" for i, h in enumerate(ctxs[qid]))
            lines += [f"### {qid}: {q['question']}", f"{'answerable' if q['answerable'] else 'UNANSWERABLE (should decline)'} | context: {titles}", ""]
            for i, r in enumerate(outs):
                lines += [f"**{chr(65 + i)}**", r["answer"], ""]
                grades.append((qid, chr(65 + i), ""))
    OUT.mkdir(exist_ok=True)
    (OUT / "report.md").write_text("\n".join(lines))
    (OUT / "key.json").write_text(json.dumps(key, indent=2))
    with open(OUT / "grades.csv", "w", newline="") as f:
        csv.writer(f).writerows(grades)
    print(f"wrote {OUT / 'report.md'} and {OUT / 'grades.csv'}")


def run_score() -> None:
    key = json.loads((OUT / "key.json").read_text())
    per: dict[str, dict[str, list[float]]] = {}
    for r in csv.DictReader((OUT / "grades.csv").read_text().splitlines()):
        if not r["score"].strip():
            continue
        task = "chat" if r["id"][0] in "au" and len(r["id"]) == 3 else "summaries"
        per.setdefault(task, {}).setdefault(key[r["id"]][r["label"]], []).append(float(r["score"]))
    if not per:
        sys.exit("No scores in grades.csv yet.")
    for task, models in per.items():
        print(f"\n{task}: mean grade (1-5)")
        for m, s in sorted(models.items(), key=lambda kv: -statistics.mean(kv[1])):
            print(f"  {m:12} {statistics.mean(s):.2f}  (n={len(s)})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["summaries", "chat", "report", "score"])
    ap.add_argument("--n", type=int, default=30, help="summary items to sample")
    a = ap.parse_args()
    {"summaries": lambda: run_summaries(a.n), "chat": run_chat, "report": run_report, "score": run_score}[a.cmd]()
