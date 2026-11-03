"""Shared runtime composition; external production adapters must be installed."""

from dataclasses import asdict, dataclass
import logging

from ..contracts import reference
from ..persistence import PersistenceStore, ProductionStorageAdapter, SQLiteStore
from ..persistence.coordinator import DurableCoordinator
from ..semantics import SemanticApprovalService, semantic_registry
from ..semantics.common import clone, digest, GovernanceError
from ..semantics.contracts import validate_scope
from ..assessment.contracts import register_assessment_contracts
from ..specifications.contracts import register_specification_contracts
from ..execution.contracts import register_execution_contracts
from ..worker.contracts import register_worker_contracts
from .config import ConfigurationError
from .security import IdentityProvider, AuthorizationProvider, ComposedAuthorityProvider

logger = logging.getLogger(__name__)


@dataclass
class AdapterFactories:
    """Trusted application registration, never import paths supplied by a user."""
    storage: dict
    identity: dict
    authorization: dict


class AuthorizationFailure(GovernanceError):
    def __init__(self, code, proof):
        self.audit_authorization = clone(proof)
        super().__init__(code, "The configured provider did not authorize this exact operation and scope.")


class RuntimeOperationGuard:
    def __init__(self, authority, policy, coordinator):
        self.authority, self.policy, self.coordinator = authority, policy, coordinator

    def __call__(self, operation, context, payload, documents, outcome, now):
        if operation not in ("propose_binding", "submit_review", "register_evidence") or "error_code" in outcome:
            return
        document = documents[-1]
        if operation == "propose_binding":
            scope, subject = document["interpretation_scope"], reference(document)
        elif operation == "submit_review":
            scope, subject = document["requested_scope"], document["subject_reference"]
        else:
            scope, subject = payload.get("authorization_scope"), reference(document)
            if scope is None:
                raise GovernanceError("authorization_scope_required", "Runtime evidence registration requires an explicit authorization scope.")
            validate_scope(scope, self.coordinator.catalogue.resolve)
            if scope["purpose"] != document["purpose_scope"]:
                raise GovernanceError("scope_mismatch", "Evidence authorization purpose does not match its record.")
        proof = self.authority.verify(context, operation, subject, scope, self.policy.reference(), now)
        if proof["verification_outcome"] != "verified":
            raise AuthorizationFailure("authority_denied" if proof["verification_outcome"] == "denied" else "authority_unavailable", proof)
        self.coordinator.audit_event("authorization.operation_verified", operation=operation, authorization=proof)


class FrameworkRuntime:
    def __init__(self, config, store, coordinator, service, authority):
        self.config, self.store, self.coordinator = config, store, coordinator
        self.catalogue, self.service, self.authority = coordinator.catalogue, service, authority

    def health_check(self):
        try:
            storage = self.coordinator.health_check()
            identity = self.authority.identity_provider.health_check()
            authorization = self.authority.authorization_provider.health_check()
            return {"ready": all(v.get("ready") is True for v in (storage, identity, authorization)),
                    "mode": self.config.mode, "storage": storage, "identity": identity, "authorization": authorization}
        except GovernanceError:
            raise
        except Exception:
            raise ConfigurationError("runtime_health_unavailable", "Health providers did not return a safe verified readiness result.") from None

    def audit_history(self):
        return self.coordinator.audit_history()

    def requirement_assessment_engine(self, *, strategies=None):
        from ..assessment.engine import PredictionRequirementAssessmentEngine
        return PredictionRequirementAssessmentEngine(self, strategies=strategies)

    def business_query_service(self, project_root, **options):
        from ..query import DynamicBusinessQueryService
        return DynamicBusinessQueryService(project_root, runtime=self, catalogue=self.catalogue, **options)

    def specification_service(self, *, operations=None):
        from ..specifications.service import SpecificationService
        return SpecificationService(self, operations=operations)

    def controlled_preparation_service(self, *, sources=None, evidence=None, operations=None, reconciliation=None):
        from ..execution.service import ControlledPreparationService
        return ControlledPreparationService(self, sources=sources, evidence=evidence, operations=operations, reconciliation=reconciliation)

    def local_preparation_worker(self, *, store, adapters, operators=None):
        from ..worker.service import LocalPreparationWorker
        return LocalPreparationWorker(self,store=store,adapters=adapters,operators=operators)

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _build(factories, name, config, secrets, code):
    factory = factories.get(name)
    if factory is None:
        raise ConfigurationError(code, "Configured integration is not installed; no external connectivity is claimed.")
    try:
        return factory(config, secrets)
    except GovernanceError:
        raise
    except Exception:
        raise ConfigurationError("integration_startup_failed", "Configured adapter failed startup; inspect safe connector diagnostics.") from None


