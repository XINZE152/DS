# services/wechat_api.py
import json
import time
import threading
import httpx
from core.config import settings
from core.logging import get_logger  # ✅ 新增：导入 logger

logger = get_logger(__name__)        # ✅ 新增：初始化 logger

_WXA_ENV_ALLOWED = frozenset({"release", "trial", "develop"})


def _normalize_wxa_env_version() -> str:
    v = (getattr(settings, "WECHAT_WXA_ENV_VERSION", None) or "release").strip().lower()
    return v if v in _WXA_ENV_ALLOWED else "release"


def _wxacode_response_to_png(resp: httpx.Response, context: str) -> bytes:
    """微信接口失败时常返回 JSON；成功为 PNG/JPEG 二进制。避免把 JSON 当图片保存。"""
    raw = resp.content
    if len(raw) >= 8 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        return raw
    if len(raw) >= 3 and raw[:3] == b"\xff\xd8\xff":
        return raw
    try:
        err = json.loads(raw.decode("utf-8"))
        if isinstance(err, dict) and "errcode" in err:
            msg = err.get("errmsg", str(err))
            logger.error("%s 微信返回错误: %s", context, err)
            raise ValueError(msg)
    except (UnicodeDecodeError, json.JSONDecodeError):
        pass
    logger.error(
        "%s 响应非图片(前16字节=%r), content-type=%s",
        context,
        raw[:16],
        resp.headers.get("content-type", ""),
    )
    raise ValueError("微信返回非图片数据，请检查 access_token、路径与 env_version 配置")


async def get_access_token() -> str:
    """简易 access_token 缓存，7000s"""
    import time
    now = int(time.time())
    if not hasattr(get_access_token, "_cache") or now - get_access_token._cache[1] > 7000:
        url = ("https://api.weixin.qq.com/cgi-bin/token"
               "?grant_type=client_credential"
               f"&appid={settings.WECHAT_APP_ID}"
               f"&secret={settings.WECHAT_APP_SECRET}")
        async with httpx.AsyncClient() as cli:
            ret = await cli.get(url)
            ret.raise_for_status()
            get_access_token._cache = (ret.json()["access_token"], now)
    return get_access_token._cache[0]

async def get_wxacode(path: str, scene: str = "", width: int = 280) -> bytes:
    """获取临时小程序码二进制"""
    token = await get_access_token()
    url = f"https://api.weixin.qq.com/wxa/getwxacode?access_token={token}"
    body = {"path": path, "scene": scene, "width": width}
    async with httpx.AsyncClient() as cli:
        r = await cli.post(url, json=body)
        r.raise_for_status()
        return _wxacode_response_to_png(r, "getwxacode")

# ==================== 永久小程序码接口 ====================
async def get_wxacode_unlimit(scene: str, page: str, width: int = 280) -> bytes:
    """
    获取长期有效的小程序码（无限数量）
    :param scene: 场景值，长度不超过32个字符（如 "m=123"）
    :param page: 小程序页面路径，必须以 '/' 开头
    :param width: 二维码宽度
    :return: 图片二进制数据
    """
    token = await get_access_token()
    url = f"https://api.weixin.qq.com/wxa/getwxacodeunlimit?access_token={token}"
    env_ver = _normalize_wxa_env_version()
    logger.debug(
        "getwxacodeunlimit appid=%s env_version=%s page=%s scene=%s",
        settings.WECHAT_APP_ID,
        env_ver,
        page,
        scene,
    )
    payload = {
        "scene": scene,
        "page": page,
        "width": width,
        "check_path": False,          # 不校验页面是否存在（便于未发布页面）
        "env_version": env_ver,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return _wxacode_response_to_png(resp, "getwxacodeunlimit")


# ---------- URL Link（网页拉起小程序） ----------
_urllink_memo: dict[str, tuple[str, float]] = {}
_urllink_memo_lock = threading.Lock()
URLLINK_MEMO_TTL_SEC = 86400


async def generate_miniprogram_urllink(*, path: str, query: str = "") -> str:
    """
    调用 wxa/generate_urllink，返回 https 的 url_link。
    path 如 pages/index/index；query 如 a=1&b=2（不要带 ?）。
    """
    token = await get_access_token()
    api_url = f"https://api.weixin.qq.com/wxa/generate_urllink?access_token={token}"
    env_ver = _normalize_wxa_env_version()
    body: dict = {
        "path": path,
        "env_version": env_ver,
        "is_expire": False,
    }
    if query:
        body["query"] = query
    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url, json=body, timeout=15)
        resp.raise_for_status()
    data = resp.json()
    if data.get("errcode"):
        logger.error("generate_urllink 失败: %s", data)
        raise ValueError(data.get("errmsg") or str(data))
    link = data.get("url_link")
    if not link:
        logger.error("generate_urllink 无 url_link: %s", data)
        raise ValueError("微信未返回 url_link")
    return link


