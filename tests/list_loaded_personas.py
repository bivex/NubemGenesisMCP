#!/usr/bin/env python3
"""List all loaded personas to verify names"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_orchestrator import PersonaStrategy

strategy = PersonaStrategy()

# Force load all personas
if len(strategy.persona_manager.personas) == 0:
    print("Loading all personas...")
    strategy.persona_manager.load_all_personas()

print("\n" + "="*80)
print("📋 LOADED PERSONAS")
print("="*80 + "\n")

personas = sorted(strategy.persona_manager.personas.keys())

print(f"Total: {len(personas)} personas\n")

# Group by category
categories = {}
for name in personas:
    # Try to categorize by common patterns
    if any(x in name for x in ['architect', 'system', 'solution']):
        cat = "Architecture"
    elif any(x in name for x in ['security', 'penetration', 'crypto']):
        cat = "Security"
    elif any(x in name for x in ['data', 'ml', 'ai']):
        cat = "Data & AI"
    elif any(x in name for x in ['cloud', 'gcp', 'aws', 'azure', 'kubernetes', 'devops', 'sre']):
        cat = "Cloud & DevOps"
    elif any(x in name for x in ['frontend', 'backend', 'fullstack', 'mobile', 'developer']):
        cat = "Development"
    elif any(x in name for x in ['testing', 'qa', 'debug']):
        cat = "Testing & QA"
    else:
        cat = "Other"

    if cat not in categories:
        categories[cat] = []
    categories[cat].append(name)

for cat in sorted(categories.keys()):
    print(f"\n{cat}:")
    for name in categories[cat]:
        print(f"  - {name}")

print("\n" + "="*80 + "\n")

# Search for specific personas we need
target_personas = [
    'nlp-expert', 'nlp', 'natural-language',
    'kubernetes-expert', 'kubernetes', 'k8s',
    'security-architect', 'security',
    'sre-engineer', 'sre', 'site-reliability',
    'debugging-expert', 'debugging', 'debugger'
]

print("🔍 SEARCHING FOR TARGET PERSONAS:\n")
for target in target_personas:
    matches = [p for p in personas if target in p]
    if matches:
        print(f"  '{target}' → {matches}")
    else:
        print(f"  '{target}' → ❌ NOT FOUND")

print("\n" + "="*80 + "\n")
