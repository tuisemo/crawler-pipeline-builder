export function bridge_auto_detect() {
const IGNORE_TAGS = new Set([
        'SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'PATH', 'META', 'HEAD', 'TITLE',
        'LINK', 'IFRAME', 'CANVAS'
    ]);
    const IGNORE_HINTS = [
        'header', 'footer', 'nav', 'menu', 'sidebar', 'toolbar', 'banner',
        'cookie', 'popup', 'modal', 'advert', 'ad-', 'crumb', 'search',
        'login', 'share', 'navbar', 'widget'
    ];
    const LIST_CONTAINER_SELECTORS = ['main', 'article', 'section', 'div', 'ul', 'ol', 'table', 'tbody', 'dl'];
    const PAGINATION_CONTAINER_SELECTORS = ['nav', 'div', 'section', 'ul', 'ol', 'table', 'tbody', 'tr', 'td', 'p', 'span', 'li'];
    const MARKER_CLEAR_AFTER_MS = 2200;
    const CLEANUP_TIMER_KEY = '__seaAutoCleanupTimer';
    const PAGE_TEXT_RE = /^(?:\\d{1,3}|[<>]|>>|<<|›|‹|»|«|→|下一页|下页|上一页|首页|尾页|末页|next|next page|prev|previous|more|load more|加载更多)$/i;
    const NEXT_CONTROL_RE = /(?:下一页|下页|next|next page|more|load more|加载更多|[›»→>])$/i;
    const DATE_RE = /(20\\d{2}[-/.年]\\d{1,2}[-/.月]\\d{1,2}日?)|(\\d{4}[-/.]\\d{1,2}[-/.]\\d{1,2})/;

    function cleanup() {
        document.querySelectorAll('[data-sea-auto]').forEach(el => {
            el.style.outline = '';
            el.style.backgroundColor = '';
            el.removeAttribute('data-sea-auto');
        });
        const marker = document.getElementById('sea-auto-style');
        if (marker) marker.remove();
    }
    cleanup();

    const style = document.createElement('style');
    style.id = 'sea-auto-style';
    style.textContent = `
        [data-sea-auto="item"] { outline: 2px dashed #45b7d1 !important; }
        [data-sea-auto="pagination"] { outline: 2px dashed #f7dc6f !important; }
        [data-sea-auto="field"] { outline: 2px dotted #96ceb4 !important; }
    `;
    document.head.appendChild(style);

    function isVisible(el) {
        if (!el || !(el instanceof HTMLElement)) return false;
        const s = window.getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0' && r.width >= 80 && r.height >= 10;
    }

    function textContent(el) {
        return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
    }

    function stableClassTokens(el) {
        return Array.from(el.classList || [])
            .filter(t => t && !/\\d/.test(t) && t.length > 2 && t.length < 30)
            .slice(0, 2);
    }

    function intersectStableClassTokens(elements) {
        if (!elements.length) return [];
        let shared = stableClassTokens(elements[0]);
        for (const el of elements.slice(1)) {
            const tokenSet = new Set(stableClassTokens(el));
            shared = shared.filter(token => tokenSet.has(token));
            if (shared.length === 0) break;
        }
        return shared;
    }

    function shouldIgnore(el) {
        if (!el || !(el instanceof HTMLElement) || IGNORE_TAGS.has(el.tagName)) return true;
        const classId = (el.id || '') + ' ' + (el.className || '');
        return IGNORE_HINTS.some(h => classId.toLowerCase().includes(h));
    }

    function itemSignature(el) {
        const childTags = Array.from(el.children).slice(0, 6).map(c => c.tagName.toLowerCase()).join(',');
        const cls = stableClassTokens(el).join('.');
        const anchors = el.querySelectorAll('a[href]').length > 0 ? 'a' : '-';
        const hasDate = DATE_RE.test(textContent(el)) ? 'd' : '-';
        const nestedRowBucket = Math.min(el.querySelectorAll('tr').length, 6);
        return el.tagName.toLowerCase() + '|' + cls + '|' + childTags + '|' + anchors + '|' + hasDate + '|r' + nestedRowBucket;
    }

    function analyzeRepeatedChildren(container) {
        const children = Array.from(container.children).filter(child => {
            if (!(child instanceof HTMLElement)) return false;
            if (shouldIgnore(child)) return false;
            if (!isVisible(child)) return false;
            const text = textContent(child);
            const nestedLinks = child.querySelectorAll('a[href]').length;
            const nestedRows = child.querySelectorAll('tr').length;
            if (text.length < 12) return false;
            if ((nestedLinks > 12 || nestedRows > 6) && text.length > 300) return false;
            if (child.querySelectorAll('a[href]').length === 0 && !DATE_RE.test(text) && text.length < 24) return false;
            return true;
        });
        if (children.length < 3) return null;

        const groups = new Map();
        children.forEach((child, idx) => {
            const sig = itemSignature(child);
            if (!groups.has(sig)) groups.set(sig, []);
            groups.get(sig).push({ element: child, idx });
        });

        let best = null;
        for (const [sig, items] of groups.entries()) {
            if (items.length >= 3 && (!best || items.length > best.items.length)) {
                best = { sig, items };
            }
        }
        if (!best) return null;

        const sampleItems = best.items.slice(0, 5).map(i => i.element);
        const linkCount = sampleItems.reduce((s, el) => s + el.querySelectorAll('a[href]').length, 0);
        const dateHits = sampleItems.reduce((s, el) => s + (DATE_RE.test(textContent(el)) ? 1 : 0), 0);
        const avgTextLength = sampleItems.reduce((s, el) => s + textContent(el).length, 0) / sampleItems.length;
        const listScore = best.items.length * 3 + (linkCount / sampleItems.length) * 2 + dateHits * 1.5 + Math.min(avgTextLength / 50, 4);

        return {
            container,
            items: best.items,
            itemCount: best.items.length,
            avgLinks: linkCount / sampleItems.length,
            dateHits,
            avgTextLength,
            listScore
        };
    }

    function paginationSignals(node) {
        if (!node || !(node instanceof HTMLElement) || shouldIgnore(node)) return null;
        const nestedElements = Array.from(node.querySelectorAll('a, button, [role="button"], span')).slice(0, 40);
        const elements = node.matches('a, button, [role="button"], span')
            ? [node, ...nestedElements.filter(el => el !== node)]
            : nestedElements;
        if (elements.length < 1) return null;

        let textHits = 0, numberHits = 0, hrefHits = 0, currentHits = 0;
        for (const el of elements) {
            const text = textContent(el);
            if (PAGE_TEXT_RE.test(text)) {
                textHits++;
                if (/^\\d+$/.test(text)) numberHits++;
                if (/^(?:\\d{1,3}|下一页|下一页|下页|首页|尾页|末页)$/i.test(text)) currentHits++;
            }
            const href = (el.getAttribute('href') || '').toLowerCase();
            if (href.includes('page=') || href.includes('p=') || href.includes('index_') || href.includes('next')) hrefHits++;
        }

        const classHint = /(page|pagination|pager|fy|fenye)/i.test(node.id + ' ' + node.className) ? 4 : 0;
        const renderedBonus = isVisible(node) ? 3 : 0;
        const standaloneNextBonus = elements.length === 1 && NEXT_CONTROL_RE.test(textContent(elements[0])) ? 6 : 0;
        const actionableSignals = textHits + numberHits + hrefHits + standaloneNextBonus;
        if (actionableSignals === 0 && classHint < 4) return null;
        const score = textHits * 3 + numberHits * 2 + hrefHits * 2 + currentHits + classHint + renderedBonus + standaloneNextBonus;

        return { score, element: node, rendered: isVisible(node) };
    }

    function escapeCssValue(value) {
        return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
    }

    function buildSelectorSegment(el) {
        const tag = el.nodeName.toLowerCase();
        if (el.id && /^[a-zA-Z][\\w\\-]*$/.test(el.id)) return `${tag}#${el.id}`;

        const classes = Array.from(el.classList || [])
            .filter(c => c && c.length > 1 && !/\\d/.test(c) && c.length < 30)
            .slice(0, 2);
        if (classes.length > 0) return `${tag}.${classes.join('.')}`;

        const attrCandidates = ['data-testid', 'data-cy', 'data-test', 'data-qa', 'data-id', 'name', 'role', 'itemprop', 'aria-label', 'title', 'alt'];
        for (const attr of attrCandidates) {
            const raw = el.getAttribute(attr);
            if (raw && raw.length <= 80 && !/[\\n\\r]/.test(raw)) {
                return `${tag}[${attr}="${escapeCssValue(raw)}"]`;
            }
        }
        return tag;
    }

    function getCssPath(el) {
        if (!(el instanceof Element)) return '';
        const path = [];
        while (el && el.nodeType === Node.ELEMENT_NODE) {
            const s = buildSelectorSegment(el);
            path.unshift(s);

            const candidate = path.join(' > ');
            try {
                if (document.querySelectorAll(candidate).length === 1) return candidate;
            } catch (_) {}

            el = el.parentElement;
            if (s.includes('#')) break;
            if (el && (el.nodeName.toLowerCase() === 'html' || el.nodeName.toLowerCase() === 'body')) {
                path.unshift(el.nodeName.toLowerCase());
                break;
            }
        }
        return path.join(' > ');
    }

    function getRelativeSelector(root, target) {
        if (!(root instanceof Element) || !(target instanceof Element)) return '';
        if (root === target) return ':scope';
        if (!root.contains(target)) return getCssPath(target);

        const parts = [];
        let el = target;
        while (el && el !== root && el.nodeType === Node.ELEMENT_NODE) {
            const segment = buildSelectorSegment(el);
            parts.unshift(segment);

            const candidate = ':scope > ' + parts.join(' > ');
            try {
                if (root.querySelectorAll(candidate).length === 1) return candidate;
            } catch (_) {}

            el = el.parentElement;
        }
        return ':scope > ' + parts.join(' > ');
    }

    function selectorMatchCount(selector) {
        if (!selector) return 0;
        try {
            return document.querySelectorAll(selector).length;
        } catch (_) {
            return 0;
        }
    }

    function deriveItemSelector(analysis) {
        const itemElements = analysis.items.map(item => item.element);
        if (itemElements.length === 0) return '';

        const firstItem = itemElements[0];
        const tag = firstItem.tagName.toLowerCase();
        const containerSelector = getCssPath(analysis.container);
        const _rawRelative = getRelativeSelector(analysis.container, firstItem);
        const relativeSelector = _rawRelative.startsWith(':scope > ') ? _rawRelative.slice(9) : _rawRelative;
        const itemClasses = intersectStableClassTokens(itemElements);
        const candidates = [];

        // 1. Ancestor-scoped: container > tag.class (most precise)
        if (itemClasses.length > 0 && containerSelector) {
            candidates.push(`${containerSelector} > ${tag}.${itemClasses.join('.')}`);
        }

        // 2. Container > relativeSelector path
        if (containerSelector && relativeSelector) {
            candidates.push(`${containerSelector} > ${relativeSelector}`);
        }

        // 3. Bare class (fallback, may be ambiguous)
        if (itemClasses.length > 0) {
            candidates.push(`${tag}.${itemClasses.join('.')}`);
        }

        // 4. Direct-child class on a single-child wrapper
        const directChild = firstItem.children.length === 1 ? firstItem.firstElementChild : null;
        if (directChild && itemElements.every(el => el.children.length === 1 && el.firstElementChild && el.firstElementChild.tagName === directChild.tagName)) {
            const childElements = itemElements.map(el => el.firstElementChild);
            const childTag = directChild.tagName.toLowerCase();
            const childClasses = intersectStableClassTokens(childElements);
            if (childClasses.length > 0 && containerSelector) {
                candidates.push(`${containerSelector} > ${childTag}.${childClasses.join('.')}`);
            }
        }

        // 5. Full CSS path of first item (absolute fallback)
        candidates.push(getCssPath(firstItem));

        const uniqueCandidates = Array.from(new Set(candidates.filter(Boolean)));
        let bestCandidate = '';
        let bestScore = -Infinity;
        for (const candidate of uniqueCandidates) {
            const matchCount = selectorMatchCount(candidate);
            if (matchCount === 0) continue;
            const exactness = Math.abs(matchCount - analysis.itemCount);
            // Heavily penalise selectors that match far more elements than the item count
            // (global ambiguity: same class used in nav, sidebar, footer, etc.)
            const ambiguityPenalty = matchCount > analysis.itemCount * 2 ? (matchCount - analysis.itemCount) * 6 : 0;
            const semanticBonus = /(news|article|item|card|post|entry|product|list|result|row|record)/i.test(candidate) ? 4 : 0;
            // Reward scoped paths (containing ' > ') over bare selectors
            const scopeBonus = (candidate.match(/>/g) || []).length * 3;
            const brevityBonus = Math.max(0, 5 - candidate.length / 30);
            const score = semanticBonus + scopeBonus + brevityBonus - exactness * 4 - ambiguityPenalty;
            if (score > bestScore) {
                bestScore = score;
                bestCandidate = candidate;
            }
        }

        return bestCandidate || getCssPath(firstItem);
    }

    function detectFields(itemEl) {
        const fields = [];
        const seenKeys = new Set();

        function addField(name, el, type, confidence) {
            if (!(el instanceof Element)) return;
            const selector = getRelativeSelector(itemEl, el);
            if (!selector) return;
            const key = `${name}|${type}|${selector}`;
            if (seenKeys.has(key)) return;
            seenKeys.add(key);
            fields.push({ name, selector, type, confidence });
        }

        // Title candidates: h1-h6, .title, .name, .heading
        ['h1','h2','h3','h4','h5','h6'].forEach(tag => {
            itemEl.querySelectorAll(tag).forEach(el => {
                const text = textContent(el).trim();
                if (text.length > 3 && text.length < 200) {
                    addField('title', el, 'text', 0.9);
                }
            });
        });

        itemEl.querySelectorAll('[class*="title"], [class*="name"], [class*="heading"]').forEach(el => {
            const text = textContent(el).trim();
            if (text.length > 3 && text.length < 200) {
                addField('title', el, 'text', 0.7);
            }
        });

        // Image candidates: img with src
        itemEl.querySelectorAll('img').forEach(el => {
            const src = el.getAttribute('src') || el.getAttribute('data-src');
            if (src) {
                addField('image', el, 'attr:src', 0.85);
            }
        });

        // Link candidates: first significant link
        const links = Array.from(itemEl.querySelectorAll('a[href]')).filter(el => {
            const text = textContent(el).trim();
            return text.length > 3;
        });
        if (links.length > 0) {
            addField('link', links[0], 'attr:href', 0.8);
        }

        // Price candidates
        itemEl.querySelectorAll('[class*="price"], [class*="cost"], [class*="amount"]').forEach(el => {
            const text = textContent(el).trim();
            if (text.match(/[$¥€£]|[0-9]/)) {
                addField('price', el, 'text', 0.6);
            }
        });

        // Rating candidates
        itemEl.querySelectorAll('[class*="rating"], [class*="stars"], [class*="score"]').forEach(el => {
            const text = textContent(el).trim();
            if (text.match(/[0-9.]/)) {
                addField('rating', el, 'text', 0.5);
            }
        });

        return fields;
    }

    // Collect list candidates
    const listCandidates = [];
    LIST_CONTAINER_SELECTORS.forEach(sel => {
        document.querySelectorAll(sel).forEach(container => {
            if (shouldIgnore(container)) return;
            const analysis = analyzeRepeatedChildren(container);
            if (analysis) listCandidates.push(analysis);
        });
    });

    if (listCandidates.length === 0) {
        return { success: false, reason: 'no_list_candidate' };
    }
    listCandidates.sort((a, b) => b.listScore - a.listScore);

    // Collect pagination candidates
    const seen = new Set();
    const pagCandidates = [];
    PAGINATION_CONTAINER_SELECTORS.forEach(sel => {
        document.querySelectorAll(sel).forEach(node => {
            if (seen.has(node)) return;
            seen.add(node);
            const cand = paginationSignals(node);
            if (cand && cand.score >= 6) pagCandidates.push(cand);
        });
    });
    document.querySelectorAll('a.morelink, a[rel="next"], .next a, .pager a, .pagination a').forEach(node => {
        if (seen.has(node)) return;
        seen.add(node);
        const cand = paginationSignals(node);
        if (cand && cand.score >= 6) pagCandidates.push(cand);
    });
    pagCandidates.sort((a, b) => b.score - a.score);

    const best = listCandidates[0];
    const bestPag = pagCandidates.length > 0 ? pagCandidates[0] : null;

    // Capture clean HTML BEFORE adding visual markers so that LLM evidence
    // never contains ephemeral data-sea-auto attributes.
    const cleanHtmlFragment = best.items.slice(0, 3)
        .map(i => i.element.outerHTML)
        .join('\\n')
        .replace(/\\s*data-sea-auto="[^"]*"/g, '')
        .replace(/\\s*data-bridge-highlight="[^"]*"/g, '');

    // Mark elements for visual highlighting and clear them automatically after
    // a short delay so the live page is not permanently polluted.
    best.items.slice(0, 10).forEach((item) => {
        item.element.setAttribute('data-sea-auto', 'item');
    });

    if (bestPag) {
        bestPag.element.setAttribute('data-sea-auto', 'pagination');
    }

    const existingCleanupTimer = window[CLEANUP_TIMER_KEY];
    if (typeof existingCleanupTimer === 'number') {
        window.clearTimeout(existingCleanupTimer);
    }
    window[CLEANUP_TIMER_KEY] = window.setTimeout(() => {
        cleanup();
        delete window[CLEANUP_TIMER_KEY];
    }, MARKER_CLEAR_AFTER_MS);

    // Detect fields from first item
    const fields = detectFields(best.items[0].element);

    // Calculate confidence
    const confidence = Math.min(0.98,
        (best.itemCount >= 5 ? 0.35 : best.itemCount * 0.06) +
        Math.min(best.avgLinks / 3, 0.18) +
        Math.min(best.dateHits / 4, 0.15) +
        (bestPag ? Math.min(bestPag.score / 18, 0.22) : 0)
    );

    // Determine pagination strategy
    let pagStrategy = 'none';
    let pagSelector = '';
    if (bestPag) {
        const pagButtons = bestPag.element.matches && bestPag.element.matches('a, button, [role="button"]')
            ? [bestPag.element, ...Array.from(bestPag.element.querySelectorAll('a, button, [role="button"]')).filter(btn => btn !== bestPag.element)]
            : Array.from(bestPag.element.querySelectorAll('a, button, [role="button"]'));
        const hasLoadMore = pagButtons.some(btn => /^(加载更多|load more|more)$/i.test(textContent(btn)));
        const nextBtns = pagButtons.filter(btn => NEXT_CONTROL_RE.test(textContent(btn).trim()));
        const numberedBtns = pagButtons.filter(btn => /^\\d+$/.test(textContent(btn).trim()));
        if (hasLoadMore) {
            pagStrategy = 'load_more';
        } else if (nextBtns.length > 0 || numberedBtns.length > 0) {
            pagStrategy = 'click_next';
        }
        // Find next button specifically
        if (nextBtns.length > 0) {
            pagSelector = getCssPath(nextBtns[0]);
        }
    }

    const itemSelector = deriveItemSelector(best);

    return {
        success: true,
        confidence,
        item_selector: itemSelector,
        item_count: best.itemCount,
        item_signature: best.sig,
        pagination_selector: pagSelector,
        pagination_strategy: pagStrategy,
        pagination_score: bestPag ? bestPag.score : 0,
        fields: fields.slice(0, 6),
        html_fragment: cleanHtmlFragment
    };
}
