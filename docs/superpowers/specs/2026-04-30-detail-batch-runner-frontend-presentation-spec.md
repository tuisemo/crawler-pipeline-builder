# Detail Batch Runner Frontend Presentation Spec

## 1. Purpose

This document defines how the new optional capability:

- `Generate Detail Batch Runner`

should be presented in the frontend workbench without disrupting the current list-page workflow authoring and script generation experience.

The capability is not a new mandatory workflow step. It is a **derived second-stage script generation action** based on the output contract and execution context of an already generated list-page script.


## 2. Design Goals

The frontend presentation must achieve the following:

1. Keep the current list-page workflow authoring flow unchanged.
2. Present detail batch-runner generation as an optional post-processing action.
3. Reuse as much of the current script viewing, formatting, saving, and result-display infrastructure as possible.
4. Make it clear that this is a second-stage orchestration script, not a replacement for the primary crawler script.
5. Minimize additional cognitive load for users who do not need detail-page collection.


## 3. Non-Goals

This spec does not require:

- adding new workflow canvas nodes
- adding detail extraction configuration into the DSL editor
- changing the main node palette
- forcing all users through a detail-page setup flow


## 4. Current Frontend Structure

The current workbench is centered around:

- [App.tsx](/D:/WY-DATASETS/sea-data/frontend/src/app/App.tsx)
- [WorkbenchToolbar.tsx](/D:/WY-DATASETS/sea-data/frontend/src/app/components/WorkbenchToolbar.tsx)
- [useWorkflowActions.ts](/D:/WY-DATASETS/sea-data/frontend/src/features/workflow/useWorkflowActions.ts)
- [ResultsPanel.tsx](/D:/WY-DATASETS/sea-data/frontend/src/features/results/ResultsPanel.tsx)
- [ResultDetails.tsx](/D:/WY-DATASETS/sea-data/frontend/src/features/results/ResultDetails.tsx)
- [workflowApi.ts](/D:/WY-DATASETS/sea-data/frontend/src/services/workflowApi.ts)

Current user mental model:

1. design DSL on canvas
2. validate / preview prompt / compile plan
3. generate skeleton or crawler script
4. inspect results in the results dock
5. optionally format / save / run generated script

The new capability should feel like a continuation of step 4 and step 5, not like a separate top-level product.


## 5. Product Positioning In The UI

### 5.1 Primary principle

The detail batch runner should be shown as:

- an optional **derived script generation action**

not as:

- a mandatory toolbar action in the core list-workflow path
- a new workflow node type
- a permanent extra panel in the main canvas flow

### 5.2 User-facing meaning

Frontend wording should make the distinction explicit:

- primary script: list-page collector
- secondary script: detail-page batch runner

This avoids the confusion that both are just “generate script” buttons with similar scope.


## 6. Recommended Entry Point

### 6.1 Preferred placement

The recommended primary entry point is inside the **results/script workspace**, after a list-page script has already been generated successfully.

Best placement:

- the script-focused area in [ResultDetails.tsx](/D:/WY-DATASETS/sea-data/frontend/src/features/results/ResultDetails.tsx)

This is the right place because:

- the user is already looking at the generated list script
- the user already has the relevant output contract context in mind
- the existing UI already supports script actions like format, save, and sandbox run

### 6.2 Why not the main toolbar first

Adding a new toolbar primary action immediately would create two problems:

1. it would suggest that detail batch-runner generation is part of the normal first-stage workflow
2. it would increase toolbar complexity for users who only need list collection

Therefore the first entry should be contextual and secondary.


## 7. Recommended Interaction Flow

The frontend interaction should be:

1. User generates a list-page script successfully.
2. In the script result workspace, the UI offers:
   - `Generate Detail Batch Runner`
3. Clicking it opens a lightweight configuration surface.
4. The form is prefilled from the current result payload when possible.
5. User confirms or adjusts the derived settings.
6. Frontend calls `/api/workflows/generate-detail-batch-runner`.
7. The returned batch-runner script is shown in the same script-oriented work area as a secondary generated artifact.


## 8. Recommended Trigger Conditions

The frontend should only show the entry when all of these are true:

1. current result action is script-related
   - `generate-script`
   - optionally later: `generate-skeleton`

2. result payload contains a generated script

3. result payload or known workflow output settings imply durable output, ideally SQLite

4. the user can supply or confirm a `detail_url` field mapping

### 8.1 Soft requirement

The UI may still allow manual launch even if the output contract is incomplete, but then it must show the configuration form with more required user input.


## 9. Configuration Surface Design

### 9.1 Recommended presentation form

Use a lightweight, task-focused drawer or modal instead of a full-screen new page.

Recommended component shape:

- right-side drawer
- or inline secondary panel within the results workspace

Preferred first version:

- a compact drawer

Reason:

- keeps users in the same mental context
- does not break the current workbench layout
- allows progressive disclosure

### 9.2 Required fields in the form

The configuration surface should expose:

- database path
- list result table name
- record ID field
- detail URL field
- detail task table name
- CLI output root
- concurrency
- batch size
- max attempts
- timeout

### 9.3 Recommended field sources

Prefill from:

