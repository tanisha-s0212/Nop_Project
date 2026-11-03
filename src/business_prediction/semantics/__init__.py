"""Semantic governance foundation; no data treatment or prediction execution."""

from .contracts import semantic_registry, register_semantic_contracts
from .service import SemanticApprovalService, ReviewPolicy

__all__ = ["semantic_registry", "register_semantic_contracts", "SemanticApprovalService", "ReviewPolicy"]
