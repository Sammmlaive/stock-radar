"""
買進訊號偵測模組
偵測 4 種明確的買進訊號，供「今日推薦」頁面使用

訊號說明（交易邏輯比喻）：
  均線黃金交叉 = 短期持倉成本剛穿越中期，趨勢翻多的第一天
  法人爆量買進 = 大資金今日異常大量湧入，籌碼快速集中
  RSI低谷反轉 = 股票從超賣區回升，賣壓結束、買盤接手
  MACD翻紅    = 動能從空方轉為多方的轉折點
"""
import numpy as np


def _safe(row, key, default=None):
    """安全取值，處理 None 和 NaN"""
    v = row.get(key, default) if isinstance(row, dict) else getattr(row, key, default)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return default
    return v


def detect_buy_signals(latest, prev, inst_today: dict) -> list:
    """
    偵測 4 種買進訊號

    參數：
      latest     ── 最新一日的技術指標 Series
      prev       ── 前一日的技術指標 Series
      inst_today ── 今日法人數據 dict

    回傳：觸發的訊號名稱清單，例如 ['均線黃金交叉', '法人爆量買進']
    """
    signals = []

    def lv(k, d=None): return _safe(latest, k, d)
    def pv(k, d=None): return _safe(prev, k, d)

    # ── 1. 均線黃金交叉：MA5 今日穿越 MA20 向上 ──────────────────
    # 條件：今日 MA5 > MA20，且昨日 MA5 <= MA20（剛發生穿越）
    ma5_now  = lv('ma5')
    ma20_now = lv('ma20')
    ma5_pre  = pv('ma5')
    ma20_pre = pv('ma20')
    if all(v is not None for v in [ma5_now, ma20_now, ma5_pre, ma20_pre]):
        if ma5_now > ma20_now and ma5_pre <= ma20_pre:
            signals.append('均線黃金交叉')

    # ── 2. 法人爆量買進：三大法人合計買超 > 3,000 張 且 量比 > 1.5 ──
    # 條件：大資金買進 + 市場成交量也同步放大（有效買盤）
    total_net = inst_today.get('total_net', 0) or 0
    vol_ratio = lv('vol_ratio', 0)
    if total_net > 3000 and vol_ratio > 1.5:
        signals.append('法人爆量買進')

    # ── 3. RSI 低谷反轉：前日 RSI < 30，今日回升 > 35 ──────────────
    # 條件：從超賣區（< 30）成功反彈到 35 以上，確認買盤介入
    rsi_now = lv('rsi')
    rsi_pre = pv('rsi')
    if rsi_now is not None and rsi_pre is not None:
        if rsi_pre < 30 and rsi_now > 35:
            signals.append('RSI低谷反轉')

    # ── 4. MACD 翻紅：柱狀體由負轉正 ──────────────────────────────
    # 條件：前日 MACD 柱 < 0，今日 MACD 柱 > 0（動能從空翻多）
    macd_now = lv('macd_hist')
    macd_pre = pv('macd_hist')
    if macd_now is not None and macd_pre is not None:
        if macd_pre < 0 and macd_now > 0:
            signals.append('MACD翻紅')

    return signals
