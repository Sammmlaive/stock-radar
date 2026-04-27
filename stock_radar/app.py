"""
台股全市場雷達 ─ Streamlit 網頁介面
啟動方式：python3 -m streamlit run /Users/sam/Desktop/ClaudeAgent/stock_radar/app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from database import load_scores, load_scores_history, load_ohlcv_recent, has_data
import base64


def make_sparkline_svg(prices: list, width: int = 90, height: int = 38) -> str:
    """純 SVG 走勢縮圖（上漲綠色 / 下跌紅色），無外部依賴"""
    if len(prices) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    mn, mx = min(prices), max(prices)
    if mx == mn:
        mn -= 0.01; mx += 0.01
    px, py = 4, 4
    w, h = width - px * 2, height - py * 2
    n = len(prices)

    def pt(i, p):
        x = px + i / (n - 1) * w
        y = py + (1 - (p - mn) / (mx - mn)) * h
        return f'{x:.1f},{y:.1f}'

    pts = ' '.join(pt(i, p) for i, p in enumerate(prices))
    color = '#26a69a' if prices[-1] >= prices[0] else '#ef5350'
    fill = f'{pts} {px + w:.1f},{py + h:.1f} {px:.1f},{py + h:.1f}'

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"'
        f' style="vertical-align:middle">'
        f'<rect width="{width}" height="{height}" rx="3" fill="#1a1a2e" opacity="0.8"/>'
        f'<polygon points="{fill}" fill="{color}" opacity="0.2"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}"'
        f' stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _svg_uri(svg: str) -> str:
    return f'data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}'


@st.cache_data(ttl=3600)
def load_sparklines() -> dict:
    """載入所有股票 90 天收盤價，回傳 {code: svg字串}，每小時更新一次"""
    ohlcv = load_ohlcv_recent(days=90)
    if ohlcv.empty:
        return {}
    result = {}
    for code, grp in ohlcv.groupby('code'):
        prices = grp.sort_values('date')['close'].dropna().tolist()
        if len(prices) >= 5:
            result[str(code)] = make_sparkline_svg(prices)
    return result


def with_sparks(orig: pd.DataFrame, disp: pd.DataFrame, sparks: dict) -> pd.DataFrame:
    """在格式化後的 DataFrame 最前面插入走勢縮圖欄（data URI 格式）"""
    out = disp.reset_index(drop=True).copy()
    codes = orig.reset_index(drop=True)['code'].astype(str)
    out.insert(0, '走勢', codes.map(lambda c: _svg_uri(sparks.get(c, make_sparkline_svg([])))))
    return out


@st.cache_data(ttl=3600)
def fetch_taiex():
    """抓取加權指數最新數據，每小時更新一次"""
    try:
        import yfinance as yf
        hist = yf.Ticker("^TWII").history(period="5d")
        if len(hist) >= 2:
            today = hist['Close'].iloc[-1]
            prev  = hist['Close'].iloc[-2]
            chg   = today - prev
            chg_pct = chg / prev * 100
            return round(today, 2), round(chg, 2), round(chg_pct, 2)
        elif len(hist) == 1:
            return round(hist['Close'].iloc[-1], 2), 0.0, 0.0
    except Exception:
        pass
    return None, None, None

st.set_page_config(
    page_title="台股全市場雷達",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.dataframe td { font-size: 13px !important; }
[data-testid="metric-container"] {
    background-color: #1e1e1e;
    border-radius: 8px;
    padding: 12px;
}
[data-testid="collapsedControl"] { display: none; }
section[data-testid="stSidebar"] { display: none; }
</style>
""", unsafe_allow_html=True)

# 篩選條件固定為預設值（側邊欄已移除）
show_cats = ["強勢", "中性", "弱勢"]
min_score = 0

# ──────────────────────────────────────────────────────
# 資料未就緒
# ──────────────────────────────────────────────────────
if not has_data():
    st.title("📡 台股全市場雷達")
    st.warning("⚠️  尚無資料，系統每日下午 3:35 自動更新，請稍後再試")
    st.stop()

# ──────────────────────────────────────────────────────
# 讀取數據
# ──────────────────────────────────────────────────────
df = load_scores()
if df is None or df.empty:
    st.error("讀取資料失敗，請重新更新數據")
    st.stop()

mask     = (df['category'].isin(show_cats)) & (df['score'] >= min_score)
df_view  = df[mask].copy()
sparklines = load_sparklines()

# ──────────────────────────────────────────────────────
# 標題與市場統計
# ──────────────────────────────────────────────────────
last_date = df['date'].iloc[0] if not df.empty else "—"
st.title(f"📡 台股全市場雷達  ·  {last_date}")
st.caption("📅 資料每日下午 3:35 盤後自動更新")

total = len(df)
c1, c2, c3, c4 = st.columns(4)
def pct(n): return f"{n/total*100:.1f}%" if total > 0 else "0%"
n_s = len(df[df['category'] == '強勢'])
n_n = len(df[df['category'] == '中性'])
n_w = len(df[df['category'] == '弱勢'])

# 加權指數
taiex_close, taiex_chg, taiex_chg_pct = fetch_taiex()
if taiex_close:
    chg_str = f"{taiex_chg:+.2f} ({taiex_chg_pct:+.2f}%)"
    c1.metric("📈 加權指數", f"{taiex_close:,.2f}", chg_str)
else:
    c1.metric("📈 加權指數", "—")

c2.metric("🔴 強勢", n_s, pct(n_s))
c3.metric("⚪ 中性", n_n, pct(n_n))
c4.metric("💙 弱勢", n_w, pct(n_w))
st.caption(f"共 {total} 支股票 ｜ 目前顯示 {len(df_view)} 支")
st.divider()

