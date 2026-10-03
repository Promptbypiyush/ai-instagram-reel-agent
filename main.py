import os
import json
import time
import shutil
import subprocess
import requests


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID")

# Facebook Login / Page based Instagram API:
INSTAGRAM_API_HOST = os.environ.get(
    "INSTAGRAM_API_HOST",
    "graph.facebook.com"
)

API_VERSION = "v25.0"

GEMINI_MODEL = "gemini-3.8-flash"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"

WIKIMEDIA_HEADERS = {
    "User-Agent": "PromptVerseIndia-ReelAgent/1.0 (GitHub Actions)"
}


# ============================================================
# 50 MB LIMIT
# ============================================================

MAX_VIDEO_BYTES = 50 * 1024 * 1024

# Keep a small safety margin so Instagram never receives
# a file right at the 50 MB boundary.
TARGET_MAX_BYTES = 49 * 1024 * 1024

MAX_REEL_SECONDS = 60
MIN_REEL_SECONDS = 3


# ============================================================
# HELPERS
# ============================================================

def run_command(command):
    print("Running:", " ".join(command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result.stdout


def check_ffmpeg():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed.")

    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is not installed.")

    print("ffmpeg:", shutil.which("ffmpeg"))
    print("ffprobe:", shutil.which("ffprobe"))


def get_video_duration(video_path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path
    ]

    output = run_command(command).strip()

    try:
        return float(output)
    except ValueError:
        raise RuntimeError(
            f"Could not determine video duration: {output}"
        )


# ============================================================
# GEMINI
# ============================================================

def ask_ai():

    prompt = """
You are the content creator for PromptVerse India.

Create ONE short Instagram Reel idea about:
AI, AI tools, AI prompts, AI photo editing,
AI video tricks, productivity with AI, or useful AI websites.

Return ONLY valid JSON.

Exactly this format:

{
  "topic": "short topic",
  "script": "short Hinglish reel script",
  "caption": "Instagram caption",
  "hashtags": "#AITools #AIHacks #PromptVerseIndia"
}

Rules:

- Script should be short.
- Use natural Indian Hinglish.
- Make it useful and engaging.
- Avoid fake claims.
- Avoid markdown.
- Do not put anything outside JSON.
"""

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY secret is missing."
        )

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    params = {
        "key": GEMINI_API_KEY
    }

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

        print(
            f"Gemini request attempt {attempt}/5"
        )

        try:

            response = requests.post(
                url,
                params=params,
                json=payload,
                timeout=90
            )

            if response.status_code in [
                429,
                500,
                502,
                503,
                504
            ]:

                print(
                    "Gemini temporary error:",
                    response.status_code
                )

                if attempt < 5:
                    wait_time = attempt * 10

                    print(
                        f"Waiting {wait_time} seconds..."
                    )

                    time.sleep(wait_time)

                    continue

            response.raise_for_status()

            data = response.json()

            text = (
                data["candidates"][0]
                ["content"]["parts"][0]["text"]
            )

            text = text.strip()

            # Remove markdown fences if Gemini adds them.
            if text.startswith("```"):

                text = text.replace(
                    "```json",
                    "",
                    1
                )

                text = text.replace(
                    "```",
                    ""
                )

                text = text.strip()

            result = json.loads(text)

            required = [
                "topic",
                "script",
                "caption",
                "hashtags"
            ]

            for key in required:

                if key not in result:
                    raise RuntimeError(
                        f"Gemini JSON missing: {key}"
                    )

            print(
                "Gemini generated content successfully."
            )

            return result

        except json.JSONDecodeError as error:

            print(
                "Gemini returned invalid JSON:",
                error
            )

        except requests.RequestException as error:

            print(
                "Gemini request error:",
                error
            )

        except Exception as error:

            print(
                "Gemini unexpected error:",
                error
            )

        if attempt < 5:

            wait_time = attempt * 10

            print(
                f"Retrying in {wait_time} seconds..."
            )

            time.sleep(wait_time)

    raise RuntimeError(
        "Gemini failed after 5 attempts."
    )


# ============================================================
# WIKIMEDIA SEARCH
# ============================================================

def find_video(search_text):

    print()
    print(
        f"Searching Wikimedia Commons for: {search_text}"
    )

    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": search_text,
        "gsrnamespace": 6,
        "gsrlimit": 30,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata"
    }

    try:

        response = requests.get(
            COMMONS_API,
            params=params,
            headers=WIKIMEDIA_HEADERS,
            timeout=30
        )

        if response.status_code == 403:

            print(
                "Wikimedia returned HTTP 403."
            )

            return None

        response.raise_for_status()

        data = response.json()

        pages = (
            data.get("query", {})
            .get("pages", {})
        )

        candidates = []

        for page in pages.values():

            imageinfo = page.get(
                "imageinfo",
                []
            )

            if not imageinfo:
                continue

            info = imageinfo[0]

            file_url = info.get("url")

            mime = (
                info.get("mime", "")
                .lower()
            )

            file_size = info.get(
                "size",
                0
            )

            if not file_url:
                continue

            # Only video MIME types.
            is_video = mime.startswith(
                "video/"
            )

            # Also allow common extensions.
            lower_url = file_url.lower()

            extension_video = (
                lower_url.endswith(".mp4")
                or lower_url.endswith(".webm")
                or lower_url.endswith(".ogv")
                or lower_url.endswith(".mov")
                or lower_url.endswith(".m4v")
            )

            if not (
                is_video or extension_video
            ):
                continue

            # IMPORTANT:
            # Do not select a source larger than 50 MB.
            if file_size > MAX_VIDEO_BYTES:

                print(
                    "Skipping video larger than 50 MB:",
                    round(
                        file_size / 1024 / 1024,
                        2
                    ),
                    "MB"
                )

                continue

            candidates.append(
                {
                    "url": file_url,
                    "size": file_size,
                    "mime": mime
                }
            )

        # Prefer the smaller video.
        candidates.sort(
            key=lambda item: item["size"]
        )

        if not candidates:

            print(
                "No suitable Wikimedia video "
                "under 50 MB found."
            )

            return None

        selected = candidates[0]

        print(
            "Selected video:",
            selected["url"]
        )

        print(
            "Source size:",
            round(
                selected["size"] / 1024 / 1024,
                2
            ),
            "MB"
        )

        return selected["url"]

    except requests.RequestException as error:

        print(
            "Wikimedia request failed:",
            error
        )

        return None

    except Exception as error:

        print(
            "Wikimedia unexpected error:",
            error
        )

        return None


