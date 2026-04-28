"""Crawler prompt generation for crawler-workflow.

Generates structured, execution-plan-aligned prompts for LLM crawler generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass
class FieldSpec:
    """Specification for a single extraction field."""

    name: str
    selector: str
    extraction_type: str = "text"
    description: str = ""
    clean_data_type: str = ""
    normalized_sample: str = ""
    sample_value: str = ""

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
        if self.clean_data_type:
            data["clean_data_type"] = self.clean_data_type
        if self.normalized_sample:
            data["normalized_sample"] = self.normalized_sample
        if self.sample_value:
            data["sample_value"] = self.sample_value
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
        field_specs = [
            FieldSpec(
                name=f.get("name", f.get("field_name", f"field_{index + 1}")),
                selector=f.get("selector", f.get("css", "")),
                extraction_type=f.get("type", f.get("extraction_type", "text")),
                description=str(f.get("description", "") or ""),
                clean_data_type=str(f.get("clean_data_type", "") or ""),
                normalized_sample=str(f.get("normalized_sample", "") or ""),
                sample_value=str(f.get("sample_value", "") or ""),
            )
            for index, f in enumerate(fields)
        ]

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
            "- Every selector must remain a standard CSS selector that works directly with Playwright `page.query_selector(...)`, `page.query_selector_all(...)`, and `locator(...)`.",
            "- Selectors must also be compatible with DOM APIs such as `document.querySelector(...)` and `document.querySelectorAll(...)`.",
            "- Do not invent Playwright-only locator syntax such as `get_by_role(...)`, `get_by_text(...)`, `text=...`, `:has-text(...)`, `nth=`, `>>`, or XPath.",
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
                line = f"- `{field.name}` from `{field.selector}` as `{field.extraction_type}`"
                if field.clean_data_type:
                    line += f"; normalize as `{field.clean_data_type}`"
                if field.normalized_sample:
                    line += f"; expected normalized sample: `{field.normalized_sample}`"
                elif field.sample_value:
                    line += f"; raw sample: `{field.sample_value}`"
                parts.append(line)

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
            parts.append("- Persist records with local `sqlite3`, keep schema creation deterministic, and preserve dedupe/upsert behavior.")
        elif mode == "json_file":
            parts.append("- Persist records to the configured local JSON file and keep the output document valid and deterministic.")
        else:
            parts.append("- Keep records in memory unless the deterministic execution plan explicitly requests file or SQLite persistence.")

        parts.append("")
        return parts

    def _build_page_evidence(self) -> list[str]:
        if not self.html_fragment:
            return []

        html_sample = self.html_fragment[:12000]
        parts = [
            "## Page Evidence (HTML Sample)",
            "```html",
            html_sample,
        ]
        if len(self.html_fragment) > len(html_sample):
            parts.append("<!-- HTML truncated -->")
        parts.extend(["```", ""])
        return parts

    def _build_requirements(self) -> list[str]:
        parts = [
            "## Implementation Requirements",
            "- Use Playwright for Python and keep the script runnable end-to-end.",
            "- Preserve the deterministic execution plan, field schema, and output contract.",
            "- Do not replace validated selectors with alternative locator styles unless the provided selector is clearly invalid.",
            "- Use robust waits and content verification around pagination or dynamic updates.",
            "- Keep extraction logic aligned with the declared field selectors and normalization rules.",
        ]
        if self.anti_detection:
            parts.extend([
                "- Use realistic waits and browser settings; avoid noisy anti-detection theatrics that reduce determinism.",
                "- Prefer explicit synchronization over random sleeps when possible.",
            ])
        parts.append("")
        return parts

    @staticmethod
    def _format_json(data: Any, indent: int = 2) -> str:
        return json.dumps(data, ensure_ascii=False, indent=indent)
