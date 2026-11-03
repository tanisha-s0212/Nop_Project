# Semantic binding and approval foundation

Implemented baseline: **2 November 2026**. This extends the [discovery foundation](foundation.md) using the [approved semantic design](../architecture/semantic_binding_and_approval_design.md) and [framework architecture](../architecture/business_prediction_framework_architecture.md).

The implementation supports explicit, evidence-linked field interpretations and scoped business-review lifecycle records. It is an **in-process development foundation**, not production identity, authorization or decision storage. No NOP business definition or treatment is approved by implementing or testing it. All automated approvals in the tests concern synthetic fixtures.

## Implemented scope and repository additions

```text
src/business_prediction/semantics/
    __init__.py
    common.py
    contracts.py
    authority.py
    testing_authority.py
    journal.py
    service.py
tests/
    semantic_support.py
    test_semantic_contracts.py
    test_semantic_lifecycle.py
docs/development/semantic_approval_foundation.md
```

Existing Python modules, contracts and tests are unchanged. README is extended with a link to this guide. The historical architecture/design/foundation documents remain unchanged; this guide records the newly implemented capability and its bounds. No new dependency is required; the new package uses the standard library and existing framework components.

| Capability | Implemented behavior |
| --- | --- |
| Eight versioned contracts | Registers all eight design types at `1.0`, using existing `ContractDefinition`, `FieldSpec`, envelopes, four-part references, consistency checks and structured errors |
| Semantic binding | Explicit proposal, exact physical/source/schema references, typed qualifiers, evidence, uncertainty, provenance and sequential immutable revisions |
| Business review | Frozen request and evidence/approval terms, approve/reject/clarify decisions, configurable distinct-reviewer quorum and proposer/submitter separation |
| Approval lifecycle | Issued records, scoped current-use assessment, expiration/mandatory review, revocation and explicit supersession without implicit revival |
| Authority boundary | Provider-neutral authentication, action/scope verification, receipt-integrity verification and optional continuing-authority checks |
| Change/dependencies | Exact source/discovery/field comparisons, new-fingerprint review, field-removal/reorder incompatibility, evidence expiry and dependent-assertion revocation checks |
| Journal | Serialized in-process writes, expected-head checks, idempotent commands, atomic catalogue bundles, immutable decision history and instance-local issuance integrity |

Technical operations and contract types are not a business-question catalogue. There are no fixed business column names, department mappings, question routes, inference algorithms or automatic meaning approval. Physical observations and hypotheses remain untouched; an approved assertion is a binding plus applicable approval and current-use evidence.

## Contract and catalogue extension

[contracts.py](../../src/business_prediction/semantics/contracts.py) exposes:

- `semantic_registry()`: a new foundation registry with the eight additional definitions.
- `register_semantic_contracts(registry)`: adds the definitions once to an existing registry without replacing any definition.

The types are `SemanticBinding`, `BusinessReviewRequest`, `AuthorityVerificationRecord`, `BusinessReviewDecision`, `ApprovalRecord`, `SupportingEvidenceRecord`, `BindingChangeAssessment` and `BindingUseAssessment`.

Use `MetadataCatalogue(semantic_registry())` or explicitly register the additions in the existing catalogue's registry. Existing discovery bundles can then be published normally. Governance uses that same catalogue; it does not copy the source profiles into a separate profiling system. Generic catalogue validation still proves shape/reference consistency, not trusted issuance.

In addition to the existing envelope, records carry exact `evidence_references` and `dependency_versions`. Source/discovery metadata retains `approval_status=unreviewed`; a semantic decision never changes it. Binding proposals retain `proposal_state=proposed`, even after an approval is issued. Lifecycle projections are scope/context-specific.

### Exact physical and evidence references

`service.physical_field_reference(discovery_ref, table_id, field_id)` resolves a field and returns source metadata/discovery references, their source/schema versions, physical IDs and one-based position. It validates the discovery fully, not just structurally. The helper never resolves by a familiar column name.

