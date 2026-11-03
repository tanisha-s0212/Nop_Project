"""Scoped, version-aware relevance using exact semantic selectors and profiles."""

from ..contracts import reference
from ..semantics.common import digest, field_key, clone, scope_contains
from .intake import supplied


def narrow_scope(scope, field):
    result = clone(scope)
    result["field_references"] = [field]
    return result


class DataRelevanceAssessor:
    def candidates(self, requirement, service, catalogue, now):
        scope = requirement["assessment_scope"]
        concepts = supplied(requirement, "requested_concepts", [])
        selected = supplied(requirement, "target_binding_reference")
        structural = not concepts and selected is None
        bindings = service.records("SemanticBinding")
        evidence = service.records("PredictionDataEvidence")
        result = []
        for field in scope["field_references"]:
            observed = service._field(field)
            discovery = catalogue.get(field["discovery_reference"])
            table_profile = next(t for t in discovery["tables"] if t["table_id"] == field["table_id"])
            profile = {**clone(observed["observed"]), "profile_complete": table_profile["profile_complete"],
                       "observed_row_count": table_profile["observed_row_count"], "scanned_row_count": table_profile["scanned_row_count"]}
            matches = []
            for binding in bindings:
                if selected is not None and reference(binding) != selected:
                    continue
                if selected is None and concepts and binding["interpretation"]["concept"] not in concepts:
                    continue
                if structural:
                    continue
                bound = binding["physical_field_reference"]
                exact = field_key(bound) == field_key(field)
                old_position = (bound["source_metadata_reference"]["object_id"] == field["source_metadata_reference"]["object_id"] and
                                bound["table_id"] == field["table_id"] and bound["field_id"] == field["field_id"])
                if not exact and not old_position:
                    continue
                candidate_scope = narrow_scope(scope, field)
                inspection = service.inspect_binding_use(reference(binding), scope=candidate_scope, physical_field=field, now=now)
                matches.append((binding, inspection["result"], "exact_semantic_binding" if exact else "prior_snapshot_hypothesis",
                                [reference(a) for a in inspection["approvals"]]))
            if structural:
                kind = supplied(requirement, "desired_output", {}).get("value_kind")
                types = set(observed["observed"]["type_counts"])
                if kind not in ("numeric", "count") or types and types <= {"integer", "float", "decimal"}:
                    matches = [(None, "unverified", "structural_only", [])]
            for binding, state, basis, approval_refs in matches:
                binding_ref = reference(binding) if binding else None
                result.append({"candidate_id": digest({"field": field, "binding": binding_ref}),
                    "physical_field_reference": field, "binding_reference": binding_ref, "semantic_state": state,
                    "approval_references": approval_refs,
                    "relevance_basis": basis, "observed_metadata": profile,
                    "data_evidence_references": [reference(e) for e in evidence if e["binding_reference"] == binding_ref and e["physical_field_reference"] == field
                                                 and scope_contains(scope, e["assessment_scope"])],
                    "supporting_evidence": clone(binding["evidence_references"]) if binding else [],
                    "limitations": ["Typed similarity is not business meaning."] if binding is None else
                        ["Prior positional continuity does not approve this snapshot."] if basis == "prior_snapshot_hypothesis" else []})
        return result

    def select(self, requirement, candidates):
        explicit = supplied(requirement, "target_binding_reference")
        if explicit is not None:
            matches = [c for c in candidates if c["binding_reference"] == explicit]
        else:
            usable = [c for c in candidates if c["semantic_state"] == "usable"]
            matches = usable if usable else [c for c in candidates if c["binding_reference"] is not None]
        return matches[0] if len(matches) == 1 else None, len(matches)
