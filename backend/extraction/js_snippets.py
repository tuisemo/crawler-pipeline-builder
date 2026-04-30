JS_ELEMENT_PICKER = """
(config) => {
    const PICKER_ATTR = 'data-el-picker';
    const PICKER_HOVER_ATTR = 'data-el-hover';
    const PICKER_CANDIDATE_ATTR = 'data-el-picker-candidate';
    window._selectedElement = null;
    window._pickerLastSelector = '';

    // Color palette for roles
    const DEFAULT_ROLE_ORDER = ['item', 'title', 'image', 'link', 'price', 'rating', 'next_page', 'load_more', 'ignore'];
    const ROLE_COLORS = {
        'item': '#45b7d1',
        'title': '#96ceb4',
        'image': '#dda0dd',
        'link': '#ffeaa7',
        'price': '#ff9f43',
        'rating': '#ff6b9d',
        'next_page': '#00d2d3',
        'load_more': '#a3cb38',
        'ignore': '#636e72'
    };
    const EXTRA_COLORS = ['#74b9ff', '#55efc4', '#fdcb6e', '#fab1a0', '#81ecec', '#a29bfe', '#e17055', '#00b894'];
    const customRoles = Array.isArray(config?.custom_roles) ? config.custom_roles : [];
    const normalizedCustomRoles = customRoles
        .map(r => (typeof r === 'string' ? r.trim() : ''))
        .filter(r => r.length > 0 && r.length <= 32);
    normalizedCustomRoles.forEach((role, idx) => {
        if (!ROLE_COLORS[role]) ROLE_COLORS[role] = EXTRA_COLORS[idx % EXTRA_COLORS.length];
    });
    const ROLE_ORDER = [...DEFAULT_ROLE_ORDER];
    normalizedCustomRoles.forEach(role => {
        if (!ROLE_ORDER.includes(role)) ROLE_ORDER.push(role);
    });
    const roleBySelector = new Map();
    const getOrderedRoles = () => {
        if (normalizedCustomRoles.length > 0) return normalizedCustomRoles;
        return DEFAULT_ROLE_ORDER.filter(role => !['ignore'].includes(role));
    };

    function applyRole(el, role) {
        if (!el || !role) return;
        el.setAttribute(PICKER_ATTR, role);
        el.style.setProperty('--pc', ROLE_COLORS[role] || '#45b7d1');
    }

    function cleanup() {
        document.querySelectorAll('[' + PICKER_ATTR + '], [' + PICKER_HOVER_ATTR + '], [' + PICKER_CANDIDATE_ATTR + ']').forEach(el => {
            el.style.outline = '';
            el.style.backgroundColor = '';
            el.removeAttribute(PICKER_ATTR);
            el.removeAttribute(PICKER_HOVER_ATTR);
            el.removeAttribute(PICKER_CANDIDATE_ATTR);
        });
        const style = document.getElementById('el-picker-style');
        if (style) style.remove();
        const tooltip = document.getElementById('el-picker-tooltip');
        if (tooltip) tooltip.remove();
    }
    cleanup();

    // Inject styles
    const style = document.createElement('style');
    style.id = 'el-picker-style';
    style.textContent = `
        [${PICKER_ATTR}] { outline: 3px solid var(--pc, #45b7d1) !important; position: relative; cursor: pointer; }
        [${PICKER_ATTR}]::after {
            content: attr(${PICKER_ATTR});
            position: absolute; top: 0; left: 0;
            background: var(--pc, #45b7d1);
            color: white; padding: 1px 5px; font-size: 10px; font-weight: bold;
            font-family: 'Segoe UI', sans-serif; z-index: 2147483647; pointer-events: none;
            white-space: nowrap; border-radius: 0 0 3px 0;
        }
        img[${PICKER_ATTR}]::after {
            top: 2px;
            left: 2px;
        }
        [${PICKER_HOVER_ATTR}] {
            outline: 2px dashed #ffd700 !important;
            background-color: rgba(255, 215, 0, 0.15) !important;
        }
        #el-picker-tooltip {
            position: fixed; background: rgba(0,0,0,0.9); color: #00ff88;
            padding: 8px 12px; font-family: 'Consolas', monospace; font-size: 12px;
            z-index: 2147483647; border-radius: 4px; max-width: 400px;
            pointer-events: none; display: none;
        }
        #el-picker-hint {
            position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
            background: rgba(0,0,0,0.85); color: #fff; padding: 10px 20px;
            border-radius: 6px; font-size: 13px; z-index: 2147483646;
            pointer-events: none; text-align: center;
        }
    `;
    document.head.appendChild(style);

    // Create tooltip
    const tooltip = document.createElement('div');
    tooltip.id = 'el-picker-tooltip';
    document.body.appendChild(tooltip);

    // Create hint bar
    const hint = document.createElement('div');
    hint.id = 'el-picker-hint';
    hint.innerHTML = 'Click element to select &nbsp;|&nbsp; Click again to cycle role/custom field &nbsp;|&nbsp; Press Esc to confirm';
    document.body.appendChild(hint);

    function escapeCssValue(value) {
        return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
    }

    function buildSelectorSegment(el) {
        const tag = el.tagName.toLowerCase();
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
            if (el && (el.tagName.toLowerCase() === 'html' || el.tagName.toLowerCase() === 'body')) {
                path.unshift(el.tagName.toLowerCase());
                break;
            }
        }
        return path.join(' > ');
    }

    // Collect all interactive elements
    const IGNORE_TAGS = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','META','HEAD','TITLE','LINK','IFRAME','CANVAS']);
    const candidates = [];

    ['div','section','article','main','ul','ol','li','p','h1','h2','h3','h4','table','tr','td','a','img','span','button'].forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
            if (IGNORE_TAGS.has(el.tagName)) return;
            const rect = el.getBoundingClientRect();
            if (rect.width < 20 || rect.height < 10) return;
            const computedStyle = window.getComputedStyle(el);
            if (computedStyle.display === 'none' || computedStyle.visibility === 'hidden') return;
            const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
            candidates.push({ element: el, tag: el.tagName.toLowerCase(), text: text.slice(0, 80), rect });
        });
    });

    function saveSelection(el, role) {
        const sel = getCssPath(el);
        window._pickerLastSelector = sel;
        window._selectedElement = {
            selector: sel,
            tag: el.tagName.toLowerCase(),
            text: (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
            role: role
        };
    }

    // Add event listeners
    candidates.forEach(c => {
        const el = c.element;
        el.setAttribute(PICKER_CANDIDATE_ATTR, '1');

        el.addEventListener('mouseenter', (e) => {
            e.stopPropagation();
            const selector = getCssPath(el);
            const rememberedRole = roleBySelector.get(selector);
            if (rememberedRole) applyRole(el, rememberedRole);
            el.setAttribute(PICKER_HOVER_ATTR, '');
            const role = el.getAttribute(PICKER_ATTR) || '';
            const color = role ? (ROLE_COLORS[role] || '#ffd700') : '#ffd700';
            tooltip.innerHTML = `<b>${c.tag}</b> ${role ? '[' + role + ']' : '[Click to select]'}<br>` +
                `Text: ${c.text || '(none)'}<br>` +
                `Selector: <span style="color:#96ceb4">${getCssPath(el)}</span>`;
            tooltip.style.display = 'block';
            tooltip.style.left = (c.rect.left + window.scrollX) + 'px';
            tooltip.style.top = (c.rect.bottom + window.scrollY + 5) + 'px';
        });

        el.addEventListener('mouseleave', (e) => {
            el.removeAttribute(PICKER_HOVER_ATTR);
            tooltip.style.display = 'none';
        });

        el.addEventListener('click', (e) => {
            const closest = e.target && e.target.closest ? e.target.closest('[' + PICKER_CANDIDATE_ATTR + '="1"]') : null;
            if (closest !== el) return;
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();

            const selector = getCssPath(el);
            const orderedRoles = getOrderedRoles();
            if (orderedRoles.length === 0) return;
            const currentRole = roleBySelector.get(selector) || el.getAttribute(PICKER_ATTR) || '';
            let role = orderedRoles[0];
            if (currentRole) {
                const idx = orderedRoles.indexOf(currentRole);
                role = idx >= 0
                    ? orderedRoles[(idx + 1 + orderedRoles.length) % orderedRoles.length]
                    : orderedRoles[0];
            }
            roleBySelector.set(selector, role);
            applyRole(el, role);
            saveSelection(el, role);
        }, true);
    });

    // Esc to confirm and clear
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            cleanup();
            const h = document.getElementById('el-picker-hint');
            if (h) h.remove();
        }
    });

    return { count: candidates.length };
}
"""

