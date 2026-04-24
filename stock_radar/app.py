"""
台股全市場雷達 ─ Streamlit 網頁介面
啟動方式：python3 -m streamlit run /Users/sam/Desktop/ClaudeAgent/stock_radar/app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import subprocess
from database import load_scores, has_data

st.set_page_config(
    page_title="台股全市場雷達",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.dataframe td { font-size: 13px !important; }
[data-testid="metric-container"] {
    background-color: #1e1e1e;
    border-radius: 8px;
    padding: 12px;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────
# 側邊欄
# ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("📡 台股雷達")
    st.caption("每日盤後自動更新")
    st.divider()

    if st.button("🔄 立即更新數據", type="primary", use_container_width=True):
        with st.spinner("正在抓取最新數據，請稍候（首次約 5~10 分鐘）..."):
            result = subprocess.run(
                ["python3", os.path.join(os.path.dirname(__file__), "update.py")],
                capture_output=True, text=True
            )
        if result.returncode == 0:
            st.success("✅ 更新完成！")
            st.rerun()
        else:
            st.error("❌ 更新失敗，請查看終端機錯誤訊息")
            st.code(result.stderr[-1000:])

    st.divider()
    st.markdown("**篩選設定**")
    show_cats = st.multiselect(
        "顯示狀態",
        ["強勢", "中性", "弱勢"],
        default=["強勢", "中性", "弱勢"],
    )
    min_score = st.slider("最低評分", 0, 100, 0, step=5)

    st.divider()
    st.markdown("""
