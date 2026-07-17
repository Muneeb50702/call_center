"""
Unit tests for the Multi-Tenant Configuration System.
Tests tenant resolution by SIP number, default tenant fallback, and validation.
"""

import pytest
import json
import os
import tempfile
from config.tenant import TenantConfig, TenantRegistry


# ── Sample tenant data for tests ──
SAMPLE_TENANTS = {
    "tenants": [
        {
            "tenant_id": "test-alpha",
            "company_name": "Alpha Trucking",
            "sip_numbers": ["+15551000", "+15551001"],
            "human_transfer_number": "+15559999",
            "tms_api_url": "http://alpha-tms:8000",
            "voice_model": "aura-orion-en",
            "custom_keywords": ["Alpha Trucking"],
            "negotiation_floor_pct": 0.90,
            "max_concurrent_calls": 20,
        },
        {
            "tenant_id": "test-beta",
            "company_name": "Beta Logistics",
            "sip_numbers": ["+15552000"],
            "human_transfer_number": "+15558888",
            "tms_api_url": "http://beta-tms:8000",
            "voice_model": "aura-asteria-en",
            "custom_keywords": ["Beta Logistics", "BetaLog"],
            "negotiation_floor_pct": 0.85,
            "max_concurrent_calls": 50,
        },
    ]
}


@pytest.fixture
def tenant_config_file(tmp_path):
    """Create a temporary tenants.json file for testing."""
    config_file = tmp_path / "tenants.json"
    config_file.write_text(json.dumps(SAMPLE_TENANTS))
    return str(config_file)


@pytest.fixture
def registry(tenant_config_file):
    """Create a TenantRegistry loaded with sample data."""
    return TenantRegistry(config_path=tenant_config_file)


class TestTenantConfig:
    """Tests for the TenantConfig Pydantic model."""

    def test_minimal_config(self):
        config = TenantConfig(tenant_id="test", company_name="Test Co")
        assert config.tenant_id == "test"
        assert config.company_name == "Test Co"
        # Stale since the Aura-1 → Aura-2 upgrade: the field default has been
        # "aura-2-apollo-en" while this still asserted the old Aura-1 name.
        assert config.voice_model == "aura-2-apollo-en"  # Default
        assert config.negotiation_floor_pct == 0.90  # Default

    def test_full_config(self):
        config = TenantConfig(
            tenant_id="full",
            company_name="Full Test Co",
            sip_numbers=["+15550100"],
            human_transfer_number="+15559999",
            tms_api_url="http://custom-tms:8000",
            voice_model="aura-asteria-en",
            custom_keywords=["custom", "keywords"],
            negotiation_floor_pct=0.85,
            max_concurrent_calls=100,
        )
        assert config.sip_numbers == ["+15550100"]
        assert config.max_concurrent_calls == 100
        assert len(config.custom_keywords) == 2

    def test_config_missing_required_fields(self):
        with pytest.raises(Exception):
            TenantConfig()  # Missing tenant_id and company_name

    def test_config_serialization(self):
        config = TenantConfig(tenant_id="test", company_name="Test Co")
        data = config.model_dump()
        assert isinstance(data, dict)
        assert data["tenant_id"] == "test"

    def test_config_json_round_trip(self):
        config = TenantConfig(tenant_id="test", company_name="Test Co")
        json_str = config.model_dump_json()
        restored = TenantConfig.model_validate_json(json_str)
        assert restored.tenant_id == config.tenant_id


class TestTenantRegistry:
    """Tests for the TenantRegistry loader and resolver."""

    def test_loads_tenants_from_file(self, registry):
        tenants = registry.list_tenants()
        assert len(tenants) == 2

    def test_get_tenant_by_id(self, registry):
        tenant = registry.get_tenant("test-alpha")
        assert tenant is not None
        assert tenant.company_name == "Alpha Trucking"

    def test_get_tenant_unknown_id(self, registry):
        tenant = registry.get_tenant("nonexistent")
        assert tenant is None

    def test_get_default_tenant(self, registry):
        tenant = registry.get_default_tenant()
        assert tenant is not None
        assert tenant.tenant_id in ("test-alpha", "test-beta")

    @pytest.mark.asyncio
    async def test_resolve_tenant_by_sip_number(self, registry):
        tenant = await registry.resolve_tenant("+15551000")
        assert tenant is not None
        assert tenant.tenant_id == "test-alpha"

    @pytest.mark.asyncio
    async def test_resolve_tenant_second_number(self, registry):
        tenant = await registry.resolve_tenant("+15551001")
        assert tenant is not None
        assert tenant.tenant_id == "test-alpha"

    @pytest.mark.asyncio
    async def test_resolve_tenant_beta(self, registry):
        tenant = await registry.resolve_tenant("+15552000")
        assert tenant is not None
        assert tenant.tenant_id == "test-beta"
        assert tenant.voice_model == "aura-asteria-en"

    @pytest.mark.asyncio
    async def test_resolve_unknown_number(self, registry):
        tenant = await registry.resolve_tenant("+19999999999")
        assert tenant is None

    def test_missing_config_file(self, tmp_path):
        registry = TenantRegistry(config_path=str(tmp_path / "nonexistent.json"))
        assert len(registry.list_tenants()) == 0

    def test_tenant_specific_settings(self, registry):
        alpha = registry.get_tenant("test-alpha")
        beta = registry.get_tenant("test-beta")
        assert alpha.negotiation_floor_pct == 0.90
        assert beta.negotiation_floor_pct == 0.85
        assert alpha.max_concurrent_calls == 20
        assert beta.max_concurrent_calls == 50
