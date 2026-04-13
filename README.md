# GlobalTrend-Hunter

海外爆款探测 + 中文本地化脚本生成（MVP / Demo-ready）

## 功能
- 抓取趋势视频（当前支持 mock；有 API key 时可走真实源）
- 爆款分析 / 中文本地化 / 脚本生成 / 风控审核
- SQLite 入库
- 生成演示报告 `output/demo_report.md`
- **自动发现热门赛道（A 功能）**

## 快速开始

```bash
cd /Users/yanshiyi/Desktop/GlobalTrend-Hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## A 功能：自动发现热门赛道（最小使用说明）

先看推荐赛道：

```bash
python main.py --discover-tracks --discover-top-k 5
```

指定候选赛道（逗号分隔）：

```bash
python main.py --discover-tracks --discover-top-k 3 --discover-candidates "ai_tools,saas,fitness,education"
```

> 输出会显示每个赛道的 `hot_score`，可据此选择赛道再跑完整工作流。

## 生成报告（手动指定赛道）

```bash
python main.py --niche tech_niche --top-k 3 --out output/demo_report.md
```

## Web 页面（8765）

```bash
uvicorn app:app --host 127.0.0.1 --port 8765 --reload
```

打开：
- `http://127.0.0.1:8765/run`

页面包含两种模式：
- 模式A：自动发现赛道并生成报告（默认取榜首赛道）
- 模式B：手动指定赛道运行

## 当前限制
- 抓取数据可能回退到 mock
- 无 API key 时，Agent 结果可能为 mock JSON
- 趋势分为启发式规则，后续可继续优化

- Here's the English translation of your GlobalTrend-Hunter documentation:


# GlobalTrend-Hunter

Overseas Viral Detection + Chinese Localization Script Generation (MVP / Demo-ready)

## Features
- Fetch trending videos (currently supports mock; can use real sources with API key)
- Viral analysis / Chinese localization / script generation / risk control review
- SQLite storage
- Generate demo report `output/demo_report.md`
- **Automatic hot niche discovery (Feature A)**

## Quick Start

```bash
cd /Users/yanshiyi/Desktop/GlobalTrend-Hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Feature A: Automatic Hot Niche Discovery (Minimum Usage Instructions)

View recommended niches:

```bash
python main.py --discover-tracks --discover-top-k 5
```

Specify candidate niches (comma-separated):

```bash
python main.py --discover-tracks --discover-top-k 3 --discover-candidates "ai_tools,saas,fitness,education"
```

The output will display a hot_score for each niche, allowing you to select a niche before running the full workflow.

Generate Report (Manually Specify Niche)

```bash
python main.py --niche tech_niche --top-k 3 --out output/demo_report.md
```

Web Page (Port 8765)

```bash
uvicorn app:app --host 127.0.0.1 --port 8765 --reload
```

Open:

· http://127.0.0.1:8765/run

The page includes two modes:

· Mode A: Automatically discover niches and generate a report (uses the top niche by default)
· Mode B: Manually specify a niche to run

Current Limitations

· Fetched data may fall back to mock
· Without an API key, Agent results may be mock JSON
· Trend scoring uses heuristic rules, which can be further optimized in the future