Observation/hypothesis evidence has an explicit variant: `kind`, nullable `discovery_reference`, `evidence_id`, `field_id`, `hypothesis_id`, `record_reference`, `binding_reference` and `approval_reference`. Only fields appropriate to the selected variant may be non-null. Observation evidence resolves the exact discovery field/profile; hypothesis evidence remains inferred. At least one explicit observation/hypothesis reference for the primary field is required. Supporting-field evidence must name a declared supporting field.

Documentary evidence references an issued `SupportingEvidenceRecord`. Its origin cannot be marked verified by a caller flag: the provider must attest the exact artifact/digest/origin. Documentary evidence must be linked to the exact binding, source metadata or discovery context before approval. A referenced meaning-definition document must be included in the frozen evidence basis. A verified origin does not prove the document's business claim; the authorized reviewer remains responsible for that judgment.

Prior-assertion evidence pins both a binding and its approval. Revocation, supersession, expiry or unusable support propagates as a blocker when a dependent assertion is assessed. Trusted construction requires references to existing journal-issued governance records, preventing forward/cyclic approval creation; recursive use checks also detect cycles defensively.

### Supported scope profile

The implemented `ReviewScope` contains `purpose`, `namespace`, `record_grain`, `assertion_use=semantic_interpretation`, a nonempty exact `field_references` collection, nullable `business_period`, and `period_not_applicable_reason`. A bounded period specifies ISO calendar dates `start`/`end` and an explicit `calendar_reference`; it is half-open. A null period needs an explicit reason. This declares applicability, not event-date parsing or fiscal-calendar interpretation.

Containment requires matching purpose/namespace/grain/use, a subset of exact field contexts and compatible period bounds. Unknown scope never means all data. No wildcards, fuzzy field equivalence, arbitrary SQL selectors or executable expressions are supported. A narrower interpretation review is submitted as a new explicit request. Retirement is for a whole approval record; partial retirement requires an explicitly approved replacement.

Known qualifiers require actual values. Unknown/unavailable qualifiers and blocking uncertainties prevent approval. Explicit not-applicable qualifiers require reasons. None of these fields authorizes cleaning, parsing, joins or prediction targets. Approval of a field meaning is not certification of a primary key, cross-source identity or business relationship.

## Authority interface and test-only provider

[AuthorityProvider](../../src/business_prediction/semantics/authority.py) defines:

| Method | Responsibility |
| --- | --- |
| `authenticate(context, now)` | Resolve an authenticated principal and safe context reference or reject; body-supplied owner labels are insufficient |
| `verify(context, action, subject_reference, scope, policy_reference, now)` | Return a provider-receipted verification body for this exact action, object revision, purpose, scope and time |
| `verify_record(record, now)` | Check the integrity and current trust of archived authority evidence; receipt freshness at the original decision is checked separately |
| `verify_evidence_origin(artifact_reference, content_digest, origin_identity)` | Attest documentary origin; the base implementation returns false |
| `verify_continuing_authority(verification, now)` | Recheck authority when explicitly required by policy; the base implementation returns false |

No production provider is supplied. [LocalTestAuthorityProvider](../../src/business_prediction/semantics/testing_authority.py) is **for automated tests only**. It requires `test_mode=True`, and the service separately requires `allow_test_authority=True`. It uses ephemeral synthetic sessions, finite test grants and instance-local receipts. Test configuration methods can mint identities/grants; this is precisely why it is not production security. Credentials are not persisted in governance records or routine logs.

The test provider can simulate denied/unavailable authority, withdrawn grants and evidence-origin attestations. It cannot authenticate a real employee, ERP owner or finance approver. Provider instances and policy configuration belong to trusted application setup, never an LLM/user payload. A future real adapter must provide its own authoritative identity, scope, grant/revocation and receipt-verification implementation.

## Service interfaces