# ──────────────────────────────────────────────────────
# 欄位格式化（統一順序：代號名稱 → MA → 法人 → 其他指標 → 評分狀態訊號）
# ──────────────────────────────────────────────────────

_COLS = ['code', 'name', 'close', 'change_pct', 'volume',
         'ma20', 'ma60',
         'total_net',   'total_3d',   'total_5d',
         'rsi', 'k', 'd', 'vol_ratio',
         'score', 'category', 'signals']

_LABELS = ['代號', '名稱', '收盤價', '漲跌%', '成交量(張)',
           'MA20', 'MA60',
           '法人合計(今)', '法人合計(3日)', '法人合計(5日)',
           'RSI', 'K值', 'D值', '量比',
           '評分', '狀態', '訊號']

def fmt(data: pd.DataFrame) -> pd.DataFrame:
    avail = [c for c in _COLS if c in data.columns]
    d = data[avail].copy()
    d.columns = _LABELS[:len(avail)]
    num_round = {
        '收盤價': 2, '漲跌%': 2, 'MA20': 2, 'MA60': 2,
        'RSI': 1, 'K值': 1, 'D值': 1, '量比': 2, '評分': 1,
    }
    for col, dp in num_round.items():
        if col in d.columns:
            d[col] = d[col].round(dp)
    # 成交量：轉成整數（單位：張，比較好讀）
    if '成交量(張)' in d.columns:
        d['成交量(張)'] = d['成交量(張)'].fillna(0).astype(int)
    inst_cols = ['法人合計(今)', '法人合計(3日)', '法人合計(5日)']
    for col in inst_cols:
        if col in d.columns:
            d[col] = d[col].fillna(0).astype(int)
    return d

# ──────────────────────────────────────────────────────
# 回調整理形態判斷（需要30天歷史，網頁即時計算）
# ──────────────────────────────────────────────────────

def classify_pullback(hist: pd.DataFrame) -> bool:
    """
    判斷是否符合「強勢多頭回調至 MA20」形態
    hist: 某支股票最近 30 天的歷史記錄（已按日期升冪排列）
    全部 6 個條件都成立才回傳 True
    """
    if len(hist) < 20:
        return False

    latest = hist.iloc[-1]

    def sv(key, default=0):
        v = latest.get(key, default)
        try:
            f = float(v)
            return default if (f != f) else f  # NaN check
        except (TypeError, ValueError):
            return default

    ma20  = sv('ma20')
    ma60  = sv('ma60')
    close = sv('close')
    rsi   = sv('rsi', 50)
    vol_r = sv('vol_ratio', 1)

    if ma20 <= 0 or ma60 <= 0 or close <= 0:
        return False

    # 1. 多頭排列：MA20 > MA60
    if ma20 <= ma60:
        return False

    # 2. 過去 N 天有足夠的多頭基礎（≥50% 天數站上 MA20）
    above = sum(
        1 for _, r in hist.iterrows()
        if (r.get('close') or 0) > (r.get('ma20') or 0) > 0
    )
    if above < len(hist) * 0.5:
        return False

    # 3. 近期有實質漲幅後回調（30天高點 > 現價 × 1.05）
    if hist['close'].max() < close * 1.05:
        return False

    # 4. 現在靠近 MA20（距離 ≤ 3%）
    if abs(close - ma20) / ma20 > 0.03:
        return False

    # 5. RSI 在健康整理區間（35~65），排除崩跌或超買
    if not (35 <= rsi <= 65):
        return False

    # 6. 非爆量殺跌（量比 ≤ 2.5）
    if vol_r > 2.5:
        return False

    return True


def classify_n_reversal(hist: pd.DataFrame):
    """
    N字反轉型態偵測（參考 XHS 結構警報器指標邏輯）

    X段定義：
      - 起點：過去 90 天內的波段高點（pivot high，左右各至少 3 根K線都更低）
      - 底部：該高點之後的最低點（X段低點）
      - 幅度：起點到底部至少下跌 5%

    觸發條件（5 項全部成立）：
      1. 找到符合條件的 X 段（有明確下跌結構）
      2. 突破時機正確：最近 7 天內收盤首次突破 X 段起點
      3. 突破前確實被壓制：突破前收盤從未超過 X 段起點
      4. 訊號仍有效：今日低點 > X 段底部（沒有跌破底部）
      5. 未過度延伸：今日收盤 < X低 + 2×X段高度

    回傳 dict（有訊號）或 None（無訊號）
    dict 包含：x_high（X段起點）、x_low（X段底部）、decline_pct（X段跌幅）、break_pct（突破後漲幅）
    """
    needed = {'high', 'low', 'close'}
    if len(hist) < 20 or not needed.issubset(hist.columns):
        return None

    hist = hist.sort_values('date').reset_index(drop=True)
    n = len(hist)
    closes = hist['close'].values
    highs  = hist['high'].values
    lows   = hist['low'].values

    latest_close = closes[-1]
    latest_low   = lows[-1]

    pivot_len = 3       # 左右各 3 根K線確認波段高點
    recent_window = 7   # 突破必須在最近 7 天內發生

    # 掃描所有可能的 X 段起點（不掃太近的K線，要留給突破區間）
    for i in range(pivot_len, n - recent_window - 1):
        # ── 判斷是否為波段高點 ──
        left_ok  = all(highs[i] > highs[i - k] for k in range(1, pivot_len + 1))
        right_ok = all(highs[i] > highs[i + k] for k in range(1, pivot_len + 1))
        if not (left_ok and right_ok):
            continue

        pivot_high = highs[i]

        # ── X 段底部：高點之後到「最近 7 天前」的最低點 ──
        search_lows = lows[i + 1 : n - recent_window]
        if len(search_lows) < 3:
            continue
        x_low = float(min(search_lows))

        # ── X 段必須有至少 5% 跌幅 ──
        x_height = pivot_high - x_low
        if x_height < pivot_high * 0.05:
            continue

        # ── 突破前（最近 7 天外）收盤從未超過 pivot_high（確認是真實阻力） ──
        pre_break_max = float(max(closes[i + 1 : n - recent_window])) if n - recent_window > i + 1 else 0
        if pre_break_max >= pivot_high:
            continue  # 之前已突破過，不算新的 N字

        # ── 最近 7 天內，至少有一天收盤突破 pivot_high ──
        recent_closes = closes[n - recent_window:]
        if not any(c > pivot_high for c in recent_closes):
            continue

        # ── 今日低點不能跌破 X 段底部（訊號仍有效） ──
        if latest_low <= x_low:
            continue

        # ── 未過度延伸（收盤 < x_low + 2×x_height） ──
        invalid_price = x_low + x_height * 2
        if latest_close >= invalid_price:
            continue

        return {
            'x_high':      round(pivot_high, 2),
            'x_low':       round(x_low, 2),
            'decline_pct': round(x_height / pivot_high * 100, 1),
            'break_pct':   round((latest_close - pivot_high) / pivot_high * 100, 1),
        }

    return None


