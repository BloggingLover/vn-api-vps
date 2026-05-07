# VN Template API
This is a FAST Python-based API that you can use to get VN Video Editor templates either by 
Template UUID or a search term to search relevant templates.

# How to get started?
1. Run `pip install -r requirements.txt` in the root directory.
2. Run `uvicorn main:app --reload --log-level debug` (remove `debug` if you don't want to see logs) 
3. Access the API at `http://localhost:8000`.

# Authentication
All API endpoints require an API key to be sent in the request headers.

<pre>
Header Format
x-key: YOUR_API_KEY
Example (cURL)
curl -X GET "http://localhost:8000/search?query=love" \
  -H "x-key: YOUR_API_KEY"
Example (Python)
import requests

url = "http://localhost:8000/search"
headers = {
    "x-key": "YOUR_API_KEY"
}
params = {
    "query": "love"
}

response = requests.get(url, headers=headers, params=params)
print(response.json())
</pre>

# How API Keys Work
Each request must include a valid API key in the x-key header
Requests without a key → 401 Unauthorized
Invalid key → 403 Forbidden

# Setting Your API Key (Server Side)
Create a file named secret.json in the root directory:
<pre>
{
  "apiKey": "your_super_secret_key_here"
}
</pre>
⚠️ Do NOT expose this file publicly or commit it to GitHub.

# API Routes

1. Search Templates by Query
You can use this endpoint `/search?query={search_term}` to search by a specific query, e.g: "love".
2. Search a Template by Template UUID
If you have a decoded QR code, you can use the `Template UUID` and pass it here `/decode?uuid={template_id}` to etailed information for a specific template using its UUID.

# Deployment

The current API version is deployed on a Ubunto-based VPS and stored at location `/root/vn_template_api`.
Copy this code manually or through Github and replace the current code in `vn_template_api` directory. Stop the
current process on screen `api` using the following commands:
1. Enter `screen -D -r api` to get into the current running `api` screen.
2. `CTRL(CMD on Mac) + C` to stop the server.
3. `uvicorn main:app --host 0.0.0.0 --port 8000` to start the API with the new code.



