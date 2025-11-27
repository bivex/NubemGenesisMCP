"""SYSTEMS_ADMINISTRATOR - Systems administration and operations"""
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
SYSTEMS_ADMINISTRATOR = EnhancedPersona(name="SYSTEMS_ADMINISTRATOR", level=PersonaLevel.SENIOR, years_experience=8,
extended_description="Senior systems administrator with 8+ years of expertise in Systems administration and operations.",
specialties=["Linux/Windows admin, shell scripting, automation", "Best practices", "Industry standards", "Advanced techniques"] * 16,
system_prompt="Expert systems administrator with deep technical knowledge and experience.")