def classify_golden_zone(hist: pd.DataFrame):
    """
    N字反轉後「黃金買入區」偵測

    邏輯：
      1. 找到 X 段（同 N字反轉：明確下跌結構，幅度 ≥ 5%）
      2. X 段結束後，股價曾突破 X 高點（N字型態已完成）
      3. 現在股價「回跌」至黃金區間：
           x_low < 收盤 ≤ 50%水位（= x_low + x_height × 0.5）
      4. 尚未跌破出局水位（= x_low - x_height × 0.5）

    範例：X高=650、X低=550（X高度100點）
      → 50%水位 = 600、出局水位 = 500
      → 黃金區 = 收盤在 500～600 之間
    """
    needed = {'high', 'low', 'close'}
    if len(hist) < 20 or not needed.issubset(hist.columns):
        return None

    hist = hist.sort_values('date').reset_index(drop=True)
    n = len(hist)
    closes = hist['close'].values
    highs  = hist['high'].values
    lows   = hist['low'].values

    latest_close = closes[-1]
    latest_low   = lows[-1]

    pivot_len = 3

    for i in range(pivot_len, n - pivot_len - 5):
        # 判斷是否為波段高點（左右各 3 根都更低）
        left_ok  = all(highs[i] > highs[i - k] for k in range(1, pivot_len + 1))
        right_ok = all(highs[i] > highs[i + k] for k in range(1, pivot_len + 1))
        if not (left_ok and right_ok):
            continue

        pivot_high = highs[i]

        # X 段底部：高點之後到近 5 根K線前的最低點
        search_lows = lows[i + 1: n - 5]
        if len(search_lows) < 3:
            continue
        x_low_rel = int(search_lows.argmin())
        x_low     = float(search_lows[x_low_rel])
        x_low_abs = i + 1 + x_low_rel

        # X 高度須 ≥ 5%
        x_height = pivot_high - x_low
        if x_height < pivot_high * 0.05:
            continue

        # X 底部前，收盤從未超過高點（確認是真實阻力）
        pre = closes[i + 1: x_low_abs + 1]
        if len(pre) > 0 and float(max(pre)) >= pivot_high:
            continue

        # X 底部後，至少有一天收盤突破高點（N字型態已完成）
        post = closes[x_low_abs + 1:]
        if not any(c > pivot_high for c in post):
            continue

        # 計算黃金區間
        fifty_pct  = x_low + x_height * 0.5   # 50%水位（黃金區上緣）
        exit_level = x_low - x_height * 0.5   # 出局水位（跌破此處認定出局）

        # 現在股價必須在黃金區內：exit_level < 收盤 ≤ 50%水位
        if latest_close > fifty_pct:
            continue   # 尚未回跌到黃金區
        if latest_close <= exit_level:
            continue   # 已跌破出局水位
        if latest_low <= exit_level:
            continue   # 今日低點觸碰出局線

        return {
            'x_high':     round(pivot_high, 2),
            'x_low':      round(x_low, 2),
            '50%水位':    round(fifty_pct, 2),
            '出局水位':   round(exit_level, 2),
            'X跌幅%':     round(x_height / pivot_high * 100, 1),
        }

    return None


# ──────────────────────────────────────────────────────
# 分頁
# ──────────────────────────────────────────────────────
tab0, tab1, tab1b, tab1c, tab2, tab3, tab4 = st.tabs(["🎯 今日推薦", "🔴 強勢股", "📉 回調整理", "🔼 N字反轉", "💙 弱勢股", "🔍 全部股票", "📊 市場分析"])

