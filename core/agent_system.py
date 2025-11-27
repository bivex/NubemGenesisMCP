"""
Agent System - Complete implementation of 39 specialized agents
Organized by categories with intelligent selection and processing
"""

import re
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class AgentCategory(Enum):
    """Agent categories"""
    CORE_ENGINEERING = "core_engineering"
    AUTOMATION = "automation"
    CLOUD_PLATFORMS = "cloud_platforms"
    ADVANCED = "advanced"
    DOMAIN_SPECIFIC = "domain_specific"


@dataclass
class AgentCapability:
    """Single capability of an agent"""
    name: str
    description: str
    keywords: List[str]


@dataclass
class Agent:
    """Agent definition"""
    name: str
    description: str
    category: AgentCategory
    keywords: List[str]
    capabilities: List[AgentCapability] = field(default_factory=list)
    prompt_template: str = ""
    process_fn: Optional[Callable] = None
    
    async def process(self, query: str, llm_response: str) -> str:
        """Process query with agent-specific logic"""
        if self.process_fn:
            return await self.process_fn(query, llm_response)
        
        # Default processing with template
        if self.prompt_template:
            enhanced_prompt = self.prompt_template.format(
                query=query,
                response=llm_response
            )
            return enhanced_prompt
        
        return llm_response


class AgentSystem:
    """
    Complete agent system with 39 specialized agents
    """
    
    def __init__(self, llm_adapter=None, cache=None):
        self.llm_adapter = llm_adapter
        self.cache = cache
        self.agents: Dict[str, Agent] = {}
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize all 39 agents"""
        
        # ========== CORE ENGINEERING AGENTS (10) ==========
        
        self.agents['backend'] = Agent(
            name='backend',
            description='Backend development specialist for APIs, databases, and server architecture',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['api', 'backend', 'server', 'database', 'rest', 'graphql', 'microservices'],
            prompt_template="As a backend specialist, optimize this solution:\n{query}\n\nInitial response: {response}\n\nEnhanced backend solution:"
        )
        
        self.agents['frontend'] = Agent(
            name='frontend',
            description='Frontend development expert for React, Vue, Angular and UI/UX',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['react', 'vue', 'angular', 'frontend', 'ui', 'ux', 'css', 'javascript', 'typescript'],
            prompt_template="As a frontend specialist, enhance this UI solution:\n{query}\n\nBase: {response}\n\nImproved frontend approach:"
        )
        
        self.agents['fullstack'] = Agent(
            name='fullstack',
            description='Full-stack developer handling complete application architecture',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['fullstack', 'application', 'webapp', 'full-stack', 'complete', 'end-to-end'],
            prompt_template="As a fullstack architect, provide a complete solution:\n{query}\n\nInitial: {response}\n\nComplete fullstack implementation:"
        )
        
        self.agents['devops'] = Agent(
            name='devops',
            description='DevOps engineer for CI/CD, automation, and infrastructure',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['devops', 'ci', 'cd', 'pipeline', 'deployment', 'automation', 'jenkins', 'gitlab'],
            prompt_template="As a DevOps expert, optimize this deployment:\n{query}\n\nBase: {response}\n\nDevOps best practices:"
        )
        
        self.agents['architect'] = Agent(
            name='architect',
            description='Software architect for system design and architecture patterns',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['architecture', 'design', 'pattern', 'microservices', 'monolith', 'scalability', 'system'],
            prompt_template="As a software architect, design this system:\n{query}\n\nInitial: {response}\n\nArchitectural solution:"
        )
        
        self.agents['database'] = Agent(
            name='database',
            description='Database specialist for SQL, NoSQL, optimization and modeling',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['database', 'sql', 'nosql', 'mongodb', 'postgresql', 'mysql', 'redis', 'query', 'optimization'],
            prompt_template="As a database expert, optimize this data solution:\n{query}\n\nBase: {response}\n\nDatabase optimization:"
        )
        
        self.agents['security'] = Agent(
            name='security',
            description='Security expert for vulnerabilities, encryption, and best practices',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['security', 'vulnerability', 'encryption', 'authentication', 'authorization', 'owasp', 'pentest'],
            prompt_template="As a security expert, secure this implementation:\n{query}\n\nBase: {response}\n\nSecurity hardening:"
        )
        
        self.agents['performance'] = Agent(
            name='performance',
            description='Performance optimization specialist for speed and efficiency',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['performance', 'optimization', 'speed', 'efficiency', 'profiling', 'benchmark', 'latency'],
            prompt_template="As a performance expert, optimize this code:\n{query}\n\nBase: {response}\n\nPerformance optimization:"
        )
        
        self.agents['testing'] = Agent(
            name='testing',
            description='Testing specialist for unit, integration, and E2E tests',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['test', 'testing', 'unit', 'integration', 'e2e', 'tdd', 'bdd', 'coverage', 'jest', 'pytest'],
            prompt_template="As a testing expert, create comprehensive tests:\n{query}\n\nBase: {response}\n\nTest implementation:"
        )
        
        self.agents['code-reviewer'] = Agent(
            name='code-reviewer',
            description='Code review expert for quality, standards, and best practices',
            category=AgentCategory.CORE_ENGINEERING,
            keywords=['review', 'code review', 'quality', 'standards', 'refactor', 'clean code', 'solid'],
            prompt_template="As a code reviewer, analyze and improve:\n{query}\n\nCode: {response}\n\nReview and improvements:"
        )
        
        # ========== AUTOMATION & TOOLS AGENTS (7) ==========
        
        self.agents['docker'] = Agent(
            name='docker',
            description='Docker and containerization specialist',
            category=AgentCategory.AUTOMATION,
            keywords=['docker', 'container', 'dockerfile', 'compose', 'containerization', 'image'],
            prompt_template="As a Docker expert, containerize this solution:\n{query}\n\nBase: {response}\n\nDockerized implementation:"
        )
        
        self.agents['kubernetes'] = Agent(
            name='kubernetes',
            description='Kubernetes orchestration and scaling expert',
            category=AgentCategory.AUTOMATION,
            keywords=['kubernetes', 'k8s', 'orchestration', 'helm', 'pod', 'deployment', 'service', 'ingress'],
            prompt_template="As a Kubernetes expert, orchestrate this deployment:\n{query}\n\nBase: {response}\n\nKubernetes configuration:"
        )
        
        self.agents['terraform'] = Agent(
            name='terraform',
            description='Infrastructure as Code with Terraform',
            category=AgentCategory.AUTOMATION,
            keywords=['terraform', 'infrastructure', 'iac', 'provisioning', 'hcl', 'module'],
            prompt_template="As a Terraform expert, provision this infrastructure:\n{query}\n\nBase: {response}\n\nTerraform implementation:"
        )
        
        self.agents['ansible'] = Agent(
            name='ansible',
            description='Ansible automation and configuration management',
            category=AgentCategory.AUTOMATION,
            keywords=['ansible', 'playbook', 'automation', 'configuration', 'inventory', 'role'],
            prompt_template="As an Ansible expert, automate this task:\n{query}\n\nBase: {response}\n\nAnsible playbook:"
        )
        
        self.agents['monitoring'] = Agent(
            name='monitoring',
            description='Monitoring and observability with Prometheus, Grafana',
            category=AgentCategory.AUTOMATION,
            keywords=['monitoring', 'prometheus', 'grafana', 'metrics', 'alerting', 'observability', 'logging'],
            prompt_template="As a monitoring expert, implement observability:\n{query}\n\nBase: {response}\n\nMonitoring solution:"
        )
        
        self.agents['gitops'] = Agent(
            name='gitops',
            description='GitOps workflows and automation',
            category=AgentCategory.AUTOMATION,
            keywords=['gitops', 'argocd', 'flux', 'git', 'workflow', 'automation'],
            prompt_template="As a GitOps expert, implement this workflow:\n{query}\n\nBase: {response}\n\nGitOps implementation:"
        )
        
        self.agents['scripting'] = Agent(
            name='scripting',
            description='Shell scripting and automation expert',
            category=AgentCategory.AUTOMATION,
            keywords=['bash', 'shell', 'script', 'automation', 'python script', 'powershell'],
            prompt_template="As a scripting expert, automate this task:\n{query}\n\nBase: {response}\n\nAutomation script:"
        )
        
        # ========== CLOUD PLATFORM AGENTS (9) ==========
        
        self.agents['aws'] = Agent(
            name='aws',
            description='AWS cloud services and architecture expert',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['aws', 'amazon', 'ec2', 's3', 'lambda', 'cloudformation', 'rds', 'dynamodb'],
            prompt_template="As an AWS expert, implement this cloud solution:\n{query}\n\nBase: {response}\n\nAWS implementation:"
        )
        
        self.agents['gcp'] = Agent(
            name='gcp',
            description='Google Cloud Platform specialist',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['gcp', 'google cloud', 'gke', 'cloud run', 'bigquery', 'firestore', 'compute engine'],
            prompt_template="As a GCP expert, implement this solution:\n{query}\n\nBase: {response}\n\nGCP implementation:"
        )
        
        self.agents['azure'] = Agent(
            name='azure',
            description='Microsoft Azure cloud expert',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['azure', 'microsoft', 'aks', 'functions', 'cosmos', 'active directory', 'devops'],
            prompt_template="As an Azure expert, implement this solution:\n{query}\n\nBase: {response}\n\nAzure implementation:"
        )
        
        self.agents['serverless'] = Agent(
            name='serverless',
            description='Serverless architecture and FaaS expert',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['serverless', 'lambda', 'functions', 'faas', 'api gateway', 'event-driven'],
            prompt_template="As a serverless expert, design this solution:\n{query}\n\nBase: {response}\n\nServerless architecture:"
        )
        
        self.agents['cloudnative'] = Agent(
            name='cloudnative',
            description='Cloud-native application development',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['cloud-native', 'microservices', '12-factor', 'containers', 'service mesh'],
            prompt_template="As a cloud-native expert, modernize this application:\n{query}\n\nBase: {response}\n\nCloud-native solution:"
        )
        
        self.agents['multicloud'] = Agent(
            name='multicloud',
            description='Multi-cloud strategy and architecture',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['multi-cloud', 'hybrid', 'cloud agnostic', 'portability', 'vendor lock-in'],
            prompt_template="As a multi-cloud expert, design this portable solution:\n{query}\n\nBase: {response}\n\nMulti-cloud strategy:"
        )
        
        self.agents['cdn'] = Agent(
            name='cdn',
            description='CDN and edge computing specialist',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['cdn', 'cloudflare', 'edge', 'caching', 'distribution', 'performance'],
            prompt_template="As a CDN expert, optimize content delivery:\n{query}\n\nBase: {response}\n\nCDN optimization:"
        )
        
        self.agents['storage'] = Agent(
            name='storage',
            description='Cloud storage and data management',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['storage', 's3', 'blob', 'object storage', 'backup', 'archive'],
            prompt_template="As a storage expert, design this data solution:\n{query}\n\nBase: {response}\n\nStorage architecture:"
        )
        
        self.agents['networking'] = Agent(
            name='networking',
            description='Cloud networking and connectivity',
            category=AgentCategory.CLOUD_PLATFORMS,
            keywords=['networking', 'vpc', 'subnet', 'firewall', 'load balancer', 'dns', 'vpn'],
            prompt_template="As a networking expert, design this network:\n{query}\n\nBase: {response}\n\nNetwork architecture:"
        )
        
        # ========== ADVANCED TECHNOLOGY AGENTS (8) ==========
        
        self.agents['ai-ml'] = Agent(
            name='ai-ml',
            description='AI/ML model development and deployment',
            category=AgentCategory.ADVANCED,
            keywords=['ai', 'ml', 'machine learning', 'deep learning', 'neural', 'tensorflow', 'pytorch', 'model'],
            prompt_template="As an AI/ML expert, implement this model:\n{query}\n\nBase: {response}\n\nML solution:"
        )
        
        self.agents['data-science'] = Agent(
            name='data-science',
            description='Data science and analytics expert',
            category=AgentCategory.ADVANCED,
            keywords=['data science', 'analytics', 'pandas', 'numpy', 'visualization', 'statistics'],
            prompt_template="As a data scientist, analyze this data:\n{query}\n\nBase: {response}\n\nData analysis:"
        )
        
        self.agents['blockchain'] = Agent(
            name='blockchain',
            description='Blockchain and Web3 development',
            category=AgentCategory.ADVANCED,
            keywords=['blockchain', 'web3', 'smart contract', 'ethereum', 'solidity', 'defi', 'nft'],
            prompt_template="As a blockchain expert, implement this Web3 solution:\n{query}\n\nBase: {response}\n\nBlockchain implementation:"
        )
        
        self.agents['iot'] = Agent(
            name='iot',
            description='IoT and embedded systems specialist',
            category=AgentCategory.ADVANCED,
            keywords=['iot', 'embedded', 'mqtt', 'sensor', 'arduino', 'raspberry', 'edge computing'],
            prompt_template="As an IoT expert, design this solution:\n{query}\n\nBase: {response}\n\nIoT implementation:"
        )
        
        self.agents['quantum'] = Agent(
            name='quantum',
            description='Quantum computing specialist',
            category=AgentCategory.ADVANCED,
            keywords=['quantum', 'qiskit', 'quantum computing', 'qubit', 'superposition'],
            prompt_template="As a quantum computing expert, explain this concept:\n{query}\n\nBase: {response}\n\nQuantum solution:"
        )
        
        self.agents['ar-vr'] = Agent(
            name='ar-vr',
            description='AR/VR and metaverse development',
            category=AgentCategory.ADVANCED,
            keywords=['ar', 'vr', 'augmented', 'virtual', 'unity', 'unreal', 'metaverse', '3d'],
            prompt_template="As an AR/VR expert, create this experience:\n{query}\n\nBase: {response}\n\nAR/VR implementation:"
        )
        
        self.agents['robotics'] = Agent(
            name='robotics',
            description='Robotics and automation systems',
            category=AgentCategory.ADVANCED,
            keywords=['robotics', 'ros', 'automation', 'control', 'sensors', 'actuators'],
            prompt_template="As a robotics expert, design this system:\n{query}\n\nBase: {response}\n\nRobotics solution:"
        )
        
        self.agents['cybersecurity'] = Agent(
            name='cybersecurity',
            description='Advanced cybersecurity and threat analysis',
            category=AgentCategory.ADVANCED,
            keywords=['cybersecurity', 'threat', 'incident', 'forensics', 'malware', 'penetration'],
            prompt_template="As a cybersecurity expert, analyze this threat:\n{query}\n\nBase: {response}\n\nSecurity analysis:"
        )
        
        # ========== DOMAIN SPECIFIC AGENTS (5) ==========
        
        self.agents['mobile'] = Agent(
            name='mobile',
            description='Mobile app development for iOS and Android',
            category=AgentCategory.DOMAIN_SPECIFIC,
            keywords=['mobile', 'ios', 'android', 'react native', 'flutter', 'swift', 'kotlin', 'app'],
            prompt_template="As a mobile expert, develop this app:\n{query}\n\nBase: {response}\n\nMobile implementation:"
        )
        
        self.agents['gaming'] = Agent(
            name='gaming',
            description='Game development and design',
            category=AgentCategory.DOMAIN_SPECIFIC,
            keywords=['game', 'gaming', 'unity', 'unreal', 'godot', 'gameplay', 'graphics'],
            prompt_template="As a game developer, create this game:\n{query}\n\nBase: {response}\n\nGame implementation:"
        )
        
        self.agents['fintech'] = Agent(
            name='fintech',
            description='Financial technology and banking systems',
            category=AgentCategory.DOMAIN_SPECIFIC,
            keywords=['fintech', 'finance', 'banking', 'payment', 'trading', 'cryptocurrency'],
            prompt_template="As a fintech expert, implement this financial system:\n{query}\n\nBase: {response}\n\nFintech solution:"
        )
        
        self.agents['healthtech'] = Agent(
            name='healthtech',
            description='Healthcare technology and medical systems',
            category=AgentCategory.DOMAIN_SPECIFIC,
            keywords=['health', 'medical', 'healthcare', 'telemedicine', 'ehr', 'fhir', 'hipaa'],
            prompt_template="As a healthtech expert, design this medical system:\n{query}\n\nBase: {response}\n\nHealthtech solution:"
        )
        
        self.agents['edtech'] = Agent(
            name='edtech',
            description='Educational technology and e-learning',
            category=AgentCategory.DOMAIN_SPECIFIC,
            keywords=['education', 'edtech', 'learning', 'lms', 'course', 'training', 'e-learning'],
            prompt_template="As an edtech expert, create this learning solution:\n{query}\n\nBase: {response}\n\nEdtech implementation:"
        )
        
        logger.info(f"Initialized {len(self.agents)} specialized agents")
    
    def select_agent(self, query: str) -> Optional[Agent]:
        """
        Intelligently select the best agent for a query
        
        Args:
            query: User query
        
        Returns:
            Selected agent or None
        """
        query_lower = query.lower()
        scores = {}
        
        for name, agent in self.agents.items():
            score = 0
            
            # Check keywords
            for keyword in agent.keywords:
                if keyword in query_lower:
                    score += 10
                elif any(word in query_lower for word in keyword.split()):
                    score += 5
            
            # Check partial matches
            if agent.name in query_lower:
                score += 15
            
            # Category-based scoring
            if 'cloud' in query_lower and agent.category == AgentCategory.CLOUD_PLATFORMS:
                score += 3
            elif 'ai' in query_lower or 'ml' in query_lower:
                if agent.category == AgentCategory.ADVANCED:
                    score += 3
            
            if score > 0:
                scores[name] = score
        
        if not scores:
            # Default to architect for general queries
            return self.agents.get('architect')
        
        # Select agent with highest score
        best_agent = max(scores, key=scores.get)
        logger.info(f"Selected agent: {best_agent} (score: {scores[best_agent]})")
        
        return self.agents[best_agent]
    
    def get_agent(self, name: str) -> Optional[Agent]:
        """Get agent by name"""
        return self.agents.get(name)
    
    def list_agents(self) -> List[Agent]:
        """List all agents"""
        return list(self.agents.values())
    
    def list_agents_by_category(self, category: AgentCategory) -> List[Agent]:
        """List agents by category"""
        return [
            agent for agent in self.agents.values()
            if agent.category == category
        ]
    
    def search_agents(self, keyword: str) -> List[Agent]:
        """Search agents by keyword"""
        keyword_lower = keyword.lower()
        matching_agents = []
        
        for agent in self.agents.values():
            if (keyword_lower in agent.name or
                keyword_lower in agent.description.lower() or
                any(keyword_lower in kw for kw in agent.keywords)):
                matching_agents.append(agent)
        
        return matching_agents