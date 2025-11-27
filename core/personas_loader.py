"""
Personas Loader - Dynamic loading of Tier 1 enhanced personas
Loads personas from personas/enhanced/*.py files and integrates them into ALL_EXTENDED_PERSONAS
"""

import os
import sys
import importlib.util
from pathlib import Path
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


def load_persona_from_file(filepath: Path) -> Dict[str, Any]:
    """
    Load a Tier 1 persona from a Python file

    Args:
        filepath: Path to the persona file

    Returns:
        Persona dictionary with identity, system_prompt, specialties, etc.
    """
    try:
        # Load module from file
        spec = importlib.util.spec_from_file_location(filepath.stem, filepath)
        if not spec or not spec.loader:
            logger.error(f"Failed to load spec for {filepath}")
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for persona variable (check multiple naming conventions)
        persona = None
        persona_var_name = filepath.stem.upper().replace('-', '_')

        # Try PERSONA_NAME format (e.g., PRODUCT_MANAGER)
        if hasattr(module, persona_var_name):
            persona = getattr(module, persona_var_name)
        # Try PERSONA format
        elif hasattr(module, 'PERSONA'):
            persona = getattr(module, 'PERSONA')

        if persona:
            # Convert EnhancedPersona object to dictionary format
            persona_dict = {
                'identity': {
                    'name': persona.name,
                    'role': persona.name  # Use name as role for now
                },
                'system_prompt': persona.system_prompt,
                'specialties': persona.specialties,
                'capabilities': ['analyze', 'design', 'implement', 'optimize', 'mentor'],
                'level': 'L5',  # Tier 1 = L5 (highest level)
                'tier': 1,
                'enhanced': True,
                'source_file': str(filepath),
                'years_experience': getattr(persona, 'years_experience', 10)
            }

            # Add optional fields if present
            if hasattr(persona, 'knowledge_domains'):
                persona_dict['knowledge_domains'] = [
                    {
                        'name': kd.name,
                        'proficiency': kd.proficiency.value if hasattr(kd.proficiency, 'value') else str(kd.proficiency),
                        'best_practices': kd.best_practices,
                        'anti_patterns': kd.anti_patterns,
                        'patterns': kd.patterns,
                        'tools': kd.tools
                    }
                    for kd in persona.knowledge_domains
                ]

            if hasattr(persona, 'case_studies'):
                persona_dict['case_studies'] = [
                    {
                        'title': cs.title,
                        'context': cs.context,
                        'challenge': cs.challenge,
                        'solution': cs.solution,
                        'results': cs.results,
                        'lessons_learned': getattr(cs, 'lessons_learned', []),
                        'code_examples': getattr(cs, 'code_examples', [])
                    }
                    for cs in persona.case_studies
                ]

            if hasattr(persona, 'communication_style'):
                persona_dict['communication_style'] = persona.communication_style

            if hasattr(persona, 'workflows'):
                persona_dict['workflows'] = [
                    {
                        'name': wf.name,
                        'steps': wf.steps,
                        'best_practices': getattr(wf, 'best_practices', [])
                    }
                    for wf in persona.workflows
                ]

            if hasattr(persona, 'tools'):
                persona_dict['tools'] = persona.tools

            if hasattr(persona, 'rag_sources'):
                persona_dict['rag_sources'] = persona.rag_sources

            if hasattr(persona, 'philosophy'):
                persona_dict['philosophy'] = persona.philosophy

            if hasattr(persona, 'extended_description'):
                persona_dict['extended_description'] = persona.extended_description

            return persona_dict

    except Exception as e:
        logger.error(f"Error loading persona from {filepath}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None

    return None


def load_all_enhanced_personas() -> Dict[str, Dict[str, Any]]:
    """
    Load all Tier 1 enhanced personas from personas/enhanced/ directory

    Returns:
        Dictionary of personas keyed by persona-key (kebab-case)
    """
    enhanced_personas = {}

    # Get path to enhanced personas directory
    base_path = Path(__file__).parent.parent / 'personas' / 'enhanced'

    if not base_path.exists():
        logger.warning(f"Enhanced personas directory not found: {base_path}")
        return enhanced_personas

    # Week 4 Tier 1 personas (known to be valid)
    tier1_files = [
        'product_manager.py',
        'engineering_manager.py',
        'startup_cto.py',
        'blockchain_developer.py',
        'embedded_systems_engineer.py',
        'network_engineer.py'
    ]

    # Load each Tier 1 file
    for filename in tier1_files:
        filepath = base_path / filename

        if not filepath.exists():
            logger.warning(f"Tier 1 persona file not found: {filename}")
            continue

        logger.info(f"Loading enhanced persona: {filepath.stem}")
        persona_dict = load_persona_from_file(filepath)

        if persona_dict:
            # Create kebab-case key from filename
            persona_key = filepath.stem.replace('_', '-').lower()
            enhanced_personas[persona_key] = persona_dict
            logger.info(f"✓ Loaded {persona_key} ({len(persona_dict['specialties'])} specialties)")
        else:
            logger.warning(f"✗ Failed to load {filepath.stem}")

    return enhanced_personas


def merge_personas(base_personas: Dict[str, Any], enhanced_personas: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge enhanced personas into base personas dictionary
    Enhanced personas override base personas if they have the same key

    Args:
        base_personas: Base personas from personas_extended.py
        enhanced_personas: Enhanced Tier 1 personas from files

    Returns:
        Merged dictionary with enhanced personas taking precedence
    """
    merged = base_personas.copy()

    for key, persona in enhanced_personas.items():
        if key in merged:
            logger.info(f"Replacing {key} with enhanced version")
        merged[key] = persona

    return merged


def get_tier1_persona_keys() -> List[str]:
    """
    Get list of all Tier 1 enhanced persona keys

    Returns:
        List of persona keys that have been enhanced to Tier 1
    """
    base_path = Path(__file__).parent.parent / 'personas' / 'enhanced'

    if not base_path.exists():
        return []

    return [
        filepath.stem.replace('_', '-').lower()
        for filepath in base_path.glob('*.py')
        if filepath.stem != '__init__'
    ]


def get_persona_stats() -> Dict[str, Any]:
    """
    Get statistics about loaded personas

    Returns:
        Dictionary with persona statistics
    """
    from core.personas_extended import ALL_EXTENDED_PERSONAS

    tier1_keys = get_tier1_persona_keys()
    tier1_count = len(tier1_keys)

    # Count personas with 60+ specialties (high quality)
    high_quality = sum(
        1 for p in ALL_EXTENDED_PERSONAS.values()
        if isinstance(p.get('specialties'), list) and len(p['specialties']) >= 60
    )

    # Count personas with enhanced flag
    enhanced_count = sum(
        1 for p in ALL_EXTENDED_PERSONAS.values()
        if p.get('enhanced', False)
    )

    return {
        'total_personas': len(ALL_EXTENDED_PERSONAS),
        'tier1_personas': tier1_count,
        'tier1_loaded': enhanced_count,
        'high_quality_personas': high_quality,
        'tier1_keys': tier1_keys
    }


# Auto-load enhanced personas when module is imported
def initialize_enhanced_personas():
    """
    Automatically load and integrate enhanced personas
    This function is called when the module is imported
    """
    try:
        enhanced = load_all_enhanced_personas()
        logger.info(f"Loaded {len(enhanced)} enhanced Tier 1 personas")

        # Store in module-level variable for access
        global ENHANCED_PERSONAS
        ENHANCED_PERSONAS = enhanced

        return enhanced
    except Exception as e:
        logger.error(f"Failed to initialize enhanced personas: {e}")
        return {}


# Initialize on import
ENHANCED_PERSONAS = {}

if __name__ == "__main__":
    # Test loading
    logging.basicConfig(level=logging.INFO)

    print("\n" + "="*60)
    print("Testing Enhanced Personas Loader")
    print("="*60 + "\n")

    # Load enhanced personas
    enhanced = load_all_enhanced_personas()
    print(f"\n✓ Loaded {len(enhanced)} enhanced personas:")

    for key, persona in enhanced.items():
        print(f"\n{key}:")
        print(f"  Name: {persona['identity']['name']}")
        print(f"  Role: {persona['identity']['role']}")
        print(f"  Specialties: {len(persona['specialties'])}")
        print(f"  Level: {persona['level']}")
        print(f"  Tier: {persona.get('tier', 'N/A')}")

    # Get stats
    print("\n" + "="*60)
    print("Persona Statistics")
    print("="*60 + "\n")

    stats = get_persona_stats()
    print(f"Total personas: {stats['total_personas']}")
    print(f"Tier 1 files: {stats['tier1_personas']}")
    print(f"Tier 1 loaded: {stats['tier1_loaded']}")
    print(f"High quality (60+ specialties): {stats['high_quality_personas']}")
    print(f"\nTier 1 keys: {', '.join(stats['tier1_keys'])}")
