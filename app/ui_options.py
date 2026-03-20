from __future__ import annotations

"""
UI option sets.

We keep Chinese literals as unicode escapes to avoid Windows console/editor encoding
pitfalls (mojibake) when using PowerShell on mixed-encoding systems.
"""

# Core cities only (user requirement): 北京/上海/广州/深圳.
CORE_CITIES = [
    "\u5317\u4eac",  # 北京
    "\u4e0a\u6d77",  # 上海
    "\u5e7f\u5dde",  # 广州
    "\u6df1\u5733",  # 深圳
]

# Tokens that might appear inside a city/location field in job descriptions.
# Not shown in the city dropdown by default.
EXTRA_LOCATION_TOKENS = [
    "\u5168\u56fd",  # 全国
    "\u8fdc\u7a0b",  # 远程
]


def city_filter_options() -> list[str]:
    # Intentionally fixed list: avoid noisy district-level options like "北京市东城区".
    return list(CORE_CITIES)


# For company HQ selection we allow "全国/其他" in addition to core cities.
HQ_LOCATION_OPTIONS = list(CORE_CITIES) + [
    "\u5168\u56fd",  # 全国
    "\u5176\u4ed6",  # 其他
]


# Display labels: keep them English as requested ("采集渠道/来源建议弄成英文").
SOURCE_TYPE_LABELS: dict[str, str] = {
    "official": "official",
    "import": "import",
    "manual": "manual",
}

SOURCE_KIND_LABELS: dict[str, str] = {
    # Structured official portals
    "m_zhiye": "beisen",
    "hotjob": "hotjob",
    # Generic/public feeds
    "rss": "rss",
    "html_list": "html_list",
    "url_list": "url_list",
    # Optional connectors
    "tencent": "tencent",
    "kuaishou": "kuaishou",
    "jd": "jd",
    "iguopin": "iguopin",
}

