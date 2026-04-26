from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from datetime import datetime
from dotenv import load_dotenv
from html import escape
from main import hunter_workflow, discover_hot_tracks
from scraper import get_trending_videos
import threading
import traceback
import uuid
from typing import Any, Dict

load_dotenv()

app = FastAPI(title="GlobalTrend-Hunter MVP")
_JOBS: Dict[str, Dict[str, Any]] = {}


def _infer_track(niche: str, title: str = "") -> str:
    # 修复：优先使用用户输入的赛道，避免因标题关键词导致前端显示串台
    n = (niche or "").strip()
    if n:
        return n

    t = f"{title}".lower()
    if any(k in t for k in ["ai", "automation", "agent", "productivity", "workflow"]):
        return "AI工具/数字生产力"
    if any(k in t for k in ["story", "aita", "relationship", "tifu"]):
        return "Storytime/真实故事"
    if any(k in t for k in ["mindset", "habit", "psychology", "self"]):
        return "个人成长/心理认知"
    if any(k in t for k in ["routine", "life", "solo", "lifestyle"]):
        return "海外生活方式"
    return "未分类"


def _render_rows(raw, niche: str) -> str:
    rows = []
    for i, x in enumerate(raw[:20], 1):
        url = x.get("url", "")
        xid = str(x.get("id", ""))
        source = "MOCK" if "example.com" in url or xid.startswith(("yt_00", "tt_", "ig_")) else "REAL"
        title = x.get("title", "")
        title_zh = x.get("title_zh", "")
        if not title_zh:
            title_zh = x.get("title_cn", "")
        if not title_zh:
            title_zh = x.get("translated_title", "")
        platform = x.get("platform", "")
        metrics = x.get("metrics", {}) or {}
        upvotes = metrics.get("upvotes", metrics.get("likes", 0))
        comments = metrics.get("comments", 0)
        final_score = x.get("final_score", metrics.get("final_score", 0))
        rel_score = x.get("relevance_score", metrics.get("relevance_score", 0))
        trend_signal = x.get("trend_signal_score", metrics.get("trend_signal_score", 0))
        copy_signal = x.get("copy_signal_score", metrics.get("copy_signal_score", 0))
        llm_score = x.get("llm_relevance_score", None)
        llm_reason = ""
        llm_error = ""
        llm_fallback = False
        for r in x.get("reasons", []) or []:
            if not isinstance(r, str):
                continue
            if r.startswith("llm_reason:") and not llm_reason:
                llm_reason = r.split("llm_reason:", 1)[1]
            elif r.startswith("llm_error:") and not llm_error:
                llm_error = r.split("llm_error:", 1)[1]
            elif r.startswith("llm:fallback:"):
                llm_fallback = True

        if llm_score is None:
            llm_score_txt = "未进入本轮评审"
            if llm_error:
                llm_score_txt = f"未评审（{llm_error}）"
            elif llm_fallback:
                llm_score_txt = "未评审（模型未返回有效结果）"
        else:
            llm_score_txt = f"{float(llm_score):.2f}"

        why_selected = x.get("why_selected", "")
        selection_reason = x.get("selection_reason", "")
        created_utc = x.get("created_utc", 0)
        created_text = datetime.fromtimestamp(created_utc).strftime("%Y-%m-%d") if created_utc else "N/A"
        track = _infer_track(niche, title)
        detail_bits = [
            f"相关性 {float(rel_score):.2f}",
            f"趋势信号 {float(trend_signal):.2f}",
            f"可复制性 {float(copy_signal):.2f}",
            f"综合分 {float(final_score):.2f}",
            f"LLM评审 {llm_score_txt}",
        ]
        rows.append(
            '<article class="result-item">'
            f'<div class="item-topline"><span class="rank">#{i}</span><span class="pill">{escape(platform)}</span><span class="pill">{escape(track)}</span><span class="pill">{source}</span></div>'
            f'<h3>{escape(title)}</h3>'
            f'{(f"<p class=\"title-zh\">{escape(title_zh)}</p>") if title_zh else ""}'
            f'<div class="meta-row"><span>👍 {upvotes}</span><span>💬 {comments}</span><span>📅 {created_text}</span></div>'
            f'<a class="open-link" href="{escape(url)}" target="_blank">打开原帖 ↗</a>'
            '<details class="details">'
            '<summary>查看入选理由与评分</summary>'
            f'<p>{escape(" | ".join(detail_bits))}</p>'
            f'{("<p><b>LLM理由：</b>" + escape(llm_reason) + "</p>") if llm_reason else ""}'
            f'{("<p><b>选择原因：</b>" + escape(selection_reason) + "</p>") if selection_reason else ""}'
            f'{("<p><b>入选说明：</b>" + escape(why_selected) + "</p>") if why_selected else ""}'
            f'<p class="raw-link">{escape(url)}</p>'
            '</details>'
            '</article>'
        )
    return '<div class="results-list">' + "".join(rows) + "</div>" if rows else '<p class="empty">没有抓到可用结果，可以换一个更具体的 niche。</p>'


