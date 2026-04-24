"""
資料抓取模組
資料來源：
  - 台灣證交所 Open API（免費，無需帳號）：今日行情 + 三大法人
  - yfinance（免費，無需帳號）：歷史K線回填
"""
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import time
from config import DEBUG_MODE, DEBUG_STOCKS


# ────────────────────────────────────────────
# 1. 股票清單
# ────────────────────────────────────────────

def fetch_stock_list():
    """從台灣證交所取得上市普通股清單，回傳 DataFrame（code, name）
    DEBUG_MODE = True 時只回傳 DEBUG_STOCKS 清單中的股票
    """
    print("📋 取得上市股票清單...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        df = df[df['Code'].str.match(r'^\d{4}$')].copy()
        result = pd.DataFrame({'code': df['Code'].values, 'name': df['Name'].values})

        # 調試模式：只保留指定的 50 支股票
        if DEBUG_MODE:
            result = result[result['code'].isin(DEBUG_STOCKS)].copy()
            print(f"  🔧 調試模式：限縮至 {len(result)} 支股票")
        else:
            print(f"  ✅ 共 {len(result)} 檔上市股票")

        return result
    except Exception as e:
        print(f"  ❌ 失敗：{e}")
        return None


# ────────────────────────────────────────────
# 2. 今日行情（一次取得全部）
# ────────────────────────────────────────────

def fetch_today_prices():
    """從台灣證交所取得最新收盤資料
    注意：TWSE API 用民國年格式（如 '1150423' = 2026-04-23），
    以 API 實際回傳的日期為準，不用系統時間，避免日期錯誤
    """
    print("💹 取得今日行情...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        df = pd.DataFrame(data)
        df = df[df['Code'].str.match(r'^\d{4}$')].copy()

        def clean(col):
            return pd.to_numeric(df[col].str.replace(',', ''), errors='coerce')

        # 從 API 的民國年日期（如 '1150423'）轉為西元（'2026-04-23'）
        raw_date = df['Date'].iloc[0]
        api_date = f"{int(raw_date[:3]) + 1911}-{raw_date[3:5]}-{raw_date[5:7]}"

        # Change 欄位 = 今日漲跌金額，計算漲跌%
        change_amt  = clean('Change')
        close_price = clean('ClosingPrice')
        prev_close  = close_price - change_amt
        change_pct  = (change_amt / prev_close * 100).where(prev_close.abs() > 0.001, 0).round(2)

        result = pd.DataFrame({
            'date':       api_date,
            'code':       df['Code'].values,
            'open':       clean('OpeningPrice').values,
            'high':       clean('HighestPrice').values,
            'low':        clean('LowestPrice').values,
            'close':      close_price.values,
            'volume':     clean('TradeVolume').values,
            'amount':     clean('TradeValue').values,
            'change_pct': change_pct.values,
        })

        result = result.dropna(subset=['close'])
        result = result[result['close'] > 0]
        print(f"  ✅ 共 {len(result)} 檔（資料日期：{api_date}）")
        return result
    except Exception as e:
        print(f"  ❌ 失敗：{e}")
        return None


# ────────────────────────────────────────────
# 3. 三大法人（支援指定日期）
# ────────────────────────────────────────────

def fetch_today_institutional(date_str=None):
    """
    取得三大法人買賣超
    date_str: 'YYYYMMDD' 格式，None = 最新一日
    """
    label = f"（{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}）" if date_str else ""
    print(f"🏦 取得三大法人籌碼{label}...")

    if date_str:
        url = f"https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999&date={date_str}"
    else:
        url = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"

    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, timeout=30, headers=headers)
        resp.raise_for_status()
        raw = resp.json()

        if raw.get('stat') != 'OK' or not raw.get('data'):
            print("  ⚠️  此日期法人資料不可用（盤中 / 假日 / 非交易日），略過")
            return None

        rows     = raw['data']
        date_raw = raw['date']
        date_fmt = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:]}"

        records = []
        for r in rows:
            code = r[0].strip()
            if not code or not code.isdigit() or len(code) != 4:
                continue
            def to_num(s):
                return float(s.replace(',', '')) / 1000  # 股 → 張
            try:
                records.append({
                    'date':        date_fmt,
                    'code':        code,
                    'foreign_net': to_num(r[4]),
                    'trust_net':   to_num(r[10]),
                    'dealer_net':  to_num(r[11]),
                    'total_net':   to_num(r[18]),
                })
            except (ValueError, IndexError):
                continue

        result = pd.DataFrame(records)
        print(f"  ✅ {len(result)} 檔（{date_fmt}）")
        return result

    except Exception as e:
        print(f"  ⚠️  法人資料暫時無法取得（{e}），略過")
        return None


