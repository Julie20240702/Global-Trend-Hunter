# GlobalTrend-Hunter

海外爆款探测 + 中文本地化脚本生成（MVP）

## 功能
- 抓取（当前为mock，可替换真实爬虫）
- 爆款分析 Agent
- 中文适配 Agent
- 脚本生成 Agent
- 风险审核 Agent
- SQLite入库与报告输出

## 快速开始
1. 进入目录
2. 创建虚拟环境
3. 安装依赖
4. 配置 .env
5. 运行 main.py

示例命令（手动执行）：
- cd /Users/yanshiyi/Desktop/GlobalTrend-Hunter
- python3 -m venv .venv
- source .venv/bin/activate
- pip install -r requirements.txt
- cp .env.example .env
- python main.py
