from concurrent.futures import ThreadPoolExecutor, as_completed
from crawlers.crawler import crawl_images_combined
from utils import decode_qr_from_image_url, extract_template_id, fetch_vn_template

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
MAX_WORKERS = 3  # 1GB VPS: 20 workers spikes RAM and triggers OOM killer
QR_PREFIX = "VN://template"

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


def search_templates_controller(query: str, max_results=100):
    candidates = []

    if "vn template" not in query.lower():
        query += " vn template qr code"
    candidates += crawl_images_combined(query, max_results, sources=["pinterest"])

    results = []
    seen = set()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(_process_item, c): i
            for i, c in enumerate(candidates)
        }

        ordered = [None] * len(candidates)

        for fut in as_completed(futures):
            idx = futures[fut]
            ordered[idx] = fut.result()

    results = []
    seen = set()

    for item in ordered:
        if not item:
            continue

        if item["template_id"] in seen:
            continue

        seen.add(item["template_id"])
        results.append(item)

        if len(results) >= max_results:
            break

    return results