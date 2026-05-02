"""
币安合约账户信息模块
支持：统一账户 (Portfolio Margin /papi/) 与 标准合约账户 (USDT-M /fapi/)
功能：账户资金查询 / 持仓查询 / 历史成交记录
"""

import hashlib
import hmac
import time
from urllib.parse import urlencode
from typing import Optional
import requests


# ─────────────────────────────────────────────
#  配置区（建议从环境变量或配置文件读取）
# ─────────────────────────────────────────────
class BinanceConfig:
    API_KEY: str = ""        # 替换为你的 API Key
    SECRET_KEY: str = ""     # 替换为你的 Secret Key
    RECV_WINDOW: int = 5000  # 请求有效窗口(ms)，最大 60000

    # 接口基础地址
    FAPI_BASE = "https://fapi.binance.com"   # 标准 USDT-M 合约
    PAPI_BASE = "https://papi.binance.com"   # 统一账户 (Portfolio Margin)

    # ── 代理设置 ──────────────────────────────
    # 国内需要挂代理才能访问币安，填写本地代理地址即可
    # 常见软件默认端口：Clash=7890  V2RayN=10809  Shadowsocks=1080
    # 不需要代理时设为 None
    PROXY_HOST: str = "127.0.0.1"
    PROXY_PORT: int = 7897          # ← 改成你本地代理的端口
    USE_PROXY: bool = True          # ← 不需要代理时改为 False

    @classmethod
    def get_proxies(cls) -> Optional[dict]:
        """返回 requests 格式的代理字典，USE_PROXY=False 时返回 None"""
        if not cls.USE_PROXY:
            return None
        proxy_url = f"http://{cls.PROXY_HOST}:{cls.PROXY_PORT}"
        return {"http": proxy_url, "https": proxy_url}


