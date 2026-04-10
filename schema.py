from pydantic import BaseModel, Field
from typing import List, Dict

class TrendAnalysis(BaseModel):
    hook_style: str = Field(description="开场钩子类型")
    pacing: str = Field(description="节奏特征")
    emotion_points: List[str] = Field(default_factory=list)
    cta_style: str
    audience: str
    why_it_works: List[str] = Field(default_factory=list)

class LocalizationPlan(BaseModel):
    cn_platform: str
    tone: str
    hook_cn: str
    cultural_mapping: List[str] = Field(default_factory=list)
    taboo_replacements: Dict[str, str] = Field(default_factory=dict)

class ScriptDraft(BaseModel):
    title: str
    opening_3s: str
    outline: List[str] = Field(default_factory=list)
    narration: str
    subtitle_suggestions: List[str] = Field(default_factory=list)
    broll_suggestions: List[str] = Field(default_factory=list)
    cta: str

class SafetyReport(BaseModel):
    passed: bool
    risk_level: str
    reasons: List[str] = Field(default_factory=list)
    fixes: List[str] = Field(default_factory=list)
