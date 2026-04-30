# Detail Batch Runner Implementation Plan

## 1. Purpose

This document converts the approved design set for the detail batch runner product line into an execution-oriented engineering plan.

It focuses on:

- the independent detail extractor CLI
- the detail task store and state machine
- the generated batch orchestration script capability
- the connection between list-page SQLite outputs and detail-page task execution


## 2. Inputs

This implementation plan is based on the following design specs:

- [Detail Batch Runner And CLI Bridge Design](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-and-cli-bridge-design.md)
- [Detail Task Store And State Machine Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-task-store-and-state-machine-spec.md)
- [Detail Extractor CLI Contract Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-extractor-cli-contract-spec.md)
- [Detail Batch Runner Generation Context Schema](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-generation-context-schema.md)
- [Detail Batch Runner Python Skeleton Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-python-skeleton-spec.md)
- [Generate Detail Batch Runner Capability Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-generate-detail-batch-runner-capability-spec.md)
- [Detail Batch Runner Validation And Acceptance Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-validation-and-acceptance-spec.md)
- [Detail Batch Runner Frontend Presentation Spec](/D:/WY-DATASETS/sea-data/docs/superpowers/specs/2026-04-30-detail-batch-runner-frontend-presentation-spec.md)


## 3. Delivery Strategy

The work should be implemented in two parallel product tracks:

1. **Runtime engineering track**
   Builds the detail extractor CLI and task orchestration runtime contracts.

2. **Script generation track**
   Builds the platform capability that generates the stage-2 batch orchestration script.

The runtime track must define stable contracts first. The generation track should depend on those contracts instead of inventing them.


## 4. Phase Breakdown

### Phase 0: Contract Preparation

#### Goal

Freeze the core contracts before implementation starts.

#### Deliverables

- approved task table schema
- approved state machine
- approved detail CLI summary schema
- approved batch runner skeleton contract
- approved generation context schema

#### Tasks

1. finalize `detail_collection_tasks` schema
2. finalize status values and transitions
3. finalize required CLI arguments and stdout summary fields
4. finalize the generated script skeleton structure
5. finalize validation checklist for generated scripts

#### Exit criteria

- no unresolved naming disagreements across the contract docs
- all five docs are cross-consistent


### Phase 1: Detail Extractor CLI Productization

#### Goal

Create a pure engineering detail collection capability package that can be called by the future batch runner.

#### Deliverables

- installable CLI package
- `collect` subcommand
- task workspace layout
- task-local logs
- stdout JSON summary

#### Tasks

1. create package structure for the detail extractor runtime
2. implement stable CLI entry point
3. implement task workspace creation
4. implement summary JSON writing and stdout printing
5. implement runtime logging
6. document exit code semantics

#### Exit criteria

- one URL can be processed through CLI
- stdout returns valid JSON summary
- logs and workspace artifacts are created deterministically


### Phase 2: Detail Task Store Runtime

#### Goal

Create the durable database bridge between list results and detail execution tasks.

#### Deliverables

- task table creation logic
- sync logic from list result table
- claim/update logic
- retry ceiling enforcement

#### Tasks

1. implement task table DDL
2. implement sync logic for `(record_id, detail_url)`
3. implement runnable task query
4. implement claim transition to `running`
5. implement success/failure update functions
6. implement index creation

#### Exit criteria

- new tasks can be synced from the list result database
- rerunning sync does not create duplicate tasks
- lifecycle updates are durable and queryable


### Phase 3: Batch Runner Skeleton Runtime

#### Goal

Create a deterministic Python batch-runner skeleton that works without model generation first.

#### Deliverables

- local reference implementation of the batch runner skeleton
- working `ThreadPoolExecutor` concurrency path
- subprocess invocation path
- final run summary

#### Tasks

1. implement `Config`
2. implement `TaskRepository`
3. implement `CliInvoker`
4. implement `TaskRunner`
5. implement `BatchExecutor`
6. implement CLI entry and logging

#### Exit criteria

- a local handwritten reference script can:
  - sync tasks
  - claim tasks
  - invoke the detail CLI
  - persist task results


### Phase 4: Script Generation Capability

#### Goal

Turn the stage-2 batch runner into a first-class script generation product capability.

#### Deliverables

- generation payload builder
- prompt contract
- deterministic skeleton injector
- output validator

#### Tasks

1. define `Generate Detail Batch Runner` request/response contract
2. implement payload builder from database + field mapping + policy inputs
3. build skeleton-enhancement prompt flow
4. implement script validator against the skeleton checklist
5. add save/export path for generated batch runner scripts

