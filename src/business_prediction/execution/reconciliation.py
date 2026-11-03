"""Evidence-driven reconciliation; no data operations or optimistic defaults."""

from abc import ABC, abstractmethod

from ..semantics.common import digest


def check(name, passed, evidence):
    return {"check": name, "status": "unavailable" if passed is None else "passed" if passed else "failed", "evidence": evidence}


class ReconciliationStrategy(ABC):
    strategy_id: str
    version = "1.0"

    @abstractmethod
    def supports(self, operation): ...

    @abstractmethod
    def validate(self, operation, evidence):
        """Return measured checks. Never execute an operation or invent metrics."""


class RowPreservationReconciliation(ReconciliationStrategy):
    strategy_id = "native-row-preservation"

    def supports(self, operation):
        return (operation["input_grain"] == operation["output_grain"] and
            (operation["operation_type"] in ("data_quality_validation", "type_interpretation", "date_time_interpretation") or
             operation["operation_type"] in ("missing_values", "invalid_values", "duplicate_handling") and operation["parameters"].get("method") in ("retain", "flag")))

    def validate(self, operation, evidence):
        inputs, outputs = evidence["input_artifacts"], evidence["output_artifacts"]
        total = sum(a["row_count"] for a in inputs)
        accepted, rejected = evidence["accepted_count"], evidence["rejected_count"]
        schemas = {digest(a["schema"]) for a in inputs + outputs}
        return [check("input_partition", None if accepted is None or rejected is None else total == accepted+rejected,
                      "Measured input count must equal explicitly accepted plus rejected observations."),
            check("no_unapproved_rejection", None if rejected is None else rejected == 0,
                  "The row-preserving baseline does not authorize filtering; filtering requires a separate approved reconciler."),
            check("accepted_output_count", None if accepted is None else accepted == sum(a["row_count"] for a in outputs if a["role"] == "accepted"),
                  "Accepted output manifests must account for accepted records."),
            check("rejected_output_count", None if rejected is None else rejected == sum(a["row_count"] for a in outputs if a["role"] == "rejected"),
                  "Rejected records require explicit measured rejection artifacts."),
            check("row_preservation", total == sum(a["row_count"] for a in outputs), "This bounded reconciliation policy permits no silent row loss or expansion."),
            check("schema_consistency", len(schemas) == 1, "This baseline permits only unchanged artifact field schemas; richer output contracts need an extension."),
            check("duplicate_statistics", operation["operation_type"] != "data_quality_validation" or sum(a["duplicate_count"] for a in inputs) == sum(a["duplicate_count"] for a in outputs),
                  "Measured duplicate counts are retained; quality inspection must not remove records."),
            check("missingness_statistics", operation["operation_type"] != "data_quality_validation" or
                  [a["missing_counts"] for a in inputs] == [a["missing_counts"] for a in outputs],
                  "Measured missing counts must reconcile for a pure quality-inspection declaration.")]


class ReconciliationRegistry:
    def __init__(self, strategies=None):
        self._strategies = {}
        for strategy in strategies if strategies is not None else [RowPreservationReconciliation()]: self.register(strategy)

    def register(self, strategy):
        if not isinstance(strategy, ReconciliationStrategy) or not strategy.strategy_id or not strategy.version:
            raise ValueError("A trusted versioned reconciliation strategy is required.")
        key = (strategy.strategy_id, strategy.version)
        if key in self._strategies: raise ValueError("Duplicate reconciliation strategy.")
        self._strategies[key] = strategy

    def select(self, operation):
        matches = [s for s in self._strategies.values() if s.supports(operation)]
        return matches[0] if len(matches) == 1 else None

    def versions(self):
        return [list(key) for key in sorted(self._strategies)]
