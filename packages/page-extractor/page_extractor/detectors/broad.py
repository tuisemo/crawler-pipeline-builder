"""基于结构评分的正文区域检测器 (Structural scoring detector)."""

from __future__ import annotations

import re
from lxml import html, etree

from page_extractor.core.types import DetectorResult, DetectorStrategy
from page_extractor.detectors.base import BaseDetector

# 候选正文区域的最小原始文本长度
MIN_TEXT = 150


class BroadDetector(BaseDetector):
    """通过结构化评分算法自动检测网页主内容区域。"""

    def is_available(self) -> bool:
        return True  # 依赖项 lxml 在项目层面是必需的

    def detect(self, html_content: str, url: str | None = None) -> DetectorResult:
        """执行检测，返回最可能的正文区域 XPath。"""
        fallback = DetectorResult(
            content_area="/html/body", confidence=0.0, text_length=0,
            strategy=DetectorStrategy.BROAD,
        )
        if not html_content:
            return fallback
            
        try:
            tree = html.fromstring(html_content)
            doc = etree.ElementTree(tree)
        except Exception:
            return fallback

        candidates: list[tuple[object, float, int]] = []
        # 遍历常见的容器标签作为候选对象
        for element in tree.iter("div", "section", "article", "main"):
            text = self._get_clean_text(element)
            text_len = len(text)
            if text_len < MIN_TEXT:
                continue
                
            score = self._calculate_score(element, text_len)
            candidates.append((element, score, text_len))

        if not candidates:
            return fallback

        # 优先选择评分大于 0 且文本最长的区域
        scored = [(e, s, t) for e, s, t in candidates if s > 0]
        if not scored:
            scored = candidates

        scored.sort(key=lambda item: item[2], reverse=True)
        best_el, best_score, best_len = scored[0]

        xpath = doc.getpath(best_el)
        # 归一化置信度计算
        confidence = min(0.9, best_score / 80 + 0.2) if best_score > 0 else 0.3

        return DetectorResult(
            content_area=xpath,
            confidence=round(confidence, 2),
            text_length=best_len,
            strategy=DetectorStrategy.BROAD,
            element_info={
                "tag": best_el.tag, 
                "class": best_el.get("class"), 
                "id": best_el.get("id")
            },
        )

    # ------------------------------------------------------------------

    def _get_clean_text(self, element) -> str:
        """获取元素的纯文本，排除脚本、样式、导航等噪音。"""
        # 提取所有不属于噪音标签的文本节点
        bad_tags = {"script", "style", "nav", "footer", "aside", "form"}
        
        # 使用 XPath 高效提取非噪音文本
        parts = element.xpath(
            './/text()[not(ancestor::script or ancestor::style or '
            'ancestor::nav or ancestor::footer or ancestor::aside or ancestor::form)]'
        )
        joined = "".join(parts)
        return re.sub(r"\s+", " ", joined).strip()

    def _calculate_score(self, element: Any, text_len: int) -> float:
        """核心评分算法：基于文本/标点密度、语义特征与链接惩罚。"""
        # 0. 基础文本得分
        text = (element.text_content() or "").strip()
        if not text or text_len < 20:
            return 0.0

        # 1. 密度得分：标点符号是正文的重要特征
        punc_count = len(re.findall(r'[，。！？、,;.!?]', text))
        # 基础分 = 文本长度 * 0.5 + 标点奖励
        score = (text_len * 0.5) + (punc_count * 10.0)

        # 2. 内部结构特征
        # 段落 (p) 是最强的正文信号
        p_count = len(element.xpath(".//p"))
        score += p_count * 5.0
        
        # 标题 (h1-h6) 是次强信号
        h_count = len(element.xpath(".//h1|.//h2|.//h3|.//h4|.//h5|.//h6"))
        score += h_count * 3.0

        # 3. 语义加权 (根据标签和 Class/ID)
        tag = element.tag.lower() if isinstance(element.tag, str) else ""
        class_id = (element.get("class", "") + " " + element.get("id", "")).lower()
        
        semantic_weight = 1.0
        # 核心区域正面关键词
        if any(k in class_id for k in ["content", "article", "post", "main", "body", "entry", "detail"]):
            semantic_weight += 0.4
        # 噪音区域负面关键词
        if any(k in class_id for k in ["sidebar", "nav", "footer", "header", "comment", "related", "ad-", "banner", "menu"]):
            semantic_weight -= 0.6
            
        # 语义标签权重
        if tag in ["article", "main"]:
            semantic_weight += 0.6
        elif tag in ["nav", "header", "footer", "aside"]:
            semantic_weight -= 0.7
        elif tag in ["section"]:
            semantic_weight += 0.2

        # 4. 链接密度惩罚 (核心优化：过滤导航与列表)
        link_elements = element.xpath(".//a")
        link_text_len = sum(len((le.text_content() or "").strip()) for le in link_elements)
        
        if text_len > 0:
            link_density = link_text_len / text_len
            # 链接占比超过 40% 开始重罚
            if link_density > 0.4:
                semantic_weight *= (1.0 - link_density)
            # 链接占比超过 66% 通常不是正文
            if link_density > 0.66:
                return 0.0

        # 5. 视觉/属性过滤
        style = element.get("style", "").lower()
        if "display: none" in style or "visibility: hidden" in style:
            return 0.0

        final_score = score * semantic_weight
        return max(0.0, final_score)
