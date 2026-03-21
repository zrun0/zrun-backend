"""Logging configuration using structlog."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.types import EventDict, Processor


def _add_service_name(service_name: str) -> Processor:
    """Add service name to log entries.

    Args:
        service_name: Name of the service.

    Returns:
        A structlog processor.
    """

    def processor(
        _logger: Any,
        _method_name: str,
        event_dict: EventDict,
    ) -> EventDict:
        event_dict["service"] = service_name
        return event_dict

    return processor


def _rename_message_field(
    _logger: Any,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Rename the 'event' field to 'message' for consistency.

    Args:
        logger: Logger instance (unused).
        method_name: Method name (unused).
        event_dict: Event dictionary.

    Returns:
        Modified event dictionary.
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def configure_structlog(
    service_name: str,
    log_level: str = "INFO",
    log_format: str = "json",
) -> None:
    """Configure structlog for the service.

    Args:
        service_name: Name of the service.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: Log format (json or console).
    """
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _add_service_name(service_name),
    ]

    if log_format == "json":
        # JSON format for production (ELK/Loki friendly)
        processors = shared_processors + [
            _rename_message_field,
            structlog.processors.JSONRenderer(),
        ]
        logger_factory = structlog.PrintLoggerFactory()
    else:
        # Console format for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]
        logger_factory = structlog.PrintLoggerFactory()

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper()),
        ),
        context_class=dict,
        logger_factory=logger_factory,
        cache_logger_on_first_use=True,
    )


def get_logger(**kwargs: Any) -> structlog.stdlib.BoundLogger:
    """Get a bound logger with context.

    Args:
        **kwargs: Context variables to bind to the logger.

    Returns:
        A bound logger instance.
    """
    return structlog.get_logger(**kwargs)


class LoggerMixin:
    """Mixin to add logging capabilities to classes."""

    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        """Get a logger for this class.

        Returns:
            A bound logger with the class name as context.
        """
        return get_logger(class_name=self.__class__.__name__)
