from dataclasses import dataclass
from typing import Dict, Any, List
import time

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

def hunter_workflow(niche="tech_niche", top_k=20):
    init_db()
    raw_data = get_trending_videos(niche)
    items = [normalize_video(v) for v in raw_data]
    ranked = sorted(items, key=score_trend, reverse=True)[:top_k]

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
            "trend_score": score_trend(item),
            "analysis": analysis,
            "localized": localized,
            "script": script,
            "safety": safety,
            "status": "ready" if safety.get("passed") else "needs_revision",
        }
        save_record(record)
        print(f"[{record['status']}] {item.title} | score={record['trend_score']:.4f}")

if __name__ == "__main__":
    hunter_workflow()