[SemanticApprovalService](../../src/business_prediction/semantics/service.py) accepts an extended catalogue, an `AuthorityProvider`, an explicit `ReviewPolicy` and optionally an aware clock. The service rejects the test provider unless expressly enabled. `ReviewPolicy` records policy ID/version, minimum distinct approvers, independent-review requirement, no-deadline permission, continuing-authority policy and assessment TTL. These are technical deployment/test settings, not approved NOP business policies.

| Operation | Inputs and result |
| --- | --- |
| `propose_binding(...)` | Explicit object ID, field reference, interpretation, scope, evidence, provenance/qualifiers/uncertainties and authenticated context. Returns an immutable proposed binding; a new revision must name the exact current predecessor |
| `register_evidence(...)` | Artifact/version/digest, claim, relevant subject references, origin, access/retention metadata and validity. Returns a documentary evidence revision; it does not fetch files/URLs or accept caller-asserted verification |
| `submit_review(subject_ref, ...)` | Exact binding or approval, explicit scope, authenticated submitter and predecessor/reason if resubmitting. Binding requests freeze approval deadlines, conditions and limitations in `approval_terms`; lifecycle reviews have null terms |
| `decide(request_ref, subject_ref, ...)` | Exact frozen request/subject, explicit action/rationale, authenticated reviewer and replacement approval for supersession. Returns verification/decision references and an approval reference only when approve quorum/policy is satisfied |
| `assess_change(binding_ref, new_discovery_ref, ...)` | Fully validated old/new context, optional explicit candidate field and authorized assessment context. Returns an immutable change assessment, never a transferred approval |
| `assess_use(binding_ref, ...)` | Explicit requested scope **and physical field context**, authenticated assessment context and current journal head. Returns an immutable scoped-use assessment with result, lifecycle state, dependencies, reasons and bounded freshness |
| `get(ref)`, `records(kind=None)`, `history()` | Defensive copies of instance-issued governance records and ordered journal history. Generic imported JSON is not accepted as trusted issuance |

Every mutating operation, including assessment recording, requires a nonempty `command_id` and `expected_head=service.head`. Reads are local development interfaces, not a production data-access authorization API.

`SemanticBinding.interpretation` has concept, definition, definition version and nullable exact definition-evidence reference. Semantics are supplied explicitly; the service does not generate them from names. New bindings or snapshots never receive automatic approval.

### Decisions, time and lifecycle

Approve, reject and request_clarification act on binding reviews. Revoke and supersede act on approval reviews. All decisions require matching provider authority; proposal/request creation requires provider authentication and cannot grant authority. The submitter/proposer cannot self-approve under the default independent-review policy. Quorum counts distinct authenticated reviewers, and later votes cannot change frozen terms.

Approval decisions and verified provenance are recorded; an `ApprovalRecord` is issued only after policy is met. Failed authority checks record a denied/unavailable verification and raise a structured error without issuing a decision/approval. Idempotent replay returns the same outcome or the same authority error without duplicating history. A different actor/input cannot reuse the command ID.

The stored approval remains `record_state=issued`. `BindingUseAssessment.lifecycle_state` exposes proposed, approved, rejected, clarification_requested, revoked, superseded, expired, needs_review or blocked for the requested context. Its separate `result` distinguishes usable, unresolved conditions, conflicts, authority problems and other blockers. An issued conditional approval can have lifecycle state approved while its result is conditions_unverified; it grants no execution permission.

Aware timestamps come from the service clock, with backward-clock protection. Approval use starts at issuance; no backdating. Expiry and mandatory review are enforced at their exact boundaries. By default, both deadline fields are required; a policy permitting null bounds requires explicit reasons. Request submission freezes these limits and rejects already-expired terms. Caller clocks cannot override decision timestamps.

Supersession requires an independently usable replacement and an explicit authorized retirement decision. Old approval retirement is committed atomically with its lifecycle decision. Replacement issuance is a separate explicit approved operation; no implicit cross-object renewal occurs. Revoking a replacement does not reactivate its predecessor. Different active meanings for the same overlapping field scope produce conflict, not latest-wins selection.

