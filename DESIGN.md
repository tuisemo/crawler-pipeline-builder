# Design System: Sea Data Crawler Orchestration Workbench

**Product ID:** sea-data
**Primary Screen:** visual workflow designer for browser-backed crawler pipelines

## 1. Visual Theme & Atmosphere

Sea Data should feel like a **mission-control workbench for data acquisition**, not a generic admin dashboard. The interface is professional, calm, technical, and operationally trustworthy. Users are building browser automation pipelines, validating selectors, previewing prompts, generating crawler scripts, and saving executable artifacts, so the design must communicate precision and confidence.

The atmosphere should be **structured, luminous, and instrument-like**. The canvas is the main command surface, while side panels and bottom docks act as supporting instruments. The UI should avoid visual noise, floating drawer conflicts, and decorative effects that compete with configuration work.

Key characteristics:

- Clear workbench zones: command bar, node library, canvas, property inspector, and result dock.
- Bright technical surfaces with subtle depth, so long-running work feels legible rather than heavy.
- Script, DSL, selector, and prompt editing areas use darker code surfaces to signal precision work.
- AI-assisted actions should feel guided and reviewable, never magical or opaque.
- Raw JSON is treated as diagnostic material, not the primary user-facing output.

## 2. Product Experience Principles

### One Canvas, Many Instruments

The workflow canvas remains the center of gravity. Supporting panels must not cover the canvas unexpectedly. Panels can resize, collapse, or switch tabs, but they should stay in the layout flow.

### Action Leads To Evidence

Every action button should move the user to the evidence it produced. Running validation opens the result dock. Opening DSL focuses the DSL workspace. Generating code opens the script workspace. Saving a script produces a clear local path confirmation.

### Generated Artifacts Are First-Class

Scripts, prompts, records, and DSL are user artifacts. They need preview, edit, copy, format, save, restore, and compare affordances. Raw backend payloads are always available but visually secondary.

### Configuration Should Explain Itself

Node configuration should show purpose, dependency, and effect. Selector fields, pagination settings, AI backfill strategy, and extraction fields should include compact hints and validation feedback near the control.

### Safe Automation Over Speed Theater

Crawler orchestration can mutate browser state and write files. Destructive or overwriting actions need explicit confirmation or persistent visible state, while routine actions should stay one click.

## 3. Color Palette & Roles

### Foundation

