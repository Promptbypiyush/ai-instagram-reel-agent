import os
import json
import time
import requests

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

MODEL = "gemini-3.8-flash"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Wikimedia को identify करने के लिए User-Agent जरूरी है
WIKIMEDIA_HEADERS = {
    "User-Agent": "PromptVerseIndia-ReelAgent/1.0 (GitHub Actions)"
}


def ask_ai():
    prompt = """
You are the content creator for PromptVerse India.

Create ONE short Instagram Reel idea about AI, AI tools,
AI prompts, AI photo editing or AI video tricks.

Return ONLY valid JSON in exactly this format:

{
  "topic": "short topic",
  "script": "short Hinglish reel script",
  "caption": "Instagram caption",
  "hashtags": "#AITools #AIHacks #PromptVerseIndia"
}

The script should be short, useful and engaging for Indian viewers.
Do not use markdown.
Do not put anything outside the JSON.
"""

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    for attempt in range(1, 6):
        print(f"Gemini request attempt {attempt}/5")

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=60
            )

            # Temporary Gemini errors
            if response.status_code in [429, 500, 502, 503, 504]:
                print(
                    f"Gemini temporary error: HTTP "
                    f"{response.status_code}"
                )

                if attempt < 5:
                    wait_time = attempt * 10
                    print(
                        f"Waiting {wait_time} seconds before retry..."
                    )
                    time.sleep(wait_time)
                    continue

            response.raise_for_status()

            data = response.json()

            text = data["candidates"][0]["content"]["parts"][0]["text"]

            # Remove possible markdown fences
            text = text.strip()

            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            result = json.loads(text)

            print("Gemini generated content successfully.")

            return result

        except json.JSONDecodeError as e:
            print(f"Gemini returned invalid JSON: {e}")

        except requests.RequestException as e:
            print(f"Gemini request error: {e}")

        except Exception as e:
            print(f"Gemini unexpected error: {e}")

        if attempt < 5:
            wait_time = attempt * 10
            print(
                f"Waiting {wait_time} seconds before retry..."
            )
            time.sleep(wait_time)

    raise RuntimeError("Gemini failed after 5 attempts.")


def find_video(search_text):
    print(f"Searching Wikimedia Commons for: {search_text}")

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": search_text,
        "gsrnamespace": 6,
        "gsrlimit": 20,
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata"
    }

    try:
        response = requests.get(
            COMMONS_API,
            params=params,
            headers=WIKIMEDIA_HEADERS,
            timeout=30
        )

        # 403 is NOT a temporary error.
        if response.status_code == 403:
            print(
                "Wikimedia returned HTTP 403 Forbidden."
            )
            print(
                "Skipping this Wikimedia search instead of retrying."
            )
            return None

        response.raise_for_status()

        data = response.json()

        pages = data.get("query", {}).get("pages", {})

        for page in pages.values():
            imageinfo = page.get("imageinfo", [])

            if not imageinfo:
                continue

            info = imageinfo[0]

            file_url = info.get("url")
            mime = info.get("mime", "").lower()

            if not file_url:
                continue

            # Only video files
            if mime.startswith("video/"):
                print(f"Found video: {file_url}")
                return file_url

            # Also allow common video extensions
            lower_url = file_url.lower()

            if (
                lower_url.endswith(".mp4")
                or lower_url.endswith(".webm")
                or lower_url.endswith(".ogv")
                or lower_url.endswith(".mov")
            ):
                print(f"Found video: {file_url}")
                return file_url

        print("No suitable Wikimedia video found.")
        return None

    except requests.RequestException as e:
        print(f"Wikimedia request failed: {e}")
        return None

    except Exception as e:
        print(f"Wikimedia unexpected error: {e}")
        return None


def download_video(video_url):
    print(f"Downloading video: {video_url}")

    try:
        response = requests.get(
            video_url,
            headers=WIKIMEDIA_HEADERS,
            stream=True,
            timeout=60
        )

        if response.status_code == 403:
            print("Wikimedia video download returned HTTP 403.")
            return False

        response.raise_for_status()

        with open("source.mp4", "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)

        print("Video downloaded successfully.")
        return True

    except requests.RequestException as e:
        print(f"Video download failed: {e}")
        return False

    except Exception as e:
        print(f"Unexpected download error: {e}")
        return False


def main():
    print("=" * 40)
    print("AI Reel Agent")
    print("=" * 40)

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY secret is missing."
        )

    # Step 1: Generate AI content
    content = ask_ai()

    print()
    print("TOPIC:", content.get("topic"))
    print("SCRIPT:", content.get("script"))
    print("CAPTION:", content.get("caption"))
    print("HASHTAGS:", content.get("hashtags"))
    print()

    # Save generated content
    with open("content.json", "w", encoding="utf-8") as file:
        json.dump(
            content,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("content.json created.")

    # Step 2: Search for a suitable video
    topic = content.get("topic", "technology")

    video = find_video(
        f"{topic} technology video"
    )

    if video:
        success = download_video(video)

        if not success:
            print(
                "Video download failed."
            )
    else:
        print(
            "No Wikimedia video found."
        )
        print(
            "AI content was still generated successfully."
        )

    print()
    print("=" * 40)
    print("AI Reel Agent finished.")
    print("=" * 40)


if __name__ == "__main__":
    main()
