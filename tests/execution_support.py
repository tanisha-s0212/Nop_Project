"""Measured temporary synthetic artifacts and a test-only identity worker.

No NOP file is opened. This verifier is intentionally not a production adapter.
"""

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from business_prediction.adapters import MemoryAdapter, MemoryTable, SourceConfig
from business_prediction.adapters.base import encode_cell
from business_prediction.contracts import reference
from business_prediction.execution.interfaces import AdapterSourceVersionVerifier, ExecutionEvidenceVerifier
from business_prediction.runtime.development import DevelopmentAuthorizationProvider
from business_prediction.semantics.common import clone, digest, GovernanceError
from tests.specification_support import SpecificationFixture


class SyntheticEvidenceVerifier(ExecutionEvidenceVerifier):
    provider_id = "synthetic-temporary-artifact-verifier"
    development_only = True

    def __init__(self, root, clock):
        self.root = Path(root).resolve(); self.root.mkdir(exist_ok=True)
        self.clock, self.reports = clock, {}

    def health_check(self): return {"ready": True, "development_only": True}

    def write(self, request, rows, field_ids, sources, *, complete=True):
        token = str(uuid4()); directory = self.root/request["object_id"]; directory.mkdir(exist_ok=True)
        path = directory/(token+".json")
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"request_id": request["object_id"], "field_ids": field_ids, "rows": rows,
                       "source_references": sources, "complete": complete}, stream, sort_keys=True)
        return "synthetic:"+request["object_id"]+":"+token

    def path(self, locator, request_ref):
        _, owner, token = locator.split(":")
        if owner != request_ref["object_id"]: raise GovernanceError("artifact_wrong_execution", "Synthetic artifact belongs to another run.")
        path = (self.root/owner/(token+".json")).resolve()
        if self.root not in path.parents or path.parent.name != owner: raise GovernanceError("artifact_outside_staging", "Synthetic artifact escaped its isolated staging directory.")
        return path

    def inspect_artifact(self, request_reference, artifact):
        path = self.path(artifact["locator"], request_reference)
        raw = path.read_bytes(); body = json.loads(raw)
        if body["request_id"] != request_reference["object_id"]: raise GovernanceError("artifact_wrong_execution", "Synthetic scope differs.")
        rows, ids = body["rows"], body["field_ids"]
        schema, missing = [], {}
        for i, name in enumerate(ids):
            cells = [row[i] for row in rows]
            missing[name] = sum(c["type"] == "null" for c in cells)
            schema.append({"field_id": name, "types": sorted({c["type"] for c in cells if c["type"] != "null"})})
        return {"locator": artifact["locator"], "content_digest": "sha256:"+hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
            "row_count": len(rows), "duplicate_count": len(rows)-len({json.dumps(row,sort_keys=True) for row in rows}),
            "missing_counts": missing, "schema": schema, "source_references": body["source_references"], "complete": body["complete"],
            "role": artifact["role"], "measured_at": self.clock().isoformat(), "evidence_reference": "synthetic-byte-inspection:"+hashlib.sha256(raw).hexdigest()}

    def emit(self, fixture, request, *, complete=True, drop_row=False, null_counts=False, no_outputs=False, bad_fence=False):
        state = fixture.control.state(reference(request)); authorization = fixture.control.get(state["authorization_reference"])
        operation = fixture.plan["operations"][len(state["operation_receipts"])]
        with fixture.adapter.open_snapshot() as snapshot:
            table = snapshot.tables()[0]
            rows = [[encode_cell(c) for c in row.cells] for row in table.rows]
        ids = [f["field_id"] for f in fixture.fields]
        input_locator = self.write(request, rows, ids, request["source_references"])
        output_rows = rows[:-1] if drop_row else rows
        outputs = []
        if not no_outputs:
            output_locator = self.write(request, output_rows, ids, request["source_references"], complete=complete)
            outputs = [self.inspect_artifact(reference(request), {"locator": output_locator, "role": "accepted"})]
        handle = str(uuid4())
        self.reports[handle] = {"request_reference": reference(request), "authorization_reference": reference(authorization),
            "fence_token": "unrelated-fence" if bad_fence else state["fence_token"], "operation_digest": digest(operation),
            "started_at": fixture.now.isoformat(), "completed_at": fixture.now.isoformat() if complete else None, "complete": complete,
            "accepted_count": None if null_counts else len(output_rows), "rejected_count": None if null_counts else 0,
            "input_artifacts": [self.inspect_artifact(reference(request), {"locator": input_locator, "role": "input"})],
            "output_artifacts": outputs, "evidence_reference": "synthetic-worker-receipt:"+handle}
        return handle

    def inspect_operation(self, request, authorization, state, operation, evidence_handle):
        if evidence_handle not in self.reports: raise GovernanceError("operation_not_observed", "No synthetic worker execution occurred for this handle.")
        return clone(self.reports[evidence_handle])


