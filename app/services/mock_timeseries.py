from __future__ import annotations

from datetime import datetime, timedelta
import math
from statistics import mean


DEFAULT_QUERY_END = datetime(2026, 4, 24, 18, 0)
DEFAULT_QUERY_START = DEFAULT_QUERY_END - timedelta(days=7)
DEFAULT_SAMPLE_MINUTES = 30


OPTIMIZATION_TARGETS = {
    "profit": {
        "name": "装置效益",
        "unit": "元/吨",
        "lower_limit": 50.0,
        "upper_limit": 500.0,
        "measurement": "rto_target_metrics",
        "base_before": 94.6,
        "ratio_mid": 1.82,
        "ratio_amp": 0.42,
        "value_amp": 1.55,
        "phase": 0.15,
    },
    "gasoline_yield": {
        "name": "汽油收率",
        "unit": "%",
        "lower_limit": 30.0,
        "upper_limit": 42.0,
        "measurement": "rto_target_metrics",
        "base_before": 35.7,
        "ratio_mid": 0.19,
        "ratio_amp": 0.09,
        "value_amp": 0.24,
        "phase": 0.75,
    },
    "diesel_yield": {
        "name": "柴油收率",
        "unit": "%",
        "lower_limit": 18.0,
        "upper_limit": 35.0,
        "measurement": "rto_target_metrics",
        "base_before": 26.9,
        "ratio_mid": -0.11,
        "ratio_amp": 0.16,
        "value_amp": 0.28,
        "phase": 1.4,
    },
    "lpg_yield": {
        "name": "液化气收率",
        "unit": "%",
        "lower_limit": 15.0,
        "upper_limit": 26.0,
        "measurement": "rto_target_metrics",
        "base_before": 16.25,
        "ratio_mid": 0.98,
        "ratio_amp": 0.22,
        "value_amp": 0.16,
        "phase": 2.05,
    },
    "liquid_yield": {
        "name": "液收",
        "unit": "%",
        "lower_limit": 55.0,
        "upper_limit": 90.0,
        "measurement": "rto_target_metrics",
        "base_before": 78.94,
        "ratio_mid": 0.06,
        "ratio_amp": 0.03,
        "value_amp": 0.36,
        "phase": 2.7,
    },
}


OPTIMIZATION_VARIABLES = {
    "reactor_temperature": {
        "name": "反应温度",
        "tag_code": "150TIC1090",
        "unit": "℃",
        "measurement": "rto_variable_metrics",
    },
    "catalyst_oil_ratio": {
        "name": "剂油比",
        "tag_code": "150YLYQH",
        "unit": "",
        "measurement": "rto_variable_metrics",
    },
    "regenerator_temperature": {
        "name": "再生温度",
        "tag_code": "150TI1082",
        "unit": "℃",
        "measurement": "rto_variable_metrics",
    },
    "feed_preheat_temperature": {
        "name": "原料预热温度",
        "tag_code": "150TIC2006",
        "unit": "℃",
        "measurement": "rto_variable_metrics",
    },
}


