# RTO InfluxDB 数据库说明文档

本文档说明当前 Flask RTO 项目使用的 InfluxDB 2.x 数据结构、字段含义、页面映射、导入脚本和常用查询方式。

当前项目使用 InfluxDB 存储实时优化相关时序数据，包括:

- RTO 优化目标数据
- RTO 优化变量数据
- 原料/产品/公用工程/化验/成本价格与分析数据
- 首页运行状态数值数据

## 1. 基本约定

### 1.1 InfluxDB 表

InfluxDB 的核心层级是:

| 层级 | 本项目含义 |
| --- | --- |
| `bucket` | 数据库/数据桶，当前默认 `rto_mock_dev` |
| `measurement` | 类似一张业务表，例如 `rto_target_metrics` |
| `tag` | 索引维度，适合放页面、指标 key、变量 key |
| `field` | 具体数值字段，例如 `value`、`current_value` |
| `_time` | 时间戳，所有时序数据必须有 |

### 1.2 当前默认连接配置

Flask 后端从环境变量读取 InfluxDB 配置。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `INFLUX_HOST` | `http://127.0.0.1:8086` | InfluxDB 服务地址 |
| `INFLUX_ORG` | `Patro` | InfluxDB organization 名称 |
| `INFLUX_BUCKET` | `rto_mock_dev` | 当前项目使用的 bucket |
| `INFLUX_TOKEN` | 无默认值 | API Token，必须自己 export |
| `APP_TIMEZONE` | `Asia/Shanghai` | 前端 datetime-local 使用的本地时区 |

启动 Flask 前建议在同一个终端执行:


### 1.3 时间格式约定

InfluxDB 内部查询使用 UTC 时间，例如:

```text
2026-04-25T06:00:00Z
```

前端页面表单使用浏览器的 `datetime-local`，按 `Asia/Shanghai` 解释，例如:

```text
2026-04-25T14:00
```

后端会把本地时间自动转换成 UTC 再拼接 Flux 查询。

### 1.4 采样间隔约定

前端可选采样间隔:

- `5 min`
- `15 min`
- `30 min`
- `60 min`
- `120 min`


## 2. Bucket

### 2.1 当前 bucket

| bucket | retention | 用途 |
| --- | --- | --- |
| `rto_mock_dev` | 默认永久保留 | 本地开发、静态测试、页面联调 |

### 2.2 创建 bucket

```bash
influx bucket create --name rto_mock_dev --org "$INFLUX_ORG"
```


## 3. Measurement 总览

| measurement | 类似 SQL 表名 | 主要用途 | 主要页面 |
| --- | --- | --- | --- |
| `rto_target_metrics` | 优化目标指标表 | 存储优化前后值、增幅比例、上下限 | RTO 优化目标 |
| `rto_variable_metrics` | 优化变量指标表 | 存储变量当前值、优化值、模型值、上下限等 | RTO 优化变量及变量详情页 |
| `market_metric_values` | 市场/化验/成本指标表 | 存储价格、化验分析、成本相关通用指标 | 价格与化验分析全部页面 |
| `rto_runtime_status` | 首页运行状态表 | 存储首页数字、文本、布尔状态 | RTO 首页 |

## 4. `rto_target_metrics`

### 4.1 用途

`rto_target_metrics` 用于“RTO 优化目标”页面。

页面功能:

- 上方优化目标信息表
- 优化目标增幅比例图
- 用户选择目标项、开始时间、结束时间、采样间隔后刷新图表

### 4.2 Tag 字段

| tag | 类型 | 是否必填 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | string | 是 | `optimization_target` | 页面标识，当前固定为优化目标页面 |
| `target_key` | string | 是 | `lpg_yield` | 优化目标唯一 key |

### 4.3 `target_key` 枚举

| target_key | 中文名称 | 单位 | 默认下限 | 默认上限 |
| --- | --- | --- | --- | --- |
| `profit` | 装置效益 | 元/吨 | `50.0` | `500.0` |
| `gasoline_yield` | 汽油收率 | `%` | `30.0` | `42.0` |
| `diesel_yield` | 柴油收率 | `%` | `18.0` | `35.0` |
| `lpg_yield` | 液化气收率 | `%` | `15.0` | `26.0` |
| `liquid_yield` | 液收 | `%` | `55.0` | `90.0` |

