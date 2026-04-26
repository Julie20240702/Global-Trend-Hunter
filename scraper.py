from typing import List, Dict, Any, Tuple
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import os
import requests
from dotenv import load_dotenv

load_dotenv()
import time
import re
import math
import json

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

REQUEST_TIMEOUT = float(os.getenv("SCRAPER_TIMEOUT_SECONDS", "3"))
CACHE_TTL_SECONDS = int(os.getenv("SCRAPER_CACHE_TTL_SECONDS", "900"))
_TREND_CACHE: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

LLM_RERANK_ENABLED = os.getenv("ENABLE_LLM_RERANK", "1").strip().lower() in {"1", "true", "yes", "on"}
LLM_MODEL = os.getenv("LLM_RERANK_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "15"))
LLM_RERANK_MAX_ITEMS = int(os.getenv("LLM_RERANK_MAX_ITEMS", "6"))
LLM_RERANK_CHUNK_SIZE = int(os.getenv("LLM_RERANK_CHUNK_SIZE", "6"))
LLM_RERANK_WORKERS = int(os.getenv("LLM_RERANK_WORKERS", "1"))
LLM_MIN_SCORE = float(os.getenv("LLM_MIN_SCORE", "5.5"))
LLM_TRANSLATE_ALL_TITLES = os.getenv("LLM_TRANSLATE_ALL_TITLES", "0").strip().lower() in {"1", "true", "yes", "on"}
REDDIT_MAX_SUBREDDITS = int(os.getenv("REDDIT_MAX_SUBREDDITS", "10"))
REDDIT_MAX_QUERY_VARIANTS = int(os.getenv("REDDIT_MAX_QUERY_VARIANTS", "2"))
REDDIT_PER_QUERY_LIMIT = int(os.getenv("REDDIT_PER_QUERY_LIMIT", "20"))
REDDIT_MAX_WORKERS = int(os.getenv("REDDIT_MAX_WORKERS", "8"))
REDDIT_OLD_FALLBACK = os.getenv("REDDIT_OLD_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "on"}

TREND_SIGNAL_TERMS = {
    "trend", "trending", "viral", "hot", "news", "breaking", "launch", "launched", "release", "released",
    "update", "new", "growth", "surge", "exploding", "popular", "case", "study", "benchmark", "report",
    "data", "ranking", "market", "strategy", "playbook", "tested", "experiment", "lessons"
}

COPY_SIGNAL_TERMS = {
    "tool", "tools", "template", "workflow", "framework", "checklist", "example", "examples", "breakdown",
    "how", "guide", "step", "steps", "built", "build", "testing", "tested", "replicate", "system", "prompt",
    "script", "automation", "setup", "before", "after", "results", "learned"
}

LOW_VALUE_PATTERNS = [
    r"\bhelp\b", r"\badvice\b", r"\bquestion\b", r"\bcan someone\b", r"\bdoes anyone\b", r"\bwhat should i\b",
    r"\bhow do i\b", r"\blooking for\b", r"\bhiring\b", r"\bjob\b", r"\bresume\b", r"\bcv\b", r"\bsalary\b",
    r"\bbeginner\b", r"\bnoob\b", r"\bdaily thread\b", r"\bweekly thread\b", r"\bmegathread\b",
    r"\bself[- ]promo\b", r"\bpromo\b", r"\bdiscount\b", r"\bcoupon\b", r"\bgiveaway\b"
]

SUBREDDIT_HINTS = {
    "ai": ["ChatGPT", "OpenAI", "ArtificialIntelligence", "MachineLearning", "SaaS", "productivity"],
    "tools": ["ChatGPT", "OpenAI", "SaaS", "productivity", "Entrepreneur", "SideProject", "specializedtools"],
    "saas": ["SaaS", "startups", "Entrepreneur", "SideProject"],
    "productivity": ["productivity", "Notion", "ObsidianMD", "ChatGPT"],
    "personal": ["personalfinance", "financialindependence", "investing"],
    "finance": ["personalfinance", "financialindependence", "investing"],
    "crypto": ["CryptoCurrency", "Bitcoin", "ethtrader", "defi", "CryptoMarkets"],
    "fitness": ["Fitness", "bodyweightfitness", "loseit", "xxfitness"],
    "cooking": ["Cooking", "recipes", "MealPrepSunday", "AskCulinary", "food"],
    "recipe": ["recipes", "Cooking", "MealPrepSunday", "AskCulinary"],
    "travel": ["travel", "solotravel", "onebag", "Shoestring", "TravelHacks"],
    "trip": ["travel", "solotravel", "onebag", "Shoestring"],
    "gaming": ["gaming", "Games", "pcgaming", "NintendoSwitch"],
    "beauty": ["SkincareAddiction", "MakeupAddiction", "beauty"],
    "education": ["education", "Teachers", "edtech"],
}

# 通用热榜分区（跨赛道）
REDDIT_GENERAL_SUBREDDITS = [
    "popular",
    "all",
    "technology",
    "news",
    "tifu",
    "unpopularopinion",
    "ExplainLikeImFive",
    "Showerthoughts",
]

# 赛道关键词 -> 垂类分区（与SUBREDDIT_HINTS互补）
REDDIT_TRACK_SUBREDDITS = {
    "ai": ["ChatGPT", "OpenAI", "MachineLearning", "ArtificialIntelligence", "LocalLLaMA", "singularity", "ChatGPTCoding", "Automate"],
    "llm": ["LocalLLaMA", "MachineLearning", "OpenAI", "ChatGPT", "ArtificialIntelligence", "ChatGPTCoding"],
    "gpt": ["ChatGPT", "OpenAI", "ChatGPTCoding", "PromptEngineering"],
    "tools": ["ChatGPT", "OpenAI", "SaaS", "productivity", "Entrepreneur", "SideProject", "specializedtools", "Automate"],
    "automation": ["Automate", "productivity", "ChatGPTCoding", "SaaS", "Entrepreneur"],
    "saas": ["SaaS", "startups", "Entrepreneur", "SideProject"],
    "productivity": ["productivity", "Notion", "ObsidianMD", "GetDisciplined", "DecidingToBeBetter"],
    "personal": ["personalfinance", "financialindependence", "investing", "DecidingToBeBetter"],
    "finance": ["personalfinance", "financialindependence", "investing", "stocks", "Entrepreneur"],
    "career": ["careerguidance", "jobs", "Entrepreneur", "smallbusiness"],
    "money": ["personalfinance", "financialindependence", "investing", "sidehustle"],
    "crypto": ["CryptoCurrency", "Bitcoin", "ethtrader", "defi", "CryptoMarkets"],
    "fitness": ["Fitness", "bodyweightfitness", "loseit", "xxfitness"],
    "cooking": ["Cooking", "recipes", "MealPrepSunday", "AskCulinary", "food"],
    "recipe": ["recipes", "Cooking", "MealPrepSunday", "AskCulinary"],
    "travel": ["travel", "solotravel", "onebag", "Shoestring", "TravelHacks"],
    "trip": ["travel", "solotravel", "onebag", "Shoestring", "TravelHacks"],
    "lifestyle": ["selfimprovement", "GetMotivated", "DecidingToBeBetter", "unpopularopinion", "tifu"],
    "psychology": ["psychology", "selfimprovement", "Showerthoughts", "TrueOffMyChest"],
    "story": ["tifu", "TrueOffMyChest", "confession", "relationships"],
    "gaming": ["gaming", "Games", "pcgaming", "NintendoSwitch"],
    "beauty": ["SkincareAddiction", "MakeupAddiction", "beauty"],
    "education": ["education", "Teachers", "edtech", "ExplainLikeImFive"],
}


PHRASE_HINTS = {
    "travel hacks": ["travelhacks", "solotravel", "onebag", "Shoestring", "travel"],
    "ai tools": ["ChatGPT", "OpenAI", "MachineLearning", "ArtificialIntelligence", "specializedtools", "ChatGPTCoding", "Automate"],
    "chatgpt coding": ["ChatGPTCoding", "ChatGPT", "OpenAI", "LocalLLaMA"],
    "automation workflow": ["Automate", "productivity", "SaaS", "ChatGPT"],
    "side hustle": ["sidehustle", "Entrepreneur", "smallbusiness", "personalfinance"],
    "career growth": ["careerguidance", "jobs", "Entrepreneur", "DecidingToBeBetter"],
    "unpopular opinion": ["unpopularopinion", "TrueOffMyChest", "Showerthoughts"],
    "deep thoughts": ["Showerthoughts", "ExplainLikeImFive", "psychology"],
    "meal prep": ["MealPrepSunday", "EatCheapAndHealthy", "cooking"],
}


def _tokenize(text: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9]+", (text or "").lower()) if t]


def _expand_query_terms(niche: str) -> List[str]:
    # 通用扩词：仅基于用户输入，不再注入AI偏置词
    base_raw = _tokenize(niche)

    # 过滤泛词，避免“只命中一个宽泛词就高分”导致跑偏
    stop = {
        "new", "best", "top", "tips", "guide", "how", "what", "why", "when",
        "today", "week", "month", "video", "videos", "trend", "trending", "viral", "hot"
    }
    base = [t for t in base_raw if len(t) >= 3 and t not in stop]

    extra: List[str] = []
    for t in base:
        if len(t) >= 4:
            # 保留轻量形态归一，提升召回（不引入行业偏置）
            if t.endswith("s") and len(t) > 4:
                extra.append(t[:-1])
            elif not t.endswith("s"):
                extra.append(f"{t}s")
    return list(dict.fromkeys(base + extra))


def _relevance_score(niche: str, title: str, body: str = "") -> float:
    terms = _expand_query_terms(niche)
    if not terms:
        return 0.0

    text = f"{title} {body}".lower()
    title_l = (title or "").lower()

    # 短词会导致大量误匹配（如 beauty 命中 beauty and the beast 之类噪声）
    # 使用词边界，避免子串误命中。
    score = 0.0
    hit_cnt = 0
    for t in terms:
        # 兼容 hashtag（如 #ai / #travel）与普通词边界
        pat_word = re.compile(rf"\b{re.escape(t)}\b")
        pat_hash = re.compile(rf"(?<![a-z0-9])#{re.escape(t)}(?![a-z0-9])")
        title_hit = bool(pat_word.search(title_l) or pat_hash.search(title_l))
        text_hit = bool(pat_word.search(text) or pat_hash.search(text))
        if title_hit:
            score += 2.4
            hit_cnt += 1
        elif text_hit:
            score += 1.0
            hit_cnt += 1

    # 命中覆盖率奖励
    coverage = hit_cnt / max(len(set(terms)), 1)
    score += min(1.2, coverage * 2.4)

    # 强约束：一个词都不命中直接强惩罚
    if hit_cnt < 1:
        score -= 2.5

    negative = [
        "celebrity", "scandal", "gossip", "domestic violence", "sexual", "crime", "war", "politics", "election",
        "movie", "trailer", "song", "lyrics"
    ]
    for n in negative:
        if n in text:
            score -= 1.2

    return score


def _term_hits(text: str, terms: set) -> int:
    toks = set(_tokenize(text))
    return sum(1 for t in terms if t in toks)


def _niche_lexical_hit(niche: str, title: str, body: str = "") -> bool:
    n = (niche or "").strip().lower()
    text = f"{title} {body}".lower()

    # phrase级强门禁：避免 "AI tools" 被泛 "power tools" 串台
    strong_phrase_groups = [
        ["ai tools", "ai tool", "llm tools", "llm tool"],
        ["ai workflow", "llm workflow", "agent workflow"],
    ]
    has_ai_token = bool(re.search(r"\b(ai|llm|chatgpt|openai)\b", text))
    has_tool_token = bool(re.search(r"\b(tool|tools|workflow|automation|agent)\b", text))
    for grp in strong_phrase_groups:
        if any(p in n for p in grp):
            phrase_hit = any(p in text for p in grp)
            if not (phrase_hit or (has_ai_token and has_tool_token)):
                return False

    # 赛道专用词典：用于Reddit噪声门禁（尽量小而稳）
    domain_lex = {
        "crypto": ["crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "defi", "token", "airdrop", "altcoin", "web3", "onchain"],
        "fitness": ["fitness", "workout", "gym", "muscle", "cardio", "strength", "training", "fat loss", "protein"],
        "cooking": ["cook", "cooking", "recipe", "kitchen", "bake", "baking", "chef", "meal", "dish", "food"],
        "travel": ["travel", "trip", "flight", "hotel", "itinerary", "visa", "airport", "tour", "destination", "backpack", "hostel"],
        "ai": ["ai", "llm", "chatgpt", "openai", "prompt", "model", "agent", "automation", "inference"],
        "tools": ["tool", "tools", "workflow", "automation", "platform", "software", "app", "plugin"],
    }

    tokens = _tokenize(n)
    merged_terms: List[str] = []
    for t in tokens:
        merged_terms.extend(domain_lex.get(t, []))

    # 若无赛道词典命中，退化为query扩词
    if not merged_terms:
        merged_terms = _expand_query_terms(n)

    merged_terms = list(dict.fromkeys([x for x in merged_terms if x]))
    if not merged_terms:
        return False

    # 通用门禁：
    # - 单token/短query：至少1个词命中（避免过严）
    # - 多token query：至少2个词命中（降低跨赛道误召回）
    hit_cnt = sum(1 for t in merged_terms if re.search(rf"\b{re.escape(t)}\b", text))
    min_hits = 1 if len(tokens) <= 1 else 2

    # travel专门门禁：必须命中至少1个旅行词，且不能被其他赛道词主导
    if "travel" in tokens:
        travel_terms = domain_lex["travel"]
        travel_hits = sum(1 for t in travel_terms if re.search(rf"\b{re.escape(t)}\b", text))
        if travel_hits < 1:
            return False
        cross_noise = ["crypto", "bitcoin", "ethereum", "ai", "llm", "chatgpt", "openai", "lyrics", "official music video"]
        cross_hits = sum(1 for t in cross_noise if re.search(rf"\b{re.escape(t)}\b", text))
        if travel_hits == 1 and cross_hits >= 2:
            return False

    # 轻量负语境抑制：对普遍新闻/娱乐噪声降误判（非赛道特判）
    neg_noise = [
        "celebrity", "scandal", "gossip", "war", "election", "trailer", "lyrics", "box office"
    ]
    has_neg_noise = any(k in text for k in neg_noise)

    return (hit_cnt >= min_hits) and (not has_neg_noise or hit_cnt >= (min_hits + 1))


def _trend_signal_score(title: str, body: str = "") -> float:
    title_hits = _term_hits(title, TREND_SIGNAL_TERMS)
    body_hits = _term_hits(body, TREND_SIGNAL_TERMS)
    return min(5.0, title_hits * 1.6 + body_hits * 0.5)


def _copy_signal_score(title: str, body: str = "") -> float:
    title_hits = _term_hits(title, COPY_SIGNAL_TERMS)
    body_hits = _term_hits(body, COPY_SIGNAL_TERMS)
    return min(4.0, title_hits * 1.1 + body_hits * 0.35)


def _low_value_penalty(title: str, body: str = "") -> float:
    text = f"{title} {body}".lower()
    penalty = 0.0
    for pat in LOW_VALUE_PATTERNS:
        if re.search(pat, text):
            penalty += 1.5
    return min(6.0, penalty)


def _recency_score(item: Dict[str, Any]) -> float:
    created_utc = int(item.get("created_utc", 0) or 0)
    if not created_utc:
        return 1.0
    age_days = max(0.0, (time.time() - created_utc) / 86400)
    return max(0.0, 3.0 * (1.0 - min(age_days, 30.0) / 30.0))


def _engagement_score(item: Dict[str, Any]) -> float:
    m = item.get("metrics", {}) or {}
    views = float(m.get("views", 0) or 0)
    likes = float(m.get("likes", 0) or 0)
    comments = float(m.get("comments", 0) or 0)
    growth = float(m.get("growth_24h", 0) or 0)
    return math.log1p(max(views, 0)) + 1.2 * math.log1p(max(likes, 0)) + 1.4 * math.log1p(max(comments, 0)) + 0.8 * max(growth, 0)


def _trend_quality_score(niche: str, item: Dict[str, Any]) -> float:
    title = item.get("title", "")
    body = item.get("transcript", "")
    rel = float(item.get("relevance_score", _relevance_score(niche, title, body)))
    hot = _engagement_score(item)
    trend = _trend_signal_score(title, body)
    copy = _copy_signal_score(title, body)
    recency = _recency_score(item)
    penalty = _low_value_penalty(title, body)
    return 0.35 * rel + 0.22 * hot + 0.18 * trend + 0.15 * copy + 0.10 * recency - penalty


def _extract_terms_from_items(niche: str, items: List[Dict[str, Any]], top_k: int = 8) -> List[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "you", "your", "are", "how", "what", "why", "when", "where",
        "into", "onto", "about", "best", "tips", "guide", "video", "reddit", "youtube", "today", "week", "month"
    }
    niche_terms = set(_tokenize(niche))
    freq = Counter()
    weighted = Counter()

    for it in items:
        title = (it.get("title") or "")
        body = (it.get("transcript") or "")
        toks_title = [t for t in _tokenize(title) if len(t) >= 3 and t not in stop]
        toks_body = [t for t in _tokenize(body) if len(t) >= 3 and t not in stop]
        rel = max(0.0, _relevance_score(niche, title, body))
        hot = _engagement_score(it)
        w = 1.0 + 0.25 * rel + 0.15 * hot

        for t in toks_title:
            freq[t] += 2
            weighted[t] += 2 * w
        for t in toks_body:
            freq[t] += 1
            weighted[t] += 1 * w

    scored: List[Tuple[str, float]] = []
    for t, f in freq.items():
        if t in niche_terms:
            continue
        # 频率 * 热度相关加权，避免只看出现次数
        s = (1.0 + math.log1p(f)) * float(weighted.get(t, 0.0))
        scored.append((t, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scored[:top_k]]


def _rank_items(niche: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for it in items:
        title = it.get("title", "")
        body = it.get("transcript", "")
        rel = float(it.get("relevance_score", _relevance_score(niche, title, body)))
        it2 = dict(it)

        # 统一来源字段，兼容下游读取 source
        platform = (it2.get("platform") or "").strip()
        if not it2.get("source") and platform:
            it2["source"] = platform

        it2["relevance_score"] = rel
        it2["engagement_score"] = _engagement_score(it)
        it2["trend_signal_score"] = _trend_signal_score(title, body)
        it2["copy_signal_score"] = _copy_signal_score(title, body)
        it2["recency_score"] = _recency_score(it)
        it2["low_value_penalty"] = _low_value_penalty(title, body)
        it2["final_score"] = _trend_quality_score(niche, it2)
        out.append(it2)
    out.sort(key=lambda x: float(x.get("final_score", 0.0)), reverse=True)
    return out

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _mock_videos(niche: str = "AI tools") -> List[Dict[str, Any]]:
    niche_label = niche.replace("_", " ").strip() or "AI tools"
    seeds = [
        {"id": "yt_001", "title": f"3 {niche_label} ideas that are taking off this month", "platform": "YouTube"},
        {"id": "tt_002", "title": f"I tested a viral {niche_label} workflow in 24h", "platform": "TikTok"},
        {"id": "ig_003", "title": f"{niche_label.title()} setup people are saving right now", "platform": "Instagram"},
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
            "transcript": f"Today I'll show you a {niche_label} workflow that is getting attention...",
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


def _query_variants(niche: str) -> List[str]:
    q = niche.replace("_", " ").strip()
    if not q:
        return []
    variants = [
        q,
        f"{q} trend",
        f"{q} viral",
        f"{q} launch update",
    ]

    n = q.lower()
    if "ai" in n or "artificial intelligence" in n or "machine learning" in n:
        variants.extend([
            "chatgpt",
            "openai",
            "llm tools",
            "ai workflow",
        ])

    return list(dict.fromkeys(variants))[:8]


def _candidate_subreddits(niche: str, max_count: int = None) -> List[str]:
    max_count = max_count or REDDIT_MAX_SUBREDDITS
    n = (niche or "").strip().lower()
    toks = _tokenize(n)

    picks: List[str] = []

    # phrase/token 垂类优先，避免 max_count 截断后只剩 popular/all 这类泛热榜。
    for phrase, subs in PHRASE_HINTS.items():
        if phrase in n:
            picks.extend(subs)

    for t in toks:
        picks.extend(REDDIT_TRACK_SUBREDDITS.get(t, []))
        picks.extend(SUBREDDIT_HINTS.get(t, []))

    # 再补通用池，提供跨圈层热点，但不能抢在垂类前面。
    safe_general = [
        s for s in REDDIT_GENERAL_SUBREDDITS
        if (s or "").lower() not in {"tifu", "unpopularopinion"}
    ]
    picks.extend(safe_general)

    # 短 query 才补意图池，减少长尾赛道串台。
    if len(toks) <= 1:
        picks.extend(["ExplainLikeImFive", "selfimprovement", "GetMotivated", "DecidingToBeBetter"])

    # 去重并保序
    out: List[str] = []
    seen = set()
    for x in picks:
        k = (x or "").lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x)

    return out[:max_count]


def _fetch_youtube_trending(niche: str, max_results: int = 15) -> List[Dict[str, Any]]:
    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        return []

    # 多query召回：避免单一query导致AI=0
    variants = _query_variants(niche)
    if not variants:
        variants = [niche.replace("_", " ").strip()]

    all_video_ids: List[str] = []
    seen_vid = set()
    per_q = max(5, min(10, max_results))

    for q in variants[:4]:
        search_params = {
            "part": "snippet",
            "q": q,
            "type": "video",
            "order": "viewCount",
            "maxResults": per_q,
            "regionCode": "US",
            "relevanceLanguage": "en",
            "key": api_key,
        }
        try:
            r = requests.get(YOUTUBE_SEARCH_URL, params=search_params, timeout=REQUEST_TIMEOUT)
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception:
            continue
        items = data.get("items", [])
        for it in items:
            vid = (it.get("id", {}) or {}).get("videoId")
            if not vid or vid in seen_vid:
                continue
            seen_vid.add(vid)
            all_video_ids.append(vid)

    if not all_video_ids:
        return []

    # 分批取statistics
    out: List[Dict[str, Any]] = []
    for i in range(0, len(all_video_ids), 50):
        chunk = all_video_ids[i:i+50]
        stats_params = {
            "part": "statistics,snippet",
            "id": ",".join(chunk),
            "key": api_key
        }
        try:
            r2 = requests.get(YOUTUBE_VIDEOS_URL, params=stats_params, timeout=REQUEST_TIMEOUT)
            if r2.status_code != 200:
                continue
            d2 = r2.json()
        except Exception:
            continue

        for it in d2.get("items", []):
            vid = it.get("id", "")
            sn = it.get("snippet", {}) or {}
            st = it.get("statistics", {}) or {}
            views = int(st.get("viewCount", 0) or 0)
            likes = int(st.get("likeCount", 0) or 0)
            comments = int(st.get("commentCount", 0) or 0)
            title = sn.get("title", "")
            out.append(_yt_to_item(vid, title, views, likes, comments))

    return _dedup_items(out)[: max(max_results * 2, 20)]


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


def _request_reddit_json(url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    req_params = dict(params)
    req_params["raw_json"] = 1
    endpoints = [url]
    if REDDIT_OLD_FALLBACK:
        endpoints.append(url.replace("www.reddit.com", "old.reddit.com"))
    for ep in endpoints:
        r = requests.get(ep, params=req_params, headers=headers, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json() or {}
    return {}


def _collect_reddit_children(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [((c or {}).get("data") or {}) for c in (((data.get("data") or {}).get("children") or []))]


def _fetch_reddit_search(query: str, niche: str, limit: int, days: int) -> List[Dict[str, Any]]:
    ua = os.getenv("REDDIT_USER_AGENT", "").strip() or "GlobalTrendHunter/0.1"
    params = {"q": query, "sort": "top", "t": "month", "limit": max(limit, 25), "type": "link"}
    headers = {"User-Agent": ua}
    cutoff = int(time.time()) - days * 24 * 3600
    try:
        data = _request_reddit_json("https://www.reddit.com/search.json", params, headers)
        if not data:
            return []
        return _filter_reddit_posts(_collect_reddit_children(data), niche=niche, cutoff=cutoff)
    except Exception:
        return []


def _fetch_reddit_subreddit_top(subreddit: str, niche: str, limit: int, days: int) -> List[Dict[str, Any]]:
    ua = os.getenv("REDDIT_USER_AGENT", "").strip() or "GlobalTrendHunter/0.1"
    params = {"t": "month", "limit": max(limit, 25)}
    headers = {"User-Agent": ua}
    cutoff = int(time.time()) - days * 24 * 3600
    try:
        data = _request_reddit_json(f"https://www.reddit.com/r/{subreddit}/top.json", params, headers)
        if not data:
            return []
        return _filter_reddit_posts(_collect_reddit_children(data), niche=niche, cutoff=cutoff, subreddit=subreddit)
    except Exception:
        return []



def _is_low_info_title(title: str) -> bool:
    t = (title or "").strip().lower()
    if not t:
        return True
    # 过短 + 常见空泛句式
    generic = {
        "do you agree?",
        "thoughts?",
        "any thoughts?",
        "is this real?",
        "what do you think?",
    }
    if t in generic:
        return True
    toks = re.findall(r"[a-z0-9]+", t)
    if len(toks) <= 2:
        return True
    # 问句且缺少赛道实体词时通常信息量偏低
    weak_q = t.endswith("?") and len(toks) <= 5
    return weak_q

def _filter_reddit_posts(
    posts: List[Dict[str, Any]], niche: str, cutoff: int, subreddit: str = ""
) -> List[Dict[str, Any]]:
    strict_out = []
    relaxed_out = []
    for d in posts:
        if not d:
            continue

        reject_reasons: List[str] = []
        created_utc = int(d.get("created_utc", 0) or 0)
        score = int(d.get("score", 0) or 0)
        comments = int(d.get("num_comments", 0) or 0)

        if created_utc < cutoff:
            reject_reasons.append("too_old")
        if score < 15:
            reject_reasons.append("low_upvotes")
        if comments < 5:
            reject_reasons.append("low_comments")
        if reject_reasons:
            continue

        title = d.get("title", "") or ""
        body = d.get("selftext", "") or ""
        rel = _relevance_score(niche=niche, title=title, body=body)

        item = _reddit_to_item(d)
        if subreddit:
            item["source_subreddit"] = subreddit
            # 垂类分区允许轻微放宽；popular/all 不做相关性抬升，避免泛热榜污染
            if subreddit.lower() not in {"popular", "all"}:
                rel = max(rel, 1.0)
        item["relevance_score"] = rel

        quality = _trend_quality_score(niche, item)
        item["final_score"] = quality

        if rel >= 2.0 and quality >= 1.6:
            # strict通道同样加词门禁，避免“仅含 travel 一词”的新闻帖穿透
            if not _niche_lexical_hit(niche=niche, title=title, body=body):
                continue
            # 标题信息量门禁：拦截 Do you agree?/Thoughts? 一类泛帖
            if _is_low_info_title(title):
                continue
            item["selection_reason"] = "reddit_strict_pass"
            rs = list(item.get("reasons", []))
            rs.extend(["reddit:strict_pass", f"rel:{rel:.2f}", f"quality:{quality:.2f}"])
            item["reasons"] = rs
            strict_out.append(item)
        elif rel >= 0.7 and quality >= 0.4:
            # 放宽通道仍收紧：降低“标题空泛但蹭词”帖子通过率
            if rel < 1.4 and not _niche_lexical_hit(niche=niche, title=title, body=body):
                continue
            if _is_low_info_title(title):
                continue
            item["selection_reason"] = "reddit_relaxed_pass"
            rs = list(item.get("reasons", []))
            rs.extend(["reddit:relaxed_pass", f"rel:{rel:.2f}", f"quality:{quality:.2f}"])
            item["reasons"] = rs
            relaxed_out.append(item)

    out = strict_out if strict_out else relaxed_out

    out.sort(key=lambda x: (
        float(x.get("final_score", 0.0)),
        int((x.get("metrics") or {}).get("upvotes", 0)),
        int((x.get("metrics") or {}).get("comments", 0))
    ), reverse=True)
    return out


def _fetch_reddit_trending(niche: str, limit: int = 30, days: int = 30) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    per_query_limit = max(10, min(REDDIT_PER_QUERY_LIMIT, 40))
    tasks = []

    for subreddit in _candidate_subreddits(niche):
        tasks.append(("subreddit_top", subreddit, _fetch_reddit_subreddit_top, (subreddit, niche, per_query_limit, days)))

    for q in _query_variants(niche)[:REDDIT_MAX_QUERY_VARIANTS]:
        tasks.append(("reddit_search", q, _fetch_reddit_search, (q, niche, per_query_limit, days)))

    if not tasks:
        return []

    with ThreadPoolExecutor(max_workers=max(1, min(REDDIT_MAX_WORKERS, len(tasks)))) as executor:
        future_map = {
            executor.submit(fn, *args): (source_type, source_name)
            for source_type, source_name, fn, args in tasks
        }
        for future in as_completed(future_map):
            source_type, source_name = future_map[future]
            try:
                items = future.result()
            except Exception:
                continue
            for it in items:
                reasons = list(it.get("reasons", []))
                reasons.append(f"{source_type}:{source_name}")
                it["reasons"] = reasons
                out.append(it)

    ranked = _rank_items(niche, _dedup_items(out))
    return ranked[: max(limit, 40)]


def _dedup_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        platform = (it.get("platform") or "").lower()
        url = (it.get("url") or "").strip().lower()
        title = (it.get("title") or "").strip().lower()
        key = url or f"{platform}:{title}"
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _simple_zh_title(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return ""
    mapping = {
        "travel": "旅行",
        "trip": "行程",
        "flight": "航班",
        "hotel": "酒店",
        "itinerary": "行程规划",
        "visa": "签证",
        "airport": "机场",
        "tour": "旅行",
        "destination": "目的地",
        "guide": "指南",
        "tips": "技巧",
        "best": "最佳",
        "cheap": "便宜",
        "how to": "如何",
        "things to do": "必做清单",
        "where to stay": "住宿建议",
        "budget": "预算",
        "solo": "独自",
        "backpack": "背包",
    }
    out = t
    for en, zh in mapping.items():
        out = re.sub(rf"\b{re.escape(en)}\b", zh, out, flags=re.IGNORECASE)

    # 若几乎没有被翻译（仍基本为英文），给出清晰前缀，避免误判为“已翻译”
    cjk_cnt = sum(1 for ch in out if "\u4e00" <= ch <= "\u9fff")
    alpha_cnt = sum(1 for ch in out if ("a" <= ch.lower() <= "z"))
    if cjk_cnt < 2 and alpha_cnt >= 4:
        return f"中文参考：{t}"
    return out


def _humanize_reason(reason: str) -> str:
    s = str(reason or "").strip()
    if not s:
        return ""

    if s.startswith("merge:strict:youtube"):
        return "与赛道高度相关（YouTube）"
    if s.startswith("merge:strict:reddit"):
        return "与赛道高度相关（Reddit）"
    if s.startswith("merge:relaxed:youtube"):
        return "相关度中等，作为补充样本（YouTube）"
    if s.startswith("merge:relaxed:reddit"):
        return "相关度中等，作为补充样本（Reddit）"
    if s.startswith("rel:"):
        return f"关键词相关度 {s.split(':', 1)[1]}"
    if s.startswith("llm:pass:"):
        return f"语义判定相关（分数 {s.split(':')[-1]}）"
    if s.startswith("llm:reject:"):
        return f"语义评分较低但已保留（分数 {s.split(':')[-1]}）"
    if s.startswith("llm_reason:"):
        return f"语义理由：{s.split(':', 1)[1]}"
    if s.startswith("llm:fallback:no_valid_results"):
        return "语义评审暂不可用，已使用规则排序"
    if s == "llm:not_reviewed":
        return "未进入本轮语义评审，按规则排序保留"
    if s.startswith("llm_error:"):
        detail = s.split(":", 1)[1] if ":" in s else ""
        return f"语义评审暂不可用，已保留规则结果（{detail}）" if detail else "语义评审暂不可用，已保留规则结果"
    if s == "travel:intent_hit":
        return "命中旅行场景词（如行程/签证/航班等）"
    return s


def _build_pick_reason(item: Dict[str, Any]) -> str:
    rs = item.get("reasons", []) or []
    if rs:
        human = []
        for x in rs[:8]:
            hx = _humanize_reason(str(x))
            if hx:
                human.append(hx)
        if human:
            return "；".join(human)
    rel = float(item.get("relevance_score", 0.0) or 0.0)
    fin = float(item.get("final_score", 0.0) or 0.0)
    return f"规则相关性{rel:.2f}，综合分{fin:.2f}"


def _llm_json(system_prompt: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not OPENAI_API_KEY or OpenAI is None:
        return {"_error": "OPENAI_API_KEY missing or openai sdk unavailable"}
    try:
        base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1"):
                base_url = f"{base_url}/v1"
            client = OpenAI(api_key=OPENAI_API_KEY, base_url=base_url, timeout=OPENAI_TIMEOUT_SECONDS, max_retries=0)
        else:
            client = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_SECONDS, max_retries=0)
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        if isinstance(resp, str):
            if "<html" in resp[:200].lower():
                return {"_error": "OpenAI-compatible endpoint returned HTML; check OPENAI_BASE_URL and use the /v1 API path"}
            return {"_error": f"OpenAI-compatible endpoint returned plain text: {resp[:160]}"}
        content = (resp.choices[0].message.content or "{}").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        if isinstance(data, dict):
            return data
        return {"_error": "llm response is not a json object"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def _llm_rerank(niche: str, items: List[Dict[str, Any]], keep: int = 20) -> List[Dict[str, Any]]:
    if not LLM_RERANK_ENABLED or not items:
        return items[:keep]

    review_count = min(len(items), keep, max(0, LLM_RERANK_MAX_ITEMS))
    chunk_size = max(1, LLM_RERANK_CHUNK_SIZE)
    reviewed: List[Dict[str, Any]] = []

    sys_prompt = (
        "你是海外趋势编辑。按niche判断标题是否适合观察趋势、热点、爆款、可复制选题。"
        "只返回JSON：{\"results\":[{\"idx\":0,\"score\":0-10,\"reason\":\"短理由\",\"title_zh\":\"中文标题\"}]}。"
        "必须覆盖所有idx。9-10强趋势/强复制价值；7-8相关行业动态/产品/监管/融资/裁员/用户变化；"
        "5-6弱相关背景；0-4无关或平淡。score必须是0到10，不要百分制。"
    )

    def annotate_from_result(item: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
        y = dict(item)
        try:
            llm_score = float(row.get("score", 0.0) or 0.0)
        except Exception:
            llm_score = 0.0
        if 10.0 < llm_score <= 100.0:
            llm_score = llm_score / 10.0
        llm_score = max(0.0, min(10.0, llm_score))
        reason = (row.get("reason") or "").strip()
        title_zh = (row.get("title_zh") or "").strip()

        y["llm_relevance_score"] = llm_score
        if title_zh:
            y["title_zh"] = title_zh
        rs = list(y.get("reasons", []))
        rs.append(f"llm:pass:{llm_score:.1f}" if llm_score >= LLM_MIN_SCORE else f"llm:reject:{llm_score:.1f}")
        if reason:
            rs.append(f"llm_reason:{reason[:80]}")
        y["reasons"] = rs
        y["selection_reason"] = reason or y.get("selection_reason", "")
        return y

    def review_chunk(start: int, chunk: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunk_out: List[Dict[str, Any]] = []
        chunk = items[start:min(start + chunk_size, review_count)]
        payload_items = []
        for offset, x in enumerate(chunk):
            idx = start + offset
            payload_items.append({
                "idx": idx,
                "platform": x.get("platform", ""),
                "title": x.get("title", ""),
                "rule_relevance": float(x.get("relevance_score", 0.0) or 0.0),
                "rule_final": float(x.get("final_score", 0.0) or 0.0),
            })

        resp = _llm_json(sys_prompt, {"niche": niche, "items": payload_items})
        llm_error = str(resp.get("_error", "") or "") if isinstance(resp, dict) else ""
        rows = (resp or {}).get("results", []) if isinstance(resp, dict) else []
        if not rows and isinstance(resp, dict):
            rows = resp.get("items", [])
        if isinstance(rows, dict):
            rows = list(rows.values())
        by_idx: Dict[int, Dict[str, Any]] = {}
        for pos, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            try:
                idx = int(r.get("idx", r.get("index", r.get("id"))))
            except Exception:
                idx = start + pos
            if idx < start or idx >= start + len(chunk):
                if 0 <= idx < len(chunk):
                    idx = start + idx
                elif 1 <= idx <= len(chunk):
                    idx = start + idx - 1
                else:
                    idx = start + pos
            by_idx[idx] = r

        for offset, x in enumerate(chunk):
            idx = start + offset
            if llm_error:
                y = dict(x)
                y.setdefault("llm_relevance_score", None)
                rs = list(y.get("reasons", []))
                rs.append(f"llm_error:{llm_error[:120]}")
                y["reasons"] = rs
                if not y.get("selection_reason"):
                    y["selection_reason"] = llm_error[:200]
                chunk_out.append(y)
            elif idx in by_idx:
                y = annotate_from_result(x, by_idx[idx])
                if float(y.get("llm_relevance_score", 0.0) or 0.0) >= LLM_MIN_SCORE:
                    chunk_out.append(y)
            else:
                y = dict(x)
                y.setdefault("llm_relevance_score", None)
                rs = list(y.get("reasons", []))
                rs.append("llm:missing_result")
                y["reasons"] = rs
                chunk_out.append(y)
        return chunk_out

    chunks = [
        (start, items[start:min(start + chunk_size, review_count)])
        for start in range(0, review_count, chunk_size)
    ]
    if len(chunks) <= 1:
        for start, chunk in chunks:
            reviewed.extend(review_chunk(start, chunk))
    else:
        max_workers = max(1, min(LLM_RERANK_WORKERS, len(chunks)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(review_chunk, start, chunk): start
                for start, chunk in chunks
            }
            for future in as_completed(future_map):
                try:
                    reviewed.extend(future.result())
                except Exception:
                    start = future_map[future]
                    for x in items[start:min(start + chunk_size, review_count)]:
                        y = dict(x)
                        y.setdefault("llm_relevance_score", None)
                        rs = list(y.get("reasons", []))
                        rs.append("llm_error:parallel_review_failed")
                        y["reasons"] = rs
                        reviewed.append(y)

    for x in items[review_count:keep]:
        y = dict(x)
        y.setdefault("llm_relevance_score", None)
        rs = list(y.get("reasons", []))
        rs.append("llm:not_reviewed")
        y["reasons"] = rs
        reviewed.append(y)

    if not reviewed:
        return items[:keep]

    def sort_score(z: Dict[str, Any]) -> float:
        rule = min(10.0, float(z.get("final_score", 0.0) or 0.0))
        llm = z.get("llm_relevance_score", None)
        if llm is None:
            return 0.55 * rule
        return 0.65 * float(llm) + 0.35 * rule

    reviewed.sort(key=sort_score, reverse=True)
    return reviewed[:keep]


def _looks_machine_translated_or_missing(title: str, title_zh: str) -> bool:
    if not title_zh:
        return True
    if title_zh.startswith("中文参考："):
        return True
    cjk_cnt = sum(1 for ch in title_zh if "\u4e00" <= ch <= "\u9fff")
    alpha_cnt = sum(1 for ch in title_zh if ("a" <= ch.lower() <= "z"))
    return cjk_cnt < 2 and alpha_cnt >= 4


def _llm_translate_title_one(title: str) -> str:
    if not title or not OPENAI_API_KEY or OpenAI is None:
        return ""
    sys_prompt = (
        "你是中文标题翻译器。把英文社区/视频标题翻译成自然中文，保留产品名、模型名、公司名，"
        "不要添加事实，不要解释。返回JSON对象："
        "{\"title_zh\":\"...\"}。"
    )
    payload = {"title": title}
    resp = _llm_json(sys_prompt, payload)
    if not isinstance(resp, dict) or resp.get("_error"):
        return ""
    return (resp.get("title_zh") or "").strip()


def _llm_translate_titles(items: List[Dict[str, Any]], chunk_size: int = 8) -> List[Dict[str, Any]]:
    if not items or not OPENAI_API_KEY or OpenAI is None:
        return items

    out = [dict(x) for x in items]
    pending = [
        (i, x.get("title", ""))
        for i, x in enumerate(out)
        if _looks_machine_translated_or_missing(x.get("title", ""), x.get("title_zh", ""))
    ]
    if not pending:
        return out

    sys_prompt = (
        "你是中文标题翻译器。把英文社区/视频标题翻译成自然中文，保留产品名、模型名、公司名，"
        "不要添加事实，不要解释。返回JSON对象："
        "{\"results\":[{\"idx\":0,\"title_zh\":\"...\"}]}。必须覆盖所有输入idx。"
    )

    for start in range(0, len(pending), max(1, chunk_size)):
        chunk = pending[start:start + max(1, chunk_size)]
        payload = {
            "items": [
                {"idx": idx, "title": title}
                for idx, title in chunk
            ]
        }
        resp = _llm_json(sys_prompt, payload)
        if not isinstance(resp, dict) or resp.get("_error"):
            continue
        for row in resp.get("results", []) or []:
            try:
                idx = int(row.get("idx"))
            except Exception:
                continue
            title_zh = (row.get("title_zh") or "").strip()
            if title_zh and 0 <= idx < len(out):
                out[idx]["title_zh"] = title_zh
                out[idx]["title_zh_source"] = "llm_batch"
    return out


def get_trending_videos(niche: str, enable_llm: bool = None, translate_titles: bool = None) -> List[Dict[str, Any]]:
    use_llm = LLM_RERANK_ENABLED if enable_llm is None else bool(enable_llm)
    use_translation = LLM_TRANSLATE_ALL_TITLES if translate_titles is None else bool(translate_titles)
    cache_key = f"{niche.strip().lower()}|llm={int(use_llm)}|translate={int(use_translation)}"
    cached = _TREND_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return [dict(x) for x in cached[1]]

    with ThreadPoolExecutor(max_workers=2) as executor:
        yt_future = executor.submit(_fetch_youtube_trending, niche=niche, max_results=18)
        rd_future = executor.submit(_fetch_reddit_trending, niche=niche, limit=18)
        try:
            yt_seed = yt_future.result()
        except Exception:
            yt_seed = []
        try:
            rd_seed = rd_future.result()
        except Exception:
            rd_seed = []
    merged = _dedup_items(yt_seed + rd_seed)

    # 分源硬过滤：Reddit放宽相关性阈值，YouTube保持更严格
    strict = []
    relaxed = []
    for it in merged:
        title = it.get("title", "")
        body = it.get("transcript", "")
        rel = float(it.get("relevance_score", _relevance_score(niche=niche, title=title, body=body)))
        platform = (it.get("platform") or "").lower()

        strict_rel = 2.0
        relaxed_rel = 0.5
        if platform == "reddit":
            strict_rel = 1.6
            relaxed_rel = 0.5

        # 短query/泛query不要过严，优先避免 0 召回（通用化替代 AI 特判）
        niche_toks = _tokenize(niche)
        if len(niche_toks) <= 1:
            if platform == "youtube":
                strict_rel = min(strict_rel, 1.9)
                relaxed_rel = min(relaxed_rel, 0.5)
            elif platform == "reddit":
                strict_rel = min(strict_rel, 1.2)
                relaxed_rel = min(relaxed_rel, 0.4)

        # travel额外语义门禁：必须出现旅行“场景/动作”词，避免仅含 travel 的新闻政治帖
        travel_intent_terms = [
            "itinerary", "visa", "airport", "flight", "hotel", "hostel", "backpack", "carry-on",
            "layover", "road trip", "booked", "booking", "check-in", "passport", "destination",
            "tour", "trip", "traveler", "travel tips", "where to stay", "things to do"
        ]
        travel_news_noise = [
            "congress", "senate", "minister", "pope", "election", "policy", "war", "ceasefire",
            "hacked", "leak", "lawsuit", "breaking", "press conference"
        ]
        is_travel_niche = "travel" in _tokenize(niche)
        text_l = f"{title} {body}".lower()
        travel_intent_hit = any(k in text_l for k in travel_intent_terms)
        travel_noise_hit = sum(1 for k in travel_news_noise if k in text_l)

        if rel >= strict_rel:
            if is_travel_niche:
                travel_hard_block = [
                    "senator", "congress", "parliament", "election", "vote", "government",
                    "kanye", "leonardo dicaprio", "jennifer lawrence", "scorsese", "movie", "trailer",
                    "tax", "millionaire tax", "save act"
                ]
                if any(k in text_l for k in travel_hard_block):
                    continue
                if (not travel_intent_hit) and travel_noise_hit >= 1:
                    continue
            x = dict(it)
            x["relevance_score"] = rel
            rs = list(x.get("reasons", []))
            rs.extend([f"merge:strict:{platform}", f"rel:{rel:.2f}"])
            if is_travel_niche and travel_intent_hit:
                rs.append("travel:intent_hit")
            x["reasons"] = rs
            strict.append(x)
        elif rel >= relaxed_rel:
            # YouTube 放宽通道增加轻量词门禁，降低串台（尤其 travel -> AI/tool）
            if platform == "youtube" and not _niche_lexical_hit(niche=niche, title=title, body=body):
                continue
            if is_travel_niche:
                travel_hard_block = [
                    "senator", "congress", "parliament", "election", "vote", "government",
                    "kanye", "leonardo dicaprio", "jennifer lawrence", "scorsese", "movie", "trailer",
                    "tax", "millionaire tax", "save act"
                ]
                if any(k in text_l for k in travel_hard_block):
                    continue
                if not travel_intent_hit:
                    continue
            # 通用娱乐噪声降噪：仅在低相关放宽通道触发
            tl = (title or "").lower()
            generic_noise_tokens = [
                "lyrics", "official mv", "official music video", "remix", "cover", "fan cam",
                "#dance", " dance ", "challenge", "asmr"
            ]
            if rel < 1.2 and any(tok in tl for tok in generic_noise_tokens):
                continue
            x = dict(it)
            x["relevance_score"] = rel
            rs = list(x.get("reasons", []))
            rs.extend([f"merge:relaxed:{platform}", f"rel:{rel:.2f}"])
            if is_travel_niche and travel_intent_hit:
                rs.append("travel:intent_hit")
            x["reasons"] = rs
            relaxed.append(x)

    picked = strict if strict else relaxed
    if not picked:
        # 默认禁用 mock 回退，避免返回虚构数据；仅在显式开关下用于本地联调
        if os.getenv("ENABLE_MOCK_FALLBACK", "0").strip().lower() in {"1", "true", "yes", "on"}:
            ranked = _rank_items(niche=niche, items=_mock_videos(niche))
            _TREND_CACHE[cache_key] = (time.time(), [dict(x) for x in ranked])
            return ranked
        _TREND_CACHE[cache_key] = (time.time(), [])
        return []

    ranked = _rank_items(niche=niche, items=picked)
    if use_llm:
        ranked = _llm_rerank(niche=niche, items=ranked, keep=24)

    # 最终Reddit语义门禁（提高触发区间）：进一步压制弱相关帖子
    gated_ranked = []
    for x in ranked:
        if (x.get("platform") or "").lower() == "reddit":
            rel = float(x.get("relevance_score", 0.0))
            if x.get("llm_relevance_score") is not None:
                gated_ranked.append(x)
                continue
            # 对中低相关分Reddit做词门禁；高分条目直接保留
            if rel < 3.0 and not _niche_lexical_hit(
                niche=niche,
                title=x.get("title", ""),
                body=x.get("transcript", "")
            ):
                continue
        gated_ranked.append(x)
    ranked = gated_ranked

    # 分源保底混排：尽量保证Reddit在最终结果中的可见性
    yt_items = [x for x in ranked if (x.get("platform") or "").lower() == "youtube"]
    rd_items = [x for x in ranked if (x.get("platform") or "").lower() == "reddit"]

    result: List[Dict[str, Any]] = []
    # 通用分源保底：至少保留2条Reddit（若存在），其余按总分补齐
    if rd_items:
        result.extend(rd_items[:2])
        used_ids = {x.get("id") for x in result}
        for x in ranked:
            if x.get("id") in used_ids:
                continue
            result.append(x)
            if len(result) >= 20:
                break
    else:
        result = ranked[:20]

    # 输出增强：中文标题 + 抓取原因
    enhanced = []
    for x in result:
        y = dict(x)
        if not y.get("title_zh"):
            y["title_zh"] = _simple_zh_title(y.get("title", ""))
        y["why_selected"] = _build_pick_reason(y)
        if "llm_relevance_score" not in y:
            y["llm_relevance_score"] = None
        enhanced.append(y)

    if use_translation:
        enhanced = _llm_translate_titles(enhanced)

    # 无论LLM翻译是否成功，最终都保证每条有中文标题
    for y in enhanced:
        if _looks_machine_translated_or_missing(y.get("title", ""), y.get("title_zh", "")):
            retry_zh = _llm_translate_title_one(y.get("title", "")) if use_translation else ""
            if retry_zh and not _looks_machine_translated_or_missing(y.get("title", ""), retry_zh):
                y["title_zh"] = retry_zh
                y["title_zh_source"] = "llm_retry"
            else:
                y["title_zh"] = _simple_zh_title(y.get("title", ""))
                y["title_zh_source"] = "fallback"
        elif not y.get("title_zh_source"):
            y["title_zh_source"] = "existing"

    _TREND_CACHE[cache_key] = (time.time(), [dict(x) for x in enhanced])
    return enhanced
