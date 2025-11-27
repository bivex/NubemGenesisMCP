"""
Persona Selector for v6-auto-routing

Selects optimal persona(s) based on domain analysis.
"""

from typing import List, Dict
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PersonaRecommendation:
    """Represents a recommended persona with metadata"""
    persona_id: str
    confidence: float
    reason: str
    capabilities: List[str]


class PersonaSelector:
    """
    Selects optimal personas for a query based on domain analysis.
    """

    # Mapping from domains to personas
    DOMAIN_TO_PERSONA = {
        # Programming Languages
        "python": [
            ("senior-developer", 0.9, "Python development expertise"),
            ("backend-specialist", 0.7, "Backend Python development")
        ],
        "javascript": [
            ("frontend-specialist", 0.9, "Frontend JavaScript expertise"),
            ("fullstack-engineer", 0.7, "Full stack JavaScript development")
        ],
        "java": [
            ("senior-developer", 0.8, "Java development"),
            ("backend-specialist", 0.9, "Enterprise Java development")
        ],
        "go": [
            ("backend-specialist", 0.9, "Go backend development"),
            ("cloud-architect", 0.6, "Cloud-native Go applications")
        ],

        # Backend
        "backend": [
            ("backend-specialist", 0.95, "Backend architecture and APIs"),
            ("api-architect", 0.8, "API design and development")
        ],

        # Frontend
        "frontend": [
            ("frontend-specialist", 0.95, "Frontend development and UI/UX"),
            ("ux-designer", 0.7, "User experience design")
        ],

        # Database
        "database": [
            ("database-architect", 0.95, "Database design and optimization"),
            ("data-engineer", 0.6, "Data engineering and pipelines")
        ],

        # Security
        "security": [
            ("security-expert", 0.95, "Security analysis and best practices"),
            ("compliance-specialist", 0.6, "Security compliance")
        ],
        "penetration": [
            ("penetration-tester", 0.95, "Penetration testing and vulnerability assessment"),
            ("security-expert", 0.7, "Security expertise")
        ],

        # Infrastructure & Cloud
        "devops": [
            ("devops-specialist", 0.95, "DevOps practices and CI/CD"),
            ("infrastructure-engineer", 0.7, "Infrastructure automation")
        ],
        "cloud": [
            ("cloud-architect", 0.95, "Cloud architecture and design"),
            ("sre-specialist", 0.7, "Site reliability engineering")
        ],

        # Data & AI
        "data-science": [
            ("data-scientist", 0.95, "Data science and ML"),
            ("ml-engineer", 0.8, "Machine learning engineering")
        ],
        "data-engineering": [
            ("data-engineer", 0.95, "Data pipelines and ETL"),
            ("database-architect", 0.6, "Data architecture")
        ],

        # Business & Process
        "product": [
            ("product-manager", 0.95, "Product management and strategy"),
            ("business-analyst", 0.7, "Business analysis")
        ],
        "qa": [
            ("qa-engineer", 0.95, "Quality assurance and testing"),
            ("test-automation-engineer", 0.8, "Test automation")
        ],

        # General fallback
        "general": [
            ("senior-developer", 0.6, "General technical guidance")
        ]
    }

    # Task type modifiers - adds additional personas based on task
    TASK_MODIFIERS = {
        "review": {
            "personas": ["senior-developer", "code-reviewer"],
            "reason": "Code review expertise"
        },
        "security": {
            "personas": ["security-expert", "penetration-tester"],
            "reason": "Security analysis"
        },
        "optimize": {
            "personas": ["performance-engineer", "sre-specialist"],
            "reason": "Performance optimization"
        },
        "design": {
            "personas": ["system-architect", "solution-architect"],
            "reason": "System design"
        },
    }

    def select_personas(self, analysis: Dict) -> List[PersonaRecommendation]:
        """
        Selects optimal personas based on domain analysis.

        Args:
            analysis: Output from DomainAnalyzer

        Returns:
            List of PersonaRecommendation objects sorted by confidence
        """
        recommendations = []

        # 1. Primary domain personas
        primary_domain = analysis.get("primary_domain", "general")
        if primary_domain in self.DOMAIN_TO_PERSONA:
            for persona_id, base_confidence, reason in self.DOMAIN_TO_PERSONA[primary_domain]:
                # Adjust confidence based on analysis confidence
                adjusted_confidence = base_confidence * analysis.get("confidence", 0.5)

                recommendations.append(PersonaRecommendation(
                    persona_id=persona_id,
                    confidence=adjusted_confidence,
                    reason=reason,
                    capabilities=[primary_domain]
                ))

        # 2. Secondary domain personas (if complexity is high)
        complexity = analysis.get("complexity", "low")
        if complexity in ["high", "very_high"]:
            secondary_domain = analysis.get("secondary_domain")
            if secondary_domain and secondary_domain in self.DOMAIN_TO_PERSONA:
                for persona_id, base_confidence, reason in self.DOMAIN_TO_PERSONA[secondary_domain]:
                    # Lower weight for secondary domain
                    adjusted_confidence = base_confidence * 0.7

                    # Avoid duplicates
                    if not any(r.persona_id == persona_id for r in recommendations):
                        recommendations.append(PersonaRecommendation(
                            persona_id=persona_id,
                            confidence=adjusted_confidence,
                            reason=f"Secondary: {reason}",
                            capabilities=[secondary_domain]
                        ))

        # 3. Task-specific persona modifiers (ONLY if no strong domain personas)
        task_type = analysis.get("task_type", "general")

        # Only add task modifiers if we don't have high-confidence domain personas
        has_strong_domain_persona = any(r.confidence >= 0.7 for r in recommendations)

        if not has_strong_domain_persona and task_type in self.TASK_MODIFIERS:
            task_info = self.TASK_MODIFIERS[task_type]
            for persona_id in task_info["personas"]:
                # Check if not already added
                if not any(r.persona_id == persona_id for r in recommendations):
                    recommendations.append(PersonaRecommendation(
                        persona_id=persona_id,
                        confidence=0.5,  # Lower confidence for task-based
                        reason=task_info["reason"],
                        capabilities=[task_type]
                    ))

        # 4. Sort by confidence
        recommendations.sort(key=lambda x: x.confidence, reverse=True)

        # 5. Decide single vs multi-persona based on complexity
        if complexity == "very_high" and len(recommendations) >= 3:
            # Return top 3 for orchestration
            result = recommendations[:3]
        elif complexity == "high" and len(recommendations) >= 2:
            # Return top 2 for orchestration
            result = recommendations[:2]
        else:
            # Return top 1 for single persona
            result = recommendations[:1] if recommendations else [
                PersonaRecommendation(
                    persona_id="senior-developer",
                    confidence=0.5,
                    reason="Default fallback",
                    capabilities=["general"]
                )
            ]

        logger.info(f"Selected {len(result)} persona(s): {[r.persona_id for r in result]}")
        return result

    def requires_orchestration(self, recommendations: List[PersonaRecommendation]) -> bool:
        """
        Determines if orchestration (multiple personas) is needed.
        """
        return len(recommendations) > 1