### 4.4 Field 字段

| field | 类型 | 示例 | 页面含义 |
| --- | --- | --- | --- |
| `before_value` | float | `16.2500` | 优化前值 |
| `current_value` | float | `16.4820` | 当前值，系统首页优化目标曲线使用 |
| `after_value` | float | `16.5543` | 优化后值 |
| `increment_ratio` | float | `1.1499` | 增幅比例，图表主曲线字段 |
| `lower_limit` | float | `15.0000` | 目标下限 |
| `upper_limit` | float | `26.0000` | 目标上限 |

### 4.5 Line Protocol 示例

```text
rto_target_metrics,page=optimization_target,target_key=lpg_yield before_value=16.2500,current_value=16.4820,after_value=16.5543,increment_ratio=1.1499,lower_limit=15.0000,upper_limit=26.0000 1776988800
```


## 5. `rto_variable_metrics`

### 5.1 用途

`rto_variable_metrics` 用于“RTO 优化变量”总览页和四个变量详情页。

页面包括:

- 优化变量总览
- 反应温度监测
- 剂油比监测
- 再生温度监测
- 原料预热温度监测

### 5.2 Tag 字段

| tag | 类型 | 是否必填 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | string | 是 | `reactor_temperature` | 页面或变量详情标识 |
| `variable_key` | string | 是 | `reactor_temperature` | 优化变量唯一 key |
| `tag_code` | string | 是 | `150TIC1090` | 工艺位号 |

### 5.3 `variable_key` 枚举

| variable_key | 中文名称 | 页面 slug | 位号 | 单位 |
| --- | --- | --- | --- | --- |
| `reactor_temperature` | 反应温度 | `reactor-temperature` | `150TIC1090` | `℃` |
| `catalyst_oil_ratio` | 剂油比 | `catalyst-oil-ratio` | `150YLYQH` | 空 |
| `regenerator_temperature` | 再生温度 | `regenerator-temperature` | `150TI1082` | `℃` |
| `feed_preheat_temperature` | 原料预热温度 | `feed-preheat-temperature` | `150TIC2006` | `℃` |

### 5.4 Field 字段

| field | 类型 | 示例 | 页面含义 |
| --- | --- | --- | --- |
| `current_value` | float | `520.3295` | 当前值 |
| `last_optimized_value` | float | `522.2500` | 上一次优化值 |
| `optimized_value` | float | `520.5274` | 当前优化结果值 |
| `model_value` | float | `522.2500` | 智能混合模型优化结果值 |
| `feedback_value` | float | `520.5274` | 反馈调优优化结果值 |
| `output_setpoint` | float | `521.9592` | 输出设定值 |
| `delta_vs_output` | float | `-1.4318` | 优化结果值与原输出设定值差 |
| `lower_limit` | float | `518.5000` | 优化下限 |
| `upper_limit` | float | `522.3000` | 优化上限 |
| `current_step` | float | `0.3000` | 当前步幅 |
| `max_step` | float | `1.0000` | 最大步幅 |
| `apc_lower_limit` | float | `520.5000` | APC 下限 |
| `apc_upper_limit` | float | `522.5000` | APC 上限 |
| `dcs_lower_limit` | float | `0.0000` | DCS 下限 |
| `dcs_upper_limit` | float | `600.0000` | DCS 上限 |
| `push_enabled` | bool | `true` | 优化结果下达开关 |
| `apc_status` | string | `"未接受"` | APC 接受状态 |


### 5.5 Line Protocol 示例

```text
rto_variable_metrics,page=reactor_temperature,variable_key=reactor_temperature,tag_code=150TIC1090 current_value=520.3295,last_optimized_value=522.2500,optimized_value=520.5274,model_value=522.2500,feedback_value=520.5274,output_setpoint=521.9592,delta_vs_output=-1.4318,lower_limit=518.5000,upper_limit=522.3000,current_step=0.3000,max_step=1.0000,apc_lower_limit=520.5000,apc_upper_limit=522.5000,dcs_lower_limit=0.0000,dcs_upper_limit=600.0000,push_enabled=true,apc_status="未接受" 1777096800
```