- **Harbor Mist** (#F3F7FB): primary app background, a cool and quiet base for long sessions.
- **Ice Surface** (#FFFFFF): panel and card surfaces.
- **Pale Blueprint** (#EFF6FF): selected or gently highlighted surfaces.
- **Dock Slate** (#0F172A): code, DSL, and raw diagnostic surfaces.

### Primary & Interactive

- **Command Blue** (#2563EB): primary actions, active navigation, selected nodes, focus rings.
- **Signal Cyan** (#06B6D4): secondary technical accents, field count indicators, selector assistance.
- **Graph Indigo** (#4F46E5): graph-specific emphasis, flow badges, active workflow structure.

### Feedback

- **Verified Green** (#16A34A): successful validation, saved files, synced DSL.
- **Caution Amber** (#F59E0B): partial execution, unsaved edits, recoverable schema warnings.
- **Fault Red** (#DC2626): failed requests, destructive actions, invalid selectors.
- **Info Slate** (#64748B): neutral metadata, helper text, inactive status.

### Lines & Text

- **Ink Black** (#0F172A): primary text and key labels.
- **Readable Slate** (#334155): secondary but important body text.
- **Muted Steel** (#64748B): hints, metadata, disabled copy.
- **Soft Border** (#DBEAFE): panel strokes, canvas boundary, low-contrast separators.
- **Structural Border** (#CBD5E1): stronger panel dividers and dock separation.

Usage rules:

- Use Command Blue only for active controls and primary completion paths.
- Keep destructive actions red and visually isolated from common workflow controls.
- Use dark surfaces only where users read or edit structured text: code, prompt, DSL, JSON.
- Avoid purple as the default SaaS accent; use indigo only for graph semantics.

## 4. Typography Rules

Primary UI typography should be a modern, compact sans-serif with excellent Chinese and Latin readability. Use the existing app stack if no dedicated font is bundled, but design future refinements around:

- **Display / Page Title:** 28-36px, 800 weight, tight line-height, used only in the main toolbar identity.
- **Panel Titles:** 14-16px, 700-800 weight, clear and compact.
- **Body Text:** 13-14px, 400-500 weight, relaxed enough for Chinese explanations.
- **Metadata / Hints:** 11-12px, 400-500 weight, muted color, never the only carrier of critical information.
- **Code / Selectors / DSL:** 12.5-13.5px monospace, 1.55-1.65 line-height, dark surface or high-contrast light surface.

Text behavior:

- Button labels should be action-oriented: "生成脚本", "保存到项目", "复制脚本".
- Panel copy should be concise and instructional.
- Avoid mixing English and Chinese unless the term is an actual API or DSL keyword.
- Long IDs and selectors should truncate visually but remain copyable.

## 5. Layout Principles

### Desktop Workbench

Use a five-zone model:

- **Top Command Bar:** workflow identity, selected node, execution boundaries, and run actions.
- **Left Node Library:** addable node types, search/filter later, compact descriptions.
- **Center Canvas:** React Flow graph, minimap, fit controls, canvas-level helper overlay.
- **Right Inspector:** selected node configuration, AI assistance, validation and dependency hints.
- **Bottom Dock:** execution results, script workspace, prompt workspace, DSL editor, raw diagnostics.

Desktop layout should use a stable grid:

- Left panel: 280-320px.
- Right inspector: 360-440px.
- Canvas: flexible center, never below 140px while bottom dock is open.
- Bottom dock: flexible but should receive more space for script or DSL views.

### Responsive Behavior

- At tablet width, side panels can stack above/below the canvas but must remain collapsible.
- At mobile width, use a single-column task flow with explicit tabs: "画布", "配置", "结果", "DSL".
- Avoid overlapping drawers on small screens; if a modal is unavoidable, it must block only one focused task.

## 6. Component Styling

### Command Bar

The command bar is a bright operational header. It should combine product identity, workflow summary, and action buttons without becoming a crowded ribbon.

- Surface: Ice Surface (#FFFFFF), subtle lower shadow.
- Primary action: filled Command Blue.
- Secondary actions: outlined, white background, blue-gray stroke.
- Running action: disabled peers plus spinner inside the active button.

### Workspace Switcher

Panel toggles should look like mode controls, not random utility buttons.

- Active state: Command Blue fill.
- Inactive state: white surface with Structural Border.
- Labels should match visible zones: "节点库", "属性配置", "执行结果", "DSL 编辑器".

### Panels

Panels should feel like docked instruments.

- Radius: 16-18px.
- Stroke: Structural Border or Soft Border.
- Shadow: soft and diffuse, never heavy.
- Header: compact, fixed height, icon + label + optional status.
- Body: internal scroll only; the full app shell should not scroll.

### Canvas Nodes

Nodes are compact execution cards.

- Width: 200-230px.
- Radius: 14px.
- Selected state: Command Blue stroke plus soft blue halo.
- Type badge: pill-shaped, pale blue background.
- Summary text: single-line truncation.
- Handles: visible blue points with white border.

Node categories should later receive semantic accents:

- Entry and navigation nodes: blue.
- Extraction nodes: cyan.
- Control-flow nodes: indigo.
- Output nodes: green.
- Termination nodes: slate.

### Property Inspector

The inspector should be the place where users understand and correct node behavior.

- Group fields by intent: identity, target, limits, extraction, AI assistance, advanced.
- Each group should have a short explanation and local validation.
- Selector inputs use monospace and optional test/optimize buttons nearby.
- Repeated fields should use table-like rows on desktop and stacked cards on mobile.

### Bottom Result Dock

The result dock is an artifact workspace.

- It should default to the most useful artifact for the last action.
- Script generation opens "脚本工作区".
- Prompt preview opens "提示词工作区".
- Validation opens structured validation findings.
- Raw JSON is collapsed under diagnostics.

### Code, Prompt, And DSL Surfaces

Structured text surfaces should be stable and copy-friendly.

- Background: Dock Slate (#0F172A).
- Text: pale blue-white (#DBEAFE).
- Radius: 10-12px.
- Controls above the editor: copy, edit, format, restore, save, wrap mode.
- If Monaco is used inside hidden tabs, enforce layout recalculation; otherwise prefer a reliable textarea for DSL editing.

## 7. Motion & Feedback

Motion should clarify cause and effect.

- Panel open/close: 160-220ms ease-out.
- Node add: fit-to-view and brief selection highlight.
- Result arrival: dock focus and subtle reveal, not a toast-only confirmation.
- Save success: inline path confirmation plus success tag.
- Validation errors: anchor the user to the affected field or node when possible.

Avoid decorative motion that interferes with precision work.

## 8. Accessibility & Usability

- All icon buttons need visible text or tooltips.
- Focus states must be visible on buttons, tabs, inputs, canvas controls, and code actions.
- Color must not be the only status signal; pair color with label text.
- Code areas need copy buttons and keyboard-selectable content.
- Error messages should identify the failing action and a next step.
- Long-running actions should prevent conflicting execution but leave non-conflicting navigation available.

## 9. Do / Do Not

Do:

- Keep generated scripts and prompts at the top of result views.
- Use layout-flow panels instead of overlapping drawers.
- Keep diagnostic JSON accessible but visually secondary.
- Make every AI-assisted edit reviewable before it mutates the workflow.
- Preserve canvas state and selection when switching panels.

Do not:

- Hide generated artifacts behind raw payloads.
- Let bottom panels cover the property inspector.
- Use generic dashboard cards for everything.
- Overload the toolbar with rarely used controls.
- Rely on toast messages as the only confirmation for important actions.

## 10. Agent Implementation Guide

When modifying the frontend:

1. Start from this file before changing visual design.
2. Prefer semantic class names such as `bottom-dock`, `workbench-panel`, `script-workspace`, and `node-inspector`.
3. Add or update CSS custom properties before scattering raw colors.
4. Treat script, prompt, DSL, and records as first-class artifacts.
5. Verify real UI behavior with a headed browser after layout changes.
6. Do not introduce overlapping drawers unless a focused modal task truly requires it.

