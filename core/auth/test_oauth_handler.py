"""
Unit tests for OAuth handler
"""

import os
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

# Set test environment
os.environ['GOOGLE_OAUTH_CLIENT_ID'] = 'test_client_id.apps.googleusercontent.com'
os.environ['GOOGLE_OAUTH_CLIENT_SECRET'] = 'test_client_secret'
os.environ['GOOGLE_OAUTH_REDIRECT_URI'] = 'http://localhost:8080/auth/google/callback'

from .oauth_handler import GoogleOAuthHandler


class TestGoogleOAuthHandler:
    """Test suite for GoogleOAuthHandler"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.handler = GoogleOAuthHandler(
            client_id='test_client_id.apps.googleusercontent.com',
            client_secret='test_client_secret',
            redirect_uri='http://localhost:8080/auth/google/callback',
            jwt_secret='test_jwt_secret_key_for_testing'
        )
    
    def test_initialization(self):
        """Test OAuth handler initialization"""
        assert self.handler.client_id == 'test_client_id.apps.googleusercontent.com'
        assert self.handler.client_secret == 'test_client_secret'
        assert self.handler.redirect_uri == 'http://localhost:8080/auth/google/callback'
        assert self.handler.is_configured() is True
    
    def test_initialization_without_config(self):
        """Test OAuth handler when not configured"""
        # Clear environment
        os.environ.pop('GOOGLE_OAUTH_CLIENT_ID', None)
        os.environ.pop('GOOGLE_OAUTH_CLIENT_SECRET', None)
        
        handler = GoogleOAuthHandler()
        assert handler.is_configured() is False
        
        # Restore environment
        os.environ['GOOGLE_OAUTH_CLIENT_ID'] = 'test_client_id.apps.googleusercontent.com'
        os.environ['GOOGLE_OAUTH_CLIENT_SECRET'] = 'test_client_secret'
    
    def test_generate_pkce_pair(self):
        """Test PKCE code verifier and challenge generation"""
        verifier, challenge = self.handler.generate_pkce_pair()
        
        assert len(verifier) > 43  # Minimum length for PKCE
        assert len(challenge) > 0
        assert verifier != challenge  # Should be different
        
        # Generate another pair - should be unique
        verifier2, challenge2 = self.handler.generate_pkce_pair()
        assert verifier != verifier2
        assert challenge != challenge2
    
    def test_get_authorization_url(self):
        """Test authorization URL generation"""
        result = self.handler.get_authorization_url()
        
        assert 'authorization_url' in result
        assert 'state' in result
        assert 'nonce' in result
        assert 'code_verifier' in result
        
        url = result['authorization_url']
        assert 'accounts.google.com/o/oauth2/v2/auth' in url
        assert 'client_id=test_client_id' in url
        assert f'redirect_uri={self.handler.redirect_uri}' in url
        assert 'scope=openid' in url
        assert 'code_challenge=' in url
        assert 'code_challenge_method=S256' in url
        assert f"state={result['state']}" in url
        assert f"nonce={result['nonce']}" in url
    
    def test_get_authorization_url_not_configured(self):
        """Test authorization URL generation without config"""
        handler = GoogleOAuthHandler(
            client_id=None,
            client_secret=None
        )
        
        with pytest.raises(ValueError, match="OAuth not configured"):
            handler.get_authorization_url()
    
    def test_create_session_token(self):
        """Test JWT session token creation"""
        user_info = {
            'google_id': '123456789',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User',
            'picture': 'https://example.com/photo.jpg'
        }
        
        token = self.handler.create_session_token(user_info, expires_in_hours=24)
        
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Token should have 3 parts (header.payload.signature)
        parts = token.split('.')
        assert len(parts) == 3
    
    def test_validate_session_token(self):
        """Test JWT session token validation"""
        user_info = {
            'google_id': '123456789',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User',
            'picture': None
        }
        
        # Create token
        token = self.handler.create_session_token(user_info, expires_in_hours=24)
        
        # Validate token
        payload = self.handler.validate_session_token(token)
        
        assert payload is not None
        assert payload['email'] == 'test@example.com'
        assert payload['google_id'] == '123456789'
        assert payload['name'] == 'Test User'
        assert payload['email_verified'] is True
    
    def test_validate_expired_token(self):
        """Test validation of expired token"""
        user_info = {
            'google_id': '123456789',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User'
        }
        
        # Create token that expires immediately
        import jwt
        now = datetime.utcnow()
        payload = {
            'sub': user_info['email'],
            'google_id': user_info['google_id'],
            'email': user_info['email'],
            'iat': now,
            'exp': now - timedelta(hours=1),  # Already expired
            'iss': 'nubemsfc-mcp-server',
            'aud': 'nubemsfc-web-client'
        }
        
        expired_token = jwt.encode(payload, self.handler.jwt_secret, algorithm='HS256')
        
        # Should return None for expired token
        result = self.handler.validate_session_token(expired_token)
        assert result is None
    
    def test_validate_invalid_token(self):
        """Test validation of invalid token"""
        invalid_token = "invalid.token.here"
        
        result = self.handler.validate_session_token(invalid_token)
        assert result is None
    
    def test_validate_tampered_token(self):
        """Test validation of tampered token"""
        user_info = {
            'google_id': '123456789',
            'email': 'test@example.com',
            'email_verified': True,
            'name': 'Test User'
        }
        
        # Create valid token
        token = self.handler.create_session_token(user_info)
        
        # Tamper with token (change last character)
        tampered_token = token[:-1] + ('a' if token[-1] != 'a' else 'b')
        
        # Should return None for tampered token
        result = self.handler.validate_session_token(tampered_token)
        assert result is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
