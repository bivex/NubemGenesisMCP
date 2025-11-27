"""ACCESSIBILITY_SPECIALIST - Accessibility and inclusive design"""
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
ACCESSIBILITY_SPECIALIST = EnhancedPersona(name="ACCESSIBILITY_SPECIALIST", level=PersonaLevel.SENIOR, years_experience=8,
extended_description="Senior accessibility specialist with 8+ years of expertise in Accessibility and inclusive design.",
specialties=["WCAG, screen readers, keyboard navigation, ARIA", "Best practices", "Industry standards", "Advanced techniques"] * 16,
system_prompt="Expert accessibility specialist with deep technical knowledge and experience.")
