import os
import sys
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
IG_ID = os.getenv("INSTAGRAM_USER_ID")

HOST = os.getenv("INSTAGRAM_API_HOST", "graph.facebook.com")
VER = os.getenv("META_API_VERSION", "v25.0")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

OUTPUT = "reel.mp4"
AUDIO = "voice.mp3"
WORK = Path("reel_assets")

MAX_BYTES = 50 * 1024 * 1024
REEL_SECONDS = 15


# ============================================================
# HELPERS
# ============================================================

def run(cmd):
    print("\nRunning:", " ".join(cmd), flush=True)

    r = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(r.stdout, flush=True)

    if r.returncode != 0:
        raise RuntimeError("Command failed")


def api_url(path):
    return f"https://{HOST}/{VER}/{path}"


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
    ]

    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)

    return ImageFont.load_default()


def draw_text(draw, value, fnt, width, y, chars=20):
    lines = textwrap.wrap(str(value), width=chars)

    for line in lines:
        box = draw.textbbox((0, 0), line, font=fnt)
        tw = box[2] - box[0]
        x = (width - tw) // 2

        draw.text(
            (x, y),
            line,
            font=fnt,
            fill="white",
            stroke_width=2,
            stroke_fill="black"
        )

        y += int(fnt.size * 1.25)


# ============================================================
# GEMINI
# ============================================================

