"""PDF snapshot generation for detail extraction."""

from __future__ import annotations

import contextlib

from page_extractor.utils.logging import get_logger


def snapshot_element(page, selector: str, output_path: str, pdf_format: str = "A4", pdf_margin: str = "10mm") -> bool:
    logger = get_logger()
    try:
        count = page.evaluate("(sel) => document.querySelectorAll(sel).length", selector)
        if count == 0:
            return snapshot_full_page(page, output_path, pdf_format, pdf_margin)
    except Exception:
        return snapshot_full_page(page, output_path, pdf_format, pdf_margin)
    try:
        page.evaluate(
            """
            (selector) => {
                const target = document.querySelector(selector);
                if (!target) return;
                const ancestors = new Set();
                let node = target;
                while (node) {
                    ancestors.add(node);
                    node = node.parentElement;
                }
                ancestors.forEach((ancestor) => {
                    if (ancestor.parentElement) {
                        Array.from(ancestor.parentElement.children).forEach((sibling) => {
                            if (!ancestors.has(sibling) && sibling !== target) {
                                sibling.setAttribute('data-detail-hidden', sibling.style.display || '');
                                sibling.style.display = 'none';
                            }
                        });
                    }
                });
            }
            """,
            selector,
        )
        page.pdf(
            path=output_path,
            format=pdf_format,
            print_background=True,
            margin={"top": pdf_margin, "bottom": pdf_margin, "left": pdf_margin, "right": pdf_margin},
        )
        page.evaluate(
            """
            () => {
                document.querySelectorAll('[data-detail-hidden]').forEach((el) => {
                    const original = el.getAttribute('data-detail-hidden');
                    el.style.display = original || '';
                    el.removeAttribute('data-detail-hidden');
                });
            }
            """
        )
        logger.info("[Snapshot] Cropped PDF generated: %s", output_path)
        return True
    except Exception as exc:
        logger.warning("[Snapshot] Cropped PDF generation failed: %s", exc)
        with contextlib.suppress(Exception):
            page.evaluate(
                """
                () => {
                    document.querySelectorAll('[data-detail-hidden]').forEach((el) => {
                        const original = el.getAttribute('data-detail-hidden');
                        el.style.display = original || '';
                        el.removeAttribute('data-detail-hidden');
                    });
                }
                """
            )
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

