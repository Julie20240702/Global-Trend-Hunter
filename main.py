from dataclasses import dataclass
from typing import Dict, Any, List
import time
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from scraper import get_trending_videos
from agents import (
    call_agent_to_analyze,
    call_agent_to_localize,
    call_agent_to_generate_script,
    call_agent_to_safety_check,
)
from db import init_db, save_record


@dataclass
class TrendItem:
    id: str
    title: str
    platform: str
    url: str
    metrics: Dict[str, Any]
    transcript: str = ""
    comments_sample: List[str] = None


def normalize_video(v: Dict[str, Any]) -> TrendItem:
    return TrendItem(
        id=str(v.get("id")),
        title=v.get("title", ""),
        platform=v.get("platform", "unknown"),
        url=v.get("url", ""),
        metrics=v.get("metrics", {}),
        transcript=v.get("transcript", ""),
        comments_sample=v.get("comments_sample", [])[:50],
    )


def score_trend(item: TrendItem) -> float:
    m = item.metrics or {}
    views = m.get("views", 0)
    likes = m.get("likes", 0)
    comments = m.get("comments", 0)
    growth = m.get("growth_24h", 0.0)
    return 0.4 * growth + 0.3 * (likes / max(views, 1)) + 0.3 * (comments / max(views, 1))


def safe_call(fn, *args, retries=2, sleep_s=1, **kwargs):
    last_err = None
    for _ in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            time.sleep(sleep_s)
    raise last_err


