#!/usr/bin/env python3
"""
Enhanced Claude Code Integration
Implementa patrones de autenticación multi-método basados en análisis de frameworks
"""

import subprocess
import sys
import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncIterator
from dataclasses import dataclass

@dataclass
class AuthenticationResult:
    success: bool
    method: str
    response: Optional[str] = None
    error: Optional[str] = None

class EnhancedClaudeIntegration:
    """
    Integración mejorada con Claude Code CLI usando patrones de frameworks líderes

    Características:
    - Autenticación multi-método con fallbacks
    - Detección inteligente de configuración
    - Manejo robusto de errores
    - Timeout y circuit breaker patterns
    """

    def __init__(self, debug: bool = False):
        self.debug = debug
        self.logger = self._setup_logging()
        self.auth_methods = [
            'claude_subscription',    # Método preferido
            'claude_api_key',        # Con flag --api-key
            'anthropic_api_key',     # Variable de entorno
            'fallback_wrapper'       # Último recurso
        ]
        self.timeout_short = 10
        self.timeout_long = 60

    def _setup_logging(self) -> logging.Logger:
        """Configurar logging si debug está habilitado"""
        logger = logging.getLogger('enhanced_claude')
        if self.debug:
            logger.setLevel(logging.DEBUG)
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def check_claude_availability(self) -> bool:
        """Verificar si Claude Code CLI está disponible"""
        try:
            result = subprocess.run(
                ['claude', '--version'],
                capture_output=True,
                text=True,
                timeout=self.timeout_short
            )
            available = result.returncode == 0
            self.logger.debug(f"Claude CLI availability: {available}")
            return available
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.debug(f"Claude CLI not available: {e}")
            return False

    def test_authentication(self) -> AuthenticationResult:
        """Probar la autenticación actual de Claude Code"""
        if not self.check_claude_availability():
            return AuthenticationResult(
                success=False,
                method="none",
                error="Claude CLI not available"
            )

        try:
            # Test con comando simple
            test_result = subprocess.run(
                ['claude', '-p'],
                input='Hello',
                capture_output=True,
                text=True,
                timeout=self.timeout_short
            )

            success = (test_result.returncode == 0 and
                      'authentication' not in test_result.stderr.lower() and
                      'invalid' not in test_result.stderr.lower())

            if success:
                return AuthenticationResult(
                    success=True,
                    method="claude_subscription",
                    response=test_result.stdout[:100]
                )
            else:
                return AuthenticationResult(
                    success=False,
                    method="claude_subscription",
                    error=test_result.stderr
                )

        except subprocess.TimeoutExpired:
            return AuthenticationResult(
                success=False,
                method="claude_subscription",
                error="Authentication test timeout"
            )
        except Exception as e:
            return AuthenticationResult(
                success=False,
                method="claude_subscription",
                error=str(e)
            )

    def authenticate_and_execute(self, query: str) -> str:
        """
        Ejecutar query con autenticación multi-método

        Implementa el patrón de fallback chain usado en frameworks líderes
        """
        self.logger.debug(f"Executing query: {query[:50]}...")

        if not self.check_claude_availability():
            return self._fallback_wrapper(query)

        # Método 1: Claude Code subscription (preferido)
        try:
            auth_test = self.test_authentication()
            if auth_test.success:
                self.logger.debug("Using Claude subscription method")
                result = subprocess.run(
                    ['claude', '-p'],
                    input=query,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_long
                )

                if result.returncode == 0:
                    return result.stdout.strip()
                else:
                    self.logger.debug(f"Claude subscription failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            self.logger.debug("Claude subscription timeout")
        except Exception as e:
            self.logger.debug(f"Claude subscription error: {e}")

        # Método 2: API key desde variable de entorno
        if os.getenv('ANTHROPIC_API_KEY'):
            try:
                self.logger.debug("Trying with ANTHROPIC_API_KEY")
                result = subprocess.run(
                    ['claude', '--api-key', os.getenv('ANTHROPIC_API_KEY'), '-p'],
                    input=query,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_long
                )

                if result.returncode == 0:
                    return result.stdout.strip()
                else:
                    self.logger.debug(f"API key method failed: {result.stderr}")

            except Exception as e:
                self.logger.debug(f"API key method error: {e}")

        # Método 3: Buscar API key en archivos de configuración
        api_key = self._find_api_key_in_config()
        if api_key:
            try:
                self.logger.debug("Trying with found API key")
                result = subprocess.run(
                    ['claude', '--api-key', api_key, '-p'],
                    input=query,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_long
                )

                if result.returncode == 0:
                    return result.stdout.strip()

            except Exception as e:
                self.logger.debug(f"Found API key method error: {e}")

        # Método 4: Fallback con instrucciones
        return self._fallback_wrapper(query)

    def _find_api_key_in_config(self) -> Optional[str]:
        """Buscar API key en archivos de configuración comunes"""
        possible_locations = [
            Path.home() / '.claude' / 'config.json',
            Path.home() / '.anthropic' / 'config.json',
            Path.home() / '.config' / 'anthropic' / 'config.json',
            Path('.env'),
            Path('.env.local')
        ]

        for config_path in possible_locations:
            if config_path.exists():
                try:
                    if config_path.suffix == '.json':
                        with open(config_path) as f:
                            config = json.load(f)
                            if 'api_key' in config:
                                return config['api_key']
                            if 'anthropic_api_key' in config:
                                return config['anthropic_api_key']
                    else:
                        # Archivo .env
                        with open(config_path) as f:
                            for line in f:
                                if 'ANTHROPIC_API_KEY=' in line:
                                    return line.split('=', 1)[1].strip().strip('"\'')
                except Exception as e:
                    self.logger.debug(f"Error reading {config_path}: {e}")

        return None

    def _fallback_wrapper(self, query: str) -> str:
        """Mensaje de fallback con instrucciones claras"""
        return f"""🔧 Claude Code requiere configuración de autenticación

Consulta enviada: {query[:100] + '...' if len(query) > 100 else query}

⚡ Para configurar Claude Code correctamente:

1. 📱 Ejecuta en una terminal nueva: claude setup-token
2. 🌐 Se abrirá tu navegador para login
3. ✅ Inicia sesión con tu cuenta Claude Pro/Max
4. 🔒 Autoriza la aplicación
5. ✨ ¡Listo! Claude Code funcionará completamente

📋 Alternativa: Ejecuta claude-setup-helper para instrucciones detalladas

🚀 Una vez configurado, tendrás acceso completo a NubemSuperFClaude con Claude Code!

💡 Si ya tienes una API key, puedes exportarla:
   export ANTHROPIC_API_KEY="tu-api-key-aqui" """

    async def stream_execute(self, query: str) -> AsyncIterator[str]:
        """Ejecutar con streaming - para implementación futura"""
        # Placeholder para funcionalidad de streaming
        response = self.authenticate_and_execute(query)

        # Simular streaming dividiendo la respuesta
        words = response.split()
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.05)  # Simular delay

    def get_diagnostics(self) -> Dict[str, Any]:
        """Obtener información de diagnóstico del sistema"""
        diagnostics = {
            'claude_cli_available': self.check_claude_availability(),
            'auth_test': None,
            'environment_vars': {},
            'config_files': {}
        }

        # Test de autenticación
        if diagnostics['claude_cli_available']:
            auth_result = self.test_authentication()
            diagnostics['auth_test'] = {
                'success': auth_result.success,
                'method': auth_result.method,
                'error': auth_result.error
            }

        # Variables de entorno relevantes
        env_vars = ['ANTHROPIC_API_KEY', 'CLAUDE_API_KEY', 'OPENAI_API_KEY']
        for var in env_vars:
            value = os.getenv(var)
            diagnostics['environment_vars'][var] = 'set' if value else 'not_set'

        # Archivos de configuración
        config_files = [
            Path.home() / '.claude' / 'config.json',
            Path.home() / '.anthropic' / 'config.json',
            Path('.env')
        ]

        for config_file in config_files:
            diagnostics['config_files'][str(config_file)] = config_file.exists()

        return diagnostics

# Función de conveniencia para usar desde bash
def main():
    """Función principal para uso desde línea de comandos"""
    if len(sys.argv) < 2:
        print("Usage: python enhanced_claude_integration.py <query>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    debug = os.getenv('CLAUDE_DEBUG', 'false').lower() == 'true'

    integration = EnhancedClaudeIntegration(debug=debug)

    # Si el argumento es 'diagnostics', mostrar diagnósticos
    if query.lower() == 'diagnostics':
        diagnostics = integration.get_diagnostics()
        print(json.dumps(diagnostics, indent=2))
        return

    # Ejecutar query normal
    response = integration.authenticate_and_execute(query)
    print(response)

if __name__ == "__main__":
    main()