# ────────────────────────────────────────────
# 4. 回填最近 N 個交易日法人數據
# ────────────────────────────────────────────

def backfill_institutional(days=5):
    """
    往回抓最近 N 個交易日的法人數據（自動跳過假日）
    類比：補看最近幾天的法人進出場記錄
    """
    print(f"\n📅 回填最近 {days} 個交易日法人數據...")
    results = []
    check_date = datetime.now()
    found = 0
    attempts = 0

    while found < days and attempts < 20:
        attempts += 1
        check_date -= timedelta(days=1)
        date_str = check_date.strftime('%Y%m%d')

        data = fetch_today_institutional(date_str)
        if data is not None and not data.empty:
            results.append(data)
            found += 1

        time.sleep(0.5)

    if results:
        combined = pd.concat(results, ignore_index=True)
        print(f"  ✅ 共回填 {found} 個交易日，{len(combined)} 筆記錄")
        return combined

    print("  ❌ 法人回填失敗")
    return None


# ────────────────────────────────────────────
# 5. 歷史數據回填（首次執行才需要）
# ────────────────────────────────────────────

def backfill_history(codes, days=90):
    """
    使用 yfinance 一次性下載所有股票的歷史 K 線
    codes: 台股代號清單（不含 .TW）
    days: 要回填幾天的歷史
    """
    print(f"\n📚 首次執行，回填 {len(codes)} 支股票歷史數據（約 5~10 分鐘）...")
    print("   請耐心等候，之後每天只需幾秒更新\n")

    end_date   = datetime.now()
    start_date = end_date - timedelta(days=days + 30)

    symbols = [f"{c}.TW" for c in codes]
    all_data = []
    batch_size = 50

    for i in range(0, len(symbols), batch_size):
        batch_syms  = symbols[i: i + batch_size]
        batch_codes = codes[i:  i + batch_size]

        progress = f"{min(i + batch_size, len(symbols))}/{len(symbols)}"
        print(f"  下載進度：{progress} 支...", end='\r')

        try:
            raw = yf.download(
                batch_syms,
                start=start_date.strftime('%Y-%m-%d'),
                end=end_date.strftime('%Y-%m-%d'),
                progress=False,
                auto_adjust=True,
                threads=True,
            )

            if raw is None or raw.empty:
                continue

            for sym, code in zip(batch_syms, batch_codes):
                try:
                    if len(batch_syms) == 1:
                        stock = raw
                    else:
                        stock = raw.xs(sym, axis=1, level=1)

                    if stock.empty or 'Close' not in stock.columns:
                        continue

                    df = pd.DataFrame({
                        'date':   stock.index.strftime('%Y-%m-%d'),
                        'code':   code,
                        'open':   stock['Open'].values,
                        'high':   stock['High'].values,
                        'low':    stock['Low'].values,
                        'close':  stock['Close'].values,
                        'volume': stock['Volume'].values,
                        'amount': 0,
                    }).dropna(subset=['close'])

                    df = df[df['close'] > 0]
                    all_data.append(df)

                except Exception:
                    continue

        except Exception as e:
            print(f"\n  批次 {i} 錯誤：{e}")

        time.sleep(0.3)

    print()

    if all_data:
        result = pd.concat(all_data, ignore_index=True)
        print(f"  ✅ 回填完成，共 {len(result):,} 筆歷史記錄")
        return result

    print("  ❌ 回填失敗，未取得任何數據")
    return None
