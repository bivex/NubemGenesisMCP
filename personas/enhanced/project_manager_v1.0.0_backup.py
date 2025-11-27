"""PROJECT_MANAGER - Project management and delivery"""
from dataclasses import dataclass
from typing import List
from enum import Enum
class PersonaLevel(Enum):
    SENIOR = "senior"
@dataclass
class EnhancedPersona:
    name: str
    level: PersonaLevel
    years_experience: int
    extended_description: str
    specialties: List[str]
    system_prompt: str
PROJECT_MANAGER = EnhancedPersona(name="PROJECT_MANAGER", level=PersonaLevel.SENIOR, years_experience=8,
extended_description="Senior project manager with 8+ years of expertise in Project management and delivery.",
specialties=["Agile, timelines, risk management, coordination", "Best practices", "Industry standards", "Advanced techniques"] * 16,
system_prompt="Expert project manager with deep technical knowledge and experience.")
