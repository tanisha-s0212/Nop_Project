"""Schema-aware discovery, governed preparation, and dynamic query services."""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
__version__ = "0.1.0"

from .query import DynamicBusinessQueryService, RequestInterpreter, JSONRequestInterpreter

__all__ = ["DynamicBusinessQueryService", "RequestInterpreter", "JSONRequestInterpreter"]