def start_runtime(config, policy, factories, secrets, *, clock=None):
    config.validate()
    for secret_ref in config.secret_references:
        secrets.resolve(secret_ref)  # Verify availability; never log values.
    identity = _build(factories.identity, config.identity_provider, config, secrets, "missing_identity_integration")
    authorizer = _build(factories.authorization, config.authorization_provider, config, secrets, "missing_authorization_integration")
    if not isinstance(identity, IdentityProvider) or not isinstance(authorizer, AuthorizationProvider):
        raise ConfigurationError("invalid_security_adapter", "Separate identity and authorization interfaces are required.")
    if (identity.test_only or authorizer.test_only) and not config.allow_test_providers:
        raise ConfigurationError("test_provider_disabled", "Test identity/authorization adapters need development-only opt-in.")
    if config.mode == "production" and any(p.development_only or p.test_only or not p.production_capable for p in (identity, authorizer)):
        raise ConfigurationError("unsafe_production_provider", "Production rejects test/development or unapproved identity integrations.")
    if config.mode == "production" and (identity.approval_reference != config.identity_approval_reference or
                                        authorizer.approval_reference != config.authorization_approval_reference):
        raise ConfigurationError("unapproved_security_integration", "Configured production approvals do not match the installed security adapters.")
    for provider in (identity, authorizer):
        try:
            if provider.health_check().get("ready") is not True:
                raise ValueError
        except GovernanceError:
            raise
        except Exception:
            raise ConfigurationError("security_provider_unavailable", "Security provider failed readiness; startup was blocked.") from None
    if config.storage_adapter == "sqlite":
        store = SQLiteStore(config.sqlite_path)
    else:
        store = _build(factories.storage, config.storage_adapter, config, secrets, "missing_storage_integration")
    if not isinstance(store, PersistenceStore):
        raise ConfigurationError("invalid_storage_adapter", "An approved persistence interface is required.")
    caps = store.capabilities
    if not all((caps.durable, caps.transactions, caps.immutable_history, caps.stale_write_protection, caps.recovery)):
        raise ConfigurationError("unsafe_storage_adapter", "Selected runtime storage does not meet durable transaction/recovery requirements.")
    if config.mode == "production" and (not isinstance(store, ProductionStorageAdapter) or not caps.production_approved
            or caps.test_only or store.approval_reference != config.storage_approval_reference):
        raise ConfigurationError("unapproved_production_storage", "Production requires an owner-approved external durable adapter; local storage is rejected.")
    try:
        authority = ComposedAuthorityProvider(identity, authorizer)
        coordinator = DurableCoordinator(register_worker_contracts(register_execution_contracts(register_specification_contracts(register_assessment_contracts(semantic_registry())))), store)
        coordinator.bind_runtime({"mode": config.mode, "policy_digest": digest(asdict(policy)),
                                  "identity_provider": identity.provider_id, "authorization_provider": authorizer.provider_id,
                                  "storage_adapter": store.adapter_id})
        guard = RuntimeOperationGuard(authority, policy, coordinator)
        service = SemanticApprovalService(coordinator.catalogue, authority, policy, allow_test_authority=config.allow_test_providers,
                                          clock=clock, journal=coordinator.journal, operation_guard=guard)
        result = FrameworkRuntime(config, store, coordinator, service, authority)
        if result.health_check()["ready"] is not True:
            raise ConfigurationError("runtime_not_ready", "Runtime startup health verification failed.")
        coordinator.audit_event("runtime.started", mode=config.mode)
        logger.info("runtime.started", extra={"mode": config.mode, "status": "ready"})
        return result
    except BaseException:
        store.close()
        raise
