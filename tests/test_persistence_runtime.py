from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import io
import json
import logging
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from business_prediction.contracts import reference
from business_prediction.errors import FrameworkError
from business_prediction.persistence import SQLiteStore, PersistenceError
from business_prediction.persistence.base import append_audit
from business_prediction.runtime import RuntimeConfig, AdapterFactories, start_runtime
from business_prediction.runtime.config import ConfigurationError
from business_prediction.runtime.logging import StructuredJSONFormatter
from business_prediction.runtime.secrets import EnvironmentSecrets
from business_prediction.semantics.common import digest
from tests.persistence_support import PersistentFixture


class PersistenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.f = PersistentFixture(self.temporary.name)

    def assertCode(self, code, call):
        with self.assertRaises(FrameworkError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_restart_recovers_metadata_approvals_rejections_and_current_use(self):
        binding, approval = self.f.approve()
        rejected = self.f.propose("rejected"); request = self.f.review(rejected); self.f.decide(request, "reject")
        head = self.f.service.head
        self.f.runtime.close()
        recovered = PersistentFixture(self.temporary.name)
        self.assertEqual(recovered.service.head, head)
        self.assertEqual(recovered.service.get(reference(approval)), approval)
        self.assertEqual(recovered.use(binding)["result"], "usable")
        self.assertEqual(recovered.use(rejected)["result"], "rejected")
        self.assertTrue(recovered.runtime.health_check()["storage"]["catalogue_consistent"])

    def test_real_subprocess_recovers_signed_development_receipts(self):
        binding, approval = self.f.approve()
        code = ("import json,sys; from tests.persistence_support import PersistentFixture; "
                "f=PersistentFixture(sys.argv[1]); b=f.service.records('SemanticBinding')[0]; "
                "print(json.dumps({'result':f.use(b)['result'],'approvals':len(f.service.records('ApprovalRecord'))}))")
        result = subprocess.run([sys.executable, "-B", "-W", "error", "-c", code, self.temporary.name],
            capture_output=True, text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"result": "usable", "approvals": 1})

    def test_concurrent_runtime_instances_reject_stale_writer(self):
        other = PersistentFixture(self.temporary.name)
        head = self.f.service.head
        def propose(pair):
            fixture, name = pair
            try:
                fixture.propose(name, expected_head=head)
                return "committed"
            except FrameworkError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(propose, [(self.f, "writer-one"), (other, "writer-two")]))
        self.assertCountEqual(results, ["committed", "stale_governance_head"])
        self.assertEqual(len(self.f.service.records("SemanticBinding")), 1)

    def test_transaction_exception_rolls_back_complete_unit(self):
        store = self.f.runtime.store
        before = store.snapshot()
        with self.assertRaises(RuntimeError):
            with store.transaction() as unit:
                append_audit(unit.state, "test.before_failure")
                raise RuntimeError("synthetic failure")
        self.assertEqual(store.snapshot(), before)

    def test_sql_update_failure_does_not_leave_phantom_binding(self):
        store = self.f.runtime.store
        original = store._connect
        failed = [False]
        class Connection:
            def __init__(self): self.inner = original()
            def __getattr__(self, key): return getattr(self.inner, key)
            def execute(self, sql, *args):
                if sql.startswith("UPDATE framework_state") and not failed[0]:
                    failed[0] = True
                    raise sqlite3.OperationalError("synthetic update failure")
                return self.inner.execute(sql, *args)
        with patch.object(store, "_connect", side_effect=Connection):
            with self.assertRaises(PersistenceError): self.f.propose()
        self.assertEqual(self.f.service.records("SemanticBinding"), [])
        self.assertEqual(PersistentFixture(self.temporary.name).service.records("SemanticBinding"), [])

    def test_lost_commit_acknowledgement_recovers_idempotent_outcome(self):
        store = self.f.runtime.store
        original = store._connect
        lost = [False]
        class Connection:
            def __init__(self): self.inner = original()
            def __getattr__(self, key): return getattr(self.inner, key)
            def execute(self, sql, *args):
                result = self.inner.execute(sql, *args)
                if sql == "COMMIT" and not lost[0]:
                    # Ignore read-only commits (such as head reads), lose only a write acknowledgement.
                    if self.inner.total_changes:
                        lost[0] = True
                        raise sqlite3.OperationalError("synthetic lost acknowledgement")
                return result
        command, head = "commit-retry", self.f.service.head
        with patch.object(store, "_connect", side_effect=Connection):
            self.assertCode("commit_indeterminate", lambda: self.f.propose(command_id=command, expected_head=head))
        recovered = PersistentFixture(self.temporary.name)
        result = recovered.propose(command_id=command, expected_head=head)
        self.assertEqual(result["object_id"], "binding")
        self.assertEqual(len(recovered.service.records("SemanticBinding")), 1)

    def test_catalogue_and_journal_changes_roll_back_together(self):
        before = self.f.runtime.store.snapshot()
        original_capture = self.f.runtime.coordinator._capture
        once = [False]
        def fail_capture():
            if not once[0]:
                once[0] = True
                raise PersistenceError("synthetic_capture_failure", "Synthetic pre-commit failure.")
            return original_capture()
        with patch.object(self.f.runtime.coordinator, "_capture", side_effect=fail_capture):
            self.assertCode("synthetic_capture_failure", lambda: self.f.propose())
        self.assertEqual(self.f.service.records("SemanticBinding"), [])
        self.assertEqual(self.f.service.head, before["state"]["journal"]["head"])

    def test_revocation_remains_revoked_after_restart(self):
        binding, approval = self.f.approve()
        request = self.f.review(approval); self.f.decide(request, "revoke")
        recovered = PersistentFixture(self.temporary.name)
        self.assertEqual(recovered.use(binding)["result"], "revoked")

    def test_signing_key_rotation_does_not_silently_trust_old_receipts(self):
        binding, _ = self.f.approve()
        environment = dict(self.f.environment); environment["RECEIPT_KEY"] = "different-secret-signing-key-012345678901234567890"
        recovered = PersistentFixture(self.temporary.name, environments=environment)
        self.assertEqual(recovered.use(binding)["result"], "authority_unavailable")

    def test_immutable_documents_and_history_cannot_be_replaced(self):
        binding, approval = self.f.approve()
        with self.assertRaises(PersistenceError):
            with self.f.runtime.store.transaction() as unit:
                unit.state["documents"][0]["owner_reference"] = "rewritten"
        with self.assertRaises(PersistenceError):
            with self.f.runtime.store.transaction() as unit:
                unit.state["journal"]["entries"].clear()
        self.assertEqual(self.f.service.get(reference(approval)), approval)

    def test_generic_catalogue_cannot_persist_untrusted_governance(self):
        binding = self.f.propose(); forged = deepcopy(binding); forged["object_id"] = "imported"
        self.assertCode("untrusted_governance_import", lambda: self.f.catalogue.add(forged))

    def test_replay_outcome_survives_restart_without_duplicate_approval(self):
        binding = self.f.propose(); request = self.f.review(binding)
        command, head = "stable-retry", self.f.service.head
        result = self.f.decide(request, command_id=command, expected_head=head)
        other = PersistentFixture(self.temporary.name)
        self.assertEqual(other.decide(request, command_id=command, expected_head=head), result)
        self.assertEqual(len(other.service.records("ApprovalRecord")), 1)

    def test_denial_is_durable_even_though_operation_raises(self):
        binding = self.f.propose(); request = self.f.review(binding)
        self.assertCode("authority_denied", lambda: self.f.decide(request, context=self.f.intruder))
        recovered = PersistentFixture(self.temporary.name)
        self.assertEqual(recovered.service.records("ApprovalRecord"), [])
        self.assertEqual(recovered.service.records("AuthorityVerificationRecord")[-1]["verification_outcome"], "denied")

    def test_proposal_authorization_and_failed_identity_are_audited_without_tokens(self):
        self.assertCode("authority_denied", lambda: self.f.propose(context=self.f.intruder))
        self.assertEqual(self.f.service.records("SemanticBinding"), [])
        self.assertCode("unverified_principal", lambda: self.f.propose(context="test-owner"))
        audit = self.f.runtime.audit_history()
        self.assertTrue(any(e["details"].get("error_code") == "authority_denied" for e in audit))
        self.assertTrue(any(e["details"].get("authorization", {}).get("verification_outcome") == "denied" for e in audit if e["details"].get("authorization")))
        payload = json.dumps(self.f.runtime.store.snapshot())
        self.assertNotIn(self.f.author, payload); self.assertNotIn(self.f.owner, payload)
        self.assertNotIn(self.f.environment["RECEIPT_KEY"], payload)

    def test_clock_floor_survives_restart(self):
        self.f.propose()
        other = PersistentFixture(self.temporary.name)
        other.now -= timedelta(seconds=1)
        self.assertCode("clock_regression", lambda: other.propose("backdated"))

    def test_recovery_blocks_corrupt_payload_and_orphaned_journal(self):
        self.f.propose()
        path = self.f.config.sqlite_path
        with closing(sqlite3.connect(path)) as connection:
            payload = json.loads(connection.execute("SELECT payload FROM framework_state").fetchone()[0])
            payload["journal"]["entries"][0]["document_digests"][0] = "sha256:"+"0"*64
            connection.execute("UPDATE framework_state SET payload=?,payload_digest=?", (json.dumps(payload), digest(payload)))
            connection.commit()
        self.assertCode("recovery_consistency_failed", lambda: PersistentFixture(self.temporary.name))

    def test_policy_change_needs_explicit_migration_not_silent_transfer(self):
        self.assertCode("runtime_binding_changed", lambda: PersistentFixture(self.temporary.name, minimum_approvers=2))

    def test_secret_loss_fails_closed_and_missing_secrets_do_not_start(self):
        del self.f.environment["OWNER_CREDENTIAL"]
        self.assertCode("secret_unavailable", lambda: self.f.propose(context=self.f.owner))
        self.assertCode("secret_unavailable", lambda: start_runtime(self.f.config, self.f.policy,
            self.f.factories, self.f.secrets, clock=lambda: self.f.now))

    def test_wrong_version_provider_response_is_rejected(self):
        authorizer = self.f.runtime.authority.authorization_provider
        original = authorizer.authorize
        def wrong(*args):
            result = original(*args); result["subject_reference"]["object_revision"] = 99
            return result
        with patch.object(authorizer, "authorize", side_effect=wrong):
            self.assertCode("authority_denied", lambda: self.f.propose())
        self.assertEqual(self.f.service.records("SemanticBinding"), [])

    def test_production_configuration_rejects_local_defaults_before_connecting(self):
        config = replace(self.f.config, mode="production", storage_approval_reference="storage-approval",
                         identity_approval_reference="identity-approval", authorization_approval_reference="authorization-approval")
        self.assertCode("unsafe_production_configuration", lambda: start_runtime(config, self.f.policy, self.f.factories, self.f.secrets))

    def production_config(self):
        return RuntimeConfig("production", "approved-database", "real-idp", "real-authorizer",
            storage_approval_reference="storage-approval", identity_approval_reference="identity-approval",
            authorization_approval_reference="authorization-approval", credential_strategy="external_identity")

    def test_missing_production_integrations_are_explicit(self):
        self.assertCode("missing_identity_integration", lambda: start_runtime(self.production_config(), self.f.policy,
            AdapterFactories({}, {}, {}), self.f.secrets))

    def test_missing_identity_and_unknown_config_fields_fail_validation(self):
        self.assertCode("missing_identity_provider", lambda: replace(self.f.config, identity_provider=None).validate())
        self.assertCode("invalid_configuration", lambda: RuntimeConfig.from_mapping({"mode": "production", "password": "never-accepted"}))

    def test_production_rejects_development_and_test_identity_adapters(self):
        config = replace(self.production_config(), identity_provider="local-identity", authorization_provider="local-authorization")
        self.assertCode("unsafe_production_provider", lambda: start_runtime(config, self.f.policy, self.f.factories, self.f.secrets))
        identity = self.f.runtime.authority.identity_provider
        identity.development_only, identity.production_capable, identity.test_only = False, True, True
        factories = AdapterFactories({}, {"local-identity": lambda c, s: identity}, self.f.factories.authorization)
        self.assertCode("test_provider_disabled", lambda: start_runtime(config, self.f.policy, factories, self.f.secrets))

    def test_structured_logging_and_secret_repr_do_not_expose_credentials(self):
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord("business_prediction", logging.ERROR, __file__, 1, "unsafe %s", (self.f.owner,), None)
        record.error_code = "unverified_principal"
        text = formatter.format(record)
        self.assertNotIn(self.f.owner, text)
        self.assertEqual(json.loads(text)["error_code"], "unverified_principal")
        self.assertNotIn(self.f.environment["RECEIPT_KEY"], repr(self.f.secrets.resolve("env:RECEIPT_KEY")))

    def test_unrelated_or_unsupported_database_is_not_overwritten(self):
        path = Path(self.temporary.name)/"unrelated.sqlite3"
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE unrelated(value TEXT)")
            connection.execute("INSERT INTO unrelated VALUES('preserve')")
            connection.commit()
        before = path.read_bytes()
        self.assertCode("unsupported_storage_schema", lambda: SQLiteStore(path))
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
