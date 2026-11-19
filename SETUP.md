# Tk PowerHub WhatsApp Video-Edit Bot — Setup Guide

> **Roman Urdu pehle, English neeche.** Ye bot aapki apni WhatsApp number
> par chalta hai: koi video bhejta hai, bot edit kar ke wapas bhej deta hai.

---

## Ye bot kya karta hai? (What does it do?)

Koi bhi shakhs aapke WhatsApp Business number par video bheje, bot ye
kar sakta hai:

| Command | Kaam |
|---|---|
| `hd` | Video ko 1080p HD banao |
| `trim 0:05 0:20` | Sirf 5 se 20 second ka hissa rakho |
| `compress` | Halki chhoti file banao (phone par asani se chale) |
| `text Bijli Tips` | Video par text likh do |
| `brand` | Video par "Tk PowerHub" likh do |
| `help` | Saare commands dikhao |

Kuch na likho to bot khud halki HD wali video bana kar bhej dega.

**Ehem baat (honest):** Ye bot sirf **ffmpeg editing** karta hai — trim,
compress, HD, text, brand. Is mein **AI video generation nahi hai**. Aur ye
bot **phone se akela nahi chal sakta** — is ke liye ek chhota server chahiye
jo internet par 24 ghante on rahe, kyunke Meta (WhatsApp) ko us server ka
public link (webhook URL) chahiye hota hai.

---

## Aap ko kya kya chahiye (What you need)

1. **Meta developer account** — free, developers.facebook.com par apne
   Facebook account se login karo.
2. **WhatsApp Business number** — ek alag number behtar hai (aapka personal
   WhatsApp number is par **nahi** chalna chahiye — Cloud API number par
   WhatsApp app login nahi rehta). Agar naya number nahi hai, Meta test
   number se shuru kar sakte ho, phir apna business number jor lo.
3. **Server hosting** — free options: **Render** (render.com) ya **Railway**
   (railway.app). Dono par free plan hai. Server par Python + ffmpeg hona
   chahiye — Render par ye `render.yaml` / build command se hota hai
   (neeche dekho).
4. **Ye bot ka code** — is folder ki files (`main.py`, `video_edit.py`,
   `requirements.txt`).

---

## Step by step — Meta side (pehli dafa, ~20 minute)

### Step 1 — Meta app banao
1. https://developers.facebook.com/apps kholo, **Create App** dabao.
2. App type: **Other** → **Business** chuno.
3. App ka naam likho: `Tk PowerHub Video Bot` → **Create App**.

### Step 2 — WhatsApp product joro
1. App ke dashboard mein **Add Product** → **WhatsApp** → **Set up**.
2. **API Setup** page par jao. Wahan se 2 cheezein note karo:
   - **Phone number ID** (ek lamba number) → ye `PHONE_NUMBER_ID` hai.
   - **Temporary access token** (24 ghante ka hota hai) — is se test karo.
3. **Permanent token** ke liye: Meta Business Settings → System Users →
   naya system user banao → us ko WhatsApp app ka access do →
   **Generate New Token** (permission: `whatsapp_business_messaging`,
   `whatsapp_business_management`) → ye `WHATSAPP_TOKEN` hai.
   ⚠️ Token kisi ko mat bhejo, sirf server ke env mein daalo.

### Step 3 — Test number par message bhejo (optional, free)
API Setup page par **Step 1** mein apna personal WhatsApp number daal kar
**Send Message** se test karo — pehle test number se message aayega.

---

## Step by step — Server side (Render, free plan)

1. Is folder ko GitHub par daalo (private repo theek hai).
2. https://dashboard.render.com → **New +** → **Web Service** → GitHub
   repo chuno.
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment:** `Python 3`
   - ffmpeg Render par pehle se hota hai (agar na ho to
     `apt.txt` mein `ffmpeg` likh kar dobara deploy karo).
4. **Environment Variables** mein ye 3 daalo (Render dashboard → Environment):
   - `WHATSAPP_TOKEN` = Step 2 wala permanent token
   - `PHONE_NUMBER_ID` = Step 2 wala phone number ID
   - `VERIFY_TOKEN` = koi secret string khud banao (jaise
     `tkpowerhub-verify-2026-xyz`) — ye Meta mein bhi same likhna hai
5. **Deploy** dabao. Deploy hone ke baad Render aap ko ek public URL dega,
   jaise: `https://tk-video-bot.onrender.com`

> Railway par bhi same hai: repo connect karo, variables daalo, deploy karo.

---

## Step 4 — Webhook joro (Meta ko server ka link do)

