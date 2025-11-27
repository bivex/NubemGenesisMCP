#!/usr/bin/env python3
"""
Safe JSON serialization utilities to replace pickle usage
"""

import json
import base64
from typing import Any, Optional
from datetime import datetime, date
import numpy as np


class SafeJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles complex types safely"""
    
    def default(self, obj):
        # Handle datetime objects
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        
        # Handle numpy arrays
        if isinstance(obj, np.ndarray):
            return {
                "_type": "ndarray",
                "data": obj.tolist(),
                "dtype": str(obj.dtype)
            }
        
        # Handle bytes
        if isinstance(obj, bytes):
            return {
                "_type": "bytes",
                "data": base64.b64encode(obj).decode('utf-8')
            }
        
        # Handle sets
        if isinstance(obj, set):
            return {
                "_type": "set",
                "data": list(obj)
            }
        
        # Try to convert to dict if has __dict__
        if hasattr(obj, '__dict__'):
            return {
                "_type": "object",
                "class": obj.__class__.__name__,
                "data": obj.__dict__
            }
        
        return super().default(obj)


def safe_dumps(obj: Any) -> str:
    """Safely serialize object to JSON string"""
    return json.dumps(obj, cls=SafeJSONEncoder, ensure_ascii=False)


def safe_loads(json_str: str) -> Any:
    """Safely deserialize JSON string to object"""
    def object_hook(dct):
        if "_type" in dct:
            if dct["_type"] == "ndarray":
                return np.array(dct["data"], dtype=dct["dtype"])
            elif dct["_type"] == "bytes":
                return base64.b64decode(dct["data"])
            elif dct["_type"] == "set":
                return set(dct["data"])
            elif dct["_type"] == "object":
                # For simple objects, return the data dict
                # In production, you might want to reconstruct the actual object
                return dct["data"]
        return dct
    
    return json.loads(json_str, object_hook=object_hook)


def safe_dumps_bytes(obj: Any) -> bytes:
    """Safely serialize object to bytes"""
    return safe_dumps(obj).encode('utf-8')


def safe_loads_bytes(data: bytes) -> Any:
    """Safely deserialize bytes to object"""
    return safe_loads(data.decode('utf-8'))