# ── Tab 0：今日推薦 ───────────────────────────────────
with tab0:
    st.markdown("### 🎯 今日推薦股票")
    st.caption("系統偵測到明確買進訊號的股票，僅供參考，買賣決策請自行判斷")

    if 'buy_signals' not in df.columns:
        df['buy_signals'] = ''

    # 訊號顏色、圖示、hover 說明
    SIGNAL_STYLE = {
        '均線黃金交叉': ('#1b5e20', '#e8f5e9', '📈',
                        'MA5（5日均線）今日向上穿越 MA20（20日均線）\n'
                        '條件：今日 MA5 > MA20，且昨日 MA5 ≤ MA20\n'
                        '意義：短期持倉成本剛穿越中期，趨勢翻多第一天'),
        '法人爆量買進': ('#7f4500', '#fff3e0', '💰',
                        '三大法人（外資+投信+自營）合計淨買超 > 3,000 張\n'
                        '且今日量比（今量/均量）> 1.5 倍\n'
                        '意義：大資金大量湧入，市場同步放量確認'),
        'RSI低谷反轉':  ('#0d47a1', '#e3f2fd', '🔄',
                        '前日 RSI < 30（超賣區）→ 今日 RSI > 35\n'
                        '意義：從超賣區成功反彈，賣壓結束、買盤正式接手'),
        'MACD翻紅':     ('#b71c1c', '#ffebee', '🔴',
                        '前日 MACD 柱狀體 < 0（空方動能）→ 今日 > 0（多方動能）\n'
                        '意義：短期動能從空翻多的轉折點'),
    }

    def signal_badges(signal_str: str) -> str:
        """把訊號字串轉成彩色 HTML 標籤（含 hover 說明）"""
        if not signal_str:
            return '—'
        badges = []
        for sig in signal_str.split('、'):
            sig = sig.strip()
            if sig in SIGNAL_STYLE:
                fg, bg, icon, tip = SIGNAL_STYLE[sig]
                tip_escaped = tip.replace('"', '&quot;')
                badges.append(
                    f'<span title="{tip_escaped}" style="background:{bg};color:{fg};border:1px solid {fg};'
                    f'padding:3px 10px;border-radius:20px;font-size:12px;'
                    f'font-weight:600;white-space:nowrap;margin:2px;display:inline-block;cursor:help">'
                    f'{icon} {sig}</span>'
                )
        return ' '.join(badges)

    def compute_risks(row) -> list:
        """分析各項指標，回傳風險警示清單 [(名稱, hover說明), ...]"""
        risks = []
        vol_ratio  = float(row.get('vol_ratio',  1) or 1)
        rsi        = float(row.get('rsi',        50) or 50)
        week52_pos = float(row.get('week52_pos',  0) or 0)
        total_net  = float(row.get('total_net',   0) or 0)
        change_pct = float(row.get('change_pct',  0) or 0)
        k_val      = float(row.get('k',           50) or 50)
        volume     = float(row.get('volume',       0) or 0)
        sigs       = row.get('buy_signals', '') or ''

        if vol_ratio < 0.8:
            risks.append(('量能嚴重不足',
                          f'量比={vol_ratio:.2f}，今日成交量僅為均量的 {vol_ratio*100:.0f}%\n'
                          '無量突破容易拉高出貨，訊號可信度極低'))
        elif vol_ratio < 1.0 and ('均線黃金交叉' in sigs or 'MACD翻紅' in sigs):
            risks.append(('量能偏弱',
                          f'量比={vol_ratio:.2f}，均線交叉 / MACD 翻紅未配合放量\n'
                          '有效突破需量比 > 1.5，建議等放量再確認'))

        if rsi > 80:
            risks.append(('RSI嚴重超買',
                          f'RSI={rsi:.1f}，已進入嚴重超買區（>80）\n'
                          '短線拉回機率高，追高容易被套'))
        elif rsi > 72:
            risks.append(('RSI偏高',
                          f'RSI={rsi:.1f}，偏高（>72），動能未退但追高風險升溫\n'
                          '建議等回測均線再進場'))

        if week52_pos >= 90:
            risks.append(('接近年度高點',
                          f'股價位於52週區間 {week52_pos:.0f}% 高位\n'
                          '上方空間有限、歷史壓力強，追高回撤風險大'))
        elif week52_pos >= 80:
            risks.append(('位於高位區間',
                          f'股價位於52週區間 {week52_pos:.0f}%\n'
                          '需留意高檔套牢壓力，停損點設置要精確'))

        if total_net < -1000:
            risks.append(('法人大幅賣出',
                          f'三大法人今日合計賣出 {abs(total_net):.0f} 張\n'
                          '技術訊號出現但大資金正在撤離，方向矛盾，風險高'))
        elif total_net < 0:
            risks.append(('法人小幅賣出',
                          f'法人今日賣出 {abs(total_net):.0f} 張\n'
                          '建議觀察是否連續賣出，籌碼流向存疑'))

        if change_pct >= 6:
            risks.append(('漲幅過大慎追',
                          f'今日漲幅 +{change_pct:.1f}%，接近漲停\n'
                          '追高風險極高，隔日開低機率大，建議等回測'))
        elif change_pct >= 4:
            risks.append(('漲幅偏大',
                          f'今日漲幅 +{change_pct:.1f}%\n'
                          '短線追高需謹慎，建議等拉回 MA5 附近再評估'))

        if k_val > 90:
            risks.append(('KD嚴重超買',
                          f'K值={k_val:.0f}，KD 嚴重超買（>90）\n'
                          '短線死叉風險高，急漲後容易急跌'))
        elif k_val > 80:
            risks.append(('KD進入超買',
                          f'K值={k_val:.0f}，KD 超買區間（>80）\n'
                          '動能雖強但短線壓力加大'))

        if 0 < volume < 200:
            risks.append(('流動性不足',
                          f'今日僅成交 {volume:.0f} 張\n'
                          '冷門股買賣價差大，難以在理想價位成交或出場'))

        return risks

    def risk_badges(risk_list: list) -> str:
        """把風險清單轉成 HTML 警示標籤"""
        if not risk_list:
            return '<span style="color:#66bb6a;font-size:12px;font-weight:600">✅ 無明顯風險</span>'
        badges = []
        for name, tip in risk_list:
            tip_esc = tip.replace('"', '&quot;')
            badges.append(
                f'<span title="{tip_esc}" style="background:#fff3e0;color:#e65100;'
                f'border:1px solid #ff9800;padding:2px 8px;border-radius:12px;'
                f'font-size:12px;font-weight:600;white-space:nowrap;margin:2px;'
                f'display:inline-block;cursor:help">⚠️ {name}</span>'
            )
        return ' '.join(badges)

    rec_df = df[df['buy_signals'].notna() & (df['buy_signals'] != '')].copy()
    rec_df = rec_df.sort_values('score', ascending=False).reset_index(drop=True)

    if rec_df.empty:
        st.info("📭 今日尚無股票觸發買進訊號，或數據尚未更新。請先點擊右上角「🔄 更新數據」。")
    else:
        # ── 訊號統計列 ─────────────────────────────────
        all_signal_names = ['均線黃金交叉', '法人爆量買進', 'RSI低谷反轉', 'MACD翻紅']
        stat_cols = st.columns(4)
        for i, sig in enumerate(all_signal_names):
            count = rec_df['buy_signals'].str.contains(sig, na=False).sum()
            _, _, icon, tip = SIGNAL_STYLE[sig]
            stat_cols[i].metric(f"{icon} {sig}", f"{count} 支", help=tip)

        st.divider()

        # ── 類別標籤 ────────────────────────────────────
        CAT_STYLE = {
            '強勢': ('background:#c62828;color:white', '強勢'),
            '中性': ('background:#555;color:white',    '中性'),
            '弱勢': ('background:#1565c0;color:white', '弱勢'),
            '轉強': ('background:#2e7d32;color:white', '轉強'),
            '轉弱': ('background:#6a1b9a;color:white', '轉弱'),
        }

        def cat_badge(cat: str) -> str:
            style, label = CAT_STYLE.get(cat, ('background:#888;color:white', cat))
            return (f'<span style="{style};padding:2px 10px;border-radius:12px;'
                    f'font-size:12px;font-weight:600">{label}</span>')

        # ── 建立 HTML 表格 ───────────────────────────────
        def pos_badge(pos):
            """52週位置：顏色區分高中低"""
            if pos is None or pos == 0:
                return '—'
            pos = float(pos)
            if pos >= 80:
                color, bg = '#b71c1c', '#ffebee'
            elif pos >= 50:
                color, bg = '#7f4500', '#fff3e0'
            else:
                color, bg = '#0d47a1', '#e3f2fd'
            return (f'<span style="background:{bg};color:{color};border:1px solid {color};'
                    f'padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600">'
                    f'{pos:.0f}%</span>')

        def strength_badge(s):
            if s == '強':
                return '<span style="background:#1b5e20;color:#e8f5e9;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:700">⚡ 強</span>'
            elif s == '普通':
                return '<span style="background:#424242;color:#eee;padding:2px 10px;border-radius:12px;font-size:12px">普通</span>'
            return '—'

        th  = '<th style="padding:10px 8px;white-space:nowrap">'
        thr = '<th style="padding:10px 8px;text-align:right;white-space:nowrap">'
        html_parts = [
            '<html><body style="margin:0;padding:0;background:transparent">',
            '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch;width:100%">',
            '<table style="width:max-content;min-width:100%;border-collapse:collapse;font-size:14px;color:#ddd">',
            '<thead><tr style="background:#1e1e2e;color:#aaa;text-align:left">',
            f'{th}走勢</th>{th}#</th>{th}代號</th>{th}名稱</th>',
            f'{thr}收盤價</th>{thr}漲跌%</th>{thr}量比</th>',
            f'{thr}法人合計</th>{thr}連續買進</th>',
            f'{th}52週位置</th>{th}狀態</th>{th}觸發訊號</th>{th}⚠️ 風險提示</th>',
            '</tr></thead><tbody>',
        ]

        for n, (_, row) in enumerate(rec_df.iterrows()):
            chg      = row.get('change_pct', 0) or 0
            chg_clr  = '#ef5350' if chg > 0 else ('#42a5f5' if chg < 0 else '#aaa')
            risks    = compute_risks(row)
            bg       = '#16161e' if n % 2 == 0 else '#1a1a28'
            consec   = int(row.get('inst_consec', 0) or 0)
            consec_s = f'{consec}天' if consec > 0 else '—'
            consec_c = '#66bb6a' if consec >= 3 else ('#ffb74d' if consec >= 1 else '#888')
            td       = f'style="padding:10px 8px;background:{bg}"'
            tdr      = f'style="padding:10px 8px;text-align:right;background:{bg}"'
            spark    = sparklines.get(str(row['code']), make_sparkline_svg([]))
            html_parts.append(
                f'<tr>'
                f'<td style="padding:4px 6px;background:{bg}">{spark}</td>'
                f'<td style="padding:10px 8px;background:{bg};color:#666">{n+1}</td>'
                f'<td style="padding:10px 8px;background:{bg};font-weight:700;color:#ffd54f">{row["code"]}</td>'
                f'<td {td}>{row.get("name","")}</td>'
                f'<td {tdr}>{row.get("close",0):.2f}</td>'
                f'<td style="padding:10px 8px;text-align:right;background:{bg};color:{chg_clr};font-weight:600">{chg:+.2f}%</td>'
                f'<td {tdr}>{row.get("vol_ratio",0):.2f}</td>'
                f'<td {tdr}>{int(row.get("total_net",0) or 0):,}</td>'
                f'<td style="padding:10px 8px;text-align:right;background:{bg};color:{consec_c};font-weight:600">{consec_s}</td>'
                f'<td {td}>{pos_badge(row.get("week52_pos"))}</td>'
                f'<td {td}>{cat_badge(row.get("category",""))}</td>'
                f'<td {td}>{signal_badges(row.get("buy_signals",""))}</td>'
                f'<td {td}>{risk_badges(risks)}</td>'
                f'</tr>'
            )

        html_parts.append('</tbody></table></div></body></html>')
        table_html = ''.join(html_parts)

        # 每列預估高度：多個風險標籤可能換行，保守估 72px
        row_height   = 72
        table_height = 80 + len(rec_df) * row_height
        components.html(table_html, height=table_height, scrolling=False)
        st.caption(f"共 {len(rec_df)} 支股票觸發買進訊號（依評分高→低排序）")