#### Exit criteria

- the platform can generate a runnable batch-runner script from structured inputs
- generated script passes validation checks


### Phase 5: End-To-End Product Integration

#### Goal

Connect mature list-page outputs to detail execution through the generated batch runner.

#### Deliverables

- operator documentation
- example config / sample DB walkthrough
- end-to-end smoke path

#### Tasks

1. create sample SQLite list result fixture
2. generate a batch-runner script against that fixture
3. run the script against the detail CLI
4. verify task table updates and artifact path persistence
5. write operator guide

#### Exit criteria

- one end-to-end flow is reproducible by an operator without manual database editing


### Phase 6: Frontend Optional Second-Stage Entry

#### Goal

Expose the detail batch-runner generation capability in the existing workbench without disturbing the current list-workflow authoring flow.

#### Deliverables

- contextual frontend entry for `Generate Detail Batch Runner`
- derived configuration form
- integrated result rendering for the secondary script

#### Tasks

1. add frontend API support for `/api/workflows/generate-detail-batch-runner`
2. add a contextual entry in the script results workspace
3. prefill configuration from the current list-script output contract where possible
4. show validation status and warnings in the result workspace
5. reuse existing copy / format / save affordances for the secondary script

#### Exit criteria

- the feature is only visible in eligible contexts
- users can generate a detail batch-runner script without leaving the current workbench flow
- existing primary list-script flows remain unchanged


## 5. Workstream Mapping

### Workstream A: Runtime contracts

Owner area:

- detail CLI package
- task store logic
- artifact and logging conventions

### Workstream B: Generation contracts

Owner area:

- context schema
- skeleton contract
- prompt contract
- script validation

### Workstream C: Integration and documentation

Owner area:

- example datasets
- operator workflow
- smoke testing and docs


## 6. Recommended Repository Changes

The future implementation will likely need these new areas:

- `backend/detail/`
- `backend/detail_batch/` or equivalent orchestration module
- new prompt / generation assets for detail batch runner
- documentation for generated script usage

The exact module layout can be finalized during implementation, but the capability split should remain stable.


## 7. Acceptance Criteria By Capability

### 7.1 Detail extractor CLI

Accepted when:

- it handles one URL per invocation
- it writes deterministic task artifacts
- it returns JSON summary to stdout

### 7.2 Task store

Accepted when:

- it syncs from the list result table
- it prevents duplicate logical task rows
- it tracks retries and terminal states durably

### 7.3 Batch runner runtime

Accepted when:

- it supports thread-based concurrent invocation
- it classifies failures deterministically
- it resumes from database state after restart

### 7.4 Batch runner generation

Accepted when:

- generated scripts follow the skeleton contract
- generated scripts reference the correct DB and CLI contracts
- generated scripts pass a static validation checklist


## 8. Validation Strategy

### Static validation

Validate generated scripts for:

- required classes
- required functions
- required task statuses
- presence of `subprocess.run`
- presence of `ThreadPoolExecutor`
- correct CLI executable usage

### Contract validation

Validate:

- task summary JSON shape
- task table schema compatibility
- field name mapping correctness

### Runtime smoke validation

Validate:

- syncing new tasks
- claiming and running tasks
- writing success and failure outcomes
- resumability after interruption


## 9. Major Risks

### Risk 1: Contract drift

If the detail CLI evolves without preserving summary shape, generated scripts will break.

Mitigation:

- keep the summary contract versioned
- validate the contract before generation

### Risk 2: Overfree generation

If the model is asked to generate the whole stage-2 script from free-form text, the quality will be inconsistent.

Mitigation:

- use deterministic payloads
- use a fixed skeleton contract
- validate generated output

### Risk 3: SQLite contention

If task claiming is not centralized, duplicate local execution becomes more likely.

Mitigation:

- main-thread claiming only
- worker threads only invoke subprocesses

### Risk 4: Boundary erosion

If the batch runner begins to absorb detail extraction logic, both runtime and generation complexity will spike.

Mitigation:

- enforce CLI-only detail execution
- treat detail extraction as an external capability package


## 10. Recommended Implementation Order

The recommended order is:

1. freeze contracts
2. build detail CLI
3. build task store
4. build handwritten reference batch runner
5. turn the reference runner into a generation skeleton
6. add generation payload builder and validator
7. document and smoke test the end-to-end flow


## 11. Final Recommendation

Do not start with model generation first.

Start with:

- stable runtime contracts
- a reference batch runner skeleton

Then turn those into:

- a deterministic generation capability

This sequence minimizes rework and gives the script-generation layer a stable engineering target.