## 6. `market_metric_values`

### 6.1 用途

`market_metric_values` 是一个通用指标表，用来承载价格、化验分析和成本数据。

当前覆盖页面:

- 价格与化验分析总览
- 原料和产品价格
- 公用工程价格
- 化验分析数据
- 成本价格

### 6.2 Tag 字段

| tag | 类型 | 是否必填 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | string | 是 | `raw_product_prices` | 数据所属页面 |
| `metric_group` | string | 是 | `raw_material` | 指标分组 |
| `metric_key` | string | 是 | `gasoline_price` | 指标唯一 key |

### 6.3 Field 字段

| field | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `value` | float | `4843.0000` | 指标数值 |

### 6.4 `metric_group` 枚举

| metric_group | 中文含义 | 页面 |
| --- | --- | --- |
| `raw_material` | 原料价格 | 原料和产品价格 |
| `product` | 产品价格 | 原料和产品价格 |
| `utility` | 公用工程价格 | 公用工程价格 |
| `feed_lab` | 原料化验分析 | 化验分析数据 |
| `product_lab` | 产品化验分析 | 化验分析数据 |
| `cost` | 成本价格 | 成本价格 |

### 6.5 原料价格指标

| metric_group | metric_key | 中文名称 | 单位 |
| --- | --- | --- | --- |
| `raw_material` | `raw_heavy_feed_price` | 重油新鲜进料价格 | 元/吨 |
| `raw_material` | `heavy_aromatics_price` | 重芳烃价格 | 元/吨 |

### 6.6 产品价格指标

| metric_group | metric_key | 中文名称 | 单位 |
| --- | --- | --- | --- |
| `product` | `dry_gas_price` | 干气价格 | 元/吨 |
| `product` | `lpg_price` | 液化气价格 | 元/吨 |
| `product` | `gasoline_price` | 汽油价格 | 元/吨 |
| `product` | `heavy_naphtha_price` | 重石脑油价格 | 元/吨 |
| `product` | `diesel_price` | 柴油价格 | 元/吨 |
| `product` | `slurry_price` | 油浆价格 | 元/吨 |

### 6.7 公用工程价格指标

| metric_group | metric_key | 中文名称 | 单位 |
| --- | --- | --- | --- |
| `utility` | `medium_pressure_steam_price` | 中压蒸汽 | 元/吨 |
| `utility` | `low_pressure_steam_price` | 低压蒸汽 | 元/吨 |
| `utility` | `electricity_price` | 电 | 元/kWh |
| `utility` | `desalted_water_price` | 除盐水 | 元/吨 |
| `utility` | `circulating_water_price` | 循环水 | 元/吨 |
| `utility` | `hot_water_price` | 低温热水 | 元/吨 |
| `utility` | `wastewater_price` | 污水 | 元/吨 |

### 6.8 原料化验分析指标

| metric_group | metric_key | 中文名称 | 单位 |
| --- | --- | --- | --- |
| `feed_lab` | `mixed_feed_density` | 混合进料密度 | kg/m³ |
| `feed_lab` | `mixed_feed_carbon_residue` | 混合进料残炭 | wt% |

### 6.9 产品化验分析指标

| metric_group | metric_key | 中文名称 | 单位 |
| --- | --- | --- | --- |
| `product_lab` | `gasoline_density` | 汽油产品密度 | kg/m³ |
| `product_lab` | `gasoline_fbp` | 汽油产品终馏点 | ℃ |
| `product_lab` | `diesel_density` | 柴油产品密度 | kg/m³ |
| `product_lab` | `diesel_95pct_point` | 柴油产品95%点 | ℃ |

### 6.10 成本价格指标

| metric_group | metric_key | 中文名称 | 单位 |
| --- | --- | --- | --- |
| `cost` | `feed_cost` | 原料成本 | 元/吨 |
| `cost` | `processing_cost` | 加工成本 | 元/吨 |
| `cost` | `energy_cost` | 能耗成本 | 元/吨 |
| `cost` | `total_cost` | 综合成本 | 元/吨 |

