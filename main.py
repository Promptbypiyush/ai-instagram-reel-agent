import os
import json
import time
import shutil
import subprocess
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID")

INSTAGRAM_API_HOST = os.environ.get(
    "INSTAGRAM_API_HOST",
    "graph.facebook.com"
)

API_VERSION = os.environ.get(
    "META_API_VERSION",
    "v25.0"
)

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

MAX_VIDEO_BYTES = 50 * 1024 * 1024
REEL_SECONDS = 15
POLL_SECONDS = 15
MAX_POLL_ATTEMPTS = 40

OUTPUT_VIDEO = "reel.mp4"
WORK_DIR = Path("reel_assets")


# ============================================================
# BASIC HELPERS
# ============================================================

def run_command(command):
    print()
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
            "Command failed with exit code "
            + str(result.returncode)
        )

    return result.stdout


def check_dependencies():
    print()
    print("Checking dependencies...")

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed.")

    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is not installed.")

    print("ffmpeg:", shutil.which("ffmpeg"))
    print("ffprobe:", shutil.which("ffprobe"))


def cleanup_files():
    output_path = Path(OUTPUT_VIDEO)

    if output_path.exists():
        try:
            output_path.unlink()
        except OSError:
            pass

    if WORK_DIR.exists():
        try:
            shutil.rmtree(WORK_DIR)
        except OSError:
            pass

    WORK_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# GEMINI AI
# ============================================================

