"""
資料庫操作模組
負責建立表格、讀取、寫入 SQLite 資料庫
"""
import sqlite3
import pandas as pd
from config import DB_PATH, DEBUG_MODE, DEBUG_STOCKS


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    """初始化資料庫表格（含新欄位遷移）"""
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_list (
            code TEXT PRIMARY KEY,
            name TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_prices (
            date   TEXT,
            code   TEXT,
            open   REAL,
            high   REAL,
            low    REAL,
            close  REAL,
            volume REAL,
            amount REAL,
            PRIMARY KEY (date, code)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS institutional (
            date        TEXT,
            code        TEXT,
            foreign_net REAL,
            trust_net   REAL,
            dealer_net  REAL,
            total_net   REAL,
            PRIMARY KEY (date, code)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_scores (
            date         TEXT,
            code         TEXT,
            name         TEXT,
            close        REAL,
            change_pct   REAL,
            volume       REAL,
            vol_ratio    REAL,
            ma20         REAL,
            ma60         REAL,
            rsi          REAL,
            k            REAL,
            d            REAL,
            macd_hist    REAL,
            foreign_net  REAL,
            trust_net    REAL,
            dealer_net   REAL,
            total_net    REAL,
            foreign_3d   REAL,
            trust_3d     REAL,
            total_3d     REAL,
            foreign_5d   REAL,
            trust_5d     REAL,
            total_5d     REAL,
            score        REAL,
            category     TEXT,
            signals      TEXT,
            PRIMARY KEY (date, code)
        )
    """)

    # 遷移舊資料表：補上新欄位（若已存在則跳過）
    new_cols = [
        ("k",           "REAL"),
        ("d",           "REAL"),
        ("foreign_3d",  "REAL"),
        ("trust_3d",    "REAL"),
        ("total_3d",    "REAL"),
        ("foreign_5d",  "REAL"),
        ("trust_5d",    "REAL"),
        ("total_5d",    "REAL"),
        ("buy_signals",      "TEXT"),    # 4 種明確買進訊號
        ("week52_pos",       "REAL"),    # 52週價格位置（0%=最低，100%=最高）
        ("inst_consec",      "INTEGER"), # 法人連續買進天數
        ("signal_strength",  "TEXT"),    # 訊號強弱（強 / 普通）
    ]
    for col, dtype in new_cols:
        try:
            c.execute(f"ALTER TABLE daily_scores ADD COLUMN {col} {dtype}")
        except Exception:
            pass  # 欄位已存在，略過

    conn.commit()
    conn.close()


def save_stock_list(df):
    conn = get_connection()
    df[['code', 'name']].to_sql('stock_list', conn, if_exists='replace', index=False)
    conn.close()


def save_prices(df):
    conn = get_connection()
    for _, row in df.iterrows():
        # INSERT OR REPLACE：TWSE 官方數據優先，會覆蓋同日期的 yfinance 數據
        conn.execute("""
            INSERT OR REPLACE INTO daily_prices
            (date, code, open, high, low, close, volume, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (row['date'], row['code'],
              row.get('open'), row.get('high'), row.get('low'), row['close'],
              row.get('volume'), row.get('amount', 0)))
    conn.commit()
    conn.close()


def save_institutional(df):
    conn = get_connection()
    for _, row in df.iterrows():
        conn.execute("""
            INSERT OR IGNORE INTO institutional
            (date, code, foreign_net, trust_net, dealer_net, total_net)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (row['date'], row['code'],
              row.get('foreign_net', 0), row.get('trust_net', 0),
              row.get('dealer_net', 0), row.get('total_net', 0)))
    conn.commit()
    conn.close()


def save_scores(df):
    """儲存評分結果（覆蓋當日資料）"""
    conn = get_connection()
    cols = ['date', 'code', 'name', 'close', 'change_pct', 'volume', 'vol_ratio',
            'ma20', 'ma60', 'rsi', 'k', 'd', 'macd_hist',
            'foreign_net', 'trust_net', 'dealer_net', 'total_net',
            'foreign_3d', 'trust_3d', 'total_3d',
            'foreign_5d', 'trust_5d', 'total_5d',
            'score', 'category', 'signals', 'buy_signals',
            'week52_pos', 'inst_consec', 'signal_strength']
    for _, row in df.iterrows():
        vals = [row.get(c) for c in cols]
        conn.execute(f"""
            INSERT OR REPLACE INTO daily_scores
            ({', '.join(cols)}) VALUES ({', '.join(['?']*len(cols))})
        """, vals)
    conn.commit()
    conn.close()


def load_scores():
    """讀取最新一天的評分結果"""
    conn = get_connection()
    try:
        df = pd.read_sql("""
            SELECT * FROM daily_scores
            WHERE date = (SELECT MAX(date) FROM daily_scores)
            ORDER BY score DESC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def load_scores_history(days=30):
    """讀取最近 N 個交易日的評分歷史，供形態判斷使用"""
    conn = get_connection()
    try:
        df = pd.read_sql(f"""
            SELECT date, code, close, ma20, ma60, rsi, vol_ratio
            FROM daily_scores
            WHERE date IN (
                SELECT DISTINCT date FROM daily_scores
                ORDER BY date DESC
                LIMIT {days}
            )
            ORDER BY date ASC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def load_price_history():
    """讀取股票歷史價格，供指標計算使用
    DEBUG_MODE = True 時只讀取調試清單中的股票
    """
    conn = get_connection()
    if DEBUG_MODE and DEBUG_STOCKS:
        # 把代號清單轉成 SQL 的 IN (?,?,?) 格式
        placeholders = ','.join(['?' for _ in DEBUG_STOCKS])
        df = pd.read_sql(f"""
            SELECT dp.date, dp.code, dp.open, dp.high, dp.low,
                   dp.close, dp.volume, dp.amount, sl.name
            FROM daily_prices dp
            LEFT JOIN stock_list sl ON dp.code = sl.code
            WHERE dp.code IN ({placeholders})
            ORDER BY dp.date ASC
        """, conn, params=DEBUG_STOCKS)
    else:
        df = pd.read_sql("""
            SELECT dp.date, dp.code, dp.open, dp.high, dp.low,
                   dp.close, dp.volume, dp.amount, sl.name
            FROM daily_prices dp
            LEFT JOIN stock_list sl ON dp.code = sl.code
            ORDER BY dp.date ASC
        """, conn)
    conn.close()
    return df


def load_institutional(days=5):
    """讀取最近 N 個交易日的法人籌碼（預設 5 天）"""
    conn = get_connection()
    try:
        df = pd.read_sql(f"""
            SELECT * FROM institutional
            WHERE date IN (
                SELECT DISTINCT date FROM institutional
                ORDER BY date DESC
                LIMIT {days}
            )
            ORDER BY date ASC
        """, conn)
    except Exception:
        df = pd.DataFrame()
    conn.close()
    return df


def has_data():
    if not DB_PATH.exists():
        return False
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM daily_scores")
        count = c.fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def need_backfill():
    """少於閾值的股票有 20 天以上資料，才觸發回填
    調試模式閾值：30 支；正式模式：500 支
    """
    threshold = 30 if DEBUG_MODE else 500
    if not DB_PATH.exists():
        return True
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM (
                SELECT code FROM daily_prices
                GROUP BY code HAVING COUNT(*) >= 20
            )
        """)
        count = c.fetchone()[0]
        conn.close()
        return count < threshold
    except Exception:
        return True


def need_inst_backfill():
    """法人數據少於 3 個交易日，才觸發回填"""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(DISTINCT date) FROM institutional")
        count = c.fetchone()[0]
        conn.close()
        return count < 3
    except Exception:
        return True