# ── Tab 1：強勢股 ─────────────────────────────────────
with tab1:
    st.markdown("### 🔴 強勢股")
    st.caption("評分 ≥ 60（滿分 100 分），技術面 + 法人籌碼全面偏多")

    with st.expander("📊 評分組成說明（點擊展開）", expanded=False):
        st.markdown("""
| 評分項目 | 滿分 | 評分邏輯 |
|---------|------|---------|
| **技術面** | 40分 | 收盤站上MA20（+15）、MA20>MA60多頭排列（+10）、RSI強弱（最高+15）、MACD轉正（+5） |
| **量能** | 20分 | 量比 ≥ 2.0（+20）、≥ 1.5（+12）、≥ 1.2（+6）、< 0.5（-5） |
| **法人籌碼** | 40分 | 三大法人合計淨買 > 10,000張（+40）、> 3,000張（+28）、> 500張（+16）、> 0（+6） |

> 強勢 = **60分以上**；弱勢 = **28分以下**；中性 = 29～59分
""")

    strong_df = df_view[df_view['category'] == '強勢']
    if not strong_df.empty:
        score_min = int(strong_df['score'].min())
        score_max = int(strong_df['score'].max())
        score_avg = round(strong_df['score'].mean(), 1)
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("最高評分", f"{score_max} 分")
        sc2.metric("平均評分", f"{score_avg} 分")
        sc3.metric("最低評分", f"{score_min} 分")
        st.dataframe(
            with_sparks(strong_df, fmt(strong_df), sparklines),
            column_config={'走勢': st.column_config.ImageColumn('走勢', width='small')},
            use_container_width=True, height=500, hide_index=True,
        )
        st.caption(f"共 {len(strong_df)} 支（評分 {score_min}～{score_max} 分）")
    else:
        st.info("今日無強勢股（或被篩選條件過濾）")