# ============================================================
# DOWNLOAD SOURCE VIDEO
# ============================================================

def download_video(video_url):

    output_file = "source_video"

    print()
    print(
        "Downloading source video..."
    )

    try:

        response = requests.get(
            video_url,
            headers=WIKIMEDIA_HEADERS,
            stream=True,
            timeout=90
        )

        if response.status_code == 403:

            print(
                "Wikimedia video returned HTTP 403."
            )

            return None

        response.raise_for_status()

        content_length = response.headers.get(
            "Content-Length"
        )

        if content_length:

            try:

                expected_size = int(
                    content_length
                )

                if expected_size > MAX_VIDEO_BYTES:

                    print(
                        "Download cancelled because "
                        "source is over 50 MB."
                    )

                    return None

            except ValueError:
                pass

        with open(
            output_file,
            "wb"
        ) as file:

            downloaded = 0

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):

                if not chunk:
                    continue

                downloaded += len(chunk)

                # Safety limit.
                if downloaded > MAX_VIDEO_BYTES:

                    print(
                        "Download exceeded 50 MB."
                    )

                    file.close()

                    try:
                        os.remove(
                            output_file
                        )
                    except OSError:
                        pass

                    return None

                file.write(chunk)

                print(
                    f"Downloaded "
                    f"{downloaded / 1024 / 1024:.2f} MB"
                )

        if not os.path.exists(
            output_file
        ):
            return None

        final_size = os.path.getsize(
            output_file
        )

        if final_size == 0:
            return None

        print(
            "Source video downloaded:",
            round(
                final_size / 1024 / 1024,
                2
            ),
            "MB"
        )

        return output_file

    except requests.RequestException as error:

        print(
            "Video download failed:",
            error
        )

        return None

    except Exception as error:

        print(
            "Unexpected download error:",
            error
        )

        return None