### 6.11 Line Protocol 示例

原料价格:

```text
market_metric_values,page=raw_product_prices,metric_group=raw_material,metric_key=raw_heavy_feed_price value=3781.0000 1777096800
```

产品价格:

```text
market_metric_values,page=raw_product_prices,metric_group=product,metric_key=gasoline_price value=4843.0000 1777096800
```

公用工程价格:

```text
market_metric_values,page=utilities_prices,metric_group=utility,metric_key=electricity_price value=0.5900 1777096800
```

化验分析:

```text
market_metric_values,page=lab_analysis,metric_group=feed_lab,metric_key=mixed_feed_density value=925.0000 1777096800
```

成本价格:

```text
market_metric_values,page=cost_prices,metric_group=cost,metric_key=total_cost value=3990.6600 1777096800
```

## 7. `rto_runtime_status`

### 7.1 用途

`rto_runtime_status` 用于首页运行状态。当前首页截图中的数字、时间文本、中文状态和总开关都从这个 measurement 读取。

### 7.2 Tag 字段

| tag | 类型 | 是否必填 | 示例 | 说明 |
| --- | --- | --- | --- | --- |
| `page` | string | 是 | `main` | 页面标识 |
| `status_key` | string | 是 | `today_runs` | 首页状态 key |

### 7.3 `status_key` 枚举

| status_key | 中文含义 | 使用 field | 单位/格式 |
| --- | --- | --- | --- |
| `today_runs` | RTO今日运行次数 | `value` | 次 |
| `yesterday_runs` | RTO昨日运行次数 | `value` | 次 |
| `month_runs` | RTO本月运行次数 | `value` | 次 |
| `total_runs` | RTO累计运行次数 | `value` | 次 |
| `latest_plan_time` | 最新优化计算时刻 | `text_value` | `HH:mm:ss` |
| `next_plan_remaining` | 距下次优化计算剩余时间 | `value` | 分钟 |
| `runtime_days` | RTO运行天数 | `value` | 天 |
| `usage_rate` | RTO投用率 | `value` | `%` |
| `master_switch_on` | RTO总开关 | `bool_value` | true/false |
| `equipment_status` | 装置稳态状态 | `text_value` | 例如 `稳态` |
| `runtime_status` | RTO运行状态 | `text_value` | 例如 `正常` |
| `apc_status` | RTO与APC联动状态 | `text_value` | 例如 `非联动` |
| `program_status` | RTO程序运行状态 | `text_value` | 例如 `未开始` |
| `execution_rate` | RTO执行投用率 | `value` | `%` |
| `price_benefit` | 影子价格效益 | `value` | 元/吨 |
| `cost_benefit` | 成本价格效益 | `value` | 元/吨 |

### 7.4 Field 字段

| field | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `value` | float | `85.0000` | 数值型状态，例如运行次数、投用率、效益 |
| `text_value` | string | `"正常"` | 文本型状态，例如运行状态、APC联动状态、最新优化计算时刻 |
| `bool_value` | bool | `true` | 布尔型状态，目前用于 RTO 总开关 |

不要把数字、字符串、布尔值都写入同一个 field。InfluxDB 同一个 measurement 下同名 field 的类型应保持一致，所以当前拆成 `value`、`text_value`、`bool_value` 三类。

### 7.5 Line Protocol 示例

```text
rto_runtime_status,page=main,status_key=today_runs value=85 1777116600
rto_runtime_status,page=main,status_key=latest_plan_time text_value="14:40:00" 1777116600
rto_runtime_status,page=main,status_key=master_switch_on bool_value=true 1777116600
rto_runtime_status,page=main,status_key=runtime_status text_value="正常" 1777116600
```

## 8. 页面和接口映射

### 8.1 页面映射

