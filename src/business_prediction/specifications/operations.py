"""Extensible declaration validators, with no operation execution methods."""

from abc import ABC, abstractmethod

from ..contracts import ContractDefinition, ContractRegistry, FieldSpec as F
from ..errors import ContractValidationError
from ..semantics.contracts import ref, refs, texts


def issue(code, category, message, subject=None, operation_id=None):
    return {"code": code, "category": category, "message": message,
            "subject_reference": subject, "operation_id": operation_id}


class OperationValidator(ABC):
    """Trusted backend plug-in. This interface deliberately has no execute API."""
    operation_type: str
    version = "1.0"
    permits_grain_change = False

    @abstractmethod
    def validate(self, operation, context): ...


class DeclarativeOperationValidator(OperationValidator):
    def __init__(self, operation_type, fields, *, grain_change=False):
        self.operation_type, self.permits_grain_change = operation_type, grain_change
        self.registry = ContractRegistry()
        self.registry.register(ContractDefinition("OperationParameters", self.version, fields))

    def validate(self, operation, context):
        try:
            if set(operation["parameters"]) & {"contract_type", "contract_version"}:
                return [issue("invalid_operation_parameters", "specification", "Parameter envelope fields are not caller-supplied.", operation_id=operation["operation_id"])]
            self.registry.validate({"contract_type": "OperationParameters", "contract_version": self.version,
                                   **operation["parameters"]}, resolver=context["resolver"])
        except ContractValidationError:
            return [issue("invalid_operation_parameters", "specification",
                          "Parameters do not conform to this exact operation type/version.", operation_id=operation["operation_id"])]
        p, findings = operation["parameters"], []
        def block(code, category, message):
            findings.append(issue(code, category, message, operation_id=operation["operation_id"]))
        # Parameter references cannot smuggle undeclared source dependencies.
        def references(value):
            if isinstance(value, dict):
                if value.get("contract_type") == "SemanticBinding": yield value
                else:
                    for child in value.values(): yield from references(child)
            elif isinstance(value, list):
                for child in value: yield from references(child)
        if any(r not in operation["input_binding_references"] for r in references(p)):
            block("undeclared_parameter_dependency", "specification", "Parameter binding references must be explicit operation inputs.")
        name = self.operation_type
        if name == "missing_values" and p["method"] == "constant_fill" and p["constant"] is None:
            block("missing_fill_value", "specification", "A proposed constant treatment requires an explicit approved constant, never an invented value.")
        if name == "missing_values" and p["method"] == "model_based":
            block("fitted_treatment_requires_fold_contract", "unsupported", "Learned treatment needs separately approved training-fold fit scopes; a global preparation plan is insufficient.")
        if name == "duplicate_handling" and p["method"] == "exclude" and not p["key_bindings"]:
            block("duplicate_grain_undefined", "specification", "Proposed exclusion requires explicit comparison fields and owner review of record grain.")
        if name == "date_time_interpretation":
            if p["ambiguous_policy"] == "explicit_rule":
                if p["rule_reference"] is None:
                    block("missing_date_rule", "approval", "Ambiguous dates need an exact business rule evidence reference.")
                else:
                    context["check_document"](p["rule_reference"], findings, operation["operation_id"])
        if name == "filtering_eligibility" and p["operator"] in ("in", "not_in") and not isinstance(p["value"], list):
            block("invalid_filter_value", "specification", "Set membership requires a declared array of literal values.")
        if name in ("aggregation", "join") and not p["reconciliation_checks"]:
            block("missing_reconciliation", "specification", "Grain/relationship changes require explicit row, distinct-entity and relevant quantity/financial reconciliation declarations.")
        if name == "aggregation" and not p["measure_bindings"]:
            block("missing_aggregation_measure", "specification", "Declare the measures contributing to this aggregation.")
        if name == "time_series_aggregation":
            if not p["dimensions"] or not p["measures"]:
                block("incomplete_time_series_aggregation", "specification", "Declare at least one explicit grouping dimension and measure.")
            if not p["reconciliation_checks"]:
                block("missing_reconciliation", "specification", "Grain changes require explicit row, distinct-entity and relevant quantity/financial reconciliation declarations.")
            outputs = [d["output_field_id"] for d in p["dimensions"]] + [m["output_field_id"] for m in p["measures"]]
            if len(outputs) != len(set(outputs)):
                block("duplicate_aggregation_output", "specification", "Each output field must have a unique explicit identifier.")
            declared = operation["input_binding_references"]
            used = [d["binding_reference"] for d in p["dimensions"]]
            used.extend(r for m in p["measures"] for r in m["binding_references"])
            if any(r not in declared for r in used):
                block("invalid_aggregation_bindings", "specification", "Each aggregation input must be declared exactly once as an operation dependency.")
            if operation["output_grain"] == operation["input_grain"]:
                block("aggregation_grain_unchanged", "specification", "A grouped output must declare its resulting observation grain explicitly.")
        if name == "derived_target":
            block("unverified_derivation_method", "unsupported", "This method has no trusted derivation verifier; a description alone cannot establish a constructible target.")
        if name == "join":
            r = p["relationship_reference"]
            if r not in operation["relationship_references"]:
                block("undeclared_join_relationship", "specification", "The join must declare its exact reviewed relationship dependency.")
            else:
                relation = context["resolver"](r)
                if relation["result_grain"] != operation["output_grain"] or relation["left_grain"] != operation["input_grain"]:
                    block("join_grain_mismatch", "specification", "Join grains must match the exact relationship specification.")
                keys = relation["left_key_bindings"] + relation["right_key_bindings"]
                if any(k not in operation["input_binding_references"] for k in keys):
                    block("join_keys_missing", "specification", "Both sides of the approved key tuple must be declared operation inputs.")
        return findings


