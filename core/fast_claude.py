#!/usr/bin/env python3
"""
FastClaude - Implementación optimizada para inicio rápido
Solo carga lo esencial, usa lazy loading para todo lo demás
"""

import os
import sys
from typing import Optional

class FastClaude:
    """Versión ultrarrápida de NubemClaude"""

    def __init__(self):
        self.api_key = None
        self._load_minimal_config()

    def _load_minimal_config(self):
        """Carga solo la configuración esencial"""
        # Intentar cargar API key de variable de entorno
        self.api_key = (
            os.getenv('ANTHROPIC_API_KEY') or
            os.getenv('CLAUDE_API_KEY') or
            os.getenv('OPENAI_API_KEY')
        )

        if not self.api_key:
            # Fallback a cache local
            cache_file = os.path.expanduser('~/.secrets-cache-nubemsecrets')
            if os.path.exists(cache_file):
                self._load_from_cache(cache_file)

    def _load_from_cache(self, cache_file):
        """Carga rápida desde cache"""
        try:
            with open(cache_file, 'r') as f:
                for line in f:
                    if 'ANTHROPIC_API_KEY=' in line or 'CLAUDE_API_KEY=' in line:
                        self.api_key = line.split('=', 1)[1].strip().strip('"')
                        break
        except:
            pass

    def execute(self, query: str) -> Optional[str]:
        """Ejecuta query con mínima latencia"""
        if not query:
            print("Por favor proporciona una pregunta")
            return None

        # Modo ultra-rápido: solo Claude directo si está disponible
        if self.api_key and self.api_key.startswith('sk-ant'):
            return self._execute_anthropic_direct(query)
        elif self.api_key and self.api_key.startswith('sk-'):
            return self._execute_openai_direct(query)
        else:
            return self._execute_fallback(query)

    def _execute_anthropic_direct(self, query: str) -> str:
        """Llamada directa a Anthropic API"""
        try:
            # Lazy import solo cuando se necesita
            from anthropic import Anthropic

            client = Anthropic(api_key=self.api_key)

            response = client.messages.create(
                model="claude-3-5-sonnet-latest",
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": query}]
            )

            result = response.content[0].text if response.content else "Sin respuesta"
            print(result)
            return result

        except ImportError:
            print("⚠️ Anthropic no instalado. Instala con: pip install anthropic")
            return None
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return None

    def _execute_openai_direct(self, query: str) -> str:
        """Llamada directa a OpenAI API"""
        try:
            # Lazy import
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": query}],
                max_tokens=1000,
                temperature=0
            )

            result = response.choices[0].message.content
            print(result)
            return result

        except ImportError:
            print("⚠️ OpenAI no instalado. Instala con: pip install openai")
            return None
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            return None

    def _execute_fallback(self, query: str) -> str:
        """Modo fallback sin APIs"""
        print("⚠️ No hay API keys configuradas")
        print("Configura una de estas variables de entorno:")
        print("  - ANTHROPIC_API_KEY")
        print("  - OPENAI_API_KEY")
        print("")
        print("O ejecuta el setup completo con: nubemclaude setup")
        return None


class FastClaudeInteractive(FastClaude):
    """Versión interactiva con modo chat"""

    def start_chat(self):
        """Inicia chat interactivo optimizado"""
        print("🚀 NubemClaude Fast - Modo Chat")
        print("Escribe 'exit' para salir")
        print("-" * 40)

        while True:
            try:
                query = input("\n> ").strip()

                if query.lower() in ['exit', 'quit', 'salir']:
                    print("👋 ¡Hasta luego!")
                    break

                if query:
                    self.execute(query)

            except KeyboardInterrupt:
                print("\n👋 ¡Hasta luego!")
                break
            except Exception as e:
                print(f"Error: {e}")


# Ejecución directa para testing
if __name__ == "__main__":
    import sys

    fc = FastClaude()

    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
        fc.execute(query)
    else:
        # Modo interactivo
        fci = FastClaudeInteractive()
        fci.start_chat()