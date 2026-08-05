# ============================================================
# ALPHA NEWS 6 - PRODUCTION
# BLOCK 1A
# Foundation
# ============================================================

import os
import re
import io
import json
import time
import logging
import traceback
import requests
import feedparser
import pdfplumber

from datetime import datetime, timedelta
from threading import Thread
from urllib.parse import urljoin

try:
    import fitz
except:
    fitz = None

try:
    from bs4 import BeautifulSoup
except:
    BeautifulSoup = None

from flask import Flask

# ============================================================
# HTTP SERVER
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Alpha News 6 Running"


def run_http():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )

# ============================================================
# CONFIG
# ============================================================

VERSION = "6.0.0"

BOT_TOKEN = os.environ.get("8638278037:AAGr9MKqQ045Hqa-f-godVUrQ7T9dnHt4a8", "")
CHAT_ID = os.environ.get("6315662736", "")

GEMINI_API_KEY = os.environ.get("AQ.Ab8RN6In2aXZmtWPH7oe7uy7WB3RRp3KXdoFBdnwqv_HcWD_wA", "")

ENABLE_AI = bool(GEMINI_API_KEY)

AI_MODEL = "gemini-2.5-flash"

CHECK_INTERVAL = 30

REQUEST_TIMEOUT = 20

MAX_RETRIES = 3

RETRY_DELAY = 3

ENABLE_LOGGING = True

ENABLE_RESULTS = True

ENABLE_PREOPEN = True

ENABLE_FNO = True

ENABLE_XBRL = True

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "Chrome/138 Safari/537.36"
)

# ============================================================
# NSE URLS
# ============================================================

NSE_HOME = "https://www.nseindia.com"

NSE_JSON = (
    "https://www.nseindia.com/api/"
    "corporate-announcements?index=equities"
)

RSS_URLS = {

    "announcements":
    "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",

    "board":
    "https://nsearchives.nseindia.com/content/RSS/BoardMeetings.xml",

    "actions":
    "https://nsearchives.nseindia.com/content/RSS/CorporateActions.xml"

}

# ============================================================
# GLOBAL CACHE
# ============================================================

processed_titles = set()

processed_links = set()

RESULT_CACHE = {}

COMPANY_CACHE = {}

PDF_CACHE = {}

AI_CACHE = {}

NETWORK_STATS = {

    "requests":0,
    "success":0,
    "failed":0

}

session = requests.Session()
# ============================================================
# BLOCK 1B
# LOGGING + TELEGRAM + TIME UTILITIES
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger("AlphaNews6")


def log(message, level="INFO"):

    if not ENABLE_LOGGING:
        return

    level = level.upper()

    if level == "ERROR":
        logger.error(message)

    elif level == "WARNING":
        logger.warning(message)

    else:
        logger.info(message)


session.headers.update({

    "User-Agent": USER_AGENT,

    "Accept":
    "application/json,text/html,"
    "application/xhtml+xml,"
    "application/xml;q=0.9,*/*;q=0.8",

    "Accept-Language":
    "en-US,en;q=0.9",

    "Connection":
    "keep-alive"

})


