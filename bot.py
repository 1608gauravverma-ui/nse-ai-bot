# ============================================================
# ALPHA NEWS 5
# PART 1 - FOUNDATION
# Version : 5.0.0
# Compatible : Pydroid 3 / Python 3.11+ / Render
# ============================================================

# ==========================
# IMPORTS
# ==========================

import requests
import feedparser
import logging
import json
import re
import time
import os
import io
import traceback
import io

from datetime import datetime, timedelta
from urllib.parse import urljoin
# Gemini SDK not required
genai = None
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Alpha News 5 Running"

def run_http():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

# Optional Libraries
try:
    from bs4 import BeautifulSoup
except:
    BeautifulSoup = None

try:
    import fitz          # PyMuPDF
except:
    fitz = None

try:
    import pdfplumber
except:
    pdfplumber = None


# ============================================================
# CONFIGURATION
# ============================================================

# ---------------- Telegram ----------------

BOT_TOKEN = "8638278037:AAGr9MKqQ045Hqa-f-godVUrQ7T9dnHt4a8"
CHAT_ID = "6315662736"

# ---------------- Gemini ------------------

GEMINI_API_KEY = "AQ.Ab8RN6In2aXZmtWPH7oe7uy7WB3RRp3KXdoFBdnwqv_HcWD_wA"
ENABLE_AI = True

# ---------------- Market ------------------

CHECK_INTERVAL = 30          # seconds

HEALTH_CHECK_INTERVAL = 300   # 5 minutes
MAX_IDLE_MINUTES = 10
ENABLE_PREOPEN = True
ENABLE_FNO = True
ENABLE_RESULTS = True
ENABLE_XBRL = True
ENABLE_LOGGING = True

MARKET_PREOPEN_TIME = "09:08"
MARKET_OPEN_TIME = "09:15"

# ---------------- Network -----------------

REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
RETRY_DELAY = 3

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "Chrome/138.0 Safari/537.36"
)
# =====================================================
# ALPHA AI DECISION ENGINE V6
# =====================================================

AI_MODEL = "gemini-2.5-flash"

AI_PROMPT = """
You are an Institutional Equity Research Analyst.

Analyze the NSE announcement like a professional fund manager.

Do NOT simply summarize.

Your task is to estimate how the MARKET is likely to react.

Rules:

SPECIAL RULES FOR QUARTERLY RESULTS

If the announcement is only:
- Audio Recording
- Earnings Call
- Conference Call
- Investor Presentation
- Transcript
- Webcast

AND there is NO financial result data available,
then NEVER give:
- STRONG BULLISH
- STRONG BEARISH
- BUY ON DIPS
- SELL ON RISE

Instead return:
Impact: 2/10
Sentiment: Neutral
Urgency: Low
Verdict: NEUTRAL
Confidence: 80
Action: WATCH

If financial result PDF is available, analyze:

- Revenue YoY
- Net Profit YoY
- EPS
- EBITDA Margin
- Order Book
- Guidance
- Cash Flow
- Debt
- Management Commentary

Give higher importance to:
- Profit growth
- Margin expansion
- Future guidance
- Order book
- Recurring business

Never decide only from the announcement title.
Always use the PDF content if available.

Think about:

• Financial impact
• Business impact
• Future earnings
• Sector impact
• Promoter impact
• Institutional buying/selling
• Retail psychology
• One-time vs recurring impact
• Risk factors
• Hidden positives
• Hidden negatives

If this is a RESULT announcement also analyze:

- Revenue
- EBITDA
- EBITDA Margin
- PAT
- EPS
- Cash Flow
- Debt
- Exceptional Items
- Guidance
- QoQ
- YoY

If sector specific data exists, analyze it.

Examples:

Bank:
GNPA
NNPA
Provision
Credit Cost

IT:
Guidance
Deal Wins

Auto:
Volumes

Pharma:
USFDA
Approvals

Power:
Capacity
PLF

Output ONLY in this format:

Company:

Symbol:

News Importance:
/100

Market Impact:
Highly Positive
Positive
Mixed
Negative
Highly Negative

Expected Market Reaction:

Intraday:

1-3 Days:

Swing:

Trade Bias:

STRONG BUY

BUY

WAIT

SELL

STRONG SELL

Confidence:
/100

Top Positives:

- ...

Top Negatives:

- ...

Risk Factors:

- ...

Final AI Verdict:

One short professional paragraph.

Never guess.

If sufficient information is unavailable, return WAIT.
IMPORTANT:

Return ONLY in this exact format.

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

Do not write any introduction.
Do not explain your thinking.
Return only the above format.
"""
# ============================================================
# GLOBAL VARIABLES
# ============================================================