# ── Tab 1b：回調整理 ──────────────────────────────────
with tab1b:
    st.markdown("### 📉 強勢多頭回調整理")

    with st.expander("📖 什麼是「回調整理」？篩選邏輯說明（點擊展開）", expanded=True):
        st.markdown("""
**概念說明**

這類股票的特徵：趨勢結構完好的多頭股，因短線獲利了結而**回落到 MA20（20日均線）附近整理**。

這是一個相對低風險的進場等待位——趨勢沒有壞掉，只是暫時休息補充能量。

> 類比：好股票就像馬拉松選手，偶爾需要放慢腳步補水（回調到均線），而不是一路衝刺到崩潰。

---

**系統篩選條件（6 項全部符合才納入）**

| # | 條件 | 門檻 | 為什麼重要 |
|---|------|------|----------|
| 1 | **多頭排列** | 今日 MA20 > MA60 | 確認整體趨勢結構沒有壞掉 |
| 2 | **有多頭基礎** | 過去 30 天中，≥ 50% 天數收盤站上 MA20 | 不是剛起步的弱股，是真正在上漲中的股票 |
| 3 | **有實質回調幅度** | 30天內最高點 > 現價 × 1.05 | 確認是從高點拉回（微小波動不算），有買點意義 |
| 4 | **靠近均線支撐** | 收盤與 MA20 距離 ≤ 3% | 正在回到均線附近，是歷史上容易獲得支撐的價位 |
| 5 | **RSI 合理** | 35 ≤ RSI ≤ 65 | 排除兩種危險：崩跌中（RSI<35）或追高（RSI>65） |
| 6 | **非爆量殺跌** | 量比 ≤ 2.5 | 爆量下跌代表有人在急拋，縮量整理才健康 |

> ⚠️ **重要提醒**：符合此形態**不代表可以馬上買進**。建議等待額外確認訊號，例如：
> - 出現止跌 K 棒（長下影線、吞噬、錘子線）
> - 量能回升（量比 > 1.2）
> - 搭配「今日推薦」頁面的買進訊號同時出現
""")

    # 計算符合形態的股票
    hist_df = load_scores_history(days=30)
    pullback_codes = []
    if not hist_df.empty:
        for code, grp in hist_df.groupby('code'):
            if classify_pullback(grp.sort_values('date').reset_index(drop=True)):
                pullback_codes.append(code)

    pullback_df = df[df['code'].isin(pullback_codes)].copy()
    pullback_df = pullback_df.sort_values('score', ascending=False)

    if pullback_df.empty:
        st.info("📭 今日無符合「強勢多頭回調整理」形態的股票（可能因盤整或資料不足）")
    else:
        st.caption(f"共篩選出 **{len(pullback_df)}** 支 ｜ 依評分高→低排序")
        st.dataframe(
            with_sparks(pullback_df, fmt(pullback_df), sparklines),
            column_config={'走勢': st.column_config.ImageColumn('走勢', width='small')},
            use_container_width=True, height=520, hide_index=True,
        )
        st.caption("💡 建議搭配「今日推薦」頁面確認是否同時觸發買進訊號，雙重確認後再進場評估")

