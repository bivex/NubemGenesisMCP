"""
Input validation for NubemSuperFClaude
Comprehensive validation with security best practices
"""

import re
import logging
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class ValidationLevel(Enum):
    """Validation strictness levels"""
    STRICT = "strict"      # Reject any suspicious input
    NORMAL = "normal"      # Standard validation
    PERMISSIVE = "permissive"  # Allow more flexibility


@dataclass
class ValidationRule:
    """Defines a validation rule"""
    name: str
    pattern: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_chars: Optional[str] = None
    forbidden_patterns: Optional[List[str]] = None
    custom_validator: Optional[callable] = None


class InputValidator:
    """
    Comprehensive input validation
    Implements security best practices from OWASP
    """
    
    # Common attack patterns to block
    INJECTION_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',  # JavaScript protocol
        r'on\w+\s*=',  # Event handlers
        r'[\';].*--',  # SQL comment
        r'union.*select',  # SQL injection
        r'exec\s*\(',  # Command execution
        r'eval\s*\(',  # Code evaluation
        r'\.\./|\.\.\\',  # Path traversal
        r'%2e%2e[/\\]',  # Encoded path traversal
        r'[<>]',  # HTML tags (basic)
    ]
    
    # Safe patterns for common inputs
    SAFE_PATTERNS = {
        'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
        'username': r'^[a-zA-Z0-9_-]{3,32}$',
        'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        'url': r'^https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        'alphanumeric': r'^[a-zA-Z0-9]+$',
        'numeric': r'^[0-9]+$',
        'path': r'^[a-zA-Z0-9/_.-]+$',
    }
    
    def __init__(self, level: ValidationLevel = ValidationLevel.NORMAL):
        self.level = level
        self.custom_rules: Dict[str, ValidationRule] = {}
        self.stats = {
            'validated': 0,
            'rejected': 0,
            'sanitized': 0
        }
    
    def validate_input(self, 
                       value: Any, 
                       input_type: str = 'text',
                       max_length: int = 10000,
                       required: bool = False) -> Any:
        """
        Main validation method
        
        Args:
            value: Input value to validate
            input_type: Type of input (text, email, username, etc.)
            max_length: Maximum allowed length
            required: Whether input is required
        
        Returns:
            Validated and sanitized input
        
        Raises:
            ValidationError: If validation fails
        """
        self.stats['validated'] += 1
        
        # Check if required
        if required and not value:
            raise ValidationError("Required input is missing")
        
        # Skip validation for None if not required
        if not required and value is None:
            return None
        
        # Convert to string for validation
        str_value = str(value) if value is not None else ''
        
        # Check length
        if len(str_value) > max_length:
            raise ValidationError(f"Input exceeds maximum length of {max_length}")
        
        # Check for injection attempts
        if self.level != ValidationLevel.PERMISSIVE:
            self._check_injection_patterns(str_value)
        
        # Type-specific validation
        validated = self._validate_by_type(str_value, input_type)
        
        # Sanitize if needed
        if self.level == ValidationLevel.STRICT:
            validated = self._sanitize(validated, input_type)
            if validated != str_value:
                self.stats['sanitized'] += 1
        
        return validated
    
    def _check_injection_patterns(self, value: str):
        """Check for common injection patterns"""
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                self.stats['rejected'] += 1
                raise ValidationError(f"Suspicious pattern detected: {pattern}")
    
    def _validate_by_type(self, value: str, input_type: str) -> str:
        """Validate based on input type"""
        
        # Check custom rules first
        if input_type in self.custom_rules:
            return self._apply_custom_rule(value, self.custom_rules[input_type])
        
        # Check predefined patterns
        if input_type in self.SAFE_PATTERNS:
            pattern = self.SAFE_PATTERNS[input_type]
            if not re.match(pattern, value):
                raise ValidationError(f"Invalid {input_type} format")
        
        # Type-specific validations
        if input_type == 'json':
            return self._validate_json(value)
        elif input_type == 'integer':
            return self._validate_integer(value)
        elif input_type == 'float':
            return self._validate_float(value)
        elif input_type == 'boolean':
            return self._validate_boolean(value)
        elif input_type == 'list':
            return self._validate_list(value)
        elif input_type == 'dict':
            return self._validate_dict(value)
        
        return value
    
    def _validate_json(self, value: str) -> str:
        """Validate JSON input"""
        try:
            json.loads(value)
            return value
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def _validate_integer(self, value: str) -> int:
        """Validate integer input"""
        try:
            return int(value)
        except ValueError:
            raise ValidationError(f"Invalid integer: {value}")
    
    def _validate_float(self, value: str) -> float:
        """Validate float input"""
        try:
            return float(value)
        except ValueError:
            raise ValidationError(f"Invalid float: {value}")
    
    def _validate_boolean(self, value: str) -> bool:
        """Validate boolean input"""
        if value.lower() in ['true', '1', 'yes', 'on']:
            return True
        elif value.lower() in ['false', '0', 'no', 'off']:
            return False
        else:
            raise ValidationError(f"Invalid boolean: {value}")
    
    def _validate_list(self, value: str) -> List:
        """Validate list input"""
        try:
            if value.startswith('['):
                return json.loads(value)
            else:
                return value.split(',')
        except Exception as e:
            raise ValidationError(f"Invalid list: {e}")
    
    def _validate_dict(self, value: str) -> Dict:
        """Validate dictionary input"""
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid dictionary: {e}")
    
    def _sanitize(self, value: Any, input_type: str) -> Any:
        """Sanitize input based on type"""
        if isinstance(value, str):
            # Remove control characters
            value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)
            
            # HTML encode if text
            if input_type == 'text':
                value = self._html_encode(value)
            
            # Remove extra whitespace
            value = ' '.join(value.split())
        
        return value
    
    def _html_encode(self, text: str) -> str:
        """HTML encode special characters"""
        replacements = {
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#x27;',
            '&': '&amp;',
            '/': '&#x2F;'
        }
        
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        
        return text
    
    def _apply_custom_rule(self, value: str, rule: ValidationRule) -> str:
        """Apply custom validation rule"""
        
        # Check pattern
        if rule.pattern and not re.match(rule.pattern, value):
            raise ValidationError(f"Value doesn't match pattern for {rule.name}")
        
        # Check length
        if rule.min_length and len(value) < rule.min_length:
            raise ValidationError(f"Value too short for {rule.name}")
        
        if rule.max_length and len(value) > rule.max_length:
            raise ValidationError(f"Value too long for {rule.name}")
        
        # Check allowed characters
        if rule.allowed_chars:
            for char in value:
                if char not in rule.allowed_chars:
                    raise ValidationError(f"Invalid character '{char}' for {rule.name}")
        
        # Check forbidden patterns
        if rule.forbidden_patterns:
            for pattern in rule.forbidden_patterns:
                if re.search(pattern, value):
                    raise ValidationError(f"Forbidden pattern found in {rule.name}")
        
        # Apply custom validator
        if rule.custom_validator:
            if not rule.custom_validator(value):
                raise ValidationError(f"Custom validation failed for {rule.name}")
        
        return value
    
    def add_custom_rule(self, name: str, rule: ValidationRule):
        """Add custom validation rule"""
        rule.name = name
        self.custom_rules[name] = rule
    
    def validate_batch(self, inputs: Dict[str, Any], 
                       schema: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Validate multiple inputs against a schema
        
        Args:
            inputs: Dictionary of input values
            schema: Validation schema
        
        Returns:
            Dictionary of validated values
        """
        validated = {}
        errors = []
        
        for field, rules in schema.items():
            try:
                value = inputs.get(field)
                validated[field] = self.validate_input(
                    value,
                    input_type=rules.get('type', 'text'),
                    max_length=rules.get('max_length', 10000),
                    required=rules.get('required', False)
                )
            except ValidationError as e:
                errors.append(f"{field}: {e}")
        
        if errors:
            raise ValidationError(f"Validation failed: {'; '.join(errors)}")
        
        return validated
    
    def get_stats(self) -> Dict[str, int]:
        """Get validation statistics"""
        return self.stats.copy()


class FileValidator:
    """Validate file uploads and paths"""
    
    ALLOWED_EXTENSIONS = {
        'text': ['.txt', '.md', '.rst', '.log'],
        'data': ['.json', '.csv', '.xml', '.yaml'],
        'code': ['.py', '.js', '.java', '.cpp', '.go'],
        'image': ['.jpg', '.jpeg', '.png', '.gif', '.bmp'],
        'document': ['.pdf', '.doc', '.docx', '.odt']
    }
    
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    
    @classmethod
    def validate_file_path(cls, path: str, base_dir: str = None) -> Path:
        """
        Validate file path for security
        
        Args:
            path: File path to validate
            base_dir: Base directory to restrict access
        
        Returns:
            Validated Path object
        """
        # Convert to Path object
        file_path = Path(path).resolve()
        
        # Check for path traversal
        if '..' in str(file_path):
            raise ValidationError("Path traversal detected")
        
        # Check if within base directory
        if base_dir:
            base = Path(base_dir).resolve()
            if not str(file_path).startswith(str(base)):
                raise ValidationError("Path outside allowed directory")
        
        return file_path
    
    @classmethod
    def validate_file_extension(cls, filename: str, 
                               category: str = None) -> bool:
        """Validate file extension"""
        ext = Path(filename).suffix.lower()
        
        if category:
            allowed = cls.ALLOWED_EXTENSIONS.get(category, [])
            if ext not in allowed:
                raise ValidationError(f"File type {ext} not allowed for {category}")
        else:
            # Check against all allowed extensions
            all_extensions = sum(cls.ALLOWED_EXTENSIONS.values(), [])
            if ext not in all_extensions:
                raise ValidationError(f"File type {ext} not allowed")
        
        return True
    
    @classmethod
    def validate_file_size(cls, size: int) -> bool:
        """Validate file size"""
        if size > cls.MAX_FILE_SIZE:
            raise ValidationError(f"File size exceeds maximum of {cls.MAX_FILE_SIZE} bytes")
        return True


# Global validator instance
_validator = InputValidator()


def validate(value: Any, **kwargs) -> Any:
    """Convenience function for validation"""
    return _validator.validate_input(value, **kwargs)


def validate_batch(inputs: Dict, schema: Dict) -> Dict:
    """Convenience function for batch validation"""
    return _validator.validate_batch(inputs, schema)


if __name__ == "__main__":
    # Test validation
    print("🔒 Testing Input Validation")
    print("=" * 50)
    
    validator = InputValidator(ValidationLevel.STRICT)
    
    # Test cases
    test_cases = [
        ("user@example.com", "email", True),
        ("john_doe", "username", True),
        ("<script>alert('xss')</script>", "text", False),
        ("../../etc/passwd", "path", False),
        ("123", "integer", True),
        ("SELECT * FROM users", "text", False),
    ]
    
    for value, input_type, should_pass in test_cases:
        try:
            result = validator.validate_input(value, input_type)
            status = "✅ PASS" if should_pass else "❌ FAIL (should have been rejected)"
            print(f"{status}: {value[:30]}... as {input_type}")
        except ValidationError as e:
            status = "❌ REJECTED" if not should_pass else "❌ FAIL (should have passed)"
            print(f"{status}: {value[:30]}... - {e}")
    
    print(f"\n📊 Stats: {validator.get_stats()}")