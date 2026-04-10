from typing import List, Dict, Any
import random

def get_trending_videos(niche: str) -> List[Dict[str, Any]]:
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
