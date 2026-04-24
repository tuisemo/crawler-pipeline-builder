"""Crawler prompt generation for sea-data.

Generates structured prompts for LLM to create Playwright crawler scripts.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldSpec:
    """Specification for a single extraction field."""
    name: str
    selector: str
    extraction_type: str = "text"  # "text", "attr:href", "attr:src", etc.
    description: str = ""

    def to_dex(self) -> str:
        """Convert to Dex syntax."""
        return f"{self.name}: {self.selector} > {self.extraction_type}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "selector": self.selector,
            "type": self.extraction_type,
            "description": self.description
        }


@dataclass
class ExtractionSpec:
    """Specification for data extraction."""
    item_selector: str = ""
    fields: list[FieldSpec] = field(default_factory=list)
    pagination_selector: str = ""
    pagination_strategy: str = "click_next"  # "click_next", "infinite_scroll", "load_more", "none"
    max_pages: int = 50
    stop_condition: str = "no_more_pages"  # "no_more_pages", "max_pages", "custom"


@dataclass
class WorkflowStep:
    """A single step in the crawler workflow."""
    action: str  # "visit", "wait", "extract", "click", "scroll", "repeat"
    params: dict[str, Any] = field(default_factory=dict)

    def to_prompt_line(self) -> str:
        """Convert to readable prompt line."""
        if self.action == "visit":
            return f"{self.params.get('url', '')}"
        elif self.action == "wait":
            cond = self.params.get('condition', 'dom_stable')
            timeout = self.params.get('timeout', 3000)
            return f"Wait for {cond} ({timeout}ms)"
        elif self.action == "extract":
            sel = self.params.get('selector', '')
            fields = ', '.join(self.params.get('fields', []))
            return f"Extract from {sel}: {fields}"
        elif self.action == "click":
            return f"Click: {self.params.get('selector', '')}"
        elif self.action == "scroll":
            dir = self.params.get('direction', 'down')
            return f"Scroll {dir}"
        elif self.action == "repeat":
            return f"Repeat until: {self.params.get('until', 'no_more_pages')}"
        else:
            return f"{self.action}: {self.params}"


@dataclass
class CrawlerPromptGenerator:
    """Generates prompts for LLM crawler generation."""

    target_url: str = ""
    extraction: ExtractionSpec | None = None
    workflow: list[WorkflowStep] = field(default_factory=list)
    html_fragment: str = ""
    anti_detection: bool = True
    output_filename: str = "crawler_output.json"
    special_instructions: str = ""

    def generate(self) -> str:
        """Generate the complete prompt."""
        parts = []

        parts.append("# Task: Build Playwright Crawler Script")
        parts.append("")
        parts.append("## Target URL")
        parts.append(self.target_url)
        parts.append("")

        if self.workflow:
            parts.append("## Workflow Steps")
            for i, step in enumerate(self.workflow, 1):
                parts.append(f"{i}. {step.to_prompt_line()}")
            parts.append("")

        if self.extraction:
            parts.append("## Extraction Schema")
            schema = {
                "item_selector": self.extraction.item_selector,
                "fields": [f.to_dict() for f in self.extraction.fields],
                "pagination": {
                    "strategy": self.extraction.pagination_strategy,
                    "selector": self.extraction.pagination_selector,
                    "max_pages": self.extraction.max_pages,
                    "stop_condition": self.extraction.stop_condition
                }
            }
            parts.append("```json")
            parts.append(self._format_json(schema))
            parts.append("```")
            parts.append("")

        if self.html_fragment:
            parts.append("## Page HTML Structure (Sample)")
            parts.append("```html")
            parts.append(self.html_fragment[:10000])  # Limit to 10KB for prompt
            if len(self.html_fragment) > 10000:
                parts.append("<!-- HTML truncated -->")
            parts.append("```")
            parts.append("")

        if self.extraction and self.extraction.fields:
            parts.append("## Data Fields (Dex Syntax)")
            for f in self.extraction.fields:
                parts.append(f"- {f.to_dex()}")
            parts.append("")

        parts.append("## Requirements")
        parts.append("- Use Playwright (Python)")
        parts.append("- Output JSON to `" + self.output_filename + "`")
        parts.append("- Handle pagination automatically")
        parts.append("- Include proper error handling and retries")

        if self.anti_detection:
            parts.append("- Rotate User-Agent")
            parts.append("- Random delay between requests (1-3s)")
            parts.append("- Handle dynamic content with appropriate waits")

        if self.special_instructions:
            parts.append("")
            parts.append("## Special Instructions")
            parts.append(self.special_instructions)

        return '\n'.join(parts)

    def generate_from_simple_config(
        self,
        url: str,
        item_selector: str,
        fields: list[dict[str, str]],
        pagination_selector: str = "",
        pagination_strategy: str = "click_next",
        max_pages: int = 50,
        html_fragment: str = ""
    ) -> str:
        """Generate prompt from simple configuration.

        Args:
            url: Target URL
            item_selector: CSS selector for item containers
            fields: List of {name, selector, type} dicts
            pagination_selector: CSS selector for next page button
            pagination_strategy: "click_next", "infinite_scroll", "load_more"
            max_pages: Maximum pages to crawl
            html_fragment: HTML snippet for context

        Returns:
            Generated prompt string
        """
        field_specs = [
            FieldSpec(
                name=f.get('name', f.get('field_name', 'field_' + str(i))),
                selector=f.get('selector', ''),
                extraction_type=f.get('type', f.get('extraction_type', 'text'))
            )
            for i, f in enumerate(fields)
        ]

        self.target_url = url
        self.extraction = ExtractionSpec(
            item_selector=item_selector,
            fields=field_specs,
            pagination_selector=pagination_selector,
            pagination_strategy=pagination_strategy,
            max_pages=max_pages
        )
        self.html_fragment = html_fragment
        self.workflow = [
            WorkflowStep(action="visit", params={"url": url}),
            WorkflowStep(action="wait", params={"condition": "dom_stable", "timeout": 3000}),
            WorkflowStep(action="extract", params={"selector": item_selector, "fields": [f.name for f in field_specs]}),
        ]

        if pagination_strategy == "click_next" and pagination_selector:
            self.workflow.append(
                WorkflowStep(action="click", params={"selector": pagination_selector})
            )
            self.workflow.append(
                WorkflowStep(action="repeat", params={"until": "no_more_pages", "max": max_pages})
            )
        elif pagination_strategy == "infinite_scroll":
            self.workflow.append(
                WorkflowStep(action="scroll", params={"direction": "down", "infinite": True})
            )
            self.workflow.append(
                WorkflowStep(action="repeat", params={"until": "max_scrolls", "max": 100})
            )

        return self.generate()

    @staticmethod
    def _format_json(data: Any, indent: int = 2) -> str:
        """Simple JSON formatter."""
        import json
        return json.dumps(data, ensure_ascii=False, indent=2)