JS_PICKER_DISABLE = """
() => {
    const PICKER_ATTR = 'data-el-picker';
    const PICKER_HOVER_ATTR = 'data-el-hover';
    const PICKER_CANDIDATE_ATTR = 'data-el-picker-candidate';

    document.querySelectorAll('[' + PICKER_ATTR + '], [' + PICKER_HOVER_ATTR + '], [' + PICKER_CANDIDATE_ATTR + ']').forEach(el => {
        el.style.outline = '';
        el.style.backgroundColor = '';
        el.removeAttribute(PICKER_ATTR);
        el.removeAttribute(PICKER_HOVER_ATTR);
        el.removeAttribute(PICKER_CANDIDATE_ATTR);
    });

    const style = document.getElementById('el-picker-style');
    if (style) style.remove();
    const tooltip = document.getElementById('el-picker-tooltip');
    if (tooltip) tooltip.remove();
    const hint = document.getElementById('el-picker-hint');
    if (hint) hint.remove();

    return { disabled: true };
}
"""

JS_PICKER_READ = """
() => {
    const sel = window._selectedElement;
    if (!sel) return null;
    return {
        selector: sel.selector,
        tag: sel.tag,
        text: sel.text,
        role: sel.role
    };
}
"""

JS_HIGHLIGHT_SELECTOR = """
(selector) => {
    const PICKER_ATTR = 'data-el-test';
    const HIGHLIGHT_COLOR = '#ff6b6b';

    // Remove old highlights
    document.querySelectorAll('[' + PICKER_ATTR + ']').forEach(el => {
        el.style.outline = '';
        el.removeAttribute(PICKER_ATTR);
    });

    // Inject styles
    let style = document.getElementById('el-test-style');
    if (!style) {
        style = document.createElement('style');
        style.id = 'el-test-style';
        style.textContent = `
            [${PICKER_ATTR}] {
                outline: 3px solid ${HIGHLIGHT_COLOR} !important;
                position: relative;
            }
            [${PICKER_ATTR}]::after {
                content: attr(${PICKER_ATTR});
                position: absolute; top: 0; left: 0;
                background: ${HIGHLIGHT_COLOR};
                color: white; padding: 1px 5px; font-size: 10px; font-weight: bold;
                font-family: 'Segoe UI', sans-serif; z-index: 2147483647; pointer-events: none;
                white-space: nowrap; border-radius: 0 0 3px 0;
            }
        `;
        document.head.appendChild(style);
    }

    try {
        const elements = document.querySelectorAll(selector);
        const count = elements.length;
        const samples = [];

        elements.forEach((el, i) => {
            el.setAttribute(PICKER_ATTR, `${i + 1}/${count}`);
            el.style.outline = `3px solid ${HIGHLIGHT_COLOR}`;

            if (i < 5) {
                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
                const hasImg = el.querySelectorAll('img').length > 0;
                const hasLink = el.querySelectorAll('a[href]').length > 0;
                samples.push({ text, has_image: hasImg, has_link: hasLink });
            }
        });

        return { match_count: count, sample_items: samples, error: null };
    } catch(e) {
        return { match_count: 0, sample_items: [], error: e.message };
    }
}
"""

