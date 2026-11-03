# NOP source readiness and first-dataset workflow

## Actual status

The current milestone performs read-only source discovery and evidence review. **Preparation and publication are blocked.** No training dataset, target values, features, train/validation/test split, model or forecast is produced. The request authorizes conditional preparation; it does not confirm the unresolved business definitions or confer owner authority.

See the [source readiness report](../../reports/analysis/nop_dataset_readiness_report.md), [objective assessment](../../reports/analysis/nop_prediction_objective_assessment.md), [machine-readable readiness evidence](../../reports/analysis/nop_readiness_evidence/readiness_assessment.json) and [exact approval questions](../../reports/analysis/nop_readiness_evidence/approval_blockers.json).

## Reused implementation

The [read-only evidence runner](../../reports/analysis/nop_readiness_evidence/assess_sources.py) uses the existing Excel/CSV adapters and `discover()`. Source names are enumerated recursively, not a fixed list. Prior header-row configurations are data read from the validated inventory, applied only when the recorded source hash matches. They remain unapproved physical layout interpretations.

Discovery captures source SHA-256 versions, physical schemas, field positions, table extents, missingness, type mixtures and unapproved identifier/temporal hypotheses. A 32-row prefix bounds new profiling. Adapters still read the complete physical source to discover table extents and check source integrity. The configured read budgets are 64 MiB compressed source bytes, 256 MiB expanded workbook bytes and 6 million cells per file; exceeding a budget is a reported failure, not permission to truncate a dataset.

Previously validated full-table profiles, date/identifier evidence, duplicate analysis, relationship findings and feasibility conclusions are reused for identical source hashes and matching physical table shapes/headers. Prefix observations are never represented as full-table statistics. Old diagnostic date coverage retains its documented 2 November 2026 cutoff and parsing caveats; no dates are converted or business closure inferred.

The existing assessment engine's pure intake, strategy and target assessors are exercised without impersonating a business owner. Technical family recognition is not data feasibility. A governed `PredictionRequirementAssessmentEngine` submission/assessment cannot be executed without an explicitly configured authenticated runtime, approved bindings and attributable target evidence. **No governed assessment record is issued in this milestone.** The evidence records this boundary rather than creating development grants for NOP data.

No core framework module, existing report or approval register is changed. The report runner is narrow evidence tooling, not a new execution abstraction or a fixed question-to-model routing system.

## Required next owner actions

Use D01–D13 in the existing [business clarification brief](../../reports/analysis/initial_prediction_business_clarification.md) and [readiness workbook](../../reports/analysis/initial_prediction_readiness_checklist.xlsx). They cover the authoritative source/version and authenticity; event/use; scoped document identity and detail grain; date grammar and event meaning; cancellations/returns; extraction maturity; calendar/completeness/zero policy; repeated exports; horizon/cadence; history/evaluation support; and accountable authorization.

The [decision response log](../../reports/analysis/initial_prediction_clarification_evidence/decision_response_log.csv) has no recorded confirmations. Source field consistency and unique values cannot resolve these decisions. Role labels in the brief are requested responsibilities, not authenticated approvers. D14–D17 are conditional; customer/product enrichment, monetary/unit rules, GST reconciliation and alternate mixed-date sources are required only if the agreed objective actually needs them. Unrelated inventory or GST sign-off is not a prerequisite for an issuer-level invoice count.

After the owner supplies answers/evidence, the existing approval service must verify the actual approver's authority and record exact purpose, scope, object version, timestamp, evidence, conditions and expiry/review requirements. Existing decisions must be preserved; this milestone does not edit the response log or 36-rule register.

## Bounded execution path after blockers are resolved

These are prerequisites, not actions performed or approvals granted here:

