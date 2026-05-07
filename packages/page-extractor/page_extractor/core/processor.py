"""HTML 预处理与 Markdown 后处理工具 (Content processors)."""

from __future__ import annotations

import re
from lxml import html, etree


class ContentProcessor:
    """负责 HTML 的清理、作用域限定以及 Markdown 的清洗归一化。"""

    @staticmethod
    def preprocess_html(html_content: str) -> str:
        """在提取前剥离干扰性噪音（如 iframe 和隐藏元素）。"""
        try:
            tree = html.fromstring(html_content)
        except Exception:
            return html_content

        removed = 0
        for element in list(tree.iter()):
            # 忽略脚本和样式（提取器通常会处理，但这里显式跳过）
            if element.tag in ("script", "style", "noscript"):
                continue
                
            # 移除 iframe
            if element.tag == "iframe":
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    removed += 1
                continue
            
            # 移除显式隐藏的元素
            style = (element.get("style") or "").lower().replace(" ", "")
            if "display:none" in style or "visibility:hidden" in style:
                parent = element.getparent()
                if parent is not None:
                    parent.remove(element)
                    removed += 1
                continue

        return html.tostring(tree, encoding="unicode") if removed else html_content

    @staticmethod
    def postprocess_markdown(markdown: str) -> str:
        """Markdown 格式归一化与清洗。"""
        if not markdown:
            return markdown

        lines = markdown.split("\n")

        # 1. 标题后缀清理（如：- 新闻中心 - 某某网站）
        if lines and lines[0].startswith("# "):
            title = lines[0]
            title = re.sub(r"\s+[\-\u2013]\s*\S+(\s+[\-\u2013]\s*\S+)*$", "", title)
            title = re.sub(r"_[\u4e00-\u9fff][\u4e00-\u9fff\w]{2,}$", "", title)
            title = re.sub(r"\s*\|\s*[\u4e00-\u9fff]{2,}$", "", title)
            lines[0] = title

        text = "\n".join(lines)

        # 2. 移除装饰性图片 (gif, ico)
        text = re.sub(r"!\[([^\]]*)\]\([^)]*(?:\.gif|\.ico)[^)]*\)", "", text)

        # 3. 规范化加粗冒号间距
        text = re.sub(r"\*\*(\S+)\s*:\s*\*\s*\*\s*", r"**\1:** ", text)

        # 4. 合并多余的分隔符和换行
        text = re.sub(r"(\n---\n){2,}", "\n---\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # 5. 移除尾部重复的标题块
        parts = text.split("\n---\n")
        if len(parts) >= 2:
            last = parts[-1].strip()
            if len(last) < 300:
                main_title = ""
                for ln in parts[0].split("\n"):
                    if ln.startswith("# "):
                        main_title = re.sub(r"^#+\s*", "", ln).strip()
                        break
                check = last.split("\n")[0].strip().lstrip("# ")
                if main_title and check:
                    a = re.sub(r"[\s_\-|,.;:!?]+", "", main_title).lower()
                    b = re.sub(r"[\s_\-|,.;:!?]+", "", check).lower()
                    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
                        text = parts[0].strip()

        return text.strip()

    @staticmethod
    def scope_html(html_content: str, xpath: str) -> str:
        """根据 XPath 将 HTML 范围限定在特定元素内。"""
        try:
            tree = html.fromstring(html_content)
            elements = tree.xpath(xpath)
            if not elements:
                return html_content
            return html.tostring(elements[0], encoding="unicode")
        except Exception:
            return html_content

    @staticmethod
    def format_html(html_content: str) -> str:
        """HTML 格式化（Pretty Print）。"""
        try:
            tree = html.fromstring(html_content)
            return etree.tostring(tree, encoding="unicode", pretty_print=True)
        except Exception:
            return html_content