- list script output mode
- list script output path
- list script known table name
- inferred or remembered field names

### 9.4 Recommended advanced fields

Hide these behind an “advanced settings” section:

- CLI executable
- CLI command prefix
- source URL field
- title field
- dry-run behavior
- limit behavior
- generation mode
  - `skeleton_enhancement`
  - `llm_skeleton_enhancement`


## 10. Result Presentation For The Secondary Script

### 10.1 Reuse the existing script viewer

Do not build a brand-new viewer for the generated batch runner.

Reuse the existing script-focused result experience in:

- [ResultsPanel.tsx](/D:/WY-DATASETS/sea-data/frontend/src/features/results/ResultsPanel.tsx)
- [ResultDetails.tsx](/D:/WY-DATASETS/sea-data/frontend/src/features/results/ResultDetails.tsx)

### 10.2 Distinguish primary vs secondary generated scripts

The UI must clearly label:

- `List Collector Script`
- `Detail Batch Runner Script`

This can be done through:

- a badge
- a section subtitle
- a generation-type tag

### 10.3 Recommended metadata display

For the generated detail batch runner, surface:

- generation mode
- task table name
- detail CLI executable or command prefix
- validation passed / failed
- warnings


## 11. Recommended UI States

The feature should support the following states:

### 11.1 Idle / hidden

No entry shown when no eligible list script result is present.

### 11.2 Eligible

Entry shown, waiting for user action.

### 11.3 Configuring

Drawer or inline configuration surface open.

### 11.4 Generating

Loading state while `/generate-detail-batch-runner` is running.

### 11.5 Generated successfully

Script shown in the script workspace with validation summary.

### 11.6 Validation warning

Script returned but validation warnings exist.

### 11.7 Failed

Inline error alert with backend error message.


## 12. Result Workspace Layout Recommendation

### 12.1 First version

Recommended first-version layout:

- keep the existing “script” tab
- add a script-variant switch inside that tab

Example:

- `List Script`
- `Detail Batch Runner`

This avoids adding a completely new dock tab and minimizes layout churn.

### 12.2 Why not a new bottom-dock tab first

A new dock tab would:

- increase navigation complexity
- create another major workspace concept
- fragment related script artifacts

The two scripts are better treated as related artifacts of the same overall data-collection workflow.


## 13. Data Flow In The Frontend

### 13.1 Existing flow

Today:

- `useWorkflowActions.ts` triggers first-stage actions
- `workflowApi.ts` posts to workflow endpoints
- `ResultsPanel.tsx` and `ResultDetails.tsx` render results

### 13.2 New flow

Recommended new frontend flow:

1. derive default detail-batch-runner config from current result payload
2. user edits the config surface
3. frontend posts to `/api/workflows/generate-detail-batch-runner`
4. response is normalized into the existing results model
5. script viewer shows the returned script and validation result

### 13.3 Frontend code integration points

Likely integration points:

- add new path to [workflowApi.ts](/D:/WY-DATASETS/sea-data/frontend/src/services/workflowApi.ts)
- extend result payload handling in [ResultDetails.tsx](/D:/WY-DATASETS/sea-data/frontend/src/features/results/ResultDetails.tsx)
- add a contextual secondary action host in the result script area
- optionally add frontend types for:
  - detail batch runner request
  - detail batch runner response
  - validation payload


## 14. Non-Disruption Rules

To avoid impacting the current product:

1. Do not add new workflow node types for this feature in phase 1.
2. Do not force users to configure detail-page settings before they can generate a list script.
3. Do not move or rename existing primary actions.
4. Do not change the current results dock information architecture more than necessary.
5. Keep the new feature visually secondary unless explicitly opened.


## 15. Recommended Progressive Rollout

### Phase A: Hidden contextual entry

- only shown after successful list script generation
- configuration in a small drawer
- result shown in the same script workspace

### Phase B: Richer derivation and autofill

- infer more defaults from list output contract
- remember prior mappings
- support reusable presets

### Phase C: Stronger integration

- show both primary and secondary script lifecycle together
- optionally support “regenerate detail runner” from saved result state


## 16. Recommended UX Copy Direction

Suggested labels:

- `Generate Detail Batch Runner`
- `Based on the current list output contract`
- `Optional second-stage script`
- `Reads detail URLs from SQLite and dispatches detail extraction tasks`

Avoid ambiguous labels like:

- `Generate Another Script`
- `Detail Script`

because they do not communicate the orchestration nature of the artifact.


## 17. Frontend Acceptance Criteria

The frontend presentation is acceptable when:

1. existing list-workflow authoring is unchanged
2. the new entry appears only in an eligible context
3. the user can confirm or edit derived settings
4. the frontend can call the new backend generation endpoint
5. the returned script is shown using the existing script workspace patterns
6. the user can still copy, save, format, and inspect the generated batch runner script


## 18. Final Recommendation

Present the feature as a **contextual, optional, second-stage script generation action inside the existing script result workspace**.

This is the least disruptive and most intuitive frontend shape because it keeps:

- list-page workflow authoring as the main path
- detail orchestration as a derived next step
- script artifacts grouped together in one mental model
