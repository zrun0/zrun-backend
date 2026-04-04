"""gRPC clients for BFF service.

This module provides gRPC client utilities for communicating
with downstream microservices.
"""

from zrun_bff.clients.base import BaseSkuClient, create_sku_client
from zrun_bff.clients.dependencies import (
    BaseChannelDep,
    SkuClientDep,
    get_base_channel,
    get_sku_client,
)
from zrun_bff.clients.factory import GrpcClientManager, get_client_manager
from zrun_bff.clients.interceptors import (
    build_auth_metadata,
    call_with_auth,
    get_user_context,
    set_user_context,
    user_context_scope,
)
from zrun_bff.clients.utils import handle_grpc_error, retry_with_backoff

__all__ = [
    # Base client
    "BaseSkuClient",
    "create_sku_client",
    # Dependencies
    "BaseChannelDep",
    "SkuClientDep",
    "get_base_channel",
    "get_sku_client",
    # Factory
    "GrpcClientManager",
    "get_client_manager",
    # Interceptors
    "build_auth_metadata",
    "call_with_auth",
    "get_user_context",
    "set_user_context",
    "user_context_scope",
    # Utils
    "handle_grpc_error",
    "retry_with_backoff",
]
