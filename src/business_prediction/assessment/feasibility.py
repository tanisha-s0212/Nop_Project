"""Conservative evidence gates; readiness is not training permission or accuracy."""

from datetime import date

from ..contracts import reference
from ..semantics.common import field_key, instant
from .intake import supplied, finding
from .relevance import narrow_scope


class FeasibilityEvaluator:
    def evaluate(self, requirement, candidate, strategy, data, service, now):
        issues, risks, construction = [], [], []
        binding_ref = candidate["binding_reference"]
        def block(code, category, message):
            issues.append(finding(code, category, message, binding_ref))
        if candidate["semantic_state"] != "usable":
            block("semantic_"+candidate["semantic_state"], "approval", "The exact target interpretation is not currently usable for this scope/snapshot.")
        obs = candidate["observed_metadata"]
        if not obs["profile_complete"]:
            block("incomplete_discovery_profile", "evidence", "Sampled metadata does not establish complete target population or coverage.")
        missing = sum(obs["missing_counts"].values())
        constraints = supplied(requirement, "constraints", {})
        supported = {"maximum_target_missing_fraction", "external_dependencies", "required_identifier_bindings"}
        if strategy is not None:
            supported |= set(strategy.supported_constraints)
        if set(constraints) - supported:
            block("unsupported_constraint", "unsupported", "Some constraints have no registered assessment semantics; they are not silently ignored.")
        if "maximum_target_missing_fraction" in constraints and obs["observed_row_count"]:
            fraction = missing / obs["scanned_row_count"] if obs["scanned_row_count"] else None
            if fraction is None or fraction > constraints["maximum_target_missing_fraction"]:
                block("missingness_exceeds_constraint", "evidence", "Observed missingness exceeds the supplied assessment tolerance; no treatment is executed.")
        for dependency in constraints.get("external_dependencies", []):
            ref = dependency["evidence_reference"]
            if ref is None:
                block("external_dependency_unverified", "evidence", "A required external dependency has no verified evidence.")
            else:
                record = service.get(ref)
                allowed = [f["source_metadata_reference"] for f in requirement["assessment_scope"]["field_references"]] + [f["discovery_reference"] for f in requirement["assessment_scope"]["field_references"]] + ([binding_ref] if binding_ref else [])
                if (record["origin_verification"] != "verified_origin" or record["valid_until"] and now >= instant(record["valid_until"])
                        or not any(r in allowed for r in record["relevant_subject_references"])):
                    block("external_dependency_unverified", "evidence", "External dependency evidence is unverified, expired or outside this exact source context.")
                else:
                    block("external_dependency_availability_unverified", "evidence", "Verified documentary origin is not proof that an external dependency is available; a trusted availability verifier is still required.")
        for ref in constraints.get("required_identifier_bindings", []):
            binding = service.get(ref); field = binding["physical_field_reference"]
            state = service.inspect_binding_use(ref, scope=narrow_scope(requirement["assessment_scope"], field), physical_field=field, now=now)["result"]
            if state != "usable":
                block("identifier_semantics_"+state, "approval", "Required identifier meaning/scope is not currently approved.")
            if any(service._field(field)["observed"]["missing_counts"].values()):
                block("identifier_missingness", "evidence", "A required identity field has missing values; no identifier is invented.")
            risks.append("identifier_meaning_does_not_confirm_a_primary_key")
        if missing:
            risks.append("target_missingness")
            block("missing_target_treatment", "approval", "Missing target observations require an explicit treatment/eligibility decision; no values or rows are replaced.")
        if obs["nonfinite_numeric_count"] or set(obs["type_counts"]) & {"formula", "cell_error"}:
            block("unusable_target_values", "evidence", "Nonfinite/formula/error target values need additional evidence; they are not business zeros.")
        if obs["nonmissing_count"] == 0:
            block("no_observed_outcomes", "evidence", "No nonmissing target values are observed.")
        grain = supplied(requirement, "observation_granularity")
        if strategy is None:
            return issues, risks, construction
        family = strategy.problem_type
        if family in ("forecasting", "regression") and (not set(obs["type_counts"]) or not set(obs["type_counts"]) <= {"integer", "float", "decimal"}):
            block("numeric_representation_unverified", "approval", "Numerical prediction requires an approved native numerical outcome; raw text is not automatically parsed.")
        if strategy.work_type == "analytics":
            return issues, risks, construction
        history = supplied(requirement, "history_requirements", {})
        for key in ("minimum_observations", "validation_observations"):
            if key not in history:
                block("missing_"+key, "clarification", "Specify the historical/validation support required for this target, not a universal row threshold.")
        if supplied(requirement, "decision_time_basis") is None:
            block("missing_decision_time", "clarification", "Define when the prediction is made and which input information may be known then.")
        horizon = supplied(requirement, "prediction_horizon")
        if supplied(requirement, "intent") == "future" and horizon is None:
            block("missing_horizon", "clarification", "Specify the future prediction horizon and unit.")
        if data is None:
            block("missing_observation_evidence", "evidence", "Discovery counts do not establish mature history, labelled cohorts, availability or validation support; obtain authorized profiling evidence.")
            return issues, risks, construction
        if supplied(requirement, "decision_time_basis") is not None and data["decision_time_basis"] != requirement["decision_time_basis"]:
            block("decision_time_evidence_mismatch", "evidence", "Evidence was established for a different decision-time information boundary.")
        if supplied(requirement, "intent") == "future" and (data["validation_scheme"] != "chronological" or not data["chronology_verified"]):
            block("chronological_validation_unverified", "evidence", "Future decisions require a defensible chronological validation design.")
        if not data["target_observable"]:
            block("outcome_not_observable", "evidence", "The requested outcome is not established as observed; similarly named values are insufficient.")
        if not data["grain_verified"] or grain is not None and data["observation_grain"] != grain:
            block("observation_grain_unverified", "approval", "The exact record-to-observation interpretation is not established at the requested grain.")
        for key in ("population_verified", "availability_verified", "validation_verified", "independence_verified"):
            if not data[key]:
                block(key+"_missing", "evidence", "Required population, decision-time availability, independence or validation evidence is missing.")
        train, validation = history.get("minimum_observations"), history.get("validation_observations")
        if train is not None and validation is not None:
            required = train+validation
            if family == "forecasting" and horizon is not None:
                required = train+max(validation, horizon["steps"])
            if data["mature_observations"] < required:
                block("insufficient_mature_observations", "evidence", "Mature independent observations cannot support the requested training/holdout/horizon requirements.")
        if data["leakage_findings"]:
            risks.extend(data["leakage_findings"])
            block("documented_leakage_risk", "evidence", "Recorded leakage concerns must be resolved before proceeding.")
        inputs = supplied(requirement, "input_binding_references", data["input_binding_references"])
        if inputs != data["input_binding_references"]:
            block("input_contract_mismatch", "evidence", "Requested inputs differ from the evidence's pinned availability contract.")
        if (family in ("regression", "classification") or data["input_mode"] == "explicit_inputs") and not inputs:
            block("missing_predictor_evidence", "evidence", "Supervised unknown-outcome prediction requires defensible decision-time inputs.")
        target = candidate["physical_field_reference"]
        for input_ref in inputs:
            input_binding = service.get(input_ref)
            field = input_binding["physical_field_reference"]
            if field_key(field) == field_key(target):
                risks.append("target_as_input")
                block("target_leakage", "evidence", "The target's physical field cannot be its own decision-time predictor through another alias.")
            if field["discovery_reference"] != target["discovery_reference"] or field["table_id"] != target["table_id"]:
                block("unapproved_join_dependency", "approval", "Cross-table inputs require an approved grain/relationship contract; no join is inferred or performed.")
            state = service.inspect_binding_use(input_ref, scope=narrow_scope(requirement["assessment_scope"], field), physical_field=field, now=now)["result"]
            if state != "usable":
                block("input_semantics_"+state, "approval", "An input interpretation lacks current exact-scope approval.")
            profile = service._field(field)["observed"]
            if profile["nonmissing_count"] == 0:
                block("missing_feature_values", "evidence", "A required input has no observed usable values.")
            if any(profile["missing_counts"].values()):
                block("input_missing_treatment", "approval", "Input missingness requires a separately approved preparation treatment.")
        if family == "classification":
            if supplied(requirement, "intent") == "future" and (horizon is None or data["label_horizon"] != horizon):
                block("label_window_mismatch", "evidence", "Positive/negative outcome evidence must cover the exact requested future window.")
            classes = data["class_counts"]
            if len(classes) < 2:
                block("insufficient_outcome_classes", "evidence", "At least two observed outcome classes are needed for classification assessment.")
            if not data["negative_outcomes_verified"]:
                block("negative_outcomes_unverified", "evidence", "Absent events are not negative labels; verified eligible and mature outcome observations are required.")
            minimum = history.get("minimum_per_class")
            if minimum is None:
                block("missing_class_support_requirement", "clarification", "Specify required per-class support for development and validation.")
            elif classes and min(c["count"] for c in classes) < max(minimum, 2):
                block("insufficient_class_support", "evidence", "Observed class support is below the requested minimum.")
            if classes and len({c["count"] for c in classes}) > 1:
                risks.append("unequal_class_distribution")
        if family == "forecasting" or supplied(requirement, "intent") == "future":
            time_ref = supplied(requirement, "time_binding_reference", data["time_binding_reference"])
            if time_ref is None or time_ref != data["time_binding_reference"]:
                block("missing_time_contract", "approval", "A matching approved event/observation time binding is required.")
            else:
                time_binding = service.get(time_ref); time_field = time_binding["physical_field_reference"]
                state = service.inspect_binding_use(time_ref, scope=narrow_scope(requirement["assessment_scope"], time_field), physical_field=time_field, now=now)["result"]
                if state != "usable":
                    block("time_semantics_"+state, "approval", "Observation-time meaning is not currently approved.")
                temporal = service._field(time_field)["observed"]
                counts = temporal["temporal_token_counts"]
                if (not counts or any(n for key, n in counts.items() if key in ("ambiguous_day_month_text", "century_unresolved_text", "invalid_calendar_token", "invalid_period_token", "invalid_time_token"))):
                    block("unresolved_temporal_values", "evidence", "Ambiguous, impossible or century-dependent times remain unresolved; no conversion is assumed.")
                if sum(counts.values()) != temporal["nonmissing_count"] or any(temporal["missing_counts"].values()):
                    block("uninterpreted_temporal_values", "evidence", "Some time values are absent or have no evidenced temporal interpretation; partial ranges are insufficient.")
                if data["history_start"] != temporal["unambiguous_date_min"] or data["history_end"] != temporal["unambiguous_date_max"]:
                    block("history_bounds_unverified", "evidence", "Claimed history does not reconcile with the exact unambiguous discovery bounds.")
                if time_field["discovery_reference"] != target["discovery_reference"] or time_field["table_id"] != target["table_id"]:
                    block("time_join_unapproved", "approval", "Time-to-target association would require an unapproved cross-table join.")
            if family == "forecasting" and (not data["cadence_complete"] or not data["chronology_verified"]):
                block("incomplete_temporal_support", "evidence", "Chronology or complete observation buckets/gaps have not been verified; missing activity is not zero.")
            if family == "forecasting" and horizon and horizon["unit"] != data["observation_frequency"]:
                block("horizon_frequency_mismatch", "clarification", "Horizon and observed frequency require an explicit compatible time contract; no resampling is assumed.")
            if data["history_end"] is None or date.fromisoformat(data["history_end"]) > now.date():
                block("unmatured_history", "evidence", "Future or unknown history bounds do not establish realized mature outcomes.")
        issues.extend(strategy.additional_findings(requirement, candidate, data))
        return issues, risks, construction
