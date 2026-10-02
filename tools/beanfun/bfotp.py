"""bfotp.py — beanfun 台灣區 一次性密碼 (OTP) 取得工具,Linux 原生。

這是 pungin/Beanfun (Rust + Tauri) 登入 / OTP 流程的最小可行重寫。
規格來源:https://github.com/pungin/Beanfun(協定行為;程式碼未複製)。
不碰遊戲、不碰反作弊、不需要 Wine、不需要 WebView —— 純 HTTPS。

這支是**函式庫,沒有 CLI** —— 要用的人是 tools/maple-login。
帳密登入那條路已經拿掉:beanfun 對帳密流程掛 reCAPTCHA,無頭的腳本解不了 v2 方塊
(見 docs/how-it-works.md §11),真正能走的只有 QR。

流程 (與 Rust 版 1:1):

  QR 登入 (TW,用 beanfun App 掃碼;這條路不受 reCAPTCHA 影響)
    1. GET  tw.beanfun.com/beanfun_block/bflogin/default.aspx?service=999999_T0
             -> 跟完轉址後,從最終 URL 撈 pSKey
    2. GET  login.beanfun.com/Login/Index?pSKey=...
             -> __RequestVerificationToken
    3. GET  login.beanfun.com/Login/InitLogin?pSKey=...       -> QR PNG + deeplink
    4. POST login.beanfun.com/QRLogin/CheckLoginStatus        -> 每秒問一次,等 App 按確認
    5. GET  login.beanfun.com/QRLogin/QRLogin                 -> handshake,回應丟掉
    6. GET  login.beanfun.com/Login/SendLogin                 -> 隱藏表單,接著
       POST tw.beanfun.com/beanfun_block/bflogin/return.aspx  (不跟轉址,只推進伺服器狀態)
    7. POST return.aspx (LoginCompleted 五個欄位)
             -> cookie jar 裡的 bfWebToken

  取帳號清單
    8. GET  beanfun_block/auth.aspx?channel=game_zone&...&web_token=...
    9. GET  beanfun_block/game_zone/game_server_account_list.aspx?sc&sr&dt

  取 OTP
   10. GET  beanfun_block/game_zone/game_start_step2.aspx      -> longPollingKey / unkData / createTime
   11. GET  tw.newlogin.beanfun.com/generic_handlers/get_cookies.ashx -> m_strSecretCode
   12. POST beanfun_block/generic_handlers/record_service_start.ashx
   13. GET  generic_handlers/get_result.ashx?meth=GetResultByLongPolling
   14. GET  beanfun_block/generic_handlers/get_webstart_otp.ashx -> "1;{key8}{密文hex}"
   15. DES/ECB/NoPadding 解密 -> 去掉 NUL -> 8 碼 OTP

用法(函式庫;QR 要怎麼顯示、OTP 要怎麼交給使用者,都是呼叫端的事):
    import bfotp
    s = bfotp.new_session()
    skey = bfotp.get_session_key(s)
    token, index_url = bfotp.get_login_index(s, skey)
    png, deeplink = bfotp.init_qr(s, skey, index_url)     # 這張 PNG 要給人掃
    bfotp.poll_qr(s, index_url, token, 180)
    web_token = bfotp.finalize_qr(s, skey, index_url)
    accounts = bfotp.list_accounts(s, web_token, bfotp.DEFAULT_SERVICE_CODE,
                                   bfotp.DEFAULT_SERVICE_REGION)
    otp = bfotp.get_otp(s, web_token, accounts[0], bfotp.DEFAULT_SERVICE_CODE,
                        bfotp.DEFAULT_SERVICE_REGION)

OTP 不進 argv (ps aux 全機器看得到) —— 這裡只把它 return 回去。

依賴:  requests, cryptography  (Ubuntu 24.04 兩個都預裝)
"""

from __future__ import annotations

import html
import re
import sys
import time
import urllib.parse
from datetime import datetime

