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

VARIABLE_ORDER = [
    "reactor_temperature",
    "catalyst_oil_ratio",
    "regenerator_temperature",
    "feed_preheat_temperature",
]

VARIABLE_DEFINITIONS = {
    "reactor_temperature": {
        "name": "反应温度",
        "slug": "reactor-temperature",
        "page": "reactor_temperature",
        "tag_code": "150TIC1090",
        "unit": "℃",
        "route_endpoint": "reactor_temperature",
        "chart_title": "反应温度相关参数图",
    },
    "catalyst_oil_ratio": {
        "name": "剂油比",
        "slug": "catalyst-oil-ratio",
        "page": "catalyst_oil_ratio",
        "tag_code": "150YLYQH",
        "unit": "",
        "route_endpoint": "catalyst_oil_ratio",
        "chart_title": "剂油比相关参数图",
    },
    "regenerator_temperature": {
        "name": "再生温度",
        "slug": "regenerator-temperature",
        "page": "regenerator_temperature",
        "tag_code": "150TI1082",
        "unit": "℃",
        "route_endpoint": "regenerator_temperature",
        "chart_title": "再生温度相关参数图",
    },
    "feed_preheat_temperature": {
        "name": "原料预热温度",
        "slug": "feed-preheat-temperature",
        "page": "feed_preheat_temperature",
        "tag_code": "150TIC2006",
        "unit": "℃",
        "route_endpoint": "feed_preheat_temperature",
        "chart_title": "原料预热温度相关参数图",
    },
}

VARIABLE_SLUG_TO_KEY = {definition["slug"]: key for key, definition in VARIABLE_DEFINITIONS.items()}

VARIABLE_SNAPSHOT_FIELDS = [
    "current_value",
    "last_optimized_value",
    "optimized_value",
    "model_value",
    "feedback_value",
    "output_setpoint",
    "delta_vs_output",
    "lower_limit",
    "upper_limit",
    "current_step",
    "max_step",
    "apc_lower_limit",
    "apc_upper_limit",
    "dcs_lower_limit",
    "dcs_upper_limit",
    "push_enabled",
    "apc_status",
]

VARIABLE_CHART_SERIES = [
    {"field": "current_value", "label": "当前值", "color": "#5b8ff9"},
    {"field": "model_value", "label": "智能混合模型优化结果值", "color": "#8bd17c"},
    {"field": "feedback_value", "label": "反馈调优优化结果值", "color": "#f6bd16"},
    {"field": "optimized_value", "label": "优化结果值", "color": "#ff6b6b"},
    {"field": "output_setpoint", "label": "输出设定值", "color": "#5ec9f5"},
    {"field": "upper_limit", "label": "优化上限", "color": "#37c28b"},
    {"field": "lower_limit", "label": "优化下限", "color": "#ff8c42"},
    {"field": "apc_upper_limit", "label": "APC上限", "color": "#b37feb"},
    {"field": "apc_lower_limit", "label": "APC下限", "color": "#ff85c0"},
]

VARIABLE_DETAIL_CARDS = [
    {"label": "当前值", "field": "current_value", "boxed": False},
    {"label": "优化结果", "field": "optimized_value", "boxed": False},
    {"label": "智能混合模型优化结果", "field": "model_value", "boxed": False},
    {"label": "反馈调优优化结果值", "field": "feedback_value", "boxed": False},
    {"label": "输出设定值", "field": "output_setpoint", "boxed": False},
    {"label": "优化结果值与原输出设定值差", "field": "delta_vs_output", "boxed": False},
    {"label": "优化下限", "field": "lower_limit", "boxed": True},
    {"label": "优化上限", "field": "upper_limit", "boxed": True},
    {"label": "当前步幅", "field": "current_step", "boxed": True},
    {"label": "最大步幅", "field": "max_step", "boxed": True},
    {"label": "APC下限", "field": "apc_lower_limit", "boxed": False},
    {"label": "APC上限", "field": "apc_upper_limit", "boxed": False},
    {"label": "DCS下限", "field": "dcs_lower_limit", "boxed": False},
    {"label": "DCS上限", "field": "dcs_upper_limit", "boxed": False},
]

DEFAULT_TARGET_KEY = "lpg_yield"
DEFAULT_SAMPLE_MINUTES = 30

