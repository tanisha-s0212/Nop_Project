"""Synthetic persistent-runtime fixture; no NOP source data or real identities."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from business_prediction.contracts import reference
from business_prediction.runtime import RuntimeConfig, AdapterFactories, start_runtime
from business_prediction.runtime.development import DevelopmentIdentityProvider, DevelopmentAuthorizationProvider, DevelopmentGrant
from business_prediction.runtime.secrets import EnvironmentSecrets
from business_prediction.semantics import ReviewPolicy
from tests.semantic_support import Fixture


class PersistentFixture(Fixture):
    def __init__(self, directory, *, environments=None, **policy_options):
        seed = Fixture()
        self.now, self.bundle = seed.now, seed.bundle
        self.field, self.scope, self.evidence = seed.field, seed.scope, seed.evidence
        self.counter, self.command_prefix = 0, str(uuid4())
        self.directory = Path(directory)
        self.environment = environments if environments is not None else {
            "AUTHOR_CREDENTIAL": "synthetic-author-opaque-credential", "OWNER_CREDENTIAL": "synthetic-owner-opaque-credential",
            "INTRUDER_CREDENTIAL": "synthetic-intruder-opaque-credential", "RECEIPT_KEY": "synthetic-signing-key-012345678901234567890123456789"}
        self.secrets = EnvironmentSecrets(self.environment)
        self.author, self.owner, self.intruder = (self.environment[k] for k in ("AUTHOR_CREDENTIAL", "OWNER_CREDENTIAL", "INTRUDER_CREDENTIAL"))
        credentials = {"test-proposer": "env:AUTHOR_CREDENTIAL", "test-owner": "env:OWNER_CREDENTIAL", "test-unprivileged": "env:INTRUDER_CREDENTIAL"}
        def grant(principal, actions, key):
            return DevelopmentGrant(key, principal, tuple(actions), self.scope,
                (self.now-timedelta(days=1)).isoformat(), (self.now+timedelta(days=100)).isoformat())
        self.grants = [grant("test-proposer", ("propose_binding", "submit_review", "register_evidence"), "author-grant"),
            grant("test-owner", ("approve", "reject", "request_clarification", "revoke", "supersede", "assess_use", "assess_change"), "owner-grant")]
        self.factories = AdapterFactories({},
            {"local-identity": lambda c, s: DevelopmentIdentityProvider(credentials, s)},
            {"local-authorization": lambda c, s: DevelopmentAuthorizationProvider(self.grants, s, "env:RECEIPT_KEY")})
        self.config = RuntimeConfig("development", "sqlite", "local-identity", "local-authorization",
            sqlite_path=str(self.directory/"framework.sqlite3"), credential_strategy="secret_references",
            secret_references=tuple(credentials.values())+("env:RECEIPT_KEY",))
        self.policy = ReviewPolicy("synthetic-persistent-policy", "1", **policy_options)
        self.runtime = start_runtime(self.config, self.policy, self.factories, self.secrets, clock=lambda: self.now)
        self.catalogue, self.service, self.provider = self.runtime.catalogue, self.runtime.service, self.runtime.authority
        if self.catalogue.resolve(reference(self.bundle.discovery_result)) is None:
            self.bundle.publish(self.catalogue)

    def cmd(self):
        self.counter += 1
        return self.command_prefix+":"+str(self.counter)