def send_telegram(message):

    if not BOT_TOKEN or not CHAT_ID:
        log("Telegram credentials missing", "ERROR")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {

        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True

    }

    try:

        response = session.post(
            url,
            data=payload,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code == 200:

            log("Telegram message sent")

            return True

        log(
            f"Telegram Error : {response.text}",
            "ERROR"
        )

        return False

    except Exception as e:

        log(
            f"Telegram Exception : {e}",
            "ERROR"
        )

        return False


def current_time():
    return datetime.now()


def current_time_string():
    return datetime.now().strftime("%H:%M:%S")


def today():
    return datetime.now().date()


log("=" * 60)
log("ALPHA NEWS 6 STARTING")
log(f"Version : {VERSION}")
log("=" * 60)
# ============================================================
# BLOCK 1C
# NETWORK + NSE SESSION
# ============================================================

NSE_READY = False

LAST_SESSION_REFRESH = None


def update_network_stats(success):

    NETWORK_STATS["requests"] += 1

    if success:
        NETWORK_STATS["success"] += 1
    else:
        NETWORK_STATS["failed"] += 1


def create_nse_session():

    global session
    global NSE_READY
    global LAST_SESSION_REFRESH

    try:

        session = requests.Session()

        session.headers.update({

            "User-Agent": USER_AGENT,

            "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8",

            "Accept-Language":
            "en-US,en;q=0.9",

            "Referer":
            "https://www.nseindia.com/",

            "Connection":
            "keep-alive"

        })

        response = session.get(

            NSE_HOME,

            timeout=REQUEST_TIMEOUT

        )

        if response.status_code == 200:

            NSE_READY = True

            LAST_SESSION_REFRESH = current_time()

            log("[NSE] Session Created")

            return True

        NSE_READY = False

        log(
            f"[NSE] HTTP {response.status_code}",
            "ERROR"
        )

        return False

    except Exception as e:

        NSE_READY = False

        log(
            f"[NSE] {e}",
            "ERROR"
        )

        return False


def refresh_nse_session():

    log("[NSE] Refreshing Session")

    return create_nse_session()


def safe_get(
    url,
    timeout=REQUEST_TIMEOUT,
    retries=MAX_RETRIES
):

    for attempt in range(retries):

        try:

            response = session.get(
                url,
                timeout=timeout
            )

            if response.status_code == 200:

                update_network_stats(True)

                return response

            if response.status_code in (401, 403):

                refresh_nse_session()

        except Exception as e:

            log(
                f"[NETWORK] {e}",
                "WARNING"
            )

        update_network_stats(False)

        time.sleep(RETRY_DELAY)

    return None


def download_json(url):

    response = safe_get(url)

    if response is None:
        return None

    try:

        return response.json()

    except Exception:

        return None


def download_text(url):

    response = safe_get(url)

    if response is None:
        return None

    return response.text


def download_xml(url):

    response = safe_get(url)

    if response is None:
        return None

    return feedparser.parse(response.text)
# ============================================================
# BLOCK 2A
# JSON + RSS CORE ENGINE
# ============================================================

JSON_STATS = {

    "checked":0,
    "success":0,
    "failed":0,
    "received":0,
    "duplicates":0

}

JSON_LAST_REFRESH = None


def update_json_refresh():

    global JSON_LAST_REFRESH

    JSON_LAST_REFRESH = current_time_string()


def is_duplicate_news(title, link):

    title = (title or "").strip()

    link = (link or "").strip()

    if title and title in processed_titles:
        return True

    if link and link in processed_links:
        return True

    return False


def mark_news_processed(title, link):

    if title:
        processed_titles.add(title.strip())

    if link:
        processed_links.add(link.strip())


def create_news_object(item):

    title = (
        item.get("attchmntText")
        or item.get("desc")
        or ""
    )

    attachment = item.get("attchmntFile","")

    pdf_url = ""

    if attachment:

        if attachment.startswith("http"):

            pdf_url = attachment

        else:

            pdf_url = (
                "https://nsearchives.nseindia.com"
                + attachment
            )

    return {

        "feed":"NSE",

        "title":title.strip(),

        "summary":
        item.get("desc","").strip(),

        "company":
        item.get("sm_name","").strip(),

        "symbol":
        item.get("symbol","").strip(),

        "published":
        item.get("an_dt","").strip(),

        "category":
        item.get("category","").strip(),

        "pdf_url":pdf_url,

        "link":pdf_url,

        "received_at":
        current_time_string()

    }


def initialize_json():

    JSON_STATS["checked"]=0
    JSON_STATS["success"]=0
    JSON_STATS["failed"]=0
    JSON_STATS["received"]=0
    JSON_STATS["duplicates"]=0

    log("[JSON] Engine Initialized")


initialize_json()
# ============================================================
# BLOCK 2B
# JSON DOWNLOADER
# ============================================================

def fetch_json_news():

    log("[JSON] Checking NSE Announcements...")

    try:

        data = download_json(NSE_JSON)

        if not data:

            JSON_STATS["checked"] += 1
            JSON_STATS["failed"] += 1

            return []

        JSON_STATS["checked"] += 1
        JSON_STATS["success"] += 1

        update_json_refresh()

        news_list = []

        for item in data:

            news = create_news_object(item)

            title = news["title"]
            link = news["link"]

            if is_duplicate_news(title, link):

                JSON_STATS["duplicates"] += 1
                continue

            mark_news_processed(title, link)

            news_list.append(news)

        JSON_STATS["received"] += len(news_list)

        log(
            f"[JSON] {len(news_list)} New Announcements"
        )

        return news_list

    except Exception as e:

        JSON_STATS["checked"] += 1
        JSON_STATS["failed"] += 1

        log(f"[JSON] {e}", "ERROR")

        return []


def fetch_rss_feed(feed_name):

    url = RSS_URLS.get(feed_name)

    if not url:
        return []

    feed = download_xml(url)

    if feed is None:
        return []

    items = []

    for entry in feed.entries:

        title = getattr(entry, "title", "").strip()

        link = getattr(entry, "link", "").strip()

        if is_duplicate_news(title, link):
            continue

        mark_news_processed(title, link)

        items.append({

            "feed": "RSS",

            "title": title,

            "summary":
            getattr(entry, "summary", ""),

            "company": "",

            "symbol": "",

            "published":
            getattr(entry, "published", ""),

            "category": feed_name,

            "pdf_url": "",

            "link": link,

            "received_at":
            current_time_string()

        })

    return items


def fetch_all_news():

    news = []

    news.extend(fetch_json_news())

    news.extend(fetch_rss_feed("announcements"))

    news.extend(fetch_rss_feed("board"))

    news.extend(fetch_rss_feed("actions"))

    return news


def startup_sync():

    log("[SYSTEM] Startup Sync")

    news = fetch_all_news()

    for item in news:

        mark_news_processed(

            item["title"],

            item["link"]

        )

    log("[SYSTEM] Startup Sync Complete")
# ============================================================
# BLOCK 2C
# PDF ENGINE
# ============================================================

def extract_pdf_text(pdf_url):

    if not pdf_url:
        return ""

    if pdf_url in PDF_CACHE:
        return PDF_CACHE[pdf_url]

    try:

        response = safe_get(pdf_url)

        if response is None:
            return ""

        pdf_data = io.BytesIO(response.content)

        text = ""

        # ---------- pdfplumber ----------

        if pdfplumber:

            try:

                with pdfplumber.open(pdf_data) as pdf:

                    for page in pdf.pages:

                        page_text = page.extract_text()

                        if page_text:

                            text += page_text + "\n"

            except Exception:

                text = ""

        # ---------- PyMuPDF Fallback ----------

        if not text and fitz:

            try:

                pdf_data.seek(0)

                doc = fitz.open(
                    stream=pdf_data.read(),
                    filetype="pdf"
                )

                for page in doc:

                    text += page.get_text()

            except Exception:

                text = ""

        text = text.strip()

        PDF_CACHE[pdf_url] = text

        if text:

            log(
                f"[PDF] Extracted {len(text)} characters"
            )

        else:

            log(
                "[PDF] Empty PDF",
                "WARNING"
            )

        return text

    except Exception as e:

        log(
            f"[PDF] {e}",
            "ERROR"
        )

        return ""


# ============================================================
# RESULT DETECTOR
# ============================================================

RESULT_KEYWORDS = [

    "financial results",

    "financial result",

    "quarterly results",

    "statement of standalone",

    "statement of consolidated",

    "unaudited financial",

    "audited financial",

    "earnings",

    "results for quarter",

    "results for the quarter"

]


def is_result_news(news):

    text = (

        news.get("title","") + " " +

        news.get("summary","")

    ).lower()

    for word in RESULT_KEYWORDS:

        if word in text:

            return True

    return False


def load_result_pdf(news):

    if not is_result_news(news):

        return ""

    pdf_url = news.get("pdf_url","")

    if not pdf_url:

        return ""

    log("[RESULT] Downloading PDF")

    pdf_text = extract_pdf_text(pdf_url)

    if pdf_text:

        log(

            f"[RESULT] PDF Loaded ({len(pdf_text)} chars)"

        )

    return pdf_text
# ============================================================
# BLOCK 3A
# AI ENGINE CORE
# ============================================================

HIGH_IMPACT = [

    "financial results",
    "quarterly results",
    "results",

    "order",
    "contract",

    "acquisition",
    "merger",

    "dividend",
    "bonus",
    "buyback",
    "stock split",

    "fraud",
    "default",
    "bankruptcy",
    "insolvency",

    "fire",
    "explosion",
    "accident",

    "sebi",

    "rating upgrade",
    "rating downgrade",

    "resignation",
    "appointment",

    "usfda",

    "plant shutdown",
    "factory shutdown",

    "capacity expansion",

    "rights issue",
    "preferential issue"

]

LOW_IMPACT = [

    "conference call",
    "earnings call",

    "audio recording",
    "webcast",

    "investor presentation",
    "presentation",

    "transcript",

    "analyst meet",

    "newspaper publication",

    "agm",
    "egm",

    "postal ballot"

]


def should_use_ai(news):

    if not ENABLE_AI:
        return False

    text = (

        news.get("title","") + " " +

        news.get("summary","")

    ).lower()

    for word in HIGH_IMPACT:

        if word in text:

            return True

    return False


def calculate_priority(news):

    text = (

        news.get("title","") + " " +

        news.get("summary","")

    ).lower()

    score = 5

    reason = "General"

    for word in HIGH_IMPACT:

        if word in text:

            score = 10

            reason = word

            break

    for word in LOW_IMPACT:

        if word in text:

            score = 2

            reason = word

            break

    return score, reason
# ============================================================
# BLOCK 3B
# GEMINI AI ENGINE
# ============================================================

AI_PROMPT = """
You are an Institutional Equity Research Analyst.

Analyze this NSE announcement.

Your task is NOT to summarize.

Estimate market reaction.

Use PDF financial data if available.

Return ONLY in this format:

Category:
Impact:
Sentiment:
Urgency:
Verdict:
Confidence:
Action:

Reasons:
- reason 1
- reason 2
- reason 3

Rules:

BUY only if genuinely bullish.

SELL only if genuinely bearish.

If information is insufficient return WATCH.

Never guess.
Use the extracted Financial Metrics before reading the PDF.

Analyze Revenue, PAT, EBITDA and EPS.

State whether each metric is Positive, Negative or Mixed.

If Financial Metrics and PDF conflict, trust the PDF.

Use financial numbers while deciding BUY, SELL or WATCH.
"""


def ai_analyze_news(news):

    if not ENABLE_AI:
        return None

    try:

        pdf_text = ""

metrics = {
    "revenue": "N/A",
    "pat": "N/A",
    "ebitda": "N/A",
    "eps": "N/A"
}

if news.get("pdf_url"):

    pdf_text = extract_pdf_text(
        news["pdf_url"]
    )[:12000]

    if pdf_text:

        metrics = extract_financial_metrics(pdf_text)

        result_quality = analyze_result_quality(pdf_text)

        prompt = f"""

{AI_PROMPT}

Company:
{news.get("company","")}

Symbol:
{news.get("symbol","")}

Title:
{news.get("title","")}

Summary:
{news.get("summary","")}
Financial Metrics (Auto Extracted)

Revenue:
{metrics["revenue"]}

PAT:
{metrics["pat"]}

EBITDA:
{metrics["ebitda"]}

EPS:
{metrics["eps"]}
Positive Triggers:
{", ".join(result_quality["positive"])}

Negative Triggers:
{", ".join(result_quality["negative"])}

Quality Score:
{result_quality["score"]}

PDF:

{pdf_text}

"""

        url = (
            "https://generativelanguage.googleapis.com/"
            "v1beta/models/"
            f"{AI_MODEL}:generateContent"
            f"?key={GEMINI_API_KEY}"
        )

        payload = {

            "contents":[

                {

                    "parts":[

                        {

                            "text":prompt

                        }

                    ]

                }

            ]

        }

        response = requests.post(

            url,

            json=payload,

            timeout=30

        )

        if response.status_code != 200:

            log(
                f"[AI] HTTP {response.status_code}",
                "ERROR"
            )

            return None

        data = response.json()

        return (

            data["candidates"][0]

            ["content"]["parts"][0]["text"]

        )

    except Exception as e:

        log(f"[AI] {e}","ERROR")

        return None
# ============================================================
# BLOCK 3C
# AI RESPONSE PARSER
# ============================================================

def parse_ai_response(ai_text):

    result = {

        "category": "General",

        "impact_score": 5,

        "sentiment": "Neutral",

        "urgency": "Low",

        "verdict": "WATCH",

        "confidence": 50,

        "action": "WATCH",

        "reasons": []

    }

    if not ai_text:

        return result

    try:

        lines = ai_text.splitlines()

        for line in lines:

            text = line.strip()

            lower = text.lower()

            if lower.startswith("category:"):

                result["category"] = text.split(":",1)[1].strip()

            elif lower.startswith("impact:"):

                value = text.split(":",1)[1].strip()

                try:

                    value = value.replace("/10","").strip()

                    result["impact_score"] = int(float(value))

                except:

                    pass

            elif lo