Archived verification expiry alone does not erase a legitimately issued approval. Every use still checks receipt trust, approval deadlines, dependencies and policy. When continuing authority is enabled, a withdrawn/expired grant blocks further use. Provider unavailability blocks affected operations with structured reasons.

## Change management and journal boundaries

The service reuses full foundation validation, exact reference resolution, observed schema comparison and `MetadataCatalogue.add_many()`. The [journal wrapper](../../src/business_prediction/semantics/journal.py) serializes service operations with an in-process lock, compares the expected head, records hash-linked history and tracks instance-issued document digests. Two stale writers cannot both commit the same expected state.

Generic catalogue writes remain generic. They can store structurally valid metadata but cannot add trusted entries to this service's issuance journal. Forged/exported approval JSON is rejected by `service.get()` and excluded from lifecycle selection. Receipts/hash links are development integrity evidence, not production signatures. The journal is not durable or cross-process: restarting or using another service instance does not import trust or restore approvals automatically.

A use assessment requires an explicit physical context. New source fingerprints or discovery revisions cannot inherit approval even if observed schema hashes match. Added/removed/reordered fields and changed raw headers require review or are incompatible. A positional comparison candidate is not an approved semantic rebind. Historical approvals remain assessable only for their original exact context.

Change reports record approval dependency paths. Current use also follows documentary validity and prior-assertion dependencies. No global source is selected by largest/newest file, and no latest schema is silently substituted. The service reads metadata; it does not reopen current business files to attest capture freshness. Callers must discover/provide the exact context they intend to use.

Use assessments pin the pre-commit governance head and record freshness/recheck triggers. Their own audit insertion advances the journal. They are evidence of a check, not bearer tokens or standing permission; a future consumer must recheck current state before any separately authorized operation.

## Validation and preservation

From the project root in PowerShell:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -t . -q
```

**80 tests pass with warnings treated as errors: 38 existing tests and 42 new tests.** New [contract/evidence tests](../../tests/test_semantic_contracts.py), [lifecycle tests](../../tests/test_semantic_lifecycle.py) and [synthetic fixtures](../../tests/semantic_support.py) cover all eight emitted contract types, exact references, typed qualifiers, evidence provenance/expiry, proposal revisions, approvals, rejection/clarification, revocation, supersession/no revival, scope/purpose checks, unauthorized and wrong-version attempts, independence/quorum, clock/expiry, source/schema changes, dependency revocation/purpose boundaries, invalid/forged JSON, replay and concurrent stale writers.

No existing test or implementation is replaced. Original source/report/document hashes are compared against the pre-task baseline; original source hashes also reconcile with the validated source-integrity manifest. The original datasets are used only for preservation hashes, not discovery, cleaning, transformation, joining or training. All new runtime tests use synthetic data. Requirements remain unchanged and no external service/database is created.

## Remaining limitations and next work

- Production identity providers, protected durable decision storage, cryptographic receipts, distributed concurrency, production access controls and cross-process trust recovery are not implemented.
- The initial scope profile supports explicit field sets and simple calendar periods; arbitrary selectors, wildcard compatibility and automatic contract migrations are unsupported.
- Conditions can be recorded but trusted fulfillment integration is not implemented. Required conditions therefore remain unverified and block use; they never default to true.
- Source/schema changes, evidence expiry and parent-approval retirement are checked. External documentary retraction feeds, live concept/policy changes, emergency withdrawal workflows and richer dependency-event integrations remain future work.
- Documentary artifacts are referenced, not fetched or independently authenticated from business systems. Only the test provider can simulate origin attestation here; a production connector must verify real evidence.
- There is no semantic interpreter, target discovery, preparation, feature engineering, model registry, training, evaluation, inference, LLM/MCP or UI implementation. Field-meaning acceptance does not prove keys, joins, prediction readiness or source authority.

Recommended next activity, **only after explicit approval**: review the implemented contract/scope profile and define a real authority/policy adapter plus protected journal persistence requirements. NOP business owners must still resolve the existing clarification decisions before any approved interpretation or treatment is applied to actual data. No further implementation begins automatically.
