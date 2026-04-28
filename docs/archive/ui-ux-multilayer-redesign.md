# Scraper Orchestration UI/UX Multilayer Redesign

## 1. Redesign Goals

1. Keep canvas as the primary workspace and avoid layout compression from tool panels.
2. Convert side/config/result areas into layered surfaces that appear on demand.
3. Reduce top chrome footprint and improve action discoverability.
4. Stabilize visual system (color, spacing, hierarchy) for long-session authoring.
5. Keep all workflow authoring paths intact (node add/edit/DSL/run/inspect outputs).

## 2. Spatial Model

### Layer 0: Canvas Stage (always visible)
- Full-height workspace with graph as first-class surface.
- Health signals (entry/end/disconnected) shown in the canvas header.
- Fit-view behavior on node add / DSL apply to keep new nodes visible.

### Layer 1: Floating Controls
- Compact quick controls (palette/properties/results/DSL) pinned over canvas.
- Replaces full-width control row and preserves vertical space.

### Layer 2: Floating Side Panels
- Left panel: node palette.
- Right panel: property editor.
- Both are overlays, not layout columns, so they do not squeeze the canvas.

### Layer 3: Bottom Dock Overlay
- Results / DSL editor as slide-up dock.
- Closed by default; auto-opens when actions execute.
- No permanent reserved height.

## 3. Interaction Design

1. **Author flow**
   - Add node from left floating palette.
   - Canvas auto-fit to include new node.
   - Select node to open right properties panel.
2. **Configure flow**
   - Structured property sections with risk alerts and field-level validation.
   - Selector test available in relevant nodes/fields.
3. **Run flow**
   - Action buttons in compact top toolbar.
   - Bottom dock auto-focuses to results on execution.
4. **Debug flow**
   - Artifact tabs + diagnostics JSON.
   - Prompt/script editing and save/format actions remain in-place.

## 4. Visual Language

1. **Compact top bar**
   - One-line identity + operational chips + action clusters.
2. **Consistent cool-tone palette**
   - Blue/cyan/teal for operational states; green for output.
3. **Node semantics**
   - Source/Collect/Transform/Output node categories with distinct backgrounds.
4. **Depth system**
   - Layered shadows and translucent cards for spatial separation.

## 5. Implemented in Current Refactor

1. `frontend/src/App.tsx`
   - Switched from rigid 3-column + fixed bottom occupancy to layered workspace shell.
   - Added `workflowContext` injection into `PropertyPanel`.
   - Added selector test action (`handleTestSelector`) using `/api/assist/extract-html`.
   - Added `fitViewToken` trigger for node add / DSL apply.
2. `frontend/src/components/WorkbenchToolbar.tsx`
   - Rebuilt into compact mode with grouped quick actions and summary chips.
3. `frontend/src/components/WorkflowCanvas.tsx`
   - Added graph health diagnostics in header.
   - Added node visual categories and group metadata.
   - Added fit-view token response.
4. `frontend/src/components/workflowEdgeDecorators.ts`
   - Added source-type semantic edge labels and colors for non-branch edges.
5. `frontend/src/components/workflowEdgeDecorators.test.ts`
   - Added pagination semantic edge coverage.
6. `frontend/src/App.css`
   - Replaced layout system with multilayer style architecture.
   - Fixed DSL textarea height chain for consistent editor visibility.

## 6. Next Iteration (Recommended)

1. Add drag-resize handles for right panel and bottom dock.
2. Add keyboard shortcuts overlay (`P` palette, `R` results, `D` DSL).
3. Add mini command bar for quick node insertion (`Ctrl/Cmd+K`).
4. Add visual execution replay on canvas edges/nodes after test run.