def render_demo_report(records: List[Dict[str, Any]], niche: str) -> str:
    lines = []
    lines.append("# GlobalTrend-Hunter Demo Report")
    lines.append("")
    lines.append(f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 赛道: `{niche}`")
    lines.append(f"- 样本数: `{len(records)}`")
    lines.append("")
    lines.append("## Top Trends（按趋势分数）")
    lines.append("")

    for i, r in enumerate(records, 1):
        analysis = r.get("analysis", {}) or {}
        localized = r.get("localized", {}) or {}
        script = r.get("script", {}) or {}
        safety = r.get("safety", {}) or {}
        m = r.get("metrics", {}) or {}

        lines.append(f"### {i}. {r.get('title', '')}")
        lines.append(f"- 平台: {r.get('platform', '')}")
        lines.append(f"- 链接: {r.get('url', '')}")
        lines.append(
            f"- 指标: views={m.get('views',0)}, likes={m.get('likes',0)}, comments={m.get('comments',0)}, growth_24h={m.get('growth_24h',0)}"
        )
        lines.append(f"- 趋势分: `{r.get('trend_score', 0):.4f}`")
        lines.append("")
        lines.append("**爆款分析**")
        lines.append(f"- Hook风格: {analysis.get('hook_style', '')}")
        lines.append(f"- 节奏: {analysis.get('pacing', '')}")
        lines.append(f"- 人群: {analysis.get('audience', '')}")
        lines.append("")
        lines.append("**中文本地化**")
        lines.append(f"- 平台建议: {localized.get('cn_platform', '')}")
        lines.append(f"- 中文钩子: {localized.get('hook_cn', '')}")
        lines.append("")
        lines.append("**脚本草案（30秒）**")
        lines.append(f"- 标题: {script.get('title', '')}")
        lines.append(f"- 开场3秒: {script.get('opening_3s', '')}")
        lines.append(f"- 旁白: {script.get('narration', '')}")
        lines.append(f"- CTA: {script.get('cta', '')}")
        lines.append("")
        lines.append("**风控结果**")
        lines.append(
            f"- 通过: {safety.get('passed', False)} | 风险等级: {safety.get('risk_level', 'unknown')}"
        )
        if safety.get("reasons"):
            lines.append(f"- 原因: {safety.get('reasons')}")
        if safety.get("fixes"):
            lines.append(f"- 修复建议: {safety.get('fixes')}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## Limitations")
    lines.append("- 当前抓取为mock数据，需接入真实平台API/爬虫。")
    lines.append("- Agent结果在无API key时为预设mock JSON。")
    lines.append("- 评分函数为启发式，后续可学习化优化。")
    return "\n".join(lines)


DEFAULT_DISCOVERY_NICHES = [
    "ai_tools",
    "saas",
    "productivity",
    "personal_finance",
    "fitness",
    "gaming",
    "beauty",
    "education",
]


def discover_hot_tracks(candidates: List[str] = None, tracks_top_k: int = 5, per_track_top_n: int = 1) -> List[Dict[str, Any]]:
    candidates = candidates or DEFAULT_DISCOVERY_NICHES
    board = []

    for niche in candidates:
        raw_data = get_trending_videos(niche)
        items = [normalize_video(v) for v in raw_data]
        if not items:
            continue

        ranked = sorted(items, key=score_trend, reverse=True)
        avg_score = sum(score_trend(x) for x in ranked[:5]) / max(1, len(ranked[:5]))
        samples = []
        for it in ranked[:max(1, per_track_top_n)]:
            samples.append({
                "title": it.title,
                "platform": it.platform,
                "url": it.url,
                "trend_score": round(score_trend(it), 4),
            })

        board.append({
            "niche": niche,
            "hot_score": round(avg_score, 4),
            "sample_count": len(items),
            "top_samples": samples,
        })

    board = sorted(board, key=lambda x: x["hot_score"], reverse=True)
    return board[:tracks_top_k]


def print_track_board(board: List[Dict[str, Any]]):
    print("\n🔥 Recommended Hot Tracks")
    for i, b in enumerate(board, 1):
        print(f"{i}. {b['niche']} | hot_score={b['hot_score']:.4f} | samples={b['sample_count']}")
        for s in b.get("top_samples", []):
            print(f"   - [{s['platform']}] {s['title']} (score={s['trend_score']:.4f})")
            print(f"     {s['url']}")


def hunter_workflow(niche="tech_niche", top_k=20, out_path="output/demo_report.md"):
    init_db()
    raw_data = get_trending_videos(niche)
    items = [normalize_video(v) for v in raw_data]
    ranked = sorted(items, key=score_trend, reverse=True)[:top_k]

    records = []
    for item in ranked:
        analysis = safe_call(call_agent_to_analyze, item.__dict__)
        localized = safe_call(call_agent_to_localize, analysis)
        script = safe_call(call_agent_to_generate_script, localized)
        safety = safe_call(call_agent_to_safety_check, script)

        record = {
            "video_id": item.id,
            "title": item.title,
            "platform": item.platform,
            "url": item.url,
            "metrics": item.metrics,
            "trend_score": score_trend(item),
            "analysis": analysis,
            "localized": localized,
            "script": script,
            "safety": safety,
            "status": "ready" if safety.get("passed") else "needs_revision",
        }
        save_record(record)
        records.append(record)
        print(f"[{record['status']}] {item.title} | score={record['trend_score']:.4f}")

    report = render_demo_report(records, niche=niche)
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(report, encoding="utf-8")
    print(f"\n✅ Demo report generated: {out_file.resolve()}")
    return out_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GlobalTrend-Hunter demo workflow")
    parser.add_argument("--niche", type=str, default="tech_niche", help="trend niche")
    parser.add_argument("--top-k", type=int, default=3, help="top K trends to process")
    parser.add_argument("--out", type=str, default="output/demo_report.md", help="report output path")
    parser.add_argument("--discover-tracks", action="store_true", help="discover hot niches instead of generating report")
    parser.add_argument("--discover-top-k", type=int, default=5, help="top K niches to return in discovery mode")
    parser.add_argument("--discover-candidates", type=str, default="", help="comma-separated niche candidates")
    args = parser.parse_args()

    if args.discover_tracks:
        candidates = [x.strip() for x in args.discover_candidates.split(",") if x.strip()] if args.discover_candidates else None
        board = discover_hot_tracks(candidates=candidates, tracks_top_k=args.discover_top_k, per_track_top_n=1)
        print_track_board(board)
    else:
        hunter_workflow(niche=args.niche, top_k=args.top_k, out_path=args.out)
