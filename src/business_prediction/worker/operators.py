"""Bounded pure operators, registered only by trusted application code."""

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from datetime import date
import json
import math
import re

from ..contracts import reference, reference_key
from ..execution.reconciliation import ReconciliationStrategy, check
from ..semantics.common import clone, digest, GovernanceError
from .storage import validate_batch


class PreparationOperator(ABC):
    operation_type: str
    operation_version = "1.0"
    implementation_version = "1.0"
    changes_rows = False
    changes_schema = False
    changes_grain = False
    idempotent = True

    @abstractmethod
    def validate(self, operation): ...
    @abstractmethod
    def apply(self, batch, operation, field_id): ...
    @abstractmethod
    def reconcile(self, before, accepted, rejected, operation, field_id): ...


def empty_like(batch): return {"schema": clone(batch["schema"]), "rows": [], "ordinals": []}


class InspectNativeRows(PreparationOperator):
    operation_type = "data_quality_validation"
    def validate(self, op):
        if (set(op["parameters"]) != {"checks"} or not op["parameters"]["checks"] or
                not set(op["parameters"]["checks"]) <= {"native_rows","row_count","schema","missing_counts","duplicate_count","content_integrity"}):
            raise GovernanceError("unsupported_inspection", "Inspection needs declared quality checks; business assertions are not automatically evaluated.")
    def apply(self, batch, operation, field_id): return clone(batch), empty_like(batch)
    def reconcile(self, before, accepted, rejected, operation, field_id):
        return accepted == before and not rejected["rows"] and rejected["schema"] == before["schema"]


def predicate(cell, operator, literal):
    kind, value = cell["type"], cell["value"]
    if operator in ("is_null", "not_null"):
        if literal is not None: raise GovernanceError("invalid_filter_literal", "Null checks require a null literal.")
        return (kind == "null") == (operator == "is_null")
    if kind == "null": return False  # explicit nulls never become zero or a positive match
    if kind not in ("integer", "float", "boolean", "text"):
        raise GovernanceError("unsupported_filter_type", "Only native finite scalar comparison and explicit null checks are supported.")
    values = literal if operator in ("in", "not_in") else [literal]
    if not isinstance(values,list) or not values or len(values) > 512:
        raise GovernanceError("invalid_filter_literal", "Membership needs a bounded, nonempty literal list.")
    expected = {"integer": int, "float": float, "boolean": bool, "text": str}[kind]
    if any(type(x) is not expected for x in values) or kind == "float" and (not math.isfinite(value) or any(not math.isfinite(x) for x in values)):
        raise GovernanceError("ambiguous_filter_type", "Filter literals must match the exact native type; no implicit coercion is performed.")
    if kind == "boolean" and operator not in ("eq","ne","in","not_in"):
        raise GovernanceError("unsupported_boolean_order", "Boolean outcomes have no inferred ordinal ordering.")
    if operator == "in": return value in values
    if operator == "not_in": return value not in values
    other = values[0]
    if operator == "eq": return value == other
    if operator == "ne": return value != other
    if operator == "lt": return value < other
    if operator == "lte": return value <= other
    if operator == "gt": return value > other
    if operator == "gte": return value >= other
    raise GovernanceError("unsupported_filter_operator", "No executable expressions or unknown comparisons are accepted.")


class ApprovedFilter(PreparationOperator):
    operation_type = "filtering_eligibility"
    changes_rows = True
    def validate(self, op):
        p = op["parameters"]
        if set(p) != {"binding_reference","operator","value"} or p["binding_reference"] not in op["input_binding_references"] or p["operator"] not in ("is_null","not_null","eq","ne","lt","lte","gt","gte","in","not_in"):
            raise GovernanceError("unsupported_filter", "A filter must pin its declared input meaning and bounded literal operator.")
    def apply(self, batch, operation, field_id):
        index = [c["field_id"] for c in batch["schema"]].index(field_id)
        accepted, rejected = empty_like(batch), empty_like(batch)
        p = operation["parameters"]
        for row, ordinal in zip(batch["rows"], batch["ordinals"]):
            target = accepted if predicate(row[index],p["operator"],p["value"]) else rejected
            target["rows"].append(clone(row)); target["ordinals"].append(ordinal)
        return accepted, rejected
    def reconcile(self, before, accepted, rejected, operation, field_id):
        if before["schema"] != accepted["schema"] or before["schema"] != rejected["schema"]: return False
        original = dict(zip(before["ordinals"],before["rows"]))
        if set(accepted["ordinals"]) & set(rejected["ordinals"]) or set(original) != set(accepted["ordinals"]+rejected["ordinals"]): return False
        index = [c["field_id"] for c in before["schema"]].index(field_id); p = operation["parameters"]
        for partition, expected in ((accepted,True),(rejected,False)):
            if partition["ordinals"] != sorted(partition["ordinals"]): return False
            for ordinal,row in zip(partition["ordinals"],partition["rows"]):
                if original[ordinal] != row or predicate(row[index],p["operator"],p["value"]) is not expected: return False
        return True


