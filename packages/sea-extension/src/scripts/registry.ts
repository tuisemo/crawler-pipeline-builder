import { __eval__, sea_click_and_observe, sea_extract_fields, sea_query_all, sea_scroll_bottom } from './builtins'
import { sea_auto_detect } from './auto_detect'
import { sea_clear_highlight, sea_highlight } from './highlight'
import { sea_extract_html, sea_extract_html_with_pagination } from './html_extract'

export const SCRIPT_REGISTRY = {
  sea_query_all,
  sea_extract_fields,
  sea_click_and_observe,
  sea_scroll_bottom,
  sea_auto_detect,
  sea_highlight,
  sea_clear_highlight,
  sea_extract_html,
  sea_extract_html_with_pagination,
  __eval__,
}
