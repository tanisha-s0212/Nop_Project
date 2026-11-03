# Prediction requirement assessment engine

Implemented baseline: **2 November 2026**. This extends the [framework architecture](../architecture/business_prediction_framework_architecture.md), [semantic design](../architecture/semantic_binding_and_approval_design.md), [discovery foundation](foundation.md), [semantic foundation](semantic_approval_foundation.md) and [durable runtime](durable_runtime.md).

The engine accepts **structured, dynamically supplied requirements** and assesses authorized metadata, current semantic assertions and attributed evidence. It does not interpret natural-language questions, map anticipated scenarios to datasets/models, calculate targets, prepare data or train anything. Free text is retained for review, never used as a column-name matching shortcut.

## Implemented components

```text
src/business_prediction/assessment/
    __init__.py
    contracts.py
    intake.py
    relevance.py
    target.py
    strategies.py
    feasibility.py
    engine.py
tests/
    assessment_support.py
    test_requirement_assessment.py
docs/development/prediction_requirement_assessment.md
```

| Component | Responsibility |
| --- | --- |
| [contracts](../../src/business_prediction/assessment/contracts.py) | Four additive versioned contract definitions; exact references, scope, partial intake, profile consistency and result invariants |
| [intake](../../src/business_prediction/assessment/intake.py) | Distinguish omitted/null/unknown/unavailable fields and identify necessary clarification; no language interpreter |
| [relevance](../../src/business_prediction/assessment/relevance.py) | Discover candidates within authorized source/schema field contexts using exact concepts/bindings, physical profiles and current semantics |
| [target](../../src/business_prediction/assessment/target.py) | Resolve target ambiguity, contradictory selectors, native grain and symbolic construction requirements without creating target values |
| [strategies](../../src/business_prediction/assessment/strategies.py) | Extensible assessment of technical task characteristics, without algorithms, question catalogues or model routing |
| [feasibility](../../src/business_prediction/assessment/feasibility.py) | Evaluate target/grain/quality/history/outcomes/availability/leakage/validation/dependency gates |
| [engine](../../src/business_prediction/assessment/engine.py) | Authenticate/authorize operations, coordinate components and persist immutable requirements, evidence and assessment history |

These are shared development/production-oriented backend components. They are independent of the existing table count, departments and business column names. Existing adapters and discovery populate metadata; the engine never implicitly crawls the project dataset directory or rereads business cell values. New sources enter through the existing authorized onboarding/discovery interfaces.

## Contracts and intake

All four new types are version `1.0` and reuse the existing envelope, exact four-part references, structured validation errors, semantic scope and evidence mechanisms. Existing contract definitions are unchanged. The runtime registers the additional types before storage recovery, so existing stores remain readable and new records are fully validated on restart.

### `PredictionRequirementSpecification`

Business fields are optional at intake:

- `business_outcome`, `target_description`, `business_context`, `organizational_context`.
- `intent`: a structured distinction such as historical, future or unknown_outcome; unrecognized characteristics may be unsupported.
- `requested_concepts`: exact owner-defined semantic concept IDs; alternatively an exact `target_binding_reference`.
- `desired_output.value_kind`, optional unit, `observation_granularity`, `decision_time_basis`.
- `history_requirements`: target-specific minimum observations, validation observations and per-class support where applicable. No universal sufficient-row threshold is invented.
- `prediction_horizon`: steps and unit when applicable; `time_binding_reference` and `input_binding_references` pin relevant meanings.
- Optional `construction_request`: description, output grain and physical dependencies. It requests a future approved derivation; it is not executable SQL or a computed target.
- `constraints` and `additional_context`.

Omitted, explicit null and the existing unknown/unavailable tags remain distinct. A missing target description is acceptable if an exact concept or binding grounds the target. A description alone does not ground a field. Incomplete requests are persisted and assessed as clarification-required rather than filled with fabricated definitions.

The server owns identity/version/timestamp/provenance envelope fields. Technical `assessment_scope`, authenticated context and command metadata are required even when business fields are empty: partial business intent is not permission for an unscoped data scan. New revisions name the exact immediate predecessor and preserve earlier content.

Supported common constraints are maximum_target_missing_fraction, external_dependencies and required_identifier_bindings. Unknown required constraints produce an unsupported finding rather than silently disappearing. Strategies may explicitly declare additional technical constraint keys and assess them. Opaque additional context cannot override authorization, evidence or readiness gates.