class ExecutionFixture(SpecificationFixture):
    def __init__(self, directory, **kwargs):
        super().__init__(directory, **kwargs)
        actions = {"author": ("request_preparation_execution",), "owner": ("authorize_preparation_execution", "begin_preparation_execution",
            "record_preparation_operation", "finalize_preparation_execution", "recover_preparation_execution", "revoke_preparation_execution")}
        self.grants = [replace(g, actions=g.actions+actions[g.principal_reference]) for g in self.grants]
        old = self.runtime.authority.authorization_provider
        self.runtime.authority.authorization_provider = DevelopmentAuthorizationProvider(self.grants, old._secrets, "env:KEY")
        d = self.bundle.discovery_result
        headers = tuple(f["raw_header"]["value"] for f in d["tables"][0]["fields"])
        categorical = "boolean" in d["tables"][0]["fields"][0]["observed"]["type_counts"]
        rows = [headers] + [(bool(i%2) if categorical else float(i+1), float(i*2+1), date(2026,1,i+1), float(i+100)) for i in range(20)]
        self.adapter = MemoryAdapter(SourceConfig(self.bundle.source_metadata["object_id"], "synthetic-owner", "assessment-test"),
            [MemoryTable(d["tables"][0]["name"], tuple(rows))])
        self.source_verifier = AdapterSourceVersionVerifier({self.adapter.source_id: self.adapter})
        self.evidence = SyntheticEvidenceVerifier(Path(directory)/"synthetic-staging", lambda:self.now)
        self.control = self.runtime.controlled_preparation_service(sources=self.source_verifier, evidence=self.evidence)
        plans = self.service.records("DataPreparationPlanSpecification")
        if plans: self.plan = plans[-1]
        else:
            target, observation = self.base_specs()
            self.plan = self.propose("DataPreparationPlanSpecification", self.plan_fields(target, observation))
            self.approve_spec(self.plan)

    def request_execution(self, **changes):
        args = {"request_key": self.cmd(), "worker_principal_reference": "owner", "lease_seconds": 120,
            "purpose": "Synthetic identity-worker control test, not NOP preparation.", "context": self.author,
            "command_id": self.cmd(), "expected_head": self.service.head}
        args.update(changes)
        return self.control.request(reference(self.plan), **args)

    def authorize_execution(self, request, **changes):
        args = {"approve": True, "expires_at": (self.now+timedelta(minutes=10)).isoformat(), "rationale": "Explicit synthetic operational authorization only.",
            "context": self.owner, "command_id": self.cmd(), "expected_head": self.service.head}
        args.update(changes)
        return self.control.authorize(reference(request), **args)

    def start(self):
        request = self.request_execution(); self.authorize_execution(request); self.advance("begin", request)
        return request

    def advance(self, name, request, **changes):
        args = {"context": self.owner, "command_id": self.cmd(), "expected_head": self.service.head}
        args.update(changes)
        return getattr(self.control, name)(reference(request), **args)

    def record(self, request, **faults):
        handle = self.evidence.emit(self, request, **faults)
        return self.advance("record_operation", request, operation_id=self.plan["operations"][0]["operation_id"], evidence_handle=handle)