1. Meta App → **WhatsApp** → **Configuration** → **Webhook** → **Edit**.
2. **Callback URL:** `https://tk-video-bot.onrender.com/webhook`
   (apna Render URL likho, aakhir mein `/webhook` zaroor).
3. **Verify token:** wahi secret jo Render mein `VERIFY_TOKEN` mein daala tha.
4. **Verify and Save** dabao — Meta server ko check karega. Agar green
   tick aa gaya to webhook jud gaya. ✅
5. Neeche **Webhook fields** mein **messages** ko subscribe karo
   (tick lagao) — isi se video messages bot tak aayenge.

---

## Step 5 — Number register karo (apna business number)

1. Meta App → **WhatsApp** → **API Setup** → **Step 5: Add a phone number**.
2. Apna business number daalo → OTP aayega → verify karo.
3. Is number par ab WhatsApp **app** login nahi rahega — saare messages bot
   sambhalega. Is liye alag number use karo, personal number nahi.

---

## Test karo (How to test)

1. Apne personal WhatsApp se bot wale number par ek chhoti video bhejo.
2. Caption mein likho: `compress`
3. Bot jawab dega: "Mil gayi video! Edit kar raha hun..." phir edited
   video wapas bhej dega.
4. Phir test karo: video bhejo + caption `text Bijli Tips Part 24`.
5. Koi masla ho to Render ke **Logs** dekho — wahan error likha hoga.

---

## Commands — user ke liye (Roman Urdu)

Bot par `help` likhne se ye list aati hai:

- `hd` — video ko 1080p HD banao
- `trim 0:05 0:20` — sirf 5 se 20 second ka hissa rakho
- `compress` — halki chhoti file banao
- `text Bijli Tips` — video par text likh do
- `brand` — Tk PowerHub ka naam video par lagao
- `help` — ye list dobara dikhao

Video ke saath caption mein command likho, ya video bhejne ke **10 minute
ke andar** alag message mein command likho — dono tareeqe chalte hain.

---

## Limits (Seedhi baatein)

- **Video 5 minute se zyada lambi nahi** — lambi video reject ho jayegi.
- **WhatsApp video 16 MB se bara nahi bhejta** — bot output ko khud
  15 MB ke andar rakhta hai; agar phir bhi bara ho to `trim` se chhota
  hissa bhejo.
- **AI generation nahi hai** — bot video banata nahi, sirf edit karta hai
  (trim/compress/HD/text/brand).
- **Server 24 ghante on rehna chahiye** — Render free plan par server
  15 minute khamoshi ke baad "so" jata hai; pehla message 30–60 second
  late aa sakta hai. Paid plan ($7/month) par hamesha on rehta hai.
- **Ek number = ek bot** — jo number register karo ge, us par WhatsApp
  app nahi chalegi. Personal number mat do.
- **Token secret hai** — `WHATSAPP_TOKEN` kisi se share mat karo. Agar
  leak ho jaye to Meta se naya token banao.

---

## Files is folder mein

| File | Kaam |
|---|---|
| `main.py` | Webhook server (FastAPI) — WhatsApp se baat karta hai |
| `video_edit.py` | ffmpeg editing (compress/hd/trim/text/brand) |
| `requirements.txt` | Python packages |
| `.env.example` | Settings ki misaal — isay copy kar ke `.env` banao |
| `test_pipeline.py` | Bina WhatsApp ke editing test (sample video par) |
| `SETUP.md` | Ye guide |

Local test (bina WhatsApp ke):

```bash
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
./venv/bin/python test_pipeline.py        # editing pipeline test
VERIFY_TOKEN=test-123 ./venv/bin/uvicorn main:app --port 8000
# phir browser mein: http://127.0.0.1:8000/health
```

---

## English (short version)

1. Create a Meta developer app, add the **WhatsApp** product, note the
   **Phone number ID**, and create a **permanent system-user token**
   (`whatsapp_business_messaging`).
2. Deploy this folder on **Render** (free) or **Railway**: build
   `pip install -r requirements.txt`, start
   `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set env vars
   `WHATSAPP_TOKEN`, `PHONE_NUMBER_ID`, `VERIFY_TOKEN`.
3. In Meta App → WhatsApp → Configuration, set the webhook callback URL
   to `https://<your-app>.onrender.com/webhook` with the same verify
   token, and subscribe to the **messages** field.
4. Register a (separate) business phone number. Send a video to it with
   caption `compress` to test.
5. Limits: 5-minute max video, 16 MB WhatsApp cap, no AI generation,
   free Render sleeps after 15 min idle, the registered number cannot
   also run the WhatsApp app.