import requests

# -----------------------------------------------------------------------------
# 常數 —— 全部照抄 Rust 版,不要自己發明
# -----------------------------------------------------------------------------

LOGIN_BASE = "https://login.beanfun.com/"
PORTAL_BASE = "https://tw.beanfun.com/"
NEWLOGIN_BASE = "https://tw.newlogin.beanfun.com/"

# UA 與 sec-ch-ua 的 Chrome 主版號必須一致,不然本身就是 bot 特徵。
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"'
ACCEPT_LANGUAGE = "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"

# get_webstart_otp.ashx 的 ppppp= 參數(pre-v2 用)。
# 2026-09-12 查明:這個值其實是 game_start_step2.aspx 的 m_objData.data 裡送過來的,
# WPF 舊版寫死才看起來像常數。現在一律從 blob 讀,這個只當最後的退路。
PPPPP = "1F552AEAFF976018F942B13690C990F60ED01510DDF89165F1658CCE7BC21DBA"

# --- get_webstart_otp_v2.ashx(2026-08 之後新楓之谷走這條) -------------------
# m_objData.data 的取代表。來自 GGMWebStart 的 Command.DecryptParam()。
# 每張都是 16 個十六進位字元的排列(可逆的前提),見 _decode_launch_data 的斷言。
LAUNCH_TABLES = (
    "bac987d65e432f10", "3bc4d5e6f2a79108", "cdbeaf9012456378", "4e6fb81a3c5d7092",
    "bdef1246789ac530", "5f82cb4093e71d6a", "df1468ace0357b92", "b50c61a4f93e82d7",
)

# v2 的 client attestation:GGM 1.5.0.2 的 GGMWebStart.dll。
# Gamania 出新版 GGM 時要跟著換(一年幾次),偵測點是 CheckVersion.ashx。
GGM_CV = "1.5.0.2"
GGM_HASH = "dfd568a69d87abcd8f4a93d1a4481ebb57712d1d28ab0b6fc018fcf140101e06"
GGM_ARCH = "x64"

# SendLogin 的 Accept。照抄 QR 流程的那一份,別自己發明。
ACCEPT_SENDLOGIN_QR = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)

# 新楓之谷
DEFAULT_SERVICE_CODE = "610074"
DEFAULT_SERVICE_REGION = "T9"

TIMEOUT = 30

VERBOSE = False


class BFError(Exception):
    """流程中任何一步失敗。訊息直接給使用者看。"""


def log(msg: str) -> None:
    if VERBOSE:
        print(f"[bfotp] {msg}", file=sys.stderr)


# -----------------------------------------------------------------------------
# DES/ECB/NoPadding —— 對應 core/wcdes
# -----------------------------------------------------------------------------


def _triple_des():
    """拿到 cryptography 的 TripleDES,不管它這版放在哪個模組。"""
    # 先試新位置:對舊位置做 hasattr 本身就會觸發 CryptographyDeprecationWarning
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    except ImportError:
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
    return TripleDES