def ask_ai():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is missing.")

    prompt = """
You are the content creator for PromptVerse India.

Create ONE useful Instagram Reel about:
AI, AI tools, AI prompts, AI photo editing,
AI video tricks, productivity with AI,
or useful AI websites.

Return ONLY valid JSON.

Use exactly this structure:

{
  "topic": "short topic",
  "script": "short Roman Hinglish reel script",
  "caption": "Instagram caption",
  "hashtags": "#AITools #AIHacks #PromptVerseIndia"
}

Rules:
- Use Roman Hinglish only.
- Do not use Devanagari Hindi.
- Keep the script short enough for a 15 second Reel.
- Make it useful and engaging.
- Keep it suitable for Indian viewers.
- Avoid fake claims.
- Do not use markdown.
- Do not put anything outside JSON.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        + GEMINI_MODEL
        + ":generateContent"
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

    params = {"key": GEMINI_API_KEY}

    for attempt in range(1, 6):
        print()
        print("Gemini request attempt " + str(attempt) + "/5")

        try:
            response = requests.post(
                url,
                params=params,
                json=payload,
                timeout=90
            )

            if response.status_code in [429, 500, 502, 503, 504]:
                print(
                    "Temporary Gemini error:",
                    response.status_code
                )

                if attempt < 5:
                    wait_time = attempt * 10
                    print(
                        "Waiting " + str(wait_time) + " seconds..."
                    )
                    time.sleep(wait_time)
                    continue

            response.raise_for_status()

            data = response.json()

            text = (
                data["candidates"][0]
                ["content"]["parts"][0]["text"]
            ).strip()

            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            result = json.loads(text)

            required_keys = [
                "topic",
                "script",
                "caption",
                "hashtags"
            ]

            for key in required_keys:
                if not result.get(key):
                    raise RuntimeError(
                        "Gemini JSON missing: " + key
                    )

            print()
            print("AI Topic:", result["topic"])
            print("AI Script:", result["script"])
            print("Gemini content generated successfully.")

            return result

        except json.JSONDecodeError as error:
            print("Gemini JSON error:", error)

        except requests.RequestException as error:
            print("Gemini request error:", error)

        except Exception as error:
            print("Gemini error:", error)

        if attempt < 5:
            wait_time = attempt * 10
            print(
                "Retrying in " + str(wait_time) + " seconds..."
            )
            time.sleep(wait_time)

    raise RuntimeError("Gemini failed after 5 attempts.")


# ============================================================
# FONT
# ============================================================

def find_font(size, bold=False):
    if bold:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ]
    else:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


# ============================================================
# VISUAL HELPERS
# ============================================================

def make_gradient(width, height, top_color, bottom_color):
    image = Image.new("RGB", (width, height))
    pixels = image.load()

    for y in range(height):
        ratio = y / max(1, height - 1)

        red = int(
            top_color[0] * (1 - ratio)
            + bottom_color[0] * ratio
        )
        green = int(
            top_color[1] * (1 - ratio)
            + bottom_color[1] * ratio
        )
        blue = int(
            top_color[2] * (1 - ratio)
            + bottom_color[2] * ratio
        )

        current_color = (red, green, blue)

        for x in range(width):
            pixels[x, y] = current_color

    return image


def draw_centered_text(
    draw,
    text,
    font,
    width,
    top_y,
    max_chars,
    fill
):
    lines = textwrap.wrap(
        str(text),
        width=max_chars
    )

    line_height = int(font.size * 1.25)
    current_y = top_y

    for line in lines:
        box = draw.textbbox(
            (0, 0),
            line,
            font=font
        )

        text_width = box[2] - box[0]
        x = (width - text_width) // 2

        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
            stroke_width=2,
            stroke_fill=(0, 0, 0)
        )

        current_y += line_height

    return current_y


# ============================================================
# CREATE ORIGINAL VISUALS
# ============================================================

def create_visual_frames(content):
    print()
    print("Creating original Reel visuals...")

    width = 1080
    height = 1920

    topic = str(content["topic"]).strip()
    script = str(content["script"]).strip()
    hashtags = str(content["hashtags"]).strip()

    title_font = find_font(78, True)
    script_font = find_font(52, True)
    subtitle_font = find_font(46, False)
    small_font = find_font(36, False)

    frames = []

    # FRAME 1
    image = make_gradient(
        width,
        height,
        (12, 18, 45),
        (70, 25, 100)
    )

    draw = ImageDraw.Draw(image)

    draw.ellipse(
        (-180, -180, 360, 360),
        fill=(70, 70, 170)
    )

    draw.ellipse(
        (800, 1450, 1250, 1900),
        fill=(30, 120, 170)
    )

    draw.text(
        (55, 90),
        "PROMPTVERSE INDIA",
        font=small_font,
        fill=(240, 240, 240)
    )

    draw_centered_text(
        draw,
        topic,
        title_font,
        width,
        500,
        18,
        (255, 255, 255)
    )

    draw_centered_text(
        draw,
        "AI TIP OF THE DAY",
        subtitle_font,
        width,
        1080,
        28,
        (220, 230, 255)
    )

    frame1 = WORK_DIR / "frame1.png"
    image.save(frame1)
    frames.append(frame1)

    # FRAME 2
    image = make_gradient(
        width,
        height,
        (15, 40, 50),
        (10, 90, 90)
    )

    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (55, 280, 1025, 1660),
        radius=45,
        fill=(8, 20, 25)
    )

    draw.text(
        (90, 360),
        "TRY THIS",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw_centered_text(
        draw,
        script,
        script_font,
        900,
        590,
        22,
        (255, 255, 255)
    )

    draw.text(
        (90, 1500),
        "Follow @promptverseindia",
        font=small_font,
        fill=(200, 240, 240)
    )

    frame2 = WORK_DIR / "frame2.png"
    image.save(frame2)
    frames.append(frame2)

    # FRAME 3
    image = make_gradient(
        width,
        height,
        (45, 18, 15),
        (105, 35, 60)
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 100),
        "SAVE THIS REEL",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw_centered_text(
        draw,
        hashtags,
        subtitle_font,
        width,
        650,
        26,
        (255, 235, 235)
    )

    draw_centered_text(
        draw,
        "More AI tips daily",
        title_font,
        width,
        1150,
        18,
        (255, 255, 255)
    )

    frame3 = WORK_DIR / "frame3.png"
    image.save(frame3)
    frames.append(frame3)

    print("Created 3 visual frames.")

    return frames


# ============================================================
# CREATE MP4
# ============================================================

def create_reel(frame_paths):
    print()
    print("Creating final Instagram Reel...")

    if len(frame_paths) != 3:
        raise RuntimeError("Expected exactly 3 frames.")

    frame1 = str(frame_paths[0])
    frame2 = str(frame_paths[1])
    frame3 = str(frame_paths[2])

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v0];"

        "[1:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v1];"

        "[2:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v2];"

        "[v0][v1][v2]"
        "concat=n=3:v=1:a=0,"
        "format=yuv420p[outv]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop", "1",
        "-t", "5",
        "-i", frame1,

        "-loop", "1",
        "-t", "5",
        "-i", frame2,

        "-loop", "1",
        "-t", "5",
        "-i", frame3,

        "-f", "lavfi",
        "-t", str(REEL_SECONDS),
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",

        "-filter_complex",
        filter_complex,

        "-map", "[outv]",
        "-map", "3:a",

        "-r", "30",

        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "2200k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",

        "-c:a", "aac",
        "-b:a", "96k",

        "-pix_fmt", "yuv420p",
        "-t", str(REEL_SECONDS),
        "-movflags", "+faststart",

        OUTPUT_VIDEO
    ]

    run_command(command)

    if not os.path.exists(OUTPUT_VIDEO):
        raise RuntimeError(
            "FFmpeg did not create reel.mp4."
        )

    file_size = os.path.getsize(OUTPUT_VIDEO)
    file_mb = file_size / 1024 / 1024

    print()
    print("Final Reel size:", round(file_mb, 2), "MB")

    if file_size > MAX_VIDEO_BYTES:
        raise RuntimeError(
            "Final Reel is over 50 MB."
        )

    print("Reel is safely under 50 MB.")

    return OUTPUT_VIDEO


# ============================================================
# INSTAGRAM API
# ============================================================

def instagram_url(path):
    return (
        "https://"
        + INSTAGRAM_API_HOST
        + "/"
        + API_VERSION
        + "/"
        + str(path)
    )


def check_instagram_credentials():
    print()
    print("Checking Instagram credentials...")

    if not INSTAGRAM_ACCESS_TOKEN:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN secret is missing."
        )

    if not INSTAGRAM_USER_ID:
        raise RuntimeError(
            "INSTAGRAM_USER_ID secret is missing."
        )

    if not str(INSTAGRAM_USER_ID).isdigit():
        raise RuntimeError(
            "INSTAGRAM_USER_ID must be the numeric Instagram User ID."
        )

    print("Instagram credentials found.")
    print("Instagram User ID:", INSTAGRAM_USER_ID)


def verify_instagram_user():
    print()
    print("Verifying Instagram User ID...")

    url = instagram_url(INSTAGRAM_USER_ID)

    params = {
        "fields": "id,username",
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.get(
        url,
        params=params,
        timeout=60
    )

    if response.status_code != 200:
        print("Instagram verification failed:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    returned_id = str(data.get("id", ""))
    username = data.get("username")

    print("Instagram User ID:", returned_id)
    print("Instagram username:", username)

    if returned_id != str(INSTAGRAM_USER_ID):
        raise RuntimeError(
            "Instagram returned a different User ID."
        )

    return data


# ============================================================
# CREATE REEL CONTAINER
# ============================================================

def create_reel_container(caption):
    print()
    print("Creating Instagram Reel container...")

    url = instagram_url(
        INSTAGRAM_USER_ID + "/media"
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

    if response.status_code not in [200, 201]:
        print("Instagram container error:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    container_id = data.get("id")
    upload_uri = data.get("uri")

    if not container_id:
        raise RuntimeError(
            "Instagram did not return a container ID: "
            + str(data)
        )

    print("Instagram container:", container_id)

    if upload_uri:
        print("Instagram upload URI received.")

    return container_id, upload_uri


# ============================================================
# UPLOAD VIDEO
# ============================================================

def upload_video_to_instagram(
    video_file,
    container_id,
    upload_uri=None
):
    file_size = os.path.getsize(video_file)

    if file_size > MAX_VIDEO_BYTES:
        raise RuntimeError(
            "Final video is over 50 MB."
        )

    print()
    print("Uploading Reel to Instagram...")

    if upload_uri:
        upload_url = upload_uri
    else:
        upload_url = (
            "https://rupload.facebook.com/"
            "ig-api-upload/"
            + API_VERSION
            + "/"
            + str(container_id)
        )

    headers = {
        "Authorization": (
            "OAuth " + INSTAGRAM_ACCESS_TOKEN
        ),
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "video/mp4"
    }

    with open(video_file, "rb") as video:
        response = requests.post(
            upload_url,
            headers=headers,
            data=video,
            timeout=300
        )

    if response.status_code not in [200, 201]:
        print("Instagram upload error:")
        print(response.text)
        response.raise_for_status()

    print("Video upload completed.")
    return True


# ============================================================
# WAIT FOR INSTAGRAM CONTAINER
# ============================================================

def wait_for_container(container_id):
    print()
    print("Waiting for Instagram to process the Reel...")

    url = instagram_url(container_id)

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        params = {
            "fields": "status_code,status",
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }

        response = requests.get(
            url,
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            print("Container status error:")
            print(response.text)
            response.raise_for_status()

        data = response.json()

        status_code = data.get("status_code")
        status = data.get("status")

        print(
            "Processing check "
            + str(attempt)
            + "/"
            + str(MAX_POLL_ATTEMPTS)
            + ":",
            status_code,
            status
        )

        if status_code == "FINISHED":
            print("Instagram Reel processing finished.")
            return True

        if status_code in ["ERROR", "EXPIRED"]:
            raise RuntimeError(
                "Instagram Reel processing failed: "
                + str(data)
            )

        time.sleep(POLL_SECONDS)

    raise RuntimeError(
        "Instagram Reel processing timed out."
    )


# ============================================================
# PUBLISH REEL
# ============================================================

def publish_reel(container_id):
    print()
    print("Publishing Reel to Instagram...")

    url = instagram_url(
        INSTAGRAM_USER_ID + "/media_publish"
    )

    payload = {
        "creation_id": container_id,
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.post(
        url,
        data=payload,
        timeout=60
    )

    if response.status_code not in [200, 201]:
        print("Instagram publish error:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    media_id = data.get("id")

    if not media_id:
        raise RuntimeError(
            "Instagram did not return published media ID: "
            + str(data)
        )

    print()
    print("============================================")
    print("REEL PUBLISHED SUCCESSFULLY")
    print("Instagram Media ID:", media_id)
    print("============================================")

    return media_id


# ============================================================
# MAIN
# =======================import os
import json
import time
import shutil
import subprocess
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID")

INSTAGRAM_API_HOST = os.environ.get(
    "INSTAGRAM_API_HOST",
    "graph.facebook.com"
)

API_VERSION = os.environ.get(
    "META_API_VERSION",
    "v25.0"
)

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

MAX_VIDEO_BYTES = 50 * 1024 * 1024
REEL_SECONDS = 15
POLL_SECONDS = 15
MAX_POLL_ATTEMPTS = 40

OUTPUT_VIDEO = "reel.mp4"
WORK_DIR = Path("reel_assets")


# ============================================================
# BASIC HELPERS
# ============================================================

def run_command(command):
    print()
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
            "Command failed with exit code "
            + str(result.returncode)
        )

    return result.stdout


def check_dependencies():
    print()
    print("Checking dependencies...")

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed.")

    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is not installed.")

    print("ffmpeg:", shutil.which("ffmpeg"))
    print("ffprobe:", shutil.which("ffprobe"))


def cleanup_files():
    output_path = Path(OUTPUT_VIDEO)

    if output_path.exists():
        try:
            output_path.unlink()
        except OSError:
            pass

    if WORK_DIR.exists():
        try:
            shutil.rmtree(WORK_DIR)
        except OSError:
            pass

    WORK_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# GEMINI AI
# ============================================================

def ask_ai():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is missing.")

    prompt = """