A document with verified origin is not a live dependency-availability check. External dependencies remain blocked until a trusted availability verifier exists; this implementation does not infer connectivity from a document or connect an external service.

### `PredictionDataEvidence`

Discovery provides physical counts and syntax, **not** proof of complete mature history, legitimate negative outcomes or information available at a past decision. A separate attributed summary is therefore required for predictive readiness. This record is supplied by an authorized external profiler/data owner; the engine does not manufacture it from a user's wish to predict.

The record pins the target binding, physical source/schema version, optional time binding, input bindings, observation grain/frequency, raw observation/nonmissing counts, mature observations, historical bounds, typed class counts, and explicit facts about observable outcomes, population, label negatives, chronology, cadence, independence, availability and validation support. It also records:

- Decision-time basis and validation scheme.
- Exact label horizon where future categorical outcomes require a follow-up window.
- History-only versus explicit-input mode, leakage findings and limitations.
- Profiling method, supporting evidence references, validity deadline and provider-verifiable authorization attribution.

Registration requires the `register_prediction_evidence` action for the exact new record and scope. The engine validates counts against a **complete** discovery profile: observation/nonmissing totals, mature-count bounds and class totals/distinctness must agree. Target/time/input references must all lie within the declared evidence scope. A signature is attribution, not proof that a person cannot be mistaken; claims such as chronology and eligibility remain authorized attestations rather than independently recomputed raw-data facts.

Current, compatible evidence is selected by exact requested input/time/decision context, not recency, filename or size. Different technical contexts for the same field can coexist. Conflicting current summaries within the applicable context block readiness. Expired or unverifiable summaries are excluded; if no current evidence remains, the gaps are reported. Supporting-document validity is rechecked. No source is cleaned, relabeled or consolidated to create evidence.

### `TargetAssessment`

Records the exact requirement, assessed problem family/strategy version, all relevant candidates, a uniquely selected binding if one exists, candidate source/schema references, observed metadata, semantic state, approval/evidence references and symbolic construction requirements. Unbound structural candidates are explicitly unverified. No target column, aggregate, label or target value is produced.

### `FeasibilityReadinessAssessment`

Links the exact requirement and target assessment to status, work type, blocking findings, risks, missing information, approvals/clarification needed, next action, evidence/dependency references, limitations, time and governance watermark. Both `execution_authorized` and `performance_estimated` are always false.

| Status | Meaning |
| --- | --- |
| ready_for_preparation_review | Current supplied evidence supports discussion/review of a target-specific preparation specification; not permission to execute it or train |
| analytics_only | The structured objective calls for historical analytics/calculation, not ML; no historical calculation is performed here |
| clarification_required | Missing/ambiguous target, outcome, grain, horizon, support requirements or other necessary structure |
| approval_blocked | Relevant semantic/source-context/treatment/relationship approval is absent, revoked, superseded, stale, conflicting or otherwise unusable |
| insufficient_evidence | Missing/expired/conflicting profiles, inadequate history/classes, unresolved quality/time/availability/validation support or dependencies |
| unsupported | No compatible registered technical strategy or assessment semantics for supplied constraints |

When several categories apply, unsupported precedes clarification, approval blockers and insufficient evidence. The result retains **all** findings; the primary status is not a claim that other blockers disappeared. Successful statuses cannot contain blocking findings. Results are immutable point-in-time evidence: an old successful assessment is not a standing permission after revocation or a changed source.

## Dynamic relevance and target grounding

The engine enumerates only field references authorized in the requirement scope, then resolves current discovery metadata and trusted semantic records. Exact owner-defined concept IDs or exact binding references drive semantic relevance. Physical numerical/categorical/temporal characteristics alone can supply structural hints, never an approved business target.

It neither assumes all available tables matter nor joins matching names. Multiple usable candidates require clarification or an exact selector. An explicit old/superseded target is not silently replaced. Positional similarity across changed snapshots is reported only as a prior-snapshot hypothesis; changed source fingerprints cannot inherit approval even when schema hashes agree.

The engine reuses `SemanticApprovalService.inspect_binding_use()` for the same revocation, supersession, conflicts, expiry, conditions and exact-context checks used by normal semantic assessment. Candidate/result provenance includes the actual approval references. Applicable approval/evidence deadlines bound assessment freshness, but the caller must still reassess before later authorized work.

