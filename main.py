"""
Tk PowerHub WhatsApp Video-Edit Bot — webhook server (FastAPI).

Flow:
  1. User sends a VIDEO to the bot's WhatsApp number (optionally with a
     caption command, e.g. "hd" / "trim 0:05 0:20" / "text Bijli Tips").
  2. The server downloads the video via the WhatsApp Cloud API.
  3. ffmpeg edits it (video_edit.py).
  4. The edited video is uploaded back to WhatsApp and sent to the same chat.
  5. If the user sends only TEXT after a video, the bot applies that
     command to the last video they sent (kept briefly in memory).

Config is environment variables ONLY — never put tokens in this file:
  WHATSAPP_TOKEN   — Meta permanent/system-user access token
  PHONE_NUMBER_ID  — WhatsApp Business phone number id
  VERIFY_TOKEN     — any secret string you choose; must match the one
                     entered in Meta's webhook settings
  GRAPH_VERSION    — optional, default "v21.0"
  PORT             — optional, default 8000

Run locally:  uvicorn main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from video_edit import (
    EditError,
    add_brand,
    add_text,
    compress,
    enhance_hd,
    parse_timestamp,
    probe,
    trim,
)

# ---------------------------------------------------------------------------
# Config (env only)
# ---------------------------------------------------------------------------

WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v21.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"

WORK_DIR = Path(os.environ.get("BOT_WORK_DIR", "./work"))
WORK_DIR.mkdir(parents=True, exist_ok=True)

# Last video per sender (kept 10 minutes) so a command text sent after
# the video still works.
LAST_VIDEO: dict[str, dict] = {}
LAST_VIDEO_TTL = 600  # seconds

app = FastAPI(title="Tk PowerHub WhatsApp Video-Edit Bot")

# ---------------------------------------------------------------------------
# Roman Urdu replies
# ---------------------------------------------------------------------------

HELP_TEXT = (
    "Assalam o Alaikum! Main Tk PowerHub Video Edit Bot hun. 🎬\n\n"
    "Video bhejo, phir us ke saath ya baad mein ye likho:\n\n"
    "• hd — video ko 1080p HD banao\n"
    "• trim 0:05 0:20 — sirf 5 se 20 second ka hissa rakho\n"
    "• compress — halki chhoti file banao (phone par asani se chale)\n"
    "• text Bijli Tips — video par text likh do\n"
    "• brand — Tk PowerHub ka naam video par lagao\n"
    "• help — ye list dobara dikhao\n\n"
    "Kuch na likho to main khud halki HD wali video bana kar bhej dunga. "
    "Video 16 MB se bara nahi hona chahiye."
)

DONE_TEXT = "Ho gaya jani! ✅ Tumhari edited video upar hai. Aur kuch chahiye to video dobara bhejo ya naya command likho."
WORKING_TEXT = "Mil gayi video! 🎬 Edit kar raha hun, thori der mein bhejta hun..."
NO_VIDEO_TEXT = (
    "Pehle video bhejo, phir command likho. 📹\n\n"
    "Video bhejne ke baad 'help' likho, saare commands aa jayenge."
)
MISSING_SETUP_TEXT = (
    "Bot abhi poori tarah set nahi hai — server par WhatsApp token "
    "ya number id missing hai. Owner se rabta karo."
)


# ---------------------------------------------------------------------------
# WhatsApp Cloud API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}


async def send_text(to: str, body: str) -> None:
    url = f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        resp.raise_for_status()


async def get_media_url(media_id: str) -> str:
    url = f"{GRAPH_BASE}/{media_id}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, headers=_headers())
        resp.raise_for_status()
        return resp.json()["url"]


async def download_media(media_url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=300) as client:
        async with client.stream("GET", media_url, headers=_headers()) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as fh:
                async for chunk in resp.aiter_bytes(1024 * 256):
                    fh.write(chunk)


async def upload_media(path: Path) -> str:
    """Upload a video to WhatsApp, return its media id."""
    url = f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/media"
    async with httpx.AsyncClient(timeout=300) as client:
        with open(path, "rb") as fh:
            files = {"file": (path.name, fh, "video/mp4")}
            data = {"messaging_product": "whatsapp", "type": "video"}
            resp = await client.post(url, headers=_headers(), data=data, files=files)
            resp.raise_for_status()
            return resp.json()["id"]


async def send_video(to: str, media_id: str, caption: str = "") -> None:
    url = f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "video",
        "video": {"id": media_id, "caption": caption},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=_headers(), json=payload)
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Command parsing
# ---------------------------------------------------------------------------

def parse_command(text: str) -> dict:
    """Parse a command line into {'action': ..., ...}.

    Supported:
      hd | compress | brand | help
      trim <start> <end>     e.g. trim 0:05 0:20
      text <likhna>          e.g. text Bijli Tips Part 24
    Anything else -> {'action': 'unknown'}
    """
    text = (text or "").strip()
    low = text.lower()
    if low in ("help", "madad", "menu", "start", "hi", "hello", "salam"):
        return {"action": "help"}
    if low == "hd":
        return {"action": "hd"}
    if low == "compress":
        return {"action": "compress"}
    if low == "brand":
        return {"action": "brand"}
    if low.startswith("trim"):
        parts = text.split()
        if len(parts) == 3:
            try:
                return {
                    "action": "trim",
                    "start": parse_timestamp(parts[1]),
                    "end": parse_timestamp(parts[2]),
                }
            except EditError as exc:
                return {"action": "error", "message": str(exc)}
        return {
            "action": "error",
            "message": "Trim aise likho: trim 0:05 0:20 (start aur end time).",
        }
    if low.startswith("text "):
        body = text[5:].strip()
        if body:
            return {"action": "text", "text": body}
        return {"action": "error", "message": "Text khaali hai — 'text' ke baad kuch likho."}
    if low.startswith("text"):
        return {"action": "error", "message": "Text aise likho: text Bijli Tips"}
    return {"action": "unknown"}


def apply_edit(action: dict, src: Path, dst: Path) -> Path:
    """Run the ffmpeg edit for a parsed command. Returns the output path."""
    name = action["action"]
    if name == "hd":
        return Path(enhance_hd(str(src), str(dst)))
    if name == "compress":
        return Path(compress(str(src), str(dst)))
    if name == "brand":
        return Path(add_brand(str(src), str(dst)))
    if name == "trim":
        return Path(trim(str(src), str(dst), action["start"], action["end"]))
    if name == "text":
        return Path(add_text(str(src), str(dst), action["text"]))
    # default: light HD version
    return Path(compress(str(src), str(dst)))


# ---------------------------------------------------------------------------
# Webhook endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok", "bot": "Tk PowerHub WhatsApp Video-Edit Bot"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "whatsapp_configured": bool(WHATSAPP_TOKEN and PHONE_NUMBER_ID),
    }


@app.get("/webhook")
async def verify_webhook(request: Request):
    """Meta's webhook verification (GET)."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN and VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("verification failed", status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request):
    """Incoming WhatsApp messages (POST)."""
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=400)

    # Meta sends delivery/read receipts too — ignore anything without messages.
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                await handle_message(message)
    return Response(status_code=200)


