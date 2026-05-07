from playwright.sync_api import sync_playwright
from urllib.parse import quote_plus
import random
import time


# --- Helpers ---

def _random_delay(min_ms=800, max_ms=2500):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def _human_scroll(page, step=400):
    current = 0
    target = page.evaluate("document.body.scrollHeight")

    while current < target:
        current += random.randint(step - 100, step + 100)
        page.evaluate(f"window.scrollTo({{top: {current}, behavior: 'smooth'}})")
        _random_delay(200, 600)


def _human_mouse_wiggle(page):
    for _ in range(random.randint(2, 5)):
        page.mouse.move(
            random.randint(100, 1100),
            random.randint(100, 600),
        )
        _random_delay(100, 300)


def _make_context(p, proxy: dict = None):
    browser = p.chromium.launch(
        headless=True,
        **({"proxy": proxy} if proxy else {}),
    )

    context = browser.new_context(
        viewport={
            "width": random.choice([1280, 1366, 1440, 1536]),
            "height": random.choice([720, 768, 800, 864]),
        },
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        java_script_enabled=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )

    return browser, context


# --- Pinterest Crawler ---
def crawl_pinterest_images(query: str, max_results=30, proxy: dict = None):
    results = []
    seen = set()

    with sync_playwright() as p:
        browser, context = _make_context(p, proxy)
        page = context.new_page()

        # Block heavy resources — crawler only needs HTML src attributes, not actual downloads
        page.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]
            else route.continue_())

        url = f"https://in.pinterest.com/search/pins/?q={quote_plus(query)}&rs=typed"

        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_selector('a[href^="/pin/"]', timeout=20000)

        # let layout stabilize
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(2)

        def extract_visible():
            return page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href^="/pin/"]'));

                    const pickBestFromSrcset = (srcset) => {
                        if (!srcset) return "";
                        const items = srcset.split(",").map(s => s.trim()).filter(Boolean);

                        let best = "";
                        let bestScore = -1;

                        for (const item of items) {
                            const parts = item.split(/\s+/);
                            const url = parts[0] || "";
                            const desc = parts[1] || "1x";

                            let score = 1;
                            const wMatch = desc.match(/([0-9]+)w/);   // e.g. "736w" → 736
                            const xMatch = desc.match(/([0-9.]+)x/);  // e.g. "2x"  → 800
                            if (wMatch) score = parseFloat(wMatch[1]);
                            else if (xMatch) score = parseFloat(xMatch[1]) * 400;

                            if (score > bestScore) {
                                bestScore = score;
                                best = url;
                            }
                        }

                        return best;
                    };

                    const out = [];

                    for (const a of anchors) {
                        const rect = a.getBoundingClientRect();

                        // only take elements near viewport (fix virtualization issue)
                        if (rect.bottom < 0 || rect.top > window.innerHeight * 1.5) continue;

                        const href = a.getAttribute("href") || "";
                        const pinId = href.match(/\\/pin\\/(\\d+)\\//)?.[1] || "";
                        if (!pinId) continue;

                        const card = a.closest('[data-test-id="pin"], div');
                        const img = card?.querySelector('img[src], img[srcset]');

                        const srcset = img?.getAttribute('srcset') || "";

                        const pageUrl = href ? new URL(href, location.origin).href : "";

                        out.push({
                            pin_id: pinId,
                            img: pickBestFromSrcset(srcset) || img?.currentSrc || img?.src || "",
                            page: pageUrl,
                            title: img?.alt?.trim() || ""
                        });
                    }

                    return out;
                }
            """)

        scroll_y = 0
        stagnant = 0

        while len(results) < max_results:

            batch = extract_visible()
            added = 0

            for item in batch:
                img_url = item["img"]
                pin_id = item["pin_id"]

                if not img_url or pin_id in seen:
                    continue

                if img_url.startswith("//"):
                    img_url = "https:" + img_url

                seen.add(pin_id)

                results.append({
                    "qr_image": img_url,
                    "page_url": item["page"],
                    "title": item["title"],
                    "source": "pinterest",
                    "query": query,
                    "pin_id": pin_id,
                })

                added += 1

                if len(results) >= max_results:
                    browser.close()
                    return results

            # small controlled scroll (key fix)
            scroll_y += random.randint(300, 600)
            page.evaluate(f"window.scrollTo(0, {scroll_y})")

            # allow new pins to render
            time.sleep(random.uniform(1.2, 2.2))

            if added == 0:
                stagnant += 1
            else:
                stagnant = 0

            if stagnant >= 5:
                break

        browser.close()

    return results

# --- DuckDuckGo Crawler ---
def crawl_duckduckgo(query: str, max_results=30, proxy: dict = None):
    results = []
    seen = set()

    with sync_playwright() as p:
        browser, context = _make_context(p, proxy)
        page = context.new_page()

        # Block heavy resources — only HTML DOM is needed
        page.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]
            else route.continue_())

        url = f"https://duckduckgo.com/?q={quote_plus(query)}&iax=images&ia=images"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        _random_delay(1500, 3000)
        _human_mouse_wiggle(page)

        last_height = 0
        stagnant_rounds = 0

        while len(results) < max_results:

            batch = page.evaluate("""
                () => {
                    const items = Array.from(document.querySelectorAll('figure'));
                    return items.map(fig => {
                        const img   = fig.querySelector('img');
                        const a     = fig.querySelector('a');
                        const title = fig.querySelector('h3');

                        return {
                            img: img?.src || img?.getAttribute('src') || "",
                            page: a?.href || "",
                            title: title?.innerText || ""
                        };
                    });
                }
            """)

            for item in batch:
                img_url = item["img"]

                if not img_url or img_url in seen:
                    continue

                if img_url.startswith("//"):
                    img_url = "https:" + img_url

                seen.add(img_url)

                results.append({
                    "qr_image": img_url,
                    "page_url": item["page"],
                    "title": item["title"],
                    "source": "duck",
                    "query": query,
                })

                if len(results) >= max_results:
                    browser.close()
                    return results

            _human_scroll(page)
            _human_mouse_wiggle(page)

            try:
                page.wait_for_selector("figure", timeout=15000)
            except:
                pass

            new_height = page.evaluate("document.body.scrollHeight")

            if new_height == last_height:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 3:
                break

            last_height = new_height
            _random_delay(800, 1800)

        browser.close()

    return results

def crawl_bing_images(query: str, max_results=30, proxy: dict = None):
    results = []
    seen = set()

    with sync_playwright() as p:
        browser, context = _make_context(p, proxy)
        page = context.new_page()

        # Block heavy resources — only HTML DOM is needed
        page.route("**/*", lambda route: route.abort()
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]
            else route.continue_())

        url = f"https://www.bing.com/images/search?q={quote_plus(query)}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        _random_delay(1500, 3000)
        _human_mouse_wiggle(page)

        last_height = 0
        stagnant_rounds = 0

        while len(results) < max_results:

            batch = page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a.iusc'));

                    return anchors.map(a => {
                        try {
                            const meta = JSON.parse(a.getAttribute("m") || "{}");

                            return {
                                img: meta.murl || "",
                                thumb: meta.turl || "",
                                page: meta.purl || "",
                                title: meta.t || ""
                            };
                        } catch (e) {
                            return null;
                        }
                    }).filter(Boolean);
                }
            """)

            for item in batch:
                img_url = item["img"]

                if not img_url or img_url in seen:
                    continue

                if img_url.startswith("//"):
                    img_url = "https:" + img_url

                seen.add(img_url)

                results.append({
                    "qr_image": img_url,
                    "thumbnail": item["thumb"],
                    "page_url": item["page"],
                    "title": item["title"],
                    "source": "bing",
                    "query": query,
                })

                if len(results) >= max_results:
                    browser.close()
                    return results

            _human_scroll(page)
            _human_mouse_wiggle(page)

            try:
                page.wait_for_selector("a.iusc", timeout=15000)
            except:
                pass

            new_height = page.evaluate("document.body.scrollHeight")

            if new_height == last_height:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= 3:
                break

            last_height = new_height
            _random_delay(800, 1800)

        browser.close()

    return results

# --- Orchestrator ---
def crawl_images_combined(
    query: str,
    max_results: int = 30,
    sources: list = ["pinterest", "duck", "bing"],
    deduplicate: bool = True,
    proxy: dict = None,
) -> list:

    all_results = []

    if "pinterest" in sources:
        print(f"[+] Pinterest → {query}")
        p_results = crawl_pinterest_images(query, max_results=max_results, proxy=proxy)
        print(f"    {len(p_results)} results")
        all_results.extend(p_results)

    if "duck" in sources:
        print(f"[+] DuckDuckGo → {query}")
        d_results = crawl_duckduckgo(query, max_results=max_results, proxy=proxy)
        print(f"    {len(d_results)} results")
        all_results.extend(d_results)
    if "bing" in sources:
        print(f"[+] Bing → {query}")
        b_results = crawl_bing_images(query, max_results=max_results, proxy=proxy)
        print(f"    {len(b_results)} results")
        all_results.extend(b_results)

    if deduplicate:
        seen_urls = set()
        unique = []
        for item in all_results:
            if item["qr_image"] not in seen_urls:
                seen_urls.add(item["qr_image"])
                unique.append(item)
        print(f"[+] Unique after dedup: {len(unique)}")
        return unique

    return all_results