def des_decrypt_hex(cipher_hex: str, key: str) -> str:
    """DES/ECB/NoPadding 解密,回傳 ASCII 字串 (>0x7F 一律換成 '?')。

    單 DES == 3DES 三把金鑰相同,所以用 TripleDES(key*3) 就是它,
    不必為了一個區塊密碼多裝一個套件。
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, modes

    key_bytes = key.encode("ascii", errors="replace")
    if len(key_bytes) != 8:
        raise BFError(f"DES 金鑰必須是 8 個 ASCII 位元組,拿到 {len(key_bytes)}")
    try:
        data = bytes.fromhex(cipher_hex)
    except ValueError as exc:
        raise BFError(f"OTP 密文不是合法 hex: {exc}") from exc
    if len(data) % 8 != 0:
        raise BFError(f"OTP 密文長度不是 8 的倍數: {len(data)}")

    decryptor = Cipher(_triple_des()(key_bytes * 3), modes.ECB()).decryptor()
    out = decryptor.update(data) + decryptor.finalize()
    return "".join(chr(b) if b <= 0x7F else "?" for b in out)


# -----------------------------------------------------------------------------
# 時間戳 —— 對應 core/time.rs。注意月份是 0-based 而且不補零,這是 WPF 的怪癖。
# -----------------------------------------------------------------------------


def dt_compact() -> str:
    """`?dt=` 用。格式 Y(M-1)DDhhmmssfff,例:2024-01-05 03:09:07.042 -> 2024005030907042"""
    n = datetime.now()
    return (
        f"{n.year}{n.month - 1}{n.day:02d}"
        f"{n.hour:02d}{n.minute:02d}{n.second:02d}{n.microsecond // 1000:03d}"
    )


def dt_iso() -> str:
    """`?_=` 用。格式 yyyyMMddHHmmss.fff"""
    n = datetime.now()
    return n.strftime("%Y%m%d%H%M%S") + f".{n.microsecond // 1000:03d}"


def tick_count() -> int:
    """.NET Environment.TickCount:32-bit 有號毫秒計數,伺服器只當 cache buster。"""
    v = int(time.time() * 1000) & 0xFFFFFFFF
    return v - (1 << 32) if v >= (1 << 31) else v


# -----------------------------------------------------------------------------
# HTTP session
# -----------------------------------------------------------------------------


def new_session() -> requests.Session:
    """帶瀏覽器指紋的 session。這些 header 要掛在每一個 request 上。

    裸 GET (沒有 sec-ch-ua / Accept-Language) 會被 beanfun 風控標記,
    接著在 AccountLogin 彈 reCAPTCHA。
    """
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "sec-ch-ua": SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Accept-Language": ACCEPT_LANGUAGE,
        }
    )
    return s


def check(resp: requests.Response, step: str) -> requests.Response:
    if not resp.ok:
        raise BFError(f"{step} 回傳 HTTP {resp.status_code}")
    return resp


PORTAL_HOST = "tw.beanfun.com"


def bfwebtoken(s: requests.Session, fallback: str | None = None) -> str | None:
    """從 cookie jar 取 bfWebToken,優先取 portal host 看得到的那一份。

    不用 s.cookies.get() —— 同名 cookie 掛在不同 domain 時它會丟
    CookieConflictError。轉址鏈上 login/tw/newlogin 三個 host 都會發 cookie,
    這在真機上會炸。
    """
    found = [c for c in s.cookies if c.name.lower() == "bfwebtoken"]
    for c in found:
        d = (c.domain or "").lstrip(".")
        if d and (PORTAL_HOST == d or PORTAL_HOST.endswith("." + d)):
            return c.value
    return found[0].value if found else fallback


# -----------------------------------------------------------------------------
# 登入的共用步驟(QR 流程也走這幾步)
# -----------------------------------------------------------------------------

RE_SKEY = re.compile(r"[sp][Ss]?[Kk]ey=([^&]+)")
RE_TOKEN = re.compile(r'__RequestVerificationToken[^>]+value="([^"]+)"')
RE_INPUT = re.compile(r"<input[^>]+>", re.I | re.S)
RE_INPUT_NAME = re.compile(r"""name\s*=\s*['"]([^'"]+)['"]""", re.I)
RE_INPUT_VALUE = re.compile(r"""value\s*=\s*['"]([^'"]*)['"]""", re.I)
RE_INPUT_SUBMIT = re.compile(r"""type\s*=\s*['"]submit['"]""", re.I)
RE_BFWEBTOKEN = re.compile(r"bfWebToken=([^;]+)", re.I)


