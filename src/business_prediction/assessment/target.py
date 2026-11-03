"""Target grounding and symbolic construction requirements; no target values."""

from .intake import supplied, finding


class TargetAssessor:
    def assess(self, requirement, candidates, relevance, service):
        selected, count = relevance.select(requirement, candidates)
        issues, construction = [], []
        if any(c["semantic_state"] == "conflict" for c in candidates):
            issues.append(finding("conflicting_semantic_assertions", "approval",
                "Competing approved assertions require explicit owner resolution; selecting a recent record does not resolve them."))
        if count > 1:
            issues.append(finding("multiple_candidate_targets", "clarification",
                                  "Several candidate meanings fit; choose an exact target or clarify its scope."))
        elif selected is None:
            issues.append(finding("target_not_established", "evidence",
                                  "No uniquely grounded target is established in the authorized current data."))
        else:
            ref = selected["binding_reference"]
            binding = service.get(ref) if ref else None
            concepts = supplied(requirement, "requested_concepts")
            if binding and concepts and binding["interpretation"]["concept"] not in concepts:
                issues.append(finding("contradictory_target_selectors", "clarification",
                                     "The exact target binding and requested concepts disagree.", ref))
            grain = supplied(requirement, "observation_granularity")
            if (supplied(requirement, "construction_request") is not None or
                    binding and grain is not None and grain != binding["interpretation_scope"]["record_grain"]):
                construction.append("Define and approve a target/observation construction contract at the requested grain; no construction was executed.")
                issues.append(finding("target_construction_required", "approval",
                    "Requested target grain/derivation is not an approved native field observation.", ref))
        return {"selected": selected, "findings": issues, "construction_requirements": construction}
