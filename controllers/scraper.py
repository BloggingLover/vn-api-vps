from concurrent.futures import ThreadPoolExecutor, as_completed
from crawlers.crawler import crawl_images_combined
from utils import decode_qr_from_image_url, extract_template_id, fetch_vn_template
import threading

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
MAX_WORKERS = 4  # 4GB RAM / 1 vCPU VPS: OpenCV is CPU-bound, 1 vCPU will struggle if this is too high
QR_PREFIX = "VN://template"
CRAWLER_LOCK = threading.Semaphore(4) # Allow 4 concurrent requests (browsers) with 4GB RAM

def _process_item(item):
    qr = decode_qr_from_image_url(item.get("qr_image", ""))
    if not qr or not qr.startswith(QR_PREFIX):
        return None

    template_id, id_type = extract_template_id(qr)
    if not template_id:
        return None

    vn = fetch_vn_template(template_id, id_type=id_type)
    if not vn:
        return None

    return {
        "template_id": vn.get("template_id") or template_id,
        "qr_data": qr,
        "title": vn["title"],
        "preview_image": vn["preview_image"],
        "preview_video": vn["preview_video"],
        "category": vn["category"],
        "likes": vn["likes"],
        "usage": vn["usage"],
        "author": vn["author"],
        "img_url": vn["preview_image"],
        "page_url": item["page_url"],
        "qr_image": item["qr_image"],
        "source": item["source"],
    }


def search_templates_controller(query: str, max_results=100, method=0):
    candidates = []

    if "vn template" not in query.lower():
        query += " vn template"
        
    sources_map = {
        0: ["pinterest", "duck", "bing"],
        1: ["pinterest"],
        2: ["duck"],
        3: ["bing"]
    }
    sources = sources_map.get(method, ["pinterest", "duckduckgo", "bing"])
    
    # We MUST scrape 3x more raw images than requested because most images on Bing/DuckDuckGo do not contain valid QRs.
    # We scrape 30 raw images -> filter out the 20 broken ones -> return exactly the 10 valid templates requested by Remote Config.
    images_to_scrape = max_results * 3
    
    # Global Concurrency Limiter: Prevent CPU overload by forcing max 3 simultaneous heavy browsers
    with CRAWLER_LOCK:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(crawl_images_combined, query, images_to_scrape, sources=sources)
            candidates += future.result()

    results = []
    seen = set()

    # Process candidates in chunks of 5 to avoid decoding 90 images unnecessarily
    # This prevents the 1-vCPU server from spending 90+ seconds decoding useless QRs
    chunk_size = 5
    for i in range(0, len(candidates), chunk_size):
        chunk = candidates[i:i + chunk_size]
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(_process_item, c): j for j, c in enumerate(chunk)}
            ordered_chunk = [None] * len(chunk)
            
            for fut in as_completed(futures):
                idx = futures[fut]
                ordered_chunk[idx] = fut.result()
                
        for item in ordered_chunk:
            if not item:
                continue
            if item["template_id"] in seen:
                continue
                
            seen.add(item["template_id"])
            results.append(item)
            
        if len(results) >= max_results:
            break

    final_results = results[:max_results]
    print(f"[STATS] Query: '{query}' | Sources: {sources} | Images Scanned: {len(candidates)} | Templates Found: {len(final_results)}")
    
    return final_results