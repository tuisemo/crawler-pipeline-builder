from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class VisitRequest(BaseModel):
    url: str
    session_id: str = ""

class AutoDetectRequest(BaseModel):
    url: str
    session_id: str = ""

class TestSelectorRequest(BaseModel):
    url: str = ""
    selector: str
    extraction_type: str = "text"
    session_id: str = ""

class TestFieldsRequest(BaseModel):
    item_selector: str = ""
    fields: list[dict]
    session_id: str = ""

class PageHtmlRequest(BaseModel):
    url: str
    item_selector: str = ""
    max_items: int = 3
    session_id: str = ""

class GenerateCrawlerRequest(BaseModel):
    url: str
    item_selector: str
    fields: list[dict]
    pagination_selector: str = ""
    pagination_strategy: str = "click_next"
    max_pages: int = 50
    html_fragment: str = ""
    llm_provider: str = "openai"
    llm_model: str = ""

class SessionCloseRequest(BaseModel):
    session_id: str
