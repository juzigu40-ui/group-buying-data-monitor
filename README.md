# 团购+外卖实时自动数据监测系统

> 悬赏：¥3,000 RMB  
> 当前状态：MVP v1（可运行骨架 + 可验收链路）

## 项目目标

构建一套可持续运行的数据监测系统，覆盖评价平台与外卖平台采集、数据存储、统计汇总、飞书推送与运行审计。

本仓库当前提供首版可运行实现，重点解决以下问题：
- 多平台任务统一调度
- 采集结果结构化落库（SQLite）
- 飞书推送可追踪
- 支持定时窗口策略（评价每2小时、外卖每30分钟）

## 当前交付范围（MVP v1）

### 1) 采集层
- 统一采集接口 `Collector`
- 已接入 6 个任务位（示例数据驱动）
  - 评价：大众点评 / 抖音来客 / 高德
  - 外卖：美团 / 饿了么 / 京东外卖

### 2) 调度层
- 评价窗口：10:00-20:00，间隔 2 小时
- 外卖窗口：10:30-12:30、17:00-19:00，间隔 30 分钟
- 支持 `scheduled`（按窗口）与 `all`（强制全量）两种模式
- 运行时会读取门店注册表，只执行“已绑定账号”的平台任务

### 3) 存储层
- SQLite 持久化
- 运行记录表：`runs`
- 指标明细表：`metrics`
- 任务游标表：`task_state`

### 4) 推送层
- 飞书机器人 webhook 推送
- 无 webhook 时自动降级为本地日志输出

## 当前版本边界

当前 PR 解决的是“多门店、单店单账号、无统一后台”的运行底座，已经能完成：
- 门店注册表管理
- 平台任务按账号绑定执行
- 采集结果落库
- 报表/飞书通知输出

当前 PR 还没有直接交付“实时舆情精筛引擎”：
- 现有 `review_douyin` 任务位是评价/内容采集入口，不是最终版精准舆情规则引擎
- 实时舆情需要在现有底座上补一层“门店规则匹配 + 排除词过滤 + 命中打分 + 去重推送”
- 这一层依赖真实门店样例来校准，否则容易继续出现误报

## 项目结构

```text
src/gb_monitor/
  cli.py           # 命令行入口
  config.py        # 环境配置
  collectors.py    # 采集器实现（示例文件驱动）
  store_registry.py # 多门店/多账号注册表
  schedule.py      # 调度规则
  storage.py       # SQLite 持久化
  service.py       # 任务编排与运行
  feishu.py        # 飞书推送与文本报告
examples/
  review_*.json
  delivery_*.json  # MVP 示例输入
  stores_registry.json
tests/
  test_schedule.py
  test_collectors.py
  test_service.py
  test_store_registry.py
```

## 快速开始

### 环境要求
- Python 3.11+

### 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 配置

```bash
cp .env.example .env
# 按需修改 .env 中的 webhook、数据文件路径、数据库路径、门店注册表路径
set -a; source .env; set +a
```

### 初始化数据库

```bash
gbm init-db
```

### 运行采集

```bash
# 强制执行全部任务（用于首轮验收）
gbm run --mode all --no-notify

# 按时间窗口调度执行
gbm run --mode scheduled --no-notify
```

运行时会打印 `registry_active_platforms=...`，用于确认当前账号绑定覆盖的平台范围。

### 查看统计

```bash
gbm report --hours 24
```

### 校验门店账号注册表（无统一账号场景）

```bash
gbm validate-registry --registry examples/stores_registry.json
```

说明：采集数据中的 `store_id` 需要与注册表里的 `store_id` 对齐，运行时仅保留已绑定门店的数据。

### 运行测试

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## 与需求的对应关系

- 数据采集范围：MVP 已建立评价/外卖双域结构与任务位
- 高频抓取：已实现窗口化调度与任务游标
- 数据分发：已实现飞书推送通道
- 稳定性：运行状态落库，失败任务有记录

## 下一步（接入真实生产数据）

1. 将 `examples/*.json` 输入替换为真实平台适配器（登录态、反爬策略、重试/限速）。
2. 对接真实门店注册表，支持“每个门店单独账号、无统一后台”的账号编排模式。
3. 增加告警策略（连续失败阈值、指标异常波动告警、Webhook 重试队列）。
4. 增加部署编排（systemd/cron + 健康检查 + 自动恢复）。

## 下一步（门店实时舆情）

如果业务侧要从“基础监控”往“实时舆情监测”推进，建议按下面顺序落地：

1. 每个门店建立独立规则
   - 门店名、别名、商圈、招牌菜、品牌词
2. 引入排除规则
   - 同名无关门店、无关地点、常见误报词
3. 内容命中打分
   - 标题、正文、地点、账号、热度综合评分
4. 结果分层
   - 高置信直接推送，中置信待确认，低置信丢弃
5. 后续再接经营数据
   - 只有接订单/经营数据后，才能继续做更稳的引流归因

建议客户先提供：
- 门店清单
- 每店平台账号
- 5-10 条“应该推送”的样例
- 5-10 条“应该过滤”的样例

可参考样例模板：
- `examples/store_signal_rules.template.json`

## 无统一账号场景的落地策略

针对“多门店、分散账号、没有统一 API 后台”的情况，系统采用门店注册表驱动：

- 每个门店独立维护平台账号映射（`stores_registry.json`）
- 每个平台绑定认证模式：`api` / `cookie` / `manual`
- 采集任务按“门店 x 平台”切片，失败隔离，不影响其他门店
- 账号责任人（`login_owner`）可追踪，便于失效会话排障