def get_session_key(s: requests.Session) -> str:
    """步驟 1:跟完轉址,從最終 URL 撈 pSKey。"""
    url = PORTAL_BASE + "beanfun_block/bflogin/default.aspx?service=999999_T0"
    r = check(s.get(url, timeout=TIMEOUT), "default.aspx")
    m = RE_SKEY.search(r.url)
    if not m:
        raise BFError(f"轉址結束的 URL 沒有 pSKey:{r.url}")
    log(f"skey = {m.group(1)}")
    return m.group(1)


def get_login_index(s: requests.Session, skey: str) -> tuple[str, str]:
    """步驟 2:抓 Login/Index,撈 __RequestVerificationToken。回傳 (token, index_url)。"""
    index_url = LOGIN_BASE + "Login/Index?" + urllib.parse.urlencode({"pSKey": skey})
    r = check(
        s.get(index_url, headers={"Accept": "text/html"}, timeout=TIMEOUT), "Login/Index"
    )
    m = RE_TOKEN.search(r.text)
    if not m:
        raise BFError("Login/Index 頁面沒有 __RequestVerificationToken")
    return m.group(1), index_url


def send_login(s: requests.Session, index_url: str) -> list[tuple[str, str]]:
    """步驟 6:抓 SendLogin 頁,把所有非 submit 的 <input> 全部撈出來。"""
    r = check(
        s.get(
            LOGIN_BASE + "Login/SendLogin",
            headers={"Accept": ACCEPT_SENDLOGIN_QR, "Referer": index_url},
            timeout=TIMEOUT,
        ),
        "SendLogin",
    )
    form = []
    for tag in RE_INPUT.findall(r.text):
        if RE_INPUT_SUBMIT.search(tag):
            continue
        name = RE_INPUT_NAME.search(tag)
        value = RE_INPUT_VALUE.search(tag)
        if name and value:
            form.append((name.group(1), value.group(1)))
    if not form:
        raise BFError("SendLogin 頁面撈不到任何表單欄位(可能被擋、或版型改了)")
    log(f"SendLogin: {len(form)} 個欄位")
    return form


def post_return_aspx(s: requests.Session, form: list[tuple[str, str]]) -> str | None:
    """步驟 6 後半:POST return.aspx,不跟轉址,從 302 的 Set-Cookie 撈 bfWebToken。

    一定要 allow_redirects=False —— 跟下去 cookie 就被吃掉了。
    這一步在 QR 流程只是推進伺服器狀態,拿不到 token 是正常的,所以回 None 不算錯;
    真正的 token 要等 finalize_qr() 的 LoginCompleted。
    """
    r = s.post(
        PORTAL_BASE + "beanfun_block/bflogin/return.aspx",
        headers={"Referer": LOGIN_BASE},
        data=form,
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    if not (r.ok or r.is_redirect):
        raise BFError(f"return.aspx 回傳 HTTP {r.status_code}")

    # 先掃原始 header (跟 Rust/WPF 一致),掃不到再退回 cookie jar。
    raw = getattr(r.raw, "headers", None)
    headers = raw.getlist("Set-Cookie") if hasattr(raw, "getlist") else []
    for hdr in headers:
        m = RE_BFWEBTOKEN.search(hdr)
        if m:
            log("bfWebToken 來自 Set-Cookie header")
            return m.group(1)

    token = bfwebtoken(s)
    if token:
        log("bfWebToken 來自 cookie jar")
    return token


# -----------------------------------------------------------------------------
# QR 登入 —— 用 beanfun App 掃碼。這條路不受 reCAPTCHA 影響。
# -----------------------------------------------------------------------------


def normalize_deeplink(raw: str) -> str:
    """伺服器有時把真正的 deeplink 包在 play.games.gamania.com/.../deeplink/?url= 裡面。"""
    if not raw.strip():
        return raw
    try:
        u = urllib.parse.urlparse(raw.strip())
    except ValueError:
        return raw
    if (u.hostname or "").lower() != "play.games.gamania.com":
        return raw
    if "deeplink" not in u.path.lower():
        return raw
    for k, v in urllib.parse.parse_qsl(u.query):
        if k.lower() == "url" and v:
            return v
    return raw


def init_qr(s: requests.Session, skey: str, index_url: str) -> tuple[bytes, str]:
    """GET Login/InitLogin,回傳 (QR PNG bytes, deeplink)。"""
    import base64

    url = LOGIN_BASE + "Login/InitLogin?" + urllib.parse.urlencode({"pSKey": skey})
    r = check(
        s.get(
            url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": index_url,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://login.beanfun.com",
            },
            timeout=TIMEOUT,
        ),
        "Login/InitLogin",
    )
    j = r.json()
    if j.get("Result") != 0:
        raise BFError(f"InitLogin 回 Result={j.get('Result')},拿不到 QR code")
    data = j.get("ResultData") or {}
    image = data.get("QRImage")
    if not image:
        raise BFError("InitLogin 沒有回 QRImage")
    return base64.b64decode(image), normalize_deeplink(data.get("DeepLink") or "")


