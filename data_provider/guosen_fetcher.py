# -*- coding: utf-8 -*-
"""
===================================
GuosenFetcher - 国信证券数据源
==================================

数据来源：国信证券 TradeStation API
特点：HTTP REST API，需要 GS_API_KEY
优点：覆盖沪深北交所，支持实时行情、历史K线、资金流向

市场支持：
- 深圳 (setCode=0)
- 上海 (setCode=1)
- 北交所 (setCode=2)

关键策略：
1. 复用 skills/gs-stock-market-query 中的 SSL 处理逻辑
2. 使用指数退避重试机制
3. 失败后抛出 DataFetchError 切换到其他数据源
"""

import logging
import os
import ssl
import subprocess
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import (
    BaseFetcher,
    DataFetchError,
    STANDARD_COLUMNS,
    normalize_stock_code,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://dgzt.guosen.com.cn/skills"
SOFT_NAME = "goldsun_skills"
SKILL_NAME = "gs-stock-market-query"
TIMEOUT_SECONDS = 15


def _create_ssl_context():
    """创建SSL上下文，允许不安全的 renegotiation 以兼容旧服务器"""
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers('ALL:@SECLEVEL=0')
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
        except Exception:
            pass
        return ctx
    except Exception:
        pass

    try:
        ctx = ssl._create_unverified_context()
        try:
            ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
            ctx.set_ciphers('ALL:@SECLEVEL=0')
        except Exception:
            pass
        return ctx
    except Exception:
        pass

    return None


def _curl_request(url: str) -> Dict[str, Any]:
    """使用curl发送请求，当requests/urllib失败时的备用方案"""
    try:
        result = subprocess.run(
            ["curl", "-s", "-k", url],
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='ignore'
        )
        if result.returncode == 0 and result.stdout:
            try:
                return {"_curl_response": True, **eval(result.stdout)}
            except Exception:
                return {"error": "Invalid response", "raw": result.stdout[:500]}
        else:
            return {"error": f"curl failed: {result.stderr}"}
    except Exception as e:
        return {"error": str(e)}


def _make_request(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """发送请求，支持 urllib 和 curl 备用"""
    params["skillName"] = SKILL_NAME
    try:
        query_string = urlencode(params)
        full_url = f"{url}?{query_string}"

        ssl_ctx = _create_ssl_context()
        if ssl_ctx:
            req = urllib_request.Request(full_url)
            with urllib_request.urlopen(req, context=ssl_ctx, timeout=TIMEOUT_SECONDS) as response:
                return eval(response.read().decode("utf-8"))
        else:
            req = urllib_request.Request(full_url)
            with urllib_request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
                return eval(response.read().decode("utf-8"))
    except Exception:
        full_url = f"{url}?{urlencode(params)}"
        return _curl_request(full_url)


def _map_stock_code_to_set_code(stock_code: str) -> int:
    """
    根据股票代码推断市场代码

    Returns:
        0 - 深圳
        1 - 上海
        2 - 北交所
    """
    normalized = normalize_stock_code(stock_code).upper()

    # 北交所: 92xxxx, 43xxxx, 83xxxx, 87xxxx, 88xxxx
    if normalized.startswith(("92", "43", "83", "87", "88")):
        return 2

    # 上海: 6xx, 9xx (B股)
    if normalized.startswith(("600", "601", "603", "605", "688", "900")):
        return 1

    # 深圳: 0xx, 3xx
    if normalized.startswith(("000", "001", "002", "003", "300", "301")):
        return 0

    # 默认深圳
    return 0


class GuosenFetcher(BaseFetcher):
    """
    国信证券数据源实现

    优先级：2（与 PytdxFetcher 同级，低于 Tushare/Efinance，高于 Baostock）
    数据来源：国信证券 TradeStation API

    支持：
    - A股（沪深北交所）历史K线
    - 实时行情（通过 query_past_hq 获取近期数据）
    """

    name = "GuosenFetcher"
    priority = int(os.getenv("GUOSEN_PRIORITY", "2"))

    def __init__(self):
        """初始化 GuosenFetcher"""
        self._api_key = os.getenv("GS_API_KEY", "")
        if not self._api_key:
            raise DataFetchError("GS_API_KEY 环境变量未设置，请在 .env 中配置")

    def _convert_stock_code(self, stock_code: str) -> tuple:
        """
        转换股票代码为国信格式

        Returns:
            (code, set_code) - 代码和市场代码
        """
        normalized = normalize_stock_code(stock_code)
        set_code = _map_stock_code_to_set_code(normalized)
        return normalized, set_code

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, urllib_error.URLError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从国信证券获取原始数据

        使用 queryPastHQInfo 接口获取日线数据
        """
        # 检查是否为港股或美股（不支持）
        normalized = normalize_stock_code(stock_code)
        upper = normalized.upper()

        if upper.startswith("HK") or upper.startswith("HK."):
            raise DataFetchError(f"GuosenFetcher 不支持港股 {stock_code}，请使用 AkshareFetcher")

        if upper.replace(".", "").isalpha() and len(upper) <= 5:
            raise DataFetchError(f"GuosenFetcher 不支持美股 {stock_code}，请使用 YfinanceFetcher")

        # 转换代码格式
        code, set_code = self._convert_stock_code(stock_code)

        # 计算交易日数量
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        # 交易日约为日历日的 2/5，加上一些余量
        days_diff = (end_dt - start_dt).days
        want_nums = min(days_diff * 2 + 10, 250)  # 最多250个交易日

        logger.debug(f"调用国信 queryPastHQInfo({code}, setCode={set_code}, wantNums={want_nums})")

        url = f"{DEFAULT_BASE_URL}/gsnews/market/agentbot/queryPastHQInfo/1.0"
        params = {
            "code": code,
            "setCode": str(set_code),
            "wantNums": str(want_nums),
            "target": "0",  # 沪深京
            "softName": SOFT_NAME,
            "apiKey": self._api_key
        }

        try:
            result = _make_request(url, params)

            # 检查返回码 - 国信返回 result.code
            result_code = result.get("result", {}).get("code")
            if result_code != 0:
                error_msg = result.get("result", {}).get("msg", "未知错误")
                raise DataFetchError(f"国信 API 错误: {error_msg}")

            # 国信数据在 object.dailyHQList 中
            data = result.get("object", {})
            daily_list = data.get("dailyHQList", [])
            if not daily_list:
                raise DataFetchError(f"国信 API 未查询到 {stock_code} 的历史行情")

            # 国信返回格式: [{date, open, high, low, close, vol, amount, priceChange, priceChangePct, ...}, ...]
            rows = []
            for item in daily_list:
                rows.append({
                    "date": item.get("date", ""),
                    "open": item.get("open", ""),
                    "high": item.get("max", ""),
                    "low": item.get("min", ""),
                    "close": item.get("close", ""),
                    "volume": item.get("vol", ""),
                    "amount": item.get("amount", ""),
                    "pct_chg": item.get("priceChangePct", ""),
                })
            df = pd.DataFrame(rows)

            # 过滤日期范围
            if "date" in df.columns and len(df) > 0:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                df = df[(df["date"] >= start_dt) & (df["date"] <= end_dt)]

            if len(df) == 0:
                raise DataFetchError(f"国信 API 在指定日期范围内无 {stock_code} 的数据")

            return df

        except DataFetchError:
            raise
        except Exception as e:
            raise DataFetchError(f"国信获取数据失败: {e}") from e

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化国信数据

        国信返回的列名：
        date, open, high, low, close, volume, amount, pct_chg

        需要映射到标准列名（已一致）：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()

        # 列名已经是标准格式，直接使用
        # 如果有嵌套列名（如 '0'）需要展平
        if "0" in df.columns or "1" in df.columns:
            # 重命名数字列
            col_mapping = {
                "0": "date", "1": "open", "2": "high", "3": "low",
                "4": "close", "5": "volume", "6": "amount", "7": "pct_chg"
            }
            df = df.rename(columns=col_mapping)

        # 数值类型转换 - 处理中文单位（万、亿）
        numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_chg']
        for col in numeric_cols:
            if col in df.columns:
                # 转换万/亿单位为数值
                def parse_chinese_number(val):
                    if pd.isna(val):
                        return None
                    if isinstance(val, (int, float)):
                        return float(val)
                    s = str(val).strip()
                    try:
                        if s.endswith('万'):
                            return float(s[:-1]) * 10000
                        elif s.endswith('亿'):
                            return float(s[:-1]) * 100000000
                        else:
                            return float(s)
                    except (ValueError, TypeError):
                        return None

                df[col] = df[col].apply(parse_chinese_number)

        # 添加股票代码列
        df['code'] = normalize_stock_code(stock_code)

        # 确保日期格式正确
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]

        return df

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        获取股票名称

        使用 querySingleHQ 接口获取股票基本信息

        Args:
            stock_code: 股票代码

        Returns:
            股票名称或 None
        """
        code, set_code = self._convert_stock_code(stock_code)

        url = f"{DEFAULT_BASE_URL}/gsnews/market/agentbot/queryHQInfo/1.0"
        params = {
            "code": code,
            "setCode": str(set_code),
            "target": "0",
            "softName": SOFT_NAME,
            "apiKey": self._api_key
        }

        try:
            result = _make_request(url, params)

            if result.get("code") == 0:
                data = result.get("data", {})
                hq_info = data.get("hqInfo", {})
                if hq_info:
                    return hq_info.get("name")
        except Exception as e:
            logger.warning(f"获取股票名称失败 {stock_code}: {e}")

        return None

    def get_realtime_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        获取实时行情

        Args:
            stock_code: 股票代码

        Returns:
            实时行情字典
        """
        code, set_code = self._convert_stock_code(stock_code)

        url = f"{DEFAULT_BASE_URL}/gsnews/market/agentbot/queryHQInfo/1.0"
        params = {
            "code": code,
            "setCode": str(set_code),
            "target": "0",
            "softName": SOFT_NAME,
            "apiKey": self._api_key
        }

        try:
            result = _make_request(url, params)

            if result.get("code") == 0:
                data = result.get("data", {})
                hq_info = data.get("hqInfo", {})
                return hq_info
        except Exception as e:
            logger.warning(f"获取实时行情失败 {stock_code}: {e}")

        return None

    def get_fund_flow(self, stock_code: str, period: int = 60) -> Optional[Dict[str, Any]]:
        """
        获取资金流向

        Args:
            stock_code: 股票代码
            period: 周期（天），最多60

        Returns:
            资金流向数据
        """
        code, set_code = self._convert_stock_code(stock_code)

        # 资金流向仅支持沪深市场
        if set_code == 2:
            logger.warning("国信资金流向接口不支持北交所")
            return None

        url = f"{DEFAULT_BASE_URL}/gsnews/market/agentbot/queryFundFlow/1.0"
        params = {
            "code": code,
            "setCode": str(set_code),
            "period": str(min(period, 60)),
            "softName": SOFT_NAME,
            "apiKey": self._api_key
        }

        try:
            result = _make_request(url, params)

            if result.get("code") == 0:
                return result.get("data", {})
        except Exception as e:
            logger.warning(f"获取资金流向失败 {stock_code}: {e}")

        return None