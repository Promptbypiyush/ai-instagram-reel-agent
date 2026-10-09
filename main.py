import os
import time
import json
import random
import subprocess
import base64
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont


# =========================
# CONFIG
# =========================
G = os.getenv("GEMINI_API_KEY")
IG = os.getenv("INSTAGRAM_ACCESS_TOKEN")
UID = os.getenv("INSTAGRAM_USER_ID")

HOST = os.getenv("INSTAGRAM_API_HOST", "graph.facebook.com")
VER = os.getenv("META_API_VERSION", "v25.0")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

WORK = Path("reel_work")
WORK.mkdir(exist_ok=True)

if not G or not IG or not UID:
    raise RuntimeError(
        "Missing GEMINI_API_KEY / INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_USER_ID"
    )


# =========================
# RETRY
# =========================
def wait_retry(n, cap=60):
    delay = min(cap, 2 ** n) + random.uniform(0.5, 2.5)
    print(f"Waiting {delay:.1f}s before retry...", flush=True)
    time.sleep(delay)


def post(url, data=None, timeout=120, headers=None):
    for n in range(6):
        try:
            r = requests.post(
                url,
                data=data,
                headers=headers,
                timeout=timeout
            )

            if r.status_code not in (408, 429, 500, 502, 503, 504):
                return r

            print("POST retry:", r.status_code, flush=True)

        except requests.RequestException as e:
            print("POST retry:", e, flush=True)

        wait_retry(n)

    return requests.post(
        url,
        data=data,
        headers=headers,
        timeout=180
    )


# =========================
# GEMINI TEXT
# =========================
def gemini(prompt, model=None):
    models = [
        model or MODEL,
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash"
    ]

    seen = set()

    for m in models:
        if m in seen:
            continue

        seen.add(m)

        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{m}:generateContent"
        )

        body = {
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

        for n in range(5):
            try:
                r = requests.post(
                    url,
                    headers={
                        "x-goog-api-key": G,
                        "Content-Type": "application/json"
                    },
                    json=body,
                    timeout=90
                )

                print(
                    f"Gemini {m}: HTTP {r.status_code}",
                    flush=True
                )

                if r.ok:
                    try:
                        x = r.json()
                        text = (
                            x["candidates"][0]
                            ["content"]["parts"][0]["text"]
                            .strip()
                        )
                        if text:
                            return text
                    except Exception as e:
                        print(
                            "Gemini response parse error:",
                            e,
                            flush=True
                        )

                if r.status_code in (400, 401, 403, 404):
                    print(
                        "Non-retryable model/API error:",
                        r.text[:500],
                        flush=True
                    )
                    break

                if r.status_code not in (408, 429, 500, 502, 503, 504):
                    break

            except requests.RequestException as e:
                print("Gemini retry:", e, flush=True)

            wait_retry(n)

        print(
            f"Switching Gemini model from {m}...",
            flush=True
        )

    return ""


# =========================
# GEMINI TTS
# =========================
def tts(text, out):
    models = [
        "gemini-3.8-flash-tts",
        "gemini-3.8-flash-lite-tts"
    ]

    for m in models:
        url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{m}:generateContent"
        )

        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": text,
                            "speech_metadata": {
                                "style": (
                                    "natural energetic Hindi "
                                    "Instagram Reel narration, "
                                    "clear, youthful and engaging"
                                )
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "voice": "Kore"
                    }
                }
            }
        }

        for n in range(5):
            try:
                r = requests.post(
                    url,
                    headers={
                        "x-goog-api-key": G,
                        "Content-Type": "application/json"
                    },
                    json=body,
                    timeout=120
                )

                print(
                    f"TTS {m}: HTTP {r.status_code}",
                    flush=True
                )

                if r.ok:
                    try:
                        x = r.json()

                        b64 = (
                            x["candidates"][0]
                            ["content"]["parts"][0]
                            ["inlineData"]["data"]
                        )

                        Path(out).write_bytes(
                            base64.b64decode(b64)
                        )

                        return True

                    except Exception as e:
                        print(
                            "TTS response parse error:",
                            e,
                            flush=True
                        )

                if r.status_code in (400, 401, 403, 404):
                    print(
                        "TTS API error:",
                        r.text[:500],
                        flush=True
                    )
                    break

            except requests.RequestException as e:
                print("TTS retry:", e, flush=True)

            wait_retry(n, 45)

        print(
            f"Switching TTS model from {m}...",
            flush=True
        )

    return False


# =========================
# LOCAL VOICE FALLBACK
# =========================
def local_voice(text, out):
    try:
        subprocess.run(
            [
                "espeak-ng",
                "-v",
                "hi",
                "-s",
                "155",
                "-w",
                out,
                text
            ],
            check=True,
            timeout=60
        )
        return True
    except Exception as e:
        print("Local voice error:", e, flush=True)
        return False


# =========================
# FONT
# =========================
def font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]

    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)

    return ImageFont.load_default()


# =========================
# FRAME
# =========================
def make_frame(title, body, num):
    im = Image.new(
        "RGB",
        (1080, 1920),
        (12, 15, 25)
    )

    d = ImageDraw.Draw(im)

    f1 = font(76)
    f2 = font(48)

    d.text(
        (70, 100),
        title,
        fill="white",
        font=f1
    )

    y = 360
    words = body.split()
    line = ""

    for w in words:
        test = (line + " " + w).strip()

        if d.textbbox(
            (0, 0),
            test,
            font=f2
        )[2] > 900:

            d.text(
                (70, y),
                line,
                fill="white",
                font=f2
            )

            y += 75
            line = w

        else:
            line = test

    if line:
        d.text(
            (70, y),
            line,
            fill="white",
            font=f2
        )

    d.text(
        (70, 1770),
        f"PROMPTVERSE INDIA • {num}/3",
        fill="white",
        font=font(32)
    )

    path = WORK / f"frame{num}.jpg"
    im.save(path, quality=95)

    return path


