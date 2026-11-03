"""Allowlisted JSON operational logs without credentials or exception bodies."""

from datetime import datetime, timezone
import json
import logging
import re


class StructuredJSONFormatter(logging.Formatter):
    def format(self, record):
        event = record.msg if isinstance(record.msg, str) and re.fullmatch(r"[a-z_.]{1,100}", record.msg) else "runtime.log_event"
        payload = {"recorded_at": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                   "level": record.levelname, "event": event}
        for key in ("operation", "error_code", "governance_head", "document_count", "mode", "status"):
            value = getattr(record, key, None)
            if type(value) in (str, int, bool):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=lambda value: "<unserializable>")


def configure_json_logging(stream, *, level=logging.INFO):
    """Explicit caller-owned logging; never starts files or background services."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredJSONFormatter())
    logger = logging.getLogger("business_prediction")
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return handler
