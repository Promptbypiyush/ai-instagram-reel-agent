import os
import json
import random
import time
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MODEL = "gemini-3.8-flash"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"


def ask_ai():
    prompt = """
You are the content creator for PromptVerse India.

Create ONE short Instagram Reel idea about AI, AI tools,
AI prompts, AI photo editing or AI video tricks.

Return ONLY valid JSON:
{
  "topic": "...",
  "script": "...",
  "search_query": "...",
  "caption": "...",
  "hashtags": "..."
}

Rules:
- Script must be Hindi/Hinglish.
- 20-30 seconds.
- Simple and engaging.
- search_query must be a simple English video-search phrase.
"""

    url = (
        f"https://generativelanguage.googleapis.com/"
        f"v1beta/models/{MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    # Retry only temporary Gemini server/rate-limit errors.
    # Maximum 5 attempts.
    for attempt in range(1, 6):
        try:
            print(f"Gemini request attempt {attempt}/5")

            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code == 200:
                data = response.json()

                text = (
                    data["candidates"][0]
                    ["content"]["parts"][0]["text"]
                )

                return json.loads(text)

            if response.status_code in (429, 500, 502, 503, 504):
                print(
                    f"Gemini temporary error: "
                    f"HTTP {response.status_code}"
                )

                if attempt < 5:
                    wait_time = attempt * 10
                    print(
                        f"Waiting {wait_time} seconds "
                        f"before retry..."
                    )
                    time.sleep(wait_time)
                    continue

            response.raise_for_status()

        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError
        ) as e:
            print(f"Gemini connection error: {e}")

            if attempt < 5:
                wait_time = attempt * 10
                print(
                    f"Waiting {wait_time} seconds "
                    f"before retry..."
                )
                time.sleep(wait_time)
                continue

            raise

    raise Exception(
        "Gemini API failed after 5 attempts."
    )


def find_video(query):
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 20,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata"
    }

    response = requests.get(
        COMMONS_API,
        params=params,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    pages = data.get("query", {}).get("pages", {})

    videos = []

    for page in pages.values():
        info = page.get("imageinfo", [])

        if not info:
            continue

        file_info = info[0]
        mime = file_info.get("mime", "")

        if mime.startswith("video/"):
            videos.append({
                "title": page.get("title", ""),
                "url": file_info.get("url", ""),
                "description_url":
                    "https://commons.wikimedia.org/wiki/" +
                    page.get("title", "").replace(" ", "_")
            })

    if not videos:
        raise Exception(
            "No suitable Wikimedia Commons video found."
        )

    return random.choice(videos)


def download_video(video):
    url = video["url"]

    response = requests.get(
        url,
        timeout=180
    )

    response.raise_for_status()

    with open("source.mp4", "wb") as f:
        f.write(response.content)


def main():
    if not GEMINI_API_KEY:
        raise Exception(
            "GEMINI_API_KEY is missing."
        )

    content = ask_ai()

    print("TOPIC:", content["topic"])
    print("SCRIPT:", content["script"])
    print("CAPTION:", content["caption"])
    print("HASHTAGS:", content["hashtags"])

    with open(
        "content.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            content,
            f,
            ensure_ascii=False,
            indent=2
        )

    video = find_video(
        content["search_query"]
    )

    print("VIDEO:", video["title"])
    print("SOURCE:", video["description_url"])

    download_video(video)

    print("Video downloaded successfully.")


if __name__ == "__main__":
    main()
