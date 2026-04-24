"""
評分與分類模組
分數組成（滿分 100）：
  技術面 40分：均線位置、RSI 強弱
  量能   20分：今日量 vs 均量
  籌碼   40分：三大法人買賣超
"""
import pandas as pd
import numpy as np
from signals import detect_buy_signals


def score_stock(row: pd.Series, prev: pd.Series = None):
    """
    計算單支股票評分
    row  ── 最新一日含指標的 Series（已含法人欄位）
    prev ── 前一日（用來判斷轉強 / 轉弱）
    回傳：(score, category, signals)
    """
    score   = 0
    signals = []

    def val(key, default=None):
        v = row.get(key, default)
        return None if (v is None or (isinstance(v, float) and np.isnan(v))) else v

    close  = val('close', 0)
    ma20   = val('ma20')
    ma60   = val('ma60')
    rsi    = val('rsi', 50)
    macd_h = val('macd_hist', 0)
    vol_r  = val('vol_ratio', 1)

    # ══ 技術面（最高 40 分）════════════════════

    above_ma20 = ma20 and close > ma20
    if above_ma20:
        score += 15
        signals.append("站上MA20")

    if ma20 and ma60 and ma20 > ma60:
        score += 10
        signals.append("多頭排列")

    if rsi is not None:
        if rsi >= 65:
            score += 15
        elif rsi >= 55:
            score += 8
        elif rsi >= 45:
            score += 3
        elif rsi < 35:
            score -= 5

    if macd_h and macd_h > 0:
        score += 5

    # ══ 量能（最高 20 分）══════════════════════

    if vol_r is not None:
        if vol_r >= 2.0:
            score += 20
        elif vol_r >= 1.5:
            score += 12
        elif vol_r >= 1.2:
            score += 6
        elif vol_r < 0.5:
            score -= 5

    # ══ 法人籌碼（最高 40 分）══════════════════

    total_net = val('total_net', 0) or 0
    foreign   = val('foreign_net', 0) or 0
    trust     = val('trust_net', 0) or 0

    if total_net > 10000:
        score += 40
    elif total_net > 3000:
        score += 28
    elif total_net > 500:
        score += 16
    elif total_net > 0:
        score += 6
    elif total_net < -10000:
        score -= 20
    elif total_net < -3000:
        score -= 12
    elif total_net < -500:
        score -= 5

    if trust > 500:
        score += 5

    score = max(0, min(100, score))

    # ══ 分類邏輯 ════════════════════════════════

    turning_strong = False
    turning_weak   = False
    if prev is not None:
        prev_close = prev.get('close', 0) or 0
        prev_ma20  = prev.get('ma20')
        prev_ma20  = None if (prev_ma20 is None or np.isnan(prev_ma20)) else prev_ma20
        if prev_ma20:
            if prev_close < prev_ma20 and ma20 and close >= ma20:
                turning_strong = True
            if prev_close > prev_ma20 and ma20 and close < ma20:
                turning_weak = True

    if turning_strong and score >= 45:
        category = "轉強"
        signals.append("剛站上MA20")
    elif turning_weak and score <= 55:
        category = "轉弱"
        signals.append("剛跌破MA20")
    elif score >= 60:
        category = "強勢"
    elif score <= 28:
        category = "弱勢"
    else:
        category = "中性"

    return score, category, signals