# ============================================================
# CREATE INSTAGRAM-READY REEL
# ============================================================

def create_reel(source_file):

    print()
    print(
        "Creating Instagram Reel..."
    )

    duration = get_video_duration(
        source_file
    )

    print(
        "Source duration:",
        round(duration, 2),
        "seconds"
    )

    if duration < MIN_REEL_SECONDS:

        raise RuntimeError(
            "Source video is shorter than 3 seconds."
        )

    # Use up to 60 seconds.
    reel_duration = min(
        duration,
        MAX_REEL_SECONDS
    )

    output_file = "reel.mp4"

    # Start around 45 MB target.
    target_bytes = 45 * 1024 * 1024

    # Keep audio at 128 kbps.
    audio_bitrate = 128_000

    # Calculate approximate video bitrate.
    total_bitrate = (
        target_bytes * 8
    ) / reel_duration

    video_bitrate = int(
        total_bitrate - audio_bitrate
    )

    # Keep a sensible upper/lower range.
    video_bitrate = max(
        800_000,
        min(
            video_bitrate,
            8_000_000
        )
    )

    print(
        "Initial video bitrate:",
        round(
            video_bitrate / 1_000_000,
            2
        ),
        "Mbps"
    )

    # Try multiple times to guarantee <= 50 MB.
    for attempt in range(1, 5):

        print(
            f"Re-encoding attempt "
            f"{attempt}/4"
        )

        if os.path.exists(
            output_file
        ):

            os.remove(
                output_file
            )

        bitrate_k = max(
            600,
            int(
                video_bitrate / 1000
            )
        )

        command = [
            "ffmpeg",
            "-y",

            "-ss",
            "0",

            "-i",
            source_file,

            "-t",
            str(reel_duration),

            # Vertical 9:16.
            "-vf",
            (
                "scale=1080:1920:"
                "force_original_aspect_ratio=increase,"
                "crop=1080:1920"
            ),

            "-r",
            "30",

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-b:v",
            f"{bitrate_k}k",

            "-maxrate",
            f"{bitrate_k}k",

            "-bufsize",
            f"{bitrate_k * 2}k",

            "-pix_fmt",
            "yuv420p",

            "-profile:v",
            "high",

            "-level",
            "4.1",

            "-c:a",
            "aac",

            "-b:a",
            "128k",

            "-ar",
            "48000",

            "-ac",
            "2",

            # Put moov atom at beginning.
            "-movflags",
            "+faststart",

            output_file
        ]

        run_command(command)

        if not os.path.exists(
            output_file
        ):
            raise RuntimeError(
                "ffmpeg did not create reel.mp4"
            )

        output_size = os.path.getsize(
            output_file
        )

        output_mb = (
            output_size /
            1024 /
            1024
        )

        print(
            "Final Reel size:",
            round(output_mb, 2),
            "MB"
        )

        if output_size <= TARGET_MAX_BYTES:

            print(
                "Reel is safely under 50 MB."
            )

            return output_file

        # Reduce bitrate for next attempt.
        video_bitrate = int(
            video_bitrate * 0.72
        )

    raise RuntimeError(
        "Could not create a Reel under 50 MB."
    )


# ============================================================
# INSTAGRAM API
# ============================================================