# ─────────────────────────────────────────────
#  签名工具
# ─────────────────────────────────────────────
def _sign(params: dict, secret: str) -> str:
    """对请求参数进行 HMAC-SHA256 签名"""
    query_string = urlencode(params)
    return hmac.new(
        secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_headers(api_key: str) -> dict:
    return {"X-MBX-APIKEY": api_key, "Content-Type": "application/json"}


def _get(base_url: str, path: str, params: dict, api_key: str, secret: str) -> dict:
    """发送带签名的 GET 请求（自动携带代理配置）"""
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = BinanceConfig.RECV_WINDOW
    params["signature"] = _sign(params, secret)

    url = f"{base_url}{path}"
    resp = requests.get(
        url,
        params=params,
        headers=_build_headers(api_key),
        proxies=BinanceConfig.get_proxies(),
        timeout=10,
    )
    # 打印币安返回的详细错误（code + msg），方便排查
    if not resp.ok:
        try:
            err = resp.json()
            raise requests.exceptions.HTTPError(
                f"{resp.status_code} {resp.reason} | 币安错误码: {err.get('code')} | {err.get('msg')}",
                response=resp,
            )
        except (ValueError, KeyError):
            resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────────
#  账户资金查询
# ─────────────────────────────────────────────
class AccountFunds:
    """查询账户资金信息"""

    @staticmethod
    def get_portfolio_margin_account(
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """
        统一账户 (Portfolio Margin) 余额与账户概览
        接口: GET /papi/v1/account
        返回字段包括:
          - uniMMR          : 统一保证金比例
          - accountEquity   : 账户总权益 (USD)
          - actualEquity    : 实际权益
          - accountMaintMargin : 维持保证金
          - accountInitialMargin : 初始保证金
          - accountStatus   : 账户状态
          - virtualMaxWithdrawAmount : 可转出最大金额
        """
        data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/account", {}, api_key, secret)
        return {
            "type": "portfolio_margin_account",
            "uniMMR": data.get("uniMMR"),
            "accountEquity": data.get("accountEquity"),
            "actualEquity": data.get("actualEquity"),
            "accountMaintMargin": data.get("accountMaintMargin"),
            "accountInitialMargin": data.get("accountInitialMargin"),
            "accountStatus": data.get("accountStatus"),
            "virtualMaxWithdrawAmount": data.get("virtualMaxWithdrawAmount"),
            "raw": data,
        }

    @staticmethod
    def get_portfolio_margin_balance(
        asset: Optional[str] = None,
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> list[dict]:
        """
        统一账户各资产余额明细
        接口: GET /papi/v1/balance
        可选参数 asset: 指定资产 (如 'USDT', 'BNB')，为空则返回全部
        返回字段:
          - asset           : 资产名称
          - totalWalletBalance    : 钱包余额
          - crossUnPnl      : 全仓未实现盈亏
          - availableBalance : 可用余额
          - updateTime      : 更新时间
        """
        params = {}
        if asset:
            params["asset"] = asset
        data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/balance", params, api_key, secret)
        return [
            {
                "asset": item.get("asset"),
                "totalWalletBalance": item.get("totalWalletBalance"),
                "crossUnPnl": item.get("crossUnPnl"),
                "availableBalance": item.get("availableBalance"),
                "updateTime": item.get("updateTime"),
            }
            for item in (data if isinstance(data, list) else [data])
        ]

    @staticmethod
    def get_futures_account(
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """
        标准 USDT-M 合约账户信息 (非统一账户备用)
        接口: GET /fapi/v2/account
        """
        data = _get(BinanceConfig.FAPI_BASE, "/fapi/v2/account", {}, api_key, secret)
        return {
            "type": "usdt_m_futures",
            "totalWalletBalance": data.get("totalWalletBalance"),
            "totalUnrealizedProfit": data.get("totalUnrealizedProfit"),
            "totalMarginBalance": data.get("totalMarginBalance"),
            "totalInitialMargin": data.get("totalInitialMargin"),
            "totalMaintMargin": data.get("totalMaintMargin"),
            "availableBalance": data.get("availableBalance"),
            "maxWithdrawAmount": data.get("maxWithdrawAmount"),
            "raw": data,
        }


# ─────────────────────────────────────────────
#  持仓信息查询
# ─────────────────────────────────────────────
class PositionInfo:
    """查询当前持仓"""

    @staticmethod
    def _parse_um_position(p: dict) -> dict:
        return {
            "symbol": p.get("symbol"),
            "side": "LONG" if float(p.get("positionAmt", 0)) > 0 else "SHORT",
            "positionSide": p.get("positionSide"),
            "positionAmt": p.get("positionAmt"),
            "entryPrice": p.get("entryPrice"),
            "markPrice": p.get("markPrice"),
            "unrealizedProfit": p.get("unrealizedProfit"),
            "liquidationPrice": p.get("liquidationPrice"),
            "leverage": p.get("leverage"),
            "notional": p.get("notional"),
            "isolatedMargin": p.get("isolatedMargin"),
            "marginType": p.get("marginType"),
        }

    @staticmethod
    def get_um_positions(
        symbol: Optional[str] = None,
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> list[dict]:
        """
        统一账户 USDT-M 合约持仓 (UM = USDT-Margined)

        ⚠️ 注意：/papi/v1/um/positionRisk 接口 symbol 为必填项。
           - 指定 symbol 时：直接查询该交易对持仓（快速）
           - 不指定 symbol 时：改用 /papi/v1/um/account 获取全量持仓（稍慢）

        返回字段:
          - symbol / side / positionSide / positionAmt
          - entryPrice / markPrice / unrealizedProfit
          - liquidationPrice / leverage / notional
          - isolatedMargin / marginType
        """
        if symbol:
            # 指定交易对：直接调 positionRisk（symbol 必填）
            data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/um/positionRisk",
                        {"symbol": symbol}, api_key, secret)
            positions = data if isinstance(data, list) else [data]
        else:
            # 不指定交易对：从 um/account 的 positions 字段获取全量
            data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/um/account", {}, api_key, secret)
            positions = data.get("positions", [])

        active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
        return [PositionInfo._parse_um_position(p) for p in active]

    @staticmethod
    def get_cm_positions(
        symbol: Optional[str] = None,
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> list[dict]:
        """
        统一账户 COIN-M 合约持仓 (CM = Coin-Margined)

        ⚠️ 同样：symbol 必填时走 positionRisk，不填时走 cm/account
        接口: GET /papi/v1/cm/positionRisk  或  /papi/v1/cm/account
        """
        if symbol:
            data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/cm/positionRisk",
                        {"symbol": symbol}, api_key, secret)
            positions = data if isinstance(data, list) else [data]
        else:
            data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/cm/account", {}, api_key, secret)
            positions = data.get("positions", [])

        active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
        return [
            {
                "symbol": p.get("symbol"),
                "side": "LONG" if float(p.get("positionAmt", 0)) > 0 else "SHORT",
                "positionAmt": p.get("positionAmt"),
                "entryPrice": p.get("entryPrice"),
                "markPrice": p.get("markPrice"),
                "unrealizedProfit": p.get("unrealizedProfit"),
                "liquidationPrice": p.get("liquidationPrice"),
                "leverage": p.get("leverage"),
            }
            for p in active
        ]


# ─────────────────────────────────────────────
#  历史成交记录
# ─────────────────────────────────────────────
class TradeHistory:
    """查询历史成交记录"""

    @staticmethod
    def get_um_trades(
        symbol: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> list[dict]:
        """
        统一账户 USDT-M 合约历史成交
        接口: GET /papi/v1/um/userTrades
        参数:
          - symbol     : 必填，如 'BTCUSDT'
          - start_time : 开始时间戳(ms)，如 1700000000000
          - end_time   : 结束时间戳(ms)
          - limit      : 最多返回条数，默认100，最大1000
        返回字段:
          - symbol / side / price / qty / realizedPnl
          - commission / commissionAsset
          - time (成交时间戳)
          - orderId / tradeId
          - maker (是否挂单方)
          - positionSide
        """
        params: dict = {"symbol": symbol, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/um/userTrades", params, api_key, secret)
        return [
            {
                "tradeId": t.get("id"),
                "orderId": t.get("orderId"),
                "symbol": t.get("symbol"),
                "side": t.get("side"),
                "positionSide": t.get("positionSide"),
                "price": t.get("price"),
                "qty": t.get("qty"),
                "quoteQty": t.get("quoteQty"),
                "realizedPnl": t.get("realizedPnl"),
                "commission": t.get("commission"),
                "commissionAsset": t.get("commissionAsset"),
                "time": t.get("time"),
                "maker": t.get("maker"),
            }
            for t in (data if isinstance(data, list) else [])
        ]

    @staticmethod
    def get_um_income_history(
        symbol: Optional[str] = None,
        income_type: Optional[str] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 100,
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> list[dict]:
        """
        统一账户资金流水（盈亏、手续费、资金费率等）
        接口: GET /papi/v1/um/income
        参数:
          - income_type : REALIZED_PNL / FUNDING_FEE / COMMISSION / INSURANCE_CLEAR 等
          - symbol      : 可选过滤交易对
        """
        params: dict = {"limit": limit}
        if symbol:
            params["symbol"] = symbol
        if income_type:
            params["incomeType"] = income_type
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        data = _get(BinanceConfig.PAPI_BASE, "/papi/v1/um/income", params, api_key, secret)
        return [
            {
                "symbol": item.get("symbol"),
                "incomeType": item.get("incomeType"),
                "income": item.get("income"),
                "asset": item.get("asset"),
                "info": item.get("info"),
                "time": item.get("time"),
                "tradeId": item.get("tradeId"),
            }
            for item in (data if isinstance(data, list) else [])
        ]


# ─────────────────────────────────────────────
#  聚合查询（一键获取账户全貌）
# ─────────────────────────────────────────────
class AccountSnapshot:
    """一键获取账户全貌快照"""

    @staticmethod
    def full_snapshot(
        api_key: str = BinanceConfig.API_KEY,
        secret: str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """
        返回账户资金 + 所有持仓的综合快照
        适合在策略启动时或定时轮询时调用
        """
        account = AccountFunds.get_portfolio_margin_account(api_key, secret)
        balances = AccountFunds.get_portfolio_margin_balance(api_key=api_key, secret=secret)
        um_positions = PositionInfo.get_um_positions(api_key=api_key, secret=secret)
        cm_positions = PositionInfo.get_cm_positions(api_key=api_key, secret=secret)

        return {
            "timestamp": int(time.time() * 1000),
            "account": account,
            "balances": balances,
            "um_positions": um_positions,    # USDT-M 持仓
            "cm_positions": cm_positions,    # COIN-M 持仓
        }


# ─────────────────────────────────────────────
#  本地测试入口
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # ⚠️ 使用前请在 BinanceConfig 中填写你的 API Key & Secret
    # 或通过环境变量注入（推荐生产环境使用）
    import os
    BinanceConfig.API_KEY = os.getenv("BINANCE_API_KEY", BinanceConfig.API_KEY)
    BinanceConfig.SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", BinanceConfig.SECRET_KEY)

    print("=" * 60)
    print("  账户全貌快照")
    print("=" * 60)
    snapshot = AccountSnapshot.full_snapshot()
    print(json.dumps(snapshot, indent=2, ensure_ascii=False))
