"""
从扫码枪 / 电子面单复制的一整段文本中解析运单号与快递公司编码（微信侧常用大写编码）。
支持：Tab/逗号/竖线分隔的两段式；常见字母前缀 + 单号一体式；常见中文公司名前缀。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# (前缀, 微信/系统 express_company)，按前缀长度降序在运行时排序
_PREFIX_TO_CODE: List[Tuple[str, str]] = [
    ("YUNDA", "YUNDA"),
    ("JTSD", "JTSD"),
    ("ZTO", "ZTO"),
    ("STO", "STO"),
    ("YTO", "YTO"),
    ("EMS", "EMS"),
    ("DBL", "DBL"),
    ("SF", "SF"),
    ("YT", "YTO"),
    ("YD", "YUNDA"),
    ("JT", "JTSD"),
    ("JD", "JD"),
    ("UC", "UC"),
    ("ST", "STO"),
]

_CN_TO_CODE = {
    "圆通": "YTO",
    "韵达": "YUNDA",
    "中通": "ZTO",
    "申通": "STO",
    "顺丰": "SF",
    "京东": "JD",
    "邮政": "EMS",
    "ems": "EMS",
    "极兔": "JTSD",
    "德邦": "DBL",
    "优速": "UC",
}


def _sorted_prefixes() -> List[Tuple[str, str]]:
    return sorted(_PREFIX_TO_CODE, key=lambda x: len(x[0]), reverse=True)


def _normalize_raw(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace("\r", "").replace("\n", " ")
    s = s.replace("，", ",").replace("｜", "|")
    return s


def _split_segments(s: str) -> List[str]:
    for sep in ("\t", "|", ";", ","):
        if sep in s:
            parts = [p.strip() for p in s.split(sep) if p.strip()]
            if len(parts) >= 2:
                return parts
    # 多个连续空格视为分隔（仅当形成两段时采用）
    if re.search(r"\s{2,}", s):
        parts = [p.strip() for p in re.split(r"\s{2,}", s) if p.strip()]
        if len(parts) >= 2:
            return parts
    return [s.strip()] if s.strip() else []


def _valid_tracking(t: str) -> bool:
    if not t or len(t) < 6 or len(t) > 32:
        return False
    return True


def _parse_company_token(tok: str) -> Optional[str]:
    t = tok.strip()
    if not t:
        return None
    if t in _CN_TO_CODE:
        return _CN_TO_CODE[t]
    u = t.upper()
    if u == "EMS":
        return "EMS"
    for zh, code in _CN_TO_CODE.items():
        if len(zh) >= 2 and t.startswith(zh):
            return code
    if u.isalpha() and 2 <= len(u) <= 8:
        return u
    return None


def _parse_single_token(token: str) -> Tuple[Optional[str], str]:
    """返回 (express_company 或 None, 运单号或原串)。"""
    t = token.strip().upper()
    if not t:
        return None, ""

    if t.isdigit():
        return None, t

    # 京东：JDVB… / JDVC… 等整串即为运单号，不能只剥掉前两位 JD
    if t.startswith("JD") and len(t) >= 10:
        suf = t[2:]
        if suf and not suf.isdigit():
            return "JD", t

    for prefix, code in _sorted_prefixes():
        if t.startswith(prefix):
            rest = t[len(prefix) :].strip()
            if rest and (rest.isdigit() or (rest.isalnum() and len(rest) >= 6)):
                return code, rest
            # 前缀紧贴字母数字运单号（如 JDVB0123456789）
            if rest and len(rest) >= 8 and re.match(r"^[A-Z0-9]+$", rest):
                return code, rest

    # 未识别前缀则整体当作运单号（可能为纯字母数字）
    return None, token.strip()


def parse_ship_scan(raw: str) -> Dict[str, Any]:
    """
    :return: tracking_number, express_company, segments, hint
    """
    s = _normalize_raw(raw)
    if not s:
        return {
            "tracking_number": None,
            "express_company": None,
            "segments": [],
            "hint": "空内容",
        }

    segments = _split_segments(s)
    hint_parts: List[str] = []

    express: Optional[str] = None
    tracking: Optional[str] = None

    if len(segments) >= 2:
        # 尝试两种顺序：公司+单号 / 单号+公司
        a, b = segments[0], segments[1]
        ca, ta = _parse_company_token(a), b.strip()
        cb, tb = _parse_company_token(b), a.strip()

        if ca and _valid_tracking(ta):
            express, tracking = ca, ta
            hint_parts.append("按「公司+分隔符+单号」解析")
        elif cb and _valid_tracking(tb):
            express, tracking = cb, tb
            hint_parts.append("按「单号+分隔符+公司」解析")
        elif ca:
            express, tracking = ca, ta
            hint_parts.append("识别到公司，单号长度可能异常请核对")
        elif cb:
            express, tracking = cb, tb
            hint_parts.append("识别到公司，单号长度可能异常请核对")
        else:
            # 两段都当单号相关：取较长为单号
            tracking = max(segments[:2], key=len)
            hint_parts.append("未能识别快递公司，请手动选择")
    else:
        ex, tr = _parse_single_token(segments[0])
        express, tracking = ex, tr
        if ex:
            hint_parts.append("按一体式「快递前缀+运单号」解析")
        else:
            hint_parts.append("未识别快递前缀，已整体作为运单号；请手动选择快递公司")

    if tracking:
        tracking = tracking.strip()
    if express:
        express = express.strip().upper()

    if tracking and not _valid_tracking(tracking):
        hint_parts.append("运单号长度应在 6–32 位之间")

    return {
        "tracking_number": tracking,
        "express_company": express,
        "segments": segments,
        "hint": "；".join(hint_parts) if hint_parts else "",
    }