def generate_content():
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY secret missing")

    prompt = """
Create ONE useful Instagram Reel about AI, AI tools,
AI prompts, AI photo editing, AI video tricks,
productivity with AI, or useful AI websites.

Return ONLY valid JSON:

{
  "topic": "short topic",
  "script": "short Roman Hinglish voice script",
  "caption": "Instagram caption",
  "hashtags": "#AITools #AIHacks #PromptVerseIndia"
}

Rules:
- Roman Hinglish only.
- No Devanagari.
- Script must be short enough for about 15 seconds.
- Write naturally so a Hindi AI voice can speak it.
- Useful and engaging for Indian viewers.
- No fake claims.
- No markdown.
- Nothing outside JSON.
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        + MODEL
        + ":generateContent"
    )

    r = requests.post(
        url,
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        },
        timeout=90
    )

    r.raise_for_status()

    value = (
        r.json()["candidates"][0]
        ["content"]["parts"][0]["text"]
        .strip()
    )

    value = (
        value
        .replace("```json", "")
        .replace("```", "")
        .strip()
    )

    data = json.loads(value)

    for key in [
        "topic",
        "script",
        "caption",
        "hashtags"
    ]:
        if not data.get(key):
            raise RuntimeError(
                f"Gemini missing {key}"
            )

    print("\nTOPIC:", data["topic"])
    print("SCRIPT:", data["script"])

    return data


# ============================================================
# AI VOICE
# ============================================================

def install_voice_package():
    try:
        import edge_tts
        return edge_tts
    except ImportError:
        print("\nInstalling edge-tts...", flush=True)

        subprocess.check_call([
            sys.executable,
            "-m",
            "pip",
            "install",
            "-q",
            "edge-tts"
        ])

        import edge_tts
        return edge_tts


def create_voice(script):
    edge_tts = install_voice_package()

    print("\nCreating Hindi AI voice...", flush=True)

    async def make():
        communicate = edge_tts.Communicate(
            script,
            "hi-IN-SwaraNeural",
            rate="+5%",
            volume="+0%"
        )

        await communicate.save(AUDIO)

    import asyncio
    asyncio.run(make())

    if not os.path.exists(AUDIO):
        raise RuntimeError("AI voice was not created")

    print("AI voice created successfully.", flush=True)

    return AUDIO


# ============================================================
# VISUALS
# ============================================================

def create_frames(data):
    if WORK.exists():
        shutil.rmtree(WORK)

    WORK.mkdir(parents=True, exist_ok=True)

    W, H = 1080, 1920

    title = font(76, True)
    script_font = font(50, True)
    small = font(34)

    items = [
        (
            (12, 18, 45),
            (70, 25, 100),
            data["topic"],
            title,
            18
        ),
        (
            (15, 40, 50),
            (10, 90, 90),
            data["script"],
            script_font,
            22
        ),
        (
            (45, 18, 15),
            (105, 35, 60),
            "SAVE THIS REEL\n\nMore AI tips daily",
            title,
            18
        )
    ]

    frames = []

    for i, (top, bottom, message, fnt, chars) in enumerate(
        items,
        1
    ):
        img = Image.new(
            "RGB",
            (W, H),
            top
        )

        draw = ImageDraw.Draw(img)

        for y in range(H):
            ratio = y / (H - 1)

            color = tuple(
                int(
                    top[k] * (1 - ratio)
                    + bottom[k] * ratio
                )
                for k in range(3)
            )

            draw.line(
                (0, y, W, y),
                fill=color
            )

        draw.text(
            (55, 80),
            "PROMPTVERSE INDIA",
            font=small,
            fill="white"
        )

        draw_text(
            draw,
            message,
            fnt,
            W,
            500,
            chars
        )

        path = WORK / f"frame{i}.png"

        img.save(path)
        frames.append(str(path))

    return frames


# ============================================================
# VIDEO + VOICE
# ============================================================

def create_video(frames, audio):
    print("\nCreating final Reel with AI voice...", flush=True)

    silent_video = str(WORK / "silent.mp4")

    run([
        "ffmpeg",
        "-y",

        "-loop", "1",
        "-t", "5",
        "-i", frames[0],

        "-loop", "1",
        "-t", "5",
        "-i", frames[1],

        "-loop", "1",
        "-t", "5",
        "-i", frames[2],

        "-filter_complex",
        "[0:v]scale=1080:1920,"
        "setsar=1[v0];"
        "[1:v]scale=1080:1920,"
        "setsar=1[v1];"
        "[2:v]scale=1080:1920,"
        "setsar=1[v2];"
        "[v0][v1][v2]"
        "concat=n=3:v=1:a=0,"
        "format=yuv420p[v]",

        "-map", "[v]",
        "-t", "15",

        "-r", "30",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-b:v", "2200k",

        silent_video
    ])

    run([
        "ffmpeg",
        "-y",

        "-i", silent_video,
        "-i", audio,

        "-map", "0:v:0",
        "-map", "1:a:0",

        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",

        "-t", "15",

        "-shortest",

        "-movflags", "+faststart",

        OUTPUT
    ])

    if not os.path.exists(OUTPUT):
        raise RuntimeError("Final Reel was not created")

    size = os.path.getsize(OUTPUT)

    print(
        "\nFinal Reel:",
        round(size / 1024 / 1024, 2),
        "MB"
    )

    if size > MAX_BYTES:
        raise RuntimeError("Reel is over 50 MB")


# ============================================================
# INSTAGRAM
# ============================================================

def create_container(caption):
    if not TOKEN:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN missing"
        )

    if not IG_ID:
        raise RuntimeError(
            "INSTAGRAM_USER_ID missing"
        )

    if not str(IG_ID).isdigit():
        raise RuntimeError(
            "INSTAGRAM_USER_ID must be numeric"
        )

    r = requests.post(
        api_url(f"{IG_ID}/media"),
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
            "share_to_feed": "true",
            "access_token": TOKEN
        },
        timeout=60
    )

    r.raise_for_status()

    data = r.json()

    if not data.get("id"):
        raise RuntimeError(
            f"Instagram container error: {data}"
        )

    if not data.get("uri"):
        raise RuntimeError(
            f"Instagram upload URI missing: {data}"
        )

    return data["id"], data["uri"]


def upload_video(upload_uri):
    print("\nUploading Reel to Instagram...", flush=True)

    size = os.path.getsize(OUTPUT)

    with open(OUTPUT, "rb") as f:
        r = requests.post(
            upload_uri,
            headers={
                "Authorization": f"OAuth {TOKEN}",
                "offset": "0",
                "file_size": str(size)
            },
            data=f,
            timeout=600
        )

    r.raise_for_status()

    print("Video uploaded.", flush=True)


def wait_for_processing(container_id):
    print(
        "\nWaiting for Instagram processing...",
        flush=True
    )

    for _ in range(40):
        r = requests.get(
            api_url(container_id),
            params={
                "fields": "status_code",
                "access_token": TOKEN
            },
            timeout=60
        )

        r.raise_for_status()

        status = r.json().get("status_code")

        print("Status:", status, flush=True)

        if status == "FINISHED":
            return

        if status in [
            "ERROR",
            "EXPIRED"
        ]:
            raise RuntimeError(
                "Instagram processing failed"
            )

        time.sleep(15)

    raise RuntimeError(
        "Instagram processing timeout"
    )


def publish(container_id):
    print("\nPublishing Reel...", flush=True)

    r = requests.post(
        api_url(f"{IG_ID}/media_publish"),
        data={
            "creation_id": container_id,
            "access_token": TOKEN
        },
        timeout=60
    )

    r.raise_for_status()

    print(
        "\n================================",
        flush=True
    )

    print(
        "REEL POSTED SUCCESSFULLY!",
        flush=True
    )

    print(
        r.json(),
        flush=True
    )

    print(
        "================================",
        flush=True
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("\nPROMPTVERSE INDIA AUTO REEL BOT")

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed")

    content = generate_content()

    frames = create_frames(content)

    audio = create_voice(
        content["script"]
    )

    create_video(
        frames,
        audio
    )

    caption = (
        str(content["caption"]).strip()
        + "\n\n"
        + str(content["hashtags"]).strip()
    )

    container_id, upload_uri = create_container(
        caption
    )

    upload_video(upload_uri)

    wait_for_processing(container_id)

    publish(container_id)

    print("\nALL DONE.")


if __name__ == "__main__":
    main()