session = requests.Session()

processed_links = set()

processed_titles = set()

COMPANY_CACHE = {}

RESULT_CACHE = {}

PREOPEN_CACHE = {}

LAST_PREOPEN_DATE = None

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)

logger = logging.getLogger("AlphaNews5")

# ============================================================
# LOG FUNCTION
# ============================================================

def log(message, level="INFO"):
    """
    Central logging function.
    """

    if not ENABLE_LOGGING:
        return

    level = level.upper()

    if level == "ERROR":
        logger.error(message)

    elif level == "WARNING":
        logger.warning(message)

    else:
        logger.info(message)

# ============================================================
# HTTP SESSION
# ============================================================

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

# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    """
    Send message to Telegram.
    """

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
            log("Telegram message sent.")

        else:
            log(
                f"Telegram Error : {response.text}",
                "ERROR"
            )

    except Exception as e:

        log(
            f"Telegram Exception : {e}",
            "ERROR"
        )

# ============================================================
# TIME UTILITIES
# ============================================================

def current_time():

    return datetime.now()


def today():

    return datetime.now().date()


def current_time_string():

    return datetime.now().strftime("%H:%M:%S")

# ============================================================
# STARTUP
# ============================================================

log("=" * 60)
log("ALPHA NEWS 5 STARTING...")
log("Version : 5.0.0")
log("Foundation Loaded Successfully")
log("=" * 60)
# ==========================================================
# NSE URLS
# ==========================================================

NSE_HOME = "https://www.nseindia.com/"

RSS_URLS = {

    "announcements":
    "https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml",

    "board":
    "https://nsearchives.nseindia.com/content/RSS/BoardMeetings.xml",

    "actions":
    "https://nsearchives.nseindia.com/content/RSS/CorporateActions.xml"

}

# ==========================================================
# NSE SESSION STATUS
# ==========================================================

NSE_READY = False

LAST_SESSION_REFRESH = None

# ==========================================================
# CREATE NSE SESSION
# ==========================================================

def create_nse_session():
    """
    Create fresh NSE session.

    Returns:
        bool
    """

    global session
    global NSE_READY
    global LAST_SESSION_REFRESH

    try:

        session = requests.Session()

        session.headers.update({

            "User-Agent": USER_AGENT,

            "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/webp,*/*;q=0.8",

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

            log("NSE Session Created Successfully")

            return True

        else:

            NSE_READY = False

            log(
                f"NSE Home Failed : {response.status_code}",
                "ERROR"
            )

            return False

    except Exception as e:

        NSE_READY = False

        log(

            f"NSE Session Error : {e}",

            "ERROR"

        )

        return False

# ==========================================================
# VERIFY NSE SESSION
# ==========================================================

def verify_nse_session():
    """
    Check whether current NSE session is valid.
    """

    global NSE_READY

    try:

        response = session.get(
            NSE_HOME,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code == 200:

            NSE_READY = True
            return True

        NSE_READY = False
        return False

    except Exception:

        NSE_READY = False
        return False
        # ==========================================================
# REFRESH NSE SESSION
# ==========================================================

def refresh_nse_session():
    """
    Refresh NSE session if expired.
    """

    global LAST_SESSION_REFRESH

    log("[NSE] Refreshing session...")

    if create_nse_session():

        LAST_SESSION_REFRESH = current_time()

        log("[NSE] Session refreshed")

        return True

    log("[NSE] Session refresh failed", "ERROR")

    return False
        # ==========================================================
# NETWORK STATUS
# ==========================================================

NETWORK_STATS = {

    "total_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "session_refreshes": 0

}

# ==========================================================
# UPDATE NETWORK STATS
# ==========================================================

def update_network_stats(success):

    NETWORK_STATS["total_requests"] += 1

    if success:
        NETWORK_STATS["successful_requests"] += 1
    else:
        NETWORK_STATS["failed_requests"] += 1


# ==========================================================
# SAFE GET REQUEST
# ==========================================================

def safe_get(
    url,
    timeout=REQUEST_TIMEOUT,
    retries=MAX_RETRIES,
    headers=None
):
    """
    Safe GET request with retry.
    RSS/XML requests don't require NSE session refresh.
    """

    global NETWORK_STATS

    if headers is None:
        headers = session.headers

    for attempt in range(1, retries + 1):

        try:

            response = session.get(
                url,
                timeout=timeout,
                headers=headers
            )

            # Success
            if response.status_code == 200:

                update_network_stats(True)

                return response

            # Session expired
            if response.status_code in (401, 403):

                log("[NETWORK] Session expired", "WARNING")

                # RSS/XML feeds don't need session refresh
                if "/content/RSS/" not in url:

                    refresh_nse_session()

                    NETWORK_STATS["session_refreshes"] += 1

                continue

            # Other HTTP errors
            log(
                f"HTTP {response.status_code} : Attempt {attempt}",
                "WARNING"
            )

        except Exception as e:

            log(
                f"Network Error : {e}",
                "WARNING"
            )

            update_network_stats(False)

        if attempt < retries:

            log(
                f"Retrying ({attempt}/{retries})...",
                "WARNING"
            )

            time.sleep(RETRY_DELAY)

            # RSS/XML feeds don't need session refresh
            if "/content/RSS/" not in url:

                refresh_nse_session()

                NETWORK_STATS["session_refreshes"] += 1

    log(
        f"Failed : {url}",
        "ERROR"
    )

    return None


def download_text(url):

    response = safe_get(url)

    if response is None:
        return None

    return response.text

def extract_pdf_text(pdf_url):
    if pdfplumber is None:
        log("[PDF] pdfplumber not installed", "WARNING")
        return ""

    if fitz is None:
        log("[PDF] PyMuPDF not installed", "WARNING")

    try:

        response = safe_get(pdf_url)

        if response is None:
            return ""

        pdf_file = io.BytesIO(response.content)

        text = ""

        with pdfplumber.open(pdf_file) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

        log("[PDF] Text Extracted Successfully")

        return text

    except Exception as e:

        log(f"[PDF] Error : {e}", "ERROR")

        return ""
# ==========================================================
# DOWNLOAD JSON
# ==========================================================

def download_json(url):

    response = safe_get(url)

    if response is None:
        return None

    try:

        return response.json()

    except Exception as e:

        log(

            f"JSON Decode Error : {e}",

            "ERROR"

        )

        return None


# ==========================================================
# DOWNLOAD XML
# ==========================================================

def download_xml(url):

    response = safe_get(url)

    if response is None:
        return None

    return feedparser.parse(response.text)


# ==========================================================
# NETWORK HEALTH
# ==========================================================

def show_network_health():

    log("=" * 50)

    log("NETWORK HEALTH")

    log(f"Requests : {NETWORK_STATS['total_requests']}")

    log(f"Success : {NETWORK_STATS['successful_requests']}")

    log(f"Failed : {NETWORK_STATS['failed_requests']}")

    log(f"Session Refresh : {NETWORK_STATS['session_refreshes']}")

    log("=" * 50)
    # ==========================================================
# HEALTH CHECK
# ==========================================================
LAST_HEALTH_CHECK = current_time()
LAST_SUCCESS_TIME = current_time()

def health_check():

    global LAST_HEALTH_CHECK, LAST_SUCCESS_TIME

    now = current_time()

    if (now - LAST_HEALTH_CHECK).seconds < HEALTH_CHECK_INTERVAL:
        return

    LAST_HEALTH_CHECK = now

    idle = (now - LAST_SUCCESS_TIME).total_seconds() / 60

    if idle >= MAX_IDLE_MINUTES:

        log(f"[HEALTH] No successful fetch for {idle:.1f} minutes", "WARNING")

        refresh_nse_session()

    else:

        log(f"[HEALTH] OK | Idle {idle:.1f} min")
    # ==========================================================
# MODULE 04 : F&O CORE ENGINE
# Alpha_News5 - Part 2B-1
# ==========================================================

log("Initializing F&O Core Engine...")

FNO_DATABASE = {}
FNO_LAST_REFRESH = None
FNO_LAST_COUNT = 0


def clear_fno_database():
    """
    Clear complete F&O database.
    """
    global FNO_DATABASE

    FNO_DATABASE.clear()
    log("[F&O] Database cleared")


def add_fno_symbol(symbol):
    """
    Add one F&O symbol into database.
    """

    global FNO_DATABASE

    if not symbol:
        return

    symbol = symbol.strip().upper()

    if symbol not in FNO_DATABASE:

        FNO_DATABASE[symbol] = {
            "symbol": symbol,
            "enabled": True,
            "last_seen": current_time_string()
        }


def is_fno_stock(symbol):
    """
    Check whether stock belongs to F&O universe.
    """

    if not symbol:
        return False

    symbol = symbol.strip().upper()

    return symbol in FNO_DATABASE


def get_all_fno_symbols():

    return sorted(FNO_DATABASE.keys())


def get_fno_count():

    return len(FNO_DATABASE)


def update_fno_refresh_time():

    global FNO_LAST_REFRESH

    FNO_LAST_REFRESH = current_time_string()


def show_fno_status():

    log("-----------------------------------")
    log("F&O ENGINE STATUS")
    log("-----------------------------------")
    log(f"Stocks : {get_fno_count()}")
    log(f"Last Refresh : {FNO_LAST_REFRESH}")
    log("-----------------------------------")


def initialize_fno():

    clear_fno_database()

    log("[F&O] Engine initialized")


def health_check_fno():

    if get_fno_count() == 0:

        log("[F&O] WARNING : Database Empty")
        return False

    log("[F&O] Health Check OK")

    return True


initialize_fno()

log("F&O Core Engine Loaded Successfully")
# ==========================================================
# MODULE 04 : F&O LIVE LOADER
# Alpha_News5 - Part 2B-2
# ==========================================================

FNO_API_URL = "https://www.nseindia.com/api/market-data-pre-open?key=FO"


def load_fno_database():
    """
    Download latest F&O stock list from NSE.
    """

    global FNO_LAST_COUNT

    log("[F&O] Downloading F&O list...")

    try:

        data = download_json(FNO_API_URL)

        if not data:
            log("[F&O] ERROR : Empty response")
            return False

        records = data.get("data", [])

        if not records:
            log("[F&O] ERROR : No F&O records found")
            return False

        clear_fno_database()

        loaded = 0

        for item in records:

            metadata = item.get("metadata", {})

            symbol = metadata.get("symbol", "")

            if not symbol:
                continue

            add_fno_symbol(symbol)

            loaded += 1

        FNO_LAST_COUNT = loaded

        update_fno_refresh_time()

        log(f"[F&O] Loaded {loaded} symbols")

        return True

    except Exception as e:

        log(f"[F&O] Load Failed : {e}")

        return False


def refresh_fno():

    log("[F&O] Refresh Started")

    success = load_fno_database()

    if success:

        show_fno_status()

    else:

        log("[F&O] Refresh Failed")

    return success


def get_fno_database():

    return FNO_DATABASE


# ==========================================================
# PRINT SAMPLE F&O STOCKS
# ==========================================================

def print_sample_fno(limit=10):
    """
    Print sample F&O symbols.
    """

    symbols = get_all_fno_symbols()

    if not symbols:
        log("[F&O] Database Empty")
        return

    log("-----------------------------------")
    log("F&O SAMPLE")
    log("-----------------------------------")

    for symbol in symbols[:limit]:
        log(symbol)

    log("-----------------------------------")


# ==========================================================
# FIND F&O STOCK
# ==========================================================

def find_fno_stock(symbol):

    if not symbol:
        return None

    symbol = symbol.strip().upper()

    return FNO_DATABASE.get(symbol)


# ==========================================================
# F&O SUMMARY
# ==========================================================

def get_fno_summary():

    return {

        "count": get_fno_count(),

        "last_refresh": FNO_LAST_REFRESH

    }
 # ==========================================================
# MODULE 05A : NSE JSON CORE ENGINE
# Alpha_News5 Version 5.1
# ==========================================================

log("Initializing NSE JSON Engine...")

NSE_API = "https://www.nseindia.com/api/corporate-announcements?index=equities"

JSON_STATS = {
    "checked": 0,
    "success": 0,
    "failed": 0,
    "received": 0,
    "duplicates": 0
}

JSON_LAST_REFRESH = None


def update_json_refresh():

    global JSON_LAST_REFRESH

    JSON_LAST_REFRESH = current_time_string()


def reset_json_stats():

    JSON_STATS["checked"] = 0
    JSON_STATS["success"] = 0
    JSON_STATS["failed"] = 0
    JSON_STATS["received"] = 0
    JSON_STATS["duplicates"] = 0


def initialize_json():

    reset_json_stats()

    log("[JSON] Engine Initialized")


def show_json_status():

    log("-----------------------------------")
    log("JSON ENGINE STATUS")
    log("-----------------------------------")
    log(f"Checked      : {JSON_STATS['checked']}")
    log(f"Success      : {JSON_STATS['success']}")
    log(f"Failed       : {JSON_STATS['failed']}")
    log(f"Received     : {JSON_STATS['received']}")
    log(f"Duplicates   : {JSON_STATS['duplicates']}")
    log(f"Last Refresh : {JSON_LAST_REFRESH}")
    log("-----------------------------------")


initialize_json()

log("JSON Core Engine Loaded Successfully")
# ==========================================================
# MODULE 05 : RSS HELPER ENGINE
# Alpha_News5 - Part 2C-2A
# ==========================================================

def create_news_object(item):

    title = item.get("attchmntText") or item.get("desc") or ""

    link = item.get("attchmntFile", "")

    if link and not link.startswith("http"):
        link = "https://nsearchives.nseindia.com" + link

    return {

        "feed": "NSE",

        "title": title.strip(),

        "link": link,

        "summary": item.get("desc", "").strip(),

        "published": item.get("an_dt", "").strip(),

        "symbol": item.get("symbol", "").strip(),

        "company": item.get("sm_name", "").strip(),

        "received_at": current_time_string()

    }


def mark_news_processed(title, link):
    """
    Save processed news.
    """

    if title:
        processed_titles.add(title.strip())

    if link:
        processed_links.add(link.strip())





log("RSS Helper Engine Loaded Successfully")
# ==========================================================
# JSON HELPER FUNCTIONS
# ==========================================================

def is_duplicate_news(title, link):
    """
    Returns True if news is already processed.
    """

    title = (title or "").strip()
    link = (link or "").strip()

    if title and title in processed_titles:
        return True

    if link and link in processed_links:
        return True

    return False


def update_feed_success(item_count):
    """
    Update JSON statistics after successful fetch.
    """

    JSON_STATS["checked"] += 1
    JSON_STATS["success"] += 1
    JSON_STATS["received"] += item_count

    update_json_refresh()


def update_feed_failed():
    """
    Update JSON statistics after failed fetch.
    """

    JSON_STATS["checked"] += 1
    JSON_STATS["failed"] += 1


def fetch_all_news():
    """
    Common entry point for fetching announcements.
    """

    return fetch_json_news()
# ==========================================================
# MODULE 05B : NSE JSON DOWNLOADER
# ==========================================================

def fetch_json_news():

    log("[JSON] Checking NSE Announcements...")

    try:

        data = download_json(NSE_API)

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

        log(f"[JSON] {len(news_list)} New Announcements")

        return news_list

    except Exception as e:

        JSON_STATS["checked"] += 1
        JSON_STATS["failed"] += 1

        log(f"[JSON] ERROR : {e}", "ERROR")

        return []


def fetch_all_news():

    return fetch_json_news()
 
def startup_json_sync():

    log("[JSON] Startup Sync...")

    news = fetch_json_news()

    for item in news:

        mark_news_processed(
            item["title"],
            item["link"]
        )

    log("[JSON] Startup Sync Complete")
# ==========================================================
# MODULE 06 : MAIN ENGINE
# Alpha_News5 - Part 3A
# ==========================================================

def startup_initialize():

    log("=" * 60)
    log("STARTUP INITIALIZATION")
    log("=" * 60)

    if ENABLE_FNO:
        refresh_fno()

    startup_json_sync()

    show_json_status()

    log("=" * 60)
    log("STARTUP COMPLETE")
    log("=" * 60)

    log("[SYSTEM] Live Monitoring Started")
    # ==========================================================
# MODULE 07 : TELEGRAM MESSAGE ENGINE
# ==========================================================

def format_news_message(news):

    score = news.get("impact_score", 0)

    if score >= 9:
        impact = "🚨 HIGH IMPACT"
    elif score >= 7:
        impact = "⚠️ MEDIUM IMPACT"
    else:
        impact = "ℹ️ LOW IMPACT"

    message = ""

    message += "📢 <b>NSE ANNOUNCEMENT</b>\n"
    message += impact + "\n\n"

    message += f"🏢 <b>Company :</b> {news.get('company','N/A')}\n"
    message += f"📈 <b>Symbol :</b> {news.get('symbol','N/A')}\n\n"

    message += f"📰 <b>{news.get('title','')}</b>\n\n"

    message += "━━━━━━━━━━━━━━━━━━\n"

    message += f"📂 Category : {news.get('category','General')}\n"

    message += f"📊 Impact Score : {score}/10\n"

    message += f"📈 Sentiment : {news.get('sentiment','Neutral')}\n"

    message += f"⚡ Urgency : {news.get('urgency','Low')}\n"

    message += f"🤖 AI Verdict : {news.get('verdict','Neutral')}\n"

    message += f"🎯 Confidence : {news.get('confidence',50)}%\n"

    message += f"💹 Trading Action : {news.get('action','WATCH')}\n"

    message += "\n━━━━━━━━━━━━━━━━━━\n"
    if news.get("ai_analysis"):

        message += "\n🤖 <b>AI Institutional Analysis</b>\n\n"

        message += news["ai_analysis"]

        message += "\n\n━━━━━━━━━━━━━━━━━━\n"
    reasons = news.get("reasons", [])

    if reasons:

        message += "📌 <b>Reasons</b>\n"

        for r in reasons:

            message += f"• {r}\n"

    if news.get("published"):

        message += f"\n🕒 {news['published']}"

    if news.get("link"):

        message += f"\n\n🔗 {news['link']}"

    return message


def send_news(news):

    try:

        message = format_news_message(news)

        send_telegram(message)

        log("[Telegram] News Sent")

    except Exception as e:

        log(f"[Telegram] Error : {e}", "ERROR")
        # ==========================================================
# MODULE 08 : IMPACT ANALYSIS ENGINE
# ==========================================================

RULES = {

    "quarterly results": ("Quarterly Results",10,"Bullish","Immediate"),
    "financial results": ("Quarterly Results",10,"Bullish","Immediate"),
    "results": ("Quarterly Results",10,"Bullish","Immediate"),

    "dividend": ("Dividend",9,"Bullish","High"),
    "bonus": ("Bonus Issue",9,"Bullish","High"),
    "split": ("Stock Split",8,"Bullish","High"),

    "board meeting": ("Board Meeting",6,"Neutral","Medium"),

    "order": ("Order Win",9,"Bullish","Immediate"),
    "contract": ("Order Win",9,"Bullish","Immediate"),

    "acquisition": ("Acquisition",8,"Bullish","High"),
    "merger": ("Merger",8,"Bullish","High"),

    "agm": ("Shareholders Meeting",3,"Neutral","Low"),
    "voting": ("Shareholders Meeting",3,"Neutral","Low"),

    "credit rating": ("Credit Rating",7,"Bullish","Medium"),

    "bankruptcy": ("Bankruptcy",10,"Bearish","Immediate"),
    "insolvency": ("Insolvency",10,"Bearish","Immediate")
}

# ==========================================================
# ALPHA VERDICT DATABASE V1
# ==========================================================

ALPHA_RULES = {

# ================= POSITIVE =================

"quarterly results": {
    "score": 10,
    "category": "Quarterly Results",
    "sentiment": "Bullish",
    "urgency": "Immediate",
    "action": "BUY ON DIPS",
    "confidence": 95
},

"financial results": {
    "score": 10,
    "category": "Quarterly Results",
    "sentiment": "Bullish",
    "urgency": "Immediate",
    "action": "BUY ON DIPS",
    "confidence": 95
},

"dividend": {
    "score": 9,
    "category": "Dividend",
    "sentiment": "Bullish",
    "urgency": "High",
    "action": "BUY",
    "confidence": 90
},

"bonus": {
    "score": 9,
    "category": "Bonus Issue",
    "sentiment": "Bullish",
    "urgency": "High",
    "action": "BUY",
    "confidence": 90
},

"stock split": {
    "score": 8,
    "category": "Stock Split",
    "sentiment": "Bullish",
    "urgency": "High",
    "action": "WATCH",
    "confidence": 88
},

"split": {
    "score": 8,
    "category": "Stock Split",
    "sentiment": "Bullish",
    "urgency": "High",
    "action": "WATCH",
    "confidence": 88
},

"order": {
    "score": 9,
    "category": "Order Win",
    "sentiment": "Bullish",
    "urgency": "Immediate",
    "action": "BUY",
    "confidence": 92
},

"contract": {
    "score": 9,
    "category": "Order Win",
    "sentiment": "Bullish",
    "urgency": "Immediate",
    "action": "BUY",
    "confidence": 92
},

"acquisition": {
    "score": 8,
    "category": "Acquisition",
    "sentiment": "Bullish",
    "urgency": "High",
    "action": "WATCH",
    "confidence": 86
},

"merger": {
    "score": 8,
    "category": "Merger",
    "sentiment": "Bullish",
    "urgency": "High",
    "action": "WATCH",
    "confidence": 86
},

"rating upgrade": {
    "score": 8,
    "category": "Rating Upgrade",
    "sentiment": "Bullish",
    "urgency": "High",
    "action": "BUY",
    "confidence": 89
},

# ================= NEGATIVE =================

"bankruptcy": {
    "score": 10,
    "category": "Bankruptcy",
    "sentiment": "Bearish",
    "urgency": "Immediate",
    "action": "SELL",
    "confidence": 98
},

"insolvency": {
    "score": 10,
    "category": "Insolvency",
    "sentiment": "Bearish",
    "urgency": "Immediate",
    "action": "SELL",
    "confidence": 98
},

"default": {
    "score": 10,
    "category": "Default",
    "sentiment": "Bearish",
    "urgency": "Immediate",
    "action": "SELL",
    "confidence": 97
},

"fraud": {
    "score": 10,
    "category": "Fraud",
    "sentiment": "Bearish",
    "urgency": "Immediate",
    "action": "SELL",
    "confidence": 99
},

"rating downgrade": {
    "score": 9,
    "category": "Rating Downgrade",
    "sentiment": "Bearish",
    "urgency": "Immediate",
    "action": "SELL",
    "confidence": 92
}

}

def analyze_news(news):
    #
    # AI FIRST ANALYSIS
    #

    is_result = False

    title = news.get("title", "")
    description = news.get("summary", "")
    pdf_url = news.get("pdf_url", "")

    text = f"{title} {description}".lower()

    RESULT_KEYWORDS = [
        "financial results",
        "financial result",
        "quarterly results",
        "unaudited financial",
        "audited financial",
        "statement of standalone",
        "statement of consolidated",
        "results for quarter",
        "results for the quarter",
        "earnings"
    ]

    for k in RESULT_KEYWORDS:
        if k in text:
            is_result = True
            break

    pdf_text = ""

    if is_result and pdf_url:
        log("[RESULT] Downloading Result PDF...")

        pdf_text = extract_pdf_text(pdf_url)

        if pdf_text:
            log(f"[RESULT] PDF Loaded ({len(pdf_text)} chars)")
        else:
            log("[RESULT] PDF Empty", "WARNING")

    if should_use_ai(news):

        ai_result = ai_analyze_news(news)

        if ai_result:

            news["ai_analysis"] = ai_result
            news["verdict"] = "🤖 AI Decision"
            news["action"] = "AI"
            news["confidence"] = 90

    text = (
        news.get("title", "") + " " +
        news.get("summary", "")
    ).lower()

    # Default Values
    category = "General"
    score = 4
    sentiment = "Neutral"
    urgency = "Low"
    action = "WATCH"
    confidence = 50

    reasons = []
    matched = []
        # ==========================
    # POSITIVE / NEGATIVE COUNTER
    # ==========================
    
    positive_count = 0
    negative_count = 0
    
    positive_words = [
        "profit","growth","record","highest",
        "approval","expansion","capacity",
        "order","contract","dividend",
        "bonus","split","buyback",
        "acquisition","merger",
        "rating upgrade"
    ]
    
    negative_words = [
        "loss","default","fraud",
        "bankruptcy","insolvency",
        "fire","penalty",
        "rating downgrade",
        "resignation",
        "closure",
        "shutdown"
    ]

    # Search in new database
    for keyword, data in ALPHA_RULES.items():

        if keyword in text:

            matched.append(keyword)

            if data["score"] > score:

                score = data["score"]
                category = data["category"]
                sentiment = data["sentiment"]
                urgency = data["urgency"]
                action = data["action"]
                confidence = data["confidence"]

            reasons.append(f"Detected : {keyword.title()}")
                        # Count positive / negative matches
            if data["sentiment"] == "Bullish":
                positive_count += 1

            elif data["sentiment"] == "Bearish":
                negative_count += 1


    # Multiple keyword bonus
    if len(matched) >= 2:
        score = min(score + 1, 10)
        confidence = min(confidence + 3, 99)

    if len(matched) >= 3:
        score = min(score + 1, 10)
        confidence = min(confidence + 2, 99)

    # =====================================
    # SMART SCORE ENGINE
    # =====================================

    # Multiple positive news bonus
    if positive_count >= 2:
        score += 1
        confidence += 2
        reasons.append("Multiple positive announcements")

    if positive_count >= 3:
        score += 1
        confidence += 2

    # Multiple negative news penalty
    if negative_count >= 2:
        score -= 1
        confidence += 2
        reasons.append("Multiple negative announcements")

    if negative_count >= 3:
        score -= 1
        confidence += 2

    # F&O Bonus
    symbol = news.get("symbol", "")

    if symbol and is_fno_stock(symbol):
        score += 1
        confidence += 3
        reasons.append("F&O Stock")

    # Limit values
    score = max(1, min(score, 10))
    confidence = max(40, min(confidence, 99))
    # AI Verdict
    if score >= 9:
        verdict = "🔥 STRONG BULLISH" if sentiment == "Bullish" else "🔻 STRONG BEARISH"

    elif score >= 7:
        verdict = "📈 BULLISH" if sentiment == "Bullish" else "📉 BEARISH"

    else:
        verdict = "➖ NEUTRAL"

    # Default reason
    if not reasons:
        reasons.append("General corporate announcement.")

    # Save into object
    news["category"] = category
    news["impact_score"] = score
    news["sentiment"] = sentiment
    news["urgency"] = urgency
    news["action"] = action
    news["confidence"] = confidence
    news["verdict"] = verdict
    news["reasons"] = reasons

    return news


def process_news(news_list):

    if not news_list:
        return

    log(f"[JSON] Processing {len(news_list)} announcements")

    for news in news_list:

        news = analyze_news(news)
        if news["impact_score"] < 7:

            log(
                    f"[FILTER] Ignored : "
                    f"{news['title']} "
       f"({news['impact_score']}/10)"
             )

            continue

        log(
                f"[{news['feed']}] "
                f"{news['title']} "
                f"| Score: {news['impact_score']}/10 "
                f"| {news['sentiment']}"
         )
        
        send_news(news)
    
        
        # Future Modules
        #
        # AI Impact Engine
        # PDF Engine
        # XBRL Engine
        # Telegram Engine
        # Watchlist Engine


def main_loop():

    startup_initialize()

    while True:

        try:
    
            news = fetch_all_news()
    
            process_news(news)
    
            health_check()
    
        except KeyboardInterrupt:
    
            log("Bot Stopped By User")
    
            break
    
        except Exception as e:
    
            log(f"MAIN LOOP ERROR : {e}", "ERROR")
    
            traceback.print_exc()
    
        time.sleep(CHECK_INTERVAL)

            


def main():

    log("STEP 1")

    while True:

        try:

            log("STEP 2")

            create_nse_session()

            log("STEP 3")

            main_loop()

            log("STEP 4")

        except KeyboardInterrupt:

            log("Bot stopped by user")
            break

        except Exception as e:

            log(f"FATAL ERROR : {e}", "ERROR")

            traceback.print_exc()

            log("Restarting in 15 seconds...")

            time.sleep(15)


    # ============================================================
# MODULE 08 : AI IMPACT ENGINE
# ============================================================


    # ============================================================
# GEMINI INITIALIZATION
# ============================================================
log(f"ENABLE_AI = {ENABLE_AI}")

log(f"genai available = {genai is not None}")

AI_CLIENT = None

if ENABLE_AI and genai:

    try:

        AI_CLIENT = genai.Client(api_key=GEMINI_API_KEY)

        log("[AI] Gemini Initialized Successfully")

    except Exception as e:

        log(f"[AI] Initialization Failed : {e}", "ERROR")

        ENABLE_AI = False

else:

    log("[AI] Gemini Disabled")

HIGH_IMPACT = [
    "financial results",
    "quarterly results",
    "results",
    "board meeting",
    "dividend",
    "bonus",
    "stock split",
    "split",
    "rights issue",
    "preferential",
    "acquisition",
    "merger",
    "amalgamation",
    "order",
    "contract",
    "sebi",
    "fraud",
    "default",
    "bankruptcy",
    "insolvency",
    "resignation",
    "appointment",
    "buyback"
]
# ============================================================
# AI HIGH IMPACT CHECK
# ============================================================

def should_use_ai(news):

    if not ENABLE_AI:
        return False

    text = (
        news.get("title", "") + " " +
        news.get("summary", "")
    ).lower()

    for keyword in HIGH_IMPACT:
        if keyword in text:
            return True

    return False


# ============================================================
# GEMINI DECISION ENGINE
# ============================================================

def ai_analyze_news(news):

    if not ENABLE_AI:
        return None

    try:
        PDF_TEXT = ""

        if news.get("pdf_url"):
            PDF_TEXT = extract_pdf_text(news["pdf_url"])[:12000]

        prompt = f"""
{AI_PROMPT}

