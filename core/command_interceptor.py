#!/usr/bin/env python3
"""
Command Interceptor - Pre-processes commands before sending to LLM
Handles special commands like GitHub operations
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

class CommandInterceptor:
    """Intercept and handle special commands"""
    
    def __init__(self):
        self.handlers = {}
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all command handlers"""
        try:
            # Register GitHub handler
            from core.github_handler import handle_github_command
            self.handlers['github'] = handle_github_command
            logger.info("✅ GitHub handler registered")
        except Exception as e:
            logger.warning(f"Could not register GitHub handler: {e}")
        
        try:
            # Register Personas handler
            from core.personas_handler import handle_personas_command
            self.handlers['personas'] = handle_personas_command
            logger.info("✅ Personas handler registered")
        except Exception as e:
            logger.warning(f"Could not register Personas handler: {e}")
    
    def intercept(self, query: str) -> Optional[str]:
        """
        Intercept query and handle if it's a special command
        Returns response if handled, None otherwise
        """
        query_lower = query.lower()
        
        # Check for personas commands (HIGH PRIORITY)
        personas_keywords = [
            'personas', 'perfiles', 'persona ia', 'lista.*persona',
            'todos los perfiles', 'activar persona', 'info persona'
        ]
        
        for keyword in personas_keywords:
            if keyword in query_lower:
                logger.info(f"Intercepted Personas command: {query[:50]}...")
                if 'personas' in self.handlers:
                    try:
                        result = self.handlers['personas'](query)
                        if result:
                            return result
                    except Exception as e:
                        logger.error(f"Personas handler error: {e}")
                break
        
        # Check for repository visibility change commands (HIGH PRIORITY)
        if ('cambia' in query_lower or 'cambiar' in query_lower or 'convertir' in query_lower) and \
           ('privado' in query_lower or 'privados' in query_lower or 'publico' in query_lower or 'público' in query_lower):
            logger.info(f"Intercepted visibility change command: {query[:50]}...")
            if 'github' in self.handlers:
                try:
                    result = self.handlers['github'](query)
                    if result:
                        return result
                except Exception as e:
                    logger.error(f"GitHub handler error: {e}")
        
        # Check GitHub commands
        github_keywords = [
            'github', 'repositorio', 'repos',
            'conecta con github', 'lista.*repositorio',
            'revisa.*github', 'muestra.*repos'
        ]
        
        for keyword in github_keywords:
            if keyword in query_lower:
                logger.info(f"Intercepted GitHub command: {query[:50]}...")
                if 'github' in self.handlers:
                    try:
                        result = self.handlers['github'](query)
                        if result:
                            return result
                    except Exception as e:
                        logger.error(f"GitHub handler error: {e}")
                break
        
        # Add more command checks here in the future
        
        return None
    
    def process_query(self, query: str) -> tuple[bool, Optional[str]]:
        """
        Process a query and return (handled, response)
        If handled is True, response contains the result
        If handled is False, query should be sent to LLM
        """
        result = self.intercept(query)
        if result:
            return True, result
        return False, None


# Global instance
command_interceptor = CommandInterceptor()


def preprocess_query(query: str) -> tuple[bool, Optional[str]]:
    """
    Global function to preprocess queries
    Returns (handled, response)
    """
    return command_interceptor.process_query(query)