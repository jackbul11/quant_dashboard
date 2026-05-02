"""
币安合约订单操作模块
账户类型：统一账户 (Portfolio Margin)  接口前缀：/papi/
交易品种：ETH/USDC  U本位永续合约  (symbol = ETHUSDC)

功能：
  1. 设置杠杆
  2. 市价单买入 / 卖出（开仓 & 平仓）
  3. 限价单下单
  4. 撤单 / 撤全部挂单
  5. 查询指定订单 / 查询所有挂单
  6. 查询当前持仓
  7. 交互式测试终端（命令行菜单）
"""

import hashlib
import hmac
import os
import time
from typing import Optional
from urllib.parse import urlencode

import requests


# ════════════════════════════════════════════════
#  配置区  ── 与 account_info.py 保持一致
# ════════════════════════════════════════════════
class BinanceConfig:
    API_KEY:    str  = os.getenv("BINANCE_API_KEY",    "SUaC72q0dNwHQMsxsNy1kHYhiJsHVj6abxnQjqT65f17RrW4nPPQBJEl5E5jIvli")   # 建议用环境变量
    SECRET_KEY: str  = os.getenv("BINANCE_SECRET_KEY", "MwOsFq6mwGOkY3021SQQtDKjAgH2uMhzCMXA9STww9J59OHCHgA9AAMb70Gnw2V2")
    RECV_WINDOW: int = 5000

    PAPI_BASE = "https://papi.binance.com"   # 统一账户

    # 代理（与 account_info.py 相同，按需修改）
    PROXY_HOST: str  = "127.0.0.1"
    PROXY_PORT: int  = 7897
    USE_PROXY:  bool = True

    # 默认交易对（U本位 ETH/USDC 永续）
    DEFAULT_SYMBOL: str = "ETHUSDC"

    @classmethod
    def get_proxies(cls) -> Optional[dict]:
        if not cls.USE_PROXY:
            return None
        url = f"http://{cls.PROXY_HOST}:{cls.PROXY_PORT}"
        return {"http": url, "https": url}


# ════════════════════════════════════════════════
#  底层 HTTP 工具
# ════════════════════════════════════════════════
def _sign(params: dict, secret: str) -> str:
    qs = urlencode(params)
    return hmac.new(secret.encode(), qs.encode(), hashlib.sha256).hexdigest()


def _headers(api_key: str) -> dict:
    return {"X-MBX-APIKEY": api_key, "Content-Type": "application/json"}


def _raise_for(resp: requests.Response):
    """统一错误处理：打印币安原始错误码和消息"""
    if not resp.ok:
        try:
            err = resp.json()
            raise requests.HTTPError(
                f"HTTP {resp.status_code} | 币安错误码: {err.get('code')} | {err.get('msg')}",
                response=resp,
            )
        except (ValueError, KeyError):
            resp.raise_for_status()


# ── 服务器时间同步 ───────────────────────────
# 缓存时间偏移量，避免每次请求都查一次
_time_offset_ms: int = 0


def _sync_server_time() -> int:
    """
    从币安获取服务器时间，计算本地时钟偏移量并缓存。
    修复 -1021: Timestamp outside of recvWindow（本地时钟偏差过大时触发）。
    返回当前应使用的时间戳(ms)。
    """
    global _time_offset_ms
    try:
        resp = requests.get(
            "https://fapi.binance.com/fapi/v1/time",   # 公开接口，无需签名
            proxies=BinanceConfig.get_proxies(), timeout=5,
        )
        server_ts = resp.json()["serverTime"]
        _time_offset_ms = server_ts - int(time.time() * 1000)
        print(f"[i] 时间同步完成，本地偏差 {_time_offset_ms} ms")
    except Exception as e:
        print(f"[!] 时间同步失败（使用本地时间）: {e}")
    return int(time.time() * 1000) + _time_offset_ms


def _now_ms() -> int:
    """返回经过偏移校正的当前时间戳(ms)"""
    return int(time.time() * 1000) + _time_offset_ms