MARKET_GROUP_ORDER = [
    "raw_material",
    "product",
    "utility",
    "feed_lab",
    "product_lab",
    "cost",
]

MARKET_METRIC_DEFINITIONS = {
    "raw_material": {
        "table_key": "raw_materials",
        "metrics": [
            {"key": "raw_heavy_feed_price", "name": "重油新鲜进料", "label": "重油新鲜进料价格", "unit": "元/吨", "color": "#5b8ff9"},
            {"key": "heavy_aromatics_price", "name": "重芳烃", "label": "重芳烃价格", "unit": "元/吨", "color": "#8bd17c"},
        ],
    },
    "product": {
        "table_key": "products",
        "metrics": [
            {"key": "dry_gas_price", "name": "干气", "label": "干气价格", "unit": "元/吨", "color": "#5b8ff9"},
            {"key": "lpg_price", "name": "液化气", "label": "液化气价格", "unit": "元/吨", "color": "#8bd17c"},
            {"key": "gasoline_price", "name": "汽油", "label": "汽油价格", "unit": "元/吨", "color": "#f6bd16"},
            {"key": "heavy_naphtha_price", "name": "重石脑油", "label": "重石脑油价格", "unit": "元/吨", "color": "#ff6b6b"},
            {"key": "diesel_price", "name": "柴油", "label": "柴油价格", "unit": "元/吨", "color": "#5ec9f5"},
            {"key": "slurry_price", "name": "油浆", "label": "油浆价格", "unit": "元/吨", "color": "#37c28b"},
        ],
    },
    "utility": {
        "table_key": "utilities",
        "metrics": [
            {"key": "medium_pressure_steam_price", "name": "中压蒸汽", "label": "中压蒸汽", "unit": "元/吨", "color": "#5b8ff9"},
            {"key": "low_pressure_steam_price", "name": "低压蒸汽", "label": "低压蒸汽", "unit": "元/吨", "color": "#8bd17c"},
            {"key": "electricity_price", "name": "电", "label": "电", "unit": "元/kWh", "color": "#f6bd16"},
            {"key": "desalted_water_price", "name": "除盐水", "label": "除盐水", "unit": "元/吨", "color": "#ff6b6b"},
            {"key": "circulating_water_price", "name": "循环水", "label": "循环水", "unit": "元/吨", "color": "#5ec9f5"},
            {"key": "hot_water_price", "name": "低温热水", "label": "低温热水", "unit": "元/吨", "color": "#37c28b"},
            {"key": "wastewater_price", "name": "污水", "label": "污水", "unit": "元/吨", "color": "#b37feb"},
        ],
    },
    "feed_lab": {
        "table_key": "feed_lab",
        "metrics": [
            {"key": "mixed_feed_density", "name": "混合进料密度", "label": "混合进料密度", "unit": "kg/m³", "color": "#5b8ff9"},
            {"key": "mixed_feed_carbon_residue", "name": "混合进料残炭", "label": "混合进料残炭", "unit": "wt%", "color": "#8bd17c"},
        ],
    },
    "product_lab": {
        "table_key": "product_lab",
        "metrics": [
            {"key": "gasoline_density", "name": "汽油产品密度", "label": "汽油产品密度", "unit": "kg/m³", "color": "#5b8ff9"},
            {"key": "gasoline_fbp", "name": "汽油产品终馏点", "label": "汽油产品终馏点", "unit": "℃", "color": "#8bd17c"},
            {"key": "diesel_density", "name": "柴油产品密度", "label": "柴油产品密度", "unit": "kg/m³", "color": "#f6bd16"},
            {"key": "diesel_95pct_point", "name": "柴油产品95%点", "label": "柴油产品95%点", "unit": "℃", "color": "#ff6b6b"},
        ],
    },
    "cost": {
        "table_key": "costs",
        "metrics": [
            {"key": "feed_cost", "name": "原料成本", "label": "原料成本", "unit": "元/吨", "color": "#5b8ff9"},
            {"key": "processing_cost", "name": "加工成本", "label": "加工成本", "unit": "元/吨", "color": "#8bd17c"},
            {"key": "energy_cost", "name": "能耗成本", "label": "能耗成本", "unit": "元/吨", "color": "#f6bd16"},
            {"key": "total_cost", "name": "综合成本", "label": "综合成本", "unit": "元/吨", "color": "#ff6b6b"},
        ],
    },
}

