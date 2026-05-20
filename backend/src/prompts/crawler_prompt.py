"""Crawler prompt generation for crawler-workflow.

Generates structured, execution-plan-aligned prompts for LLM crawler generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
import json
import re
from typing import Any


class _HtmlEvidenceCompressor(HTMLParser):
    def __init__(self, *, allowed_attrs: set[str], max_text_chars: int):
        super().__init__(convert_charrefs=True)
        self.allowed_attrs = allowed_attrs
        self.max_text_chars = max(0, max_text_chars)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._text_budget_used = 0

    def _should_keep_attr(self, name: str) -> bool:
        lowered = name.lower()
        return lowered in self.allowed_attrs or lowered.startswith("data-") or lowered.startswith("aria-")

    def _format_attrs(self, attrs: list[tuple[str, str | None]]) -> str:
        kept: list[str] = []
        for name, value in attrs:
            if not self._should_keep_attr(name):
                continue
            if value is None:
                kept.append(name)
                continue
            kept.append(f'{name}="{escape(value, quote=True)}"')
        return f" {' '.join(kept)}" if kept else ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        self.parts.append(f"<{tag}{self._format_attrs(attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style"} or self._skip_depth:
            return
        self.parts.append(f"<{tag}{self._format_attrs(attrs)} />")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text or self._text_budget_used >= self.max_text_chars:
            return
        remaining = self.max_text_chars - self._text_budget_used
        clipped = text[:remaining].strip()
        if not clipped:
            return
        self._text_budget_used += len(clipped)
        self.parts.append(escape(clipped))

    def handle_comment(self, data: str) -> None:
        return

    def compressed_html(self) -> str:
        html = "".join(self.parts)
        return re.sub(r">\s+<", "><", html).strip()


@dataclass
class FieldSpec:
    """Specification for a single extraction field."""

    name: str
    selector: str
    extraction_type: str = "text"
    description: str = ""

    def to_dex(self) -> str:
        return f"{self.name}: {self.selector} > {self.extraction_type}"

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "selector": self.selector,
            "type": self.extraction_type,
        }
        if self.description:
            data["description"] = self.description
        return data


@dataclass
class ExtractionSpec:
    """Specification for data extraction and pagination."""

    item_selector: str = ""
    fields: list[FieldSpec] = field(default_factory=list)
    pagination_selector: str = ""
    pagination_strategy: str = "none"
    max_pages: int = 1
    stop_condition: str = "no_more_pages"


@dataclass
class WorkflowStep:
    """A single step in the crawler workflow."""

    action: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_prompt_line(self) -> str:
        if self.action == "visit":
            return f"Visit {self.params.get('url', '')}"
        if self.action == "wait":
            cond = self.params.get("condition", "dom_stable")
            timeout = self.params.get("timeout", 3000)
            return f"Wait for {cond} ({timeout}ms)"
        if self.action == "extract":
            sel = self.params.get("selector", "")
            fields = ", ".join(self.params.get("fields", []))
            return f"Extract from {sel}: {fields}"
        if self.action == "click":
            return f"Click {self.params.get('selector', '')}"
        if self.action == "scroll":
            direction = self.params.get("direction", "down")
            return f"Scroll {direction}"
        if self.action == "repeat":
            return f"Repeat until {self.params.get('until', 'stop_condition')}"
        return f"{self.action}: {self.params}"


@dataclass
class CrawlerPromptGenerator:
    """Generate plan-aligned prompts for Playwright crawler generation."""

    target_url: str = ""
    extraction: ExtractionSpec | None = None
    workflow: list[WorkflowStep] = field(default_factory=list)
    html_fragment: str = ""
    anti_detection: bool = True
    output_contract: dict[str, Any] = field(default_factory=dict)
    execution_limits: dict[str, Any] = field(default_factory=dict)
    conditions: list[dict[str, Any]] = field(default_factory=list)
    node_types: list[str] = field(default_factory=list)
    special_instructions: str = ""

    @staticmethod
    def _compress_html_evidence(html: str) -> str:
        compression_profiles = [
            (
                {
                    "id",
                    "class",
                    "href",
                    "src",
                    "name",
                    "role",
                    "rel",
                    "type",
                    "title",
                    "placeholder",
                    "value",
                    "alt",
                },
                2000,
            ),
            (
                {
                    "id",
                    "class",
                    "href",
                    "src",
                    "name",
                    "role",
                    "rel",
                    "type",
                },
                600,
            ),
            (
                {
                    "id",
                    "class",
                    "href",
                    "src",
                    "name",
                    "role",
                },
                0,
            ),
        ]
        for allowed_attrs, max_text_chars in compression_profiles:
            parser = _HtmlEvidenceCompressor(
                allowed_attrs=allowed_attrs,
                max_text_chars=max_text_chars,
            )
            parser.feed(html)
            parser.close()
            compressed = parser.compressed_html()
            if compressed and len(compressed) <= 12000:
                return compressed
        return compressed if compressed else html.strip()

    def generate(self) -> str:
        parts: list[str] = []

        parts.append("# Crawl Objective")
        parts.append("Build or revise a Playwright crawler that follows the deterministic execution contract exactly.")
        parts.append("")

        if self.target_url:
            parts.append("## Target")
            parts.append(f"- Entry URL: `{self.target_url}`")
            if self.node_types:
                parts.append(f"- Workflow nodes: {', '.join(self.node_types)}")
            parts.append("")

        parts.extend(self._build_selector_contract())
        parts.extend(self._build_workflow_shape())
        parts.extend(self._build_extraction_contract())
        parts.extend(self._build_output_contract())
        parts.extend(self._build_page_evidence())
        parts.extend(self._build_requirements())

        if self.special_instructions:
            parts.append("## Operator Notes")
            parts.append(self.special_instructions)
            parts.append("")

        return "\n".join(parts).strip()

    @staticmethod
    def _build_field_specs(fields: list[dict[str, Any]]) -> list[FieldSpec]:
        return [
            FieldSpec(
                name=f.get("name", f.get("field_name", f"field_{index + 1}")),
                selector=f.get("selector", f.get("css", "")),
                extraction_type=f.get("type", f.get("extraction_type", "text")),
                description=str(f.get("description", "") or ""),
            )
            for index, f in enumerate(fields)
        ]

    def _configure_prompt_context(
        self,
        *,
        url: str,
        item_selector: str,
        fields: list[dict[str, Any]],
        pagination_selector: str,
        pagination_strategy: str,
        max_pages: int,
        html_fragment: str,
        output_contract: dict[str, Any] | None,
        execution_limits: dict[str, Any] | None,
        conditions: list[dict[str, Any]] | None,
        node_types: list[str] | None,
    ) -> str:
        field_specs = self._build_field_specs(fields)
        self.target_url = url
        self.extraction = ExtractionSpec(
            item_selector=item_selector,
            fields=field_specs,
            pagination_selector=pagination_selector,
            pagination_strategy=pagination_strategy or "none",
            max_pages=max_pages,
        )
        self.html_fragment = html_fragment
        self.output_contract = output_contract or {}
        self.execution_limits = execution_limits or {}
        self.conditions = conditions or []
        self.node_types = node_types or []
        self.workflow = self._build_default_workflow(url, item_selector, field_specs)
        return self.generate()

    def generate_from_simple_config(
        self,
        url: str,
        item_selector: str,
        fields: list[dict[str, Any]],
        pagination_selector: str = "",
        pagination_strategy: str = "none",
        max_pages: int = 1,
        html_fragment: str = "",
        output_contract: dict[str, Any] | None = None,
        execution_limits: dict[str, Any] | None = None,
        conditions: list[dict[str, Any]] | None = None,
        node_types: list[str] | None = None,
    ) -> str:
        return self._configure_prompt_context(
            url=url,
            item_selector=item_selector,
            fields=fields,
            pagination_selector=pagination_selector,
            pagination_strategy=pagination_strategy,
            max_pages=max_pages,
            html_fragment=html_fragment,
            output_contract=output_contract,
            execution_limits=execution_limits,
            conditions=conditions,
            node_types=node_types,
        )

    def generate_from_plan(
        self,
        plan: dict[str, Any],
        html_fragment: str = "",
    ) -> str:
        pagination = plan.get("pagination", {})
        if not isinstance(pagination, dict):
            pagination = {}
        limits = plan.get("limits", {})
        if not isinstance(limits, dict):
            limits = {}
        output_contract = plan.get("output", {})
        if not isinstance(output_contract, dict):
            output_contract = {}
        conditions = plan.get("conditions", [])
        if not isinstance(conditions, list):
            conditions = []
        node_types = plan.get("node_types", [])
        if not isinstance(node_types, list):
            node_types = []
        fields = plan.get("field_specs", [])
        if not isinstance(fields, list):
            fields = []

        return self._configure_prompt_context(
            url=str(plan.get("entry_url", "") or ""),
            item_selector=str(plan.get("item_selector", "") or ""),
            fields=fields,
            pagination_selector=str(pagination.get("selector", "") or ""),
            pagination_strategy=str(pagination.get("strategy", "none") or "none"),
            max_pages=int(pagination.get("max_pages") or limits.get("max_pages") or 1),
            html_fragment=html_fragment,
            output_contract=output_contract,
            execution_limits=limits,
            conditions=conditions,
            node_types=node_types,
        )

    def _build_default_workflow(self, url: str, item_selector: str, fields: list[FieldSpec]) -> list[WorkflowStep]:
        workflow = [
            WorkflowStep(action="visit", params={"url": url}),
            WorkflowStep(action="wait", params={"condition": "dom_stable", "timeout": 3000}),
            WorkflowStep(action="extract", params={"selector": item_selector, "fields": [field.name for field in fields]}),
        ]
        if self.extraction and self.extraction.pagination_selector and self.extraction.pagination_strategy in {"click_next", "load_more"}:
            workflow.append(WorkflowStep(action="click", params={"selector": self.extraction.pagination_selector}))
            workflow.append(WorkflowStep(action="repeat", params={"until": self.extraction.stop_condition}))
        elif self.extraction and self.extraction.pagination_strategy == "infinite_scroll":
            workflow.append(WorkflowStep(action="scroll", params={"direction": "down"}))
            workflow.append(WorkflowStep(action="repeat", params={"until": "max_pages"}))
        return workflow

    def _build_selector_contract(self) -> list[str]:
        return [
            "## Selector Compatibility Contract",
            "- Treat every selector present in the deterministic execution plan as user-validated input. Preserve it whenever possible instead of replacing it with a new selector style.",
            "- Validated selectors may be CSS selectors or XPath selectors. Keep the original selector string unless it is clearly invalid, semantically wrong for the target field, or incompatible with Playwright execution.",
            "- If a validated selector is XPath, keep using XPath in a Playwright-compatible form. Do not convert a validated XPath selector to CSS unless the XPath is clearly wrong or unsupported.",
            "- Do not invent Playwright-only locator syntax such as `get_by_role(...)`, `get_by_text(...)`, `text=...`, `:has-text(...)`, `nth=`, or `>>`.",
            "- Prefer stable semantic classes, IDs, and data-attributes over brittle position-based selectors.",
            "",
        ]

    def _build_workflow_shape(self) -> list[str]:
        if not self.workflow and not self.execution_limits and not self.conditions:
            return []

        parts = ["## Workflow Shape"]
        if self.workflow:
            for index, step in enumerate(self.workflow, 1):
                parts.append(f"{index}. {step.to_prompt_line()}")
        if self.execution_limits:
            parts.append("")
            parts.append("Execution limits:")
            parts.append("```json")
            parts.append(self._format_json(self.execution_limits))
            parts.append("```")
        if self.conditions:
            parts.append("")
            parts.append("Conditional branches:")
            parts.append("```json")
            parts.append(self._format_json(self.conditions))
            parts.append("```")
        parts.append("")
        return parts

    def _build_extraction_contract(self) -> list[str]:
        if not self.extraction:
            return []

        schema = {
            "item_selector": self.extraction.item_selector,
            "fields": [field.to_dict() for field in self.extraction.fields],
            "pagination": {
                "strategy": self.extraction.pagination_strategy,
                "selector": self.extraction.pagination_selector,
                "max_pages": self.extraction.max_pages,
                "stop_condition": self.extraction.stop_condition,
            },
        }

        parts = [
            "## Extraction Contract",
            "```json",
            self._format_json(schema),
            "```",
        ]

        if self.extraction.fields:
            parts.append("")
            parts.append("Field notes:")
            for field in self.extraction.fields:
                parts.append(f"- `{field.name}` from `{field.selector}` as `{field.extraction_type}`")

        if not self.extraction.pagination_selector or self.extraction.pagination_strategy in {"none", ""}:
            parts.append("")
            parts.append("- Do not invent pagination logic unless the execution plan explicitly requires it.")

        parts.append("")
        return parts

    def _build_output_contract(self) -> list[str]:
        if not self.output_contract:
            return []

        mode = str(self.output_contract.get("mode", "memory") or "memory").strip().lower()
        parts = [
            "## Output Contract",
            "```json",
            self._format_json(self.output_contract),
            "```",
        ]

        if mode == "sqlite":
            parts.extend([
                "- Persist records with local `sqlite3` and keep schema creation deterministic.",
                "- Store one flat SQLite column per configured field; do not collapse full records into a JSON blob column.",
                "- Preserve metadata columns for `_identity_key`, `_run_id`, `_source_url`, `_emitted_at`, and `_record_hash`.",
                "- Use `_identity_key` as the deterministic conflict target for upsert behavior.",
                "- Persist each extracted page batch before attempting pagination so interruptions do not lose prior pages.",
            ])
        elif mode == "json_file":
            parts.append("- Persist records to the configured local JSON file and keep the output document valid and deterministic.")
        else:
            parts.append("- Keep records in memory unless the deterministic execution plan explicitly requests file or SQLite persistence.")

        parts.append("")
        return parts

    def _build_page_evidence(self) -> list[str]:
        if not self.html_fragment:
            return []

        html_sample = self._compress_html_evidence(self.html_fragment)
        parts = [
            "## Page Evidence (Compressed HTML Sample)",
            "```html",
            html_sample,
        ]
        parts.extend(["```", ""])
        return parts

    def _build_requirements(self) -> list[str]:
        parts = [
            "## Implementation Requirements",
            "- Use Playwright for Python and keep the script runnable end-to-end.",
            "- Preserve the deterministic execution plan, field schema, and output contract.",
            "- Follow the selector compatibility contract above and preserve validated selectors unless they are clearly invalid or incompatible with Playwright.",
            "- If a selector is evaluated from `page` or `frame`, `page.locator(...)` is acceptable; if you already have an `ElementHandle`, use `query_selector(...)` / `query_selector_all(...)` on that handle instead of calling `.locator(...)` on it.",
            "- Never emit `ElementHandle.locator(...)` patterns such as `item.locator(...)`, `element.locator(...)`, or `first.locator(...)`; those are not valid in Playwright Python sync API.",
            "- Use robust waits and content verification around pagination or dynamic updates.",
            "- Keep extraction logic aligned with the declared field selectors and normalization rules.",
            "- Prefer minimal deterministic implementation changes over speculative architecture rewrites.",
        ]
        if self.anti_detection:
            parts.extend([
                "- Use realistic waits and browser settings; avoid noisy anti-detection theatrics that reduce determinism.",
                "- Prefer explicit synchronization over random sleeps when possible.",
            ])
        parts.extend([
            "",
            "## Acceptance Gate",
            "- Accept only if control flow stays aligned with execution plan.",
            "- Accept only if output persistence mode stays aligned with output contract.",
            "- Accept only if selectors remain compatible and as-validated whenever possible.",
            "- If any acceptance condition fails, revise before returning final script.",
        ])
        parts.append("")
        return parts

    @staticmethod
    def _format_json(data: Any, indent: int = 2) -> str:
        return json.dumps(data, ensure_ascii=False, indent=indent)
