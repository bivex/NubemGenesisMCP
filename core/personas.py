"""
Persona Management System for NubemClaude Framework
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
from dataclasses import dataclass, asdict
from .personas_unified import UnifiedPersonaManager, Persona

logger = logging.getLogger(__name__)

@dataclass
class Persona:
    """Persona data class"""
    name: str
    identity: str
    specialties: List[str]
    system_prompt: str
    capabilities: List[str]
    commands: List[Dict[str, Any]]
    confidence_scores: Dict[str, float]
    collaborates_with: List[str] = None
    rag_integration: str = None
    metrics: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert persona to dictionary"""
        return asdict(self)
    
    def get_capability_score(self, capability: str) -> float:
        """Get confidence score for a specific capability"""
        return self.confidence_scores.get(capability, 0.5)

class PersonaManager(UnifiedPersonaManager):
    """Enhanced persona manager with unified system"""
    
    def __init__(self, settings):
        self.settings = settings
        super().__init__(settings)
        # All personas are loaded by UnifiedPersonaManager
        logger.info(f"PersonaManager initialized with {self.get_total_persona_count()} personas")
        
    def load_all_personas(self) -> None:
        """Load all personas from configuration files"""
        try:
            # Load from PERSONAS.md and other files
            personas_dir = self.settings.personas_dir
            
            # Load core personas
            self._load_core_personas()
            
            # Load from markdown files
            for md_file in personas_dir.glob("PERSONAS*.md"):
                self._parse_persona_file(md_file)
            
            # Load custom personas from JSON/YAML
            custom_dir = self.settings.data_dir / "personas"
            if custom_dir.exists():
                for file in custom_dir.glob("*.{json,yaml,yml}"):
                    self._load_custom_persona(file)
            
            logger.info(f"Loaded {len(self.personas)} personas")
            
        except Exception as e:
            logger.error(f"Failed to load personas: {e}")
            # Load default personas as fallback
            self._create_default_personas()
    
    def _load_core_personas(self):
        """Load the core 16 personas"""
        core_definitions = {
            'architect': {
                'identity': 'System architect with long-term vision and scalability focus',
                'specialties': ['Microservices', 'DDD', 'Event-driven', 'Cloud-native'],
                'system_prompt': 'You are a senior system architect. Focus on scalability, maintainability, and best practices.',
                'capabilities': ['design_system', 'create_architecture', 'review_design'],
                'confidence_scores': {'design': 0.95, 'implementation': 0.7, 'ui': 0.4}
            },
            'frontend': {
                'identity': 'UI/UX specialist with focus on accessibility and performance',
                'specialties': ['React', 'Vue', 'Angular', 'CSS', 'Web Components'],
                'system_prompt': 'You are a frontend expert. Prioritize user experience, accessibility, and performance.',
                'capabilities': ['create_ui', 'optimize_frontend', 'implement_design'],
                'confidence_scores': {'ui': 0.95, 'ux': 0.9, 'backend': 0.3}
            },
            'backend': {
                'identity': 'Backend engineer specializing in APIs and databases',
                'specialties': ['REST', 'GraphQL', 'gRPC', 'Microservices', 'Databases'],
                'system_prompt': 'You are a backend engineer. Focus on performance, security, and scalability.',
                'capabilities': ['create_api', 'optimize_database', 'implement_logic'],
                'confidence_scores': {'api': 0.95, 'database': 0.9, 'ui': 0.2}
            },
            'security': {
                'identity': 'Security expert with focus on threat modeling and compliance',
                'specialties': ['OWASP', 'Pentesting', 'Encryption', 'Auth', 'Compliance'],
                'system_prompt': 'You are a security specialist. Always prioritize security and compliance.',
                'capabilities': ['security_audit', 'threat_modeling', 'implement_security'],
                'confidence_scores': {'security': 0.98, 'compliance': 0.95, 'ui': 0.2}
            },
            'devops': {
                'identity': 'Infrastructure engineer and automation expert',
                'specialties': ['CI/CD', 'Kubernetes', 'Docker', 'Terraform', 'Monitoring'],
                'system_prompt': 'You are a DevOps engineer. Focus on automation, reliability, and observability.',
                'capabilities': ['setup_cicd', 'deploy_infrastructure', 'implement_monitoring'],
                'confidence_scores': {'infrastructure': 0.95, 'automation': 0.9, 'frontend': 0.3}
            },
            'ai-specialist': {
                'identity': 'AI/ML expert specializing in LLMs and embeddings',
                'specialties': ['LLMs', 'RAG', 'Fine-tuning', 'Embeddings', 'Agents'],
                'system_prompt': 'You are an AI specialist. Focus on accuracy, efficiency, and ethical AI.',
                'capabilities': ['implement_ai', 'optimize_models', 'create_agents'],
                'confidence_scores': {'ai': 0.95, 'ml': 0.9, 'frontend': 0.3}
            }
        }
        
        for name, config in core_definitions.items():
            self.personas[name] = Persona(
                name=name,
                identity=config['identity'],
                specialties=config['specialties'],
                system_prompt=config['system_prompt'],
                capabilities=config['capabilities'],
                commands=self._generate_persona_commands(name),
                confidence_scores=config['confidence_scores'],
                collaborates_with=self._get_collaborators(name)
            )
    
    def _generate_persona_commands(self, persona_name: str) -> List[Dict[str, Any]]:
        """Generate commands for a specific persona"""
        commands = []
        
        base_commands = {
            'architect': [
                {'name': 'design-system', 'description': 'Design system architecture'},
                {'name': 'review-architecture', 'description': 'Review and improve architecture'},
                {'name': 'create-adr', 'description': 'Create Architecture Decision Record'}
            ],
            'frontend': [
                {'name': 'create-component', 'description': 'Create UI component'},
                {'name': 'optimize-performance', 'description': 'Optimize frontend performance'},
                {'name': 'audit-accessibility', 'description': 'Audit accessibility compliance'}
            ],
            'backend': [
                {'name': 'create-api', 'description': 'Create REST/GraphQL API'},
                {'name': 'optimize-query', 'description': 'Optimize database queries'},
                {'name': 'implement-cache', 'description': 'Implement caching strategy'}
            ],
            'security': [
                {'name': 'security-scan', 'description': 'Perform security scan'},
                {'name': 'threat-model', 'description': 'Create threat model'},
                {'name': 'audit-compliance', 'description': 'Audit compliance requirements'}
            ],
            'devops': [
                {'name': 'setup-pipeline', 'description': 'Setup CI/CD pipeline'},
                {'name': 'deploy-app', 'description': 'Deploy application'},
                {'name': 'configure-monitoring', 'description': 'Configure monitoring'}
            ],
            'ai-specialist': [
                {'name': 'train-model', 'description': 'Train or fine-tune model'},
                {'name': 'implement-rag', 'description': 'Implement RAG system'},
                {'name': 'optimize-prompts', 'description': 'Optimize prompts'}
            ]
        }
        
        return base_commands.get(persona_name, [])
    
    def _get_collaborators(self, persona_name: str) -> List[str]:
        """Get list of personas that collaborate with this one"""
        collaborations = {
            'architect': ['backend', 'devops', 'security'],
            'frontend': ['backend', 'architect', 'designer'],
            'backend': ['architect', 'devops', 'security', 'frontend'],
            'security': ['architect', 'backend', 'devops'],
            'devops': ['architect', 'backend', 'security'],
            'ai-specialist': ['backend', 'data-engineer', 'architect']
        }
        
        return collaborations.get(persona_name, [])
    
    def _parse_persona_file(self, file_path: Path) -> None:
        """Parse persona definitions from markdown file"""
        # This would parse the markdown files we have
        # For now, we'll use the core personas
        pass
    
    def _load_custom_persona(self, file_path: Path) -> None:
        """Load custom persona from JSON/YAML file"""
        try:
            if file_path.suffix == '.json':
                with open(file_path, 'r') as f:
                    data = json.load(f)
            else:
                with open(file_path, 'r') as f:
                    data = yaml.safe_load(f)
            
            persona = Persona(**data)
            self.personas[persona.name] = persona
            
        except Exception as e:
            logger.error(f"Failed to load custom persona from {file_path}: {e}")
    
    def _create_default_personas(self) -> None:
        """Create default personas as fallback"""
        self._load_core_personas()
    
    def get_persona(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific persona by name"""
        persona = self.personas.get(name)
        return persona.to_dict() if persona else None
    
    def list_personas(self) -> List[str]:
        """List all available personas"""
        return list(self.personas.keys())
    
    def activate_persona(self, name: str) -> bool:
        """Activate a persona"""
        if name in self.personas:
            if name not in self.active_personas:
                self.active_personas.append(name)
            return True
        return False
    
    def deactivate_persona(self, name: str) -> bool:
        """Deactivate a persona"""
        if name in self.active_personas:
            self.active_personas.remove(name)
            return True
        return False
    
    def get_active_personas(self) -> List[str]:
        """Get list of active personas"""
        return self.active_personas
    
    def find_best_persona(self, task: str) -> Optional[str]:
        """Find the best persona for a given task using confidence scores"""
        best_persona = None
        best_score = 0
        
        for name, persona in self.personas.items():
            # Simple keyword matching for now
            score = 0
            task_lower = task.lower()
            
            for specialty in persona.specialties:
                if specialty.lower() in task_lower:
                    score += 0.3
            
            for capability in persona.capabilities:
                if capability.replace('_', ' ') in task_lower:
                    score += 0.5
            
            if score > best_score:
                best_score = score
                best_persona = name
        
        return best_persona
    
    def collaborate(self, personas: List[str], task: str) -> Dict[str, Any]:
        """Enable collaboration between multiple personas"""
        results = {}
        
        for persona_name in personas:
            if persona_name in self.personas:
                persona = self.personas[persona_name]
                # Each persona contributes based on their expertise
                results[persona_name] = {
                    'contribution': f"{persona.identity} perspective on {task}",
                    'confidence': persona.get_capability_score(task)
                }
        
        return results
    
    def export_persona(self, name: str, path: str) -> bool:
        """Export a persona to file"""
        if name not in self.personas:
            return False
        
        persona = self.personas[name]
        
        try:
            with open(path, 'w') as f:
                json.dump(persona.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to export persona: {e}")
            return False
    
    def import_persona(self, path: str) -> bool:
        """Import a persona from file"""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            
            persona = Persona(**data)
            self.personas[persona.name] = persona
            return True
            
        except Exception as e:
            logger.error(f"Failed to import persona: {e}")
            return False