MARKET_AND_LAB_METRICS = {
    "raw_heavy_feed_price": {
        "name": "重油新鲜进料价格",
        "group": "raw_material",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "heavy_aromatics_price": {
        "name": "重芳烃价格",
        "group": "raw_material",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "dry_gas_price": {
        "name": "干气价格",
        "group": "product",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "lpg_price": {
        "name": "液化气价格",
        "group": "product",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "gasoline_price": {
        "name": "汽油价格",
        "group": "product",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "heavy_naphtha_price": {
        "name": "重石脑油价格",
        "group": "product",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "diesel_price": {
        "name": "柴油价格",
        "group": "product",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "slurry_price": {
        "name": "油浆价格",
        "group": "product",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "medium_pressure_steam_price": {
        "name": "中压蒸汽价格",
        "group": "utility",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "low_pressure_steam_price": {
        "name": "低压蒸汽价格",
        "group": "utility",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "electricity_price": {
        "name": "电价格",
        "group": "utility",
        "unit": "元/kWh",
        "measurement": "market_metric_values",
    },
    "desalted_water_price": {
        "name": "除盐水价格",
        "group": "utility",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "circulating_water_price": {
        "name": "循环水价格",
        "group": "utility",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "hot_water_price": {
        "name": "低温热水价格",
        "group": "utility",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "wastewater_price": {
        "name": "污水价格",
        "group": "utility",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "mixed_feed_density": {
        "name": "混合进料密度",
        "group": "feed_lab",
        "unit": "kg/m³",
        "measurement": "market_metric_values",
    },
    "mixed_feed_carbon_residue": {
        "name": "混合进料残炭",
        "group": "feed_lab",
        "unit": "wt%",
        "measurement": "market_metric_values",
    },
    "gasoline_density": {
        "name": "汽油产品密度",
        "group": "product_lab",
        "unit": "kg/m³",
        "measurement": "market_metric_values",
    },
    "gasoline_fbp": {
        "name": "汽油产品终馏点",
        "group": "product_lab",
        "unit": "℃",
        "measurement": "market_metric_values",
    },
    "diesel_density": {
        "name": "柴油产品密度",
        "group": "product_lab",
        "unit": "kg/m³",
        "measurement": "market_metric_values",
    },
    "diesel_95pct_point": {
        "name": "柴油产品95%点",
        "group": "product_lab",
        "unit": "℃",
        "measurement": "market_metric_values",
    },
    "feed_cost": {
        "name": "原料成本",
        "group": "cost",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "processing_cost": {
        "name": "加工成本",
        "group": "cost",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "energy_cost": {
        "name": "能耗成本",
        "group": "cost",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
    "total_cost": {
        "name": "综合成本",
        "group": "cost",
        "unit": "元/吨",
        "measurement": "market_metric_values",
    },
}


HOME_RUNTIME_METRICS = {
    "rto_usage_rate": {
        "name": "RTO投用率",
        "unit": "%",
        "measurement": "rto_runtime_status",
    },
    "execution_rate": {
        "name": "RTO执行投用率",
        "unit": "%",
        "measurement": "rto_runtime_status",
    },
    "price_benefit": {
        "name": "影子价格效益",
        "unit": "元/吨",
        "measurement": "rto_runtime_status",
    },
    "cost_benefit": {
        "name": "成本价格效益",
        "unit": "元/吨",
        "measurement": "rto_runtime_status",
    },
}


INFLUX_SCHEMA_BLUEPRINT = {
    "bucket": "rto_mock_dev",
    "measurements": {
        "rto_target_metrics": {
            "description": "优化目标相关时序点",
            "tags": ["target_key", "target_name", "page"],
            "fields": ["before_value", "after_value", "increment_ratio", "lower_limit", "upper_limit"],
        },
        "rto_variable_metrics": {
            "description": "优化变量监测点",
            "tags": ["variable_key", "variable_name", "tag_code", "page"],
            "fields": [
                "current_value",
                "optimized_value",
                "model_value",
                "feedback_value",
                "output_setpoint",
                "lower_limit",
                "upper_limit",
                "apc_lower_limit",
                "apc_upper_limit",
            ],
        },
        "market_metric_values": {
            "description": "价格、化验、成本等外围指标",
            "tags": ["metric_key", "metric_name", "group", "page"],
            "fields": ["value"],
        },
        "rto_runtime_status": {
            "description": "首页运行状态和效益指标",
            "tags": ["status_key", "page"],
            "fields": ["value"],
        },
    },
}


def _format_number(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_datetime_local(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def _parse_datetime_local(raw_value: str | None, fallback: datetime) -> datetime:
    if not raw_value:
        return fallback
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return fallback


def _normalize_query_window(start_raw: str | None, end_raw: str | None, sample_minutes_raw: str | int | None):
    start_at = _parse_datetime_local(start_raw, DEFAULT_QUERY_START)
    end_at = _parse_datetime_local(end_raw, DEFAULT_QUERY_END)

    if end_at <= start_at:
        end_at = start_at + timedelta(hours=6)

    try:
        sample_minutes = int(sample_minutes_raw or DEFAULT_SAMPLE_MINUTES)
    except (TypeError, ValueError):
        sample_minutes = DEFAULT_SAMPLE_MINUTES

    sample_minutes = max(5, min(sample_minutes, 24 * 60))

    total_minutes = max(int((end_at - start_at).total_seconds() // 60), sample_minutes)
    point_count = total_minutes // sample_minutes + 1
    if point_count > 480:
        sample_minutes = math.ceil(total_minutes / 479)

    return start_at, end_at, sample_minutes


def _build_time_points(start_at: datetime, end_at: datetime, sample_minutes: int):
    step = timedelta(minutes=sample_minutes)
    points = []
    current = start_at
    while current <= end_at:
        points.append(current)
        current += step
    if points[-1] != end_at:
        points.append(end_at)
    return points


def build_target_form(selected_target_key: str = "lpg_yield"):
    form = {}
    for key, config in OPTIMIZATION_TARGETS.items():
        form[key] = {
            "selected": key == selected_target_key,
            "unit": config["unit"],
            "lower_limit": _format_number(config["lower_limit"]),
            "upper_limit": _format_number(config["upper_limit"]),
        }
    return form


def build_target_history_defaults():
    return {
        "start_at": _format_datetime_local(DEFAULT_QUERY_START),
        "end_at": _format_datetime_local(DEFAULT_QUERY_END),
        "sample_minutes": DEFAULT_SAMPLE_MINUTES,
    }


def _target_snapshot(target_key: str, point_at: datetime, offset_index: int = 0):
    config = OPTIMIZATION_TARGETS[target_key]
    wave_index = ((point_at - DEFAULT_QUERY_START).total_seconds() / 1800.0) + offset_index
    before_value = (
        config["base_before"]
        + math.sin(wave_index / 5.3 + config["phase"]) * config["value_amp"]
        + math.cos(wave_index / 8.1 + config["phase"]) * config["value_amp"] * 0.35
    )
    increment_ratio = (
        config["ratio_mid"]
        + math.sin(wave_index / 4.2 + config["phase"]) * config["ratio_amp"]
        + math.cos(wave_index / 7.5 + config["phase"]) * config["ratio_amp"] * 0.25
    )
    after_value = before_value * (1 + increment_ratio / 100.0)

    return {
        "before_value": before_value,
        "after_value": after_value,
        "increment_ratio": increment_ratio,
        "lower_limit": config["lower_limit"],
        "upper_limit": config["upper_limit"],
    }


def build_target_summary(snapshot_at: datetime):
    summary = {}
    for key, config in OPTIMIZATION_TARGETS.items():
        snapshot = _target_snapshot(key, snapshot_at)
        summary[key] = {
            "name": config["name"],
            "unit": config["unit"],
            "before_value": _format_number(snapshot["before_value"]),
            "after_value": _format_number(snapshot["after_value"]),
            "increment_ratio": _format_number(snapshot["increment_ratio"]),
            "lower_limit": _format_number(snapshot["lower_limit"]),
            "upper_limit": _format_number(snapshot["upper_limit"]),
        }
    return summary


def build_target_chart_payload(target_key: str, start_raw: str | None, end_raw: str | None, sample_minutes_raw: str | int | None):
    if target_key not in OPTIMIZATION_TARGETS:
        target_key = "lpg_yield"

    start_at, end_at, sample_minutes = _normalize_query_window(start_raw, end_raw, sample_minutes_raw)
    time_points = _build_time_points(start_at, end_at, sample_minutes)

    chart_points = []
    for index, point_at in enumerate(time_points):
        snapshot = _target_snapshot(target_key, point_at, offset_index=index)
        chart_points.append(
            {
                "timestamp": _format_datetime(point_at),
                "time_label": point_at.strftime("%m-%d %H:%M"),
                "before_value": round(snapshot["before_value"], 4),
                "after_value": round(snapshot["after_value"], 4),
                "increment_ratio": round(snapshot["increment_ratio"], 4),
            }
        )

    ratio_values = [point["increment_ratio"] for point in chart_points]
    target_config = OPTIMIZATION_TARGETS[target_key]

    return {
        "schema_blueprint": INFLUX_SCHEMA_BLUEPRINT,
        "query": {
            "target_key": target_key,
            "target_name": target_config["name"],
            "start_at": _format_datetime(start_at),
            "end_at": _format_datetime(end_at),
            "sample_minutes": sample_minutes,
        },
        "available_targets": [
            {
                "key": key,
                "name": config["name"],
                "unit": config["unit"],
                "measurement": config["measurement"],
            }
            for key, config in OPTIMIZATION_TARGETS.items()
        ],
        "targets_summary": build_target_summary(end_at),
        "chart": {
            "title": f"{target_config['name']}增幅比例图",
            "series_name": f"{target_config['name']}增幅比例",
            "unit": "%",
            "points": chart_points,
            "stats": {
                "min": round(min(ratio_values), 4),
                "max": round(max(ratio_values), 4),
                "avg": round(mean(ratio_values), 4),
                "latest": round(ratio_values[-1], 4),
            },
        },
    }

