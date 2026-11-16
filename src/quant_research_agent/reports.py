"""Human-readable and machine-readable research archives."""
from __future__ import annotations

import json
from pathlib import Path

from .models import SOURCES


def write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate, meta, result = payload["candidate"], payload["metadata"], payload["result"]
    lines = [f"# Research: {candidate['title']}", "",
             f"- Status: **{payload['status']}**", "- Market: BTCUSDT spot, 1d, long-only",
             "- Trading permission: **NONE**", "- Account simulation permission: **NONE**",
             f"- Discovery: {meta['discovery']['mode']} (AI discovery: {meta['discovery']['is_ai_discovery']})",
             f"- Data provenance: {meta['data']['source']}", f"- Data SHA256: `{meta['data']['sha256']}`",
             f"- Rules: `{candidate['family']} {json.dumps(candidate['params'], sort_keys=True)}`",
             "", "## Economic hypothesis", "", candidate["rationale"], "", "## Sources", ""]
    for key in candidate["source_ids"]:
        item = SOURCES[key]
        lines.append(f"- [{item['title']}]({item['url']}): {item['scope']}")
    lines += ["", "## Frozen validation protocol", "", "- Development: 2018-01-01 to 2023-12-31",
              "- Validation: 2024-01-01 to 2024-12-31",
              "- Sealed holdout (only by explicit `finalize`): 2025-01-01 to 2025-12-31",
              "- Prior close signal, next open execution; baseline buys first open",
              "- Base fee 0.10%/side, slippage 0.05%/side; double-cost stress test",
              "- Independent cash reset in every evaluation window", "", "## Results", ""]
    for key in ("development", "validation", "validation_double_cost", "holdout", "holdout_double_cost"):
        if key not in result:
            continue
        s = result[key]
        lines += [f"### {key}", "", f"- Period: {s['start']} .. {s['end']} ({s['days']} days)",
                  f"- Strategy return (net): {s['total_return']:.2%}",
                  f"- Buy-and-hold (net): {s['buy_hold_return']:.2%}",
                  f"- Net excess (difference of period returns): {s['excess_return']:.2%}",
                  f"- Max drawdown: {s['max_drawdown']:.2%}",
                  f"- Entries / completed exits: {s['entries']} / {s['completed_trades']}", ""]
    lines += ["## Decision", ""] + [f"- {reason}" for reason in result.get("reasons", [])]
    lines += ["", "**A research outcome is not evidence of stable alpha or permission to trade.**", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    path.with_suffix(".json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
