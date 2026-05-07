"""PDF snapshot generation for detail extraction."""

from __future__ import annotations

import contextlib

from page_extractor.utils.logging import get_logger


_HIDE_JS = """
const ancestors = new Set();
let node = __TARGET__;
while (node) { ancestors.add(node); node = node.parentElement; }
ancestors.forEach((ancestor) => {
    if (ancestor.parentElement) {
        Array.from(ancestor.parentElement.children).forEach((sibling) => {
            if (!ancestors.has(sibling) && sibling !== __TARGET__) {
                sibling.setAttribute('data-detail-hidden', sibling.style.display || '');
                sibling.style.display = 'none';
            }
        });
    }
});
"""

_RESTORE_JS = """
document.querySelectorAll('[data-detail-hidden]').forEach((el) => {
    const original = el.getAttribute('data-detail-hidden');
    el.style.display = original || '';
    el.removeAttribute('data-detail-hidden');
});
"""


def snapshot_element(page, selector: str, output_path: str, pdf_format: str = "A4", pdf_margin: str = "10mm") -> bool:
    """Generate a PDF cropped to *selector*, which may be CSS or XPath."""
    logger = get_logger()
    is_xpath = selector.startswith("/") or selector.startswith("(")
    try:
        if is_xpath:
            count = page.evaluate(
                "(xp) => document.evaluate(xp, document, null, "
                "XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null).snapshotLength",
                selector,
            )
        else:
            count = page.evaluate("(sel) => document.querySelectorAll(sel).length", selector)
        if count == 0:
            return snapshot_full_page(page, output_path, pdf_format, pdf_margin)
    except Exception:
        return snapshot_full_page(page, output_path, pdf_format, pdf_margin)
    try:
        if is_xpath:
            find_js = (
                "const __TARGET__ = document.evaluate(selector, document, null, "
                "XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;"
            )
        else:
            find_js = "const __TARGET__ = document.querySelector(selector);"
        hide_js = _HIDE_JS.replace("__TARGET__", "__TARGET__")
        page.evaluate(
            f"(selector) => {{ {find_js} if (!__TARGET__) return; {hide_js} }}",
            selector,
        )
        page.pdf(
            path=output_path,
            format=pdf_format,
            print_background=True,
            margin={"top": pdf_margin, "bottom": pdf_margin, "left": pdf_margin, "right": pdf_margin},
        )
        page.evaluate(f"() => {{ {_RESTORE_JS} }}")
        logger.info("[Snapshot] Cropped PDF generated: %s", output_path)
        return True
    except Exception as exc:
        logger.warning("[Snapshot] Cropped PDF generation failed: %s", exc)
        with contextlib.suppress(Exception):
            page.evaluate(f"() => {{ {_RESTORE_JS} }}")
        return snapshot_full_page(page, output_path, pdf_format, pdf_margin)


def snapshot_full_page(page, output_path: str, pdf_format: str = "A4", pdf_margin: str = "10mm") -> bool:
    logger = get_logger()
    try:
        page.pdf(
            path=output_path,
            format=pdf_format,
            print_background=True,
            margin={"top": pdf_margin, "bottom": pdf_margin, "left": pdf_margin, "right": pdf_margin},
        )
        logger.info("[Snapshot] Full page PDF generated: %s", output_path)
        return True
    except Exception as exc:
        logger.error("[Snapshot] PDF generation failed: %s", exc)
        return False
