"""
Auto-Scaling for Personas based on demand
"""

import threading
import time
from collections import defaultdict
from typing import Dict, Any

class PersonaAutoScaler:
    """Automatically scale persona instances based on demand"""
    
    def __init__(self, max_instances_per_persona: int = 5):
        self.persona_instances = defaultdict(list)
        self.persona_load = defaultdict(int)
        self.max_instances = max_instances_per_persona
        self.scaling_threshold = 0.8  # 80% load triggers scaling
        self.lock = threading.Lock()
        
    def get_available_instance(self, persona_type: str):
        """Get an available instance of a persona"""
        with self.lock:
            if persona_type not in self.persona_instances or not self.persona_instances[persona_type]:
                self.spawn_persona_instance(persona_type)
            
            # Find least loaded instance
            instances = self.persona_instances[persona_type]
            return min(instances, key=lambda x: x.get("load", 0))
    
    def spawn_persona_instance(self, persona_type: str):
        """Spawn a new persona instance"""
        with self.lock:
            if len(self.persona_instances[persona_type]) < self.max_instances:
                new_instance = {
                    "id": f"{persona_type}_{len(self.persona_instances[persona_type])}",
                    "type": persona_type,
                    "load": 0,
                    "created_at": time.time()
                }
                self.persona_instances[persona_type].append(new_instance)
                return new_instance
    
    def scale_personas_by_demand(self):
        """Check and scale personas based on current demand"""
        with self.lock:
            for persona_type, instances in self.persona_instances.items():
                if not instances:
                    continue
                
                avg_load = sum(inst["load"] for inst in instances) / len(instances)
                
                if avg_load > self.scaling_threshold:
                    self.spawn_persona_instance(persona_type)
                elif avg_load < 0.2 and len(instances) > 1:
                    # Scale down if load is low
                    self.persona_instances[persona_type].pop()
    
    def update_load(self, persona_type: str, instance_id: str, load_delta: float):
        """Update the load for a specific persona instance"""
        with self.lock:
            for instance in self.persona_instances[persona_type]:
                if instance["id"] == instance_id:
                    instance["load"] = max(0, min(1, instance["load"] + load_delta))