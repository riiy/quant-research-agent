"""Constrained hypothesis discovery via OpenAI Responses API."""
from __future__ import annotations

import json
import os
from urllib import error, request

from .models import Candidate, SOURCES, seed_candidate


def load_env_file(filepath=".env"):
    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # 跳过空行和以 # 开头的注释行
            if not line or line.startswith("#") or "=" not in line:
                continue

            # 使用 split("=", 1) 确保只按第一个等号分割
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            # 去除值两端的单引号或双引号
            if (value.startswith('"') and value.endswith('"')) or \
               (value.startswith("'") and value.endswith("'")):
                value = value[1:-1]

            # 注册到环境变量（使用 os.environ.setdefault 可避免覆盖已有环境变量）
            os.environ[key] = value

# 调用函数加载
load_env_file(".env")


API_URL = os.getenv("OPENAI_API_URL", "https://api.openai.com/v1/responses")


def discover(mode: str = "api") -> tuple[Candidate, dict]:
    """Return one auditable hypothesis chosen *before* looking at BTC returns.

    seed mode is exclusively for offline integration testing, not autonomous discovery.
    """
    if mode == "seed":
        return seed_candidate(), {"mode": "seed", "model": None, "usage": {}, "is_ai_discovery": False}
    if mode != "api":
        raise ValueError("mode must be 'api' or 'seed'")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for --mode api; Plus is not an API key")
    model = os.getenv("QUANT_MODEL", "gpt-6-luna")
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "rationale": {"type": "string"},
            "family": {"type": "string", "enum": ["sma", "momentum", "breakout"]},
            "params": {"anyOf": [
                {"type": "object", "properties": {"fast": {"type": "integer"}, "slow": {"type": "integer"}}, "required": ["fast", "slow"], "additionalProperties": False},
                {"type": "object", "properties": {"lookback": {"type": "integer"}}, "required": ["lookback"], "additionalProperties": False},
                {"type": "object", "properties": {"entry": {"type": "integer"}, "exit": {"type": "integer"}}, "required": ["entry", "exit"], "additionalProperties": False},
            ]},
            "source_ids": {"type": "array", "items": {"type": "string", "enum": list(SOURCES)}},
        }, "required": ["title", "rationale", "family", "params", "source_ids"],
    }
    prompt = (
        "You are an evidence-first quantitative researcher. Generate exactly ONE testable "
        "BTCUSDT SPOT DAILY long-only hypothesis inspired by the source notes below. "
        "Do not claim that futures evidence establishes BTC alpha. No data mining, "
        "no parameter search, no fabricated references. Choose a simple family. "
        "sma: fast integer 20..100 and slow integer 120..250 (fast<slow). "
        "momentum: lookback integer 60..250. "
        "breakout: entry integer 20..150 and exit integer 10..80 (exit<entry). "
        "Return the required JSON object. Sources: " + json.dumps(SOURCES, ensure_ascii=False)
    )
    body = {
        "model": model, "instructions": prompt,
        "input": [{"role": "user", "content": [{"type": "input_text",
                 "text": "Select one hypothesis, articulate its economic rationale and likely failure modes."}]}],
        "max_output_tokens": 800,
        "text": {"format": {"type": "json_schema", "name": "candidate", "strict": True, "schema": schema}},
    }
    req = request.Request(API_URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=45) as r:
            response = json.load(r)
    except error.HTTPError as e:
        # Avoid logging request headers or credentials.
        raise RuntimeError(f"OpenAI HTTP {e.code} (check model access and API account)") from None
    if response.get("status") not in (None, "completed"):
        raise RuntimeError(f"Model response not completed: {response.get('status')}")
    fragments = [c.get("text", "") for item in response.get("output", [])
                 for c in item.get("content", []) if c.get("type") == "output_text"]
    if not fragments:
        raise RuntimeError("No JSON response from model")
    candidate = Candidate.from_dict(json.loads("".join(fragments)))
    return candidate, {"mode": "api", "model": model, "usage": response.get("usage", {}),
                       "response_id": response.get("id"), "is_ai_discovery": True}