def instagram_url(path):

    return (
        f"https://{INSTAGRAM_API_HOST}/"
        f"{API_VERSION}/{path}"
    )


def check_instagram_credentials():

    if not INSTAGRAM_ACCESS_TOKEN:

        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN secret is missing."
        )

    if not INSTAGRAM_USER_ID:

        raise RuntimeError(
            "INSTAGRAM_USER_ID secret is missing."
        )

    print(
        "Instagram credentials found."
    )


# ============================================================
# CREATE REEL CONTAINER
# ============================================================

def create_reel_container(
    caption
):

    print()
    print(
        "Creating Instagram Reel container..."
    )

    url = instagram_url(
        f"{INSTAGRAM_USER_ID}/media"
    )

    payload = {
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
        "share_to_feed": "true",
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.post(
        url,
        data=payload,
        timeout=60
    )

    if response.status_code != 200:

        print(
            "Instagram container error:",
            response.text
        )

        response.raise_for_status()

    data = response.json()

    container_id = data.get(
        "id"
    )

    upload_uri = data.get(
        "uri"
    )

    if not container_id:

        raise RuntimeError(
            f"Instagram did not return "
            f"a container ID: {data}"
        )

    print(
        "Instagram container:",
        container_id
    )

    if upload_uri:
        print(
            "Instagram returned upload URI."
        )

    return (
        container_id,
        upload_uri
    )


# ============================================================
# UPLOAD VIDEO TO INSTAGRAM
# ============================================================

def upload_video_to_instagram(
    video_file,
    container_id,
    upload_uri=None
):

    file_size = os.path.getsize(
        video_file
    )

    if file_size > MAX_VIDEO_BYTES:

        raise RuntimeError(
            "Final video is over 50 MB."
        )

    print()
    print(
        "Uploading Reel to Instagram..."
    )

    if upload_uri:

        upload_url = upload_uri

    else:

        upload_url = (
            "https://rupload.facebook.com/"
            f"ig-api-upload/{API_VERSION}/"
            f"{container_id}"
        )

    headers = {
        "Authorization":
            f"OAuth {INSTAGRAM_ACCESS_TOKEN}",

        "offset":
            "0",

        "file_size":
            str(file_size),

        "Content-Type":
            "video/mp4"
    }

    with open(
        video_file,
        "rb"
    ) as file:

        response = requests.post(
            upload_url,
            headers=headers,
            data=file,
            timeout=300
        )

    if response.status_code not in [
        200,
        201
    ]:

        print(
            "Instagram video upload error:",
            response.text
        )

        response.raise_for_status()

    print(
        "Video uploaded to Instagram successfully."
    )

    print(
        "Upload response:",
        response.text
    )


# ============================================================
# CHECK INSTAGRAM CONTAINER
# ============================================================

def wait_for_container(
    container_id
):

    print()
    print(
        "Waiting for Instagram to process Reel..."
    )

    url = instagram_url(
        container_id
    )

    params = {
        "fields":
            "status_code,status",
        "access_token":
            INSTAGRAM_ACCESS_TOKEN
    }

    # Up to 10 minutes.
    for attempt in range(1, 61):

        response = requests.get(
            url,
            params=params,
            timeout=60
        )

        if response.status_code != 200:

            print(
                "Status check error:",
                response.text
            )

            response.raise_for_status()

        data = response.json()

        status_code = data.get(
            "status_code"
        )

        status_text = data.get(
            "status",
            ""
        )

        print(
            f"Instagram status "
            f"{attempt}/60:",
            status_code,
            status_text
        )

        if status_code == "FINISHED":

            print(
                "Instagram Reel is ready to publish."
            )

            return True

        if status_code == "PUBLISHED":

            print(
                "Reel is already published."
            )

            return True

        if status_code in [
            "ERROR",
            "EXPIRED"
        ]:

            raise RuntimeError(
                "Instagram Reel processing failed: "
                f"{status_code} - {status_text}"
            )

        time.sleep(10)

    raise RuntimeError(
        "Instagram Reel processing timed out."
    )


# ============================================================
# PUBLISH REEL
# ============================================================

def publish_reel(
    container_id
):

    print()
    print(
        "Publishing Reel..."
    )

    url = instagram_url(
        f"{INSTAGRAM_USER_ID}/media_publish"
    )

    payload = {
        "creation_id":
            container_id,

        "access_token":
            INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.post(
        url,
        data=payload,
        timeout=90
    )

    if response.status_code != 200:

        print(
            "Instagram publish error:",
            response.text
        )

        response.raise_for_status()

    data = response.json()

    media_id = data.get(
        "id"
    )

    if not media_id:

        raise RuntimeError(
            f"Instagram did not return "
            f"media ID: {data}"
        )

    print()
    print(
        "========================================"
    )

    print(
        "REEL PUBLISHED SUCCESSFULLY"
    )

    print(
        "Instagram Media ID:",
        media_id
    )

    print(
        "========================================"
    )

    return media_id


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "========================================"
    )

    print(
        "PromptVerse India - Daily AI Reel Agent"
    )

    print(
        "========================================"
    )

    check_ffmpeg()

    check_instagram_credentials()

    # --------------------------------------------------------
    # 1. Generate AI content
    # --------------------------------------------------------

    content = ask_ai()

    print()
    print(
        "TOPIC:",
        content["topic"]
    )

    print(
        "SCRIPT:",
        content["script"]
    )

    print(
        "CAPTION:",
        content["caption"]
    )

    print(
        "HASHTAGS:",
        content["hashtags"]
    )

    # --------------------------------------------------------
    # 2. Save AI content
    # --------------------------------------------------------

    with open(
        "content.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            content,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        "content.json created."
    )

    # --------------------------------------------------------
    # 3. Search Wikimedia
    # --------------------------------------------------------

    topic = content.get(
        "topic",
        "technology"
    )

    video_url = find_video(
        f"{topic} technology video"
    )

    if not video_url:

        raise RuntimeError(
            "No suitable Wikimedia video "
            "under 50 MB was found."
        )

    # --------------------------------------------------------
    # 4. Download source
    # --------------------------------------------------------

    source_file = download_video(
        video_url
    )

    if not source_file:

        raise RuntimeError(
            "Could not download source video."
        )

    # --------------------------------------------------------
    # 5. Create final Reel
    # --------------------------------------------------------

    reel_file = create_reel(
        source_file
    )

    # --------------------------------------------------------
    # 6. Final 50 MB safety check
    # --------------------------------------------------------

    final_size = os.path.getsize(
        reel_file
    )

    print(
        "Final Reel:",
        round(
            final_size / 1024 / 1024,
            2
        ),
        "MB"
    )

    if final_size > MAX_VIDEO_BYTES:

        raise RuntimeError(
            "SAFETY STOP: Reel is above 50 MB."
        )

    # --------------------------------------------------------
    # 7. Caption
    # --------------------------------------------------------

    caption = (
        content["caption"].strip()
        + "\n\n"
        + content["hashtags"].strip()
    )

    # --------------------------------------------------------
    # 8. Create Instagram container
    # --------------------------------------------------------

    (
        container_id,
        upload_uri
    ) = create_reel_container(
        caption
    )

    # --------------------------------------------------------
    # 9. Upload video
    # --------------------------------------------------------

    upload_video_to_instagram(
        reel_file,
        container_id,
        upload_uri
    )

    # --------------------------------------------------------
    # 10. Wait for processing
    # --------------------------------------------------------

    wait_for_container(
        container_id
    )

    # --------------------------------------------------------
    # 11. Publish
    # --------------------------------------------------------

    publish_reel(
        container_id
    )

    print()
    print(
        "Daily AI Reel automation completed."
    )


if __name__ == "__main__":

    main()
