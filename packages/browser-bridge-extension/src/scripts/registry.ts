import { __eval__, bridge_click_element, bridge_extract_fields, bridge_query_selector, bridge_scroll_to_bottom } from './builtins'
import { bridge_auto_detect } from './auto_detect'
import { bridge_clear_highlight, bridge_highlight_selector } from './highlight'
import { bridge_extract_items, bridge_extract_pagination_context } from './html_extract'

export const SCRIPT_REGISTRY = {
  bridge_query_selector,
  bridge_extract_fields,
  bridge_click_element,
  bridge_scroll_to_bottom,
  bridge_auto_detect,
  bridge_highlight_selector,
  bridge_clear_highlight,
  bridge_extract_items,
  bridge_extract_pagination_context,
  __eval__,
}