You are the content creator for PromptVerse India.

Create ONE useful Instagram Reel about:
AI, AI tools, AI prompts, AI photo editing,
AI video tricks, productivity with AI,
or useful AI websites.

Return ONLY valid JSON.

Use exactly this structure:

{
  "topic": "short topic",
  "script": "short Roman Hinglish reel script",
  "caption": "Instagram caption",
  "hashtags": "#AITools #AIHacks #PromptVerseIndia"
}

Rules:
- Use Roman Hinglish only.
- Do not use Devanagari Hindi.
- Keep the script short enough for a 15 second Reel.
- Make it useful and engaging.
- Keep it suitable for Indian viewers.
- Avoid fake claims.
- Do not use markdown.
- Do not put anything outside JSON.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        + GEMINI_MODEL
        + ":generateContent"
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

    params = {"key": GEMINI_API_KEY}

    for attempt in range(1, 6):
        print()
        print("Gemini request attempt " + str(attempt) + "/5")

        try:
            response = requests.post(
                url,
                params=params,
                json=payload,
                timeout=90
            )

            if response.status_code in [429, 500, 502, 503, 504]:
                print(
                    "Temporary Gemini error:",
                    response.status_code
                )

                if attempt < 5:
                    wait_time = attempt * 10
                    print(
                        "Waiting " + str(wait_time) + " seconds..."
                    )
                    time.sleep(wait_time)
                    continue

            response.raise_for_status()

            data = response.json()

            text = (
                data["candidates"][0]
                ["content"]["parts"][0]["text"]
            ).strip()

            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            result = json.loads(text)

            required_keys = [
                "topic",
                "script",
                "caption",
                "hashtags"
            ]

            for key in required_keys:
                if not result.get(key):
                    raise RuntimeError(
                        "Gemini JSON missing: " + key
                    )

            print()
            print("AI Topic:", result["topic"])
            print("AI Script:", result["script"])
            print("Gemini content generated successfully.")

            return result

        except json.JSONDecodeError as error:
            print("Gemini JSON error:", error)

        except requests.RequestException as error:
            print("Gemini request error:", error)

        except Exception as error:
            print("Gemini error:", error)

        if attempt < 5:
            wait_time = attempt * 10
            print(
                "Retrying in " + str(wait_time) + " seconds..."
            )
            time.sleep(wait_time)

    raise RuntimeError("Gemini failed after 5 attempts.")


