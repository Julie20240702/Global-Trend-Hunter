from typing import List, Dict, Any
import random
import os
import requests
import time
import re


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9]+", (text or "").lower()) if t]


def _expand_query_terms(niche: str) -> List[str]:
    base = _tokenize(niche)
    s = " ".join(base)
    extra = []
    if any(k in s for k in ["ai", "artificial", "llm", "agent", "automation", "workflow", "productivity"]):
        extra += ["ai", "gpt", "chatgpt", "llm", "agent", "prompt", "automation", "workflow", "productivity", "copilot"]
    return list(dict.fromkeys(base + extra))


def _relevance_score(niche: str, title: str, body: str = "") -> float:
    terms = _expand_query_terms(niche)
    if not terms:
        return 0.0
    text = f"{title} {body}".lower()
    title_l = (title or "").lower()

    score = 0.0
    hit_cnt = 0
    for t in terms:
        if t in title_l:
            score += 2.0
            hit_cnt += 1
        elif t in text:
            score += 0.8
            hit_cnt += 1

    # AI工具/生产力方向的“意图词”加分（不再做硬性扣分）
    intent_terms = ["tool", "tools", "app", "apps", "saas", "workflow", "automation", "productivity", "no-code", "agent"]
    intent_hit = any(k in text for k in intent_terms)
    if intent_hit:
        score += 1.2

    # 语义密度不足时小幅降权，避免过严筛空
    if hit_cnt < 2:
        score -= 0.8

    negative = [
        "celebrity", "scandal", "gossip", "domestic violence", "sexual", "crime", "war", "politics", "election"
    ]
    for n in negative:
        if n in text:
            score -= 1.5

    return score

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _mock_videos() -> List[Dict[str, Any]]:
    seeds = [
        {"id": "yt_001", "title": "3 AI tools that save 10 hours/week", "platform": "YouTube"},
        {"id": "tt_002", "title": "I built a no-code app in 24h", "platform": "TikTok"},
        {"id": "ig_003", "title": "Tech setup under $100", "platform": "Instagram"},
    ]
    out = []
    for s in seeds:
        views = random.randint(50000, 2000000)
        likes = int(views * random.uniform(0.02, 0.12))
        comments = int(views * random.uniform(0.002, 0.02))
        growth_24h = random.uniform(0.5, 9.0)
        out.append({
            **s,
            "url": f"https://example.com/{s['id']}",
            "metrics": {"views": views, "likes": likes, "comments": comments, "growth_24h": growth_24h},
            "transcript": "Today I'll show you a workflow that changed my productivity...",
            "comments_sample": ["this is gold", "need part 2", "worked for me"]
        })
    return out


def _yt_to_item(video_id: str, title: str, views: int, likes: int, comments: int) -> Dict[str, Any]:
    # YouTube API不直接给24h增长，这里给一个启发式代理值，避免评分崩掉
    growth_24h = min(9.0, max(0.5, (likes / max(views, 1)) * 120))
    return {
        "id": f"yt_{video_id}",
        "title": title,
        "platform": "YouTube",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "metrics": {
            "views": views,
            "likes": likes,
            "comments": comments,
            "growth_24h": growth_24h
        },
        "transcript": "",
        "comments_sample": []
    }


def _fetch_youtube_trending(niche: str, max_results: int = 15) -> List[Dict[str, Any]]:
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return []

    q = niche.replace("_", " ")
    search_params = {
        "part": "snippet",
        "q": q,
        "type": "video",
        "order": "viewCount",
        "maxResults": max_results,
        "regionCode": "US",
        "relevanceLanguage": "en",
        "key": api_key,
    }
    r = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=20)
    if r.status_code != 200:
        return []
    data = r.json()
    items = data.get("items", [])
    video_ids = [it.get("id", {}).get("videoId") for it in items if it.get("id", {}).get("videoId")]
    if not video_ids:
        return []

    stats_params = {
        "part": "statistics,snippet",
        "id": ",".join(video_ids),
        "key": api_key
    }
    r2 = requests.get(YOUTUBE_VIDEOS_URL, params=stats_params, timeout=20)
    if r2.status_code != 200:
        return []
    d2 = r2.json()

    out = []
    for it in d2.get("items", []):
        vid = it.get("id", "")
        sn = it.get("snippet", {}) or {}
        st = it.get("statistics", {}) or {}
        views = int(st.get("viewCount", 0) or 0)
        likes = int(st.get("likeCount", 0) or 0)
        comments = int(st.get("commentCount", 0) or 0)
        title = sn.get("title", "")
        out.append(_yt_to_item(vid, title, views, likes, comments))
    return out


