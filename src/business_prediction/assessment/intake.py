"""Partial structured intent handling, with no natural-language interpretation."""

from ..contracts import value_state, ValueState


def supplied(document, key, default=None):
    return document[key] if value_state(document, key) == ValueState.PRESENT else default


def finding(code, category, message, binding_reference=None):
    return {"code": code, "category": category, "message": message, "binding_reference": binding_reference}


def intake_findings(requirement):
    issues = []
    for key, message in (("business_outcome", "Describe the requested business outcome."),
                         ("intent", "Specify historical calculation, future prediction or an unknown outcome."),
                         ("desired_output", "Specify the requested output characteristics."),
                         ("observation_granularity", "Specify what one requested observation represents.")):
        if supplied(requirement, key) is None:
            issues.append(finding("missing_"+key, "clarification", message))
    if not supplied(requirement, "requested_concepts") and supplied(requirement, "target_binding_reference") is None:
        issues.append(finding("target_semantics_unspecified", "clarification",
                              "Supply an exact semantic concept or target binding; descriptions alone are not interpreted as field mappings."))
    return issues
