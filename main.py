import json
import os
from pathlib import Path
from typing import List, Optional, Union

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from fastapi.openapi.utils import get_openapi

from controllers.decode_code import decode_code_controller
from controllers.scraper import search_templates_controller


# --- Secret loading ---------------------------------------------------------
# Keep this file on the server only. The client should only receive the x-key value.
ROOT_DIR = Path(__file__).resolve().parent
SECRET_FILE = ROOT_DIR / "secret.json"


def load_api_key() -> str:
    if not SECRET_FILE.exists():
        raise RuntimeError(f"Missing secret file: {SECRET_FILE}")

    with SECRET_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)

    api_key = data.get("apiKey")
    if not api_key or not isinstance(api_key, str):
        raise RuntimeError("secret.json must contain a string field named 'apiKey'")

    return api_key


EXPECTED_API_KEY = load_api_key()

# Reads the header named exactly: x-key
api_key_header = APIKeyHeader(name="x-key", auto_error=True)


async def verify_api_key(x_key: str = Security(api_key_header)):
    # Single gate for every request. Keeps auth logic in one place.
    if not x_key:
        raise HTTPException(status_code=401, detail="Missing x-key header")

    if x_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")


# --- App --------------------------------------------------------------------
app = FastAPI(
    title="VN QR Template API",
    description="Search and extract VN Video Editor templates using QR detection",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Author(BaseModel):
    name: Optional[str] = Field(None, example="Nehal Yadav")
    username: Optional[str] = Field(None, example="nehal__yaduvanshi")
    avatar: Optional[str] = Field(None, example="https://avatar-url.com/avatar.jpg")


class TemplateItem(BaseModel):
    template_id: Union[int, str] = Field(..., example=712014)
    qr_data: str = Field(..., example="VN://template?id=712014")
    title: Optional[str] = Field(None, example="Love Story")
    preview_image: Optional[str] = Field(None, example="https://image-url.com/image.jpg")
    preview_video: Optional[str] = Field(None, example="https://video-url.com/video.mp4")
    category: Optional[str] = Field(None, example="others")
    likes: Optional[int] = Field(None, example=1169)
    usage: Optional[int] = Field(None, example=178720)
    author: Optional[Author]
    page_url: Optional[str] = Field(None, example="https://youtube.com/watch?v=abc")
    qr_image: Optional[str] = Field(None, example="https://image-url.com/qr.jpg")


class SearchResponse(BaseModel):
    query: str = Field(..., example="love")
    limit: int = Field(..., example=100)
    total: int = Field(..., example=3)
    results: List[TemplateItem]


@app.get("/proxy-image", include_in_schema=False)
async def proxy_image(url: str = Query(...)):
    try:
        # Small timeout keeps the endpoint from hanging on bad upstream URLs.
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Failed to fetch image")

        content_type = resp.headers.get("content-type", "image/jpeg")

        return StreamingResponse(
            iter([resp.content]),
            media_type=content_type,
            headers={
                "Content-Disposition": "inline"
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", include_in_schema=False)
def home():
    # Optional landing page for local testing or simple deployment checks.
    index_path = ROOT_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))

    return JSONResponse(
        {
            "status": "running",
            "usage": "/search?query=love%20VN%20template",
        }
    )


@app.get(
    "/search",
    response_model=SearchResponse,
    summary="Search VN templates using QR extraction",
    description="""
Search VN Video Editor templates by scanning QR codes from images across multiple sources.

### Features:
- Extracts VN template QR codes from images
- Fetches full template metadata from VN API
- Supports multiple sources (DuckDuckGo, Pinterest, etc.)

### Returns:
- Template metadata (title, preview, usage, likes)
- Author info
- Source page URL
- QR image used for extraction
""",
    responses={
        200: {
            "description": "Successful template search",
            "content": {
                "application/json": {
                    "example": {
                        "query": "love",
                        "limit": 100,
                        "source": "all",
                        "total": 3,
                        "results": [
                            {
                                "template_id": 699546,
                                "qr_data": "VN://template?id=699546",
                                "title": "💗🧸🙈@vn_templates_codes",
                                "preview_image": "https://a.cf.vlognow.me/...jpg",
                                "preview_video": "https://a.cf.vlognow.me/...mp4",
                                "category": "others",
                                "likes": 323,
                                "usage": 63252,
                                "author": {
                                    "name": "editor_ram",
                                    "username": "editor_ram",
                                    "avatar": "https://avatar-url.com/avatar.jpg",
                                },
                                "page_url": "https://youtube.com/watch?v=GB2",
                                "source": "duck",
                                "qr_image": "https://ytimg.com/...jpg",
                            }
                        ],
                    }
                }
            },
        }
    }, 
    dependencies=[Depends(verify_api_key)]
)
def search(
    query: str = Query(..., example="love vn template"),
    limit: int = Query(100, ge=1, le=200),
):
    results = search_templates_controller(
        query,
        max_results=limit,
    )

    return {
        "query": query,
        "limit": limit,
        "total": len(results),
        "results": results,
    }


@app.get(
    "/decode",
    summary="Decode VN template from QR or ID",
    description="""
Decode VN template using:

- Full QR code → VN://template?id=xxxx
- OR template ID → 123456

Returns full template metadata from VN API.
""",
dependencies=[Depends(verify_api_key)]
)
def decode_code(
    code: str = Query(..., example="VN://template?id=699546")
):
    print(f"Received code to decode: '{code}'")
    return decode_code_controller(code)