# ============================================================
# FONT
# ============================================================

def find_font(size, bold=False):
    if bold:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ]
    else:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


# ============================================================
# VISUAL HELPERS
# ============================================================

def make_gradient(width, height, top_color, bottom_color):
    image = Image.new("RGB", (width, height))
    pixels = image.load()

    for y in range(height):
        ratio = y / max(1, height - 1)

        red = int(
            top_color[0] * (1 - ratio)
            + bottom_color[0] * ratio
        )
        green = int(
            top_color[1] * (1 - ratio)
            + bottom_color[1] * ratio
        )
        blue = int(
            top_color[2] * (1 - ratio)
            + bottom_color[2] * ratio
        )

        current_color = (red, green, blue)

        for x in range(width):
            pixels[x, y] = current_color

    return image


def draw_centered_text(
    draw,
    text,
    font,
    width,
    top_y,
    max_chars,
    fill
):
    lines = textwrap.wrap(
        str(text),
        width=max_chars
    )

    line_height = int(font.size * 1.25)
    current_y = top_y

    for line in lines:
        box = draw.textbbox(
            (0, 0),
            line,
            font=font
        )

        text_width = box[2] - box[0]
        x = (width - text_width) // 2

        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
            stroke_width=2,
            stroke_fill=(0, 0, 0)
        )

        current_y += line_height

    return current_y


# ============================================================
# CREATE ORIGINAL VISUALS
# ============================================================

def create_visual_frames(content):
    print()
    print("Creating original Reel visuals...")

    width = 1080
    height = 1920

    topic = str(content["topic"]).strip()
    script = str(content["script"]).strip()
    hashtags = str(content["hashtags"]).strip()

    title_font = find_font(78, True)
    script_font = find_font(52, True)
    subtitle_font = find_font(46, False)
    small_font = find_font(36, False)

    frames = []

    # FRAME 1
    image = make_gradient(
        width,
        height,
        (12, 18, 45),
        (70, 25, 100)
    )

    draw = ImageDraw.Draw(image)

    draw.ellipse(
        (-180, -180, 360, 360),
        fill=(70, 70, 170)
    )

    draw.ellipse(
        (800, 1450, 1250, 1900),
        fill=(30, 120, 170)
    )

    draw.text(
        (55, 90),
        "PROMPTVERSE INDIA",
        font=small_font,
        fill=(240, 240, 240)
    )

    draw_centered_text(
        draw,
        topic,
        title_font,
        width,
        500,
        18,
        (255, 255, 255)
    )

    draw_centered_text(
        draw,
        "AI TIP OF THE DAY",
        subtitle_font,
        width,
        1080,
        28,
        (220, 230, 255)
    )

    frame1 = WORK_DIR / "frame1.png"
    image.save(frame1)
    frames.append(frame1)

    # FRAME 2
    image = make_gradient(
        width,
        height,
        (15, 40, 50),
        (10, 90, 90)
    )

    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (55, 280, 1025, 1660),
        radius=45,
        fill=(8, 20, 25)
    )

    draw.text(
        (90, 360),
        "TRY THIS",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw_centered_text(
        draw,
        script,
        script_font,
        900,
        590,
        22,
        (255, 255, 255)
    )

    draw.text(
        (90, 1500),
        "Follow @promptverseindia",
        font=small_font,
        fill=(200, 240, 240)
    )

    frame2 = WORK_DIR / "frame2.png"
    image.save(frame2)
    frames.append(frame2)

    # FRAME 3
    image = make_gradient(
        width,
        height,
        (45, 18, 15),
        (105, 35, 60)
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 100),
        "SAVE THIS REEL",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw_centered_text(
        draw,
        hashtags,
        subtitle_font,
        width,
        650,
        26,
        (255, 235, 235)
    )

    draw_centered_text(
        draw,
        "More AI tips daily",
        title_font,
        width,
        1150,
        18,
        (255, 255, 255)
    )

    frame3 = WORK_DIR / "frame3.png"
    image.save(frame3)
    frames.append(frame3)

    print("Created 3 visual frames.")

    return frames


# ============================================================
# CREATE MP4
# ============================================================

def create_reel(frame_paths):
    print()
    print("Creating final Instagram Reel...")

    if len(frame_paths) != 3:
        raise RuntimeError("Expected exactly 3 frames.")

    frame1 = str(frame_paths[0])
    frame2 = str(frame_paths[1])
    frame3 = str(frame_paths[2])

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v0];"

        "[1:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v1];"

        "[2:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v2];"

        "[v0][v1][v2]"
        "concat=n=3:v=1:a=0,"
        "format=yuv420p[outv]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop", "1",
        "-t", "5",
        "-i", frame1,

        "-loop", "1",
        "-t", "5",
        "-i", frame2,

        "-loop", "1",
        "-t", "5",
        "-i", frame3,

        "-f", "lavfi",
        "-t", str(REEL_SECONDS),
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",

        "-filter_complex",
        filter_complex,

        "-map", "[outv]",
        "-map", "3:a",

        "-r", "30",

        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "2200k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",

        "-c:a", "aac",
        "-b:a", "96k",

        "-pix_fmt", "yuv420p",
        "-t", str(REEL_SECONDS),
        "-movflags", "+faststart",

        OUTPUT_VIDEO
    ]

    run_command(command)

    if not os.path.exists(OUTPUT_VIDEO):
        raise RuntimeError(
            "FFmpeg did not create reel.mp4."
        )

    file_size = os.path.getsize(OUTPUT_VIDEO)
    file_mb = file_size / 1024 / 1024

    print()
    print("Final Reel size:", round(file_mb, 2), "MB")

    if file_size > MAX_VIDEO_BYTES:
        raise RuntimeError(
            "Final Reel is over 50 MB."
        )

    print("Reel is safely under 50 MB.")

    return OUTPUT_VIDEO