def _get(path: str, params: dict,
         api_key=BinanceConfig.API_KEY,
         secret=BinanceConfig.SECRET_KEY) -> dict:
    params["timestamp"]  = _now_ms()
    params["recvWindow"] = BinanceConfig.RECV_WINDOW
    params["signature"]  = _sign(params, secret)
    resp = requests.get(
        BinanceConfig.PAPI_BASE + path, params=params,
        headers=_headers(api_key), proxies=BinanceConfig.get_proxies(), timeout=10,
    )
    _raise_for(resp)
    return resp.json()


def _post(path: str, params: dict,
          api_key=BinanceConfig.API_KEY,
          secret=BinanceConfig.SECRET_KEY) -> dict:
    params["timestamp"]  = _now_ms()
    params["recvWindow"] = BinanceConfig.RECV_WINDOW
    params["signature"]  = _sign(params, secret)
    resp = requests.post(
        BinanceConfig.PAPI_BASE + path, params=params,
        headers=_headers(api_key), proxies=BinanceConfig.get_proxies(), timeout=10,
    )
    _raise_for(resp)
    return resp.json()


def _delete(path: str, params: dict,
            api_key=BinanceConfig.API_KEY,
            secret=BinanceConfig.SECRET_KEY) -> dict:
    params["timestamp"]  = _now_ms()
    params["recvWindow"] = BinanceConfig.RECV_WINDOW
    params["signature"]  = _sign(params, secret)
    resp = requests.delete(
        BinanceConfig.PAPI_BASE + path, params=params,
        headers=_headers(api_key), proxies=BinanceConfig.get_proxies(), timeout=10,
    )
    _raise_for(resp)
    return resp.json()


