#!/usr/bin/env python3
"""
Personas Handler - Manages AI Personas for NubemClaude
"""

import os
import json
from typing import Dict, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class PersonasHandler:
    """Handle AI Personas listing and management"""
    
    def __init__(self):
        self.personas_dir = Path(__file__).parent.parent / "personas"
        self.personas = {}
        self.load_personas()
    
    def load_personas(self):
        """Load all available personas from files"""
        try:
            # Load from personas directory
            if self.personas_dir.exists():
                for persona_file in self.personas_dir.glob("*.json"):
                    try:
                        with open(persona_file, 'r', encoding='utf-8') as f:
                            persona_data = json.load(f)
                            persona_name = persona_file.stem
                            self.personas[persona_name] = persona_data
                            logger.debug(f"Loaded persona: {persona_name}")
                    except Exception as e:
                        logger.error(f"Error loading persona {persona_file}: {e}")
            
            # Try to load from unified personas
            try:
                from core.personas_unified import UnifiedPersonaManager
                manager = UnifiedPersonaManager()
                
                # Add personas from unified manager
                for category, persona_ids in manager.persona_categories.items():
                    for persona_id in persona_ids:
                        persona = manager.get_persona(persona_id)
                        if persona:
                            # Handle both dict and object formats
                            if isinstance(persona, dict):
                                self.personas[persona_id] = {
                                    "name": persona.get('name', persona_id),
                                    "category": category,
                                    "description": persona.get('description', ''),
                                    "capabilities": persona.get('capabilities', []),
                                    "tags": persona.get('tags', [])
                                }
                            else:
                                self.personas[persona_id] = {
                                    "name": getattr(persona, 'name', persona_id),
                                    "category": category,
                                    "description": getattr(persona, 'description', ''),
                                    "capabilities": getattr(persona, 'capabilities', []),
                                    "tags": getattr(persona, 'tags', [])
                                }
                
                logger.info(f"Loaded {len(self.personas)} personas total")
            except Exception as e:
                logger.debug(f"Could not load unified personas: {e}")
                
        except Exception as e:
            logger.error(f"Error loading personas: {e}")
    
    def list_all_personas(self) -> str:
        """List all available AI personas with details"""
        output = ["🤖 **PERSONAS IA DISPONIBLES EN NUBEMCLAUDE**\n"]
        output.append("=" * 60)
        
        # Group by category
        categories = {}
        for persona_id, persona_data in self.personas.items():
            category = persona_data.get('category', 'general')
            if category not in categories:
                categories[category] = []
            categories[category].append((persona_id, persona_data))
        
        # Display by category
        total_count = 0
        for category in sorted(categories.keys()):
            personas_in_cat = categories[category]
            output.append(f"\n📁 **{category.upper()}** ({len(personas_in_cat)} personas)")
            output.append("-" * 40)
            
            for persona_id, persona_data in sorted(personas_in_cat, key=lambda x: x[0]):
                total_count += 1
                name = persona_data.get('name', persona_id)
                desc = persona_data.get('description', 'Sin descripción')
                
                # Truncate description if too long
                if len(desc) > 60:
                    desc = desc[:57] + "..."
                
                output.append(f"{total_count:2}. 👤 **{name}** (`{persona_id}`)")
                output.append(f"    📝 {desc}")
                
                # Show capabilities if available
                caps = persona_data.get('capabilities', [])
                if caps and isinstance(caps, list):
                    caps_str = ", ".join(caps[:3])  # Show first 3 capabilities
                    if len(caps) > 3:
                        caps_str += f" +{len(caps)-3} más"
                    output.append(f"    💡 {caps_str}")
        
        output.append("\n" + "=" * 60)
        output.append(f"📊 **TOTAL: {total_count} Personas IA disponibles**")
        
        # Add usage instructions
        output.append("\n💡 **USO:**")
        output.append("• Para activar una persona: `activar persona [nombre]`")
        output.append("• Para ver detalles: `info persona [nombre]`")
        output.append("• Para orquestar: `orchestrate [tarea]`")
        
        return "\n".join(output)
    
    def get_persona_info(self, persona_id: str) -> str:
        """Get detailed information about a specific persona"""
        if persona_id not in self.personas:
            # Try case-insensitive search
            for pid, pdata in self.personas.items():
                if pid.lower() == persona_id.lower():
                    persona_id = pid
                    break
            else:
                return f"❌ Persona '{persona_id}' no encontrada"
        
        persona = self.personas[persona_id]
        output = [f"👤 **INFORMACIÓN DE PERSONA: {persona.get('name', persona_id)}**\n"]
        output.append("=" * 50)
        
        output.append(f"**ID:** `{persona_id}`")
        output.append(f"**Categoría:** {persona.get('category', 'general')}")
        output.append(f"**Descripción:** {persona.get('description', 'Sin descripción')}")
        
        if persona.get('capabilities'):
            output.append("\n**Capacidades:**")
            for cap in persona['capabilities']:
                output.append(f"  • {cap}")
        
        if persona.get('tags'):
            output.append(f"\n**Tags:** {', '.join(persona['tags'])}")
        
        if persona.get('tools'):
            output.append(f"\n**Herramientas:** {', '.join(persona['tools'])}")
        
        return "\n".join(output)


# Global instance
personas_handler = PersonasHandler()


def handle_personas_command(query: str) -> str:
    """Handle personas-related commands"""
    query_lower = query.lower()
    
    # List all personas
    if any(word in query_lower for word in ['lista', 'listar', 'todos', 'todas', 'perfiles', 'personas']):
        if 'persona' in query_lower or 'perfiles' in query_lower:
            return personas_handler.list_all_personas()
    
    # Get specific persona info
    if 'info' in query_lower or 'información' in query_lower:
        import re
        match = re.search(r'persona\s+([a-zA-Z0-9_-]+)', query_lower)
        if match:
            persona_id = match.group(1)
            return personas_handler.get_persona_info(persona_id)
    
    # Activate persona
    if 'activar' in query_lower or 'activate' in query_lower:
        import re
        match = re.search(r'persona\s+([a-zA-Z0-9_-]+)', query_lower)
        if match:
            persona_id = match.group(1)
            return f"Para activar la persona '{persona_id}', usa el comando: `activate {persona_id}`"
    
    return None


if __name__ == "__main__":
    # Test the handler
    handler = PersonasHandler()
    print(handler.list_all_personas())