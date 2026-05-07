import requests
import cv2
from urllib.parse import urlparse, parse_qs, unquote
import re
import threading
import numpy as np
import re

_http_local = threading.local()
# ─────────────────────────────────────────────
# SESSION (ANTI-BLOCK HEADERS)
# ─────────────────────────────────────────────
def get_session():
    if not hasattr(_http_local, "s"):
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Accept": "text/html,application/json,image/*,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://duckduckgo.com/"
        })
        _http_local.s = s
    return _http_local.s

def decode_qr_from_image_url(image_url: str):
    try:
        # Handle DuckDuckGo redirect URLs
        if "duckduckgo.com/iu/" in image_url:
            qs = parse_qs(urlparse(image_url).query)
            image_url = unquote(qs.get("u", [""])[0])

        # Use correct Referer per CDN — Pinterest blocks requests with wrong Referer
        if "pinimg.com" in image_url or "pinterest.com" in image_url:
            referer = "https://www.pinterest.com/"
        else:
            referer = "https://duckduckgo.com/"

        session = get_session()
        session.headers.update({"Referer": referer})

        # Download image
        r = session.get(image_url, timeout=10)
        if r.status_code != 200:
            return None

        arr = np.frombuffer(r.content, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None

        detector = cv2.QRCodeDetector()

        # Try direct decode first
        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data

        h, w = img.shape

        # Upscale for better QR visibility (common fix for Pinterest images)
        if w < 800:
            scale = 800 / w
            img = cv2.resize(img, (800, int(h * scale)), interpolation=cv2.INTER_CUBIC)

        # Second attempt after upscaling
        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data

        # Improve contrast (helps with low-quality/compressed images)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        img = clahe.apply(img)

        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data

        # Adaptive threshold for noisy or low-contrast QR regions
        img = cv2.adaptiveThreshold(
            img,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11,
            2
        )

        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data

        # Light blur to stabilize noisy edges
        img = cv2.GaussianBlur(img, (5, 5), 0)

        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data

        # Multi-scale fallback (catches small QR codes missed earlier)
        for scale in [1.2, 1.5, 2.0]:
            resized = cv2.resize(
                img,
                (int(w * scale), int(h * scale)),
                interpolation=cv2.INTER_CUBIC
            )

            data, _, _ = detector.detectAndDecode(resized)
            if data:
                return data

        return None

    except Exception:
        return None

# ─────────────────────────────────────────────
# TEMPLATE ID
# ─────────────────────────────────────────────
def extract_template_id(qr: str):
    """Returns (template_id, id_type) where id_type is 'id' or 'uuid'."""
    # Newer QR format: VN://template?uuid=470f06fe55754d6c8522d4b2b8a01763
    m_uuid = re.search(r"uuid=([a-fA-F0-9\-]+)", qr)
    if m_uuid:
        return m_uuid.group(1), "uuid"
    # Older QR format: VN://template?id=712014
    m_id = re.search(r"id=(\d+)", qr)
    if m_id:
        return m_id.group(1), "id"
    return None, None

def fetch_vn_template(template_id: str, id_type: str = "id"):
    try:
        base = "https://api2.vlognow.me/vnflow/api/v1/public/template"
        print(f"Fetching template — type={id_type}, value={template_id}")

        if id_type == "uuid":
            # UUID format → /unique_id/ is the correct VN API endpoint
            url = f"{base}/unique_id/{template_id}"
            r = get_session().get(url, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 1:
                    return parse_template(data["data"])
        else:
            # Numeric ID format → try direct ID endpoint
            url = f"{base}/{template_id}"
            r = get_session().get(url, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 1:
                    return parse_template(data["data"])
            # fallback to unique_id
            url = f"{base}/unique_id/{template_id}"
            r = get_session().get(url, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 1:
                    return parse_template(data["data"])

        print("URL used (last attempt):", url)
        return None

    except Exception as e:
        print(f"fetch_vn_template error: {e}")
        return None


def parse_template(d):
    return {
        "template_id": d.get("id"),
        "title": d.get("title"),
        "preview_image": d.get("background"),
        "preview_video": d.get("postvideourl"),
        "duration": d.get("duration"),
        "category": d.get("category_id"),
        "likes": d.get("like_num"),
        "usage": d.get("apply_num"),
        "author": {
            "name": d.get("author_info", {}).get("nickname"),
            "username": d.get("author_info", {}).get("username"),
            "avatar": d.get("author_info", {}).get("avatar"),
        },
        "vnt_url": d.get("vnt_url"),
    }