"""
Basic tests for OAuth Device Flow implementation.

Tests core functionality without requiring external dependencies.
"""

import sys
import os
import asyncio
import unittest
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.device_code_storage import InMemoryDeviceCodeStorage
from auth.device_flow_handler import generate_user_code


class TestGenerateUserCode(unittest.TestCase):
    """Test user code generation."""

    def test_format(self):
        """Test user code format is XXXX-XXXX."""
        code = generate_user_code()
        self.assertRegex(code, r'^[BCDFGHJKLMNPQRSTVWXYZ23456789]{4}-[BCDFGHJKLMNPQRSTVWXYZ23456789]{4}$')

    def test_length(self):
        """Test user code length is 9 chars (including dash)."""
        code = generate_user_code()
        self.assertEqual(len(code), 9)

    def test_has_dash(self):
        """Test user code has dash in middle."""
        code = generate_user_code()
        self.assertEqual(code[4], '-')

    def test_no_ambiguous_chars(self):
        """Test user code excludes ambiguous characters."""
        # Generate many codes to test randomness
        codes = [generate_user_code() for _ in range(100)]
        all_chars = ''.join(codes)

        # Should not contain: 0, O, I, 1, L
        self.assertNotIn('0', all_chars)
        self.assertNotIn('O', all_chars)
        self.assertNotIn('I', all_chars)
        self.assertNotIn('1', all_chars)
        self.assertNotIn('L', all_chars)

    def test_uniqueness(self):
        """Test generated codes are unique."""
        codes = [generate_user_code() for _ in range(100)]
        # Should have at least 95% unique codes (allowing for rare collisions)
        unique_codes = set(codes)
        self.assertGreater(len(unique_codes), 95)


class TestInMemoryDeviceCodeStorage(unittest.IsolatedAsyncioTestCase):
    """Test in-memory device code storage."""

    async def asyncSetUp(self):
        """Set up test storage."""
        self.storage = InMemoryDeviceCodeStorage()

    async def test_store_and_get(self):
        """Test storing and retrieving device code."""
        device_info = {
            "device_code": "test_device_123",
            "user_code": "ABCD-EFGH",
            "client_id": "test_client",
            "scope": "openid email",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        }

        await self.storage.store(device_info, ttl=900)

        # Retrieve by device code
        retrieved = await self.storage.get("test_device_123")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["user_code"], "ABCD-EFGH")
        self.assertEqual(retrieved["status"], "pending")

    async def test_get_by_user_code(self):
        """Test reverse lookup by user code."""
        device_info = {
            "device_code": "test_device_456",
            "user_code": "WXYZ-1234",
            "client_id": "test_client",
            "scope": "openid",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        }

        await self.storage.store(device_info, ttl=900)

        # Lookup by user code
        device_code = await self.storage.get_by_user_code("WXYZ-1234")
        self.assertEqual(device_code, "test_device_456")

    async def test_update_status(self):
        """Test updating device status."""
        device_info = {
            "device_code": "test_device_789",
            "user_code": "HIJK-LMNO",
            "client_id": "test_client",
            "scope": "openid",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        }

        await self.storage.store(device_info, ttl=900)

        # Update status
        user_info = {
            "email": "test@example.com",
            "google_id": "123456"
        }
        await self.storage.update_status("test_device_789", "approved", user_info)

        # Verify update
        retrieved = await self.storage.get("test_device_789")
        self.assertEqual(retrieved["status"], "approved")
        self.assertEqual(retrieved["user_info"]["email"], "test@example.com")

    async def test_delete(self):
        """Test deleting device code."""
        device_info = {
            "device_code": "test_device_delete",
            "user_code": "PQRS-TUVW",
            "client_id": "test_client",
            "scope": "openid",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        }

        await self.storage.store(device_info, ttl=900)

        # Delete
        await self.storage.delete("test_device_delete")

        # Verify deleted
        retrieved = await self.storage.get("test_device_delete")
        self.assertIsNone(retrieved)

        # User code lookup should also fail
        device_code = await self.storage.get_by_user_code("PQRS-TUVW")
        self.assertIsNone(device_code)

    async def test_poll_time_tracking(self):
        """Test last poll time tracking."""
        device_info = {
            "device_code": "test_device_poll",
            "user_code": "POLL-TEST",
            "client_id": "test_client",
            "scope": "openid",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        }

        await self.storage.store(device_info, ttl=900)

        # Initially no poll time
        last_poll = await self.storage.get_last_poll_time("test_device_poll")
        self.assertIsNone(last_poll)

        # Update poll time
        await self.storage.update_last_poll_time("test_device_poll")

        # Should have poll time now
        last_poll = await self.storage.get_last_poll_time("test_device_poll")
        self.assertIsNotNone(last_poll)
        self.assertIsInstance(last_poll, datetime)

    async def test_oauth_state_mapping(self):
        """Test OAuth state to device code mapping."""
        await self.storage.store_oauth_state("oauth_state_123", "device_456", ttl=900)

        # Retrieve device code by state
        device_code = await self.storage.get_by_oauth_state("oauth_state_123")
        self.assertEqual(device_code, "device_456")

        # Non-existent state
        device_code = await self.storage.get_by_oauth_state("nonexistent")
        self.assertIsNone(device_code)

    async def test_ttl_expiration(self):
        """Test TTL expiration (simulated)."""
        device_info = {
            "device_code": "test_expire",
            "user_code": "EXPR-TEST",
            "client_id": "test_client",
            "scope": "openid",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=1)).isoformat()
        }

        # Store with 1 second TTL
        await self.storage.store(device_info, ttl=1)

        # Should exist initially
        retrieved = await self.storage.get("test_expire")
        self.assertIsNotNone(retrieved)

        # Wait for expiration
        await asyncio.sleep(2)

        # Should be expired now
        retrieved = await self.storage.get("test_expire")
        self.assertIsNone(retrieved)


if __name__ == '__main__':
    unittest.main()
