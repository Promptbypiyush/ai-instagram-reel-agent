import os, time, json, random, subprocess, base64
from pathlib import Path
import requests
from PIL import Image, ImageDraw, ImageFont

G = os.getenv("GEMINI_API_KEY")
IG = os.getenv("INSTAGRAM_ACCESS_TOKEN")
UID = os.getenv("INSTAGRAM_USER_ID")
HOST = os.getenv("INSTAGRAM_API_HOST", "graph.facebook.com")
VER = os.getenv("META_API_VERSION", "v25.0")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
WORK = Path("reel_work")
WORK.mkdir(exist_ok=True)

if not all((G, IG, UID)):
    raise RuntimeError("Missing GitHub Secrets: GEMINI_API_KEY, INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_USER_ID")

S = requests.Session()

def pause(n, cap=45):
    time.sleep(min(cap, 2 ** n) + random.uniform(.3, 1.5))

def request(method, url, **kwargs):
    last = None
    for n in range(6):
        try:
            r = S.request(method, url, timeout=kwargs.pop("timeout", 120) if n == 0 else 120, **kwargs)
            if r.status_code not in (408, 429, 500, 502, 503, 504):
                return r
            last = RuntimeError(f"HTTP {r.status_code}: {r.text[:400]}")
            print("Retryable HTTP:", r.status_code, flush=True)
        except requests.RequestException as e:
            last = e
            print("Network retry:", e, flush=True)
        pause(n)
    raise RuntimeError(f"Request failed after retries: {last}")

def gemini(prompt, model=None):
    models = list(dict.fromkeys([model or MODEL, "gemini-3.8-flash", "gemini-2.5-flash"]))
    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        for n in range(4):
            try:
                r = S.post(url, headers={"x-goog-api-key": G, "Content-Type": "application/json"},
                           json=body, timeout=90)
                print(f"Gemini {m}: HTTP {r.status_code}", flush=True)
                if r.ok:
                    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    result = "".join(p.get("text", "") for p in parts).strip()
                    if result:
                        return result
                if r.status_code in (400, 401, 403, 404):
                    print("Gemini response:", r.text[:500], flush=True)
                    break
            except (requests.RequestException, ValueError, IndexError, KeyError) as e:
                print("Gemini retry:", e, flush=True)
            pause(n)
    return ""

def tts(text, out):
    for m in ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [
                {"text": text, "speech_metadata": {"style": "Natural, lively Hindi Instagram Reel narration"}}
            ]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}},
                    "languageCode": "hi-IN"
                }
            }
        }
        for n in range(4):
            try:
                r = S.post(url, headers={"x-goog-api-key": G, "Content-Type": "application/json"},
                           json=body, timeout=120)
                print(f"TTS {m}: HTTP {r.status_code}", flush=True)
                if r.ok:
                    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    for p in parts:
                        audio = p.get("inlineData", {}).get("data")
                        if audio:
                            Path(out).write_bytes(base64.b64decode(audio))
                            return True
                if r.status_code in (400, 401, 403, 404):
                    print("TTS response:", r.text[:400], flush=True)
                    break
            except (requests.RequestException, ValueError, IndexError, KeyError) as e:
                print("TTS retry:", e, flush=True)
            pause(n)
    return False

def local_voice(text, out):
    # espeak-ng must already be installed by the workflow runner.
    try:
        subprocess.run(["espeak-ng", "-v", "hi", "-s", "155", "-w", str(out), text],
                       check=True, timeout=60)
        return True
    except Exception as e:
        print("Local voice unavailable:", e, flush=True)
        return False

def get_font(size):
    for p in (
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def make_frame(title, body, num):
    im = Image.new("RGB", (1080, 1920), (12, 15, 25))
    d = ImageDraw.Draw(im)
    d.text((65, 100), title[:55], fill="white", font=get_font(68))
    f = get_font(46)
    y, line = 360, ""
    for word in body.split():
        test = (line + " " + word).strip()
        if d.textbbox((0, 0), test, font=f)[2] > 940:
            d.text((65, y), line, fill="white", font=f)
            y += 78
            line = word
            if y > 1550:
                break
        else:
            line = test
    if line and y <= 1550:
        d.text((65, y), line, fill="white", font=f)
    d.text((65, 1780), f"PROMPTVERSE INDIA • {num}/3", fill="white", font=get_font(30))
    p = WORK / f"frame{num}.jpg"
    im.save(p, quality=92)
    return p

def make_video(frames, audio, out, raw_pcm=False):
    lst = WORK / "list.txt"
    with lst.open("w", encoding="utf-8") as f:
        for frame in frames:
            f.write(f"file '{Path(frame).resolve()}'\n")
            f.write("duration 5\n")
        f.write(f"file '{Path(frames[-1]).resolve()}'\n")
    audio_input = (["-f", "s16le", "-ar", "24000", "-ac", "1"] if raw_pcm else [])
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
           *audio_input, "-i", str(audio), "-t", "15",
           "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
           "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-ar", "48000", "-b:a", "128k", "-shortest", str(out)]
    subprocess.run(cmd, check=True, timeout=240)

