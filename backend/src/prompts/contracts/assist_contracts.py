"""Assist task response contracts."""

FIELD_INFERENCE_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "item_selector": "string",
  "fields": [
    {"name": "string", "selector": "string", "type": "string", "confidence": 0.0}
  ],
  "confidence": 0.0,
  "reason": "string"
}

Rules:
- "fields" must always be an array, even when empty.
- Each field entry must remain a JSON object.
- "confidence" values must be numbers between 0 and 1.
"""

SELECTOR_OPTIMIZATION_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "optimized_selector": "string",
  "confidence": 0.0,
  "reason": "string"
}

Rules:
- "optimized_selector" must be a selector string (standard CSS or XPath), or an empty string if unavailable.
- "confidence" must be a number between 0 and 1.
"""

PAGINATION_ANALYSIS_RESPONSE_CONTRACT = """Return one JSON object with this shape:
{
  "pagination_strategy": "click_next|infinite_scroll|load_more|none",
  "next_button_selector": "string",
  "page_number_selectors": ["string"],
  "confidence": 0.0,
  "reason": "string"
}

Rules:
- "page_number_selectors" must always be an array.
- Use empty strings or an empty array when data is unavailable.
- "confidence" must be a number between 0 and 1.
"""