MARKET_CHART_GROUPS = {
    "raw_material": {"title": "原料价格变化曲线图", "unit": "元/吨"},
    "product": {"title": "产品价格变化曲线图", "unit": "元/吨"},
    "utility": {"title": "公用工程价格变化曲线", "unit": "价格"},
    "feed_lab": {"title": "原料化验分析数据变化曲线", "unit": "分析值"},
    "product_lab": {"title": "产品化验分析数据变化曲线", "unit": "分析值"},
    "cost": {"title": "成本价格变化曲线", "unit": "元/吨"},
}


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
        "org": current_app.config.get("INFLUX_ORG", "").strip(),
        "token": current_app.config.get("INFLUX_TOKEN", "").strip(),
        "bucket": current_app.config.get("INFLUX_BUCKET", "").strip(),
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


def _to_bool(raw_value: str | None, fallback: bool = False) -> bool:
    if raw_value is None:
        return fallback
    return raw_value.strip().lower() in {"true", "t", "1", "yes", "y"}


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


def _normalize_variable_key(variable_key: str | None) -> str:
    if variable_key in VARIABLE_DEFINITIONS:
        return variable_key
    return VARIABLE_ORDER[0]


def get_variable_key_by_slug(variable_slug: str) -> str | None:
    return VARIABLE_SLUG_TO_KEY.get(variable_slug)


def _normalize_sample_minutes(raw_value: str | int | None) -> int:
    try:
        sample_minutes = int(raw_value or DEFAULT_SAMPLE_MINUTES)
    except (TypeError, ValueError):
        sample_minutes = DEFAULT_SAMPLE_MINUTES
    return max(5, min(sample_minutes, 24 * 60))


def _flux_or_conditions(column_name: str, values: list[str]) -> str:
    return " or ".join(f'r.{column_name} == "{value}"' for value in values)