Company:
{news.get('company','')}

Symbol:
{news.get('symbol','')}

Title:
{news.get('title','')}

Summary:
{news.get('summary','')}
PDF:
{PDF_TEXT}
"""

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{AI_MODEL}:generateContent?key={GEMINI_API_KEY}"
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
            log(f"[AI] HTTP {response.status_code}", "ERROR")
            return None

        data = response.json()

        return (
            data["candidates"][0]
                ["content"]["parts"][0]["text"]
        )

    except Exception as e:

        log(f"[AI] {e}", "ERROR")

        return None



LOW_IMPACT = [
    "investor presentation",
    "presentation",
    "conference call",
    "earnings call",
    "earnings call audio",
    "audio recording",
    "link of audio recording",
    "analyst meet",
    "transcript",
    "webcast",
    "newspaper publication",
    "postal ballot",
    "agm",
    "egm"
]


def calculate_impact(news):

    text = (
        news.get("title", "") + " " +
        news.get("summary", "")
    ).lower()

    score = 5
    reason = "General Announcement"

    for word in HIGH_IMPACT:

        if word in text:

            score = 10
            reason = word.title()

            break

    for word in LOW_IMPACT:

        if word in text:

            score = 2
            reason = word.title()

            break

    return score, reason


def classify_news(score):

    if score >= 9:
        return "HIGH"

    elif score >= 6:
        return "MEDIUM"

   
    return "LOW"


if __name__ == "__main__":
    print("MAIN CALLED")
    Thread(target=run_http, daemon=True).start()
    main()