def poll_qr(s: requests.Session, index_url: str, token: str, timeout_sec: int) -> None:
    """每秒問一次 QRLogin/CheckLoginStatus,直到使用者在 App 上確認。

    Content-Length: 0 一定要自己設 —— 伺服器是嚴格 HTTP/1.1,
    收到 chunked 會直接回 411。
    """
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": index_url,
        "Origin": "https://login.beanfun.com",
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": "0",
    }
    if token:
        headers["RequestVerificationToken"] = token

    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        r = check(
            s.post(
                LOGIN_BASE + "QRLogin/CheckLoginStatus",
                headers=headers,
                data="",
                timeout=TIMEOUT,
            ),
            "QRLogin/CheckLoginStatus",
        )
        msg = (r.json() or {}).get("ResultMessage")
        log(f"QR 狀態:{msg}")
        if msg == "Success":
            return
        if msg == "Token Expired":
            raise BFError("QR code 過期了,重跑一次。")
        if msg not in ("Failed", "Wait Login"):
            raise BFError(f"QR 輪詢收到未知狀態:{r.text[:200]}")
        time.sleep(1)
    raise BFError(f"等了 {timeout_sec} 秒沒掃碼,放棄。")


def finalize_qr(s: requests.Session, skey: str, index_url: str) -> str:
    """QR 收尾四步,回傳 bfWebToken。"""
    # 1. handshake,回應丟掉
    check(
        s.get(
            LOGIN_BASE + "QRLogin/QRLogin",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Referer": index_url,
            },
            timeout=TIMEOUT,
        ),
        "QRLogin/QRLogin",
    )

    # 2-3. SendLogin -> return.aspx(這一步拿不到 token 是正常的)
    form = send_login(s, index_url)
    post_return_aspx(s, form)

    # 4. LoginCompleted 尾巴:固定五欄位,這次跟轉址,token 從 cookie jar 拿
    check(
        s.post(
            PORTAL_BASE + "beanfun_block/bflogin/return.aspx",
            headers={"Referer": LOGIN_BASE},
            data=[
                ("SessionKey", skey),
                ("AuthKey", "OK"),
                ("ServiceCode", ""),
                ("ServiceRegion", ""),
                ("ServiceAccountSN", "0"),
            ],
            timeout=TIMEOUT,
        ),
        "return.aspx (LoginCompleted)",
    )
    token = bfwebtoken(s)
    if not token:
        raise BFError("LoginCompleted 之後 cookie 裡沒有 bfWebToken")
    return token


# -----------------------------------------------------------------------------
# 帳號清單
# -----------------------------------------------------------------------------

RE_ACCOUNT_ROW = re.compile(
    r'onclick="([^"]*)"><div id="(\w+)" sn="(\d+)" name="([^"]+)"'
)
RE_LIMIT_NOTICE = re.compile(
    r'<div id="divServiceAccountAmountLimitNotice" class="InnerContent">(.*)</div>'
)