class ApprovedTypeInterpretation(PreparationOperator):
    operation_type = "type_interpretation"
    changes_schema = True  # conditional; native assertions preserve it
    def validate(self, op):
        p = op["parameters"]
        if set(p) != {"value_type","format"} or len(op["input_binding_references"]) != 1:
            raise GovernanceError("unsupported_type_interpretation", "Type interpretation requires exactly one declared meaning.")
        if p["format"] in (None,"native"):
            if p["value_type"] not in ("integer","float","boolean","text","date","datetime","time","decimal"):
                raise GovernanceError("unsupported_type_interpretation", "Unknown native type.")
        elif p["format"] == "canonical_integer_text" and p["value_type"] == "integer":
            if op["information_role"] in ("target","identifier","time"):
                raise GovernanceError("protected_type_interpretation", "This bounded conversion cannot redefine a target, identifier or business date.")
        else: raise GovernanceError("ambiguous_type_interpretation", "No ambiguous date, numerical locale or arbitrary parser is supported.")
    def apply(self, batch, operation, field_id):
        result = clone(batch); index = [c["field_id"] for c in result["schema"]].index(field_id); p = operation["parameters"]
        expected = p["value_type"] if p["format"] in (None,"native") else "text"
        if result["schema"][index]["types"] != [expected]:
            raise GovernanceError("type_evidence_incomplete", "Mixed or unobserved input types cannot support this bounded interpretation.")
        for row in result["rows"]:
            cell = row[index]
            if cell["type"] == "null": continue
            if p["format"] in (None,"native"):
                if cell["type"] != p["value_type"]: raise GovernanceError("native_type_mismatch", "Values do not support the approved native type assertion.")
            else:
                if cell["type"] != "text" or not re.fullmatch(r"[+-]?(?:0|[1-9][0-9]*)",cell["value"]):
                    raise GovernanceError("ambiguous_integer_text", "Only canonical integer tokens without spaces, leading zeroes, dates or locale separators are accepted.")
                value = int(cell["value"])
                if not -(2**63) <= value < 2**63: raise GovernanceError("integer_range_exceeded", "Conversion exceeds the declared bounded integer representation.")
                row[index] = {"type":"integer","value":value}
        if p["format"] == "canonical_integer_text": result["schema"][index]["types"] = ["integer"]
        return result, empty_like(result)
    def reconcile(self, before, accepted, rejected, operation, field_id):
        if rejected["rows"] or before["ordinals"] != accepted["ordinals"] or len(before["rows"]) != len(accepted["rows"]): return False
        index = [c["field_id"] for c in before["schema"]].index(field_id); p = operation["parameters"]
        expected_schema = clone(before["schema"])
        if p["format"] == "canonical_integer_text": expected_schema[index]["types"] = ["integer"]
        if accepted["schema"] != expected_schema or rejected["schema"] != expected_schema: return False
        for old,new in zip(before["rows"],accepted["rows"]):
            if any(a != b for i,(a,b) in enumerate(zip(old,new)) if i != index): return False
            if old[index]["type"] == "null":
                if old[index] != new[index]: return False
            elif p["format"] in (None,"native"):
                if old[index] != new[index] or new[index]["type"] != p["value_type"]: return False
            elif new[index]["type"] != "integer" or Decimal(old[index]["value"]) != Decimal(new[index]["value"]): return False
        return True


