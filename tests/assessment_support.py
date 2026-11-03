"""Independent synthetic schemas and explicit, attributed evidence for assessment."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig
from business_prediction.discovery import discover
from business_prediction.contracts import reference
from business_prediction.runtime import RuntimeConfig, AdapterFactories, start_runtime
from business_prediction.runtime.development import DevelopmentIdentityProvider, DevelopmentAuthorizationProvider, DevelopmentGrant
from business_prediction.runtime.secrets import EnvironmentSecrets
from business_prediction.semantics import ReviewPolicy
from tests.semantic_support import evidence_ref


class AssessmentFixture:
    def __init__(self, directory, *, categorical=False, headers=None, table_name="pane-R", missing=False,
                 ambiguous_dates=False, concept="metric.any", source_id="assessment-source", uninterpreted_dates=False,
                 input_missing=False, extra_table=False):
        self.now = datetime(2026, 11, 2, 9, tzinfo=timezone.utc)
        self.prefix, self.counter = str(uuid4()), 0
        self.concept = concept
        headers = headers or ("north_metric_Ω", "axis9", "clock_opaque", "extra_value")
        rows = [headers]
        for i in range(20):
            value = bool(i % 2) if categorical else float(i+1)
            if missing and i == 0: value = None
            stamp = "03/04/2026" if ambiguous_dates and i == 0 else date(2026, 1, i+1)
            if uninterpreted_dates and i == 0: stamp = 45000
            rows.append((value, None if input_missing and i == 0 else float(i*2+1), stamp, float(i+100)))
        tables = [MemoryTable(table_name, tuple(rows))]
        if extra_table: tables.append(MemoryTable("independent_grid", (("independent",), (17.0,), (19.0,))))
        adapter = MemoryAdapter(SourceConfig(source_id, "synthetic-owner", "assessment-test"), tables)
        self.bundle = discover(adapter)
        d = self.bundle.discovery_result
        self.fields = [{"source_metadata_reference": reference(self.bundle.source_metadata), "discovery_reference": reference(d),
            "source_version": d["source_version"], "schema_version": d["schema_version"], "table_id": t["table_id"],
            "field_id": f["field_id"], "field_position": f["position"]} for t in d["tables"] for f in t["fields"]]
        self.scope = {"purpose": "assessment-test", "namespace": "fixture-space", "record_grain": "source-record",
            "assertion_use": "semantic_interpretation", "field_references": self.fields,
            "business_period": None, "period_not_applicable_reason": "No business period restriction asserted in this synthetic fixture."}
        self.environment = {"AUTHOR": "synthetic-assessment-author-secret", "OWNER": "synthetic-assessment-owner-secret",
                            "STRANGER": "synthetic-assessment-stranger-secret", "KEY": "synthetic-assessment-signing-key-012345678901234567890"}
        self.author, self.owner, self.stranger = (self.environment[k] for k in ("AUTHOR", "OWNER", "STRANGER"))
        secrets = EnvironmentSecrets(self.environment)
        def grant(actor, actions, name):
            return DevelopmentGrant(name, actor, tuple(actions), self.scope, (self.now-timedelta(days=1)).isoformat(), (self.now+timedelta(days=100)).isoformat())
        self.grants = [grant("author", ("propose_binding", "submit_review", "submit_requirement", "register_evidence"), "author"),
            grant("owner", ("approve", "reject", "request_clarification", "revoke", "supersede", "assess_use", "assess_change",
                            "assess_requirement", "register_prediction_evidence"), "owner")]
        factories = AdapterFactories({}, {"identity": lambda c,s: DevelopmentIdentityProvider(
            {"author": "env:AUTHOR", "owner": "env:OWNER", "stranger": "env:STRANGER"}, s)},
            {"authority": lambda c,s: DevelopmentAuthorizationProvider(self.grants, s, "env:KEY")})
        config = RuntimeConfig("development", "sqlite", "identity", "authority", sqlite_path=str(Path(directory)/"assessment.sqlite3"),
            credential_strategy="secret_references", secret_references=("env:AUTHOR", "env:OWNER", "env:STRANGER", "env:KEY"))
        self.runtime = start_runtime(config, ReviewPolicy("assessment-policy", "1"), factories, secrets, clock=lambda:self.now)
        self.service, self.engine = self.runtime.service, self.runtime.requirement_assessment_engine()
        if self.runtime.catalogue.resolve(reference(d)) is None:
            self.bundle.publish(self.runtime.catalogue)
        existing = self.service.records("SemanticBinding")
        if existing:
            self.target = next(b for b in existing if b["object_id"] == "target")
            self.input = next(b for b in existing if b["object_id"] == "input")
            self.time = next(b for b in existing if b["object_id"] == "time")
        else:
            self.target = self.bind(0, concept, "target")
            self.input = self.bind(1, "context.any", "input")
            self.time = self.bind(2, "clock.any", "time")

    def cmd(self):
        self.counter += 1
        return self.prefix+":"+str(self.counter)

    def bind(self, position, concept, name, *, approve=True):
        scope = deepcopy(self.scope); scope["field_references"] = [self.fields[position]]
        binding = self.service.propose_binding(object_id=name, physical_field_reference=self.fields[position],
            interpretation={"concept": concept, "definition": "An explicitly reviewed synthetic field interpretation.",
                            "definition_version": "1", "definition_reference": None}, scope=scope,
            evidence=[evidence_ref("observation", discovery_reference=reference(self.bundle.discovery_result),
                field_id=self.fields[position]["field_id"], evidence_id=self.fields[position]["field_id"]+":profile")],
            context=self.author, command_id=self.cmd(), expected_head=self.service.head)
        if approve: self.approve(binding)
        return binding

    def approve(self, binding):
        req = self.service.submit_review(reference(binding), scope=binding["interpretation_scope"], context=self.author,
            command_id=self.cmd(), expected_head=self.service.head, expires_at=(self.now+timedelta(days=30)).isoformat(),
            review_due_at=(self.now+timedelta(days=25)).isoformat())
        result = self.service.decide(reference(req), reference(binding), action="approve", context=self.owner,
            rationale="Synthetic owner confirmation only.", command_id=self.cmd(), expected_head=self.service.head)
        return self.service.get(result["approval_reference"])

    def fields_for(self, family="forecasting", **changes):
        fields = {"business_outcome": "A previously unseen organizational objective supplied as structured metadata.",
            "business_context": "Synthetic fixture only", "requested_concepts": [self.concept],
            "intent": "future" if family == "forecasting" else "unknown_outcome", "observation_granularity": "source-record",
            "desired_output": {"value_kind": "categorical" if family == "classification" else "numeric"},
            "decision_time_basis": "before_the_requested_outcome", "history_requirements": {"minimum_observations": 10, "validation_observations": 5}}
        if family == "forecasting":
            fields["prediction_horizon"] = {"steps": 2, "unit": "day"}
            fields["time_binding_reference"] = reference(self.time)
        if family == "classification": fields["history_requirements"]["minimum_per_class"] = 2
        if family in ("classification", "regression"): fields["input_binding_references"] = [reference(self.input)]
        if family == "analytics": fields["intent"] = "historical"
        fields.update(changes)
        return fields

    def submit(self, fields=None, **changes):
        return self.engine.submit_requirement(fields if fields is not None else self.fields_for(), scope=self.scope,
            context=self.author, command_id=self.cmd(), expected_head=self.service.head, **changes)

    def data(self, family="forecasting", **changes):
        observed = self.bundle.discovery_result["tables"][0]["fields"][0]["observed"]
        time_obs = self.bundle.discovery_result["tables"][0]["fields"][2]["observed"]
        facts = {"time_binding_reference": reference(self.time) if family == "forecasting" else None,
            "input_binding_references": [reference(self.input)] if family in ("regression", "classification") else [],
            "observation_grain": "source-record", "observation_frequency": "day" if family == "forecasting" else None,
            "observation_count": 20, "nonmissing_count": observed["nonmissing_count"], "mature_observations": observed["nonmissing_count"],
            "history_start": time_obs["unambiguous_date_min"] if family == "forecasting" else None,
            "history_end": time_obs["unambiguous_date_max"] if family == "forecasting" else None,
            "class_counts": [{"value_type": "boolean", "value_repr": "false", "count": 10}, {"value_type": "boolean", "value_repr": "true", "count": 10}] if family == "classification" else [],
            **{k: True for k in ("target_observable", "grain_verified", "cadence_complete", "chronology_verified", "population_verified",
                "negative_outcomes_verified", "availability_verified", "validation_verified", "independence_verified")},
            "input_mode": "history_only" if family == "forecasting" else "explicit_inputs", "leakage_findings": [],
            "decision_time_basis": "before_the_requested_outcome", "validation_scheme": "chronological" if family == "forecasting" else "grouped_independent",
            "label_horizon": None,
            "limitations": ["Authorized synthetic summary, not a model evaluation."], "method_reference": "synthetic-full-profile-v1"}
        facts.update(changes)
        return self.engine.register_data_evidence(reference(self.target), facts, scope=self.scope, context=self.owner,
            command_id=self.cmd(), expected_head=self.service.head, valid_until=(self.now+timedelta(days=20)).isoformat())

    def assess(self, requirement, **changes):
        args = {"context": self.owner, "command_id": self.cmd(), "expected_head": self.service.head}
        args.update(changes)
        return self.engine.assess(reference(requirement), **args)
