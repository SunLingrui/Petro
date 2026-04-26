# InfluxDB 2.x RTO Schema

这份方案按 InfluxDB 2.x + Flux 查询设计。

先说明一件关键的事: InfluxDB 没有传统 SQL 意义上的“建表”。真正需要你创建的是 `bucket`，而 `measurement/tag/field` 会在你第一次写入数据时自动形成。

## 1. 先建 Bucket

```bash
export INFLUX_HOST="http://127.0.0.1:8086"
export INFLUX_ORG="your-org"
export INFLUX_TOKEN="your-token"

influx config create \
  --config-name local-rto \
  --host-url "$INFLUX_HOST" \
  --org "$INFLUX_ORG" \
  --token "$INFLUX_TOKEN" \
  --active

influx bucket create --name rto_mock_dev --org "$INFLUX_ORG"
```

如果你想让测试数据长期保留，可以不设置 retention。上面这条命令默认就是永久保留。

## 2. Measurement 设计

### `rto_target_metrics`

用途: `优化目标` 页面和首页的优化目标曲线。

推荐 tags:

- `page`: `optimization_target`
- `target_key`: `profit` / `gasoline_yield` / `diesel_yield` / `lpg_yield` / `liquid_yield`

推荐 fields:

- `before_value` float
- `after_value` float
- `increment_ratio` float
- `lower_limit` float
- `upper_limit` float

说明:

- 前端图表直接查 `increment_ratio`
- 上面的信息表直接取同一时刻的 `before_value`、`after_value`、`lower_limit`、`upper_limit`

### `rto_variable_metrics`

用途: `优化变量总览` 和四个变量详情页。

推荐 tags:

- `page`: `optimization_variables` / `reactor_temperature` / `catalyst_oil_ratio` / `regenerator_temperature` / `feed_preheat_temperature`
- `variable_key`: `reactor_temperature` / `catalyst_oil_ratio` / `regenerator_temperature` / `feed_preheat_temperature`
- `tag_code`: `150TIC1090` 这类位号

推荐 fields:

- `current_value`
- `optimized_value`
- `model_value`
- `feedback_value`
- `output_setpoint`
- `lower_limit`
- `upper_limit`
- `apc_lower_limit`
- `apc_upper_limit`
- `current_step`
- `max_step`

### `market_metric_values`

用途: `原料和产品价格`、`公用工程价格`、`化验分析数据`、`成本价格`、`价格与化验分析总览`。

推荐 tags:

- `page`: `raw_product_prices` / `utilities_prices` / `lab_analysis` / `cost_prices` / `price_lab_overview`
- `metric_group`: `raw_material` / `product` / `utility` / `feed_lab` / `product_lab` / `cost`
- `metric_key`: 例如 `raw_heavy_feed_price`、`gasoline_price`、`mixed_feed_density`

推荐 fields:

- `value`

### `rto_runtime_status`

用途: 首页数值型状态。

推荐 tags:

- `page`: `main`
- `status_key`: `today_runs` / `month_runs` / `usage_rate` / `price_benefit` / `cost_benefit`

推荐 fields:

- `value`

说明:

- 像“稳态/正常/未开始”这类字符串状态，不建议和核心时序指标混在一张 measurement 里做图。
- 这类字符串可以放单独 measurement，或者继续由后端配置接口返回。

## 3. 页面到 Schema 的映射

| 页面 | measurement | 主 tag |
| --- | --- | --- |
| 优化目标 | `rto_target_metrics` | `target_key` |
| 优化变量总览 | `rto_variable_metrics` | `variable_key` |
| 反应温度/剂油比/再生温度/原料预热温度 | `rto_variable_metrics` | `variable_key` |
| 原料和产品价格 | `market_metric_values` | `metric_group`, `metric_key` |
| 公用工程价格 | `market_metric_values` | `metric_group`, `metric_key` |
| 化验分析数据 | `market_metric_values` | `metric_group`, `metric_key` |
| 成本价格 | `market_metric_values` | `metric_group`, `metric_key` |
| 首页数值指标 | `rto_runtime_status` | `status_key` |

## 4. 写入样例数据

我已经把一份可直接导入的 line protocol 样例放在:

[`/Users/andy/Desktop/实习/Web/data/rto_seed.lp`](/Users/andy/Desktop/实习/Web/data/rto_seed.lp)

写入命令:

```bash
influx write \
  --bucket rto_mock_dev \
  --org "$INFLUX_ORG" \
  --precision s \
  --file /Users/andy/Desktop/实习/Web/data/rto_seed.lp
```

## 5. 你现在最需要的 Flux 查询

### 5.1 优化目标增幅比例图

用户会改:

- 开始时间
- 结束时间
- 采样时间
- 目标项

查询直接这样写:

```flux
from(bucket: "rto_mock_dev")
  |> range(start: 2026-04-24T00:00:00Z, stop: 2026-04-24T04:00:00Z)
  |> filter(fn: (r) =>
    r._measurement == "rto_target_metrics" and
    r.page == "optimization_target" and
    r.target_key == "lpg_yield" and
    r._field == "increment_ratio"
  )
  |> aggregateWindow(every: 30m, fn: mean, createEmpty: false)
  |> yield(name: "increment_ratio")
```

前端把:

- `start` 映射到 `range(start: ...)`
- `stop` 映射到 `range(stop: ...)`
- `sample` 映射到 `aggregateWindow(every: ...)`
- 目标选择映射到 `target_key`

### 5.2 优化目标信息表取最新一行

这个查询用于刷新表格里的 `before_value`、`after_value`、`lower_limit`、`upper_limit`:

```flux
from(bucket: "rto_mock_dev")
  |> range(start: 2026-04-24T00:00:00Z, stop: 2026-04-24T04:00:00Z)
  |> filter(fn: (r) =>
    r._measurement == "rto_target_metrics" and
    r.page == "optimization_target"
  )
  |> group(columns: ["target_key"])
  |> last()
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
```

说明:

- `group(columns: ["target_key"])` 后每个优化目标都会保留一条最新记录
- `pivot` 后前端更好拿字段

### 5.3 单个优化变量详情页

以反应温度为例:

```flux
from(bucket: "rto_mock_dev")
  |> range(start: 2026-04-24T00:00:00Z, stop: 2026-04-24T04:00:00Z)
  |> filter(fn: (r) =>
    r._measurement == "rto_variable_metrics" and
    r.variable_key == "reactor_temperature"
  )
  |> filter(fn: (r) =>
    r._field == "current_value" or
    r._field == "optimized_value" or
    r._field == "model_value" or
    r._field == "feedback_value" or
    r._field == "output_setpoint"
  )
  |> aggregateWindow(every: 30m, fn: mean, createEmpty: false)
```

### 5.4 价格/化验/成本页

以原料价格图为例:

```flux
from(bucket: "rto_mock_dev")
  |> range(start: 2026-04-24T00:00:00Z, stop: 2026-04-24T04:00:00Z)
  |> filter(fn: (r) =>
    r._measurement == "market_metric_values" and
    r.metric_group == "raw_material"
  )
  |> filter(fn: (r) => r._field == "value")
  |> aggregateWindow(every: 30m, fn: mean, createEmpty: false)
```