def list_accounts(
    s: requests.Session, web_token: str, service_code: str, service_region: str
) -> list[dict]:
    """步驟 8-9:auth.aspx 打完 cookie,再抓遊戲帳號清單。

    createtime 這裡刻意不抓 —— OTP 第 1 步會從它自己的回應撈到,
    省 N 個 HTTP request,也少一個會失敗的特例。
    """
    inner = f"game_start.aspx?service_code_and_region={service_code}_{service_region}"
    check(
        s.get(
            PORTAL_BASE + "beanfun_block/auth.aspx",
            params={
                "channel": "game_zone",
                "page_and_query": inner,
                "web_token": bfwebtoken(s, web_token),
            },
            timeout=TIMEOUT,
        ),
        "auth.aspx",
    )

    r = check(
        s.get(
            PORTAL_BASE + "beanfun_block/game_zone/game_server_account_list.aspx",
            params={"sc": service_code, "sr": service_region, "dt": dt_compact()},
            timeout=TIMEOUT,
        ),
        "game_server_account_list.aspx",
    )

    accounts = []
    for onclick, sid, ssn, sname in RE_ACCOUNT_ROW.findall(r.text):
        if not (sid and ssn and sname):
            continue
        accounts.append(
            {
                "enabled": bool(onclick),
                "sid": sid,
                "ssn": ssn,
                "sname": html.unescape(sname),
            }
        )
    accounts.sort(key=lambda a: a["ssn"])

    if not accounts:
        notice = RE_LIMIT_NOTICE.search(r.text)
        if notice:
            raise BFError(f"沒有可用的遊戲帳號。伺服器訊息:{notice.group(1)}")
        raise BFError("沒有撈到任何遊戲帳號(cookie 過期,或這個 service code 沒開帳號)")
    return accounts


# -----------------------------------------------------------------------------
# OTP
# -----------------------------------------------------------------------------

RE_LONG_POLLING_KEY = re.compile(r'GetResultByLongPolling&key=(.*)"')
RE_UNK_DATA = re.compile(r'MyAccountData.ServiceAccountCreateTime \+ "(.*)=(.*)";')
RE_CREATE_TIME = re.compile(r'ServiceAccountCreateTime: "([^"]+)"')
RE_SECRET_CODE = re.compile(r"var m_strSecretCode = '(.*)';")

RE_OBJ_DATA = re.compile(r"var m_objData\s*=\s*\{(.*?)\};", re.S)
RE_OBJ_SN = re.compile(r'"sn"\s*:\s*"([^"]*)"')
RE_OBJ_BLOB = re.compile(r'"data"\s*:\s*"([^"]*)"')


def _decode_launch_blob_with(body: str, selector: int, table_idx: int) -> str | None:
    """用指定的取代表還原一次。不符就回 None(換下一張表)。"""
    table = LAUNCH_TABLES[table_idx]
    out = []
    for ch in body:
        i = table.find(ch)
        if i < 0:
            return None
        out.append("%x" % i)
    norm = "".join(out)
    off = selector + 1
    if len(norm) < off + 8:
        return None
    key = norm[off : off + 8]
    cipher_hex = norm[:off] + norm[off + 8 :]
    try:
        return des_decrypt_hex(cipher_hex, key).strip("\0")
    except Exception:
        return None


