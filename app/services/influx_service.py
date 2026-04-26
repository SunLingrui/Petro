from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import error, parse, request

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python 3.8 fallback
    ZoneInfo = None

from flask import current_app


TARGET_ORDER = [
    "profit",
    "gasoline_yield",
    "diesel_yield",
    "lpg_yield",
    "liquid_yield",
]

TARGET_DEFINITIONS = {
    "profit": {"name": "装置效益", "unit": "元/吨", "lower_limit": 50.0, "upper_limit": 500.0},
    "gasoline_yield": {"name": "汽油收率", "unit": "%", "lower_limit": 30.0, "upper_limit": 42.0},
    "diesel_yield": {"name": "柴油收率", "unit": "%", "lower_limit": 18.0, "upper_limit": 35.0},
    "lpg_yield": {"name": "液化气收率", "unit": "%", "lower_limit": 15.0, "upper_limit": 26.0},
    "liquid_yield": {"name": "液收", "unit": "%", "lower_limit": 55.0, "upper_limit": 90.0},
}

DEFAULT_TARGET_KEY = "lpg_yield"
DEFAULT_SAMPLE_MINUTES = 30


class InfluxQueryError(RuntimeError):
    pass


def _get_timezone():
    timezone_name = current_app.config.get("APP_TIMEZONE", "Asia/Shanghai")
    if ZoneInfo is not None:
        return ZoneInfo(timezone_name)
    if timezone_name == "Asia/Shanghai":
        return timezone(timedelta(hours=8))
    return timezone.utc


def _get_required_config() -> dict[str, str]:
    config = {
        "host": current_app.config.get("INFLUX_HOST", "").rstrip("/"),
        "org": current_app.config.get("INFLUX_ORG", ""),
        "token": current_app.config.get("INFLUX_TOKEN", ""),
        "bucket": current_app.config.get("INFLUX_BUCKET", ""),
    }
    missing = [key for key, value in config.items() if not value]
    if missing:
        raise InfluxQueryError(f"InfluxDB 配置不完整，缺少: {', '.join(missing)}")
    return config


def _parse_annotated_csv(payload: str) -> list[dict[str, str]]:
    data_lines = []
    for line in payload.splitlines():
        if not line or line.startswith("#"):
            continue
        data_lines.append(line)

    if not data_lines:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
    rows: list[dict[str, str]] = []
    for row in reader:
        normalized = {
            key: value
            for key, value in row.items()
            if key not in {"", "result", "table"} and key is not None
        }
        rows.append(normalized)
    return rows


def _query_flux_rows(flux: str) -> list[dict[str, str]]:
    config = _get_required_config()
    endpoint = f"{config['host']}/api/v2/query?org={parse.quote(config['org'])}"
    payload = flux.encode("utf-8")
    headers = {
        "Authorization": f"Token {config['token']}",
        "Accept": "application/csv",
        "Content-Type": "application/vnd.flux",
    }
    http_request = request.Request(endpoint, data=payload, headers=headers, method="POST")

    try:
        with request.urlopen(http_request, timeout=12) as response:
            raw_payload = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace").strip()
        raise InfluxQueryError(f"InfluxDB 查询失败: HTTP {exc.code} {error_body}") from exc
    except error.URLError as exc:
        raise InfluxQueryError(f"InfluxDB 连接失败: {exc.reason}") from exc

    return _parse_annotated_csv(raw_payload)


def _to_float(raw_value: str | None, fallback: float | None = None) -> float | None:
    if raw_value in (None, ""):
        return fallback
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return fallback


def _parse_utc_datetime(raw_value: str) -> datetime:
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_flux_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_local_input(value: datetime) -> str:
    return value.astimezone(_get_timezone()).strftime("%Y-%m-%dT%H:%M")


def _format_local_display(value: datetime) -> str:
    return value.astimezone(_get_timezone()).strftime("%Y-%m-%d %H:%M")


