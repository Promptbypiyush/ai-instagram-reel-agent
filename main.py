import os
import json
import random
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

MODEL = "gemini-3.8-flash"

def ask_ai():
    prompt = """
You are the content creator for PromptVerse India.

Create ONE short Instagram Reel idea about AI, AI tools, AI prompts,
AI photo editing or AI video tricks.

Return ONLY valid JSON:
{
  "topic": "...",
  "script": "...",
  "search_query": "...",
  "caption": "...",
  "hashtags": "..."
}

The script should be Hindi/Hinglish, interesting and suitable for a
20-30 second Reel.
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

    response = requests.post(
        url,
        params={"key": GEMINI_API_KEY},
        json={
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
        },
        timeout=60
    )

    response.raise_for_status()

    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]

    return json.loads(text)


def find_video(query):
    url = "https://api.pexels.com/v1/videos/search"

    headers = {
        "Authorization": PEXELS_API_KEY
    }

    params = {
        "query": query,
        "orientation": "portrait",
        "size": "medium",
        "per_page": 10
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=60
    )

    response.raise_for_status()

    videos = response.json().get("videos", [])

    if not videos:
        raise Exception("No Pexels video found.")

    return random.choice(videos)


def download_video(video):
    files = video.get("video_files", [])

    portrait_files = [
        f for f in files
        if f.get("width", 0) > 0 and f.get("height", 0) > f.get("width", 0)
    ]

    if not portrait_files:
        portrait_files = files

    file = max(
        portrait_files,
        key=lambda x: x.get("width", 0) * x.get("height", 0)
    )

    url = file["link"]

    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with open("source.mp4", "wb") as f:
        f.write(response.content)


def main():
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY is missing.")

    if not PEXELS_API_KEY:
        raise Exception("PEXELS_API_KEY is missing.")

    content = ask_ai()

    print("TOPIC:", content["topic"])
    print("SCRIPT:", content["script"])
    print("CAPTION:", content["caption"])

    with open("content.json", "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

    video = find_video(content["search_query"])

    print("Pexels video:", video["url"])

    download_video(video)

    print("Video downloaded successfully.")


if __name__ == "__main__":
    main()
