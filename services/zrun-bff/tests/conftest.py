"""Pytest configuration and fixtures for zrun-bff tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_claims() -> dict:
    """Sample JWT claims for testing."""
    return {
        "sub": "test-user-123",
        "name": "Test User",
        "email": "test@example.com",
        "scope": "pda:read pda:write",
    }


@pytest.fixture
def admin_claims() -> dict:
    """Admin JWT claims for testing."""
    return {
        "sub": "admin-user",
        "name": "Admin User",
        "email": "admin@example.com",
        "scope": "admin:all web:admin",
    }