**評分說明**
- 🔴 **強勢**：≥ 60 分
- ⚪ **中性**：29~59 分
- 💙 **弱勢**：≤ 28 分
""")

# ──────────────────────────────────────────────────────
# 資料未就緒
# ──────────────────────────────────────────────────────
if not has_data():
    st.title("📡 台股全市場雷達")
    st.warning("⚠️  尚無資料，請點擊左側「立即更新數據」按鈕")
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

# ──────────────────────────────────────────────────────
# 標題與市場統計
# ──────────────────────────────────────────────────────
last_date = df['date'].iloc[0] if not df.empty else "—"
st.title(f"📡 台股全市場雷達  ·  {last_date}")

total = len(df)
c1, c2, c3 = st.columns(3)
def pct(n): return f"{n/total*100:.1f}%" if total > 0 else "0%"
n_s = len(df[df['category'] == '強勢'])
n_n = len(df[df['category'] == '中性'])
n_w = len(df[df['category'] == '弱勢'])

c1.metric("🔴 強勢", n_s, pct(n_s))
c2.metric("⚪ 中性", n_n, pct(n_n))
c3.metric("💙 弱勢", n_w, pct(n_w))
st.caption(f"共 {total} 支股票 ｜ 目前顯示 {len(df_view)} 支")
st.divider()

# ──────────────────────────────────────────────────────
# 欄位格式化（統一順序：代號名稱 → MA → 法人 → 其他指標 → 評分狀態訊號）
# ──────────────────────────────────────────────────────

_COLS = ['code', 'name', 'close', 'change_pct', 'volume',
         'ma20', 'ma60',
         'foreign_net', 'foreign_3d', 'foreign_5d',
         'trust_net',   'trust_3d',   'trust_5d',
         'total_net',   'total_3d',   'total_5d',
         'rsi', 'k', 'd', 'vol_ratio',
         'score', 'category', 'signals']

_LABELS = ['代號', '名稱', '收盤價', '漲跌%', '成交量(張)',
           'MA20', 'MA60',
           '外資(今)', '外資(3日)', '外資(5日)',
           '投信(今)', '投信(3日)', '投信(5日)',
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
    inst_cols = ['外資(今)', '外資(3日)', '外資(5日)',
                 '投信(今)', '投信(3日)', '投信(5日)',
                 '法人合計(今)', '法人合計(3日)', '法人合計(5日)']
    for col in inst_cols:
        if col in d.columns:
            d[col] = d[col].fillna(0).astype(int)
    return d

# ──────────────────────────────────────────────────────
# 分頁
# ──────────────────────────────────────────────────────
tab0, tab1, tab2, tab3, tab4 = st.tabs(["🎯 今日推薦", "🔴 強勢股", "💙 弱勢股", "🔍 全部股票", "📊 市場分析"])

# ── Tab 0：今日推薦 ───────────────────────────────────
with tab0:
    st.markdown("### 🎯 今日推薦股票")
    st.caption("系統偵測到明確買進訊號的股票，僅供參考，買賣決策請自行判斷")

    if 'buy_signals' not in df.columns:
        df['buy_signals'] = ''

    # 訊號顏色與圖示
    SIGNAL_STYLE = {
        '均線黃金交叉': ('#1b5e20', '#e8f5e9', '📈'),
        '法人爆量買進': ('#7f4500', '#fff3e0', '💰'),
        'RSI低谷反轉':  ('#0d47a1', '#e3f2fd', '🔄'),
        'MACD翻紅':     ('#b71c1c', '#ffebee', '🔴'),
    }

    def signal_badges(signal_str: str) -> str:
        """把訊號字串轉成彩色 HTML 標籤"""
        if not signal_str:
            return '—'
        badges = []
        for sig in signal_str.split('、'):
            sig = sig.strip()
            if sig in SIGNAL_STYLE:
                fg, bg, icon = SIGNAL_STYLE[sig]
                badges.append(
                    f'<span style="background:{bg};color:{fg};border:1px solid {fg};'
                    f'padding:3px 10px;border-radius:20px;font-size:12px;'
                    f'font-weight:600;white-space:nowrap;margin:2px;display:inline-block">'
                    f'{icon} {sig}</span>'
                )
        return ' '.join(badges)

    rec_df = df[df['buy_signals'].notna() & (df['buy_signals'] != '')].copy()
    rec_df = rec_df.sort_values('score', ascending=False).reset_index(drop=True)

    if rec_df.empty:
        st.info("📭 今日尚無股票觸發買進訊號，或數據尚未更新。請先點擊左側「立即更新數據」。")
    else:
        # ── 訊號統計列 ─────────────────────────────────
        all_signal_names = ['均線黃金交叉', '法人爆量買進', 'RSI低谷反轉', 'MACD翻紅']
        stat_cols = st.columns(4)
        for i, sig in enumerate(all_signal_names):
            count = rec_df['buy_signals'].str.contains(sig, na=False).sum()
            _, _, icon = SIGNAL_STYLE[sig]
            stat_cols[i].metric(f"{icon} {sig}", f"{count} 支")

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
        th = '<th style="padding:10px 8px;white-space:nowrap">'
        thr = '<th style="padding:10px 8px;text-align:right;white-space:nowrap">'
        html_parts = [
            '<html><body style="margin:0;padding:0;background:transparent">',
            '<table style="width:100%;border-collapse:collapse;font-size:14px;color:#ddd">',
            '<thead><tr style="background:#1e1e2e;color:#aaa;text-align:left">',
            f'{th}#</th>{th}代號</th>{th}名稱</th>',
            f'{thr}收盤價</th>{thr}漲跌%</th>{thr}量比</th>',
            f'{thr}法人合計</th>{thr}RSI</th>{thr}評分</th>',
            f'{th}狀態</th>{th}觸發訊號</th>',
            '</tr></thead><tbody>',
        ]

        for n, (_, row) in enumerate(rec_df.iterrows()):
            chg     = row.get('change_pct', 0) or 0
            chg_clr = '#ef5350' if chg > 0 else ('#42a5f5' if chg < 0 else '#aaa')
            bg      = '#16161e' if n % 2 == 0 else '#1a1a28'
            td      = f'style="padding:10px 8px;background:{bg}"'
            tdr     = f'style="padding:10px 8px;text-align:right;background:{bg}"'
            html_parts.append(
                f'<tr>'
                f'<td {td} style="padding:10px 8px;background:{bg};color:#666">{n+1}</td>'
                f'<td {td} style="padding:10px 8px;background:{bg};font-weight:700;color:#ffd54f">{row["code"]}</td>'
                f'<td {td}>{row.get("name","")}</td>'
                f'<td {tdr}>{row.get("close",0):.2f}</td>'
                f'<td style="padding:10px 8px;text-align:right;background:{bg};color:{chg_clr};font-weight:600">{chg:+.2f}%</td>'
                f'<td {tdr}>{row.get("vol_ratio",0):.2f}</td>'
                f'<td {tdr}>{int(row.get("total_net",0) or 0):,}</td>'
                f'<td {tdr}>{row.get("rsi",0):.1f}</td>'
                f'<td style="padding:10px 8px;text-align:right;background:{bg};font-weight:700;color:#fff">{row.get("score",0):.0f}</td>'
                f'<td {td}>{cat_badge(row.get("category",""))}</td>'
                f'<td {td}>{signal_badges(row.get("buy_signals",""))}</td>'
                f'</tr>'
            )

        html_parts.append('</tbody></table></body></html>')
        table_html = ''.join(html_parts)

        row_height = 52
        table_height = 60 + len(rec_df) * row_height
        components.html(table_html, height=table_height, scrolling=False)
        st.caption(f"共 {len(rec_df)} 支股票觸發買進訊號（依評分高→低排序）")

# ── Tab 1：強勢股 ─────────────────────────────────────
with tab1:
    st.markdown("### 🔴 強勢股")
    st.caption("評分 ≥ 60，技術面 + 法人全面偏多")
    strong_df = df_view[df_view['category'] == '強勢']
    if not strong_df.empty:
        st.dataframe(fmt(strong_df), use_container_width=True, height=500, hide_index=True)
        st.caption(f"共 {len(strong_df)} 支")
    else:
        st.info("今日無強勢股（或被篩選條件過濾）")

# ── Tab 2：弱勢股 ─────────────────────────────────────
with tab2:
    st.markdown("### 💙 弱勢股")
    st.caption("評分 ≤ 28，技術面 + 法人全面偏空，建議觀望")
    weak_df = df_view[df_view['category'] == '弱勢']
    if not weak_df.empty:
        st.dataframe(fmt(weak_df), use_container_width=True, height=500, hide_index=True)
        st.caption(f"共 {len(weak_df)} 支")
    else:
        st.info("今日無弱勢股（或被篩選條件過濾）")

# ── Tab 3：全部股票 ───────────────────────────────────
with tab3:
    st.markdown("### 🔍 全市場搜尋")

    row1 = st.columns([3, 1])
    with row1[0]:
        keyword = st.text_input("輸入股票代號或名稱關鍵字", placeholder="例：台積電、2330、金融...")
    with row1[1]:
        sort_by = st.selectbox("排序方式", ["評分（高→低）", "漲跌%（高→低）", "量比（高→低）", "外資買超（高→低）", "法人合計5日（高→低）"])

    search_df = df_view.copy()
    if keyword:
        mk = (search_df['code'].str.contains(keyword, na=False) |
              search_df['name'].str.contains(keyword, na=False))
        search_df = search_df[mk]

    sort_map = {
        "評分（高→低）":        'score',
        "漲跌%（高→低）":       'change_pct',
        "量比（高→低）":        'vol_ratio',
        "外資買超（高→低）":    'foreign_net',
        "法人合計5日（高→低）": 'total_5d',
    }
    search_df = search_df.sort_values(sort_map[sort_by], ascending=False)

    st.dataframe(fmt(search_df), use_container_width=True, height=550, hide_index=True)
    st.caption(f"顯示 {len(search_df)} 支股票")

# ── Tab 4：市場分析 ───────────────────────────────────
with tab4:
    st.markdown("### 📊 今日市場強弱分佈")

    import altair as alt
    cat_order = ['強勢', '中性', '弱勢']
    cat_color = {
        '強勢': '#ff4b4b', '中性': '#888888', '弱勢': '#0066cc',
    }
    dist = df.groupby('category').size().reset_index(name='數量')
    dist['category'] = pd.Categorical(dist['category'], categories=cat_order, ordered=True)
    dist = dist.sort_values('category')

    bar = alt.Chart(dist).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X('category:N', sort=cat_order, title='狀態', axis=alt.Axis(labelFontSize=14)),
        y=alt.Y('數量:Q', title='股票數量'),
        color=alt.Color('category:N',
                        scale=alt.Scale(domain=cat_order, range=list(cat_color.values())),
                        legend=None),
        tooltip=['category', '數量'],
    ).properties(height=300)
    st.altair_chart(bar, use_container_width=True)

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
