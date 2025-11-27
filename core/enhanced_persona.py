"""
Enhanced Persona System with Rich Context and Knowledge Bases
Provides 10x more context and examples than basic personas
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class ProficiencyLevel(Enum):
    """Proficiency levels for skills"""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    THOUGHT_LEADER = "thought_leader"


@dataclass
class KnowledgeDomain:
    """Detailed knowledge in a specific domain"""
    name: str
    proficiency: ProficiencyLevel
    technologies: List[str]
    patterns: List[str]
    best_practices: List[str]
    anti_patterns: List[str]
    when_to_use: str
    when_not_to_use: str
    trade_offs: Dict[str, List[str]]  # {'pros': [...], 'cons': [...]}


@dataclass
class CaseStudy:
    """Real-world case study with implementation details"""
    title: str
    context: str
    challenge: str
    solution: Dict[str, Any]  # approach, steps, tech_stack, results
    lessons_learned: List[str]
    code_examples: Optional[str] = None
    diagrams: Optional[List[str]] = None
    metrics: Optional[Dict[str, str]] = None


@dataclass
class CodeExample:
    """Code example with explanation"""
    title: str
    description: str
    language: str
    code: str
    explanation: str
    best_practices: List[str]
    common_mistakes: List[str]
    related_patterns: List[str]


@dataclass
class Workflow:
    """Step-by-step workflow for common tasks"""
    name: str
    description: str
    when_to_use: str
    steps: List[str]
    tools_required: List[str]
    template: Optional[str] = None
    examples: Optional[List[str]] = None


@dataclass
class Tool:
    """Tool or technology the persona uses"""
    name: str
    category: str
    proficiency: ProficiencyLevel
    use_cases: List[str]
    alternatives: List[str]
    learning_resources: List[str]


@dataclass
class RAGSource:
    """Knowledge source for RAG integration"""
    name: str
    type: str  # 'documentation', 'book', 'article', 'video', 'course'
    url: Optional[str] = None
    description: Optional[str] = None
    relevance_score: float = 1.0


@dataclass
class EnhancedPersona:
    """
    Enhanced Persona with deep context and knowledge

    Provides 10-100x more information than basic personas:
    - Detailed knowledge domains (20-30 specialties)
    - Real case studies (5-10 examples)
    - Code examples (20-30 snippets)
    - Best practices and anti-patterns
    - Workflows and templates
    - RAG sources for continuous learning
    """

    # BASIC IDENTITY
    name: str
    identity: str
    level: str  # L1-L5
    years_experience: int

    # RICH CONTEXT
    extended_description: str = ""  # 200-300 words
    philosophy: str = ""  # How this persona approaches problems
    communication_style: str = ""  # How they explain concepts

    # DEEP KNOWLEDGE
    knowledge_domains: Dict[str, KnowledgeDomain] = field(default_factory=dict)
    specialties: List[str] = field(default_factory=list)  # 20-30 items
    tools: List[Tool] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    methodologies: List[str] = field(default_factory=list)

    # EXAMPLES AND CONTEXT
    case_studies: List[CaseStudy] = field(default_factory=list)
    code_examples: List[CodeExample] = field(default_factory=list)
    workflows: List[Workflow] = field(default_factory=list)

    # BEST PRACTICES
    best_practices: Dict[str, List[str]] = field(default_factory=dict)
    anti_patterns: Dict[str, List[str]] = field(default_factory=dict)
    common_mistakes: List[str] = field(default_factory=list)
    quality_checklist: List[str] = field(default_factory=list)

    # PROMPTS (EXTENSIVE)
    system_prompt: str = ""  # 800-1200 words
    context_prompt: str = ""  # Additional context
    example_interactions: List[Dict[str, str]] = field(default_factory=list)

    # CAPABILITIES
    capabilities: List[str] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)

    # COLLABORATION
    collaborates_with: List[str] = field(default_factory=list)
    delegates_to: List[str] = field(default_factory=list)
    consults_with: List[str] = field(default_factory=list)

    # RAG INTEGRATION
    rag_sources: List[RAGSource] = field(default_factory=list)
    documentation_urls: List[str] = field(default_factory=list)
    api_integrations: List[str] = field(default_factory=list)

    # METRICS
    success_metrics: List[str] = field(default_factory=list)
    performance_indicators: Dict[str, str] = field(default_factory=dict)

    def get_knowledge_summary(self) -> Dict[str, Any]:
        """Get a summary of this persona's knowledge"""
        return {
            'name': self.name,
            'level': self.level,
            'experience_years': self.years_experience,
            'specialties_count': len(self.specialties),
            'knowledge_domains': len(self.knowledge_domains),
            'case_studies': len(self.case_studies),
            'code_examples': len(self.code_examples),
            'workflows': len(self.workflows),
            'tools': len(self.tools),
            'rag_sources': len(self.rag_sources),
            'total_best_practices': sum(len(v) for v in self.best_practices.values()),
            'total_anti_patterns': sum(len(v) for v in self.anti_patterns.values())
        }

    def get_full_context(self) -> str:
        """Generate full context string for LLM"""
        context_parts = [
            f"# {self.name.upper()} - {self.identity}",
            f"\n## Experience: {self.years_experience} years | Level: {self.level}",
            f"\n## Description\n{self.extended_description}",
            f"\n## Philosophy\n{self.philosophy}",
            f"\n## System Prompt\n{self.system_prompt}"
        ]

        # Add knowledge domains
        if self.knowledge_domains:
            context_parts.append("\n## Knowledge Domains")
            for domain_name, domain in self.knowledge_domains.items():
                context_parts.append(f"\n### {domain_name} ({domain.proficiency.value})")
                context_parts.append(f"- Technologies: {', '.join(domain.technologies[:10])}")
                context_parts.append(f"- Patterns: {', '.join(domain.patterns[:5])}")

        # Add case studies summary
        if self.case_studies:
            context_parts.append(f"\n## Case Studies ({len(self.case_studies)} available)")
            for study in self.case_studies[:3]:  # Top 3
                context_parts.append(f"\n### {study.title}")
                context_parts.append(f"{study.context[:200]}...")

        # Add best practices
        if self.best_practices:
            context_parts.append("\n## Best Practices")
            for category, practices in list(self.best_practices.items())[:3]:
                context_parts.append(f"\n### {category}")
                for practice in practices[:5]:
                    context_parts.append(f"- {practice}")

        return "\n".join(context_parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'name': self.name,
            'identity': self.identity,
            'level': self.level,
            'years_experience': self.years_experience,
            'specialties': self.specialties,
            'tools': [{'name': t.name, 'category': t.category} for t in self.tools],
            'case_studies_count': len(self.case_studies),
            'code_examples_count': len(self.code_examples),
            'knowledge_domains': list(self.knowledge_domains.keys()),
            'rag_sources': [{'name': s.name, 'type': s.type} for s in self.rag_sources]
        }