1. Onboard the approved source/version into an explicitly configured authenticated runtime. Publish the exact `DataSourceMetadata` / `SchemaDiscoveryResult` revisions. Discovery exports from this assessment are unapproved evidence, not signed production snapshots.
2. Propose exact `SemanticBinding` revisions for required fields/time/identity meanings; obtain scoped current `ApprovalRecord` records. Register attributable `PredictionDataEvidence`, submit the agreed `PredictionRequirementSpecification` and run the existing assessment engine. Its best readiness result still requires separate preparation review.
3. Create `PredictionTargetSpecification` and `ObservationSpecification`, plus `RelationshipSpecification` only for necessary approved relationships. Obtain the applicable `SpecificationApprovalRecord` records. No join is required by default.
4. Resolve any execution capability gap through a separately approved implementation task. The discussion-first invoice-document count needs document-grain/time-bucket construction; the present local worker rejects aggregation, derived targets and grain changes. It also cannot interpret ambiguous dates. Validation-only declarations do not supply executable operators.
5. Specify an exact `DataPreparationPlanSpecification`, issue current `PreparationPlanValidation`, and obtain scoped plan/operation approvals. Verify supported operators, reconciliations, source/schema versions, observation grain, chronology, explicit duplicate/missingness rules and leakage restrictions. Do not weaken checks to admit the data.
6. Use existing execution request/authorization, worker identity, active lease/fence and registered operator sequence. Write only isolated derivative staging artifacts; preserve original sources, rejected records, operation receipts and immutable lineage.
7. Verify target/observation validity, row partitions, hashes, schema/grain, chronology, known-at-cutoff evidence and execution completeness. Failure or missing reconciliation blocks success.
8. Request separate publication authority; recheck approvals, source versions and every artifact before immutable publication. Only a committed `PreparationPublicationRecord` plus verified objects establishes publication. Record artifact location, SHA-256, schema, row counts and validation/provenance.

If approval, authorization, data evidence or supported execution is missing, stop. Do not bypass the worker, substitute source rows for the target, create labels, impute zeros or guess dates. Production mode must continue to reject development-only providers and absent external integrations. A bounded local run still needs explicitly assigned real approval/authorization; synthetic test credentials confer none.

## Meaning of training-ready in this milestone

A published artifact would contain validated observations and approved target values suitable for subsequent ML preparation. It would not imply sufficient model accuracy or permission to train. Population/target completeness, unambiguous time, explicit grain and duplicate policies, mature observations and point-in-time input availability must be proved for the approved purpose.

Chronological development/holdout **requirements** must be specified where relevant, but no train/validation/test split, feature construction or model training occurs in this milestone. A historical count or diagnostic aggregation is analytics, not a prediction.

## Reproduction and evidence preservation

The completed evidence directory is immutable to the runner. For another authorized read-only assessment, use a different empty output directory:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
New-Item -ItemType Directory -Path reports/analysis/nop_readiness_evidence_review
.\.venv\Scripts\python.exe -B -W error reports/analysis/nop_readiness_evidence/assess_sources.py --root . --output reports/analysis/nop_readiness_evidence_review
```

The runner enumerates all file formats. Unsupported/unreadable sources are recorded as failures; none is silently excluded. It writes exclusive JSON evidence only, verifies source hashes before/after, and never creates an execution/artifact store or approval. Use a new directory for each review and keep prior evidence.

[Synthetic evidence-tool tests](../../tests/test_nop_readiness_evidence.py) exercise unfamiliar Excel/CSV schemas, mixed and absent values, ambiguous/invalid dates, unsafe prior-profile reuse, insufficient documentary confirmation, unsupported technical outputs and exclusive evidence writes. Existing framework tests cover insufficient history, leakage, approval lifecycle, source immutability, integrity, interruption/recovery and production fail-closed behavior. The full suite runs with warnings treated as errors; final results are recorded in the readiness report.

## Stop boundary

Next action is the scoped NOP owner review, not cleaning or training. Once the exact answers and authorization are available, reassess against the unchanged contracts and separately approve any necessary operator capability. No further development activity is started by this document.
