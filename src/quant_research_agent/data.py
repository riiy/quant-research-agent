"""Reproducible BTCUSDT daily Binance public-data ingestion."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
from urllib import request
import zipfile

BASE = "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/"
DAY = timedelta(days=1)


@dataclass(frozen=True)
class Bar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float


def parse_timestamp(number: str) -> date:
    n = int(number)
    # Binance spot archives switch from milliseconds to microseconds in 2025.
    seconds = n / (1_000_000 if n >= 10**15 else 1_000)
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    if dt.hour != 0 or dt.minute != 0 or dt.second != 0:
        raise ValueError("Daily UTC bar does not start at 00:00")
    return dt.date()


def parse_row(row: list[str]) -> Bar:
    if len(row) < 6:
        raise ValueError("Malformed Binance kline")
    day = parse_timestamp(row[0])
    o, h, l, c, v = (float(row[i]) for i in range(1, 6))
    if not all(map(math.isfinite, (o, h, l, c, v))) or min(o, h, l, c) <= 0 or v < 0:
        raise ValueError(f"Invalid price/volume {day}")
    if h < max(o, c, l) or l > min(o, c, h):
        raise ValueError(f"Inconsistent OHLC {day}")
    return Bar(day, o, h, l, c, v)


def verify_bars(bars: list[Bar], minimum: int = 1) -> None:
    if len(bars) < minimum:
        raise ValueError(f"Need at least {minimum} daily observations, got {len(bars)}")
    for prev, cur in zip(bars, bars[1:]):
        if cur.day != prev.day + DAY:
            raise ValueError(f"Missing/duplicate/out-of-order day: {prev.day} -> {cur.day}")


def load_csv(path: Path) -> list[Bar]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected = {"day", "open", "high", "low", "close", "volume"}
        if set(reader.fieldnames or []) != expected:
            raise ValueError("Expected columns: day,open,high,low,close,volume")
        bars = []
        for r in reader:
            day = date.fromisoformat(r["day"])
            bar = Bar(day, *(float(r[x]) for x in ("open", "high", "low", "close", "volume")))
            if not all(math.isfinite(x) for x in (bar.open, bar.high, bar.low, bar.close, bar.volume)):
                raise ValueError("Nonfinite OHLCV")
            if min(bar.open, bar.high, bar.low, bar.close) <= 0 or bar.volume < 0 or bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
                raise ValueError(f"Invalid OHLCV {day}")
            bars.append(bar)
    verify_bars(bars)
    return bars


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def months(start: str, end: str):
    sy, sm = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    if not (1 <= sm <= 12 and 1 <= em <= 12) or (sy, sm) > (ey, em):
        raise ValueError("Invalid month interval")
    y, m = sy, sm
    while (y, m) <= (ey, em):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def _fetch(url: str) -> bytes:
    # HTTPS-only fixed Binance host; never use arbitrary model-provided URLs.
    req = request.Request(url, headers={"User-Agent": "quant-research-agent/0.1"})
    with request.urlopen(req, timeout=30) as r:
        return r.read()


def fetch_month(month: str, cache: Path) -> tuple[list[Bar], dict]:
    name = f"BTCUSDT-1d-{month}.zip"
    archive, checksum_path = cache / name, cache / f"{name}.CHECKSUM"
    cache.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        archive.write_bytes(_fetch(BASE + name))
    if not checksum_path.exists():
        checksum_path.write_bytes(_fetch(BASE + name + ".CHECKSUM"))
    content = checksum_path.read_text(encoding="utf-8")
    match = re.fullmatch(r"\s*([0-9a-fA-F]{64})\s+\*?" + re.escape(name) + r"\s*", content)
    if not match:
        raise ValueError(f"Unexpected checksum format: {name}")
    digest = sha256_file(archive)
    if digest.lower() != match.group(1).lower():
        raise ValueError(f"Checksum mismatch for {name}")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if names != [name.replace(".zip", ".csv")]:
            raise ValueError("Unexpected archive contents")
        with z.open(names[0]) as f:
            bars = [parse_row(row) for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8"))]
    verify_bars(bars)
    if bars[0].day.strftime("%Y-%m") != month or bars[-1].day.strftime("%Y-%m") != month:
        raise ValueError(f"Month contents inconsistent: {month}")
    return bars, {"file": name, "sha256": digest}


def ingest(root: Path, start: str, end: str) -> Path:
    """Download completed archive months, check SHA256 and exact day continuity."""
    today = datetime.now(timezone.utc).date()
    if end >= today.strftime("%Y-%m"):
        raise ValueError("Only completed months may be ingested")
    data_dir = root / "data"
    all_bars: list[Bar] = []
    manifests = []
    for month in months(start, end):
        b, m = fetch_month(month, data_dir / "archive")
        all_bars.extend(b)
        manifests.append(m)
    verify_bars(all_bars)
    output = data_dir / "BTCUSDT-1d.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["day", "open", "high", "low", "close", "volume"])
        for b in all_bars:
            writer.writerow([b.day.isoformat(), b.open, b.high, b.low, b.close, b.volume])
    tmp.replace(output)
    manifest = {"source": "binance-public-data-spot-monthly", "symbol": "BTCUSDT", "interval": "1d",
                "first": str(all_bars[0].day), "last": str(all_bars[-1].day), "rows": len(all_bars),
                "csv_sha256": sha256_file(output), "archives": manifests}
    (data_dir / "BTCUSDT-1d.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return output


def load_research_data(path: Path) -> tuple[list[Bar], dict]:
    bars = load_csv(path)
    actual_hash = sha256_file(path)
    manifest_file = path.with_suffix(".manifest.json")
    if manifest_file.exists():
        manifest = json.loads(manifest_file.read_text())
        if actual_hash != manifest.get("csv_sha256") or manifest.get("rows") != len(bars):
            raise ValueError("Manifest mismatches CSV; data modified or incomplete")
    else:
        manifest = {"source": "unverified-local-csv"}
    return bars, {"sha256": actual_hash, "source": manifest["source"],
                  "first": str(bars[0].day), "last": str(bars[-1].day), "rows": len(bars)}


def prefix_hash(bars: list[Bar], end: date) -> str:
    """Freeze the exact pre-holdout OHLCV prefix across later dataset extensions."""
    digest = hashlib.sha256()
    for b in bars:
        if b.day > end:
            break
        digest.update((b.day.isoformat() + "," + ",".join(format(x, ".17g") for x in
                       (b.open, b.high, b.low, b.close, b.volume)) + "\n").encode())
    return digest.hexdigest()
