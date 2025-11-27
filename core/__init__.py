"""
NubemClaude Framework Core
The Ultimate AI-Powered Development Framework
"""

from .framework import NubemClaudeFramework
from .personas import PersonaManager
from .commands import CommandRegistry
from .config import Settings

__version__ = "3.0.0"
__all__ = [
    "NubemClaudeFramework",
    "PersonaManager", 
    "CommandRegistry",
    "Settings"
]