async def get_or_create_permanent_pay_urllink(merchant_user_id: int) -> str:
    """线下永久收款页 URL Link，带 query id=商户用户ID；带进程内缓存减轻微信配额压力。"""
    query = f"id={merchant_user_id}"
    cache_key = f"pages/offline/permanentPay|{query}"
    now = time.time()
    with _urllink_memo_lock:
        hit = _urllink_memo.get(cache_key)
        if hit and now - hit[1] < URLLINK_MEMO_TTL_SEC:
            return hit[0]
    link = await generate_miniprogram_urllink(
        path="pages/offline/permanentPay",
        query=query,
    )
    with _urllink_memo_lock:
        _urllink_memo[cache_key] = (link, now)
    return link


# ---------- URL Scheme（微信内 H5 立即跳转，减少 URL Link 中间确认页） ----------
_scheme_memo: dict[str, tuple[str, float]] = {}
_scheme_memo_lock = threading.Lock()
SCHEME_MEMO_TTL_SEC = 86400


async def generate_miniprogram_openlink(*, path: str, query: str = "") -> str:
    """
    调用 wxa/generatescheme，返回 weixin://dl/business/?t=... 的 openlink。
    文档说明：可在用户打开 H5 时立即 location.href / replace 调用，适合微信内置浏览器。
    """
    token = await get_access_token()
    api_url = f"https://api.weixin.qq.com/wxa/generatescheme?access_token={token}"
    env_ver = _normalize_wxa_env_version()
    jump_wxa: dict = {"path": path, "env_version": env_ver}
    if query:
        jump_wxa["query"] = query
    body: dict = {"jump_wxa": jump_wxa, "is_expire": False}
    async with httpx.AsyncClient() as client:
        resp = await client.post(api_url, json=body, timeout=15)
        resp.raise_for_status()
    data = resp.json()
    if data.get("errcode"):
        logger.error("generatescheme 失败: %s", data)
        raise ValueError(data.get("errmsg") or str(data))
    openlink = data.get("openlink")
    if not openlink:
        logger.error("generatescheme 无 openlink: %s", data)
        raise ValueError("微信未返回 openlink")
    return openlink


async def get_or_create_permanent_pay_openlink(merchant_user_id: int) -> str:
    """与永久收款 URL Link 同 path/query；进程内缓存减轻微信生成配额压力。"""
    query = f"id={merchant_user_id}"
    cache_key = f"pages/offline/permanentPay|{query}"
    now = time.time()
    with _scheme_memo_lock:
        hit = _scheme_memo.get(cache_key)
        if hit and now - hit[1] < SCHEME_MEMO_TTL_SEC:
            return hit[0]
    link = await generate_miniprogram_openlink(
        path="pages/offline/permanentPay",
        query=query,
    )
    with _scheme_memo_lock:
        _scheme_memo[cache_key] = (link, now)
    return link