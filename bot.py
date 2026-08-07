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

        result_quality = {
            "positive": [],
            "negative": [],
            "score": 0
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

        return data["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:

        log(f"[AI] {e}", "ERROR")

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

            elif lower.startswith("sentiment:"):

                result["sentiment"] = text.split(":",1)[1].strip()

            elif lower.startswith("urgency:"):

                result["urgency"] = text.split(":",1)[1].strip()

            elif lower.startswith("verdict:"):

                result["verdict"] = text.split(":",1)[1].strip()

            elif lower.startswith("confidence:"):

                value = text.split(":",1)[1]

                value = value.replace("%","").strip()

                try:

                    result["confidence"] = int(float(value))
                except:
                    pass

            elif lower.startswith("action:"):

                result["action"] = text.split(":",1)[1].strip().upper()

            elif text.startswith("-"):

                result["reasons"].append(

                    text.replace("-","").strip()

                )

    except Exception as e:

        log(f"[AI Parser] {e}", "ERROR")

    return result


def apply_ai_result(news, ai_text):

    parsed = parse_ai_response(ai_text)

    news["category"] = parsed["category"]

    news["impact_score"] = parsed["impact_score"]

    news["sentiment"] = parsed["sentiment"]

    news["urgency"] = parsed["urgency"]

    news["verdict"] = parsed["verdict"]

    news["confidence"] = parsed["confidence"]

    news["action"] = parsed["action"]

    news["reasons"] = parsed["reasons"]

    news["ai_analysis"] = ai_text

    return news
# ============================================================
# BLOCK 4A
# RESULT ANALYZER ENGINE
# ============================================================

RESULT_FIELDS = {

    "revenue":[
        "revenue",
        "total income",
        "income from operations",
        "net sales"
    ],

    "ebitda":[
        "ebitda"
    ],

    "pat":[
        "profit after tax",
        "net profit",
        "profit for the period"
    ],

    "eps":[
        "eps",
        "earnings per share"
    ],

    "debt":[
        "debt",
        "borrowings"
    ],

    "guidance":[
        "guidance",
        "outlook"
    ]

}


def search_keywords(text, keywords):

    text = text.lower()

    for word in keywords:

        if word.lower() in text:
            return True

    return False


def analyze_result_pdf(pdf_text):

    report = {

        "Revenue": False,

        "EBITDA": False,

        "PAT": False,

        "EPS": False,

        "Debt": False,

        "Guidance": False

    }

    if not pdf_text:

        return report

    for field, words in RESULT_FIELDS.items():

        if search_keywords(pdf_text, words):

            if field == "revenue":
                report["Revenue"] = True

            elif field == "ebitda":
                report["EBITDA"] = True

            elif field == "pat":
                report["PAT"] = True

            elif field == "eps":
                report["EPS"] = True

            elif field == "debt":
                report["Debt"] = True

            elif field == "guidance":
                report["Guidance"] = True

    return report

# ============================================================
# BLOCK 4B
# RESULT GROWTH ANALYZER
# ============================================================

POSITIVE_PATTERNS = [

    "grew",
    "growth",
    "increase",
    "increased",
    "higher",
    "improved",
    "record high",
    "strong demand",
    "margin expanded",
    "highest ever",
    "all time high"

]

NEGATIVE_PATTERNS = [

    "decline",
    "declined",
    "decrease",
    "decreased",
    "lower",
    "loss",
    "loss widened",
    "margin contraction",
    "weak demand",
    "shutdown",
    "fire",
    "accident"

]


def detect_growth_sentiment(pdf_text):

    if not pdf_text:

        return {

            "positive": 0,

            "negative": 0

        }

    text = pdf_text.lower()

    positive = 0

    negative = 0

    for word in POSITIVE_PATTERNS:

        if word in text:

            positive += 1

    for word in NEGATIVE_PATTERNS:

        if word in text:

            negative += 1

    return {

        "positive": positive,

        "negative": negative

    }


def result_score(report, sentiment):

    score = 5

    reasons = []

    if report["Revenue"]:

        score += 1

        reasons.append("Revenue Found")

    if report["EBITDA"]:

        score += 1

        reasons.append("EBITDA Found")

    if report["PAT"]:

        score += 1

        reasons.append("PAT Found")

    if report["EPS"]:

        score += 1

        reasons.append("EPS Found")

    if report["Guidance"]:

        score += 1

        reasons.append("Management Guidance")

    score += sentiment["positive"]

    score -= sentiment["negative"]

    score = max(1, min(score, 10))

    return score, reasons
# ============================================================
# BLOCK 4C
# RESULT + AI MERGE ENGINE
# ============================================================

def analyze_result_news(news):

    pdf_text = load_result_pdf(news)

    if not pdf_text:
        return news

    report = analyze_result_pdf(pdf_text)

    # Auto Extract Financial Metrics
    news["financial_metrics"] = extract_financial_metrics(pdf_text)

    # Auto Result Quality
    news["result_quality"] = analyze_result_quality(pdf_text)

    sentiment = detect_growth_sentiment(pdf_text)

    result_score_value, result_reasons = result_score(
        report,
        sentiment
    )

    news["result_score"] = result_score_value

    news["result_report"] = report

    if "reasons" not in news:
        news["reasons"] = []

    news["reasons"].extend(result_reasons)

    # AI handled later in finalize_analysis()

    if result_score_value >= 8:

        news["impact_score"] = max(
            news.get("impact_score", 0),
            result_score_value
        )

        news["sentiment"] = "Bullish"
        news["action"] = "BUY"
        news["verdict"] = "RESULT POSITIVE"
        news["confidence"] = 85

    elif result_score_value <= 3:

        news["impact_score"] = result_score_value
        news["sentiment"] = "Bearish"
        news["action"] = "SELL"
        news["verdict"] = "RESULT NEGATIVE"
        news["confidence"] = 85

    else:

        news["impact_score"] = result_score_value
        news["sentiment"] = "Neutral"
        news["action"] = "WATCH"
        news["verdict"] = "MIXED RESULT"
        news["confidence"] = 70

    return news
# ============================================================
# BLOCK 5A
# MATERIAL EVENT ENGINE
# ============================================================

MATERIAL_EVENTS = {

    "fire": {
        "score": 10,
        "sentiment": "Bearish",
        "action": "SELL"
    },

    "explosion": {
        "score": 10,
        "sentiment": "Bearish",
        "action": "SELL"
    },

    "accident": {
        "score": 9,
        "sentiment": "Bearish",
        "action": "SELL"
    },

    "plant shutdown": {
        "score": 10,
        "sentiment": "Bearish",
        "action": "SELL"
    },

    "factory shutdown": {
        "score": 10,
        "sentiment": "Bearish",
        "action": "SELL"
    },

    "usfda": {
        "score": 9,
        "sentiment": "Mixed",
        "action": "WATCH"
    },

    "warning letter": {
        "score": 9,
        "sentiment": "Bearish",
        "action": "SELL"
    },

    "sebi": {
        "score": 8,
        "sentiment": "Mixed",
        "action": "WATCH"
    },

    "search operation": {
        "score": 10,
        "sentiment": "Bearish",
        "action": "SELL"
    },

    "income tax": {
        "score": 8,
        "sentiment": "Bearish",
        "action": "WATCH"
    },

    "resignation": {
        "score": 8,
        "sentiment": "Mixed",
        "action": "WATCH"
    },

    "death": {
        "score": 10,
        "sentiment": "Bearish",
        "action": "SELL"
    }

}


def detect_material_event(news):

    text = (

        news.get("title","") + " " +

        news.get("summary","")

    ).lower()

    for keyword, data in MATERIAL_EVENTS.items():

        if keyword in text:

            news["category"] = "Material Event"

            news["impact_score"] = max(

                news.get("impact_score",5),

                data["score"]

            )

            news["sentiment"] = data["sentiment"]

            news["action"] = data["action"]

            news["confidence"] = 90

            if "reasons" not in news:

                news["reasons"] = []

            news["reasons"].append(

                f"Material Event : {keyword}"

            )

            return True

    return False
# ============================================================
# BLOCK 5B
# SMART MATERIAL EVENT ENGINE
# ============================================================

POSITIVE_MODIFIERS = [

    "operations unaffected",
    "business unaffected",
    "fully insured",
    "adequately insured",
    "insurance claim",
    "no material impact",
    "production resumed",
    "normal operations",
    "contained quickly"

]

NEGATIVE_MODIFIERS = [

    "production stopped",
    "operations stopped",
    "major damage",
    "significant damage",
    "plant closed",
    "factory closed",
    "material impact",
    "shutdown",
    "fatality"

]


def refine_material_event(news):

    text = (

        news.get("title","") + " " +

        news.get("summary","")

    ).lower()

    positive = 0

    negative = 0

    for word in POSITIVE_MODIFIERS:

        if word in text:

            positive += 1

    for word in NEGATIVE_MODIFIERS:

        if word in text:

            negative += 1

    if positive > negative:

        news["impact_score"] = max(

            5,

            news["impact_score"] - 3

        )

        news["action"] = "WATCH"

        news["confidence"] = 75

        news["reasons"].append(

            "Operations appear unaffected"

        )

    elif negative > positive:

        news["impact_score"] = min(

            10,

            news["impact_score"] + 1

        )

        news["action"] = "SELL"

        news["confidence"] = 95

        news["reasons"].append(

            "Material operational disruption"

        )

    return news
# ============================================================
# BLOCK 5C
# ORDER / CAPEX / EXPANSION ENGINE
# ============================================================

POSITIVE_EVENTS = {

    "order": (9, "BUY"),

    "contract": (9, "BUY"),

    "letter of award": (10, "BUY"),

    "work order": (9, "BUY"),

    "capacity expansion": (8, "BUY"),

    "plant expansion": (8, "BUY"),

    "commercial production": (8, "BUY"),

    "commissioned": (8, "BUY"),

    "new project": (8, "BUY"),

    "long term agreement": (9, "BUY"),

    "strategic partnership": (8, "BUY"),

    "joint venture": (8, "WATCH"),

    "export order": (9, "BUY"),

    "repeat order": (9, "BUY")

}


def detect_positive_event(news):

    text = (

        news.get("title","") + " " +

        news.get("summary","")

    ).lower()

    for keyword, data in POSITIVE_EVENTS.items():

        if keyword in text:

            score, action = data

            news["category"] = "Business Update"

            news["impact_score"] = max(

                news.get("impact_score",5),

                score

            )

            news["sentiment"] = "Bullish"

            news["action"] = action

            news["confidence"] = max(

                news.get("confidence",70),

                90

            )

            if "reasons" not in news:

                news["reasons"] = []

            news["reasons"].append(

                f"Business Event : {keyword}"

            )

            return True

    return False
# ============================================================
# BLOCK 6A
# MASTER ANALYSIS ENGINE
# ============================================================

def analyze_news(news):

    # Default Values

    news.setdefault("impact_score", 5)
    news.setdefault("category", "General")
    news.setdefault("sentiment", "Neutral")
    news.setdefault("urgency", "Medium")
    news.setdefault("action", "WATCH")
    news.setdefault("confidence", 50)
    news.setdefault("reasons", [])

    # -------------------------------
    # Result Engine
    # -------------------------------

    if is_result_news(news):
        news = analyze_result_news(news)

    # -------------------------------
    # Material Events
    # -------------------------------

    if detect_material_event(news):
        news = refine_material_event(news)

    # -------------------------------
    # Business Events
    # -------------------------------

    detect_positive_event(news)

    # IMPORTANT:
    # AI yahan call NAHI hogi.
    # AI sirf finalize_analysis() me chalegi.

    news["impact_score"] = max(1, min(news["impact_score"], 10))
    news["confidence"] = max(40, min(news["confidence"], 99))

    return news

    # --------------------------------
    # Final Verdict
    # --------------------------------

    if news["impact_score"] >= 9:

        if news["sentiment"].lower().startswith("bear"):

            news["verdict"] = "🔻 STRONG SELL"

        else:

            news["verdict"] = "🚀 STRONG BUY"

    elif news["impact_score"] >= 7:

        if news["sentiment"].lower().startswith("bear"):

            news["verdict"] = "📉 SELL"

        else:

            news["verdict"] = "📈 BUY"

    else:

        news["verdict"] = "👀 WATCH"

    return news
# ============================================================
# BLOCK 6B
# AI BUDGET MANAGER + FINAL DECISION ENGINE
# ============================================================

def finalize_analysis(news):

    # ---------------------------------------
    # AI CALL ONLY ONCE
    # ---------------------------------------

    ai_used = False

    if should_use_ai(news):

        ai_text = ai_analyze_news(news)

        if ai_text:

            news = apply_ai_result(news, ai_text)

            ai_used = True

    # ---------------------------------------
    # FALLBACK ENGINE
    # ---------------------------------------

    if not ai_used:

        score = news.get("impact_score", 5)

        sentiment = news.get("sentiment", "Neutral")

        if score >= 9:

            if sentiment.lower().startswith("bear"):

                news["action"] = "SELL"

                news["verdict"] = "🔻 STRONG SELL"

            else:

                news["action"] = "BUY"

                news["verdict"] = "🚀 STRONG BUY"

        elif score >= 7:

            if sentiment.lower().startswith("bear"):

                news["action"] = "SELL"

                news["verdict"] = "📉 SELL"

            else:

                news["action"] = "BUY"

                news["verdict"] = "📈 BUY"

        else:

            news["action"] = "WATCH"

            news["verdict"] = "👀 WATCH"

    # ---------------------------------------
    # LIMITS
    # ---------------------------------------

    news["impact_score"] = max(
        1,
        min(news.get("impact_score", 5), 10)
    )

    news["confidence"] = max(
        40,
        min(news.get("confidence", 50), 99)
    )

    return news


# ============================================================
# COMPLETE ANALYSIS
# ============================================================

def complete_analysis(news):

    news = analyze_news(news)

    news = finalize_analysis(news)

    return news
  # ============================================================
# BLOCK 7A
# TELEGRAM MESSAGE FORMATTER
# ============================================================

def format_news_message(news):

    message = ""

    score = news.get("impact_score", 5)

    if score >= 9:
        impact = "🚨 HIGH IMPACT"
    elif score >= 7:
        impact = "⚡ MEDIUM IMPACT"
    else:
        impact = "ℹ️ LOW IMPACT"

    message += "📢 <b>ALPHA NEWS 6</b>\n"
    message += impact + "\n\n"

    message += f"🏢 <b>Company :</b> {news.get('company','N/A')}\n"
    message += f"📈 <b>Symbol :</b> {news.get('symbol','N/A')}\n\n"

    message += f"📰 <b>{news.get('title','')}</b>\n\n"

    message += "━━━━━━━━━━━━━━━━━━\n"

    message += f"📂 Category : {news.get('category','General')}\n"
    message += f"📊 Impact : {news.get('impact_score',5)}/10\n"
    message += f"📈 Sentiment : {news.get('sentiment','Neutral')}\n"
    message += f"⚡ Urgency : {news.get('urgency','Low')}\n"
    message += f"🎯 Confidence : {news.get('confidence',50)}%\n"
    message += f"💹 Action : <b>{news.get('action','WATCH')}</b>\n"
    message += f"🤖 Verdict : <b>{news.get('verdict','WATCH')}</b>\n"

    if news.get("result_score") is not None:

        message += (
            f"\n📑 Result Score : "
            f"{news.get('result_score')}/10\n"
        )

    if news.get("financial_metrics"):

        fm = news["financial_metrics"]

        message += (
            "\n📊 <b>Financial Metrics</b>\n"
            f"💰 Revenue : {fm.get('revenue','N/A')}\n"
            f"🏦 PAT : {fm.get('pat','N/A')}\n"
            f"📈 EBITDA : {fm.get('ebitda','N/A')}\n"
            f"🎯 EPS : {fm.get('eps','N/A')}\n"
        )

    if news.get("result_quality"):

        rq = news["result_quality"]

        message += (
            f"\n⭐ <b>Quality Score :</b> "
            f"{rq.get('score',0)}/10\n"
        )

        if rq.get("positive"):

            message += "\n✅ <b>Positive Triggers</b>\n"

            for item in rq["positive"]:
                message += f"• {item}\n"

        if rq.get("negative"):

            message += "\n❌ <b>Negative Triggers</b>\n"

            for item in rq["negative"]:
                message += f"• {item}\n"

    reasons = news.get("reasons", [])

    if reasons:

        message += "\n📌 <b>Reasons</b>\n"

        for reason in reasons[:5]:
            message += f"• {reason}\n"

    if news.get("ai_analysis"):

        message += (
            "\n━━━━━━━━━━━━━━━━━━\n"
            "<b>🤖 AI Analysis</b>\n\n"
        )

        message += news["ai_analysis"].strip()

    if news.get("published"):

        message += (
            f"\n\n🕒 {news['published']}"
        )

    if news.get("link"):

        message += (
            f"\n🔗 {news['link']}"
        )

    return message
    # ============================================================
# BLOCK 7B
# TELEGRAM SEND ENGINE
# ============================================================

def send_news(news):

    try:

        message = format_news_message(news)

        success = send_telegram(message)

        if success:

            log(

                f"[TELEGRAM] Sent : "

                f"{news.get('company','Unknown')}"

            )

        else:

            log(

                "[TELEGRAM] Send Failed",

                "ERROR"

            )

    except Exception as e:

        log(

            f"[TELEGRAM] {e}",

            "ERROR"

        )


def send_startup_message():

    message = (

        "✅ <b>ALPHA NEWS 6 STARTED</b>\n\n"

        f"Version : {VERSION}\n"

        f"Time : {current_time_string()}\n\n"

        "🚀 Live Monitoring Started"

    )

    send_telegram(message)


def send_health_message():

    message = (

        "💚 <b>ALPHA NEWS HEALTH CHECK</b>\n\n"

        f"Requests : {NETWORK_STATS['requests']}\n"

        f"Success : {NETWORK_STATS['success']}\n"

        f"Failed : {NETWORK_STATS['failed']}\n"

        f"Time : {current_time_string()}"

    )

    send_telegram(message)
    # ============================================================
# BLOCK 7C
# NEWS PROCESSING ENGINE
# ============================================================

MIN_IMPACT_SCORE = 7


def process_news(news_list):

    if not news_list:

        return

    log(f"[ENGINE] Processing {len(news_list)} news")

    for news in news_list:

        try:

            # Complete Analysis
            news = complete_analysis(news)

            score = news.get("impact_score", 0)

            # Ignore low impact news
            if score < MIN_IMPACT_SCORE:

                log(
                    f"[FILTER] Ignored ({score}/10) : "
                    f"{news.get('title','')}"
                )

                continue

            # Send Telegram
            send_news(news)

            log(
                f"[SENT] "
                f"{news.get('company','Unknown')} | "
                f"{score}/10 | "
                f"{news.get('action','WATCH')}"
            )

        except Exception as e:

            log(
                f"[PROCESS] {e}",
                "ERROR"
            )

            traceback.print_exc()
            # ============================================================
# BLOCK 8A
# MAIN LOOP ENGINE
# ============================================================

def main_loop():

    log("=" * 60)
    log("LIVE MONITORING STARTED")
    log("=" * 60)

    startup_sync()

    while True:

        try:

            news_list = fetch_all_news()

            if news_list:

                process_news(news_list)

            else:

                log("[ENGINE] No New Announcements")

        except KeyboardInterrupt:

            log("[SYSTEM] Bot Stopped By User")

            break

        except Exception as e:

            log(f"[MAIN LOOP] {e}", "ERROR")

            traceback.print_exc()

        time.sleep(CHECK_INTERVAL)
        # ============================================================
# BLOCK 8B
# STARTUP + RUN ENGINE
# ============================================================

def startup():

    log("=" * 60)
    log("ALPHA NEWS 6 INITIALIZING...")
    log("=" * 60)

    create_nse_session()

    send_startup_message()

    startup_sync()

    log("[SYSTEM] Startup Complete")


def main():

    startup()

    main_loop()



        
# ============================================================
# BLOCK 7A
# RESULT METRICS EXTRACTOR
# ============================================================

RESULT_PATTERNS = {

    "revenue": [
        r"Revenue\s+from\s+Operations[:\s₹]*([\d,\.]+)",
        r"Total\s+Income[:\s₹]*([\d,\.]+)"
    ],

    "pat": [
        r"Net\s+Profit[:\s₹]*([\d,\.\-\(\)]+)",
        r"Profit\s+After\s+Tax[:\s₹]*([\d,\.\-\(\)]+)",
        r"PAT[:\s₹]*([\d,\.\-\(\)]+)"
    ],

    "ebitda": [
        r"EBITDA[:\s₹]*([\d,\.\-\(\)]+)"
    ],

    "eps": [
        r"EPS[:\s₹]*([\d,\.\-]+)",
        r"Earnings\s+Per\s+Share[:\s₹]*([\d,\.\-]+)"
    ]
}


def extract_financial_metrics(pdf_text):

    result = {
        "revenue": "N/A",
        "pat": "N/A",
        "ebitda": "N/A",
        "eps": "N/A"
    }

    if not pdf_text:
        return result

    for key, patterns in RESULT_PATTERNS.items():

        for pattern in patterns:

            match = re.search(
                pattern,
                pdf_text,
                flags=re.I
            )

            if match:
                result[key] = match.group(1).strip()
                break

    return result
    # ============================================================
# BLOCK 7C
# RESULT QUALITY ANALYZER
# ============================================================

POSITIVE_RESULT_WORDS = [

    "record revenue",
    "record profit",
    "highest ever",
    "margin expansion",
    "strong growth",
    "order book",
    "guidance raised",
    "debt reduced",
    "cash increased",
    "capacity expansion",
    "robust demand",
    "improved margin",
    "strong cash flow"

]

NEGATIVE_RESULT_WORDS = [

    "loss",
    "net loss",
    "margin pressure",
    "guidance cut",
    "weak demand",
    "decline",
    "lower revenue",
    "profit declined",
    "debt increased",
    "impairment",
    "shutdown",
    "exceptional loss",
    "cash burn"

]


def analyze_result_quality(pdf_text):

    report = {
        "positive": [],
        "negative": [],
        "score": 0
    }

    if not pdf_text:
        return report

    text = pdf_text.lower()

    for word in POSITIVE_RESULT_WORDS:
        if word in text:
            report["positive"].append(word)
            report["score"] += 1

    for word in NEGATIVE_RESULT_WORDS:
        if word in text:
            report["negative"].append(word)
            report["score"] -= 1

    return report


if __name__ == "__main__":

    Thread(
        target=run_http,
        daemon=True
    ).start()

    try:
        main()

    except KeyboardInterrupt:
        log("[SYSTEM] Stopped By User")

    except Exception as e:
        log(f"[FATAL] {e}", "ERROR")
        traceback.print_exc()