class ApprovedTimeSeriesAggregation(PreparationOperator):
    """Explicit grouped aggregation. It emits observed groups only and never fills gaps."""
    operation_type = "time_series_aggregation"
    changes_rows = True
    changes_schema = True
    changes_grain = True
    implementation_version = "1.0"

    def validate(self, op):
        p = op["parameters"]
        if set(p) != {"dimensions", "measures", "reconciliation_checks", "missing_period_policy"}:
            raise GovernanceError("unsupported_aggregation", "Aggregation parameters must use the exact registered schema.")
        if not p["dimensions"] or not p["measures"] or p["missing_period_policy"] != "observed_only":
            raise GovernanceError("unsupported_aggregation", "Explicit dimensions/measures and observed-only period handling are required.")
        if not p["reconciliation_checks"] or op["input_grain"] == op["output_grain"]:
            raise GovernanceError("aggregation_reconciliation_required", "A grain change needs explicit reconciliation and a distinct output grain.")
        outputs = [d["output_field_id"] for d in p["dimensions"]] + [m["output_field_id"] for m in p["measures"]]
        if len(outputs) != len(set(outputs)) or any(not isinstance(x, str) or not x.strip() for x in outputs):
            raise GovernanceError("invalid_aggregation_outputs", "Aggregation output field identifiers must be explicit and unique.")
        declared = op["input_binding_references"]
        used = [d["binding_reference"] for d in p["dimensions"]]
        for measure in p["measures"]:
            method, refs = measure["method"], measure["binding_references"]
            if method == "count":
                if refs: raise GovernanceError("invalid_count_measure", "Row count has no input bindings.")
            elif method == "count_distinct":
                if not refs: raise GovernanceError("invalid_distinct_measure", "Distinct count requires an explicit identity binding tuple.")
            elif len(refs) != 1:
                raise GovernanceError("invalid_numeric_measure", "A numeric aggregation requires exactly one declared measure binding.")
            used.extend(refs)
        if any(ref not in declared for ref in used):
            raise GovernanceError("undeclared_aggregation_input", "Every aggregation binding must be an explicit operation dependency.")

    @staticmethod
    def _calendar_value(cell, bucket):
        if bucket == "native": return cell
        if cell["type"] != "date":
            raise GovernanceError("date_bucket_requires_native_date", "Calendar bucketing accepts only native date cells; text and datetimes need an explicitly reviewed interpretation first.")
        try: value = date.fromisoformat(cell["value"])
        except (TypeError, ValueError): raise GovernanceError("invalid_native_date", "Date cell is not canonical ISO calendar data.") from None
        if value.isoformat() != cell["value"]:
            raise GovernanceError("invalid_native_date", "Date cell is not canonical ISO calendar data.")
        if bucket == "month": token = f"{value.year:04d}-{value.month:02d}"
        elif bucket == "quarter": token = f"{value.year:04d}-Q{(value.month - 1) // 3 + 1}"
        else: token = f"{value.year:04d}"
        return {"type": "text", "value": token}

    def apply(self, batch, operation, field_ids):
        if not isinstance(field_ids, dict): raise GovernanceError("aggregation_bindings_unresolved", "Aggregation requires exact resolved field identifiers.")
        schema_ids = [c["field_id"] for c in batch["schema"]]
        p = operation["parameters"]
        dimensions = []
        output_schema = []
        for d in p["dimensions"]:
            fid = field_ids.get(reference_key(d["binding_reference"]))
            if fid not in schema_ids: raise GovernanceError("aggregation_field_missing", "A declared group field is absent from the captured input schema.")
            col = batch["schema"][schema_ids.index(fid)]
            bucket = d["bucket"]
            if bucket != "native" and col["types"] != ["date"]:
                raise GovernanceError("date_bucket_requires_native_date", "Calendar bucketing requires a single native date type.")
            dimensions.append((schema_ids.index(fid), d, col))
            output_schema.append({"field_id": d["output_field_id"], "types": ["text"] if bucket != "native" else list(col["types"])})
        measures = []
        for m in p["measures"]:
            indexes = []
            for ref in m["binding_references"]:
                fid = field_ids.get(reference_key(ref))
                if fid not in schema_ids: raise GovernanceError("aggregation_field_missing", "A declared measure field is absent from the captured input schema.")
                indexes.append(schema_ids.index(fid))
            method = m["method"]
            if method in ("sum", "mean", "min", "max"):
                if batch["schema"][indexes[0]]["types"] not in (["integer"], ["float"], ["integer", "float"], ["float", "integer"]):
                    raise GovernanceError("numeric_measure_required", "Numeric aggregation requires observed integer or float inputs only.")
                types = ["float"]
            else: types = ["integer"]
            measures.append((indexes, m, method))
            output_schema.append({"field_id": m["output_field_id"], "types": types})
        groups = {}
        for row in batch["rows"]:
            group_cells = []
            for index, d, _ in dimensions:
                cell = row[index]
                if cell["type"] == "null": raise GovernanceError("aggregation_missing_dimension", "Null group values are unresolved and cannot be silently excluded or assigned a bucket.")
                cell = self._calendar_value(cell, d["bucket"])
                group_cells.append(cell)
            key = json.dumps(group_cells, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            state = groups.setdefault(key, {"groups": group_cells, "values": [[] for _ in measures]})
            for position, (indexes, _, method) in enumerate(measures):
                if method == "count":
                    state["values"][position].append(1)
                else:
                    cells = [row[index] for index in indexes]
                    if any(cell["type"] == "null" for cell in cells):
                        raise GovernanceError("aggregation_missing_measure", "Null measure or identity components require an explicit approved treatment.")
                    if method == "count_distinct":
                        state["values"][position].append(tuple((cell["type"], cell["value"]) for cell in cells))
                    else:
                        cell = cells[0]
                        if cell["type"] not in ("integer", "float") or not math.isfinite(cell["value"]):
                            raise GovernanceError("invalid_numeric_measure", "Numeric aggregation encountered a nonfinite or nonnumeric value.")
                        state["values"][position].append(cell["value"])
        rows = []
        for key in sorted(groups):
            state = groups[key]; row = list(state["groups"])
            for (_, _, method), values in zip(measures, state["values"]):
                if method == "count": result = len(values)
                elif method == "count_distinct": result = len(set(values))
                elif method == "sum": result = float(sum(values))
                elif method == "mean": result = float(sum(values) / len(values))
                elif method == "min": result = float(min(values))
                else: result = float(max(values))
                if type(result) is float and not math.isfinite(result): raise GovernanceError("aggregation_overflow", "Aggregation result is outside finite numeric range.")
                row.append({"type": "integer" if type(result) is int else "float", "value": result})
            rows.append(row)
        accepted = {"schema": output_schema, "rows": rows, "ordinals": list(range(1, len(rows) + 1))}
        return accepted, empty_like(batch)

    def reconcile(self, before, accepted, rejected, operation, field_ids):
        try:
            expected, empty = self.apply(before, operation, field_ids)
            return accepted == expected and rejected == empty
        except (GovernanceError, KeyError, TypeError, ValueError, IndexError):
            return False


class PreparationOperatorRegistry:
    def __init__(self, operators=None):
        self._operators = {}
        for op in operators if operators is not None else (InspectNativeRows(),ApprovedFilter(),ApprovedTypeInterpretation(),ApprovedTimeSeriesAggregation()): self.register(op)
    def register(self, operator):
        if (not isinstance(operator,PreparationOperator) or not operator.operation_type or not operator.operation_version or not operator.implementation_version or
                any(type(v) is not bool for v in (operator.changes_rows,operator.changes_schema,operator.changes_grain,operator.idempotent)) or
                operator.changes_grain and (operator.operation_type,operator.operation_version) != ("time_series_aggregation", "1.0")):
            raise ValueError("Register a trusted bounded operator with explicit capability declarations.")
        key = (operator.operation_type,operator.operation_version)
        if key in self._operators: raise ValueError("Operator implementation already registered.")
        self._operators[key] = operator
    def get(self, op):
        result = self._operators.get((op["operation_type"],op["operation_version"]))
        if result is None: raise GovernanceError("unregistered_preparation_operator", "No registered executable implementation supports this exact operation.")
        if op["input_grain"] != op["output_grain"] and not result.changes_grain: raise GovernanceError("unsupported_worker_grain", "This operator does not construct new observation grains.")
        result.validate(op)
        return result
    def versions(self):
        return [[a,b,op.implementation_version,str(op.changes_rows),str(op.changes_schema),str(op.changes_grain),str(op.idempotent)] for (a,b),op in sorted(self._operators.items())]
    @property
    def signature(self): return digest(self.versions())[7:]


class WorkerReconciliation(ReconciliationStrategy):
    strategy_id = "registered-worker-reconciliation"
    def __init__(self, registry, store, resolver): self.registry,self.store,self.resolver = registry,store,resolver
    @property
    def version(self): return "1.0-"+self.registry.signature
    def supports(self, op):
        try: self.registry.get(op); return True
        except GovernanceError: return False
    def validate(self, operation, evidence):
        inputs, outputs = evidence["input_artifacts"],evidence["output_artifacts"]
        a = [d for d in outputs if d["role"] == "accepted"]; r = [d for d in outputs if d["role"] == "rejected"]
        if len(inputs) != 1 or len(a) != 1 or len(r) != 1:
            return [check("worker_partition_manifests",False,"One input and explicit accepted/rejected artifacts are required.")]
        before = self.store.read(inputs[0]["locator"])["batch"]
        accepted = self.store.read(a[0]["locator"])["batch"]; rejected = self.store.read(r[0]["locator"])["batch"]
        operator = self.registry.get(operation)
        if operation["operation_type"] == "time_series_aggregation":
            field_id = {reference_key(r): self.resolver(r)["physical_field_reference"]["field_id"] for r in operation["input_binding_references"]}
        else:
            binding_ref = operation["parameters"].get("binding_reference") or (operation["input_binding_references"][0] if operation["operation_type"] == "type_interpretation" else None)
            field_id = self.resolver(binding_ref)["physical_field_reference"]["field_id"] if binding_ref else None
        valid = operator.reconcile(before,accepted,rejected,operation,field_id)
        return [check("operator_specific_reconciliation",valid,"Typed cells, exact row lineage, approved predicate/type semantics and schema were independently checked."),
            check("input_partition",True if operator.changes_grain else len(before["rows"]) == len(accepted["rows"])+len(rejected["rows"]),"Grain-changing operations are independently recomputed; row-preserving operations partition physical identities."),
            check("observed_partition_counts",evidence["accepted_count"] == len(accepted["rows"]) and evidence["rejected_count"] == len(rejected["rows"]),"Counts come from sealed artifacts, never caller success flags.")]