Requested grain changes or derivations produce construction requirements and approval blockers. Repeated identifiers, line-level counts or an amount-like field do not establish an approved aggregate, revenue definition or primary key. Identifiers requested as dependencies retain their metadata/semantic checks and limitations; uniqueness alone never confirms a business key.

## Technical problem assessment and readiness gates

The default families are extensible technical strategies, not predefined business scenarios:

| Family | Structured characteristics and evidence requirements |
| --- | --- |
| Historical analytics | Historical intent; approved native meaning/grain and quality still apply. No model or future horizon is required |
| Forecasting | Future numerical/count process; approved observation time/grain, matching frequency/horizon, mature support, complete cadence, chronology and defensible chronological validation |
| Regression | Unknown numerical outcome; comparable labelled observations, independent support and admissible decision-time inputs. A future horizon is not automatically required |
| Classification | Categorical/boolean outcome; observed classes, eligible population, verified negatives and mature support. Future outcomes additionally require matching label window, observation time and chronological validation |

The engine does not choose an algorithm. Native type compatibility is one diagnostic, not a definition of the target. Numerical text, formulas, errors and nonfinite values are not silently interpreted as reliable numerical outcomes. Missing target/input values require treatment/eligibility decisions; a tolerance is not imputation approval. Sampled discovery cannot establish full coverage.

Temporal checks distinguish ambiguous day/month values, unresolved centuries, invalid dates and uninterpreted values such as possible numeric serial dates. Partial min/max coverage does not establish complete history. Missing activity is not filled with zero. Time-to-target or feature links across tables require approved relationship/grain contracts, so the initial engine blocks them instead of performing a join.

Predictive support uses explicit requested minimum training/validation observations and horizon requirements. Classification examines typed class counts and per-class support; unequal distribution is reported without inventing a universal imbalance threshold. Counts do not prove performance or that a requested seasonal pattern is supported.

Feature checks are metadata-only: exact approved input bindings, observed availability/missingness, same-table compatibility, known-at-decision evidence and leakage flags. Using the target field through another alias is still target leakage. Current/future-derived information and unresolved availability fail readiness rather than being used to generate features.

Registered `AssessmentStrategy` implementations provide a technical family/version, `supports()` predicate and evidence-based additional findings. They may declare supported constraint keys. Plugins are trusted backend code, not import paths or executable expressions supplied by callers. New families can be added without a question catalogue; unsupported methods remain explicit. No algorithm selection, fitting, metric calculation or confidence value is part of this interface.

## Public interfaces and runtime integration

```python
# runtime is created through the existing explicit start_runtime() interface.
engine = runtime.requirement_assessment_engine()

# scope comes from authorized, exact discovered field references.
# credential is an opaque context verified by the configured identity provider.
requirement = engine.submit_requirement(
    {}, scope=scope, context=credential,
    command_id='unique-submission-command', expected_head=runtime.service.head,
)
```

The empty business payload is accepted but will need clarification. A complete external integration supplies structured concepts/characteristics and, where available, authorized evidence; it does not send a natural-language question for the backend to interpret.

| Method | Responsibility |
| --- | --- |
| `submit_requirement(fields, scope, context, command_id, expected_head, object_id=None, predecessor=None)` | Validate/store an immutable partial requirement under exact scoped submit authority |
| `register_data_evidence(binding_ref, facts, scope, context, command_id, expected_head, valid_until, supporting_evidence=())` | Record a complete, attributed technical summary after consistency and action/scope checks; no missing facts are invented |
| `assess(requirement_ref, context, command_id, expected_head)` | Reauthorize, resolve current semantics/data evidence, assess candidates/task/readiness and atomically persist target/result records |
| `get(ref)` | Exact historical read for trusted backend callers; external integrations must enforce read permissions |
| `StrategyRegistry.register(strategy)` | Register a trusted technical assessment extension, not a question/model route |

Examples with substantially different synthetic schemas are in the [fixture](../../tests/assessment_support.py) and [focused tests](../../tests/test_requirement_assessment.py). Do not construct profile facts by copying example booleans into real data: external profiling and accountable owner evidence are prerequisites.

