"""Unit tests for gRPC client factory and manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zrun_core.grpc import GrpcChannelConfig, GrpcClientFactory, GrpcClientManager


class TestGrpcChannelConfig:
    """Tests for GrpcChannelConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = GrpcChannelConfig()
        assert config.max_receive_message_length == 128 * 1024 * 1024
        assert config.max_send_message_length == 128 * 1024 * 1024
        assert config.keepalive_time_ms == 30000
        assert config.keepalive_timeout_ms == 5000
        assert config.keepalive_permit_without_calls is False

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = GrpcChannelConfig(
            max_receive_message_length=64 * 1024 * 1024,
            max_send_message_length=64 * 1024 * 1024,
            keepalive_time_ms=60000,
            keepalive_timeout_ms=10000,
            keepalive_permit_without_calls=True,
        )
        assert config.max_receive_message_length == 64 * 1024 * 1024
        assert config.max_send_message_length == 64 * 1024 * 1024
        assert config.keepalive_time_ms == 60000
        assert config.keepalive_timeout_ms == 10000
        assert config.keepalive_permit_without_calls is True

    def test_to_options(self) -> None:
        """Test converting config to gRPC options."""
        config = GrpcChannelConfig()
        options = config.to_options()

        assert isinstance(options, list)
        assert all(isinstance(opt, tuple) and len(opt) == 2 for opt in options)

        # Check specific options
        option_dict = dict(options)
        assert "grpc.max_receive_message_length" in option_dict
        assert "grpc.max_send_message_length" in option_dict
        assert "grpc.keepalive_time_ms" in option_dict
        assert "grpc.keepalive_timeout_ms" in option_dict


class TestGrpcClientFactory:
    """Tests for GrpcClientFactory."""

    @pytest.fixture
    def factory(self) -> GrpcClientFactory:
        """Create factory instance for testing."""
        config = GrpcChannelConfig(
            max_receive_message_length=1024,
            max_send_message_length=1024,
        )
        return GrpcClientFactory(config=config)

    def test_factory_initialization(self, factory: GrpcClientFactory) -> None:
        """Test factory initialization."""
        assert factory._config is not None

    @patch("grpc.insecure_channel")
    def test_create_channel(self, mock_grpc_channel: MagicMock, factory: GrpcClientFactory) -> None:
        """Test creating an insecure channel."""
        mock_channel = MagicMock()
        mock_grpc_channel.return_value = mock_channel

        channel = factory.create_channel("localhost:50051")

        assert channel == mock_channel
        mock_grpc_channel.assert_called_once()
        call_args = mock_grpc_channel.call_args
        assert call_args[0][0] == "localhost:50051"
        # Options are passed as keyword argument
        if call_args[1]:
            assert "options" in call_args[1]

    @patch("grpc.secure_channel")
    def test_create_secure_channel(
        self,
        mock_grpc_channel: MagicMock,
        factory: GrpcClientFactory,
    ) -> None:
        """Test creating a secure channel."""
        mock_channel = MagicMock()
        mock_grpc_channel.return_value = mock_channel
        credentials = MagicMock()

        channel = factory.create_secure_channel("example.com:443", credentials)

        assert channel == mock_channel
        mock_grpc_channel.assert_called_once()


class TestGrpcClientManager:
    """Tests for GrpcClientManager."""

    @pytest.fixture
    def manager(self) -> GrpcClientManager:
        """Create manager instance for testing."""
        return GrpcClientManager()

    def test_manager_initialization(self, manager: GrpcClientManager) -> None:
        """Test manager initialization."""
        assert manager._factory is not None
        assert manager._channels == {}
        assert manager._ref_counts == {}

    @pytest.mark.asyncio
    async def test_get_channel_creates_new(self, manager: GrpcClientManager) -> None:
        """Test getting a channel creates a new one."""
        channel = await manager.get_channel("localhost:50051")

        assert channel is not None
        assert "localhost:50051" in manager._channels
        assert manager._ref_counts["localhost:50051"] == 1

    @pytest.mark.asyncio
    async def test_get_channel_reuses_existing(self, manager: GrpcClientManager) -> None:
        """Test getting a channel reuses existing one."""
        channel1 = await manager.get_channel("localhost:50051")
        channel2 = await manager.get_channel("localhost:50051")

        # Should return same channel
        assert channel1 is channel2
        # Reference count should be 2
        assert manager._ref_counts["localhost:50051"] == 2

    @pytest.mark.asyncio
    async def test_get_channel_different_targets(self, manager: GrpcClientManager) -> None:
        """Test getting channels for different targets."""
        channel1 = await manager.get_channel("localhost:50051")
        channel2 = await manager.get_channel("localhost:50052")

        # Should return different channels
        assert channel1 is not channel2
        assert len(manager._channels) == 2

    @pytest.mark.asyncio
    async def test_release_channel_decrements_ref_count(
        self,
        manager: GrpcClientManager,
    ) -> None:
        """Test releasing a channel decrements reference count."""
        await manager.get_channel("localhost:50051")
        await manager.get_channel("localhost:50051")  # ref count = 2

        await manager.release_channel("localhost:50051")

        assert manager._ref_counts["localhost:50051"] == 1

    @pytest.mark.asyncio
    async def test_release_channel_closes_when_zero_ref(
        self,
        manager: GrpcClientManager,
    ) -> None:
        """Test releasing channel closes it when ref count reaches zero."""
        channel = await manager.get_channel("localhost:50051")
        mock_close = AsyncMock()
        channel.close = mock_close  # type: ignore[method-assign]

        await manager.release_channel("localhost:50051")

        # Channel should be closed and removed
        mock_close.assert_called_once()
        assert "localhost:50051" not in manager._channels
        assert "localhost:50051" not in manager._ref_counts

    @pytest.mark.asyncio
    async def test_release_channel_nonexistent_target(self, manager: GrpcClientManager) -> None:
        """Test releasing a channel that doesn't exist doesn't raise."""
        # Should not raise an exception
        await manager.release_channel("nonexistent:50051")
        assert True

    @pytest.mark.asyncio
    async def test_close_all(self, manager: GrpcClientManager) -> None:
        """Test closing all channels."""
        # Create multiple channels
        channel1 = await manager.get_channel("localhost:50051")
        channel2 = await manager.get_channel("localhost:50052")

        mock_close1 = AsyncMock()
        mock_close2 = AsyncMock()
        channel1.close = mock_close1  # type: ignore[method-assign]
        channel2.close = mock_close2  # type: ignore[method-assign]

        await manager.close_all()

        # All channels should be closed
        mock_close1.assert_called_once()
        mock_close2.assert_called_once()
        assert manager._channels == {}
        assert manager._ref_counts == {}

    @pytest.mark.asyncio
    async def test_get_client_manager_returns_manager(self) -> None:
        """Test get_client_manager returns GrpcClientManager instance."""
        from zrun_core.grpc import get_client_manager

        manager = await get_client_manager()

        # Should return GrpcClientManager instance
        assert isinstance(manager, GrpcClientManager)
