"""Synthetic local worker fixtures using real sealed files, never NOP data."""

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
from uuid import uuid4

from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig, CSVAdapter
from business_prediction.contracts import reference
from business_prediction.discovery import discover
from business_prediction.runtime import RuntimeConfig, AdapterFactories, start_runtime
from business_prediction.runtime.development import DevelopmentIdentityProvider, DevelopmentAuthorizationProvider, DevelopmentGrant
from business_prediction.runtime.secrets import EnvironmentSecrets
from business_prediction.semantics import ReviewPolicy
from business_prediction.worker.storage import LocalArtifactStorage
from tests.specification_support import SpecificationFixture


class WorkerFixture(SpecificationFixture):
    def __init__(self, directory, *, text_input=False, csv_source=False, categorical=False, headers=None):
        self.directory = Path(directory); self.now = datetime(2026,11,2,9,tzinfo=timezone.utc)
        self.prefix,self.counter = str(uuid4()),0; self.concept = "owner.dynamic-outcome"
        headers = headers or ("signal-X","context-A","event-T","other-Z")
        rows = [headers]+[(bool(i%2) if categorical else float(i+1),str(i) if text_input else float(i),date(2026,1,i+1),float(i+100)) for i in range(20)]
        config = SourceConfig("worker-synthetic-source","synthetic-owner","assessment-test")
        self.source_file = None
        if csv_source:
            self.source_file = self.directory/"synthetic.csv"
            if not self.source_file.exists():
                import csv
                with self.source_file.open("w",encoding="utf-8",newline="") as stream: csv.writer(stream).writerows(rows)
            self.adapter = CSVAdapter(self.source_file,config)
        else: self.adapter = MemoryAdapter(config,[MemoryTable("unfamiliar-source-grid",tuple(rows))])
        self.bundle = discover(self.adapter); d = self.bundle.discovery_result
        self.fields = [{"source_metadata_reference":reference(self.bundle.source_metadata),"discovery_reference":reference(d),"source_version":d["source_version"],
            "schema_version":d["schema_version"],"table_id":t["table_id"],"field_id":f["field_id"],"field_position":f["position"]} for t in d["tables"] for f in t["fields"]]
        self.scope = {"purpose":"assessment-test","namespace":"worker-synthetic-space","record_grain":"source-record","assertion_use":"semantic_interpretation",
            "field_references":self.fields,"business_period":None,"period_not_applicable_reason":"Explicit synthetic scope only."}
        self.environment = {"AUTHOR":"synthetic-author-secret","OWNER":"synthetic-owner-secret","STRANGER":"synthetic-stranger-secret","KEY":"synthetic-worker-key-012345678901234567890123456789"}
        self.author,self.owner,self.stranger = (self.environment[k] for k in ("AUTHOR","OWNER","STRANGER"))
        secret = EnvironmentSecrets(self.environment)
        author_actions = ("propose_binding","submit_review","register_evidence","propose_specification","submit_specification_review","request_preparation_execution","request_preparation_publication")
        owner_actions = ("approve","reject","request_clarification","revoke","supersede","assess_use","assess_change","approve_specification","reject_specification",
            "request_clarification_specification","revoke_specification_approval","supersede_specification_approval","validate_preparation_plan","authorize_preparation_execution",
            "begin_preparation_execution","record_preparation_operation","finalize_preparation_execution","recover_preparation_execution","revoke_preparation_execution",
            "execute_preparation_operator","recover_preparation_worker","publish_preparation_artifacts","read_preparation_publication","recover_preparation_publication")
        self.grants = [DevelopmentGrant(actor,actor,actions,self.scope,(self.now-timedelta(days=1)).isoformat(),(self.now+timedelta(days=100)).isoformat()) for actor,actions in (("author",author_actions),("owner",owner_actions))]
        factories = AdapterFactories({}, {"identity":lambda c,s:DevelopmentIdentityProvider({"author":"env:AUTHOR","owner":"env:OWNER","stranger":"env:STRANGER"},s)},
            {"authority":lambda c,s:DevelopmentAuthorizationProvider(self.grants,s,"env:KEY")})
        cfg = RuntimeConfig("development","sqlite","identity","authority",sqlite_path=str(self.directory/"metadata.sqlite3"),credential_strategy="secret_references",secret_references=tuple("env:"+k for k in self.environment))
        self.runtime = start_runtime(cfg,ReviewPolicy("worker-policy","1"),factories,secret,clock=lambda:self.now)
        self.service,self.specs = self.runtime.service,self.runtime.specification_service()
        if self.runtime.catalogue.resolve(reference(d)) is None: self.bundle.publish(self.runtime.catalogue)
        bindings = self.service.records("SemanticBinding")
        if bindings:
            self.target,self.input,self.time = (next(b for b in bindings if b["object_id"] == k) for k in ("target","input","time"))
        else:
            self.target = self.bind(0,self.concept,"target"); self.input = self.bind(1,"owner.context","input"); self.time = self.bind(2,"owner.clock","time")
        self.store = LocalArtifactStorage(self.directory/"artifacts",protected_paths=[self.source_file] if self.source_file else [])
        self.worker = self.runtime.local_preparation_worker(store=self.store,adapters={self.adapter.source_id:self.adapter})
        self.control,self.publisher = self.worker.control,self.worker.publication_service()
        plans = self.service.records("DataPreparationPlanSpecification")
        if plans: self.plan = plans[-1]
        else:
            target,obs = self.base_specs()
            self.plan = self.propose("DataPreparationPlanSpecification",self.plan_fields(target,obs,operations=[self.operation(parameters={"checks":["native_rows"]})]))
            self.approve_spec(self.plan)

    def target_fields(self, **changes):
        fields = super().target_fields()
        fields["value_type"] = next(iter(self.bundle.discovery_result["tables"][0]["fields"][0]["observed"]["type_counts"]))
        fields.update(changes); return fields

    def set_operations(self, operations):
        fields = self.plan_fields(self.control.get(self.plan["target_reference"]),self.control.get(self.plan["observation_reference"]),operations=operations)
        self.plan = self.propose("DataPreparationPlanSpecification",fields,predecessor=reference(self.plan)); self.approve_spec(self.plan)
        return self.plan

    def start(self):
        request = self.control.request(reference(self.plan),request_key=self.cmd(),worker_principal_reference="owner",lease_seconds=120,purpose="Synthetic local operator test only.",
            context=self.author,command_id=self.cmd(),expected_head=self.service.head)
        outcome = self.control.authorize(reference(request),approve=True,expires_at=(self.now+timedelta(minutes=10)).isoformat(),rationale="Explicit synthetic execution permission.",
            context=self.owner,command_id=self.cmd(),expected_head=self.service.head)
        if outcome["authorization_reference"] is None: return request
        self.control.begin(reference(request),context=self.owner,command_id=self.cmd(),expected_head=self.service.head)
        return request

    def run(self, request, operation_id=None, **changes):
        state = self.control.state(reference(request))
        operation_id = operation_id or self.plan["operations"][len(state["operation_receipts"])] ["operation_id"]
        args = {"operation_id":operation_id,"fence_token":state["fence_token"],"context":self.owner,"command_id":self.cmd(),"expected_head":self.service.head}
        args.update(changes)
        return self.worker.run_next(reference(request),**args)

    def finish(self, request):
        return self.control.finalize(reference(request),context=self.owner,command_id=self.cmd(),expected_head=self.service.head)

    def publish(self, request, **changes):
        proposal = self.publisher.request(reference(request),publication_key=changes.pop("publication_key",self.cmd()),context=self.author,command_id=self.cmd(),expected_head=self.service.head)
        args = {"context":self.owner,"command_id":self.cmd(),"expected_head":self.service.head}; args.update(changes)
        return self.publisher.publish(reference(proposal),**args)