def decode_launch_blob(blob: str) -> dict[str, str]:
    """把 game_start_step2 的 m_objData.data 還原成 key=value。

    格式(來自 GGMWebStart 的 Command.DecryptParam):
    首字元是十六進位的表選擇碼 n;其餘每個字元換成它在表裡的索引(再寫成十六進位)
    得到 normalized hex;其中位移 n+1 起的 8 個字元是 DES 金鑰(ASCII),
    拿掉後剩下的是密文 hex;DES/ECB/NoPadding 解開,去掉尾端 NUL。
    欄位以 & 分隔(實際是 &&&&),第一個 ';' 之後是尾碼不是欄位。

    表的選法上游沒定論(8 張表但 n%4 也解得開),所以逐張試到解出
    LaunchTicket= 或 ppppp= 為止 —— 錯的表只會產生雜訊,不會剛好拼出欄位名。
    """
    if not blob:
        raise BFError("m_objData.data 是空的")
    try:
        selector = int(blob[0], 16)
    except ValueError:
        raise BFError(f"m_objData.data 的表選擇碼不是十六進位:{blob[0]!r}")
    rest = blob[1:]

    order = [selector % 4, selector % len(LAUNCH_TABLES)] + list(range(len(LAUNCH_TABLES)))
    tried = []
    for idx in order:
        if idx in tried:
            continue
        tried.append(idx)
        plain = _decode_launch_blob_with(rest, selector, idx)
        if plain and ("LaunchTicket=" in plain or "ppppp=" in plain):
            log(f"launch blob:選擇碼 {selector},用第 {idx} 張表")
            fields = {}
            for seg in plain.split(";")[0].split("&"):
                if seg and "=" in seg:
                    k, v = seg.split("=", 1)
                    fields[k] = v
            return fields
    raise BFError("m_objData.data 八張表都解不出 LaunchTicket / ppppp")