# ════════════════════════════════════════════════
#  杠杆设置
# ════════════════════════════════════════════════
class LeverageManager:

    @staticmethod
    def set_leverage(
        leverage: int,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret: str  = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """
        设置合约杠杆倍数
        接口: POST /papi/v1/um/leverage
        参数:
          leverage : 1 ~ 125（ETH 最高支持 100x，具体以币安为准）
        返回:
          leverage / symbol / maxNotionalValue
        """
        if not 1 <= leverage <= 125:
            raise ValueError(f"杠杆倍数必须在 1~125 之间，当前: {leverage}")

        data = _post("/papi/v1/um/leverage", {
            "symbol":   symbol,
            "leverage": leverage,
        }, api_key, secret)

        print(f"[✓] 杠杆设置成功  {symbol}  {data.get('leverage')}x  "
              f"最大名义价值: {data.get('maxNotionalValue')} USDC")
        return data


# ════════════════════════════════════════════════
#  订单操作
# ════════════════════════════════════════════════
class OrderManager:
    """
    所有方向说明（双向持仓模式）：
      positionSide = LONG  → 多仓
      positionSide = SHORT → 空仓
      side = BUY  + positionSide = LONG  → 开多
      side = SELL + positionSide = LONG  → 平多
      side = SELL + positionSide = SHORT → 开空
      side = BUY  + positionSide = SHORT → 平空

    单向持仓模式：
      positionSide = BOTH，side = BUY / SELL
    """

    # ── 市价单 ──────────────────────────────────
    @staticmethod
    def market_open_long(
        quantity: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """市价开多（做多）"""
        return OrderManager._place_order(
            symbol=symbol, side="BUY", order_type="MARKET",
            quantity=quantity, position_side="LONG",
            api_key=api_key, secret=secret,
        )

    @staticmethod
    def market_close_long(
        quantity: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """市价平多"""
        return OrderManager._place_order(
            symbol=symbol, side="SELL", order_type="MARKET",
            quantity=quantity, position_side="LONG",
            api_key=api_key, secret=secret,
        )

    @staticmethod
    def market_open_short(
        quantity: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """市价开空（做空）"""
        return OrderManager._place_order(
            symbol=symbol, side="SELL", order_type="MARKET",
            quantity=quantity, position_side="SHORT",
            api_key=api_key, secret=secret,
        )

    @staticmethod
    def market_close_short(
        quantity: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """市价平空"""
        return OrderManager._place_order(
            symbol=symbol, side="BUY", order_type="MARKET",
            quantity=quantity, position_side="SHORT",
            api_key=api_key, secret=secret,
        )

    # ── 限价单 ──────────────────────────────────
    @staticmethod
    def limit_open_long(
        quantity: float,
        price: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        time_in_force: str = "GTC",
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """限价开多"""
        return OrderManager._place_order(
            symbol=symbol, side="BUY", order_type="LIMIT",
            quantity=quantity, price=price,
            position_side="LONG", time_in_force=time_in_force,
            api_key=api_key, secret=secret,
        )

    @staticmethod
    def limit_close_long(
        quantity: float,
        price: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        time_in_force: str = "GTC",
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """限价平多"""
        return OrderManager._place_order(
            symbol=symbol, side="SELL", order_type="LIMIT",
            quantity=quantity, price=price,
            position_side="LONG", time_in_force=time_in_force,
            api_key=api_key, secret=secret,
        )

    @staticmethod
    def limit_open_short(
        quantity: float,
        price: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        time_in_force: str = "GTC",
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """限价开空"""
        return OrderManager._place_order(
            symbol=symbol, side="SELL", order_type="LIMIT",
            quantity=quantity, price=price,
            position_side="SHORT", time_in_force=time_in_force,
            api_key=api_key, secret=secret,
        )

    @staticmethod
    def limit_close_short(
        quantity: float,
        price: float,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        time_in_force: str = "GTC",
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """限价平空"""
        return OrderManager._place_order(
            symbol=symbol, side="BUY", order_type="LIMIT",
            quantity=quantity, price=price,
            position_side="SHORT", time_in_force=time_in_force,
            api_key=api_key, secret=secret,
        )

    # ── 撤单 ────────────────────────────────────
    @staticmethod
    def cancel_order(
        order_id: int,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """
        撤销指定订单。
        注意：-2011 Unknown order 常见原因：
          1. orderId 输入错误
          2. 订单已成交或已被撤销
          3. 该订单属于其他交易对
        建议先用 [10] 查询当前挂单确认 orderId 后再撤销。
        """
        data = _delete("/papi/v1/um/order", {
            "symbol":  symbol,
            "orderId": order_id,
        }, api_key, secret)
        print(f"[✓] 已撤销订单  orderId={data.get('orderId')}  状态={data.get('status')}")
        return data

    @staticmethod
    def cancel_all_open_orders(
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """撤销该交易对所有挂单"""
        data = _delete("/papi/v1/um/allOpenOrders", {
            "symbol": symbol,
        }, api_key, secret)
        print(f"[✓] 已撤销 {symbol} 所有挂单")
        return data

    # ── 查询 ────────────────────────────────────
    @staticmethod
    def get_order(
        order_id: int,
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """查询指定订单详情"""
        return _get("/papi/v1/um/order", {
            "symbol":  symbol,
            "orderId": order_id,
        }, api_key, secret)

    @staticmethod
    def get_open_orders(
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> list[dict]:
        """查询所有当前挂单"""
        data = _get("/papi/v1/um/openOrders", {"symbol": symbol}, api_key, secret)
        return data if isinstance(data, list) else []

    @staticmethod
    def get_position(
        symbol: str = BinanceConfig.DEFAULT_SYMBOL,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> list[dict]:
        """查询当前持仓（指定交易对）"""
        data = _get("/papi/v1/um/positionRisk", {"symbol": symbol}, api_key, secret)
        positions = data if isinstance(data, list) else [data]
        return [p for p in positions if float(p.get("positionAmt", 0)) != 0]

    # ── 内部通用下单 ─────────────────────────────
    @staticmethod
    def _place_order(
        symbol: str,
        side: str,            # BUY / SELL
        order_type: str,      # MARKET / LIMIT
        quantity: float,
        position_side: str,   # LONG / SHORT / BOTH
        price: Optional[float] = None,
        time_in_force: Optional[str] = None,
        api_key: str = BinanceConfig.API_KEY,
        secret:  str = BinanceConfig.SECRET_KEY,
    ) -> dict:
        """
        接口: POST /papi/v1/um/order
        返回关键字段:
          orderId / symbol / side / positionSide / type
          origQty / price / avgPrice / status
          cumQuote (成交金额) / executedQty (成交数量)
        """
        params: dict = {
            "symbol":       symbol,
            "side":         side,
            "positionSide": position_side,
            "type":         order_type,
            "quantity":     quantity,
        }
        if order_type == "LIMIT":
            if price is None:
                raise ValueError("限价单必须指定 price")
            params["price"]       = price
            params["timeInForce"] = time_in_force or "GTC"

        data = _post("/papi/v1/um/order", params, api_key, secret)

        action = {
            ("BUY",  "LONG"):  "开多 ▲",
            ("SELL", "LONG"):  "平多 ▼",
            ("SELL", "SHORT"): "开空 ▼",
            ("BUY",  "SHORT"): "平空 ▲",
        }.get((side, position_side), f"{side} {position_side}")

        print(
            f"[✓] 下单成功  {symbol}  {action}  "
            f"类型={data.get('type')}  数量={data.get('origQty')}  "
            f"均价={data.get('avgPrice') or data.get('price')}  "
            f"状态={data.get('status')}  orderId={data.get('orderId')}"
        )
        return data


# ════════════════════════════════════════════════
#  交互式测试终端
# ════════════════════════════════════════════════
def _input_float(prompt: str) -> float:
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("  请输入有效数字")


def _input_int(prompt: str) -> int:
    while True:
        try:
            return int(input(prompt).strip())
        except ValueError:
            print("  请输入有效整数")


def interactive_terminal():
    import json

    symbol = BinanceConfig.DEFAULT_SYMBOL
    api_key = BinanceConfig.API_KEY
    secret  = BinanceConfig.SECRET_KEY

    MENU = """
╔══════════════════════════════════════════╗
║   ETH/USDC 合约订单测试终端              ║
║   交易对: {symbol:<28}║
╠══════════════════════════════════════════╣
║  [1] 设置杠杆                            ║
║  [2] 市价开多                            ║
║  [3] 市价平多                            ║
║  [4] 市价开空                            ║
║  [5] 市价平空                            ║
║  [6] 限价开多                            ║
║  [7] 限价开空                            ║
║  [8] 撤销指定订单                        ║
║  [9] 撤销所有挂单                        ║
║  [10] 查询当前挂单                       ║
║  [11] 查询当前持仓                       ║
║  [0] 退出                                ║
╚══════════════════════════════════════════╝
"""

    print(MENU.format(symbol=symbol))

    # 启动时自动同步一次服务器时间，防止 -1021 时间戳错误
    _sync_server_time()
    print()

    while True:
        choice = input("请输入操作编号 > ").strip()
        print()

        try:
            if choice == "0":
                print("退出终端。")
                break

            elif choice == "1":
                lv = _input_int("  杠杆倍数 (1-100): ")
                LeverageManager.set_leverage(lv, symbol, api_key, secret)

            elif choice == "2":
                qty = _input_float("  开多数量 (ETH 数量，如 0.01): ")
                r = OrderManager.market_open_long(qty, symbol, api_key, secret)
                print(json.dumps(r, indent=2, ensure_ascii=False))

            elif choice == "3":
                qty = _input_float("  平多数量 (ETH 数量): ")
                r = OrderManager.market_close_long(qty, symbol, api_key, secret)
                print(json.dumps(r, indent=2, ensure_ascii=False))

            elif choice == "4":
                qty = _input_float("  开空数量 (ETH 数量，如 0.01): ")
                r = OrderManager.market_open_short(qty, symbol, api_key, secret)
                print(json.dumps(r, indent=2, ensure_ascii=False))

            elif choice == "5":
                qty = _input_float("  平空数量 (ETH 数量): ")
                r = OrderManager.market_close_short(qty, symbol, api_key, secret)
                print(json.dumps(r, indent=2, ensure_ascii=False))

            elif choice == "6":
                qty   = _input_float("  开多数量 (ETH): ")
                price = _input_float("  限价价格 (USDC): ")
                r = OrderManager.limit_open_long(qty, price, symbol, api_key=api_key, secret=secret)
                print(json.dumps(r, indent=2, ensure_ascii=False))

            elif choice == "7":
                qty   = _input_float("  开空数量 (ETH): ")
                price = _input_float("  限价价格 (USDC): ")
                r = OrderManager.limit_open_short(qty, price, symbol, api_key=api_key, secret=secret)
                print(json.dumps(r, indent=2, ensure_ascii=False))

            elif choice == "8":
                # 先列出当前挂单，方便确认 orderId
                orders = OrderManager.get_open_orders(symbol, api_key, secret)
                if not orders:
                    print("  当前无挂单，无需撤销")
                else:
                    print("  当前挂单列表：")
                    for o in orders:
                        print(
                            f"    orderId={o.get('orderId')}  "
                            f"{o.get('side')} {o.get('positionSide')}  "
                            f"类型={o.get('type')}  "
                            f"数量={o.get('origQty')}  价格={o.get('price')}  "
                            f"状态={o.get('status')}"
                        )
                    oid = _input_int("  输入要撤销的 orderId: ")
                    valid_ids = [int(o.get("orderId", -1)) for o in orders]
                    if oid not in valid_ids:
                        print(f"  [!] orderId={oid} 不在当前挂单列表中，请确认后重试")
                    else:
                        r = OrderManager.cancel_order(oid, symbol, api_key, secret)
                        print(json.dumps(r, indent=2, ensure_ascii=False))

            elif choice == "9":
                confirm = input(f"  确认撤销 {symbol} 所有挂单？(y/N): ").strip().lower()
                if confirm == "y":
                    r = OrderManager.cancel_all_open_orders(symbol, api_key, secret)
                    print(json.dumps(r, indent=2, ensure_ascii=False))
                else:
                    print("  已取消")

            elif choice == "10":
                orders = OrderManager.get_open_orders(symbol, api_key, secret)
                if not orders:
                    print("  当前无挂单")
                else:
                    for o in orders:
                        print(
                            f"  orderId={o.get('orderId')}  "
                            f"{o.get('side')} {o.get('positionSide')}  "
                            f"类型={o.get('type')}  "
                            f"数量={o.get('origQty')}  价格={o.get('price')}  "
                            f"状态={o.get('status')}"
                        )

            elif choice == "11":
                positions = OrderManager.get_position(symbol, api_key, secret)
                if not positions:
                    print("  当前无持仓")
                else:
                    for p in positions:
                        amt  = float(p.get("positionAmt", 0))
                        side = "多仓 ▲" if amt > 0 else "空仓 ▼"
                        print(
                            f"  {symbol}  {side}  数量={p.get('positionAmt')}  "
                            f"开仓均价={p.get('entryPrice')}  "
                            f"标记价={p.get('markPrice')}  "
                            f"未实现盈亏={p.get('unrealizedProfit')}  "
                            f"杠杆={p.get('leverage')}x  "
                            f"爆仓价={p.get('liquidationPrice')}"
                        )
            else:
                print("  无效选项，请重新输入")

        except Exception as e:
            print(f"  [✗] 操作失败: {e}")

        print()


# ════════════════════════════════════════════════
#  入口
# ════════════════════════════════════════════════
if __name__ == "__main__":
    # Key 也可以直接写在这里（仅本地测试用）
    # BinanceConfig.API_KEY    = "你的APIKey"
    # BinanceConfig.SECRET_KEY = "你的SecretKey"

    # 代理端口按需修改
    # BinanceConfig.PROXY_PORT = 7890

    interactive_terminal()