# ── Tab 1c：N字反轉 ───────────────────────────────────
with tab1c:
    st.markdown("### 🔼 N字反轉")

    with st.expander("📖 型態圖示說明（點擊展開）", expanded=False):
        st.markdown("""
N字反轉形狀像英文字母 N，分為兩個階段：

```
價格
 ↑
 │  X高(起點)──────────────────── 突破！→ 第一區塊
 │      ╲                       ╱
 │       ╲    X段（下跌）      ╱
 │        ╲                  ╱
 │  50%水位 ╲──────────────── → 黃金買入區（回跌到此出現訊號）
 │         X低(底部)
 │  出局水位 ─────────────────── → 跌破此處訊號失效
 │
 └──────────────────────────────────────→ 時間
```
""")

    # ── 同時掃描兩種型態（共用一次載入 ohlcv）──
    @st.cache_data(ttl=1800, show_spinner=False)
    def get_n_reversal_results():
        ohlcv_df = load_ohlcv_recent(days=90)
        if ohlcv_df.empty:
            return [], {}, [], {}
        n_codes, n_details, g_codes, g_details = [], {}, [], {}
        for code, grp in ohlcv_df.groupby('code'):
            hist = grp.sort_values('date').reset_index(drop=True)
            info = classify_n_reversal(hist)
            if info is not None:
                n_codes.append(code)
                n_details[code] = info
            ginfo = classify_golden_zone(hist)
            if ginfo is not None:
                g_codes.append(code)
                g_details[code] = ginfo
        return n_codes, n_details, g_codes, g_details

    with st.spinner("正在掃描 N字反轉型態（約需 5-15 秒）…"):
        n_codes, n_details, g_codes, g_details = get_n_reversal_results()

    # ══ 第一區塊：突破X高點 ════════════════════════════
    st.markdown("#### 📈 第一區塊：剛突破 X 高點（最近 7 天內突破）")
    st.caption("股價剛突破前波下跌的起點高位，是 N字型態完成的突破訊號")

    n_df = df[df['code'].isin(n_codes)].copy()
    if not n_df.empty and n_details:
        n_df['X高']      = n_df['code'].map(lambda c: n_details.get(c, {}).get('x_high', ''))
        n_df['X低']      = n_df['code'].map(lambda c: n_details.get(c, {}).get('x_low', ''))
        n_df['X跌幅%']   = n_df['code'].map(lambda c: n_details.get(c, {}).get('decline_pct', ''))
        n_df['突破後漲%'] = n_df['code'].map(lambda c: n_details.get(c, {}).get('break_pct', ''))
        n_df = n_df.sort_values('score', ascending=False)

    if n_df.empty:
        st.info("📭 今日無符合「剛突破X高點」型態的股票")
    else:
        st.caption(f"共篩選出 **{len(n_df)}** 支 ｜ 依評分高→低排序")
        _disp_n = fmt(n_df).reset_index(drop=True)
        _orig_n = n_df.reset_index(drop=True)
        if 'X高' in _orig_n.columns and 'MA60' in _disp_n.columns:
            _pos = _disp_n.columns.get_loc('MA60') + 1
            _disp_n.insert(_pos,     'X高', _orig_n['X高'])
            _disp_n.insert(_pos + 1, 'X低', _orig_n['X低'])
        st.dataframe(
            with_sparks(n_df, _disp_n, sparklines),
            column_config={'走勢': st.column_config.ImageColumn('走勢', width='small')},
            use_container_width=True, height=400, hide_index=True,
        )
        st.caption("💡 突破後留意是否縮量回測，若低點不破 X 低則訊號持續有效")

    st.divider()

    # ══ 第二區塊：黃金買入區 ═══════════════════════════
    st.markdown("#### 🥇 第二區塊：黃金買入區（回跌至 X 段 50% 位置）")

    with st.expander("📖 黃金買入區邏輯說明（點擊展開）", expanded=False):
        st.markdown("""
**什麼情況會出現黃金買入區訊號？**

1. 股票先完成了 N字反轉（突破 X 高點）
2. 突破後股價**回跌**至 X 高到 X 低距離的 **50% 水位**
3. 這個位置是「拉回補倉」的低風險進場區

**訊號存在條件（每日收盤後判斷）：**
- ✅ 收盤 ≤ 50% 水位（= X低 + X高度 × 50%）
- ✅ 收盤 > 出局水位（= X低 − X高度 × 50%）

**範例（X高=650，X低=550，X高度=100點）：**
| 關鍵水位 | 計算 | 價格 |
|--------|------|------|
| X 高點 | 突破點 | 650 |
| 50% 水位（黃金區上緣） | 550 + 50 | 600 |
| X 低點 | 支撐底部 | 550 |
| 出局水位 | 550 − 50 | 500 |

> ⚠️ 跌破 500 → 出局，訊號消失
""")

    g_df = df[df['code'].isin(g_codes)].copy()
    if not g_df.empty and g_details:
        g_df['X高']    = g_df['code'].map(lambda c: g_details.get(c, {}).get('x_high', ''))
        g_df['X低']    = g_df['code'].map(lambda c: g_details.get(c, {}).get('x_low', ''))
        g_df['50%水位'] = g_df['code'].map(lambda c: g_details.get(c, {}).get('50%水位', ''))
        g_df['出局水位'] = g_df['code'].map(lambda c: g_details.get(c, {}).get('出局水位', ''))
        g_df['X跌幅%'] = g_df['code'].map(lambda c: g_details.get(c, {}).get('X跌幅%', ''))
        g_df = g_df.sort_values('score', ascending=False)

    if g_df.empty:
        st.info("📭 今日無股票進入黃金買入區（N字突破後尚未回跌到 50% 位置，或已跌破出局水位）")
    else:
        st.caption(f"共篩選出 **{len(g_df)}** 支 ｜ 依評分高→低排序")
        _disp_g = fmt(g_df).reset_index(drop=True)
        _orig_g = g_df.reset_index(drop=True)
        if 'X高' in _orig_g.columns and 'MA60' in _disp_g.columns:
            _pos = _disp_g.columns.get_loc('MA60') + 1
            _disp_g.insert(_pos,     'X高', _orig_g['X高'])
            _disp_g.insert(_pos + 1, 'X低', _orig_g['X低'])
        st.dataframe(
            with_sparks(g_df, _disp_g, sparklines),
            column_config={'走勢': st.column_config.ImageColumn('走勢', width='small')},
            use_container_width=True, height=400, hide_index=True,
        )
        st.caption("💡 黃金買入區：回跌至低風險進場區，每日收盤後自動更新是否仍在區間內")


