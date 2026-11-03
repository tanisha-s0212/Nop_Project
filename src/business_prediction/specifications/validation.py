"""Read-only specification checks over trusted versioned metadata.

Findings describe blockers. A clean result authorizes neither data access nor
preparation execution. No source values are evaluated or transformed here.
"""

from datetime import date, timedelta

from ..contracts import reference
from ..semantics.common import digest, field_key, instant, scope_contains
from ..assessment.relevance import narrow_scope
from .operations import issue


def table_key(field):
    return (digest(field["discovery_reference"]), field["table_id"])


class PreparationPlanValidator:
    def __init__(self, operations):
        self.operations = operations

    def inspect(self, subject, manager, now, *, require_approval=True):
        findings, approvals, visited = [], [], set()
        root_scope = subject["specification_scope"]
        def add(code, category, message, obj=None, op=None):
            findings.append(issue(code, category, message, reference(obj) if obj else None, op))
        def binding(ref, owner):
            b = manager.service.get(ref); field = b["physical_field_reference"]
            scope = narrow_scope(root_scope, field)
            state = manager.service.inspect_binding_use(ref, scope=scope, physical_field=field, now=now)
            approvals.extend(reference(a) for a in state["compatible_approvals"])
            if state["result"] != "usable":
                add("semantic_"+state["result"], "approval", "Exact-scope semantic meaning is not currently approved for use.", owner)
            return b
        def document(ref, output=findings, op=None):
            e = manager.service.get(ref)
            relevant = [reference(subject)]
            relevant += [f[k] for f in root_scope["field_references"] for k in ("source_metadata_reference", "discovery_reference")]
            if (e["origin_verification"] != "verified_origin" or e["valid_until"] and now >= instant(e["valid_until"]) or
                    not any(r in relevant for r in e["relevant_subject_references"])):
                output.append(issue("unverified_documentary_evidence", "evidence", "Documentary evidence is expired, unverified or outside this exact physical/specification context.", operation_id=op))
        def evidence(items):
            if not items:
                add("missing_evidence", "evidence", "A specification or operation needs explicit supporting evidence.")
            for e in items:
                if e["kind"] == "documentary": document(e["record_reference"])
                elif e["kind"] == "approved_assertion":
                    b = binding(e["binding_reference"], subject)
                    a = manager.service.get(e["approval_reference"])
                    if manager.service._approval_state(a, now) != "usable" or not scope_contains(a["approval_scope"], narrow_scope(root_scope, b["physical_field_reference"])):
                        add("evidence_approval_not_usable", "approval", "Evidence's pinned semantic approval is no longer usable.", subject)
                elif e["discovery_reference"] not in [f["discovery_reference"] for f in root_scope["field_references"]]:
                    add("evidence_scope_mismatch", "evidence", "Evidence does not belong to the authorized physical snapshots.", subject)
        def visit(obj, own_approval=True):
            identity = digest(reference(obj))
            if identity in visited: return
            visited.add(identity)
            if not scope_contains(root_scope, obj["specification_scope"]):
                add("dependency_scope_mismatch", "specification", "Dependent specifications must fit the requesting purpose, namespace, physical scope and applicability.", obj)
            if own_approval:
                state = manager.specification_state(reference(obj), now)
                approvals.extend(state["approval_references"])
                if state["state"] != "approved":
                    add("specification_"+state["state"], "approval", "An exact specification revision lacks current explicit approval.", obj)
            evidence(obj["evidence_references"])
            kind = obj["contract_type"]
            if kind == "PredictionTargetSpecification":
                b = binding(obj["semantic_binding_reference"], obj)
                if b["interpretation"]["definition"] != obj["business_meaning"]:
                    add("conflicting_target_meaning", "specification", "Target meaning differs from its pinned semantic interpretation; resolve explicitly.", obj)
                if obj["target_grain"] != b["interpretation_scope"]["record_grain"] or obj["construction_requirements"]:
                    add("target_construction_unverified", "unsupported", "A native field meaning does not approve a new observation grain or derived target; a trusted derivation contract verifier is required.", obj)
                observed = manager.service._field(obj["physical_field_reference"])["observed"]
                physical = obj["physical_field_reference"]
                discovery = manager.runtime.catalogue.get(physical["discovery_reference"])
                table = next(t for t in discovery["tables"] if t["table_id"] == physical["table_id"])
                if not table["profile_complete"]:
                    add("incomplete_target_profile", "evidence", "A sampled profile cannot establish the full target population.", obj)
                if obj["value_type"] not in observed["type_counts"] or len(observed["type_counts"]) != 1:
                    add("target_type_unverified", "evidence", "Target physical type/mixed representation does not match the declared native outcome type.", obj)
                if not observed["nonmissing_count"]:
                    add("no_observed_target", "evidence", "No nonmissing target observation is evidenced.", obj)
                for c in obj["eligibility"] + obj["inclusion_criteria"] + obj["exclusion_criteria"]:
                    for r in c["binding_references"]: binding(r, obj)
                if obj["historical_boundaries"] is None and (obj["history_not_applicable_reason"] is None or obj["prediction_horizon"] is not None):
                    add("missing_target_history", "specification", "Historical applicability boundaries must be explicitly established.", obj)
                if obj["historical_boundaries"] is not None and obj["history_not_applicable_reason"] is not None:
                    add("conflicting_history_specification", "specification", "A historical interval and a not-applicable assertion conflict.", obj)
                requirement_ref = obj["requirement_reference"]
                if requirement_ref:
                    req = manager.service.get(requirement_ref)
                    if not scope_contains(root_scope, req["assessment_scope"]):
                        add("requirement_scope_mismatch", "specification", "The requirement is outside this specification scope.", obj)
                    if req.get("target_binding_reference") and req["target_binding_reference"] != obj["semantic_binding_reference"]:
                        add("requirement_target_mismatch", "specification", "The target conflicts with the requirement's exact binding selector.", obj)
                    if req.get("prediction_horizon") and req["prediction_horizon"] != obj["prediction_horizon"]:
                        add("requirement_horizon_mismatch", "specification", "Target and requested horizon differ.", obj)
            elif kind == "ObservationSpecification":
                target = manager.service.get(obj["target_reference"]); visit(target)
                if target["target_grain"] != obj["observation_grain"]:
                    add("target_observation_grain_mismatch", "specification", "Target and observation grains differ.", obj)
                if obj["alignment"]["mode"] != "native":
                    add("observation_construction_unverified", "unsupported", "Target-to-observation construction needs an approved verified derivation, never implicit alignment.", obj)
                for r in obj["entity_binding_references"]: binding(r, obj)
                for c in obj["eligibility"]:
                    for r in c["binding_references"]: binding(r, obj)
                if obj["historical_boundaries"] != target["historical_boundaries"]:
                    add("historical_boundary_mismatch", "specification", "Target and observation historical boundaries must agree exactly.", obj)
                non_temporal = (obj["time_not_applicable_reason"] is not None and obj["time_binding_reference"] is None and
                    obj["time_basis"] is None and obj["expected_frequency"] is None and obj["historical_boundaries"] is None and
                    obj["future_boundaries"] is None and obj["observation_period"] is None and target["prediction_horizon"] is None)
                if obj["time_not_applicable_reason"] is not None and not non_temporal:
                    add("conflicting_time_specification", "specification", "A not-applicable time assertion conflicts with temporal requirements or supplied time fields.", obj)
                if non_temporal:
                    pass  # Explicitly reviewed cross-sectional observations are not forecasts.
                elif (obj["time_binding_reference"] is None or obj["time_basis"] is None or obj["expected_frequency"] is None):
                    add("missing_observation_time", "specification", "Declare the observation time meaning, frequency and binding; no reporting period is guessed.", obj)
                else:
                    b = binding(obj["time_binding_reference"], obj)
                    physical = b["physical_field_reference"]
                    profile = manager.service._field(physical)["observed"]
                    counts = profile["temporal_token_counts"]
                    if (not counts or any(counts.get(k, 0) for k in ("ambiguous_day_month_text", "century_unresolved_text", "invalid_calendar_token", "invalid_period_token", "invalid_time_token")) or
                            sum(counts.values()) != profile["nonmissing_count"] or any(profile["missing_counts"].values())):
                        add("unresolved_observation_dates", "evidence", "Time metadata contains absent, ambiguous, invalid or uninterpreted values; no dates are resolved by this validator.", obj)
                    period = obj["historical_boundaries"]
                    if period:
                        low, high = profile["unambiguous_date_min"], profile["unambiguous_date_max"]
                        if low is None or high is None or period["start"] < low or (date.fromisoformat(period["end"])-timedelta(days=1)).isoformat() > high:
                            add("history_outside_evidence", "evidence", "The requested history exceeds the exact unambiguous source-date coverage.", obj)
                        if period["end"] > now.date().isoformat():
                            add("unmatured_history", "evidence", "Historical observations cannot extend into the future.", obj)
                    if table_key(physical) != table_key(target["physical_field_reference"]):
                        add("cross_table_time_alignment_unverified", "unsupported", "Time-to-target association is not proved by separate field approvals.", obj)
                if obj["observation_period"] != obj["historical_boundaries"]:
                    add("observation_period_mismatch", "specification", "Observation and historical periods need one explicit compatible interval.", obj)
                future, history = obj["future_boundaries"], obj["historical_boundaries"]
                periods = [p for p in (future, history, obj["observation_period"]) if p]
                if len({p["calendar_reference"] for p in periods}) > 1:
                    add("calendar_mismatch", "specification", "Observation boundaries must use one explicit compatible calendar.", obj)
                if future and history and future["start"] < history["end"]:
                    add("temporal_boundary_overlap", "leakage", "Historical and future observation windows overlap.", obj)
                if target["prediction_horizon"] and not future:
                    add("missing_future_boundary", "specification", "A forecast horizon requires explicit future applicability boundaries.", obj)
                if target["prediction_horizon"] and target["prediction_horizon"]["unit"] != obj["expected_frequency"]:
                    add("horizon_frequency_mismatch", "specification", "A frequency/horizon conversion requires a separately reviewed time specification; no resampling is assumed.", obj)
                if future and target["prediction_horizon"] and target["prediction_horizon"]["unit"] == "day":
                    if (date.fromisoformat(future["end"]) - date.fromisoformat(future["start"])).days != target["prediction_horizon"]["steps"]:
                        add("horizon_boundary_mismatch", "specification", "The future daily interval differs from the explicit horizon.", obj)
                for r in obj["relationship_references"]: visit(manager.service.get(r))
            elif kind == "RelationshipSpecification":
                sides = []
                for key in ("left_key_bindings", "right_key_bindings"):
                    bs = [binding(r, obj) for r in obj[key]]; sides.append(bs)
                    if len({table_key(b["physical_field_reference"]) for b in bs}) != 1:
                        add("relationship_key_scope_mismatch", "specification", "A composite relationship key must come from one exact table snapshot per side.", obj)
                if any(b["interpretation_scope"]["record_grain"] != obj[g] for bs, g in zip(sides, ("left_grain", "right_grain")) for b in bs):
                    add("relationship_grain_mismatch", "specification", "Relationship side grains differ from their reviewed field meanings.", obj)
                if obj["cardinality"] == "unknown" or not obj["reconciliation_checks"]:
                    add("relationship_evidence_incomplete", "evidence", "Relationship cardinality and row/distinct/measure reconciliation expectations require owner evidence.", obj)
                if not any(e["kind"] == "documentary" for e in obj["evidence_references"]):
                    add("relationship_claim_unverified", "evidence", "A relationship requires contextual owner evidence beyond matching names, values or unique fields.", obj)
            elif kind == "DataPreparationPlanSpecification":
                target = manager.service.get(obj["target_reference"]); visit(target)
                observation = manager.service.get(obj["observation_reference"]); visit(observation)
                if observation["target_reference"] != obj["target_reference"]:
                    add("plan_target_conflict", "specification", "Plan and observation must reference the same exact target revision.", obj)
                if obj["output_grain"] != observation["observation_grain"]:
                    add("plan_observation_grain_mismatch", "specification", "Plan output and observation grains differ.", obj)
                if obj["unresolved_decisions"]:
                    add("unresolved_business_decisions", "approval", "Plan retains unresolved business decisions.", obj)
                if not obj["quality_checks"] or not obj["leakage_controls"]:
                    add("missing_validation_controls", "specification", "Declare data quality and information-availability/leakage controls.", obj)
                for r in obj["relationship_references"]: visit(manager.service.get(r))
                declared = {field_key(f) for f in obj["source_references"]}
                if field_key(target["physical_field_reference"]) not in declared:
                    add("target_source_not_declared", "specification", "Plan source manifest omits its physical target.", obj)
                required_bindings = observation["entity_binding_references"] + ([observation["time_binding_reference"]] if observation["time_binding_reference"] else [])
                required_bindings += [r for c in observation["eligibility"] + target["eligibility"] + target["inclusion_criteria"] + target["exclusion_criteria"] for r in c["binding_references"]]
                if any(field_key(manager.service.get(r)["physical_field_reference"]) not in declared for r in required_bindings):
                    add("observation_source_not_declared", "specification", "The source manifest must include explicit time, entity and eligibility dependencies.", obj)
                if obj["input_grain"] != obj["specification_scope"]["record_grain"]:
                    add("plan_input_grain_mismatch", "specification", "Plan input grain differs from the explicitly authorized source grain.", obj)
                grain, done = obj["input_grain"], []
                connected = {table_key(target["physical_field_reference"])}
                for op in obj["operations"]:
                    oid = op["operation_id"]
                    if oid in done or set(op["depends_on"]) - set(done) or done and done[-1] not in op["depends_on"]:
                        add("invalid_operation_dependencies", "specification", "Operations require distinct IDs and an explicit preceding serial dependency chain; forward/cyclic branches are unsupported.", obj, oid)
                    if op["input_grain"] != grain:
                        add("operation_grain_mismatch", "specification", "Operation input grain does not match its predecessor output.", obj, oid)
                    if not op["purpose"] or not op["required_approvals"] or not set(op["required_approvals"]) <= set(obj["required_approvals"]):
                        add("operation_approval_not_declared", "approval", "Operation approval requirements must be included in the frozen plan review.", obj, oid)
                    evidence(op["evidence_references"])
                    opfields = {field_key(f) for f in op["source_references"]}
                    if not opfields or not opfields <= declared:
                        add("operation_source_not_declared", "specification", "Operation physical sources must be an explicit subset of the plan manifest.", obj, oid)
                    for r in op["input_binding_references"]:
                        b = binding(r, obj); field = b["physical_field_reference"]
                        if field_key(field) not in opfields:
                            add("operation_input_not_declared", "specification", "Input meanings must be pinned to the operation's physical manifest.", obj, oid)
                        if op["information_role"] == "predictor" and field_key(field) == field_key(target["physical_field_reference"]):
                            add("target_as_predictor", "leakage", "A target alias cannot become an available predictor.", obj, oid)
                    if op["information_role"] == "predictor" and op["availability"] != "before_decision":
                        add("predictor_availability_unverified", "leakage", "Predictor availability must be established before the decision time.", obj, oid)
                    for r in op["relationship_references"]:
                        if r not in obj["relationship_references"]:
                            add("relationship_not_declared", "approval", "Operation relationship is absent from the plan's dependency manifest.", obj, oid)
                    validator = self.operations.get(op["operation_type"], op["operation_version"])
                    if validator is None:
                        add("unsupported_operation", "unsupported", "No trusted validator supports this exact operation type/version.", obj, oid)
                    else:
                        context = {"resolver": manager.runtime.catalogue.resolve, "check_document": document}
                        findings.extend(validator.validate(op, context))
                        if op["output_grain"] != op["input_grain"] and not validator.permits_grain_change:
                            add("unsupported_grain_change", "specification", "This operation cannot declare a change in record grain.", obj, oid)
                        if op["output_grain"] != op["input_grain"] and op is not obj["operations"][-1]:
                            add("grain_change_must_be_terminal", "unsupported", "A grain-changing operation must be the final worker step; downstream field rebinding requires a new discovery and approved semantic bindings.", obj, oid)
                    tables = {table_key(f) for f in op["source_references"]}
                    if op["operation_type"] == "join" and validator:
                        if not op["relationship_references"]:
                            add("join_without_relationship", "approval", "No reviewed relationship dependency is declared.", obj, oid)
                        else:
                            allowed_tables = set()
                            for r in op["relationship_references"]:
                                relation = manager.service.get(r); visit(relation)
                                allowed_tables |= {table_key(manager.service.get(b)["physical_field_reference"]) for b in relation["left_key_bindings"] + relation["right_key_bindings"]}
                            if not tables <= allowed_tables or not tables & connected:
                                add("join_source_scope_mismatch", "specification", "A join cannot connect an unrelated source beyond its reviewed relationship sides.", obj, oid)
                            connected |= tables
                    elif not tables <= connected:
                        add("implicit_cross_table_operation", "unsupported", "Independent source tables cannot be mixed without a preceding approved explicit join declaration.", obj, oid)
                    grain = op["output_grain"]; done.append(oid)
                if grain != obj["output_grain"]:
                    add("final_grain_mismatch", "specification", "The operation chain does not produce the plan's declared output grain.", obj)
        visit(subject, require_approval)
        # A later published snapshot never inherits prior approvals, even when
        # physical positions/names remain unchanged. Historical records survive.
        catalogue_documents = manager.runtime.catalogue.export_documents()
        for field in root_scope["field_references"]:
            for meta in catalogue_documents:
                if (meta["contract_type"] == "DataSourceMetadata" and meta["object_id"] == field["source_metadata_reference"]["object_id"]
                        and meta["object_revision"] > field["source_metadata_reference"]["object_revision"]):
                    add("source_snapshot_changed", "approval", "A newer source metadata revision is known; review exact snapshots before reusing this specification.", subject)
                    break
                if (meta["contract_type"] == "SchemaDiscoveryResult" and meta["source_reference"]["object_id"] == field["source_metadata_reference"]["object_id"]
                        and meta["object_revision"] > field["discovery_reference"]["object_revision"]):
                    add("schema_snapshot_changed", "approval", "A later discovery revision requires explicit compatibility review; approval is not transferred.", subject)
                    break
        unique = {digest(f): f for f in findings}
        return {"findings": list(unique.values()), "approval_references": list({digest(a): a for a in approvals}.values())}
