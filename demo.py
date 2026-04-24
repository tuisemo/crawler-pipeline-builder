
import json
import time
import random
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

# ================= CONFIGURATION =================
ENTRY_URL = "https://www.eworldship.com/app/product_1772.html"
ITEM_SELECTOR = "body > div.desktop > div.kq-wrapper > div.kq-row > div.kq-col3"
MAX_PAGES = 50
MAX_ITEMS = 5
OUTPUT_FILE = "crawler_output.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
]

# ================= HELPER FUNCTIONS =================
def random_delay(min_sec=1.0, max_sec=3.0):
    """Introduce realistic human-like delay between actions."""
    time.sleep(random.uniform(min_sec, max_sec))

def retry_operation(func, retries=3, base_delay=2.0):
    """Simple retry wrapper for network/page operations."""
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            print(f"  [RETRY] Attempt {attempt + 1}/{retries} failed: {e}")
            time.sleep(base_delay * (attempt + 1))
    raise Exception("Max retries exceeded")

def extract_items(page, base_url):
    """Extract structured data from the current page."""
    items = []
    try:
        # Wait for items to render
        page.wait_for_selector(ITEM_SELECTOR, timeout=10000)
        elements = page.locator(ITEM_SELECTOR).all()
        
        for el in elements:
            try:
                # Title
                title_el = el.locator(":scope > div.kq-well > a > p.product-title")
                title = title_el.inner_text().strip() if title_el.count() > 0 else ""
                
                # Image
                img_el = el.locator(":scope > div.kq-well > a > div.product-img > img")
                img_src = img_el.get_attribute("src") if img_el.count() > 0 else ""
                if img_src:
                    img_src = urljoin(base_url, img_src)
                    
                # Link
                link_el = el.locator(":scope > div.kq-well > a")
                link_href = link_el.get_attribute("href") if link_el.count() > 0 else ""
                if link_href:
                    link_href = urljoin(base_url, link_href)
                    
                items.append({
                    "title": title,
                    "image": img_src,
                    "link": link_href
                })
            except Exception as e:
                print(f"  [WARN] Failed to extract item: {e}")
                continue
    except Exception as e:
        print(f"  [ERROR] Failed to locate items container: {e}")
    return items

# ================= MAIN CRAWLER =================
def run_crawler():
    with sync_playwright() as p:
        # Anti-detection context setup
        context = p.chromium.launch(headless=False).new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(USER_AGENTS),
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True
        )
        page = context.new_page()
        page.set_extra_http_headers({
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        })

        all_items = []
        current_page = 1
        
        try:
            print(f"[INFO] Navigating to {ENTRY_URL}")
            retry_operation(lambda: page.goto(ENTRY_URL, wait_until="domcontentloaded", timeout=30000))
            random_delay(1.5, 3.0)
            
            while current_page <= MAX_PAGES and len(all_items) < MAX_ITEMS:
                print(f"[INFO] Extracting page {current_page}...")
                new_items = extract_items(page, ENTRY_URL)
                all_items.extend(new_items)
                
                if len(all_items) >= MAX_ITEMS:
                    print(f"[INFO] Reached max items limit ({MAX_ITEMS}).")
                    break
                    
                if current_page >= MAX_PAGES:
                    break
                    
                # Pagination Logic
                print(f"[INFO] Attempting to navigate to next page...")
                
                # Fallback selectors since plan specifies empty selector
                next_selectors = [
                    'a:has-text("下一页")',
                    'a:has-text("Next")',
                    '.next-page',
                    '.pagination a:has-text(">")',
                    'a.next',
                    'a[rel="next"]'
                ]
                
                next_btn = None
                for sel in next_selectors:
                    try:
                        locator = page.locator(sel).first
                        if locator.is_visible():
                            next_btn = locator
                            break
                    except:
                        continue
                        
                if not next_btn:
                    print("[INFO] No next page button found. Stopping pagination.")
                    break
                    
                # Capture state before click to verify actual page change
                try:
                    first_item_before = page.locator(ITEM_SELECTOR).first.inner_text()
                except:
                    first_item_before = ""
                    
                next_btn.scroll_into_view_if_needed()
                random_delay(0.5, 1.0)
                next_btn.click()
                
                # Wait for navigation/content update
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                except:
                    pass
                    
                random_delay(1.5, 3.0)
                
                # Verify content actually changed
                try:
                    page.wait_for_selector(ITEM_SELECTOR, timeout=5000)
                    first_item_after = page.locator(ITEM_SELECTOR).first.inner_text()
                    if first_item_before == first_item_after:
                        print("[INFO] Content did not change after clicking next. Stopping.")
                        break
                except Exception as e:
                    print(f"[WARN] Pagination verification failed: {e}")
                    break
                    
                current_page += 1
                
        except Exception as e:
            print(f"[ERROR] Crawler execution failed: {e}")
        finally:
            context.close()
            
        # Output results
        print(f"[INFO] Total items extracted: {len(all_items)}")
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_items, f, indent=2, ensure_ascii=False)
        print(f"[INFO] Data successfully saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    run_crawler()
