from extraction.html_extractor import HtmlExtractor


class FakeItem:
    def __init__(self, html: str, parent_html: str | None = None):
        self._html = html
        self._parent_html = parent_html or f"<section>{html}</section>"

    def inner_html(self):
        return self._html

    def evaluate(self, _script: str):
        return self._parent_html


class FakePage:
    def __init__(self, items, selector_map=None):
        self._items = items
        self._selector_map = selector_map or {}

    def query_selector_all(self, selector: str):
        if selector in self._selector_map:
            return self._selector_map[selector]
        return self._items


class FakeControl:
    def __init__(self, text: str, href: str = ''):
        self._text = text
        self._href = href

    def inner_text(self):
        return self._text

    def get_attribute(self, name: str):
        if name == 'href':
            return self._href
        return ''


class FakePaginationNode:
    def __init__(self, text: str, outer_html: str, controls, class_name: str = 'kq-pager', node_id: str = ''):
        self._text = text
        self._outer_html = outer_html
        self._controls = controls
        self._class_name = class_name
        self._id = node_id

    def evaluate(self, _script: str):
        return self._outer_html

    def inner_text(self):
        return self._text

    def query_selector_all(self, selector: str):
        if selector == 'a, button, [role="button"], span':
            return self._controls
        return []

    def get_attribute(self, name: str):
        if name == 'class':
            return self._class_name
        if name == 'id':
            return self._id
        return ''


def test_extract_item_container_reports_total_match_count_not_sample_size():
    items = [FakeItem(f"<div>item-{idx}</div>") for idx in range(5)]

    result = HtmlExtractor().extract_item_container(FakePage(items), ".item", max_items=3)

    assert result.item_count == 5
    assert "item-0" in result.html
    assert "item-2" in result.html
    assert "item-3" not in result.html


def test_extract_wrapper_context_reports_total_match_count_not_sample_size():
    items = [
        FakeItem(
            "<div>item-0</div>",
            parent_html="<section><div>item-0</div><div>item-1</div><div>item-2</div></section>",
        ),
        FakeItem("<div>item-1</div>"),
        FakeItem("<div>item-2</div>"),
        FakeItem("<div>item-3</div>"),
        FakeItem("<div>item-4</div>"),
    ]

    result = HtmlExtractor().extract_wrapper_context(FakePage(items), ".item", max_items=3)

    assert result.item_count == 5
    assert "item-0" in result.html


def test_extract_pagination_context_includes_global_pager_markup():
    items = [FakeItem(f"<div>item-{idx}</div>", parent_html=f"<div class='item'>item-{idx}</div>") for idx in range(5)]
    pager = FakePaginationNode(
        text="13030 条 1/326 页 1 2 3 下一页 尾页",
        outer_html='<div class="kq-pager"><span class="current">1</span><a href="/list?p=2">2</a><a href="/list?p=3">3</a><a href="/list?p=2">下一页</a><a href="/list?p=326">尾页</a></div>',
        controls=[
            FakeControl('1'),
            FakeControl('2', '/list?p=2'),
            FakeControl('3', '/list?p=3'),
            FakeControl('下一页', '/list?p=2'),
            FakeControl('尾页', '/list?p=326'),
        ],
    )
    page = FakePage(items, selector_map={'.kq-pager': [pager]})

    result = HtmlExtractor().extract_pagination_context(page, '.item', max_items=3)

    assert result.item_count == 5
    assert '<!-- PAGINATION -->' in result.html
    assert 'kq-pager' in result.html
    assert '下一页' in result.html