def _fetch_latest_measurement_timestamp(measurement: str, field_name: str) -> datetime | None:
    config = _get_required_config()
    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: -365d)
  |> filter(fn: (r) =>
    r._measurement == "{measurement}" and
    r._field == "{field_name}"
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


def _resolve_query_window(
    start_local: str | None,
    end_local: str | None,
    sample_minutes_raw: str | int | None,
    measurement: str,
    field_name: str,
) -> tuple[datetime, datetime, int]:
    sample_minutes = _normalize_sample_minutes(sample_minutes_raw)

    parsed_start = _parse_local_input(start_local)
    parsed_end = _parse_local_input(end_local)

    if parsed_start and parsed_end and parsed_start < parsed_end:
        return parsed_start, parsed_end, sample_minutes

    latest_point = _fetch_latest_measurement_timestamp(measurement, field_name)
    if latest_point is None:
        latest_point = datetime.now(timezone.utc)

    end_at = parsed_end or latest_point
    start_at = parsed_start or (end_at - timedelta(hours=4))

    if start_at >= end_at:
        start_at = end_at - timedelta(hours=4)

    return start_at, end_at, sample_minutes


def _build_history_payload(start_at: datetime, end_at: datetime, sample_minutes: int) -> dict[str, Any]:
    return {
        "start_at": _format_local_input(start_at),
        "end_at": _format_local_input(end_at),
        "sample_minutes": sample_minutes,
        "start_display": _format_local_display(start_at),
        "end_display": _format_local_display(end_at),
    }


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


def _build_target_chart_payload(target_key: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    definition = TARGET_DEFINITIONS[target_key]
    if not points:
        return {
            "target_key": target_key,
            "target_name": definition["name"],
            "unit": "%",
            "points": [],
            "stats": {"latest": "--", "min": "--", "max": "--", "avg": "--"},
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
    start_at, end_at, resolved_sample = _resolve_query_window(
        start_local,
        end_local,
        sample_minutes,
        measurement="rto_target_metrics",
        field_name="increment_ratio",
    )
    summary = _fetch_target_summary(start_at, end_at)
    chart_points = _fetch_target_chart(selected_target, start_at, end_at, resolved_sample)

    return {
        "selected_target": selected_target,
        "target_rows": _build_target_rows(summary, selected_target),
        "target_history": _build_history_payload(start_at, end_at, resolved_sample),
        "chart": _build_target_chart_payload(selected_target, chart_points),
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
        "chart": _build_target_chart_payload(selected_target, []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": error_message,
    }


def _fetch_variable_snapshot_rows(variable_keys: list[str] | None = None) -> dict[str, dict[str, str]]:
    config = _get_required_config()
    field_clause = _flux_or_conditions("_field", VARIABLE_SNAPSHOT_FIELDS)
    variable_filter = ""
    if variable_keys:
        variable_filter = f' and ({_flux_or_conditions("variable_key", variable_keys)})'

    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: -365d)
  |> filter(fn: (r) =>
    r._measurement == "rto_variable_metrics" and
    ({field_clause}){variable_filter}
  )
  |> group(columns: ["variable_key", "_field"])
  |> last()
  |> pivot(rowKey: ["variable_key"], columnKey: ["_field"], valueColumn: "_value")
""".strip()

    rows = _query_flux_rows(flux)
    summary: dict[str, dict[str, str]] = {}
    for row in rows:
        variable_key = row.get("variable_key")
        if variable_key:
            summary[variable_key] = row
    return summary


def _build_variable_overview_rows(summary_rows: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for variable_key in VARIABLE_ORDER:
        definition = VARIABLE_DEFINITIONS[variable_key]
        row = summary_rows.get(variable_key, {})
        rows.append(
            {
                "key": variable_key,
                "name": definition["name"],
                "tag": definition["tag_code"],
                "unit": definition["unit"],
                "detail_url_key": definition["route_endpoint"],
                "current_value": _format_number(_to_float(row.get("current_value"))),
                "last_optimized_value": _format_number(_to_float(row.get("last_optimized_value"))),
                "optimized_value": _format_number(_to_float(row.get("optimized_value"))),
                "delta_vs_output": _format_number(_to_float(row.get("delta_vs_output"))),
                "current_step": _format_number(_to_float(row.get("current_step"))),
                "max_step": _format_number(_to_float(row.get("max_step"))),
                "output_setpoint": _format_number(_to_float(row.get("output_setpoint"))),
                "push_enabled": _to_bool(row.get("push_enabled")),
            }
        )
    return rows


def get_optimization_variables_payload() -> dict[str, Any]:
    summary_rows = _fetch_variable_snapshot_rows()
    return {
        "variable_rows": _build_variable_overview_rows(summary_rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_empty_optimization_variables_payload(error_message: str | None = None) -> dict[str, Any]:
    rows = []
    for variable_key in VARIABLE_ORDER:
        definition = VARIABLE_DEFINITIONS[variable_key]
        rows.append(
            {
                "key": variable_key,
                "name": definition["name"],
                "tag": definition["tag_code"],
                "unit": definition["unit"],
                "detail_url_key": definition["route_endpoint"],
                "current_value": "--",
                "last_optimized_value": "--",
                "optimized_value": "--",
                "delta_vs_output": "--",
                "current_step": "--",
                "max_step": "--",
                "output_setpoint": "--",
                "push_enabled": False,
            }
        )
    return {"variable_rows": rows, "generated_at": datetime.now(timezone.utc).isoformat(), "error": error_message}


def _build_variable_monitor_data(variable_key: str, snapshot_row: dict[str, str] | None) -> dict[str, Any]:
    row = snapshot_row or {}
    status_text = (row.get("apc_status") or "未联动").strip()
    status_class = "state-good" if status_text == "已接受" else "state-danger"
    return {
        "push_enabled": _to_bool(row.get("push_enabled")),
        "apc_status": status_text,
        "apc_status_class": status_class,
        "current_value": _format_number(_to_float(row.get("current_value"))),
        "last_optimized_value": _format_number(_to_float(row.get("last_optimized_value"))),
        "optimized_value": _format_number(_to_float(row.get("optimized_value"))),
        "model_value": _format_number(_to_float(row.get("model_value"))),
        "feedback_value": _format_number(_to_float(row.get("feedback_value"))),
        "output_setpoint": _format_number(_to_float(row.get("output_setpoint"))),
        "delta_vs_output": _format_number(_to_float(row.get("delta_vs_output"))),
        "lower_limit": _format_number(_to_float(row.get("lower_limit"))),
        "upper_limit": _format_number(_to_float(row.get("upper_limit"))),
        "current_step": _format_number(_to_float(row.get("current_step"))),
        "max_step": _format_number(_to_float(row.get("max_step"))),
        "apc_lower_limit": _format_number(_to_float(row.get("apc_lower_limit"))),
        "apc_upper_limit": _format_number(_to_float(row.get("apc_upper_limit"))),
        "dcs_lower_limit": _format_number(_to_float(row.get("dcs_lower_limit"))),
        "dcs_upper_limit": _format_number(_to_float(row.get("dcs_upper_limit"))),
    }


def _build_variable_detail_cards(monitor_data: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for definition in VARIABLE_DETAIL_CARDS:
        cards.append(
            {
                "label": definition["label"],
                "value": monitor_data.get(definition["field"], "--"),
                "boxed": definition["boxed"],
            }
        )
    return cards


def _fetch_variable_chart_points(variable_key: str, start_at: datetime, end_at: datetime, sample_minutes: int) -> list[dict[str, Any]]:
    config = _get_required_config()
    start_flux = _format_flux_time(start_at)
    end_flux = _format_flux_time(end_at)
    field_clause = _flux_or_conditions("_field", [series["field"] for series in VARIABLE_CHART_SERIES])
    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: {start_flux}, stop: {end_flux})
  |> filter(fn: (r) =>
    r._measurement == "rto_variable_metrics" and
    r.variable_key == "{variable_key}" and
    ({field_clause})
  )
  |> aggregateWindow(every: {sample_minutes}m, fn: mean, createEmpty: false)
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
""".strip()

    rows = _query_flux_rows(flux)
    points: list[dict[str, Any]] = []
    for row in rows:
        point_time = _parse_utc_datetime(row["_time"])
        point = {
            "timestamp": point_time.isoformat(),
            "time_label": point_time.astimezone(_get_timezone()).strftime("%m-%d %H:%M"),
        }
        has_value = False
        for series in VARIABLE_CHART_SERIES:
            numeric_value = _to_float(row.get(series["field"]))
            if numeric_value is not None:
                point[series["field"]] = round(numeric_value, 4)
                has_value = True
        if has_value:
            points.append(point)
    return points


def _build_variable_chart_payload(variable_key: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    definition = VARIABLE_DEFINITIONS[variable_key]
    populated_series = []
    for series in VARIABLE_CHART_SERIES:
        if any(series["field"] in point for point in points):
            populated_series.append(series)

    y_values: list[float] = []
    for point in points:
        for series in populated_series:
            value = point.get(series["field"])
            if value is not None:
                y_values.append(float(value))

    if y_values:
        y_min = min(y_values)
        y_max = max(y_values)
    else:
        y_min = 0.0
        y_max = 1.0

    return {
        "variable_key": variable_key,
        "variable_name": definition["name"],
        "unit": definition["unit"],
        "title": definition["chart_title"],
        "points": points,
        "series_meta": populated_series,
        "y_min": y_min,
        "y_max": y_max,
    }


def get_variable_detail_payload(
    variable_key: str,
    start_local: str | None = None,
    end_local: str | None = None,
    sample_minutes: str | int | None = None,
) -> dict[str, Any]:
    normalized_key = _normalize_variable_key(variable_key)
    start_at, end_at, resolved_sample = _resolve_query_window(
        start_local,
        end_local,
        sample_minutes,
        measurement="rto_variable_metrics",
        field_name="current_value",
    )
    snapshot_rows = _fetch_variable_snapshot_rows([normalized_key])
    monitor_data = _build_variable_monitor_data(normalized_key, snapshot_rows.get(normalized_key))
    chart_points = _fetch_variable_chart_points(normalized_key, start_at, end_at, resolved_sample)
    definition = VARIABLE_DEFINITIONS[normalized_key]

    return {
        "variable": {
            "key": normalized_key,
            "name": definition["name"],
            "page": definition["page"],
            "tag_code": definition["tag_code"],
            "unit": definition["unit"],
            "slug": definition["slug"],
            "chart_title": definition["chart_title"],
        },
        "monitor_data": monitor_data,
        "monitor_cards": _build_variable_detail_cards(monitor_data),
        "history_data": _build_history_payload(start_at, end_at, resolved_sample),
        "chart": _build_variable_chart_payload(normalized_key, chart_points),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_empty_variable_detail_payload(variable_key: str | None = None, error_message: str | None = None) -> dict[str, Any]:
    normalized_key = _normalize_variable_key(variable_key)
    now_local = datetime.now(_get_timezone())
    start_at = now_local - timedelta(hours=4)
    definition = VARIABLE_DEFINITIONS[normalized_key]
    monitor_data = _build_variable_monitor_data(normalized_key, None)
    return {
        "variable": {
            "key": normalized_key,
            "name": definition["name"],
            "page": definition["page"],
            "tag_code": definition["tag_code"],
            "unit": definition["unit"],
            "slug": definition["slug"],
            "chart_title": definition["chart_title"],
        },
        "monitor_data": monitor_data,
        "monitor_cards": _build_variable_detail_cards(monitor_data),
        "history_data": {
            "start_at": start_at.strftime("%Y-%m-%dT%H:%M"),
            "end_at": now_local.strftime("%Y-%m-%dT%H:%M"),
            "sample_minutes": DEFAULT_SAMPLE_MINUTES,
            "start_display": start_at.strftime("%Y-%m-%d %H:%M"),
            "end_display": now_local.strftime("%Y-%m-%d %H:%M"),
        },
        "chart": _build_variable_chart_payload(normalized_key, []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": error_message,
    }


def _normalize_market_group(metric_group: str | None) -> str:
    if metric_group in MARKET_CHART_GROUPS:
        return metric_group
    return "raw_material"


def _metric_definitions_for_group(metric_group: str) -> list[dict[str, Any]]:
    return MARKET_METRIC_DEFINITIONS[metric_group]["metrics"]


def _fetch_market_latest_rows() -> dict[str, dict[str, str]]:
    config = _get_required_config()
    group_clause = _flux_or_conditions("metric_group", MARKET_GROUP_ORDER)
    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: -365d)
  |> filter(fn: (r) =>
    r._measurement == "market_metric_values" and
    r._field == "value" and
    ({group_clause})
  )
  |> group(columns: ["metric_group", "metric_key"])
  |> last()
  |> keep(columns: ["_time", "_value", "metric_group", "metric_key"])
""".strip()

    latest_rows: dict[str, dict[str, str]] = {}
    for row in _query_flux_rows(flux):
        metric_group = row.get("metric_group")
        metric_key = row.get("metric_key")
        if metric_group and metric_key:
            latest_rows[f"{metric_group}:{metric_key}"] = row
    return latest_rows


def get_price_lab_overview_payload() -> dict[str, Any]:
    latest_rows = _fetch_market_latest_rows()
    tables: dict[str, list[dict[str, Any]]] = {}
    for metric_group in MARKET_GROUP_ORDER:
        group_definition = MARKET_METRIC_DEFINITIONS[metric_group]
        table_rows = []
        for metric in group_definition["metrics"]:
            row = latest_rows.get(f"{metric_group}:{metric['key']}", {})
            table_rows.append(
                {
                    "key": metric["key"],
                    "name": metric["name"],
                    "value": _format_number(_to_float(row.get("_value"))),
                    "unit": metric["unit"],
                }
            )
        tables[group_definition["table_key"]] = table_rows

    return {
        "overview_tables": tables,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_empty_price_lab_overview_payload(error_message: str | None = None) -> dict[str, Any]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for metric_group in MARKET_GROUP_ORDER:
        group_definition = MARKET_METRIC_DEFINITIONS[metric_group]
        tables[group_definition["table_key"]] = [
            {
                "key": metric["key"],
                "name": metric["name"],
                "value": "--",
                "unit": metric["unit"],
            }
            for metric in group_definition["metrics"]
        ]
    return {"overview_tables": tables, "generated_at": datetime.now(timezone.utc).isoformat(), "error": error_message}


def _fetch_market_chart_points(metric_group: str, start_at: datetime, end_at: datetime, sample_minutes: int) -> list[dict[str, Any]]:
    config = _get_required_config()
    start_flux = _format_flux_time(start_at)
    end_flux = _format_flux_time(end_at)
    metric_keys = [metric["key"] for metric in _metric_definitions_for_group(metric_group)]
    key_clause = _flux_or_conditions("metric_key", metric_keys)
    flux = f"""
from(bucket: "{config['bucket']}")
  |> range(start: {start_flux}, stop: {end_flux})
  |> filter(fn: (r) =>
    r._measurement == "market_metric_values" and
    r.metric_group == "{metric_group}" and
    r._field == "value" and
    ({key_clause})
  )
  |> aggregateWindow(every: {sample_minutes}m, fn: mean, createEmpty: false)
  |> keep(columns: ["_time", "_value", "metric_key"])
""".strip()

    points_by_time: dict[str, dict[str, Any]] = {}
    for row in _query_flux_rows(flux):
        point_time = _parse_utc_datetime(row["_time"])
        timestamp = point_time.isoformat()
        point = points_by_time.setdefault(
            timestamp,
            {
                "timestamp": timestamp,
                "time_label": point_time.astimezone(_get_timezone()).strftime("%m-%d %H:%M"),
            },
        )
        metric_key = row.get("metric_key")
        value = _to_float(row.get("_value"))
        if metric_key and value is not None:
            point[metric_key] = round(value, 4)

    return [points_by_time[timestamp] for timestamp in sorted(points_by_time)]


def _build_market_chart_payload(metric_group: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    group_definition = MARKET_CHART_GROUPS[metric_group]
    series_meta = [
        {
            "field": metric["key"],
            "label": metric["label"],
            "color": metric["color"],
        }
        for metric in _metric_definitions_for_group(metric_group)
        if any(metric["key"] in point for point in points)
    ]

    y_values: list[float] = []
    for point in points:
        for series in series_meta:
            value = point.get(series["field"])
            if value is not None:
                y_values.append(float(value))

    return {
        "metric_group": metric_group,
        "title": group_definition["title"],
        "unit": group_definition["unit"],
        "points": points,
        "series_meta": series_meta,
        "y_min": min(y_values) if y_values else 0.0,
        "y_max": max(y_values) if y_values else 1.0,
    }


def get_market_price_chart_payload(
    metric_group: str | None,
    start_local: str | None = None,
    end_local: str | None = None,
    sample_minutes: str | int | None = None,
) -> dict[str, Any]:
    normalized_group = _normalize_market_group(metric_group)
    start_at, end_at, resolved_sample = _resolve_query_window(
        start_local,
        end_local,
        sample_minutes,
        measurement="market_metric_values",
        field_name="value",
    )
    chart_points = _fetch_market_chart_points(normalized_group, start_at, end_at, resolved_sample)

    return {
        "metric_group": normalized_group,
        "history_data": _build_history_payload(start_at, end_at, resolved_sample),
        "chart": _build_market_chart_payload(normalized_group, chart_points),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_raw_product_prices_payload(
    start_local: str | None = None,
    end_local: str | None = None,
    sample_minutes: str | int | None = None,
) -> dict[str, Any]:
    return {
        "raw_material": get_market_price_chart_payload("raw_material", start_local, end_local, sample_minutes),
        "product": get_market_price_chart_payload("product", start_local, end_local, sample_minutes),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_empty_market_price_chart_payload(metric_group: str | None = None, error_message: str | None = None) -> dict[str, Any]:
    normalized_group = _normalize_market_group(metric_group)
    now_local = datetime.now(_get_timezone())
    start_at = now_local - timedelta(hours=4)
    return {
        "metric_group": normalized_group,
        "history_data": {
            "start_at": start_at.strftime("%Y-%m-%dT%H:%M"),
            "end_at": now_local.strftime("%Y-%m-%dT%H:%M"),
            "sample_minutes": DEFAULT_SAMPLE_MINUTES,
            "start_display": start_at.strftime("%Y-%m-%d %H:%M"),
            "end_display": now_local.strftime("%Y-%m-%d %H:%M"),
        },
        "chart": _build_market_chart_payload(normalized_group, []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": error_message,
    }


def build_empty_raw_product_prices_payload(error_message: str | None = None) -> dict[str, Any]:
    return {
        "raw_material": build_empty_market_price_chart_payload("raw_material", error_message),
        "product": build_empty_market_price_chart_payload("product", error_message),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": error_message,
    }


def payload_as_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)