All mutating operations require explicit action grants (`submit_requirement`, `register_prediction_evidence`, `assess_requirement`) and verified runtime identity. Caller names, role labels, target descriptions or approval-like booleans do not authorize anything. Provider failures return structured errors and durable audit evidence without a fabricated assessment.

The implementation reuses the semantic service's command transaction/replay machinery through a trusted in-process extension. It shares the runtime's catalogue, journal, identity/authorization bridge, clock and persistence. Assessment types are protected journal-issued records; direct generic catalogue import cannot create trusted assessment history. Requirements, targets and results survive restart, with original versions preserved.

## Compatibility and production boundary

Changes to earlier modules are limited and justified:

- [runtime factory](../../src/business_prediction/runtime/factory.py): registers the additional contracts and exposes the engine constructor.
- [durable coordinator](../../src/business_prediction/persistence/coordinator.py): includes assessment records in protected issuance/recovery checks.
- [semantic service](../../src/business_prediction/semantics/service.py): extracts a reusable read-only semantic-state evaluator and adds the restricted metadata-command extension. Existing semantic assessment uses the same evaluator.
- README links to this guide. Earlier architecture/development documents, contract definitions and all existing tests remain unchanged.

Storage format and existing contract versions are not replaced. Existing stores recover through the expanded registry; an older application that lacks these new contract types must not silently downgrade a store containing them. No project database is initialized by this task; tests use temporary state only.

Development uses the existing explicitly configured local providers. Production uses the same engine and requires the existing approved storage/identity/authorization startup gates. There is no development fallback. Production-oriented structured interfaces are implemented, but **no real production database, enterprise identity provider, policy service or external profiling connector is connected**. Read/onboarding ACLs for an external API remain the integration layer's responsibility; backend object/history methods are not public unauthenticated endpoints.

## Validation and restrictions

Run the complete suite from the project root:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
.\.venv\Scripts\python.exe -B -W error -m unittest discover -s tests -t . -q
```

New tests cover partial/unknown requests, unseen concepts and unrelated schemas, multiple targets, unapproved/revoked/superseded meanings, conflicting evidence, forecast/regression/classification characteristics, exact label horizons, insufficient history, missingness, temporal ambiguity/uninterpreted values, leakage, unsupported constraints, external dependencies, cross-table blockers, durable history/restart and production fail-closed behavior. Final validation passed all **141 tests** (105 existing and 36 new) with warnings treated as errors; the run completed in 250.624 seconds. Existing tests remain unchanged.

Preservation validation compared SHA-256 hashes with the implementation-start baseline: 243 existing files were unchanged, four existing files were modified as documented above, 11 files were added and none were removed. All 17 original source files also matched the earlier source-integrity report. Prior reports, four notebooks and existing tests were unchanged; requirements were unchanged and no project database was created. Local links in this guide and README and Python syntax for the added/modified modules passed validation.

No original NOP source is cleaned, transformed, joined, aggregated or used for labels/features/models. Existing reports, notebooks and business-rule evidence are preserved. No preparation, training, evaluation, model registry, inference, LLM, MCP or UI component is implemented. No accuracy, forecast, label value or confidence score is fabricated.

## Limitations and next step

- Evidence summaries are authorized, versioned attestations reconciled with discovery counts; the engine does not independently scan raw records to prove chronology, eligibility, label windows or decision-time availability.
- Concept matching is exact and structured. Synonyms, natural-language interpretation and semantic vocabulary stewardship belong to external integration/owner review. Unknown meanings do not become approved automatically.
- Ready means preparation-specification review only. Data treatments, derived targets, cross-table relationships, feature definitions and execution authorization still need their own approved contracts.
- Raw ambiguous dates, mixed numerical text, unresolved missingness and unsupported dependency evidence remain blockers. No automatic date conversion, deduplication, zero filling or joining resolves them here.
- Supported scope/grain/evidence assumptions remain bounded by the existing framework. Arbitrary joins, causal/counterfactual claims, complex censoring and new technical task families need explicit evidence and trusted extensions; they are not forced into regression or forecasting.
- The local SQLite/full-state runtime retains its prior scalability/security limits. Assessment snapshots can become stale and must be rechecked; they are not portable permission tokens.

Recommended next milestone, **only after explicit approval**: specify target/observation and preparation-plan contracts, resolve the relevant business decisions and implement bounded plan validation. Do not begin source preparation, feature engineering, training or inference automatically.
