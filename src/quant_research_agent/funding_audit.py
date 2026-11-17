"""Research-only BTCUSDT USD-M perpetual funding archive quality gate.

This program only downloads/reads monthly funding *settlements* in 2020-2023.
No trade signal, spot return, model, broker API or holdout is accessed.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
from urllib import error, request
import zipfile

FIRST = date(2020, 1, 1)
END_EXCLUSIVE = date(2024, 1, 1)
SYMBOL = "BTCUSDT"
DATASET = "fundingRate"
ORIGIN = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/"
SCHEMA = ("calc_time", "funding_interval_hours", "last_funding_rate")
HOURS = (0, 8, 16)
MONTHLY_MAX_BYTES = 8_000_000
EXPECTED_INTERVAL_HOURS = 8
EXPECTED_DAYS = (END_EXCLUSIVE - FIRST).days
EXPECTED_ROWS = EXPECTED_DAYS * 3
PROTOCOL = "BTC_PERP_FUNDING_PRESSURE_v1_data_audit_2020_2023"


class FundingAuditError(ValueError):
    pass


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def months():
    for y in range(2020, 2024):
        for m in range(1, 13):
            yield f"{y:04d}-{m:02d}"


def _get_fixed(url: str) -> bytes:
    # URL assembled exclusively from frozen constants and validated YYYY-MM strings.
    if not url.startswith(ORIGIN) or not re.fullmatch(
        r"https://data\.binance\.vision/data/futures/um/monthly/fundingRate/BTCUSDT/"
        r"BTCUSDT-fundingRate-20(?:20|21|22|23)-(?:0[1-9]|1[0-2])\.zip(?:\.CHECKSUM)?", url
    ):
        raise FundingAuditError("Unexpected funding archive URL")
    req = request.Request(url, headers={"User-Agent": "quant-research-agent/0.1"})
    with request.urlopen(req, timeout=30) as response:
        payload = response.read(MONTHLY_MAX_BYTES + 1)
    if len(payload) > MONTHLY_MAX_BYTES:
        raise FundingAuditError("Monthly archive/checksum too large")
    return payload


def load_verified_archive(cache: Path, month: str, *, offline: bool) -> tuple[bytes, dict]:
    if month not in set(months()):
        raise FundingAuditError("Month outside frozen 2020-2023 interval")
    cache.mkdir(parents=True, exist_ok=True)
    filename = f"{SYMBOL}-{DATASET}-{month}.zip"
    archive = cache / filename
    checksum = cache / (filename + ".CHECKSUM")
    # Check the checksum first. Never trust an existing ZIP without it.
    for path in (checksum, archive):
        if not path.exists():
            if offline:
                raise FundingAuditError(f"Missing locally cached file (offline): {path}")
            data = _get_fixed(ORIGIN + path.name)
            temp = path.with_name(path.name + ".download")
            try:
                temp.write_bytes(data)
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
    content = checksum.read_text(encoding="utf-8-sig")
    m = re.fullmatch(r"\s*([0-9a-fA-F]{64})\s+\*?" + re.escape(filename) + r"\s*", content)
    if not m:
        raise FundingAuditError(f"Bad CHECKSUM format: {filename}")
    if archive.stat().st_size > MONTHLY_MAX_BYTES:
        raise FundingAuditError(f"Archive too large: {filename}")
    payload = archive.read_bytes()
    digest = sha256_bytes(payload)
    if digest.lower() != m.group(1).lower():
        raise FundingAuditError(f"Checksum mismatch for {filename}")
    return payload, {"file": filename, "sha256": digest, "month": month}


def read_month(payload: bytes, month: str) -> list[tuple[int, int, str]]:
    filename = f"{SYMBOL}-{DATASET}-{month}.csv"
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as z:
            infos = z.infolist()
            if len(infos) != 1 or infos[0].filename != filename:
                raise FundingAuditError(f"Unexpected ZIP contents for {month}")
            if infos[0].file_size > MONTHLY_MAX_BYTES:
                raise FundingAuditError(f"Decompressed file too large: {month}")
            with z.open(infos[0]) as f:
                raw = f.read(MONTHLY_MAX_BYTES + 1)
    except zipfile.BadZipFile as exc:
        raise FundingAuditError(f"Invalid ZIP file for {month}") from exc
    if len(raw) > MONTHLY_MAX_BYTES:
        raise FundingAuditError(f"Uncompressed CSV too large: {month}")
    try:
        data = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data, newline=""))
        if reader.fieldnames is None or tuple(s.strip() for s in reader.fieldnames) != SCHEMA:
            raise FundingAuditError(f"Unexpected funding CSV columns for {month}: {reader.fieldnames}")
        rows = []
        for line, row in enumerate(reader, start=2):
            if None in row or any(v is None for v in row.values()):
                raise FundingAuditError(f"Malformed row in {month}:{line}")
            stamp = int(row["calc_time"].strip())
            interval = int(row["funding_interval_hours"].strip())
            rate_text = row["last_funding_rate"].strip()
            rate = Decimal(rate_text)
            if not rate.is_finite() or abs(rate) >= 1:
                raise FundingAuditError(f"Out-of-range funding rate in {month}:{line}")
            # Strict UTC epoch millis. Extremely large (microsecond) timestamps fail.
            if stamp < 10**12 or stamp >= 10**14:
                raise FundingAuditError(f"Unexpected timestamp unit in {month}:{line}")
            dt = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc)
            if dt.strftime("%Y-%m") != month:
                raise FundingAuditError(f"Funding settlement belongs to another month: {month}:{line}")
            if interval <= 0 or interval > 24:
                raise FundingAuditError(f"Invalid funding interval in {month}:{line}")
            rows.append((stamp, interval, str(rate)))
    except (UnicodeDecodeError, InvalidOperation, OverflowError) as exc:
        raise FundingAuditError(f"Invalid data encoding/value in {month}") from exc
    except (ValueError, TypeError) as exc:
        if isinstance(exc, FundingAuditError):
            raise
        raise FundingAuditError(f"Invalid row content in {month}: {exc}") from exc
    if not rows:
        raise FundingAuditError(f"Empty monthly archive: {month}")
    return rows


def audit_rows(rows: list[tuple[int, int, str]], archive_meta: list[dict]) -> tuple[dict, list[tuple[int, int, str]]]:
    """No silent dedup, data padding, or interval repair; emit explicit failure diagnostics."""
    issues: list[dict] = []
    seen: set[int] = set()
    duplicate_times = []
    off_grid_times = []
    inconsistent_intervals = []
    out_of_order_count = 0
    prev = -1
    for stamp, interval, _ in rows:
        if stamp in seen:
            duplicate_times.append(stamp)
        seen.add(stamp)
        if stamp <= prev:
            out_of_order_count += 1
        prev = stamp
        dt = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc)
        if (dt.hour not in HOURS or dt.minute or dt.second or dt.microsecond):
            off_grid_times.append(stamp)
        if interval != EXPECTED_INTERVAL_HOURS:
            inconsistent_intervals.append({"time_ms": stamp, "hours": interval})
    expected_stamps = set()
    current = datetime(2020, 1, 1, tzinfo=timezone.utc)
    while current.date() < END_EXCLUSIVE:
        for h in HOURS:
            expected_stamps.add(int(current.replace(hour=h).timestamp() * 1000))
        current += timedelta(days=1)
    missing = sorted(expected_stamps - seen)
    unexpected = sorted(seen - expected_stamps)
    def issue_if(name: str, count: int, example):
        if count:
            issues.append({"issue": name, "count": count, "examples": example[:5]})
    issue_if("DUPLICATE_SETTLEMENT_TIMES", len(duplicate_times), duplicate_times)
    issue_if("MISSING_EXPECTED_SETTLEMENTS", len(missing), missing)
    issue_if("UNEXPECTED_SETTLEMENT_TIMES", len(unexpected), unexpected)
    issue_if("OFF_8H_UTC_GRID", len(off_grid_times), off_grid_times)
    issue_if("NON_8H_INTERVAL", len(inconsistent_intervals), inconsistent_intervals)
    issue_if("NOT_STRICTLY_CHRONOLOGICAL", out_of_order_count, [out_of_order_count])
    if len(rows) != EXPECTED_ROWS:
        issues.append({"issue": "UNEXPECTED_ROW_COUNT", "expected": EXPECTED_ROWS, "actual": len(rows)})
    counts = {str(y): 0 for y in range(2020, 2024)}
    negative = positive = zero = 0
    for stamp, _interval, rate in rows:
        d = datetime.fromtimestamp(stamp / 1000, tz=timezone.utc).date()
        if FIRST <= d < END_EXCLUSIVE:
            counts[str(d.year)] += 1
        sign = Decimal(rate)
        negative += sign < 0
        positive += sign > 0
        zero += sign == 0
    report = {
        "protocol": PROTOCOL,
        "market": "BTCUSDT USD-M perpetual funding settlements",
        "research_only": True,
        "range": {"from": FIRST.isoformat(), "through": "2023-12-31", "days": EXPECTED_DAYS},
        "status": "DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED" if not issues else "STOP_DATA_AUDIT_FAILED",
        "expected_settlements": EXPECTED_ROWS,
        "observed_rows": len(rows),
        "unique_settlement_times": len(seen),
        "yearly_counts": counts,
        "sign_counts": {"positive": positive, "negative": negative, "zero": zero},
        "checks": {"sha256_monthly_archives": True, "header_contract": SCHEMA,
                   "expected_utc_hours": HOURS, "expected_interval_hours": EXPECTED_INTERVAL_HOURS,
                   "duplicates_repaired": False, "missing_values_imputed": False},
        "issues": issues,
        "archives": archive_meta,
        "limitations": (
            "Funding payments are observed at settlement time, not at the start of their "
            "funding period; signals must use only earlier completed settlements. "
            "Funding rate alone is not direct open interest, leverage, or liquidation data. "
            "No spot prices, predictive claim, trades, fees or holdout are inspected here."
        ),
    }
    return report, rows


def run_audit(root: Path, *, offline: bool = False) -> dict:
    cache = root / "funding" / "archive"
    collected = []
    archives = []
    for month in months():
        payload, meta = load_verified_archive(cache, month, offline=offline)
        collected.extend(read_month(payload, month))
        archives.append(meta)
    report, rows = audit_rows(collected, archives)
    out_dir = root / "funding"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "BTCUSDT-funding-2020-2023.audit.json"
    data_path = out_dir / "BTCUSDT-funding-2020-2023.csv"
    if report["status"] == "DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED":
        # Canonical output is made only on clean data, in immutable original order.
        buf = io.StringIO(newline="")
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(SCHEMA)
        for row in rows:
            writer.writerow(row)
        data = buf.getvalue().encode("utf-8")
        report["canonical_csv_sha256"] = sha256_bytes(data)
        # Both snapshots are versioned by their source-checksum list; refuse
        # silent changes if a prior canonical snapshot exists.
        if data_path.exists() and data_path.read_bytes() != data:
            raise FundingAuditError("Existing canonical funding CSV changed; stop and inspect upstream archives")
        if not data_path.exists():
            temp = data_path.with_suffix(".csv.tmp")
            temp.write_bytes(data)
            temp.replace(data_path)
    else:
        report["canonical_csv_sha256"] = None
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if report_path.exists() and report_path.read_text(encoding="utf-8") != text:
        raise FundingAuditError("Existing audit differs; stop rather than overwrite evidence")
    if not report_path.exists():
        temp = report_path.with_suffix(".json.tmp")
        temp.write_text(text, encoding="utf-8")
        temp.replace(report_path)
    return {"status": report["status"], "report": str(report_path), "canonical_csv": str(data_path) if report["canonical_csv_sha256"] else None,
            "observed": len(rows), "expected": EXPECTED_ROWS, "issues": report["issues"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-funding", description="BTC 2020-2023 funding archive audit only; no signal or backtest")
    parser.add_argument("--home", type=Path, default=Path(os.getenv("QUANT_HOME", "runtime")))
    cmd = parser.add_subparsers(dest="command", required=True)
    run = cmd.add_parser("audit", help="Download SHA256-verified frozen 2020-2023 funding archives and audit their UTC settlements")
    run.add_argument("--offline", action="store_true", help="Only read existing cached ZIP/CHECKSUM files")
    args = parser.parse_args(argv)
    try:
        outcome = run_audit(args.home, offline=args.offline)
        print(json.dumps(outcome, indent=2, ensure_ascii=False))
        return 0 if outcome["status"] == "DATA_AUDIT_PASSED_MECHANISM_NOT_TESTED" else 2
    except (FundingAuditError, OSError, error.URLError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