def upload_public_url(video_file):
    size = Path(video_file).stat().st_size
    if size > 100 * 1024 * 1024:
        raise RuntimeError(f"Video is {size // (1024*1024)} MB; temporary host limit is 100 MB.")
    print("Uploading video to temporary public hosting...", flush=True)
    with open(video_file, "rb") as f:
        r = S.post("https://tempfile.org/api/upload/local",
                   files={"files": (Path(video_file).name, f, "video/mp4")},
                   data={"expiryHours": "24"}, timeout=180)
    if not r.ok:
        raise RuntimeError(f"Temporary video upload failed: HTTP {r.status_code}: {r.text[:500]}")
    data = r.json()
    if not data.get("success") or not data.get("files"):
        raise RuntimeError(f"Temporary video host returned an error: {data}")
    file_id = data["files"][0].get("id")
    if not file_id:
        raise RuntimeError(f"Temporary host did not return a file ID: {data}")
    url = f"https://tempfile.org/{file_id}/download"
    print("Temporary public video URL ready (expires after 24 hours).", flush=True)
    return url

def instagram(video_file, caption):
    base = f"https://{HOST}/{VER}"
    video_url = upload_public_url(video_file)
    r = request("POST", f"{base}/{UID}/media", data={
        "media_type": "REELS", "video_url": video_url, "caption": caption,
        "access_token": IG
    })
    if not r.ok:
        raise RuntimeError(f"Instagram container error: {r.text[:1000]}")
    cid = r.json().get("id")
    if not cid:
        raise RuntimeError(f"Instagram did not return a container ID: {r.text[:500]}")
    for i in range(40):
        q = request("GET", f"{base}/{cid}", params={
            "fields": "status_code,status", "access_token": IG
        }, timeout=60)
        state = q.json()
        print("Instagram processing:", state, flush=True)
        status = state.get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"Instagram video processing failed: {state}")
        time.sleep(15)
    else:
        raise RuntimeError("Instagram processing timed out after 10 minutes.")
    r = request("POST", f"{base}/{UID}/media_publish",
                data={"creation_id": cid, "access_token": IG})
    if not r.ok:
        raise RuntimeError(f"Instagram publish failed: {r.text[:1000]}")
    print("REEL PUBLISHED:", r.text, flush=True)

def main():
    print("PROMPTVERSE INDIA AUTO REEL BOT STARTED", flush=True)
    prompt = """Return ONLY valid JSON with keys topic, script, caption, hashtags.
Create a factual or entertaining Hindi Instagram Reel package for a general audience.
Keep narration around 30-40 Hindi words so it fits a 15-second Reel.
Use this exact JSON structure:
{"topic":"short Hindi topic","script":"Hindi narration","caption":"short Hindi caption","hashtags":["#reels","#viral","#ai","#india","#trending"]}
No markdown or code fences."""
    raw = gemini(prompt)
    fallback = {
        "topic": "AI की मजेदार जानकारी",
        "script": "क्या आप जानते हैं, AI की मदद से अब लोग वीडियो, तस्वीरें और आवाज़ कुछ ही मिनटों में बना सकते हैं। लेकिन AI से मिली जानकारी को शेयर करने से पहले उसकी सच्चाई ज़रूर जाँचें।",
        "caption": "AI की दुनिया तेज़ी से बदल रही है! 🤯",
        "hashtags": ["#reels", "#viral", "#ai", "#india", "#trending"]
    }
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean) if clean else fallback
        if not isinstance(data, dict) or not data.get("script"):
            data = fallback
    except Exception:
        data = fallback
    topic = str(data.get("topic", "AI की जानकारी")).strip()[:100]
    script = str(data.get("script", fallback["script"])).strip()
    caption = str(data.get("caption", fallback["caption"])).strip()
    tags = data.get("hashtags", fallback["hashtags"])
    if not isinstance(tags, list):
        tags = fallback["hashtags"]
    tags = " ".join(str(t) for t in tags[:5])
    print("TOPIC:", topic, flush=True)

    audio_pcm = WORK / "voice.pcm"
    audio_wav = WORK / "voice.wav"
    raw_pcm = tts(script, str(audio_pcm))
    if raw_pcm:
        audio = audio_pcm
    elif local_voice(script, audio_wav):
        audio = audio_wav
    else:
        raise RuntimeError("Voice generation failed. Check Gemini TTS API access; espeak-ng fallback must be installed.")

    frames = [
        make_frame(topic, script, 1),
        make_frame(topic, script, 2),
        make_frame(topic, script, 3)
    ]
    mp4 = WORK / "reel.mp4"
    make_video(frames, audio, mp4, raw_pcm=raw_pcm)
    if not mp4.exists() or mp4.stat().st_size < 10000:
        raise RuntimeError("FFmpeg did not create a valid Reel video.")
    final_caption = f"{caption}\n\n{tags}"
    instagram(mp4, final_caption)

if __name__ == "__main__":
    main()