def calculate_all_scores(price_df: pd.DataFrame, inst_multi_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    對所有股票計算評分
    price_df      ── 含技術指標的全市場 DataFrame（所有日期）
    inst_multi_df ── 最近 5 個交易日的三大法人 DataFrame
    """

    # ── 建立法人查找表（以代號為 key）────────────────
    inst_today       = {}   # 當日法人  {code: {foreign_net, trust_net, ...}}
    inst_3d          = {}   # 三日累計  {code: {foreign_3d, trust_3d, total_3d}}
    inst_5d          = {}   # 五日累計  {code: {foreign_5d, trust_5d, total_5d}}
    inst_consecutive = {}   # 法人連續買進天數 {code: int}

    if inst_multi_df is not None and not inst_multi_df.empty:
        dates = sorted(inst_multi_df['date'].unique())

        # 最新一日
        latest_date = dates[-1]
        for _, r in inst_multi_df[inst_multi_df['date'] == latest_date].iterrows():
            inst_today[r['code']] = {
                'foreign_net': r.get('foreign_net', 0) or 0,
                'trust_net':   r.get('trust_net',   0) or 0,
                'dealer_net':  r.get('dealer_net',  0) or 0,
                'total_net':   r.get('total_net',   0) or 0,
            }

        # 三日累計（最近 3 個交易日）
        dates_3d = dates[-3:]
        grp3 = inst_multi_df[inst_multi_df['date'].isin(dates_3d)].groupby('code')
        for code, g in grp3:
            inst_3d[code] = {
                'foreign_3d': round(g['foreign_net'].sum(), 0),
                'trust_3d':   round(g['trust_net'].sum(),   0),
                'total_3d':   round(g['total_net'].sum(),   0),
            }

        # 五日累計（全部，最多 5 日）
        dates_5d = dates[-5:]
        grp5 = inst_multi_df[inst_multi_df['date'].isin(dates_5d)].groupby('code')
        for code, g in grp5:
            inst_5d[code] = {
                'foreign_5d': round(g['foreign_net'].sum(), 0),
                'trust_5d':   round(g['trust_net'].sum(),   0),
                'total_5d':   round(g['total_net'].sum(),   0),
            }

        # 法人連續買進天數（從最新日往回數，total_net > 0 才算）
        for code, group in inst_multi_df.groupby('code'):
            sorted_g = group.sort_values('date', ascending=False)
            count = 0
            for _, row in sorted_g.iterrows():
                if (row.get('total_net', 0) or 0) > 0:
                    count += 1
                else:
                    break
            inst_consecutive[code] = count

    # ── 逐支股票評分 ─────────────────────────────────
    results = []
    for code, group in price_df.groupby('code'):
        group = group.sort_values('date').reset_index(drop=True)
        if len(group) < 2:
            continue

        latest = group.iloc[-1]
        prev   = group.iloc[-2]

        # 把法人數據注入 latest（以代號查找，不再用日期對比）
        today_inst = inst_today.get(code, {})
        latest_with_inst = latest.to_dict()
        latest_with_inst.update(today_inst)
        latest_series = pd.Series(latest_with_inst)

        def g(k):
            v = latest.get(k)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return None
            return v

        score, category, signals = score_stock(latest_series, prev)

        # 偵測 4 種明確買進訊號
        buy_signal_list = detect_buy_signals(latest_series, prev, today_inst)

        # 訊號強弱：多訊號同時出現，或單訊號配合放量，才算強
        vol_r_val = g('vol_ratio') or 1
        if len(buy_signal_list) >= 2 or (len(buy_signal_list) == 1 and vol_r_val >= 1.5):
            signal_strength = '強'
        elif len(buy_signal_list) == 1:
            signal_strength = '普通'
        else:
            signal_strength = ''

        # 直接由前後兩日收盤算漲跌幅（比 pct_change 更可靠）
        close_now  = g('close') or 0
        close_prev = prev.get('close', 0) or 0
        if close_prev > 0:
            change_pct = round((close_now - close_prev) / close_prev * 100, 2)
        else:
            change_pct = 0.0

        three_d = inst_3d.get(code, {})
        five_d  = inst_5d.get(code, {})

        results.append({
            'date':        g('date'),
            'code':        code,
            'name':        g('name') or code,
            'close':       g('close'),
            'change_pct':  change_pct,
            'volume':      g('volume'),
            'vol_ratio':   round(g('vol_ratio') or 0, 2),
            'ma20':        round(g('ma20') or 0, 2),
            'ma60':        round(g('ma60') or 0, 2),
            'rsi':         round(g('rsi') or 0, 1),
            'k':           round(g('k')   or 0, 1),
            'd':           round(g('d')   or 0, 1),
            'macd_hist':   g('macd_hist'),
            'foreign_net': today_inst.get('foreign_net', 0),
            'trust_net':   today_inst.get('trust_net',   0),
            'dealer_net':  today_inst.get('dealer_net',  0),
            'total_net':   today_inst.get('total_net',   0),
            'foreign_3d':  three_d.get('foreign_3d', 0),
            'trust_3d':    three_d.get('trust_3d',   0),
            'total_3d':    three_d.get('total_3d',   0),
            'foreign_5d':  five_d.get('foreign_5d',  0),
            'trust_5d':    five_d.get('trust_5d',    0),
            'total_5d':    five_d.get('total_5d',    0),
            'week52_pos':      round(g('week52_pos') or 0, 1),
            'inst_consec':     inst_consecutive.get(code, 0),
            'score':           score,
            'category':        category,
            'signals':         '、'.join(signals) if signals else '—',
            'buy_signals':     '、'.join(buy_signal_list) if buy_signal_list else '',
            'signal_strength': signal_strength,
        })

    df = pd.DataFrame(results).sort_values('score', ascending=False).reset_index(drop=True)
    return df