async def handle_message(message: dict) -> None:
    sender = message.get("from", "")
    msg_type = message.get("type", "")
    if not sender:
        return

    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        try:
            await send_text(sender, MISSING_SETUP_TEXT)
        except Exception:
            pass
        return

    if msg_type == "video":
        await handle_video_message(sender, message)
    elif msg_type == "text":
        await handle_text_message(sender, message.get("text", {}).get("body", ""))
    else:
        await send_text(
            sender,
            "Main sirf video edit karta hun. 📹 Video bhejo, phir 'help' likho.",
        )


async def handle_video_message(sender: str, message: dict) -> None:
    video = message.get("video", {})
    media_id = video.get("id")
    caption = (video.get("caption") or "").strip()
    if not media_id:
        await send_text(sender, "Video nahi mili — dobara bhejo.")
        return

    await send_text(sender, WORKING_TEXT)

    job_id = uuid.uuid4().hex[:10]
    src = WORK_DIR / f"in_{job_id}.mp4"
    dst = WORK_DIR / f"out_{job_id}.mp4"
    try:
        media_url = await get_media_url(media_id)
        await download_media(media_url, src)
        info = probe(str(src))
        if info["duration"] > 300:
            await send_text(
                sender,
                "Video bohat lambi hai — 5 minute se zyada ki video edit nahi kar sakta. "
                "Chhota hissa bhejo.",
            )
            return

        LAST_VIDEO[sender] = {"path": str(src), "at": time.time()}

        if caption:
            cmd = parse_command(caption)
            if cmd["action"] == "help":
                await send_text(sender, HELP_TEXT)
                return
            if cmd["action"] == "error":
                await send_text(sender, cmd["message"])
                return
            if cmd["action"] == "unknown":
                await send_text(
                    sender,
                    "Ye command samajh nahi aayi. 'help' likho, saare commands aa jayenge.",
                )
                return
            out = apply_edit(cmd, src, dst)
        else:
            out = apply_edit({"action": "compress"}, src, dst)

        media_out = await upload_media(out)
        await send_video(sender, media_out)
        await send_text(sender, DONE_TEXT)
    except EditError as exc:
        await send_text(sender, f"Edit nahi ho saki: {exc}")
    except Exception as exc:  # network / WhatsApp API errors
        await send_text(sender, f"Kuch ghalat ho gaya, dobara try karo. ({type(exc).__name__})")
    finally:
        for p in (dst,):
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                pass


async def handle_text_message(sender: str, text: str) -> None:
    cmd = parse_command(text)
    if cmd["action"] == "help":
        await send_text(sender, HELP_TEXT)
        return
    if cmd["action"] == "error":
        await send_text(sender, cmd["message"])
        return
    if cmd["action"] == "unknown":
        await send_text(
            sender,
            "Ye command samajh nahi aayi. Pehle video bhejo, phir 'help' likho.",
        )
        return

    record = LAST_VIDEO.get(sender)
    if not record or time.time() - record["at"] > LAST_VIDEO_TTL:
        await send_text(sender, NO_VIDEO_TEXT)
        return

    src = Path(record["path"])
    if not src.exists():
        await send_text(sender, NO_VIDEO_TEXT)
        return

    await send_text(sender, WORKING_TEXT)
    job_id = uuid.uuid4().hex[:10]
    dst = WORK_DIR / f"out_{job_id}.mp4"
    try:
        out = apply_edit(cmd, src, dst)
        media_out = await upload_media(out)
        await send_video(sender, media_out)
        await send_text(sender, DONE_TEXT)
    except EditError as exc:
        await send_text(sender, f"Edit nahi ho saki: {exc}")
    except Exception as exc:
        await send_text(sender, f"Kuch ghalat ho gaya, dobara try karo. ({type(exc).__name__})")
    finally:
        try:
            if dst.exists():
                dst.unlink()
        except OSError:
            pass
