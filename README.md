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

### 3) 存储层
- SQLite 持久化
- 运行记录表：`runs`
- 指标明细表：`metrics`
- 任务游标表：`task_state`

### 4) 推送层
- 飞书机器人 webhook 推送
- 无 webhook 时自动降级为本地日志输出

## 项目结构

```text
src/gb_monitor/
  cli.py           # 命令行入口
  config.py        # 环境配置
  collectors.py    # 采集器实现（示例文件驱动）
  schedule.py      # 调度规则
  storage.py       # SQLite 持久化
  service.py       # 任务编排与运行
  feishu.py        # 飞书推送与文本报告
examples/
  review_*.json
  delivery_*.json  # MVP 示例输入
tests/
  test_schedule.py
  test_collectors.py
  test_service.py
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
# 按需修改 .env 中的 webhook、数据文件路径、数据库路径
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

### 查看统计

```bash
gbm report --hours 24
```

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
2. 增加门店配置中心（多门店批量管理、优先级与动态开关）。
3. 增加告警策略（连续失败阈值、指标异常波动告警、Webhook 重试队列）。
4. 增加部署编排（systemd/cron + 健康检查 + 自动恢复）。