# ============================================================
# INSTAGRAM API
# ============================================================

def instagram_url(path):
    return (
        "https://"
        + INSTAGRAM_API_HOST
        + "/"
        + API_VERSION
        + "/"
        + str(path)
    )


def check_instagram_credentials():
    print()
    print("Checking Instagram credentials...")

    if not INSTAGRAM_ACCESS_TOKEN:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN secret is missing."
        )

    if not INSTAGRAM_USER_ID:
        raise RuntimeError(
            "INSTAGRAM_USER_ID secret is missing."
        )

    if not str(INSTAGRAM_USER_ID).isdigit():
        raise RuntimeError(
            "INSTAGRAM_USER_ID must be the numeric Instagram User ID."
        )

    print("Instagram credentials found.")
    print("Instagram User ID:", INSTAGRAM_USER_ID)


def verify_instagram_user():
    print()
    print("Verifying Instagram User ID...")

    url = instagram_url(INSTAGRAM_USER_ID)

    params = {
        "fields": "id,username",
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.get(
        url,
        params=params,
        timeout=60
    )

    if response.status_code != 200:
        print("Instagram verification failed:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    returned_id = str(data.get("id", ""))
    username = data.get("username")

    print("Instagram User ID:", returned_id)
    print("Instagram username:", username)

    if returned_id != str(INSTAGRAM_USER_ID):
        raise RuntimeError(
            "Instagram returned a different User ID."
        )

    return data


# ============================================================
# CREATE REEL CONTAINER
# ============================================================

def create_reel_container(caption):
    print()
    print("Creating Instagram Reel container...")

    url = instagram_url(
        INSTAGRAM_USER_ID + "/media"
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

    if response.status_code not in [200, 201]:
        print("Instagram container error:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    container_id = data.get("id")
    upload_uri = data.get("uri")

    if not container_id:
        raise RuntimeError(
            "Instagram did not return a container ID: "
            + str(data)
        )

    print("Instagram container:", container_id)

    if upload_uri:
        print("Instagram upload URI received.")

    return container_id, upload_uri


# ============================================================
# UPLOAD VIDEO
# ============================================================

def upload_video_to_instagram(
    video_file,
    container_id,
    upload_uri=None
):
    file_size = os.path.getsize(video_file)

    if file_size > MAX_VIDEO_BYTES:
        raise RuntimeError(
            "Final video is over 50 MB."
        )

    print()
    print("Uploading Reel to Instagram...")

    if upload_uri:
        upload_url = upload_uri
    else:
        upload_url = (
            "https://rupload.facebook.com/"
            "ig-api-upload/"
            + API_VERSION
            + "/"
            + str(container_id)
        )

    headers = {
        "Authorization": (
            "OAuth " + INSTAGRAM_ACCESS_TOKEN
        ),
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "video/mp4"
    }

    with open(video_file, "rb") as video:
        response = requests.post(
            upload_url,
            headers=headers,
            data=video,
            timeout=300
        )

    if response.status_code not in [200, 201]:
        print("Instagram upload error:")
        print(response.text)
        response.raise_for_status()

    print("Video upload completed.")
    return True


# ============================================================
# WAIT FOR INSTAGRAM CONTAINER
# ============================================================

def wait_for_container(container_id):
    print()
    print("Waiting for Instagram to process the Reel...")

    url = instagram_url(container_id)

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        params = {
            "fields": "status_code,status",
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }

        response = requests.get(
            url,
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            print("Container status error:")
            print(response.text)
            response.raise_for_status()

        data = response.json()

        status_code = data.get("status_code")
        status = data.get("status")

        print(
            "Processing check "
            + str(attempt)
            + "/"
            + str(MAX_POLL_ATTEMPTS)
            + ":",
            status_code,
            status
        )

        if status_code == "FINISHED":
            print("Instagram Reel processing finished.")
            return True

        if status_code in ["ERROR", "EXPIRED"]:
            raise RuntimeError(
                "Instagram Reel processing failed: "
                + str(data)
            )

        time.sleep(POLL_SECONDS)

    raise RuntimeError(
        "Instagram Reel processing timed out."
    )


# ============================================================
# PUBLISH REEL
# ============================================================

def publish_reel(container_id):
    print()
    print("Publishing Reel to Instagram...")

    url = instagram_url(
        INSTAGRAM_USER_ID + "/media_publish"
    )

    payload = {
        "creation_id": container_id,
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.post(
        url,
        data=payload,
        timeout=60
    )

    if response.status_code not in [200, 201]:
        print("Instagram publish error:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    media_id = data.get("id")

    if not media_id:
        raise RuntimeError(
            "Instagram did not return published media ID: "
            + str(data)
        )

    print()
    print("============================================")
    print("REEL PUBLISHED SUCCESSFULLY")
    print("Instagram Media ID:", media_id)
    print("============================================")

    return media_id


# ============================================================
# MAIN
# =======================import os
import json
import time
import shutil
import subprocess
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
INSTAGRAM_ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_USER_ID = os.environ.get("INSTAGRAM_USER_ID")

INSTAGRAM_API_HOST = os.environ.get(
    "INSTAGRAM_API_HOST",
    "graph.facebook.com"
)

API_VERSION = os.environ.get(
    "META_API_VERSION",
    "v25.0"
)

GEMINI_MODEL = os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.8-flash"
)

MAX_VIDEO_BYTES = 50 * 1024 * 1024
REEL_SECONDS = 15
POLL_SECONDS = 15
MAX_POLL_ATTEMPTS = 40

OUTPUT_VIDEO = "reel.mp4"
WORK_DIR = Path("reel_assets")


# ============================================================
# BASIC HELPERS
# ============================================================

def run_command(command):
    print()
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
            "Command failed with exit code "
            + str(result.returncode)
        )

    return result.stdout


def check_dependencies():
    print()
    print("Checking dependencies...")

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed.")

    if not shutil.which("ffprobe"):
        raise RuntimeError("ffprobe is not installed.")

    print("ffmpeg:", shutil.which("ffmpeg"))
    print("ffprobe:", shutil.which("ffprobe"))


def cleanup_files():
    output_path = Path(OUTPUT_VIDEO)

    if output_path.exists():
        try:
            output_path.unlink()
        except OSError:
            pass

    if WORK_DIR.exists():
        try:
            shutil.rmtree(WORK_DIR)
        except OSError:
            pass

    WORK_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# GEMINI AI
# ============================================================

def ask_ai():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY secret is missing.")

    prompt = """
You are the content creator for PromptVerse India.

Create ONE useful Instagram Reel about:
AI, AI tools, AI prompts, AI photo editing,
AI video tricks, productivity with AI,
or useful AI websites.

Return ONLY valid JSON.

Use exactly this structure:

{
  "topic": "short topic",
  "script": "short Roman Hinglish reel script",
  "caption": "Instagram caption",
  "hashtags": "#AITools #AIHacks #PromptVerseIndia"
}

Rules:
- Use Roman Hinglish only.
- Do not use Devanagari Hindi.
- Keep the script short enough for a 15 second Reel.
- Make it useful and engaging.
- Keep it suitable for Indian viewers.
- Avoid fake claims.
- Do not use markdown.
- Do not put anything outside JSON.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        + GEMINI_MODEL
        + ":generateContent"
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

    params = {"key": GEMINI_API_KEY}

    for attempt in range(1, 6):
        print()
        print("Gemini request attempt " + str(attempt) + "/5")

        try:
            response = requests.post(
                url,
                params=params,
                json=payload,
                timeout=90
            )

            if response.status_code in [429, 500, 502, 503, 504]:
                print(
                    "Temporary Gemini error:",
                    response.status_code
                )

                if attempt < 5:
                    wait_time = attempt * 10
                    print(
                        "Waiting " + str(wait_time) + " seconds..."
                    )
                    time.sleep(wait_time)
                    continue

            response.raise_for_status()

            data = response.json()

            text = (
                data["candidates"][0]
                ["content"]["parts"][0]["text"]
            ).strip()

            if text.startswith("```"):
                text = text.replace("```json", "", 1)
                text = text.replace("```", "")
                text = text.strip()

            result = json.loads(text)

            required_keys = [
                "topic",
                "script",
                "caption",
                "hashtags"
            ]

            for key in required_keys:
                if not result.get(key):
                    raise RuntimeError(
                        "Gemini JSON missing: " + key
                    )

            print()
            print("AI Topic:", result["topic"])
            print("AI Script:", result["script"])
            print("Gemini content generated successfully.")

            return result

        except json.JSONDecodeError as error:
            print("Gemini JSON error:", error)

        except requests.RequestException as error:
            print("Gemini request error:", error)

        except Exception as error:
            print("Gemini error:", error)

        if attempt < 5:
            wait_time = attempt * 10
            print(
                "Retrying in " + str(wait_time) + " seconds..."
            )
            time.sleep(wait_time)

    raise RuntimeError("Gemini failed after 5 attempts.")


# ============================================================
# FONT
# ============================================================

def find_font(size, bold=False):
    if bold:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ]
    else:
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)

    return ImageFont.load_default()


# ============================================================
# VISUAL HELPERS
# ============================================================

def make_gradient(width, height, top_color, bottom_color):
    image = Image.new("RGB", (width, height))
    pixels = image.load()

    for y in range(height):
        ratio = y / max(1, height - 1)

        red = int(
            top_color[0] * (1 - ratio)
            + bottom_color[0] * ratio
        )
        green = int(
            top_color[1] * (1 - ratio)
            + bottom_color[1] * ratio
        )
        blue = int(
            top_color[2] * (1 - ratio)
            + bottom_color[2] * ratio
        )

        current_color = (red, green, blue)

        for x in range(width):
            pixels[x, y] = current_color

    return image


def draw_centered_text(
    draw,
    text,
    font,
    width,
    top_y,
    max_chars,
    fill
):
    lines = textwrap.wrap(
        str(text),
        width=max_chars
    )

    line_height = int(font.size * 1.25)
    current_y = top_y

    for line in lines:
        box = draw.textbbox(
            (0, 0),
            line,
            font=font
        )

        text_width = box[2] - box[0]
        x = (width - text_width) // 2

        draw.text(
            (x, current_y),
            line,
            font=font,
            fill=fill,
            stroke_width=2,
            stroke_fill=(0, 0, 0)
        )

        current_y += line_height

    return current_y


# ============================================================
# CREATE ORIGINAL VISUALS
# ============================================================

def create_visual_frames(content):
    print()
    print("Creating original Reel visuals...")

    width = 1080
    height = 1920

    topic = str(content["topic"]).strip()
    script = str(content["script"]).strip()
    hashtags = str(content["hashtags"]).strip()

    title_font = find_font(78, True)
    script_font = find_font(52, True)
    subtitle_font = find_font(46, False)
    small_font = find_font(36, False)

    frames = []

    # FRAME 1
    image = make_gradient(
        width,
        height,
        (12, 18, 45),
        (70, 25, 100)
    )

    draw = ImageDraw.Draw(image)

    draw.ellipse(
        (-180, -180, 360, 360),
        fill=(70, 70, 170)
    )

    draw.ellipse(
        (800, 1450, 1250, 1900),
        fill=(30, 120, 170)
    )

    draw.text(
        (55, 90),
        "PROMPTVERSE INDIA",
        font=small_font,
        fill=(240, 240, 240)
    )

    draw_centered_text(
        draw,
        topic,
        title_font,
        width,
        500,
        18,
        (255, 255, 255)
    )

    draw_centered_text(
        draw,
        "AI TIP OF THE DAY",
        subtitle_font,
        width,
        1080,
        28,
        (220, 230, 255)
    )

    frame1 = WORK_DIR / "frame1.png"
    image.save(frame1)
    frames.append(frame1)

    # FRAME 2
    image = make_gradient(
        width,
        height,
        (15, 40, 50),
        (10, 90, 90)
    )

    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (55, 280, 1025, 1660),
        radius=45,
        fill=(8, 20, 25)
    )

    draw.text(
        (90, 360),
        "TRY THIS",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw_centered_text(
        draw,
        script,
        script_font,
        900,
        590,
        22,
        (255, 255, 255)
    )

    draw.text(
        (90, 1500),
        "Follow @promptverseindia",
        font=small_font,
        fill=(200, 240, 240)
    )

    frame2 = WORK_DIR / "frame2.png"
    image.save(frame2)
    frames.append(frame2)

    # FRAME 3
    image = make_gradient(
        width,
        height,
        (45, 18, 15),
        (105, 35, 60)
    )

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 100),
        "SAVE THIS REEL",
        font=title_font,
        fill=(255, 255, 255)
    )

    draw_centered_text(
        draw,
        hashtags,
        subtitle_font,
        width,
        650,
        26,
        (255, 235, 235)
    )

    draw_centered_text(
        draw,
        "More AI tips daily",
        title_font,
        width,
        1150,
        18,
        (255, 255, 255)
    )

    frame3 = WORK_DIR / "frame3.png"
    image.save(frame3)
    frames.append(frame3)

    print("Created 3 visual frames.")

    return frames


# ============================================================
# CREATE MP4
# ============================================================

def create_reel(frame_paths):
    print()
    print("Creating final Instagram Reel...")

    if len(frame_paths) != 3:
        raise RuntimeError("Expected exactly 3 frames.")

    frame1 = str(frame_paths[0])
    frame2 = str(frame_paths[1])
    frame3 = str(frame_paths[2])

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v0];"

        "[1:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v1];"

        "[2:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1[v2];"

        "[v0][v1][v2]"
        "concat=n=3:v=1:a=0,"
        "format=yuv420p[outv]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop", "1",
        "-t", "5",
        "-i", frame1,

        "-loop", "1",
        "-t", "5",
        "-i", frame2,

        "-loop", "1",
        "-t", "5",
        "-i", frame3,

        "-f", "lavfi",
        "-t", str(REEL_SECONDS),
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",

        "-filter_complex",
        filter_complex,

        "-map", "[outv]",
        "-map", "3:a",

        "-r", "30",

        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "2200k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",

        "-c:a", "aac",
        "-b:a", "96k",

        "-pix_fmt", "yuv420p",
        "-t", str(REEL_SECONDS),
        "-movflags", "+faststart",

        OUTPUT_VIDEO
    ]

    run_command(command)

    if not os.path.exists(OUTPUT_VIDEO):
        raise RuntimeError(
            "FFmpeg did not create reel.mp4."
        )

    file_size = os.path.getsize(OUTPUT_VIDEO)
    file_mb = file_size / 1024 / 1024

    print()
    print("Final Reel size:", round(file_mb, 2), "MB")

    if file_size > MAX_VIDEO_BYTES:
        raise RuntimeError(
            "Final Reel is over 50 MB."
        )

    print("Reel is safely under 50 MB.")

    return OUTPUT_VIDEO


# ============================================================
# INSTAGRAM API
# ============================================================

def instagram_url(path):
    return (
        "https://"
        + INSTAGRAM_API_HOST
        + "/"
        + API_VERSION
        + "/"
        + str(path)
    )


def check_instagram_credentials():
    print()
    print("Checking Instagram credentials...")

    if not INSTAGRAM_ACCESS_TOKEN:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN secret is missing."
        )

    if not INSTAGRAM_USER_ID:
        raise RuntimeError(
            "INSTAGRAM_USER_ID secret is missing."
        )

    if not str(INSTAGRAM_USER_ID).isdigit():
        raise RuntimeError(
            "INSTAGRAM_USER_ID must be the numeric Instagram User ID."
        )

    print("Instagram credentials found.")
    print("Instagram User ID:", INSTAGRAM_USER_ID)


def verify_instagram_user():
    print()
    print("Verifying Instagram User ID...")

    url = instagram_url(INSTAGRAM_USER_ID)

    params = {
        "fields": "id,username",
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.get(
        url,
        params=params,
        timeout=60
    )

    if response.status_code != 200:
        print("Instagram verification failed:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    returned_id = str(data.get("id", ""))
    username = data.get("username")

    print("Instagram User ID:", returned_id)
    print("Instagram username:", username)

    if returned_id != str(INSTAGRAM_USER_ID):
        raise RuntimeError(
            "Instagram returned a different User ID."
        )

    return data


# ============================================================
# CREATE REEL CONTAINER
# ============================================================

def create_reel_container(caption):
    print()
    print("Creating Instagram Reel container...")

    url = instagram_url(
        INSTAGRAM_USER_ID + "/media"
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

    if response.status_code not in [200, 201]:
        print("Instagram container error:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    container_id = data.get("id")
    upload_uri = data.get("uri")

    if not container_id:
        raise RuntimeError(
            "Instagram did not return a container ID: "
            + str(data)
        )

    print("Instagram container:", container_id)

    if upload_uri:
        print("Instagram upload URI received.")

    return container_id, upload_uri


# ============================================================
# UPLOAD VIDEO
# ============================================================

def upload_video_to_instagram(
    video_file,
    container_id,
    upload_uri=None
):
    file_size = os.path.getsize(video_file)

    if file_size > MAX_VIDEO_BYTES:
        raise RuntimeError(
            "Final video is over 50 MB."
        )

    print()
    print("Uploading Reel to Instagram...")

    if upload_uri:
        upload_url = upload_uri
    else:
        upload_url = (
            "https://rupload.facebook.com/"
            "ig-api-upload/"
            + API_VERSION
            + "/"
            + str(container_id)
        )

    headers = {
        "Authorization": (
            "OAuth " + INSTAGRAM_ACCESS_TOKEN
        ),
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "video/mp4"
    }

    with open(video_file, "rb") as video:
        response = requests.post(
            upload_url,
            headers=headers,
            data=video,
            timeout=300
        )

    if response.status_code not in [200, 201]:
        print("Instagram upload error:")
        print(response.text)
        response.raise_for_status()

    print("Video upload completed.")
    return True


# ============================================================
# WAIT FOR INSTAGRAM CONTAINER
# ============================================================

def wait_for_container(container_id):
    print()
    print("Waiting for Instagram to process the Reel...")

    url = instagram_url(container_id)

    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        params = {
            "fields": "status_code,status",
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }

        response = requests.get(
            url,
            params=params,
            timeout=60
        )

        if response.status_code != 200:
            print("Container status error:")
            print(response.text)
            response.raise_for_status()

        data = response.json()

        status_code = data.get("status_code")
        status = data.get("status")

        print(
            "Processing check "
            + str(attempt)
            + "/"
            + str(MAX_POLL_ATTEMPTS)
            + ":",
            status_code,
            status
        )

        if status_code == "FINISHED":
            print("Instagram Reel processing finished.")
            return True

        if status_code in ["ERROR", "EXPIRED"]:
            raise RuntimeError(
                "Instagram Reel processing failed: "
                + str(data)
            )

        time.sleep(POLL_SECONDS)

    raise RuntimeError(
        "Instagram Reel processing timed out."
    )


# ============================================================
# PUBLISH REEL
# ============================================================

def publish_reel(container_id):
    print()
    print("Publishing Reel to Instagram...")

    url = instagram_url(
        INSTAGRAM_USER_ID + "/media_publish"
    )

    payload = {
        "creation_id": container_id,
        "access_token": INSTAGRAM_ACCESS_TOKEN
    }

    response = requests.post(
        url,
        data=payload,
        timeout=60
    )

    if response.status_code not in [200, 201]:
        print("Instagram publish error:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    media_id = data.get("id")

    if not media_id:
        raise RuntimeError(
            "Instagram did not return published media ID: "
            + str(data)
        )

    print()
    print("============================================")
    print("REEL PUBLISHED SUCCESSFULLY")
    print("Instagram Media ID:", media_id)
    print("============================================")

    return media_id


# ============================================================
# MAIN
# =======================
