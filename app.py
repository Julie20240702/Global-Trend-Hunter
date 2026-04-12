from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from datetime import datetime
from main import hunter_workflow, discover_hot_tracks
from scraper import get_trending_videos

app = FastAPI(title="GlobalTrend-Hunter MVP")


def _infer_track(niche: str, title: str = "") -> str:
    t = f"{niche} {title}".lower()
    if any(k in t for k in ["ai", "automation", "agent", "productivity", "workflow"]):
        return "AI工具/数字生产力"
    if any(k in t for k in ["story", "aita", "relationship", "tifu"]):
        return "Storytime/真实故事"
    if any(k in t for k in ["mindset", "habit", "psychology", "self"]):
        return "个人成长/心理认知"
    if any(k in t for k in ["routine", "life", "solo", "lifestyle"]):
        return "海外生活方式"
    return niche


def _render_rows(raw, niche: str) -> str:
    rows = []
    for i, x in enumerate(raw[:20], 1):
        url = x.get("url", "")
        xid = str(x.get("id", ""))
        source = "MOCK" if "example.com" in url or xid.startswith(("yt_00", "tt_", "ig_")) else "REAL"
        title = x.get("title", "")
        platform = x.get("platform", "")
        metrics = x.get("metrics", {}) or {}
        upvotes = metrics.get("upvotes", metrics.get("likes", 0))
        comments = metrics.get("comments", 0)
        created_utc = x.get("created_utc", 0)
        created_text = datetime.fromtimestamp(created_utc).strftime("%Y-%m-%d") if created_utc else "N/A"
        track = _infer_track(niche, title)
        rows.append(
            f'<li>{i}. [{source}] [{platform}] <b>赛道:</b> {track}<br/>{title}<br/>'
            f'指标: upvotes={upvotes} | comments={comments} | date={created_text}<br/>'
            f'<a href="{url}" target="_blank">{url}</a></li>'
        )
    return "<ul>" + "".join(rows) + "</ul>" if rows else "<p>无抓取结果</p>"


def page(msg: str = "", report_path: str = "", result_html: str = "") -> str:
    return f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>GlobalTrend-Hunter MVP</title>
      <style>
        body {{ font-family: Arial; max-width: 900px; margin: 30px auto; }}
        input, button {{ padding: 8px; margin: 6px 0; }}
        .box {{ background: #f6f8fa; padding: 12px; border-radius: 8px; white-space: pre-wrap; }}
        .result li {{ margin: 8px 0; line-height: 1.5; }}
      </style>
    </head>
    <body>
      <h2>GlobalTrend-Hunter（MVP）</h2>
      <p>有 <code>YOUTUBE_API_KEY</code> 时优先拉取真实 YouTube 数据；Reddit 走公开搜索接口；两者都失败才回退 mock。</p>

      <h3>模式A：自动发现赛道（推荐）</h3>
      <form method="post" action="/discover-run">
        <label>返回赛道数（Top K）：</label><br/>
        <input name="discover_top_k" type="number" value="5" /><br/>
        <label>候选赛道（逗号分隔，可留空）：</label><br/>
        <input name="discover_candidates" value="" /><br/>
        <label>每赛道处理条数：</label><br/>
        <input name="top_k" type="number" value="3" /><br/>
        <button type="submit">自动发现并生成报告</button>
      </form>

      <h3>模式B：手动指定赛道</h3>
      <form method="post" action="/run">
        <label>赛道 niche：</label><br/>
        <input name="niche" value="tech_niche" /><br/>
        <label>Top K：</label><br/>
        <input name="top_k" type="number" value="3" /><br/>
        <button type="submit">运行工作流</button>
      </form>

      <div class="box">
        <p>{msg}</p>
        <p>{report_path}</p>
      </div>

      <div class="box result">
        <h3>本次抓取样本（用于核验是否真实）</h3>
        {result_html}
      </div>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def home():
    return page()


@app.post("/run", response_class=HTMLResponse)
def run(niche: str = Form("tech_niche"), top_k: int = Form(3)):
    raw = get_trending_videos(niche)
    out = hunter_workflow(niche=niche, top_k=top_k, out_path="output/demo_report.md")

    result_html = _render_rows(raw, niche=niche)

    msg = "✅ 运行完成（近30天热帖优先）"
    report = f"报告路径：{out}"
    return page(msg=msg, report_path=report, result_html=result_html)

@app.post("/discover-run", response_class=HTMLResponse)
def discover_run(
    discover_top_k: int = Form(5),
    discover_candidates: str = Form(""),
    top_k: int = Form(3),
):
    candidates = [x.strip() for x in discover_candidates.split(",") if x.strip()] if discover_candidates else None
    board = discover_hot_tracks(candidates=candidates, tracks_top_k=discover_top_k, per_track_top_n=1)
    if not board:
        return page(msg="⚠️ 未发现可用赛道", report_path="", result_html="<p>无抓取结果</p>")

    best_niche = board[0]["niche"]
    raw = get_trending_videos(best_niche)
    out = hunter_workflow(niche=best_niche, top_k=top_k, out_path="output/demo_report.md")

    result_html = _render_rows(raw, niche=best_niche)

    lines = [f"✅ 自动发现完成，已使用赛道：{best_niche}（近30天热帖）", "赛道榜单："]
    for i, b in enumerate(board, 1):
        lines.append(f"{i}. {b['niche']} | hot_score={b['hot_score']} | samples={b['sample_count']}")
    msg = "\n".join(lines)
    report = f"报告路径：{out}"
    return page(msg=msg, report_path=report, result_html=result_html)