| 页面 | Flask route | measurement | 主要 tag |
| --- | --- | --- | --- |
| RTO 首页 | `/main` | `rto_runtime_status`, `rto_target_metrics` | `status_key`, `target_key` |
| RTO 优化目标 | `/rto/optimization-target` | `rto_target_metrics` | `target_key` |
| RTO 优化变量总览 | `/rto/optimization-variables` | `rto_variable_metrics` | `variable_key` |
| 反应温度详情 | `/rto/variables/reactor-temperature` | `rto_variable_metrics` | `variable_key=reactor_temperature` |
| 剂油比详情 | `/rto/variables/catalyst-oil-ratio` | `rto_variable_metrics` | `variable_key=catalyst_oil_ratio` |
| 再生温度详情 | `/rto/variables/regenerator-temperature` | `rto_variable_metrics` | `variable_key=regenerator_temperature` |
| 原料预热温度详情 | `/rto/variables/feed-preheat-temperature` | `rto_variable_metrics` | `variable_key=feed_preheat_temperature` |
| 价格与化验分析总览 | `/analytics/overview` | `market_metric_values` | `metric_group`, `metric_key` |
| 原料和产品价格 | `/analytics/raw-product-prices` | `market_metric_values` | `metric_group=raw_material/product` |
| 公用工程价格 | `/analytics/utilities-prices` | `market_metric_values` | `metric_group=utility` |
| 化验分析数据 | `/analytics/lab-analysis` | `market_metric_values` | `metric_group=feed_lab/product_lab` |
| 成本价格 | `/analytics/cost-prices` | `market_metric_values` | `metric_group=cost` |

### 8.2 JSON 数据接口

| 接口 | 参数 | 返回内容 |
| --- | --- | --- |
| `/main/status/data` | 无 | 首页运行状态数据 |
| `/main/target-chart/data` | `target`, `start_at`, `end_at`, `sample_minutes` | 首页优化目标曲线 |
| `/rto/optimization-target/data` | `target`, `start_at`, `end_at`, `sample_minutes` | 优化目标表格和增幅比例曲线 |
| `/rto/variables/<variable_slug>/data` | `start_at`, `end_at`, `sample_minutes` | 单个变量卡片数据和曲线 |
| `/analytics/raw-product-prices/data` | `group`, `start_at`, `end_at`, `sample_minutes` | 原料或产品价格曲线 |
| `/analytics/utilities-prices/data` | `start_at`, `end_at`, `sample_minutes` | 公用工程价格曲线 |
| `/analytics/lab-analysis/data` | `group`, `start_at`, `end_at`, `sample_minutes` | 原料或产品化验分析曲线 |
| `/analytics/cost-prices/data` | `start_at`, `end_at`, `sample_minutes` | 成本价格曲线 |


## 9. 测试数据

### 9.1 数据生成脚本

测试数据由下面脚本生成:

```text
/Users/andy/Desktop/实习/Web/scripts/generate_rto_seed.py
```

输出文件:

```text
/Users/andy/Desktop/实习/Web/data/rto_seed.lp
```

当前 seed 数据覆盖:

| measurement | 数据区间 | 间隔 | 说明 |
| --- | --- | --- | --- |
| `rto_target_metrics` | `2026-04-18 00:00` 至 `2026-04-25 12:00` UTC | 30 分钟 | 优化目标测试数据，含更明显波动 |
| `rto_variable_metrics` | `2026-04-18 00:00` 至 `2026-04-25 12:00` UTC | 30 分钟 | 优化变量测试数据，含更明显波动 |
| `market_metric_values` | `2026-04-18 00:00` 至 `2026-04-25 12:00` UTC | 30 分钟 | 价格、化验、成本测试数据，含更明显波动 |
| `rto_runtime_status` | `2026-04-18 00:00` 至 `2026-04-25 12:00` UTC | 30 分钟 | 首页状态测试数据 |

换算到前端本地时间，推荐测试区间是:

```text
2026-04-18T08:00 至 2026-04-25T20:00
```

### 9.2 生成并导入

推荐直接使用脚本:

```bash
export INFLUX_HOST="http://127.0.0.1:8086"
export INFLUX_ORG="Patro"
export INFLUX_BUCKET="rto_mock_dev"
export INFLUX_TOKEN="你的真实 token"

bash /Users/andy/Desktop/实习/Web/scripts/import_rto_seed.sh.example
```
