"""
Pytest configuration for device flow tests

Mocks external dependencies that might not be installed
"""

import sys
from unittest.mock import Mock, MagicMock

# Mock google_auth_oauthlib before any imports
if 'google_auth_oauthlib' not in sys.modules:
    google_auth_mock = MagicMock()
    google_auth_mock.flow = MagicMock()
    sys.modules['google_auth_oauthlib'] = google_auth_mock
    sys.modules['google_auth_oauthlib.flow'] = google_auth_mock.flow

# Mock google.oauth2
if 'google.oauth2' not in sys.modules:
    google_mock = MagicMock()
    google_mock.oauth2 = MagicMock()
    google_mock.oauth2.id_token = MagicMock()
    sys.modules['google'] = google_mock
    sys.modules['google.oauth2'] = google_mock.oauth2
    sys.modules['google.oauth2.id_token'] = google_mock.oauth2.id_token

# Mock google.auth
if 'google.auth.transport' not in sys.modules:
    google_auth_transport = MagicMock()
    sys.modules['google.auth'] = MagicMock()
    sys.modules['google.auth.transport'] = google_auth_transport
    sys.modules['google.auth.transport.requests'] = MagicMock()
