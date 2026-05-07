# VN Template API - Future Optimizations & Scaling Plan

This document outlines the recommended strategies to scale the VN Template API, specifically designed to make it run smoothly on a 1GB RAM VPS, handle high user traffic, and provide a seamless in-app user experience.

## 1. Database & Caching Strategy (Supabase)

Running Playwright for every search request is highly resource-intensive and slow. The ultimate solution is to integrate a managed database like **Supabase** (PostgreSQL) to act as a middleman.

### The Flow
1. **App Request:** User searches for "Love" in the app.
2. **Normalize:** The API normalizes the query (e.g., "Love", "love vn template qr" all become `"love vn template"`).
3. **Database Check:** The API checks the Supabase database for the query.
    *   **Cache Hit:** If found, the API returns the templates instantly (< 100ms) with zero Playwright usage.
    *   **Cache Miss:** If not found, the API uses Playwright to scrape, decodes the QRs, saves the results to Supabase, and returns the data to the user.
4. **Force Refresh:** The app has a "Run a new search" button. When clicked, it calls `/search?query=love&force_refresh=true`. The API uses Playwright to find *new* templates, appends them to the database, and returns the combined list.

### Supabase SQL Schema
Run this in the Supabase SQL editor to create the tables. This structure allows you to manually add, delete, or rearrange the order of templates directly from the Supabase dashboard using the `sort_order` column.

```sql
-- 1. Table for all unique templates
CREATE TABLE templates (
    template_id BIGINT PRIMARY KEY,
    qr_data TEXT,
    title TEXT,
    preview_image TEXT,
    preview_video TEXT,
    category TEXT,
    likes INTEGER,
    usage INTEGER,
    author_name TEXT,
    author_username TEXT,
    author_avatar TEXT,
    page_url TEXT,
    qr_image TEXT,
    source TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Table for normalized search queries
CREATE TABLE searches (
    query TEXT PRIMARY KEY,
    last_scraped_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Table linking searches to templates with a custom sort order
CREATE TABLE search_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    search_query TEXT REFERENCES searches(query) ON DELETE CASCADE,
    template_id BIGINT REFERENCES templates(template_id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(search_query, template_id)
);
```

---

## 2. Playwright & Memory Optimizations (Crucial for 1GB VPS)

When you do need to use Playwright (on cache misses or force refreshes), you must optimize it so the 1GB VPS doesn't crash.

1. **Headless Mode:** Ensure `headless=True` in `crawlers/crawler.py` before deploying to production.
2. **Block Heavy Resources:** Playwright should be configured to abort loading actual image bytes, fonts, and CSS. The crawler only needs the HTML DOM to extract the `src` attributes.
3. **Reduce Concurrency:** In `controllers/scraper.py`, lower `MAX_WORKERS` from `20` to `3` or `5`. Threading OpenCV QR decoding and heavy network requests will spike RAM instantly. Slower processing of fewer threads is necessary for stability on a small server.

---

## 3. Query Normalization Logic

Implement a helper function in your Python backend to standardize user input before hitting the database or crawlers.

```python
def normalize_query(q: str) -> str:
    q = q.lower().strip()
    # Remove common suffixes/prefixes so "love template qr" == "love vn template"
    removals = ["vn template", "template qr code", "template qr", "qr code", "template"]
    for r in removals:
        q = q.replace(r, "").strip()
    
    # Standardize to a single base format
    return f"{q} vn template".strip()
```

---

## 4. VPS Server Stabilization (Linux Swap)

Since the physical RAM is only 1GB, the OS will aggressively kill the Python process (OOM Killer) if Playwright spikes. Creating a Swap file uses your SSD as overflow RAM.

Run these commands via SSH on your VPS to create a 2GB swap file:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make it permanent across reboots
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