# =========================
# VIDEO
# =========================
def video(frames, audio, out):
    lst = WORK / "list.txt"

    with open(lst, "w", encoding="utf-8") as f:
        for x in frames:
            f.write(
                f"file '{Path(x).resolve()}'\n"
            )
            f.write("duration 5\n")

        f.write(
            f"file '{Path(frames[-1]).resolve()}'\n"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(lst),
        "-i",
        str(audio),
        "-t",
        "15",
        "-vf",
        "scale=1080:1920:"
        "force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(out)
    ]

    subprocess.run(
        cmd,
        check=True,
        timeout=240
    )


# =========================
# INSTAGRAM
# =========================
def instagram(video_file, caption):
    base = f"https://{HOST}/{VER}"

    video_url = upload_public_url(video_file)

    r = post(
        f"{base}/{UID}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": IG
        },
        timeout=120
    )

    if not r.ok:
        raise RuntimeError(
            "Instagram container error: " + r.text
        )

    cid = r.json()["id"]

    for i in range(40):
        try:
            q = requests.get(
                f"{base}/{cid}",
                params={
                    "fields": "status_code,status",
                    "access_token": IG
                },
                timeout=60
            )

            x = q.json()

            print(
                "Instagram:",
                x,
                flush=True
            )

            if x.get("status_code") == "FINISHED":
                break

            if x.get("status_code") == "ERROR":
                raise RuntimeError(
                    "Instagram processing failed: " +
                    str(x)
                )

        except requests.RequestException as e:
            print(
                "Instagram status retry:",
                e,
                flush=True
            )

        time.sleep(15)

    else:
        raise RuntimeError(
            "Instagram processing timeout"
        )

    r = post(
        f"{base}/{UID}/media_publish",
        data={
            "creation_id": cid,
            "access_token": IG
        },
        timeout=120
    )

    if not r.ok:
        raise RuntimeError(
            "Publish error: " + r.text
        )

    print(
        "REEL PUBLISHED:",
        r.text,
        flush=True
    )


# =========================
# PUBLIC VIDEO URL
# =========================
def upload_public_url(video):
    u = os.getenv("REEL_VIDEO_URL")

    if u:
        return u

    raise RuntimeError(
        "REEL_VIDEO_URL is not set. "
        "Instagram requires a publicly reachable video URL."
    )


# =========================
# MAIN
# =========================
def main():
    print(
        "PROMPTVERSE INDIA AUTO REEL BOT",
        flush=True
    )

    prompt = """
Create one viral Hindi Instagram Reel package.

Return ONLY valid JSON.
Do not use markdown.
Do not add ```json.

{
  "topic": "short topic",
  "script": "Hindi narration around 45-70 words",
  "caption": "short Hindi caption",
  "hashtags": [
    "#reels",
    "#viral",
    "#ai",
    "#india",
    "#trending"
  ]
}

Make it interesting, factual or entertaining,
and suitable for a general audience.
"""

    raw = gemini(prompt)

    if not raw:
        print(
            "Gemini failed completely. Using fallback content.",
            flush=True
        )

    try:
        raw = (
            raw
            .replace("```json", "")
            .replace("```", "")
            .strip()
        )

        data = json.loads(raw)

    except Exception:
        data = {
            "topic": "AI की एक मजेदार और काम की जानकारी",
            "script": (
                "क्या आपको पता है कि आज AI कितनी तेजी से "
                "हमारी रोजमर्रा की जिंदगी बदल रहा है? "
                "छोटे-छोटे काम से लेकर वीडियो बनाने तक, "
                "AI अब कई काम सेकंडों में कर सकता है। "
                "लेकिन सबसे जरूरी बात है कि इसका इस्तेमाल "
                "समझदारी और सही तरीके से किया जाए।"
            ),
            "caption": (
                "AI की दुनिया सच में तेजी से बदल रही है! 🤯"
            ),
            "hashtags": [
                "#reels",
                "#viral",
                "#ai",
                "#india",
                "#trending"
            ]
        }

    topic = str(
        data.get("topic", "AI")
    ).strip()

    script = str(
        data.get("script", "")
    ).strip()

    caption = str(
        data.get("caption", "")
    ).strip()

    tags = data.get(
        "hashtags",
        [
            "#reels",
            "#viral",
            "#ai",
            "#india",
            "#trending"
        ]
    )

    tags = " ".join(
        str(x) for x in tags[:5]
    )

    print(
        "TOPIC:",
        topic,
        flush=True
    )

    # =========================
    # AUDIO
    # =========================
    audio = WORK / "voice.wav"

    if not tts(
        script,
        str(audio)
    ):
        print(
            "Gemini TTS failed; trying local voice...",
            flush=True
        )

        if not local_voice(
            script,
            str(audio)
        ):
            raise RuntimeError(
                "Voice generation failed"
            )

    # =========================
    # FRAMES
    # =========================
    frames = [
        make_frame(
            topic,
            script[:250],
            1
        ),
        make_frame(
            topic,
            script[250:500] or script,
            2
        ),
        make_frame(
            topic,
            script[500:] or script,
            3
        )
    ]

    # =========================
    # VIDEO
    # =========================
    mp4 = WORK / "reel.mp4"

    video(
        frames,
        audio,
        mp4
    )

    # =========================
    # CAPTION
    # =========================
    final_caption = (
        f"{caption}\n\n{tags}"
    )

    # =========================
    # INSTAGRAM
    # =========================
    instagram(
        mp4,
        final_caption
    )


if __name__ == "__main__":
    main()
