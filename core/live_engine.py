import asyncio
import json
import traceback
from datetime import datetime, timedelta
import pandas as pd

from core.backtester import DataFetcher, TrendAnalyzer, Indicators, h4_confirm, h1_entry_signal, CONFIG
from core.order_manager import OrderManager

class LiveEngine:
    def __init__(self):
        self.is_running = False
        self.symbol = "ETHUSDC"
        self.fetcher = DataFetcher()
        self.queues = []
        self.dry_run = True # Safe mode for the first time
        
    async def add_client(self, queue: asyncio.Queue):
        self.queues.append(queue)
        
    async def remove_client(self, queue: asyncio.Queue):
        if queue in self.queues:
            self.queues.remove(queue)
            
    async def broadcast(self, message: dict):
        for q in self.queues:
            await q.put(message)

    def start(self, symbol: str):
        if self.is_running:
            return
        self.symbol = symbol
        self.is_running = True
        asyncio.create_task(self._loop())
        
    def stop(self):
        self.is_running = False

    async def _loop(self):
        await self.broadcast({"type": "log", "message": f"[SYSTEM] 机器人已启动，监听 {self.symbol}，每 30 秒轮询一次...", "level": "sys-msg"})
        if self.dry_run:
            await self.broadcast({"type": "log", "message": f"[SYSTEM] 当前为 Dry-Run 模式，不会向币安发送真实订单。", "level": "warning"})
        
        while self.is_running:
            try:
                now = datetime.now()
                # Use a smaller lookback for live to avoid massive fetch
                fetch_start = now - timedelta(days=30) 
                
                # Fetch data in threads to not block the asyncio event loop
                df_1d = await asyncio.to_thread(self.fetcher.fetch_ohlcv, self.symbol.replace("USDC", "/USDC"), "1d", fetch_start, now)
                df_4h = await asyncio.to_thread(self.fetcher.fetch_ohlcv, self.symbol.replace("USDC", "/USDC"), "4h", fetch_start, now)
                df_1h = await asyncio.to_thread(self.fetcher.fetch_ohlcv, self.symbol.replace("USDC", "/USDC"), "1h", fetch_start, now)
                
                if df_1d.empty or df_4h.empty or df_1h.empty:
                    await self.broadcast({"type": "log", "message": "[ERROR] 获取 K线数据失败或数据不足，等待下一次重试。", "level": "error"})
                    await asyncio.sleep(30)
                    continue
                    
                # Calculate indicators
                df_1d["ma5"] = Indicators.sma(df_1d["close"], CONFIG["daily_ma_fast"])
                df_1d["ma20"] = Indicators.sma(df_1d["close"], CONFIG["daily_ma_slow"])
                adx_1h = Indicators.adx(df_1h, CONFIG["adx_period"])
                
                d_idx = len(df_1d) - 1
                h1_idx = len(df_1h) - 1
                
                price = float(df_1h["close"].iloc[-1])
                
                # Analyze Signals
                trend = TrendAnalyzer.daily_trend(df_1d, d_idx)
                is_bull = trend == "bull"
                
                confirmed, sup_4h, res_4h = h4_confirm(price, df_4h, trend)
                signal, sl_level = h1_entry_signal(price, df_1h, trend)
                
                adx_val = adx_1h.iloc[h1_idx]
                
                dist_pct = "--"
                dist_val = 999.0
                if trend == "bull" and sl_level is not None:
                    dist_val = (price - sl_level) / sl_level * 100
                    dist_pct = f"{dist_val:.2f}%"
                elif trend == "bear" and sl_level is not None:
                    dist_val = (sl_level - price) / sl_level * 100
                    dist_pct = f"{dist_val:.2f}%"
                
                # Emit signal update
                await self.broadcast({
                    "type": "signal_update",
                    "daily": {
                        "text": "多头 (P>MA)" if is_bull else "空头 (P<MA)" if trend == "bear" else "中性", 
                        "color": "var(--primary)" if is_bull else "var(--danger)" if trend == "bear" else "var(--text-muted)"
                    },
                    "h4": {
                        "text": "支撑确认" if confirmed and is_bull else "压力确认" if confirmed and trend=="bear" else "等待确认", 
                        "color": "var(--primary)" if confirmed else "var(--warning)"
                    },
                    "dist": {
                        "text": dist_pct, 
                        "color": "var(--primary)" if dist_val < CONFIG["max_entry_dist"] * 100 else "var(--text-muted)"
                    },
                    "adx": {
                        "text": f"{adx_val:.1f}" if not pd.isna(adx_val) else "--", 
                        "color": "var(--primary)" if not pd.isna(adx_val) and adx_val > CONFIG["adx_min"] else "var(--warning)"
                    }
                })
                
                log_trend = "多" if is_bull else "空" if trend == "bear" else "平"
                await self.broadcast({
                    "type": "log",
                    "message": f"实时分析: 日线{log_trend}, 4H{'已确认' if confirmed else '未确认'}, 距{'支撑' if is_bull else '压力'}{dist_pct}, ADX={(f'{adx_val:.1f}' if not pd.isna(adx_val) else '--')}, 现价={price:.2f}",
                    "level": ""
                })
                
                # Check execution
                if trend and confirmed and signal and not pd.isna(adx_val) and adx_val > CONFIG["adx_min"]:
                    action_side = "BUY" if is_bull else "SELL"
                    position_side = "LONG" if is_bull else "SHORT"
                    qty = 0.001 # FIXED SAFE QUANTITY
                    
                    await self.broadcast({
                        "type": "log",
                        "message": f"🚀 信号完全共振！准备执行下单: {action_side} {qty} @ {price:.2f}",
                        "level": "highlight"
                    })
                    
                    if not self.dry_run:
                        try:
                            if action_side == "BUY":
                                res = await asyncio.to_thread(OrderManager.market_open_long, qty, symbol=self.symbol)
                            else:
                                res = await asyncio.to_thread(OrderManager.market_open_short, qty, symbol=self.symbol)
                                
                            order_id = res.get("orderId", "N/A")
                            await self.broadcast({
                                "type": "execution",
                                "side": action_side,
                                "posSide": position_side,
                                "orderType": "MARKET",
                                "qty": qty,
                                "price": price,
                                "orderId": order_id
                            })
                        except Exception as e:
                            await self.broadcast({"type": "log", "message": f"❌ 下单失败: {e}", "level": "error"})
                    else:
                        await self.broadcast({
                            "type": "execution",
                            "side": action_side,
                            "posSide": position_side,
                            "orderType": "MOCK_MARKET",
                            "qty": qty,
                            "price": price,
                            "orderId": f"mock_{int(datetime.now().timestamp())}"
                        })
                        
            except Exception as e:
                traceback.print_exc()
                await self.broadcast({"type": "log", "message": f"[ERROR] 监控循环异常: {e}", "level": "error"})
                
            # Wait for next poll
            for _ in range(30):
                if not self.is_running:
                    break
                await asyncio.sleep(1)

live_engine = LiveEngine()