def get_otp(
    s: requests.Session,
    web_token: str,
    account: dict,
    service_code: str,
    service_region: str,
) -> str:
    """步驟 10-15。回傳 8 碼 OTP。"""

    # --- 10. game_start_step2.aspx:longPollingKey + unkData + createTime
    r = check(
        s.get(
            PORTAL_BASE + "beanfun_block/game_zone/game_start_step2.aspx",
            params={
                "service_code": service_code,
                "service_region": service_region,
                "sotp": account["ssn"],
                "dt": dt_compact(),
            },
            timeout=TIMEOUT,
        ),
        "game_start_step2.aspx",
    )
    body = r.text

    m = RE_LONG_POLLING_KEY.search(body)
    if not m:
        raise BFError("game_start_step2 沒有 longPollingKey（服務或 session 可能異常）")
    long_polling_key = m.group(1)

    m = RE_UNK_DATA.search(body)
    if not m:
        raise BFError("game_start_step2 沒有 unkData(台版必要欄位)")
    unk_key = urllib.parse.unquote(m.group(1)).lstrip("&")
    unk_value = urllib.parse.unquote(m.group(2))

    m = RE_CREATE_TIME.search(body)
    if not m:
        raise BFError("game_start_step2 沒有 ServiceAccountCreateTime")
    screatetime = m.group(1)
    log("game_start_step2 必要欄位已取得")

    # --- 10b. m_objData:v2 的 LaunchTicket(或 pre-v2 的真 ppppp)都藏在這
    m = RE_OBJ_DATA.search(body)
    if not m:
        raise BFError("game_start_step2 沒有 m_objData(頁面格式又變了?)")
    obj = m.group(1)
    m_sn = RE_OBJ_SN.search(obj)
    m_blob = RE_OBJ_BLOB.search(obj)
    if not (m_sn and m_blob):
        raise BFError("m_objData 少了 sn 或 data")
    launch_sn = m_sn.group(1)
    launch = decode_launch_blob(m_blob.group(1))

    # --- 11. get_cookies.ashx:m_strSecretCode (只有這步用 newlogin host)
    r = check(
        s.get(NEWLOGIN_BASE + "generic_handlers/get_cookies.ashx", timeout=TIMEOUT),
        "get_cookies.ashx",
    )
    m = RE_SECRET_CODE.search(r.text)
    if not m:
        raise BFError("get_cookies.ashx 沒有 m_strSecretCode")
    secret_code = m.group(1)

    # --- 12. record_service_start.ashx:回應丟掉,只為了讓伺服器記狀態
    check(
        s.post(
            PORTAL_BASE + "beanfun_block/generic_handlers/record_service_start.ashx",
            data={
                "service_code": service_code,
                "service_region": service_region,
                "service_account_id": account["sid"],
                "sotp": account["ssn"],
                "service_account_display_name": account["sname"],
                "service_account_create_time": screatetime,
                unk_key: unk_value,
            },
            timeout=TIMEOUT,
        ),
        "record_service_start.ashx",
    )

    # --- 13. long poll 觸發,回應同樣丟掉
    check(
        s.get(
            PORTAL_BASE + "generic_handlers/get_result.ashx",
            params={
                "meth": "GetResultByLongPolling",
                "key": long_polling_key,
                "_": dt_iso(),
            },
            timeout=TIMEOUT,
        ),
        "get_result.ashx",
    )

    # --- 14. 取 OTP。走哪一條由 blob 的內容決定,不是由遊戲決定:
    #   LaunchTicket -> v2(POST JSON,新楓之谷 2026-08 起走這條)
    #   ppppp        -> pre-v2(GET query string,其他遊戲仍在用)
    if "LaunchTicket" in launch:
        if not launch["LaunchTicket"]:
            raise BFError("blob 裡的 LaunchTicket 是空的")
        log("走 v2:get_webstart_otp_v2.ashx")
        r = check(
            s.post(
                PORTAL_BASE + "beanfun_block/generic_handlers/get_webstart_otp_v2.ashx",
                json={
                    "SN": launch_sn,
                    "LaunchTicket": launch["LaunchTicket"],
                    "CV": GGM_CV,
                    "Hash": GGM_HASH,
                    "arch": GGM_ARCH,
                },
                timeout=TIMEOUT,
            ),
            "get_webstart_otp_v2.ashx",
        )
        try:
            reply = r.json()
        except ValueError:
            raise BFError("get_webstart_otp_v2 回的不是 JSON")
        if reply.get("result") != 1:
            raise BFError("伺服器拒絕發 OTP(v2)")
        payload = reply.get("data") or ""
        if len(payload) < 8:
            raise BFError(f"v2 的 data 太短,放不下 8 byte 金鑰:{len(payload)}")
        return des_decrypt_hex(payload[8:], payload[:8]).strip("\0")

    # pre-v2:ppppp 等參數一律用 blob 送過來的,不要用寫死的常數
    log("走 pre-v2:get_webstart_otp.ashx")
    url = (
        PORTAL_BASE
        + "beanfun_block/generic_handlers/get_webstart_otp.ashx"
        + f"?SN={long_polling_key}"
        + f"&WebToken={bfwebtoken(s, web_token)}"
        + f"&SecretCode={secret_code}"
        + f"&ppppp={launch.get('ppppp', PPPPP)}"
        + f"&ServiceCode={launch.get('ServiceCode', service_code)}"
        + f"&ServiceRegion={launch.get('ServiceRegion', service_region)}"
        + f"&ServiceAccount={launch.get('ServiceAccount', account['sid'])}"
        + f"&CreateTime={launch.get('CreateTime', screatetime).replace(' ', '%20')}"
        + f"&d={tick_count()}"
    )
    r = check(s.get(url, timeout=TIMEOUT), "get_webstart_otp.ashx")
    envelope = r.text

    # --- 15. 拆信封 + 解密
    if not envelope:
        raise BFError("get_webstart_otp 回了空字串")
    parts = envelope.split(";")
    if len(parts) < 2:
        raise BFError("get_webstart_otp 回應格式不對")
    if parts[0] != "1":
        raise BFError("伺服器拒絕發 OTP")

    payload = parts[1]
    if len(payload) < 8:
        raise BFError(f"OTP 內容太短,放不下 8 byte 金鑰:{len(payload)}")
    return des_decrypt_hex(payload[8:], payload[:8]).strip("\0")
