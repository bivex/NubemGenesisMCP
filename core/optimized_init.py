#!/usr/bin/env python3
"""
NubemSuperFClaude - Optimized Initialization
Carga eficiente de recursos y configuración
"""

import os
import sys
import logging
from pathlib import Path
from functools import lru_cache

# Configurar logging mínimo
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Suprimir warnings innecesarios
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# Suprimir warnings de bibliotecas específicas
import warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=DeprecationWarning)

# Cache global para configuración
_config_cache = {}
_secrets_loaded = False


@lru_cache(maxsize=1)
def get_nubem_dir():
    """Obtener directorio base del proyecto"""
    return Path.home() / "NubemSuperFClaude"


@lru_cache(maxsize=1)
def load_environment():
    """Cargar variables de entorno una sola vez"""
    global _secrets_loaded

    if _secrets_loaded:
        return True

    nubem_dir = get_nubem_dir()

    # Cargar .env si existe
    env_file = nubem_dir / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)

    # Cargar cache de secretos local
    secrets_cache = Path.home() / ".secrets-cache-nubemsecrets"
    if secrets_cache.exists():
        try:
            with open(secrets_cache) as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        if 'export ' in line:
                            line = line.replace('export ', '')
                        if '=' in line:
                            key, value = line.strip().split('=', 1)
                            # Solo establecer si no existe
                            if not os.getenv(key):
                                os.environ[key] = value.strip('"').strip("'")
        except Exception as e:
            if os.getenv('NC_DEBUG') == 'true':
                logger.warning(f"Error loading secrets cache: {e}")

    _secrets_loaded = True
    return True


@lru_cache(maxsize=1)
def get_config():
    """Obtener configuración centralizada"""
    global _config_cache

    if _config_cache:
        return _config_cache

    # Cargar ambiente primero
    load_environment()

    config = {
        'debug': os.getenv('NC_DEBUG', 'false').lower() == 'true',
        'qdrant_disabled': os.getenv('QDRANT_DISABLED', 'false').lower() == 'true',
        'api_port': int(os.getenv('API_PORT', '8000')),
        'log_level': os.getenv('LOG_LEVEL', 'WARNING'),
        'project_id': os.getenv('SECRET_MANAGER_PROJECT', 'nubemsecrets'),
        'use_cache': os.getenv('USE_CACHE', 'true').lower() == 'true',
        'max_workers': int(os.getenv('MAX_WORKERS', '4')),
    }

    _config_cache = config
    return config


def init_logging(debug=None):
    """Configurar logging optimizado"""
    config = get_config()
    debug = debug if debug is not None else config['debug']

    level = logging.DEBUG if debug else logging.WARNING

    # Configurar formato simple
    format_str = '%(message)s' if not debug else '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    logging.basicConfig(
        level=level,
        format=format_str,
        force=True
    )

    # Silenciar logs ruidosos
    if not debug:
        for logger_name in ['urllib3', 'google', 'grpc', 'tensorflow', 'absl']:
            logging.getLogger(logger_name).setLevel(logging.ERROR)


def check_dependencies():
    """Verificar dependencias críticas (con cache)"""

    @lru_cache(maxsize=1)
    def _check():
        missing = []

        critical_packages = [
            'anthropic',
            'openai',
            'fastapi',
            'pydantic'
        ]

        for package in critical_packages:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)

        if missing and os.getenv('NC_DEBUG') == 'true':
            logger.warning(f"Paquetes faltantes: {', '.join(missing)}")
            logger.info("Instala con: pip install " + ' '.join(missing))

        return len(missing) == 0

    return _check()


def quick_init():
    """Inicialización rápida para uso normal"""
    load_environment()
    init_logging()
    return get_config()


if __name__ == "__main__":
    # Test de inicialización
    config = quick_init()
    print("✅ Inicialización optimizada completada")
    if config['debug']:
        print(f"📋 Configuración: {config}")