def page(msg: str = "", report_path: str = "", result_html: str = "") -> str:
    return f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>GlobalTrend-Hunter MVP</title>
      <style>
        * {{ box-sizing: border-box; }}
        body {{
          font-family: Arial, Helvetica, sans-serif;
          max-width: 980px;
          margin: 28px auto;
          padding: 0 18px 40px;
          color: #18221f;
          background: #f7f8f7;
        }}
        h2 {{ margin-bottom: 6px; }}
        .subtle {{ color: #5a6762; line-height: 1.5; margin-top: 0; }}
        .panel {{
          background: #ffffff;
          border: 1px solid #dce3df;
          border-radius: 8px;
          padding: 16px;
          margin: 18px 0;
        }}
        .forms {{
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 14px;
          align-items: start;
        }}
        label {{ display: block; color: #34413c; font-size: 14px; margin-top: 10px; }}
        input {{
          width: 100%;
          padding: 9px 10px;
          margin-top: 5px;
          border: 1px solid #bac6c0;
          border-radius: 6px;
          background: #fff;
          color: #18221f;
        }}
        button {{
          margin-top: 14px;
          padding: 10px 14px;
          border: 0;
          border-radius: 6px;
          background: #246b52;
          color: #fff;
          font-weight: 700;
          cursor: pointer;
        }}
        button[disabled] {{ opacity: 0.72; cursor: wait; }}
        .box {{
          background: #ffffff;
          border: 1px solid #dce3df;
          padding: 12px 14px;
          border-radius: 8px;
          white-space: pre-wrap;
          margin: 16px 0;
        }}
        .result h3 {{ margin-top: 0; }}
        .results-list {{ display: grid; gap: 12px; }}
        .result-item {{
          background: #ffffff;
          border: 1px solid #dce3df;
          border-radius: 8px;
          padding: 14px;
        }}
        .item-topline {{ display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }}
        .rank {{ font-weight: 700; color: #246b52; }}
        .pill {{
          border: 1px solid #cbd6d1;
          border-radius: 999px;
          padding: 2px 8px;
          font-size: 12px;
          color: #4d5a55;
          background: #f8fbf9;
        }}
        .result-item h3 {{
          font-size: 18px;
          line-height: 1.35;
          margin: 0 0 6px;
          overflow-wrap: anywhere;
        }}
        .title-zh {{
          color: #246b52;
          font-size: 16px;
          line-height: 1.45;
          margin: 0 0 10px;
          overflow-wrap: anywhere;
        }}
        .meta-row {{
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          color: #5a6762;
          font-size: 14px;
          margin: 10px 0;
        }}
        .open-link {{
          display: inline-block;
          color: #9b2f24;
          font-weight: 700;
          text-decoration: none;
          margin-top: 2px;
        }}
        .open-link:hover {{ text-decoration: underline; }}
        .details {{
          margin-top: 10px;
          border-top: 1px solid #edf1ef;
          padding-top: 9px;
          color: #4f5d58;
          font-size: 13px;
        }}
        .details summary {{ cursor: pointer; color: #246b52; font-weight: 700; }}
        .raw-link {{ overflow-wrap: anywhere; color: #6a7772; }}
        .empty {{ color: #6a7772; }}
        .loading-overlay {{
          position: fixed;
          inset: 0;
          display: none;
          align-items: center;
          justify-content: center;
          background: rgba(247, 248, 247, 0.86);
          z-index: 20;
        }}
        .loading-card {{
          width: min(480px, calc(100% - 32px));
          background: #ffffff;
          border: 1px solid #dce3df;
          border-radius: 8px;
          padding: 18px;
          box-shadow: 0 12px 32px rgba(24, 34, 31, 0.14);
        }}
        .loading-title {{
          font-size: 18px;
          margin-bottom: 8px;
        }}
        .loading-stage {{
          margin: 12px 0 8px;
          color: #246b52;
          font-weight: 700;
        }}
        .loading-time {{
          color: #5a6762;
          font-size: 14px;
          margin-top: 10px;
        }}
        .loading-tips {{
          margin: 12px 0 0;
          padding-left: 18px;
          color: #5a6762;
          font-size: 14px;
          line-height: 1.55;
        }}
        .bar {{
          height: 6px;
          background: #dce3df;
          border-radius: 6px;
          overflow: hidden;
          margin-top: 12px;
        }}
        .bar span {{
          display: block;
          height: 100%;
          width: 35%;
          background: #246b52;
          animation: slide 1.1s infinite alternate;
        }}
        @keyframes slide {{
          from {{ transform: translateX(-20%); }}
          to {{ transform: translateX(210%); }}
        }}
      </style>
      <script>
        let loadingTimer = null;
        const loadingStages = [
          '正在连接 Reddit / YouTube 数据源',
          '正在合并候选帖子并去重',
          '正在计算热度评分与相关性',
          '正在进行 LLM 语义审核（如已开启）',
          '正在整理结果并渲染页面'
        ];

        function markRunning(form) {{
          const overlay = document.getElementById('loading-overlay');
          const stageEl = document.getElementById('loading-stage');
          const timerEl = document.getElementById('loading-time');
          const submitBtn = form.querySelector('button[type="submit"]');
          if (overlay) overlay.style.display = 'flex';
          if (submitBtn) submitBtn.disabled = true;

          const started = Date.now();
          let idx = 0;
          if (stageEl) stageEl.textContent = loadingStages[idx];
          loadingTimer = setInterval(() => {{
            idx = (idx + 1) % loadingStages.length;
            if (stageEl) stageEl.textContent = loadingStages[idx];
            if (timerEl) {{
              const sec = Math.floor((Date.now() - started) / 1000);
              timerEl.textContent = `已运行 ${{sec}} 秒，首次冷启动可能需要 20~90 秒`;
            }}
          }}, 2200);
          return true;
        }}
      </script>
    </head>
    <body>
      <div id="loading-overlay" class="loading-overlay">
        <div class="loading-card">
          <div class="loading-title"><b>正在抓取趋势</b></div>
          <div class="loading-stage" id="loading-stage">准备开始...</div>
          <div class="bar"><span></span></div>
          <div class="loading-time" id="loading-time">已运行 0 秒</div>
          <ul class="loading-tips">
            <li>默认会优先使用近30天热帖，速度更稳定</li>
            <li>开启 LLM 语义评分时，耗时会明显增加</li>
            <li>若你在演示，建议先用同一 niche 热身一次</li>
          </ul>
        </div>
      </div>

      <h2>GlobalTrend-Hunter MVP</h2>
      <p class="subtle">输入一个海外赛道关键词，抓取趋势候选并用 LLM 做语义审核。默认展示精简结果，详细评分可以展开查看。</p>

      <div class="panel forms">
        <section>
          <h3>自动发现高潜赛道</h3>
          <form method="post" action="/discover-run" onsubmit="return markRunning(this)">
            <label>候选赛道（逗号分隔，可空）</label>
            <input name="discover_candidates" placeholder="tech, ai tools, fitness, travel" />
            <label>返回前几名赛道</label>
            <input name="discover_top_k" type="number" value="5" />
            <label>入选赛道生成报告 Top K 视频</label>
            <input name="top_k" type="number" value="3" />
            <button type="submit">自动发现并生成报告</button>
          </form>
        </section>

        <section>
          <h3>按指定赛道抓取</h3>
          <form method="post" action="/run" onsubmit="return markRunning(this)">
            <label>赛道 niche</label>
            <input name="niche" value="tech_niche" />
            <label>Top K</label>
            <input name="top_k" type="number" value="3" />
            <label>绕过缓存，1=是，0=否</label>
            <input name="nocache" type="number" value="0" />
            <label>启用 LLM 语义评分，1=是，0=否</label>
            <input name="enable_llm" type="number" value="1" />
            <label>生成脚本报告，1=是，0=否</label>
            <input name="generate_report" type="number" value="0" />
            <button type="submit">抓取趋势</button>
          </form>
        </section>
      </div>

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


@app.get("/run", response_class=HTMLResponse)
def run_page():
    return page(msg="请在表单里填写赛道后点击“抓取趋势”。")


def _run_job(job_id: str, payload: Dict[str, Any]) -> None:
    try:
        _JOBS[job_id].update({"status": "running", "stage": "准备抓取候选内容"})
        kind = payload.get("kind")

        if kind == "run":
            niche = str(payload.get("niche", "tech_niche"))
            top_k = int(payload.get("top_k", 3) or 3)
            nocache = int(payload.get("nocache", 0) or 0)
            enable_llm = int(payload.get("enable_llm", 0) or 0)
            generate_report = int(payload.get("generate_report", 0) or 0)

            if nocache == 1:
                try:
                    from scraper import _TREND_CACHE
                    prefix = f"{niche.strip().lower()}|"
                    for key in list(_TREND_CACHE.keys()):
                        if key.startswith(prefix):
                            _TREND_CACHE.pop(key, None)
                except Exception:
                    pass

            _JOBS[job_id]["stage"] = "正在抓取候选并做规则排序"
            raw_fast = get_trending_videos(niche, enable_llm=False, translate_titles=False)
            result_html = _render_rows(raw_fast, niche=niche)
            _JOBS[job_id].update({
                "status": "partial",
                "stage": "已返回规则结果，正在后台补充 LLM 语义评审" if enable_llm == 1 else "规则结果已完成",
                "msg": "已先返回规则排序结果，LLM 评审完成后会自动更新。" if enable_llm == 1 else "✅ 抓取完成（快速模式，未启用 LLM）。",
                "report": "",
                "result_html": result_html,
            })

            if enable_llm == 1:
                _JOBS[job_id]["stage"] = "正在进行 LLM 语义评审与标题整理"
                raw = get_trending_videos(niche, enable_llm=True, translate_titles=False)
            else:
                raw = raw_fast
            result_html = _render_rows(raw, niche=niche)

            if generate_report == 1:
                _JOBS[job_id]["stage"] = "正在生成脚本报告"
                out = hunter_workflow(niche=niche, top_k=top_k, out_path="output/demo_report.md", raw_data=raw)
                msg = "✅ 抓取与脚本报告生成完成（近30天热帖优先）"
                report = f"报告路径：{out}"
            else:
                llm_note = "已启用 LLM 语义评分；明显低分结果会过滤，未进入评审的候选按规则排序保留。" if enable_llm == 1 else "已跳过 LLM 语义评分以提升页面速度。"
                msg = f"✅ 抓取完成（近30天热帖优先）。{llm_note}"
                report = "需要生成脚本报告时，把“生成脚本报告”改为 1；需要 LLM 评分时，把“启用 LLM 语义评分”改为 1。"

            _JOBS[job_id].update({
                "status": "done",
                "stage": "已完成",
                "msg": msg,
                "report": report,
                "result_html": result_html,
            })
            return

        if kind == "discover":
            _JOBS[job_id]["stage"] = "正在发现高潜赛道"
            discover_top_k = int(payload.get("discover_top_k", 5) or 5)
            discover_candidates = str(payload.get("discover_candidates", "") or "")
            top_k = int(payload.get("top_k", 3) or 3)

            candidates = [x.strip() for x in discover_candidates.split(",") if x.strip()] if discover_candidates else None
            board = discover_hot_tracks(candidates=candidates, tracks_top_k=discover_top_k, per_track_top_n=1)
            if not board:
                _JOBS[job_id].update({
                    "status": "done",
                    "msg": "⚠️ 未发现可用赛道",
                    "report": "",
                    "result_html": "<p>无抓取结果</p>",
                })
                return

            best_niche = board[0]["niche"]
            _JOBS[job_id]["stage"] = f"已选中 {best_niche}，正在抓取样本"
            raw = get_trending_videos(best_niche, translate_titles=False)
            _JOBS[job_id].update({
                "status": "partial",
                "stage": "已返回赛道样本，正在生成报告",
                "msg": f"已发现赛道：{best_niche}。报告生成中...",
                "report": "",
                "result_html": _render_rows(raw, niche=best_niche),
            })
            out = hunter_workflow(niche=best_niche, top_k=top_k, out_path="output/demo_report.md", raw_data=raw)

            result_html = _render_rows(raw, niche=best_niche)

            lines = [f"✅ 自动发现完成，已使用赛道：{best_niche}（近30天热帖）", "赛道榜单："]
            for i, b in enumerate(board, 1):
                lines.append(f"{i}. {b['niche']} | hot_score={b['hot_score']} | samples={b['sample_count']}")
            msg = "\n".join(lines)
            report = f"报告路径：{out}"

            _JOBS[job_id].update({
                "status": "done",
                "stage": "已完成",
                "msg": msg,
                "report": report,
                "result_html": result_html,
            })
            return

        raise ValueError(f"unknown job kind: {kind}")
    except Exception as e:
        _JOBS[job_id].update({
            "status": "error",
            "stage": "执行失败",
            "msg": f"❌ 执行失败: {e}",
            "report": traceback.format_exc(),
            "result_html": "<p>任务执行异常，请查看错误堆栈。</p>",
        })


@app.post("/run")
def run(
    niche: str = Form("tech_niche"),
    top_k: int = Form(3),
    nocache: int = Form(0),
    enable_llm: int = Form(0),
    generate_report: int = Form(0),
):
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {
        "status": "queued",
        "stage": "任务排队中",
        "msg": "任务排队中...",
        "report": "",
        "result_html": "",
    }
    payload = {
        "kind": "run",
        "niche": niche,
        "top_k": int(top_k or 3),
        "nocache": int(nocache or 0),
        "enable_llm": int(enable_llm or 0),
        "generate_report": int(generate_report or 0),
    }
    threading.Thread(target=_run_job, args=(job_id, payload), daemon=True).start()
    return RedirectResponse(url=f"/job/{job_id}", status_code=303)

@app.post("/discover-run", response_class=HTMLResponse)
def discover_run(
    discover_top_k: int = Form(5),
    discover_candidates: str = Form(""),
    top_k: int = Form(3),
):
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {
        "status": "queued",
        "stage": "任务排队中",
        "msg": "任务排队中...",
        "report": "",
        "result_html": "",
    }
    payload = {
        "kind": "discover",
        "discover_top_k": int(discover_top_k or 5),
        "discover_candidates": discover_candidates,
        "top_k": int(top_k or 3),
    }
    threading.Thread(target=_run_job, args=(job_id, payload), daemon=True).start()
    return RedirectResponse(url=f"/job/{job_id}", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return page(msg="❌ 任务不存在或已过期", report_path="", result_html="")

    return f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <title>任务执行中</title>
      <style>
        * {{ box-sizing: border-box; }}
        body {{
          font-family: Arial, Helvetica, sans-serif;
          max-width: 980px;
          margin: 28px auto;
          padding: 0 18px 40px;
          color: #18221f;
          background: #f7f8f7;
        }}
        .panel, .box {{
          background: #fff;
          border: 1px solid #dce3df;
          border-radius: 8px;
          padding: 16px;
          margin: 16px 0;
        }}
        .subtle {{ color: #5a6762; line-height: 1.5; }}
        .status-line {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
        .badge {{
          border: 1px solid #cbd6d1;
          border-radius: 999px;
          padding: 3px 9px;
          font-size: 12px;
          color: #4d5a55;
          background: #f8fbf9;
        }}
        .bar {{
          height: 6px;
          background: #dce3df;
          border-radius: 6px;
          overflow: hidden;
          margin-top: 14px;
        }}
        .bar span {{
          display: block;
          height: 100%;
          width: 35%;
          background: #246b52;
          animation: slide 1.1s infinite alternate;
        }}
        @keyframes slide {{
          from {{ transform: translateX(-20%); }}
          to {{ transform: translateX(210%); }}
        }}
        .result h3 {{ margin-top: 0; }}
        .results-list {{ display: grid; gap: 12px; }}
        .result-item {{
          background: #ffffff;
          border: 1px solid #dce3df;
          border-radius: 8px;
          padding: 14px;
        }}
        .item-topline {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }}
        .rank {{ font-weight: 700; color: #246b52; }}
        .pill {{
          border: 1px solid #cbd6d1;
          border-radius: 999px;
          padding: 2px 8px;
          font-size: 12px;
          color: #4d5a55;
          background: #f8fbf9;
        }}
        .result-item h3 {{
          font-size: 18px;
          line-height: 1.35;
          margin: 0 0 6px;
          overflow-wrap: anywhere;
        }}
        .title-zh {{ color: #246b52; font-size: 16px; line-height: 1.45; margin: 0 0 10px; }}
        .meta-row {{ display: flex; flex-wrap: wrap; gap: 10px; color: #5a6762; font-size: 14px; margin: 10px 0; }}
        .open-link {{ display: inline-block; color: #9b2f24; font-weight: 700; text-decoration: none; margin-top: 2px; }}
        .details {{ margin-top: 10px; border-top: 1px solid #edf1ef; padding-top: 9px; color: #4f5d58; font-size: 13px; }}
        .details summary {{ cursor: pointer; color: #246b52; font-weight: 700; }}
        .raw-link {{ overflow-wrap: anywhere; color: #6a7772; }}
      </style>
    </head>
    <body>
      <h2>GlobalTrend-Hunter</h2>
      <section class="panel">
        <div class="status-line">
          <b id="statusText">任务启动中</b>
          <span class="badge" id="statusBadge">queued</span>
          <span class="badge" id="elapsed">0 秒</span>
        </div>
        <p class="subtle" id="stageText">正在准备任务...</p>
        <div class="bar" id="progressBar"><span></span></div>
        <p class="subtle">现在会先显示规则排序结果，LLM 评审和标题整理完成后自动替换成最终结果。</p>
        <p><a href="/">返回首页</a> · <a href="/job/{job_id}/json" target="_blank">查看 JSON 状态</a></p>
      </section>
      <section class="box">
        <p id="messageBox">{escape(job.get("msg", ""))}</p>
        <p id="reportBox">{escape(job.get("report", ""))}</p>
      </section>
      <section class="box result">
        <h3 id="resultTitle">结果会自动出现</h3>
        <div id="resultBox">{job.get("result_html", "")}</div>
      </section>
      <script>
        const jobId = "{job_id}";
        const started = Date.now();
        let lastHtml = "";
        async function pollJob() {{
          const res = await fetch(`/job/${{jobId}}/json`, {{ cache: "no-store" }});
          const data = await res.json();
          if (!data.ok) {{
            document.getElementById("statusText").textContent = "任务不存在";
            return;
          }}
          document.getElementById("statusBadge").textContent = data.status || "";
          document.getElementById("stageText").textContent = data.stage || data.msg || "";
          document.getElementById("messageBox").textContent = data.msg || "";
          document.getElementById("reportBox").textContent = data.report || "";
          document.getElementById("elapsed").textContent = Math.floor((Date.now() - started) / 1000) + " 秒";
          if (data.result_html && data.result_html !== lastHtml) {{
            lastHtml = data.result_html;
            document.getElementById("resultBox").innerHTML = data.result_html;
            document.getElementById("resultTitle").textContent = data.status === "partial" ? "已先返回规则结果" : "最终结果";
          }}
          if (data.status === "done") {{
            document.getElementById("statusText").textContent = "任务完成";
            const bar = document.getElementById("progressBar");
            if (bar) bar.style.display = "none";
            return;
          }}
          if (data.status === "error") {{
            document.getElementById("statusText").textContent = "任务失败";
            return;
          }}
          document.getElementById("statusText").textContent = data.status === "partial" ? "已有结果，继续优化中" : "任务执行中";
          setTimeout(pollJob, 1000);
        }}
        pollJob();
      </script>
    </body>
    </html>
    """


@app.get("/job/{job_id}/json")
def job_json(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        return JSONResponse({"ok": False, "error": "job_not_found"}, status_code=404)
    return JSONResponse({"ok": True, "job_id": job_id, **job})