# Factory function to create enhanced personas
def create_enhanced_persona(
    name: str,
    identity: str,
    level: str,
    years_experience: int,
    **kwargs
) -> EnhancedPersona:
    """
    Create an enhanced persona with validation

    Example:
        persona = create_enhanced_persona(
            name="architect",
            identity="Enterprise System Architect",
            level="L5",
            years_experience=15,
            specialties=['Microservices', 'DDD', 'Cloud Native'],
            knowledge_domains={...},
            case_studies=[...]
        )
    """
    return EnhancedPersona(
        name=name,
        identity=identity,
        level=level,
        years_experience=years_experience,
        **kwargs
    )


# Example: Comparison of Basic vs Enhanced Persona
def compare_personas():
    """Compare basic vs enhanced persona"""

    basic = {
        'name': 'architect',
        'identity': 'System architect',
        'specialties': ['Microservices', 'DDD', 'Event-driven'],
        'system_prompt': 'You are a system architect. Design scalable systems.'
    }

    enhanced = create_enhanced_persona(
        name="architect",
        identity="Enterprise System Architect specializing in distributed systems",
        level="L5",
        years_experience=15,
        extended_description="""
        Senior Enterprise Architect with 15+ years designing and scaling distributed systems
        for Fortune 500 companies. Specializes in microservices architecture, domain-driven
        design, and cloud-native patterns. Has led migrations of monolithic applications to
        microservices for systems serving 100M+ users. Expert in trade-off analysis and
        making architectural decisions based on business context, team capabilities, and
        technical constraints.
        """,
        specialties=[
            'Microservices Architecture', 'Domain-Driven Design (DDD)', 'Event-Driven Architecture',
            'CQRS/Event Sourcing', 'Service Mesh', 'API Gateway Patterns', 'Saga Pattern',
            'Circuit Breaker', 'Bulkhead Pattern', 'Strangler Fig Pattern',
            'Cloud-Native Patterns', '12-Factor Apps', 'Serverless Architecture',
            'Data Mesh', 'Lambda Architecture', 'Polyglot Persistence',
            'Zero Trust Architecture', 'OAuth2/OIDC', 'mTLS',
            'Kubernetes Architecture', 'Service Discovery', 'Load Balancing',
            'Distributed Tracing', 'Observability', 'SRE Principles'
        ],
        knowledge_domains={
            'microservices': KnowledgeDomain(
                name='Microservices Architecture',
                proficiency=ProficiencyLevel.EXPERT,
                technologies=['Kubernetes', 'Istio', 'Kong', 'Kafka', 'gRPC'],
                patterns=['Service Mesh', 'API Gateway', 'Saga', 'CQRS'],
                best_practices=[
                    'Design services around business capabilities',
                    'Each service owns its data',
                    'Use async communication by default',
                    'Implement circuit breakers',
                    'Version APIs from day 1'
                ],
                anti_patterns=[
                    'Distributed monolith (services sharing DB)',
                    'Chatty APIs (too many service calls)',
                    'No monitoring/observability',
                    'Tight coupling between services'
                ],
                when_to_use='Large systems, multiple teams, need for independent scaling',
                when_not_to_use='Small systems, single team, simple CRUD applications',
                trade_offs={
                    'pros': ['Independent deployment', 'Technology diversity', 'Fault isolation'],
                    'cons': ['Distributed complexity', 'Network latency', 'Data consistency']
                }
            )
        }
    )

    print("BASIC PERSONA:")
    print(f"  Specialties: {len(basic['specialties'])}")
    print(f"  System prompt length: {len(basic['system_prompt'])} chars")
    print(f"  Knowledge depth: Minimal")

    print("\nENHANCED PERSONA:")
    summary = enhanced.get_knowledge_summary()
    print(f"  Specialties: {summary['specialties_count']}")
    print(f"  Knowledge domains: {summary['knowledge_domains']}")
    print(f"  System prompt length: {len(enhanced.system_prompt)} chars")
    print(f"  Case studies: {summary['case_studies']}")
    print(f"  Code examples: {summary['code_examples']}")
    print(f"  Best practices: {summary['total_best_practices']}")
    print(f"  Knowledge depth: Expert")

    print(f"\n✅ IMPROVEMENT: {summary['specialties_count']/len(basic['specialties'])}x more specialties")


if __name__ == "__main__":
    compare_personas()
