"""
每日數據更新腳本
執行方式：python3 /Users/sam/Desktop/ClaudeAgent/stock_radar/update.py
建議時機：每天下午 3:35 盤後執行
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from datetime import datetime

from config import HISTORY_DAYS
from database import (init_db, save_stock_list, save_prices, save_institutional,
                      save_scores, load_price_history, load_institutional,
                      need_backfill, need_inst_backfill)
from data_fetcher import (fetch_stock_list, fetch_today_prices,
                          fetch_today_institutional, backfill_history,
                          backfill_institutional)
from indicators import calculate_indicators
from scoring import calculate_all_scores


def run():
    print("=" * 55)
    print(f"🚀  台股雷達更新  ─  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # 1. 初始化資料庫
    init_db()

    # 2. 取得股票清單
    stock_list = fetch_stock_list()
    if stock_list is None or stock_list.empty:
        print("❌ 無法取得股票清單，請確認網路連線")
        return
    save_stock_list(stock_list)

    # 3. 首次執行：回填歷史 K 線
    if need_backfill():
        codes = stock_list['code'].tolist()
        history = backfill_history(codes, days=HISTORY_DAYS)
        if history is not None:
            save_prices(history)
        else:
            print("⚠️  歷史回填失敗，指標計算可能不準確")

    # 4. 回填法人歷史數據（不足 3 個交易日時補抓）
    if need_inst_backfill():
        inst_history = backfill_institutional(days=5)
        if inst_history is not None:
            save_institutional(inst_history)

    # 5. 先抓法人，從回應中取得實際最新交易日期（T86 日期最準確）
    institutional = fetch_today_institutional()
    actual_date = None
    if institutional is not None and not institutional.empty:
        actual_date = institutional['date'].iloc[0]  # e.g. '2026-04-23'
        save_institutional(institutional)
        print(f"  📅 確認最新交易日：{actual_date}")

    # 6. 抓取今日行情（yfinance，以收盤後即時數據為準）
    today_prices = fetch_today_prices(stock_list['code'].tolist())
    if today_prices is not None:
        save_prices(today_prices)

    # 建立 {code: change_pct} 對照表，供後面直接套用正確漲跌幅
    change_pct_map = {}
    if today_prices is not None:
        change_pct_map = dict(zip(today_prices['code'], today_prices['change_pct']))
        price_api_date = today_prices['date'].iloc[0]
    else:
        price_api_date = None

    # 7. 計算技術指標
    print("\n📐 計算技術指標（約需 1 分鐘）...")
    price_history = load_price_history()

    if price_history.empty:
        print("❌ 資料庫無價格數據")
        return

    all_with_indicators = []
    codes = price_history['code'].unique()
    for code in codes:
        stock_df = price_history[price_history['code'] == code].copy()
        if len(stock_df) >= 20:
            calculated = calculate_indicators(stock_df)
            all_with_indicators.append(calculated)

    if not all_with_indicators:
        print("❌ 指標計算失敗，請確認歷史數據完整性")
        return

    all_df = pd.concat(all_with_indicators, ignore_index=True)

    # 用 API 的 Change 欄位覆蓋最新一天的漲跌幅（更準確）
    if change_pct_map and price_api_date:
        mask = all_df['date'] == price_api_date
        all_df.loc[mask, 'change_pct'] = all_df.loc[mask, 'code'].map(change_pct_map)

    print(f"  ✅ 完成 {len(all_with_indicators)} 支股票指標計算")

    # 8. 讀取最近 10 日法人數據（多載供連續買進天數計算，3d/5d 累計仍取最近幾日）
    print("\n🏆 計算評分與分類...")
    inst_data = load_institutional(days=10)
    scores_df = calculate_all_scores(all_df, inst_data)

    if scores_df.empty:
        print("❌ 評分計算失敗")
        return

    # 9. 寫入資料庫
    save_scores(scores_df)

    # 10. 統計摘要
    print(f"\n{'=' * 55}")
    print(f"✅  更新完成！共評分 {len(scores_df)} 支股票")
    print(f"{'─' * 55}")
    for cat in ['強勢', '轉強', '中性', '轉弱', '弱勢']:
        n = len(scores_df[scores_df['category'] == cat])
        bar = '█' * (n // 10)
        print(f"  {cat}：{n:>4} 支  {bar}")
    print(f"{'=' * 55}")
    print("  現在可以開啟網頁：")
    print("  python3 -m streamlit run /Users/sam/Desktop/ClaudeAgent/stock_radar/app.py")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    run()