def _reddit_to_item(post: Dict[str, Any]) -> Dict[str, Any]:
    pid = post.get("id", "")
    title = post.get("title", "")
    score = int(post.get("score", 0) or 0)
    comments = int(post.get("num_comments", 0) or 0)
    upvote_ratio = float(post.get("upvote_ratio", 0.0) or 0.0)
    created_utc = int(post.get("created_utc", 0) or 0)
    views_proxy = max(1, score * 25)
    likes_proxy = max(0, int(score * upvote_ratio))
    growth_24h = min(9.0, max(0.5, (upvote_ratio * 10) - 1.0))
    permalink = post.get("permalink", "")
    return {
        "id": f"rd_{pid}",
        "title": title,
        "platform": "Reddit",
        "url": f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com/",
        "created_utc": created_utc,
        "metrics": {
            "views": views_proxy,
            "likes": likes_proxy,
            "comments": comments,
            "growth_24h": growth_24h,
            "upvotes": score,
            "upvote_ratio": upvote_ratio,
        },
        "transcript": (post.get("selftext", "") or "")[:500],
        "comments_sample": [],
    }


def _fetch_reddit_trending(niche: str, limit: int = 30, days: int = 30) -> List[Dict[str, Any]]:
    ua = os.getenv("REDDIT_USER_AGENT", "").strip() or "GlobalTrendHunter/0.1"
    q = niche.replace("_", " ")
    # 中文niche在Reddit召回较弱，追加英文语义词提升命中
    q = f"{q} AI tools productivity automation workflow SaaS"
    params = {"q": q, "sort": "top", "t": "month", "limit": max(limit, 50), "type": "link"}
    headers = {"User-Agent": ua}
    cutoff = int(time.time()) - days * 24 * 3600
    try:
        # Reddit在不同入口的可用性差异较大：优先old.reddit，再回退www.reddit
        data = {}
        endpoints = [
            "https://old.reddit.com/search.json",
            "https://www.reddit.com/search.json",
        ]
        req_params = dict(params)
        req_params["raw_json"] = 1

        last_status = None
        for ep in endpoints:
            r = requests.get(ep, params=req_params, headers=headers, timeout=20)
            last_status = r.status_code
            if r.status_code == 200:
                data = r.json() or {}
                break
        if not data:
            return []
        children = ((data.get("data") or {}).get("children") or [])
        strict_out = []
        relaxed_out = []
        for c in children:
            d = (c or {}).get("data") or {}
            if not d:
                continue
            created_utc = int(d.get("created_utc", 0) or 0)
            score = int(d.get("score", 0) or 0)
            comments = int(d.get("num_comments", 0) or 0)
            if created_utc < cutoff:
                continue
            if score < 10 or comments < 3:
                continue

            title = d.get("title", "") or ""
            body = d.get("selftext", "") or ""
            rel = _relevance_score(niche=niche, title=title, body=body)

            item = _reddit_to_item(d)
            item["relevance_score"] = rel
            if rel >= 2.0:
                strict_out.append(item)
            elif rel >= 0.5:
                relaxed_out.append(item)

        out = strict_out if strict_out else relaxed_out

        # 先按相关性，再按互动热度排序
        out.sort(key=lambda x: (
            float(x.get("relevance_score", 0.0)),
            int((x.get("metrics") or {}).get("upvotes", 0)),
            int((x.get("metrics") or {}).get("comments", 0))
        ), reverse=True)
        return out
    except Exception:
        return []


def get_trending_videos(niche: str) -> List[Dict[str, Any]]:
    yt = _fetch_youtube_trending(niche=niche, max_results=10)
    rd = _fetch_reddit_trending(niche=niche, limit=10)
    merged = yt + rd
    if merged:
        return merged
    return _mock_videos()