# ── Tab 2：弱勢股 ─────────────────────────────────────
with tab2:
    st.markdown("### 💙 弱勢股")
    st.caption("評分 ≤ 28（滿分 100 分），技術面 + 法人籌碼全面偏空，建議觀望")

    with st.expander("📊 評分組成說明（點擊展開）", expanded=False):
        st.markdown("""
| 評分項目 | 滿分 | 評分邏輯 |
|---------|------|---------|
| **技術面** | 40分 | 收盤站上MA20（+15）、MA20>MA60多頭排列（+10）、RSI強弱（最高+15）、MACD轉正（+5） |
| **量能** | 20分 | 量比 ≥ 2.0（+20）、≥ 1.5（+12）、≥ 1.2（+6）、< 0.5（-5） |
| **法人籌碼** | 40分 | 三大法人合計淨買 > 10,000張（+40）、> 3,000張（+28）、> 500張（+16）；若法人大賣最多扣20分 |

> 強勢 = **60分以上**；弱勢 = **28分以下**；中性 = 29～59分
""")

    weak_df = df_view[df_view['category'] == '弱勢']
    if not weak_df.empty:
        score_min = int(weak_df['score'].min())
        score_max = int(weak_df['score'].max())
        score_avg = round(weak_df['score'].mean(), 1)
        wc1, wc2, wc3 = st.columns(3)
        wc1.metric("最高評分", f"{score_max} 分")
        wc2.metric("平均評分", f"{score_avg} 分")
        wc3.metric("最低評分", f"{score_min} 分")
        st.dataframe(
            with_sparks(weak_df, fmt(weak_df), sparklines),
            column_config={'走勢': st.column_config.ImageColumn('走勢', width='small')},
            use_container_width=True, height=500, hide_index=True,
        )
        st.caption(f"共 {len(weak_df)} 支（評分 {score_min}～{score_max} 分）")
    else:
        st.info("今日無弱勢股（或被篩選條件過濾）")

# ── Tab 3：全部股票 ───────────────────────────────────
with tab3:
    st.markdown("### 🔍 全市場搜尋")

    row1 = st.columns([3, 1])
    with row1[0]:
        keyword = st.text_input("輸入股票代號或名稱關鍵字", placeholder="例：台積電、2330、金融...")
    with row1[1]:
        sort_by = st.selectbox("排序方式", ["評分（高→低）", "漲跌%（高→低）", "量比（高→低）", "法人合計5日（高→低）"])

    search_df = df_view.copy()
    if keyword:
        mk = (search_df['code'].str.contains(keyword, na=False) |
              search_df['name'].str.contains(keyword, na=False))
        search_df = search_df[mk]

    sort_map = {
        "評分（高→低）":        'score',
        "漲跌%（高→低）":       'change_pct',
        "量比（高→低）":        'vol_ratio',
        "法人合計5日（高→低）": 'total_5d',
    }
    search_df = search_df.sort_values(sort_map[sort_by], ascending=False)

    st.dataframe(
        with_sparks(search_df, fmt(search_df), sparklines),
        column_config={'走勢': st.column_config.ImageColumn('走勢', width='small')},
        use_container_width=True, height=550, hide_index=True,
    )
    st.caption(f"顯示 {len(search_df)} 支股票")

# ── Tab 4：市場分析 ───────────────────────────────────
with tab4:
    st.markdown("### 📊 今日市場強弱分佈")

    import plotly.graph_objects as go
    cat_order = ['強勢', '中性', '弱勢']
    cat_color = {'強勢': '#ff4b4b', '中性': '#888888', '弱勢': '#0066cc'}
    dist = df.groupby('category').size().reset_index(name='數量')
    dist['category'] = pd.Categorical(dist['category'], categories=cat_order, ordered=True)
    dist = dist.sort_values('category')

    bar_fig = go.Figure(go.Bar(
        x=dist['category'],
        y=dist['數量'],
        marker_color=[cat_color.get(c, '#888888') for c in dist['category']],
        text=dist['數量'],
        textposition='outside',
    ))
    bar_fig.update_layout(height=320, showlegend=False,
                          xaxis_title='狀態', yaxis_title='股票數量',
                          margin=dict(t=20, b=20))
    st.plotly_chart(bar_fig, use_container_width=True)

    st.markdown("### 📋 法人籌碼統計（5日累計）")
    stat_cols = st.columns(3)
    with stat_cols[0]:
        top_foreign = df.nlargest(10, 'foreign_5d')[['code', 'name', 'foreign_net', 'foreign_3d', 'foreign_5d', 'score']]
        top_foreign.columns = ['代號', '名稱', '外資今日', '外資3日', '外資5日', '評分']
        st.markdown("**外資買超 Top 10（5日）**")
        st.dataframe(top_foreign, hide_index=True, use_container_width=True)
    with stat_cols[1]:
        top_trust = df.nlargest(10, 'trust_5d')[['code', 'name', 'trust_net', 'trust_3d', 'trust_5d', 'score']]
        top_trust.columns = ['代號', '名稱', '投信今日', '投信3日', '投信5日', '評分']
        st.markdown("**投信買超 Top 10（5日）**")
        st.dataframe(top_trust, hide_index=True, use_container_width=True)
    with stat_cols[2]:
        top_total = df.nlargest(10, 'total_5d')[['code', 'name', 'total_net', 'total_3d', 'total_5d', 'score']]
        top_total.columns = ['代號', '名稱', '法人今日', '法人3日', '法人5日', '評分']
        st.markdown("**三大法人 Top 10（5日）**")
        st.dataframe(top_total, hide_index=True, use_container_width=True)
