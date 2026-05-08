from backend.extraction.auto_detector import AutoDetector, JS_AUTO_DETECT


class FakePageResult:
    def __init__(self, result):
        self._result = result

    def evaluate(self, _script: str):
        return self._result


class FakePageError:
    def evaluate(self, _script: str):
        raise RuntimeError("boom")


def test_auto_detector_maps_evaluated_result():
    detector = AutoDetector()
    page = FakePageResult(
        {
            "success": True,
            "item_selector": "div.quote",
            "item_count": 10,
            "item_signature": "div|quote",
            "pagination_selector": ".pager .next a",
            "pagination_strategy": "click_next",
            "pagination_score": 11,
            "confidence": 0.88,
            "fields": [
                {
                    "name": "title",
                    "selector": ":scope > .title",
                    "type": "text",
                    "confidence": 0.9,
                }
            ],
            "html_fragment": "<div class='quote'>...</div>",
        }
    )

    result = detector.detect(page)

    assert result.item_selector == "div.quote"
    assert result.item_count == 10
    assert result.pagination_selector == ".pager .next a"
    assert result.pagination_strategy == "click_next"
    assert len(result.fields) == 1
    assert result.fields[0].selector == ":scope > .title"


def test_auto_detector_returns_none_pagination_strategy_when_detection_fails():
    detector = AutoDetector()

    result = detector.detect(FakePageError())

    assert result.item_selector == ""
    assert result.item_count == 0
    assert result.pagination_selector == ""
    assert result.pagination_strategy == "none"


def test_auto_detector_js_replaces_prior_cleanup_timer():
    assert "const CLEANUP_TIMER_KEY = '__seaAutoCleanupTimer';" in JS_AUTO_DETECT
    assert "window.clearTimeout(existingCleanupTimer);" in JS_AUTO_DETECT
    assert "delete window[CLEANUP_TIMER_KEY];" in JS_AUTO_DETECT
