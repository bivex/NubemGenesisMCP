"""Pytest configuration for performance tests"""

import sys
from unittest.mock import MagicMock

# Mock Google OAuth modules before any imports
google_mock = MagicMock()
sys.modules['google_auth_oauthlib'] = google_mock
sys.modules['google_auth_oauthlib.flow'] = MagicMock()
sys.modules['google'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.id_token'] = MagicMock()
sys.modules['google.auth'] = MagicMock()
sys.modules['google.auth.transport'] = MagicMock()
sys.modules['google.auth.transport.requests'] = MagicMock()
