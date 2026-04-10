import os
import json
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
API_KEY = os.getenv("OPENAI_API_KEY", "")

def _mock_json(task: str) -> Dict[str, Any]:
    if task == "analyze":
        return {
            "hook_style": "数字承诺型",
            "pacing": "快节奏",
            "emotion_points": ["省时", "效率提升"],
            "cta_style": "评论区互动",
            "audience": "职场+学生",
            "why_it_works": ["开头收益明确", "可执行性强"]
        }
    if task == "localize":
        return {
            "cn_platform": "小红书",
            "tone": "真诚分享",
            "hook_cn": "3个AI工具，每周省10小时",
            "cultural_mapping": ["no-code=>零代码"],
            "taboo_replacements": {"暴富": "增收"}
        }
    if task == "script":
        return {
            "title": "3个AI工具让我每周多出10小时",
            "opening_3s": "别再瞎忙了，这3个工具直接帮你省时间。",
            "outline": ["痛点", "工具1", "工具2", "工具3", "总结"],
            "narration": "先说结论，我把重复工作交给AI后效率翻倍。",
            "subtitle_suggestions": ["工具名+场景"],
            "broll_suggestions": ["屏幕录制"],
            "cta": "评论区回复“清单”拿模板。"
        }
    if task == "safety":
        return {"passed": True, "risk_level": "low", "reasons": [], "fixes": []}
    return {}

def _llm_json(system_prompt: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not API_KEY:
        return {}
    client = OpenAI(api_key=API_KEY)
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.4,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)

def call_agent_to_analyze(video: Dict[str, Any]) -> Dict[str, Any]:
    d = _llm_json("你是爆款分析师，输出JSON字段: hook_style,pacing,emotion_points,cta_style,audience,why_it_works", video)
    return d or _mock_json("analyze")

def call_agent_to_localize(analysis: Dict[str, Any]) -> Dict[str, Any]:
    d = _llm_json("你是中文本地化编辑，输出JSON字段: cn_platform,tone,hook_cn,cultural_mapping,taboo_replacements", analysis)
    return d or _mock_json("localize")

def call_agent_to_generate_script(localized: Dict[str, Any]) -> Dict[str, Any]:
    d = _llm_json("你是短视频编导，输出JSON字段: title,opening_3s,outline,narration,subtitle_suggestions,broll_suggestions,cta", localized)
    return d or _mock_json("script")

def call_agent_to_safety_check(script: Dict[str, Any]) -> Dict[str, Any]:
    d = _llm_json("你是风控审核，输出JSON字段: passed,risk_level,reasons,fixes", script)
    return d or _mock_json("safety")
