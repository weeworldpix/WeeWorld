import os
import json
import requests
import smtplib
import schedule
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta

# ── Config from environment variables ──────────────────────────────────────
GOOGLE_CLIENT_ID     = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
ANTHROPIC_API_KEY    = os.environ.get("ANTHROPIC_API_KEY")
GMAIL_ADDRESS        = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD   = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL      = os.environ.get("RECIPIENT_EMAIL")

def get_access_token():
    """Exchange refresh token for a fresh access token."""
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id":     GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": GOOGLE_REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    })
    return r.json().get("access_token")

def get_yesterdays_photos(access_token):
    """Fetch up to 5 photos taken yesterday from Google Photos."""
    yesterday = datetime.now() - timedelta(days=1)
    body = {
        "pageSize": 5,
        "filters": {
            "dateFilter": {
                "dates": [{
                    "year":  yesterday.year,
                    "month": yesterday.month,
                    "day":   yesterday.day,
                }]
            },
            "mediaTypeFilter": {"mediaTypes": ["PHOTO"]}
        }
    }
    r = requests.post(
        "https://photoslibrary.googleapis.com/v1/mediaItems:search",
        headers={"Authorization": f"Bearer {access_token}"},
        json=body
    )
    items = r.json().get("mediaItems", [])
    return items

def generate_captions(photo_count, date_str):
    """Ask Claude to write posts for all 3 platforms."""
    prompt = f"""You are a warm, creative social media manager for Mother Miracle LLC, a loving daycare in the DMV area.

Generate 3 social media posts for {photo_count} photo(s) taken yesterday ({date_str}) at the daycare.

Rules:
- NEVER use children's names — say "our little ones", "tiny explorers", "our kiddos"
- Warm, nurturing, joyful tone
- Highlight learning through play
- Make parents feel their children are loved and safe
- Each post tailored to the platform

Format EXACTLY like this:

[INSTAGRAM]
3-4 sentences. Visual, emotional, storytelling. End with a question.
#hashtag1 #hashtag2 (15-20 hashtags)

[FACEBOOK]
4-5 sentences. Conversational, speak directly to parents.
#hashtag1 #hashtag2 (5-7 hashtags)

[TIKTOK]
Start with a hook. 1-2 punchy sentences. Fun and energetic.
#hashtag1 #hashtag2 (8-10 hashtags)"""

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": prompt}]
        }
    )
    return r.json()["content"][0]["text"]

def extract_section(text, tag):
    import re
    m = re.search(rf'\[{tag}\]([\s\S]*?)(?=\[|$)', text)
    return m.group(1).strip() if m else ""

def build_email_html(captions, photos, date_str):
    instagram = extract_section(captions, "INSTAGRAM")
    facebook  = extract_section(captions, "FACEBOOK")
    tiktok    = extract_section(captions, "TIKTOK")

    photo_html = ""
    for p in photos[:3]:
        url = p.get("baseUrl", "") + "=w400-h400-c"
        photo_html += f'<img src="{url}" style="width:120px;height:120px;object-fit:cover;border-radius:10px;margin:4px;">'

    def post_block(platform, emoji, color, content):
        lines = content.split("\n")
        hi = next((i for i, l in enumerate(lines) if l.strip().startswith("#")), -1)
        caption  = "\n".join(lines[:hi]).strip()  if hi > -1 else content
        hashtags = "\n".join(lines[hi:]).strip()  if hi > -1 else ""
        return f"""
        <div style="background:#fff;border:1.5px solid #f0e8ec;border-radius:16px;padding:20px;margin-bottom:16px;">
          <div style="font-size:13px;font-weight:700;color:{color};margin-bottom:10px;">{emoji} {platform}</div>
          <div style="font-size:15px;line-height:1.7;color:#2d2d2d;white-space:pre-wrap;">{caption}</div>
          {f'<div style="margin-top:10px;font-size:13px;color:#8b6fd4;line-height:1.8;">{hashtags}</div>' if hashtags else ''}
        </div>"""

    return f"""
    <div style="font-family:'Nunito',Arial,sans-serif;max-width:600px;margin:0 auto;background:#fffafc;padding:24px;">
      <div style="background:linear-gradient(135deg,#e8748a,#8b6fd4);border-radius:16px;padding:24px;text-align:center;margin-bottom:24px;">
        <div style="font-size:32px;margin-bottom:8px;">🌟</div>
        <h1 style="color:white;margin:0;font-size:22px;">Mother Miracle</h1>
        <p style="color:rgba(255,255,255,0.85);margin:4px 0 0;font-size:14px;">Your daily social media posts — {date_str}</p>
      </div>

      {f'<div style="margin-bottom:20px;text-align:center;">{photo_html}</div>' if photo_html else ''}

      <p style="font-size:14px;color:#888;margin-bottom:16px;">✨ Here are today\'s ready-to-post captions. Just copy and paste!</p>

      {post_block("Instagram", "📸", "#E1306C", instagram)}
      {post_block("Facebook",  "👍", "#1877F2", facebook)}
      {post_block("TikTok",    "🎵", "#69C9D0", tiktok)}

      <div style="text-align:center;padding:16px;font-size:12px;color:#bbb;">
        Mother Miracle LLC · Powered by AI · Sent automatically every morning 🌸
      </div>
    </div>"""

def send_email(html, date_str, photo_count):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🌟 Mother Miracle — {photo_count} posts ready for {date_str}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Email sent to {RECIPIENT_EMAIL}")

def run_daily_job():
    print(f"🤖 Running daily job at {datetime.now()}")
    try:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
        token    = get_access_token()
        photos   = get_yesterdays_photos(token)
        count    = len(photos)
        print(f"📸 Found {count} photos from yesterday")
        if count == 0:
            print("No photos found — skipping email.")
            return
        captions = generate_captions(count, date_str)
        html     = build_email_html(captions, photos, date_str)
        send_email(html, date_str, count)
    except Exception as e:
        print(f"❌ Error: {e}")

# ── Schedule at 7am ET (11:00 UTC) ─────────────────────────────────────────
schedule.every().day.at("11:00").do(run_daily_job)

print("🌟 Mother Miracle Robot is running — posts will be emailed daily at 7am!")

# Run once immediately on startup for testing
run_daily_job()

while True:
    schedule.run_pending()
    time.sleep(60)
