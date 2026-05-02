#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║     ETH 日内多周期合约回测系统  v4.0  (用户策略版)                    ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  【策略逻辑（严格按照用户模型）】                                       ║
║  日线判断方向                                                        ║
║    多头: 收盘 > MA5 AND 收盘 > 开盘 AND 收盘 > MA20                  ║
║    空头: 收盘 < MA5 AND 收盘 < 开盘 AND 收盘 < MA20                  ║
║                                                                  ║
║  4H确认趋势                                                         ║
║    多头: 当前价格处于4H支撑位上方                                       ║
║    空头: 当前价格处于4H压力位下方                                       ║
║                                                                  ║
║  1H入场                                                            ║
║    多头: 价格在1H支撑上方 且 距支撑 < 2% → 入场做多                    ║
║    空头: 价格在1H压力下方 且 距压力 < 2% → 入场做空                    ║
║    止盈: 4H压力位  |  止损: 1H支撑位下方0.1%                          ║
║                                                                  ║
║  【继承v3风控体系】                                                    ║
║  [A] 动态仓位    : 回撤>10%→半仓  回撤>20%→四分之一仓                 ║
║  [B] 连续亏损保护: 连续3笔止损→暂停1天                                 ║
║  [C] ADX过滤    : ADX<20(震荡市)→不开仓                              ║
║  [D] 移动止损    : 1R保本 / 2R锁定0.5R利润                           ║
║  [E] 日风控      : 单日亏损>2%→停止当日交易                            ║
║                                                                  ║
║  数据源: Binance  |  执行周期: 1H K线驱动  |  无需15m数据              ║
╚══════════════════════════════════════════════════════════════════╝
"""

import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
plt.rcParams["font.family"] = ["SimHei", "PingFang SC", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


# ════════════════════════════════════════════════════════════════
#  ⚙️  全局配置
# ════════════════════════════════════════════════════════════════
CONFIG = {
    "symbols":          ["ETH/USDT"],
    "start_date":       "2022-01-01",
    "end_date":         "2025-12-31",
    "initial_capital":  10_000,
    "leverage":         3,             # 合约杠杆倍数

    # ── 用户策略核心参数 ──────────────────────────────────────────
    "daily_ma_fast":    5,             # 日线 MA5
    "daily_ma_slow":    20,            # 日线 MA20
    "max_entry_dist":   0.02,          # 距1H支撑/压力最大距离 2%
    "sl_buffer_pct":    0.001,         # 止损在支撑下方额外缓冲 0.1%

    # ── 支撑/压力识别参数 ─────────────────────────────────────────
    "sr_swing_window":  8,             # 摆动高低点识别窗口（根K线）
    "sr_lookback_4h":   60,            # 4H支撑压力参考的历史K线数
    "sr_lookback_1h":   80,            # 1H支撑压力参考的历史K线数
    "sr_cluster_pct":   0.005,         # 聚类合并阈值 0.5%
    "min_rr":           1.5,           # 最低盈亏比要求

    # ── v3 风控参数（保持不变）────────────────────────────────────
    "adx_period":       14,
    "adx_min":          18,            # ADX低于此值视为震荡市
    "dd_half_pos":      0.10,          # 回撤>10% → 半仓
    "dd_quarter_pos":   0.20,          # 回撤>20% → 四分之一仓
    "consec_loss_max":  5,             # 连续止损N次暂停
    "consec_loss_pause_days": 1,
    "trail_be_trigger": 1.5,           # 浮盈1R → 保本
    "trail_lock_trigger": 2.0,         # 浮盈2R → 锁定0.5R
    "trail_lock_ratio": 0.5,
    "daily_loss_limit_pct": 0.03,      # 日亏损限额 2%

    # ── 交易所 ────────────────────────────────────────────────────
    "exchange":         "binance",
    "taker_fee":        0.0005,
    "proxy_port":       7897,          # ← 改成你本地代理端口（Clash/V2ray等）
}


# ════════════════════════════════════════════════════════════════
#  数据结构
# ════════════════════════════════════════════════════════════════
@dataclass
class Trade:
    symbol:        str
    direction:     str
    entry_time:    datetime
    entry_price:   float
    stop_loss:     float
    take_profit:   float
    position_size: float
    rr_ratio:      float = 0.0
    sl_distance:   float = 0.0

    exit_time:     Optional[datetime] = None
    exit_price:    Optional[float]    = None
    exit_reason:   str = ""
    pnl_pct:       float = 0.0
    pnl_usdt:      float = 0.0

    be_triggered:   bool = False
    lock_triggered: bool = False

    @property
    def is_open(self): return self.exit_time is None


@dataclass
class BacktestResult:
    symbol:       str
    trades:       List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    daily_stats:  Dict        = field(default_factory=dict)

    @property
    def total_trades(self):   return len(self.trades)
    @property
    def winning_trades(self): return [t for t in self.trades if t.pnl_usdt > 0]
    @property
    def win_rate(self):
        return len(self.winning_trades) / self.total_trades if self.trades else 0.0
    @property
    def total_pnl(self):      return sum(t.pnl_usdt for t in self.trades)
    @property
    def avg_win(self):
        w = [t.pnl_usdt for t in self.trades if t.pnl_usdt > 0]
        return np.mean(w) if w else 0.0
    @property
    def avg_loss(self):
        l = [t.pnl_usdt for t in self.trades if t.pnl_usdt < 0]
        return np.mean(l) if l else 0.0
    @property
    def profit_factor(self):
        gp = sum(t.pnl_usdt for t in self.trades if t.pnl_usdt > 0)
        gl = abs(sum(t.pnl_usdt for t in self.trades if t.pnl_usdt < 0))
        return gp / gl if gl > 0 else float("inf")
    @property
    def max_drawdown(self):
        if not self.equity_curve: return 0.0
        peak = self.equity_curve[0]; max_dd = 0.0
        for v in self.equity_curve:
            if v > peak: peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd
    @property
    def sharpe_ratio(self):
        if len(self.trades) < 2: return 0.0
        rets = np.array([t.pnl_pct for t in self.trades])
        std  = np.std(rets)
        return (np.mean(rets) / std * np.sqrt(252)) if std > 0 else 0.0
    @property
    def avg_rr(self):
        rrs = [t.rr_ratio for t in self.trades if t.rr_ratio > 0]
        return np.mean(rrs) if rrs else 0.0
    @property
    def long_trades(self):    return [t for t in self.trades if t.direction == "long"]
    @property
    def short_trades(self):   return [t for t in self.trades if t.direction == "short"]
    @property
    def daily_stop_count(self):
        return sum(1 for v in self.daily_stats.values() if v.get("stopped", False))
    @property
    def consec_pause_count(self):
        return sum(1 for v in self.daily_stats.values() if v.get("paused", False))
    @property
    def be_count(self):   return sum(1 for t in self.trades if t.be_triggered)
    @property
    def lock_count(self): return sum(1 for t in self.trades if t.lock_triggered)


# ════════════════════════════════════════════════════════════════
#  数据获取
# ════════════════════════════════════════════════════════════════
class DataFetcher:
    def __init__(self):
        try:
            import ccxt
            self.exchange = getattr(ccxt, CONFIG["exchange"])({
                "enableRateLimit": True,
                "options": {"defaultType": "future"},
                "proxies": {
                    "http":  f"http://127.0.0.1:{CONFIG['proxy_port']}",
                    "https": f"http://127.0.0.1:{CONFIG['proxy_port']}",
                },
            })
        except ImportError:
            raise ImportError("请先安装 ccxt: pip install ccxt")

    def fetch_ohlcv(self, symbol, timeframe, since, until) -> pd.DataFrame:
        since_ms = int(since.timestamp() * 1000)
        until_ms = int(until.timestamp() * 1000)
        all_candles = []
        print(f"  ↓ {symbol:12s} [{timeframe:4s}]", end="", flush=True)
        retry = 0
        while since_ms < until_ms:
            try:
                candles = self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=since_ms, limit=1000
                )
                if not candles: break
                all_candles.extend(candles)
                since_ms = candles[-1][0] + 1
                time.sleep(0.15); retry = 0
            except Exception as e:
                retry += 1
                if retry > 3: print(f"  ! 重试失败: {e}"); break
                time.sleep(2 * retry)
        print(f"  {len(all_candles):>6,} 条  OK")
        if not all_candles: return pd.DataFrame()
        df = pd.DataFrame(all_candles,
                          columns=["timestamp","open","high","low","close","volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
        df = df[df["timestamp"] <= pd.Timestamp(until)]
        df.set_index("timestamp", inplace=True)
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df.astype(float)


# ════════════════════════════════════════════════════════════════
#  技术指标
# ════════════════════════════════════════════════════════════════
class Indicators:

    @staticmethod
    def sma(series, period):
        return series.rolling(period).mean()

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high  = df["high"]; low = df["low"]; close = df["close"]
        plus_dm  = high.diff().clip(lower=0)
        minus_dm = (-low.diff()).clip(lower=0)
        # 只保留单方向更大的
        mask = plus_dm >= minus_dm
        plus_dm_clean  = plus_dm.where(mask, 0)
        minus_dm_clean = minus_dm.where(~mask, 0)
        prev_c = close.shift(1)
        tr = pd.concat([(high-low), (high-prev_c).abs(), (low-prev_c).abs()], axis=1).max(axis=1)
        atr14    = tr.rolling(period).mean()
        plus_di  = 100 * plus_dm_clean.rolling(period).mean()  / atr14
        minus_di = 100 * minus_dm_clean.rolling(period).mean() / atr14
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        return dx.rolling(period).mean()


# ════════════════════════════════════════════════════════════════
#  支撑/压力识别（摆动高低点 + 聚类合并）
# ════════════════════════════════════════════════════════════════
class SupportResistance:

    @staticmethod
    def swing_levels(df: pd.DataFrame, window: int) -> tuple:
        """返回 (highs数组, lows数组)，均已排序"""
        highs, lows = [], []
        arr_h = df["high"].values
        arr_l = df["low"].values
        for i in range(window, len(df) - window):
            if arr_h[i] == max(arr_h[i - window: i + window + 1]):
                highs.append(arr_h[i])
            if arr_l[i] == min(arr_l[i - window: i + window + 1]):
                lows.append(arr_l[i])
        return np.array(sorted(highs)), np.array(sorted(lows))

    @staticmethod
    def cluster(levels: np.ndarray, tol: float = None) -> np.ndarray:
        if tol is None: tol = CONFIG["sr_cluster_pct"]
        if len(levels) == 0: return np.array([])
        clustered, group = [], [levels[0]]
        for lvl in levels[1:]:
            if (lvl - group[-1]) / group[-1] < tol:
                group.append(lvl)
            else:
                clustered.append(float(np.mean(group)))
                group = [lvl]
        clustered.append(float(np.mean(group)))
        return np.array(clustered)

    @classmethod
    def nearest_support(cls, price: float, df: pd.DataFrame, window: int, lookback: int):
        """返回价格下方最近的支撑位，找不到返回 None"""
        past = df.tail(lookback)
        if len(past) < window * 2 + 1:
            return None
        _, lows = cls.swing_levels(past, window)
        levels  = cls.cluster(lows)
        below   = levels[levels < price]
        return float(below[-1]) if len(below) > 0 else None

    @classmethod
    def nearest_resistance(cls, price: float, df: pd.DataFrame, window: int, lookback: int):
        """返回价格上方最近的压力位，找不到返回 None"""
        past = df.tail(lookback)
        if len(past) < window * 2 + 1:
            return None
        highs, _ = cls.swing_levels(past, window)
        levels   = cls.cluster(highs)
        above    = levels[levels > price]
        return float(above[0]) if len(above) > 0 else None


# ════════════════════════════════════════════════════════════════
#  ① 日线趋势判断（用户策略）
#  多头: 收盘 > MA5 AND 收盘 > 开盘 AND 收盘 > MA20
#  空头: 收盘 < MA5 AND 收盘 < 开盘 AND 收盘 < MA20
# ════════════════════════════════════════════════════════════════
class TrendAnalyzer:

    @staticmethod
    def daily_trend(df_1d: pd.DataFrame, idx: int) -> Optional[str]:
        slow = CONFIG["daily_ma_slow"]
        if idx < slow: return None
        close = df_1d["close"].iloc[idx]
        open_ = df_1d["open"].iloc[idx]
        ma5   = Indicators.sma(df_1d["close"], CONFIG["daily_ma_fast"]).iloc[idx]
        ma20  = Indicators.sma(df_1d["close"], CONFIG["daily_ma_slow"]).iloc[idx]
        if pd.isna(ma5) or pd.isna(ma20): return None

        if close > ma5 and close > open_ and close > ma20:
            return "bull"
        if close < ma5 and close < open_ and close < ma20:
            return "bear"
        return None  # 中性，不交易


# ════════════════════════════════════════════════════════════════
#  ② 4H确认（用户策略）
#  多头: 当前价格在4H支撑上方，返回 (True, sup_4h, res_4h)
# ════════════════════════════════════════════════════════════════
def h4_confirm(price: float, df_4h: pd.DataFrame, trend: str):
    """
    返回 (confirmed: bool, support_4h: float|None, resistance_4h: float|None)
    多头: 价格需在4H支撑上方，并取得4H压力位作止盈目标
    空头: 价格需在4H压力下方，并取得4H支撑位作止盈目标
    """
    w   = CONFIG["sr_swing_window"]
    lb  = CONFIG["sr_lookback_4h"]
    sup = SupportResistance.nearest_support(price, df_4h, w, lb)
    res = SupportResistance.nearest_resistance(price, df_4h, w, lb)

    if trend == "bull":
        confirmed = (sup is not None)          # 价格在4H支撑上方 → 多头确认
        return confirmed, sup, res
    else:  # bear
        confirmed = (res is not None)          # 价格在4H压力下方 → 空头确认
        return confirmed, sup, res


# ════════════════════════════════════════════════════════════════
#  ③ 1H入场信号（用户策略）
#  多头: 价格在1H支撑上方 且 距离 < 2%
#  空头: 价格在1H压力下方 且 距离 < 2%
# ════════════════════════════════════════════════════════════════
def h1_entry_signal(price: float, df_1h: pd.DataFrame, trend: str):
    """
    返回 (signal: bool, sl_level: float|None)
    sl_level = 1H 支撑/压力位（止损用）
    """
    w   = CONFIG["sr_swing_window"]
    lb  = CONFIG["sr_lookback_1h"]
    max_dist = CONFIG["max_entry_dist"]

    if trend == "bull":
        sup = SupportResistance.nearest_support(price, df_1h, w, lb)
        if sup is None: return False, None
        dist = (price - sup) / sup
        if dist < max_dist:
            return True, sup
        return False, sup

    else:  # bear
        res = SupportResistance.nearest_resistance(price, df_1h, w, lb)
        if res is None: return False, None
        dist = (res - price) / res
        if dist < max_dist:
            return True, res
        return False, res


# ════════════════════════════════════════════════════════════════
#  [A] 动态仓位
# ════════════════════════════════════════════════════════════════
def calc_position_size(capital: float, peak_capital: float) -> float:
    if peak_capital <= 0:
        return capital * CONFIG["leverage"]
    dd = (peak_capital - capital) / peak_capital
    if dd >= CONFIG["dd_quarter_pos"]:   mult = 0.25
    elif dd >= CONFIG["dd_half_pos"]:    mult = 0.50
    else:                                mult = 1.00
    return capital * CONFIG["leverage"] * mult


# ════════════════════════════════════════════════════════════════
#  [D] 移动止损更新
# ════════════════════════════════════════════════════════════════
def update_trailing_stop(trade: Trade, cur_high: float, cur_low: float) -> Trade:
    sl_dist = trade.sl_distance
    if sl_dist <= 0: return trade

    if trade.direction == "long":
        float_r = (cur_high - trade.entry_price) / sl_dist
        if not trade.lock_triggered and float_r >= CONFIG["trail_lock_trigger"]:
            new_sl = trade.entry_price + sl_dist * CONFIG["trail_lock_ratio"]
            if new_sl > trade.stop_loss:
                trade.stop_loss = new_sl; trade.lock_triggered = True
        elif not trade.be_triggered and float_r >= CONFIG["trail_be_trigger"]:
            new_sl = trade.entry_price + sl_dist * 0.05
            if new_sl > trade.stop_loss:
                trade.stop_loss = new_sl; trade.be_triggered = True
    else:
        float_r = (trade.entry_price - cur_low) / sl_dist
        if not trade.lock_triggered and float_r >= CONFIG["trail_lock_trigger"]:
            new_sl = trade.entry_price - sl_dist * CONFIG["trail_lock_ratio"]
            if new_sl < trade.stop_loss:
                trade.stop_loss = new_sl; trade.lock_triggered = True
        elif not trade.be_triggered and float_r >= CONFIG["trail_be_trigger"]:
            new_sl = trade.entry_price - sl_dist * 0.05
            if new_sl < trade.stop_loss:
                trade.stop_loss = new_sl; trade.be_triggered = True
    return trade


# ════════════════════════════════════════════════════════════════
#  回测引擎
# ════════════════════════════════════════════════════════════════
class BacktestEngine:

    def __init__(self):
        self.fetcher = DataFetcher()

    def run(self, symbol: str) -> BacktestResult:
        result       = BacktestResult(symbol=symbol)
        capital      = float(CONFIG["initial_capital"])
        peak_capital = capital

        start       = datetime.strptime(CONFIG["start_date"], "%Y-%m-%d")
        end         = datetime.strptime(CONFIG["end_date"],   "%Y-%m-%d")
        fetch_start = start - timedelta(days=120)   # 预热数据

        print(f"\n{'═'*62}")
        print(f"  交易对: {symbol}  (v4 用户策略版)")
        print(f"  策略: 日线MA5/MA20 + 4H支撑确认 + 1H入场(<2%)")
        print(f"{'═'*62}")

        # ── 只需3个周期数据 ───────────────────────────────────────
        df_1d = self.fetcher.fetch_ohlcv(symbol, "1d", fetch_start, end)
        df_4h = self.fetcher.fetch_ohlcv(symbol, "4h", fetch_start, end)
        df_1h = self.fetcher.fetch_ohlcv(symbol, "1h", fetch_start, end)

        if any(df.empty for df in [df_1d, df_4h, df_1h]):
            print("  ⚠ 数据不足，跳过"); return result

        # 预计算日线 MA5 / MA20（速度优化）
        df_1d["ma5"]  = Indicators.sma(df_1d["close"], CONFIG["daily_ma_fast"])
        df_1d["ma20"] = Indicators.sma(df_1d["close"], CONFIG["daily_ma_slow"])

        # 预计算1H ADX（[C]过滤）
        adx_1h = Indicators.adx(df_1h, CONFIG["adx_period"])

        result.equity_curve.append(capital)
        current_trade: Optional[Trade] = None

        current_day   = None
        day_start_cap = capital
        day_stopped   = False
        day_paused    = False

        consec_losses = 0
        pause_until: Optional[datetime] = None

        filter_stats = {
            "no_daily_trend":  0,
            "h4_not_confirm":  0,
            "h1_dist_too_far": 0,
            "rr_too_low":      0,
            "adx_filter":      0,
            "daily_stopped":   0,
            "consec_paused":   0,
            "signals_taken":   0,
        }

        df_trade = df_1h[df_1h.index >= pd.Timestamp(start)]
        total    = len(df_trade)

        for step_i, (ts, row) in enumerate(df_trade.iterrows()):

            if step_i % 1000 == 0:
                pct = step_i / total * 100
                dd  = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
                print(f"  进度: {pct:5.1f}%  资金: {capital:,.2f} U  "
                      f"交易: {result.total_trades}笔  回撤: {dd:.1%}", end="\r")

            price   = float(row["close"])
            day_str = ts.strftime("%Y-%m-%d")

            # 峰值更新 [A]
            if capital > peak_capital:
                peak_capital = capital

            # 每日重置
            if day_str != current_day:
                if current_day is not None:
                    result.daily_stats[current_day] = {
                        "pnl":     capital - day_start_cap,
                        "stopped": day_stopped,
                        "paused":  day_paused,
                    }
                current_day   = day_str
                day_start_cap = capital
                day_stopped   = False
                day_paused    = False

            # ── [D] 移动止损更新 ─────────────────────────────────
            if current_trade and current_trade.is_open:
                current_trade = update_trailing_stop(
                    current_trade, float(row["high"]), float(row["low"])
                )

            # ── 止损/止盈检查 ────────────────────────────────────
            if current_trade and current_trade.is_open:
                exit_price = None; reason = ""
                if current_trade.direction == "long":
                    if float(row["low"])  <= current_trade.stop_loss:
                        exit_price = current_trade.stop_loss; reason = "sl"
                    elif float(row["high"]) >= current_trade.take_profit:
                        exit_price = current_trade.take_profit; reason = "tp"
                else:
                    if float(row["high"]) >= current_trade.stop_loss:
                        exit_price = current_trade.stop_loss; reason = "sl"
                    elif float(row["low"])  <= current_trade.take_profit:
                        exit_price = current_trade.take_profit; reason = "tp"

                if exit_price is not None:
                    current_trade = self._close_trade(current_trade, ts, exit_price, reason)
                    capital += current_trade.pnl_usdt
                    result.trades.append(current_trade)
                    result.equity_curve.append(capital)

                    # [B] 连续亏损计数
                    if reason == "sl":
                        consec_losses += 1
                        if consec_losses >= CONFIG["consec_loss_max"]:
                            pause_until   = ts + timedelta(days=CONFIG["consec_loss_pause_days"])
                            consec_losses = 0
                    else:
                        consec_losses = 0

                    # [E] 日风控
                    if (capital - day_start_cap) / day_start_cap <= -CONFIG["daily_loss_limit_pct"]:
                        day_stopped = True

                    current_trade = None

            # 持仓中不开新仓
            if current_trade:
                continue

            # ── [B] 连续亏损暂停 ─────────────────────────────────
            if pause_until and ts < pause_until:
                filter_stats["consec_paused"] += 1
                day_paused = True
                continue

            # ── [E] 日风控 ───────────────────────────────────────
            if day_stopped:
                filter_stats["daily_stopped"] += 1
                continue

            # ── 获取当前时刻对应的日线、4H索引 ─────────────────────
            d_idx  = int(df_1d.index.searchsorted(ts, side="right")) - 1
            h4_idx = int(df_4h.index.searchsorted(ts, side="right")) - 1
            h1_idx = int(df_1h.index.searchsorted(ts, side="right")) - 1

            if d_idx < CONFIG["daily_ma_slow"] or h4_idx < 20 or h1_idx < 20:
                continue

            # ── ① 日线趋势判断 ───────────────────────────────────
            trend = TrendAnalyzer.daily_trend(df_1d, d_idx)
            if trend is None:
                filter_stats["no_daily_trend"] += 1; continue

            # ── [C] ADX过滤（1H级别）───────────────────────────
            adx_val = adx_1h.iloc[h1_idx]
            if not pd.isna(adx_val) and adx_val < CONFIG["adx_min"]:
                filter_stats["adx_filter"] += 1; continue

            # ── ② 4H确认 ────────────────────────────────────────
            df_4h_past = df_4h[df_4h.index <= ts]
            confirmed, sup_4h, res_4h = h4_confirm(price, df_4h_past, trend)
            if not confirmed:
                filter_stats["h4_not_confirm"] += 1; continue

            # 止盈目标来自4H压力/支撑
            if trend == "bull" and res_4h is None:
                filter_stats["h4_not_confirm"] += 1; continue
            if trend == "bear" and sup_4h is None:
                filter_stats["h4_not_confirm"] += 1; continue

            # ── ③ 1H入场信号 ─────────────────────────────────────
            df_1h_past = df_1h[df_1h.index <= ts]
            signal, sl_level = h1_entry_signal(price, df_1h_past, trend)
            if not signal:
                filter_stats["h1_dist_too_far"] += 1; continue

            # ── 构建止损/止盈 ────────────────────────────────────
            if trend == "bull":
                sl      = sl_level * (1 - CONFIG["sl_buffer_pct"])   # 1H支撑下方
                tp      = res_4h                                       # 4H压力
                sl_dist = price - sl
                tp_dist = tp - price
            else:
                sl      = sl_level * (1 + CONFIG["sl_buffer_pct"])   # 1H压力上方
                tp      = sup_4h                                       # 4H支撑
                sl_dist = sl - price
                tp_dist = price - tp

            if sl_dist <= 0 or tp_dist <= 0:
                continue

            rr = tp_dist / sl_dist
            if rr < CONFIG["min_rr"]:
                filter_stats["rr_too_low"] += 1; continue

            # ── 开仓 [A] 动态仓位 ────────────────────────────────
            pos_size = calc_position_size(capital, peak_capital)
            current_trade = Trade(
                symbol        = symbol,
                direction     = trend == "bull" and "long" or "short",
                entry_time    = ts,
                entry_price   = price,
                stop_loss     = sl,
                take_profit   = tp,
                position_size = pos_size,
                rr_ratio      = rr,
                sl_distance   = sl_dist,
            )
            filter_stats["signals_taken"] += 1

        # 强制平仓（回测结束）
        if current_trade and current_trade.is_open:
            lp = float(df_1h["close"].iloc[-1])
            current_trade = self._close_trade(current_trade, df_1h.index[-1], lp, "end")
            capital += current_trade.pnl_usdt
            result.trades.append(current_trade)
            result.equity_curve.append(capital)

        dd_final = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
        print(f"  进度: 100.0%  资金: {capital:,.2f} U  "
              f"交易: {result.total_trades}笔  回撤: {dd_final:.1%}  ✓                ")

        print(f"\n  📋 信号过滤统计:")
        print(f"     日线趋势不满足  : {filter_stats['no_daily_trend']:>6,}")
        print(f"     4H未确认方向    : {filter_stats['h4_not_confirm']:>6,}")
        print(f"     1H距支撑过远    : {filter_stats['h1_dist_too_far']:>6,}")
        print(f"     盈亏比不足      : {filter_stats['rr_too_low']:>6,}")
        print(f"  ✦  ADX震荡过滤    : {filter_stats['adx_filter']:>6,}")
        print(f"     日风控停止      : {filter_stats['daily_stopped']:>6,}")
        print(f"  ✦  连续亏损暂停   : {filter_stats['consec_paused']:>6,}")
        print(f"     ✅ 最终入场信号 : {filter_stats['signals_taken']:>6,}")

        return result

    @staticmethod
    def _close_trade(trade: Trade, exit_time, exit_price: float, reason: str) -> Trade:
        trade.exit_time  = exit_time
        trade.exit_price = exit_price
        trade.exit_reason = reason
        if trade.direction == "long":
            raw_pct = (exit_price - trade.entry_price) / trade.entry_price
        else:
            raw_pct = (trade.entry_price - exit_price) / trade.entry_price
        fee = trade.position_size * CONFIG["taker_fee"] * 2
        pnl = trade.position_size * raw_pct - fee
        trade.pnl_usdt = pnl
        trade.pnl_pct  = pnl / (trade.position_size / CONFIG["leverage"])
        return trade


# ════════════════════════════════════════════════════════════════
#  报告 & 可视化
# ════════════════════════════════════════════════════════════════
class Reporter:
    C = {
        "bg":"#0d1117","panel":"#161b22","green":"#26a641","red":"#da3633",
        "blue":"#58a6ff","gold":"#e3b341","purple":"#bc8cff",
        "gray":"#30363d","text":"#e6edf3","muted":"#8b949e",
    }

    @classmethod
    def print_summary(cls, results):
        init = CONFIG["initial_capital"]
        print(f"\n\n{'═'*68}")
        print("  📊  ETH 日内多周期策略  v4.0  回测汇总")
        print(f"  区间: {CONFIG['start_date']} ~ {CONFIG['end_date']}"
              f"   资金: {init:,} USDT   杠杆: {CONFIG['leverage']}x")
        print(f"  策略: 日线MA5/MA20/开盘 → 4H支撑确认 → 1H入场(<2%)")
        print(f"{'═'*68}")
        for r in results:
            if not r.trades:
                print(f"  {r.symbol}  ─ 无交易信号（可尝试加长回测周期或调整参数）─")
                continue
            final = r.equity_curve[-1] if r.equity_curve else init
            roi   = (final - init) / init
            sign  = "📈" if roi >= 0 else "📉"
            print(f"\n  {sign} {r.symbol}")
            print(f"     总交易   : {r.total_trades:>4d} 笔  "
                  f"做多 {len(r.long_trades)} / 做空 {len(r.short_trades)}")
            print(f"     胜  率   : {r.win_rate:.1%}   "
                  f"盈亏比: {r.profit_factor:.2f}   "
                  f"平均RR: {r.avg_rr:.2f}")
            print(f"     总盈亏   : {r.total_pnl:>+,.2f} U  "
                  f"ROI: {roi:>+.2%}   终值: {final:>,.2f} U")
            print(f"     最大回撤 : {r.max_drawdown:.1%}   "
                  f"Sharpe: {r.sharpe_ratio:.2f}   "
                  f"日风控: {r.daily_stop_count}天")
            print(f"     平均盈   : {r.avg_win:>+,.2f} U   "
                  f"平均亏: {r.avg_loss:>+,.2f} U")
            print(f"     保本止损 : {r.be_count}次   "
                  f"锁利止损: {r.lock_count}次   "
                  f"连亏暂停: {r.consec_pause_count}天")

    @classmethod
    def plot(cls, results, save_path="backtest_v4.png"):
        valid = [r for r in results if r.trades]
        if not valid: print("  ⚠ 无数据，跳过绘图"); return
        C   = cls.C
        n   = len(valid)
        fig = plt.figure(figsize=(22, 7 * n + 2))
        fig.patch.set_facecolor(C["bg"])

        for ri, r in enumerate(valid):
            init = CONFIG["initial_capital"]

            # 权益曲线
            ax1 = fig.add_subplot(n, 3, ri*3+1)
            ax1.set_facecolor(C["panel"])
            eq  = r.equity_curve; x = list(range(len(eq)))
            ax1.plot(x, eq, color=C["blue"], linewidth=1.5, zorder=3)
            ax1.axhline(init, color=C["muted"], linestyle="--", linewidth=0.8, alpha=0.6)
            ax1.fill_between(x, init, eq, where=[v >= init for v in eq],
                             color=C["green"], alpha=0.2)
            ax1.fill_between(x, init, eq, where=[v < init  for v in eq],
                             color=C["red"],   alpha=0.2)
            # 标记最大回撤区间
            peak = eq[0]; peak_i = 0; max_dd = 0; trough_i = 0
            for i, v in enumerate(eq):
                if v > peak: peak = v; peak_i = i
                dd = (peak - v) / peak if peak > 0 else 0
                if dd > max_dd: max_dd = dd; trough_i = i
            ax1.axvspan(peak_i, trough_i, color=C["red"], alpha=0.08)

            final = eq[-1] if eq else init
            roi   = (final - init) / init
            ax1.set_title(
                f"{r.symbol}  权益曲线\nROI {roi:+.2%}  MDD {r.max_drawdown:.1%}"
                f"  Sharpe {r.sharpe_ratio:.2f}",
                color=C["text"], fontsize=10, fontweight="bold")
            ax1.set_ylabel("资金 (USDT)", color=C["muted"], fontsize=9)
            cls._style(ax1, C)

            # 逐笔盈亏 + 累积盈亏叠加
            ax2 = fig.add_subplot(n, 3, ri*3+2)
            ax2.set_facecolor(C["panel"])
            pnls  = [t.pnl_usdt for t in r.trades]
            bar_c = [C["green"] if p > 0 else C["red"] for p in pnls]
            ax2.bar(range(len(pnls)), pnls, color=bar_c, alpha=0.85, width=0.8)
            ax2.axhline(0, color=C["muted"], linewidth=0.8)
            cum = np.cumsum(pnls)
            ax2b = ax2.twinx()
            ax2b.plot(cum, color=C["gold"], linewidth=1.2, linestyle="--", alpha=0.8)
            ax2b.tick_params(colors=C["muted"])
            for s in ax2b.spines.values(): s.set_edgecolor(C["gray"])
            ax2.set_title(
                f"逐笔盈亏\n胜率 {r.win_rate:.1%}  盈亏比 {r.profit_factor:.2f}"
                f"  保本止损 {r.be_count}次",
                color=C["text"], fontsize=10, fontweight="bold")
            ax2.set_ylabel("单笔盈亏 (USDT)", color=C["muted"], fontsize=9)
            cls._style(ax2, C)

            # 月度盈亏
            ax3 = fig.add_subplot(n, 3, ri*3+3)
            ax3.set_facecolor(C["panel"])
            monthly = {}
            for t in r.trades:
                ym = t.entry_time.strftime("%Y-%m")
                monthly[ym] = monthly.get(ym, 0) + t.pnl_usdt
            months = sorted(monthly); vals = [monthly[m] for m in months]
            mc = [C["green"] if v >= 0 else C["red"] for v in vals]
            ax3.bar(range(len(months)), vals, color=mc, alpha=0.85)
            ax3.axhline(0, color=C["muted"], linewidth=0.8)
            ax3.set_xticks(range(len(months)))
            ax3.set_xticklabels([m[5:] for m in months], rotation=45,
                                color=C["muted"], fontsize=8)
            win_m = sum(1 for v in vals if v > 0)
            ax3.set_title(
                f"月度盈亏\n盈利月 {win_m}/{len(months)}"
                f"  日风控 {r.daily_stop_count}天  连亏暂停 {r.consec_pause_count}天",
                color=C["text"], fontsize=10, fontweight="bold")
            ax3.set_ylabel("月盈亏 (USDT)", color=C["muted"], fontsize=9)
            cls._style(ax3, C)

        fig.suptitle(
            f"ETH 日内多周期合约策略 v4  |  {CONFIG['start_date']} ~ {CONFIG['end_date']}"
            f"  |  日线MA5/MA20 + 4H支撑 + 1H<2%入场",
            color=C["text"], fontsize=11, fontweight="bold", y=0.99)
        plt.tight_layout(pad=2.5)
        plt.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
        plt.close()
        print(f"\n  📈 图表 → {save_path}")

    @staticmethod
    def _style(ax, C):
        ax.tick_params(colors=C["muted"])
        for s in ax.spines.values(): s.set_edgecolor(C["gray"])
        ax.grid(color=C["gray"], linewidth=0.4, alpha=0.5)

    @staticmethod
    def export_csv(results, save_path="trades_v4.csv"):
        rows = []
        for r in results:
            for t in r.trades:
                rows.append({
                    "交易对":   t.symbol,
                    "方向":     "做多" if t.direction == "long" else "做空",
                    "入场时间": t.entry_time,
                    "入场价格": round(t.entry_price, 4),
                    "止损":     round(t.stop_loss, 4),
                    "止盈":     round(t.take_profit, 4),
                    "盈亏比":   round(t.rr_ratio, 2),
                    "出场时间": t.exit_time,
                    "出场价格": round(t.exit_price, 4) if t.exit_price else "",
                    "出场原因": {"tp":"止盈","sl":"止损","end":"回测结束"}.get(t.exit_reason, t.exit_reason),
                    "保本止损": "是" if t.be_triggered else "否",
                    "锁利止损": "是" if t.lock_triggered else "否",
                    "盈亏(USDT)": round(t.pnl_usdt, 4),
                    "盈亏(%)":  f"{t.pnl_pct:.4%}",
                })
        if not rows: print("  ⚠ 无记录"); return
        pd.DataFrame(rows).to_csv(save_path, index=False, encoding="utf-8-sig")
        print(f"  📋 交易记录 → {save_path}")


# ════════════════════════════════════════════════════════════════
#  主程序
# ════════════════════════════════════════════════════════════════
def main():
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   ETH 日内多周期合约回测  v4.0  (用户策略精准版)               ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  策略: 日线MA{CONFIG['daily_ma_fast']}/MA{CONFIG['daily_ma_slow']}/开盘 → 4H支撑确认 → 1H<{CONFIG['max_entry_dist']:.0%}入场      ║")
    print(f"║  [A] 动态仓位    回撤>10%→半仓  回撤>20%→四分之一仓           ║")
    print(f"║  [B] 连续亏损    连续{CONFIG['consec_loss_max']}笔止损→暂停{CONFIG['consec_loss_pause_days']}天                          ║")
    print(f"║  [C] ADX过滤     ADX<{CONFIG['adx_min']} 震荡市不开仓                        ║")
    print(f"║  [D] 移动止损    1R保本 / 2R锁定0.5R                           ║")
    print(f"║  [E] 日风控      亏损>{CONFIG['daily_loss_limit_pct']:.0%} 停止当日交易                      ║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    engine   = BacktestEngine()
    reporter = Reporter()
    results  = []

    for symbol in CONFIG["symbols"]:
        try:
            results.append(engine.run(symbol))
        except Exception as e:
            import traceback
            print(f"\n  ⚠ {symbol} 出错: {e}"); traceback.print_exc()

    reporter.print_summary(results)
    reporter.plot(results, "backtest_v4.png")
    reporter.export_csv(results, "trades_v4.csv")

    print("\n✅  v4 回测完成！")
    print("  backtest_v4.png  ← 权益曲线 / 逐笔盈亏 / 月度盈亏")
    print("  trades_v4.csv    ← 完整交易明细（可用 Excel 打开）\n")


if __name__ == "__main__":
    main()