JS_TEST_FIELDS = """
(config) => {
    const FIELD_COLORS = ['#45b7d1','#96ceb4','#dda0dd','#ffeaa7','#ff9f43','#ff6b9d','#00d2d3','#a3cb38'];
    const BASE_ATTR = 'data-el-field';
    const itemSelector = (config && config.item_selector) ? String(config.item_selector).trim() : '';
    const fields = config && Array.isArray(config.fields) ? config.fields : null;

    if (!fields) {
        return { error: 'fields must be an array, got: ' + typeof fields, field_results: [] };
    }

    try {
        const itemContainers = itemSelector
            ? Array.from(document.querySelectorAll(itemSelector))
            : [document];
        const results = [];

        fields.forEach((field, fIdx) => {
            const name = field && (field.name || field.field_name || '');
            const selector = field && (field.selector || field.css || '') || '';
            const rawType = field && (field.type || field.extraction_type || 'text') || 'text';
            const type = rawType === 'all(text)' ? 'all_text' : rawType;
            const color = FIELD_COLORS[fIdx % FIELD_COLORS.length];
            let fieldResult = { name, selector, type, match_count: 0, values: [], success: false, error: null };

            if (!selector) {
                fieldResult.error = 'empty selector';
                results.push(fieldResult);
                return;
            }

            try {
                let elements = [];
                itemContainers.forEach(container => {
                    try {
                        const queried = Array.from(
                            container === document
                                ? document.querySelectorAll(selector)
                                : container.querySelectorAll(selector)
                        );
                        elements.push(...queried);
                    } catch (_) {
                        // Fallback for relative selectors if :scope is not accepted by target browser.
                        if (container !== document && selector.startsWith(':scope')) {
                            const fallbackSelector = selector.replace(/^:scope\\s*>\\s*/, '').replace(/^:scope\\s*/, '').trim();
                            if (fallbackSelector) {
                                try {
                                    elements.push(...Array.from(container.querySelectorAll(fallbackSelector)));
                                } catch (_) {}
                            }
                        }
                    }
                });
                elements = Array.from(new Set(elements));
                fieldResult.match_count = elements.length;

                elements.forEach((el) => {
                    el.setAttribute(BASE_ATTR, `${fIdx}:` + name);
                    el.style.outline = `2px solid ${color}`;

                    let value = null;
                    try {
                        if (type === 'text') {
                            value = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        } else if (type === 'html' || type === 'inner') {
                            value = el.innerHTML || '';
                        } else if (type === 'outer') {
                            value = el.outerHTML || '';
                        } else if (type.startsWith('attr:')) {
                            const parts = type.split(':');
                            const attrName = parts[1];
                            const isAbs = parts.includes('abs');
                            if (attrName === 'href') {
                                const link = el.tagName === 'A' ? el : el.querySelector('a[href]');
                                value = link ? (isAbs ? link.href : link.getAttribute('href')) : null;
                            } else if (attrName === 'src') {
                                const img = el.tagName === 'IMG' ? el : el.querySelector('img[src]');
                                value = img ? (isAbs ? img.src : img.getAttribute('src')) : null;
                            } else {
                                value = el.getAttribute(attrName);
                            }
                        } else if (type === 'all_text') {
                            value = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim();
                        } else if (type === 'all(@href)') {
                            const hrefs = [];
                            if (el.matches && el.matches('a[href]')) {
                                const selfHref = el.getAttribute('href');
                                if (selfHref) hrefs.push(selfHref);
                            }
                            hrefs.push(...Array.from(el.querySelectorAll('a[href]')).map(a => a.getAttribute('href')).filter(Boolean));
                            value = hrefs;
                        } else if (type === 'all(@src)') {
                            const srcs = [];
                            if (el.matches && el.matches('img[src]')) {
                                const selfSrc = el.getAttribute('src');
                                if (selfSrc) srcs.push(selfSrc);
                            }
                            srcs.push(...Array.from(el.querySelectorAll('img[src]')).map(img => img.getAttribute('src')).filter(Boolean));
                            value = srcs;
                        }
                    } catch(_) { value = null; }

                    if (value !== null && value !== '') {
                        fieldResult.values.push(String(value).slice(0, 200));
                    }
                });

                fieldResult.success = fieldResult.values.length > 0 || fieldResult.match_count > 0;
            } catch(e) {
                fieldResult.error = e.message;
            }

            results.push(fieldResult);
        });

        return { field_results: results, error: null };
    } catch(e) {
        return { field_results: [], error: e.message };
    }
}
"""

