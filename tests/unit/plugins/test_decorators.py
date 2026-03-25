"""
Tests for SDK decorators.
"""

from unittest.mock import MagicMock

import pytest

from xcore.sdk.decorators import action, require_service, route, validate_payload


class TestActionDecorator:
    """Test @action decorator."""

    @pytest.mark.asyncio
    async def test_action_decorator(self):
        """Test action decorator functionality."""

        class Plugin:
            @action("process")
            async def process_action(self, payload):
                return {"status": "ok"}

        plugin = Plugin()

        # Check decorator added metadata
        assert hasattr(plugin.process_action, "_xcore_action")
        assert plugin.process_action._xcore_action == "process"


class TestRouteDecorator:
    """Test @route decorator."""

    def test_route_decorator(self):
        """Test route decorator."""
        MagicMock()

        class Plugin:
            @route("/items")
            async def list_items(self):
                return []

        plugin = Plugin()

        # Verify route metadata
        assert hasattr(plugin.list_items, "_xcore_route")
        assert plugin.list_items._xcore_route["path"] == "/items"


class TestRequireServiceDecorator:
    """Test @require_service decorator."""

    @pytest.mark.asyncio
    async def test_require_service(self):
        """Test require_service decorator."""

        class Plugin:
            def __init__(self):
                self.services = {"db": MagicMock()}

            def get_service(self, name):
                return self.services[name]

            @require_service("db")
            async def get_data(self):
                return self.get_service("db").query()

        plugin = Plugin()
        await plugin.get_data()
        plugin.services["db"].query.assert_called_once()


class TestValidatePayloadDecorator:
    """Test @validate_payload decorator."""

    @pytest.mark.asyncio
    async def test_validate_payload(self):
        """Test payload validation."""
        from pydantic import BaseModel

        class InputModel(BaseModel):
            name: str
            count: int

        class Plugin:
            @validate_payload(InputModel)
            async def create(self, data: InputModel):
                # data is InputModel due to decorator
                return {"name": data.name, "count": data.count}

        plugin = Plugin()

        # Valid payload
        result = await plugin.create({"name": "test", "count": 5})
        assert result["name"] == "test"
        assert result["count"] == 5

        # Invalid payload should return error dict as per decorator implementation
        result = await plugin.create({"name": "test", "count": "not_an_int"})
        assert result["status"] == "error"
        assert result["code"] == "validation_error"