def _format_number(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "--"
    return f"{value:.{digits}f}"


def _parse_local_input(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        naive_value = datetime.strptime(raw_value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None
    return naive_value.replace(tzinfo=_get_timezone()).astimezone(timezone.utc)


def _normalize_target_key(target_key: str | None) -> str:
    if target_key in TARGET_DEFINITIONS:
        return target_key
    return DEFAULT_TARGET_KEY


def _normalize_sample_minutes(raw_value: str | int | None) -> int:
    try:
        sample_minutes = int(raw_value or DEFAULT_SAMPLE_MINUTES)
    except (TypeError, ValueError):
        sample_minutes = DEFAULT_SAMPLE_MINUTES
    return max(5, min(sample_minutes, 24 * 60))


def _fetch_latest_target_timestamp() -> datetime | None:
    config = _get_required_config()
    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: -365d)
  |> filter(fn: (r) =>
    r._measurement == "rto_target_metrics" and
    r.page == "optimization_target" and
    r._field == "increment_ratio"
  )
  |> group()
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
  |> keep(columns: ["_time"])
""".strip()
    rows = _query_flux_rows(flux)
    if not rows:
        return None
    return _parse_utc_datetime(rows[0]["_time"])


def _resolve_query_window(start_local: str | None, end_local: str | None, sample_minutes_raw: str | int | None):
    sample_minutes = _normalize_sample_minutes(sample_minutes_raw)

    parsed_start = _parse_local_input(start_local)
    parsed_end = _parse_local_input(end_local)

    if parsed_start and parsed_end and parsed_start < parsed_end:
        return parsed_start, parsed_end, sample_minutes

    latest_point = _fetch_latest_target_timestamp()
    if latest_point is None:
        latest_point = datetime.now(timezone.utc)

    end_at = parsed_end or latest_point
    start_at = parsed_start or (end_at - timedelta(hours=4))

    if start_at >= end_at:
        start_at = end_at - timedelta(hours=4)

    return start_at, end_at, sample_minutes


def _fetch_target_summary(start_at: datetime, end_at: datetime) -> dict[str, dict[str, Any]]:
    config = _get_required_config()
    start_flux = _format_flux_time(start_at)
    end_flux = _format_flux_time(end_at)
    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: {start_flux}, stop: {end_flux})
  |> filter(fn: (r) =>
    r._measurement == "rto_target_metrics" and
    r.page == "optimization_target" and
    (
      r._field == "before_value" or
      r._field == "after_value" or
      r._field == "increment_ratio" or
      r._field == "lower_limit" or
      r._field == "upper_limit"
    )
  )
  |> group(columns: ["target_key", "_field"])
  |> last()
  |> pivot(rowKey: ["target_key"], columnKey: ["_field"], valueColumn: "_value")
""".strip()

    rows = _query_flux_rows(flux)
    summary: dict[str, dict[str, Any]] = {}
    for row in rows:
        target_key = row.get("target_key")
        if not target_key:
            continue
        summary[target_key] = {
            "before_value": _to_float(row.get("before_value")),
            "after_value": _to_float(row.get("after_value")),
            "increment_ratio": _to_float(row.get("increment_ratio")),
            "lower_limit": _to_float(row.get("lower_limit")),
            "upper_limit": _to_float(row.get("upper_limit")),
        }
    return summary


def _fetch_target_chart(target_key: str, start_at: datetime, end_at: datetime, sample_minutes: int) -> list[dict[str, Any]]:
    config = _get_required_config()
    start_flux = _format_flux_time(start_at)
    end_flux = _format_flux_time(end_at)
    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: {start_flux}, stop: {end_flux})
  |> filter(fn: (r) =>
    r._measurement == "rto_target_metrics" and
    r.page == "optimization_target" and
    r.target_key == "{target_key}" and
    r._field == "increment_ratio"
  )
  |> aggregateWindow(every: {sample_minutes}m, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value"])
""".strip()

    rows = _query_flux_rows(flux)
    points: list[dict[str, Any]] = []
    for row in rows:
        point_time = _parse_utc_datetime(row["_time"])
        value = _to_float(row.get("_value"))
        if value is None:
            continue
        points.append(
            {
                "timestamp": point_time.isoformat(),
                "time_label": point_time.astimezone(_get_timezone()).strftime("%H:%M"),
                "value": round(value, 4),
            }
        )
    return points


def _build_target_rows(summary: dict[str, dict[str, Any]], selected_target: str) -> list[dict[str, Any]]:
    rows = []
    for target_key in TARGET_ORDER:
        definition = TARGET_DEFINITIONS[target_key]
        target_summary = summary.get(target_key, {})
        lower_limit = target_summary.get("lower_limit", definition["lower_limit"])
        upper_limit = target_summary.get("upper_limit", definition["upper_limit"])
        rows.append(
            {
                "key": target_key,
                "name": definition["name"],
                "selected": target_key == selected_target,
                "unit": definition["unit"],
                "lower_limit": _format_number(lower_limit),
                "upper_limit": _format_number(upper_limit),
                "before_value": _format_number(target_summary.get("before_value")),
                "after_value": _format_number(target_summary.get("after_value")),
                "increment_ratio": _format_number(target_summary.get("increment_ratio")),
            }
        )
    return rows


def _build_chart_payload(target_key: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    definition = TARGET_DEFINITIONS[target_key]
    if not points:
        return {
            "target_key": target_key,
            "target_name": definition["name"],
            "unit": "%",
            "points": [],
            "stats": {
                "latest": "--",
                "min": "--",
                "max": "--",
                "avg": "--",
            },
        }

    values = [point["value"] for point in points]
    average_value = sum(values) / len(values)
    return {
        "target_key": target_key,
        "target_name": definition["name"],
        "unit": "%",
        "points": points,
        "stats": {
            "latest": _format_number(values[-1]),
            "min": _format_number(min(values)),
            "max": _format_number(max(values)),
            "avg": _format_number(average_value),
        },
    }


def get_optimization_target_payload(
    target_key: str | None = None,
    start_local: str | None = None,
    end_local: str | None = None,
    sample_minutes: str | int | None = None,
) -> dict[str, Any]:
    selected_target = _normalize_target_key(target_key)
    start_at, end_at, resolved_sample = _resolve_query_window(start_local, end_local, sample_minutes)
    summary = _fetch_target_summary(start_at, end_at)
    chart_points = _fetch_target_chart(selected_target, start_at, end_at, resolved_sample)

    return {
        "selected_target": selected_target,
        "target_rows": _build_target_rows(summary, selected_target),
        "target_history": {
            "start_at": _format_local_input(start_at),
            "end_at": _format_local_input(end_at),
            "sample_minutes": resolved_sample,
            "start_display": _format_local_display(start_at),
            "end_display": _format_local_display(end_at),
        },
        "chart": _build_chart_payload(selected_target, chart_points),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_import_payload() -> dict[str, Any]:
    payload = get_optimization_target_payload()
    targets = {}
    for row in payload["target_rows"]:
        targets[row["key"]] = {
            "before_value": row["before_value"],
            "after_value": row["after_value"],
            "lower_limit": row["lower_limit"],
            "upper_limit": row["upper_limit"],
            "increment_ratio": row["increment_ratio"],
        }
    return {
        "source": "influxdb",
        "generated_at": payload["generated_at"],
        "targets": targets,
        "selected_target": payload["selected_target"],
        "chart": payload["chart"],
        "history": payload["target_history"],
    }


def build_empty_optimization_target_payload(target_key: str | None = None, error_message: str | None = None) -> dict[str, Any]:
    selected_target = _normalize_target_key(target_key)
    now_local = datetime.now(_get_timezone())
    start_at = now_local - timedelta(hours=4)
    return {
        "selected_target": selected_target,
        "target_rows": _build_target_rows({}, selected_target),
        "target_history": {
            "start_at": start_at.strftime("%Y-%m-%dT%H:%M"),
            "end_at": now_local.strftime("%Y-%m-%dT%H:%M"),
            "sample_minutes": DEFAULT_SAMPLE_MINUTES,
            "start_display": start_at.strftime("%Y-%m-%d %H:%M"),
            "end_display": now_local.strftime("%Y-%m-%d %H:%M"),
        },
        "chart": _build_chart_payload(selected_target, []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": error_message,
    }


def payload_as_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
