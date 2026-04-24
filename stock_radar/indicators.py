"""
技術指標計算模組
輸入：個股歷史 OHLCV 資料
輸出：加上 MA、RSI、MACD、KD、布林通道、量比 等欄位

指標類比：
  MA（均線）  = 過去 N 天的「平均持倉成本」，價格在均線上 = 持有者賺錢
  RSI         = 買賣力道計量器（0~100），>70 過熱、<30 超賣
  MACD        = 動能加速計，柱狀體由負轉正 = 動能從空翻多
  KD          = 短線超買超賣指標，K 值 > D 值且低檔交叉 = 買進訊號
  量比        = 今日量 / 20日均量，>1.5 代表放量（有主力進場）
"""
import pandas as pd
import numpy as np
from ta.trend import MACD
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands
from config import MA_SHORT, MA_LONG, RSI_PERIOD, VOLUME_AVG_DAYS


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    計算單支股票的所有技術指標
    df 必須含欄位：date, open, high, low, close, volume
    """
    if len(df) < MA_SHORT:
        return df  # 資料不足，跳過

    df = df.copy().sort_values('date').reset_index(drop=True)

    close  = df['close']
    high   = df['high']
    low    = df['low']
    volume = df['volume']

    # ── 均線 ──────────────────────────────────
    df['ma5']  = close.rolling(5).mean()        # 短期均線（黃金交叉訊號用）
    df['ma20'] = close.rolling(MA_SHORT).mean()
    df['ma60'] = close.rolling(MA_LONG).mean()

    # ── RSI ───────────────────────────────────
    df['rsi'] = RSIIndicator(close, n=RSI_PERIOD).rsi()

    # ── MACD ──────────────────────────────────
    macd_obj       = MACD(close, n_slow=26, n_fast=12, n_sign=9)
    df['macd']     = macd_obj.macd()
    df['macd_sig'] = macd_obj.macd_signal()
    df['macd_hist']= macd_obj.macd_diff()   # 柱狀體，正 = 多頭動能

    # ── KD ────────────────────────────────────
    kd       = StochasticOscillator(high, low, close, n=9, d_n=3)
    df['k']  = kd.stoch()
    df['d']  = kd.stoch_signal()

    # ── 布林通道 ──────────────────────────────
    bb             = BollingerBands(close, n=20)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()

    # ── 量比 ──────────────────────────────────
    df['vol_ma20']  = volume.rolling(VOLUME_AVG_DAYS).mean()
    df['vol_ratio'] = (volume / df['vol_ma20']).round(2)

    # ── 漲跌幅（%）────────────────────────────
    df['change_pct'] = close.pct_change() * 100

    return df