class OperationRegistry:
    def __init__(self, validators=()):
        self._validators = {}
        for validator in validators: self.register(validator)

    def register(self, validator):
        if not isinstance(validator, OperationValidator) or not validator.operation_type or not validator.version:
            raise ValueError("A trusted versioned declaration validator is required.")
        key = (validator.operation_type, validator.version)
        if key in self._validators: raise ValueError("Operation validator already registered.")
        self._validators[key] = validator

    def get(self, name, version):
        return self._validators.get((name, version))

    def versions(self):
        return [list(key) for key in sorted(self._validators)]


def default_operation_registry():
    text, nullable = F("string"), F("string", nullable=True)
    time_dimension = F("object", fields={"binding_reference": ref("SemanticBinding"),
        "output_field_id": text, "bucket": F("string", choices=("native", "month", "quarter", "year"))})
    measure = F("object", fields={"binding_references": refs("SemanticBinding"),
        "output_field_id": text, "method": F("string", choices=("count", "count_distinct", "sum", "mean", "min", "max"))})
    definitions = {
        "type_interpretation": {"value_type": text, "format": nullable},
        "missing_values": {"method": F("string", choices=("retain", "flag", "exclude", "constant_fill", "model_based")), "constant": F("any", nullable=True)},
        "invalid_values": {"method": F("string", choices=("retain", "flag", "exclude")), "rule_definition": text},
        "duplicate_handling": {"method": F("string", choices=("retain", "flag", "exclude")), "key_bindings": refs("SemanticBinding")},
        "date_time_interpretation": {"format": text, "timezone": text, "calendar": text,
            "ambiguous_policy": F("string", choices=("reject", "explicit_rule")), "rule_reference": ref("SupportingEvidenceRecord", nullable=True)},
        "filtering_eligibility": {"binding_reference": ref("SemanticBinding"),
            "operator": F("string", choices=("is_null", "not_null", "eq", "ne", "lt", "lte", "gt", "gte", "in", "not_in")), "value": F("any", nullable=True)},
        "aggregation": {"group_bindings": refs("SemanticBinding"), "measure_bindings": refs("SemanticBinding"),
            "method": F("string", choices=("sum", "count", "min", "max", "mean")), "reconciliation_checks": texts()},
        "time_series_aggregation": {"dimensions": F("array", items=time_dimension), "measures": F("array", items=measure),
            "reconciliation_checks": texts(), "missing_period_policy": F("string", choices=("observed_only",))},
        "join": {"relationship_reference": ref("RelationshipSpecification"),
            "join_type": F("string", choices=("left", "inner", "full")), "reconciliation_checks": texts()},
        "derived_target": {"method_reference": text, "output_value_type": text, "definition": text},
        "data_quality_validation": {"checks": texts()}}
    validators = []
    for name, params in definitions.items():
        fields = {"contract_type": F("string", choices=("OperationParameters",)), "contract_version": F("string", choices=("1.0",)), **params}
        validators.append(DeclarativeOperationValidator(name, fields, grain_change=name in ("aggregation", "join", "derived_target", "time_series_aggregation")))
    return OperationRegistry(validators)