JS_CLEAR_HIGHLIGHTS = """
() => {
    const attrs = ['data-el-test','data-el-field','data-inspector-id'];
    attrs.forEach(attr => {
        document.querySelectorAll('[' + attr + ']').forEach(el => {
            el.style.outline = '';
            el.removeAttribute(attr);
        });
    });
    ['el-test-style','el-field-style','inspector-style'].forEach(id => {
        const s = document.getElementById(id);
        if (s) s.remove();
    });
    return { cleared: true };
}
"""

JS_SCAN_PAGE = """
() => {
    const IGNORE_TAGS = new Set(['SCRIPT','STYLE','NOSCRIPT','SVG','META','HEAD','TITLE','LINK','IFRAME','CANVAS']);
    const IGNORE_KW = ['navbar','navbar-collapse','nav-link','nav-item','footer','footer-content','site-footer','header','site-header','ad-','advertisement','sponsor','popup','modal','cookie','cookies','sidebar','widget','toolbar'];
    const MIN_W = 20, MIN_H = 12;
    const colors = ['#FF6B6B','#4ECDC4','#45B7D1','#96CEB4','#FFEAA7','#DDA0DD','#98D8C8','#F7DC6F','#BB8FCE','#85C1E9'];

    function ignore(el) {
        if (!el || !el.className) return false;
        const c = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        return IGNORE_KW.some(k => c.includes(k));
    }

    function isVisible(el) {
        if (!el || !(el instanceof HTMLElement)) return false;
        const cs = window.getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return cs.display !== 'none' && cs.visibility !== 'hidden' && cs.opacity !== '0' && r.width > 0 && r.height > 0;
    }

    function getText(el) { return (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim(); }

    function stableClassSig(el) {
        return Array.from(el.classList || [])
            .filter(c => c.length > 2 && !/\\d/.test(c))
            .slice(0, 2).join('.');
    }

    function itemSignature(el) {
        const childTags = Array.from(el.children).slice(0, 6).map(c => c.tagName.toLowerCase()).join(',');
        const cls = stableClassSig(el);
        const hasAnchors = el.querySelectorAll('a[href]').length > 0 ? 'a' : '-';
        return el.tagName.toLowerCase() + '|' + cls + '|' + childTags + '|' + hasAnchors;
    }

    function escapeCssValue(value) {
        return String(value).replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
    }

    function buildSelectorSegment(el) {
        const tag = el.nodeName.toLowerCase();
        if (el.id && /^[a-zA-Z][\\w\\-]*$/.test(el.id)) return `${tag}#${el.id}`;

        const classes = Array.from(el.classList || [])
            .filter(c => c.length > 1 && !/\\d/.test(c) && c.length < 30)
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

    // Score container by repeated-child pattern (list detection)
    function scoreContainer(container) {
        const children = Array.from(container.children).filter(c =>
            c instanceof HTMLElement && isVisible(c) && getText(c).length >= 3
        );
        if (children.length < 2) return null;

        const groups = new Map();
        children.forEach(child => {
            const sig = itemSignature(child);
            if (!groups.has(sig)) groups.set(sig, []);
            groups.get(sig).push(child);
        });

        let best = null;
        for (const [sig, items] of groups.entries()) {
            if (items.length >= 2 && (!best || items.length > best.items.length)) {
                best = { sig, items };
            }
        }
        if (!best) return null;

        const avgLinks = best.items.reduce((s, el) => s + el.querySelectorAll('a[href]').length, 0) / best.items.length;
        const avgText = best.items.reduce((s, el) => s + getText(el).length, 0) / best.items.length;
        const score = best.items.length * 4 + avgLinks * 3 + Math.min(avgText / 20, 8);

        return { container, items: best.items, score, avgLinks, avgText };
    }

    // Score pagination nodes
    function scorePagination(node) {
        const anchors = Array.from(node.querySelectorAll('a[href], button')).slice(0, 30);
        if (anchors.length < 2) return null;
        let textHits = 0, hrefHits = 0;
        for (const a of anchors) {
            const t = getText(a).trim();
            // Match single digits (1,2,3...) and common pagination text
            if ((t.length <= 4 && /^[0-9]+$/.test(t)) || /^(?:上一页|下一页|下页|首页|尾页|next|prev|[<>])$/i.test(t)) textHits++;
            const h = (a.getAttribute('href') || '').toLowerCase();
            if (h.includes('page=') || h.includes('p=') || h.includes('index') || h.includes('pag')) hrefHits++;
        }
        return { score: textHits * 2 + hrefHits * 3, element: node };
    }

    // Inject CSS for inspector highlights
    const style = document.createElement('style');
    style.id = 'inspector-style';
    style.textContent = `
        [data-inspector-id] { outline: 2px solid var(--ic); position: relative; }
        [data-inspector-id]::before {
            content: '#' attr(data-inspector-id);
            position: absolute; top: 0; left: 0;
            background: var(--ic);
            color: white; padding: 1px 5px; font-size: 10px; font-weight: bold;
            font-family: 'Segoe UI', sans-serif; z-index: 2147483647; pointer-events: none;
            white-space: nowrap; border-radius: 0 0 3px 0;
        }
    `;
    document.head.appendChild(style);

    // Collect all DOM elements that will be marked
    const toMark = [];
    const seenIds = new Set();
    let id = 1;

    // Best list container items
    const CONTAINER_SELECTORS = ['main','article','section','div','ul','ol','table','tbody'];
    const listCandidates = [];
    CONTAINER_SELECTORS.forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
            if (ignore(el)) return;
            const scored = scoreContainer(el);
            if (scored) listCandidates.push(scored);
        });
    });
    listCandidates.sort((a, b) => b.score - a.score);

    if (listCandidates.length > 0) {
        const best = listCandidates[0];
        best.items.forEach(item => {
            toMark.push({ el: item, id: id, region: 'list' });
            seenIds.add(item);
            id++;
        });
    }

    // Pagination links
    const pagCandidates = [];
    ['nav','div','ul'].forEach(sel => {
        document.querySelectorAll(sel).forEach(node => {
            if (ignore(node)) return;
            const s = scorePagination(node);
            if (s && s.score >= 2) pagCandidates.push(s);
        });
    });
    pagCandidates.sort((a, b) => b.score - a.score);
    if (pagCandidates.length > 0) {
        pagCandidates[0].element.querySelectorAll('a[href], button').forEach(link => {
            toMark.push({ el: link, id: id, region: 'pagination' });
            id++;
        });
    }

    // Other important elements
    ['div','section','article','main','ul','ol','li','p','h1','h2','h3','h4','h5','h6','table','tr','td','a'].forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
            if (IGNORE_TAGS.has(el.tagName)) return;
            if (ignore(el)) return;
            if (seenIds.has(el)) return;

            const text = getText(el);
            const links = el.querySelectorAll('a[href]').length;
            // Important if: has links, or substantial text, or is an image/video container
            const isImportant = links > 0 || text.length >= 5 || el.querySelectorAll('img,video,figure').length > 0;
            if (!isImportant) return;
            toMark.push({ el: el, id: id, region: 'other' });
            id++;
        });
    });

    // Apply marks to DOM
    const result = [];
    toMark.forEach(({ el, id: eid, region }) => {
        const rect = el.getBoundingClientRect();
        const text = getText(el);
        const color = colors[(eid - 1) % colors.length];

        el.setAttribute('data-inspector-id', eid);
        el.style.setProperty('--ic', color);
        el.style.outline = `2px solid ${color}`;

        result.push({
            id: eid,
            tag: el.tagName.toLowerCase(),
            selector: getCssPath(el),
            text: text.slice(0, 100),
            top: Math.round(rect.top),
            left: Math.round(rect.left),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            color,
            region
        });
    });

    return { elements: result, total: result.length, listScore: listCandidates.length > 0 ? listCandidates[0].score : 0 };
}
"""
