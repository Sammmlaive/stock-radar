"""
設定檔 - 系統參數集中管理
"""
import os
from pathlib import Path

# 路徑設定
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH  = DATA_DIR / "stocks.db"

DATA_DIR.mkdir(exist_ok=True)

# 技術指標參數
MA_SHORT        = 20   # 短期均線：類似「短線持倉均價」
MA_LONG         = 60   # 長期均線：類似「中線持倉均價」
RSI_PERIOD      = 14   # RSI 觀察週期
VOLUME_AVG_DAYS = 20   # 計算均量的天數

# 歷史數據天數（首次執行時回填）
HISTORY_DAYS = 90

# ────────────────────────────────────────────
# 調試模式（DEBUG_MODE = True 時只處理下方 50 支股票）
# 線上（CLOUD_MODE=true）自動切換成全市場模式
# ────────────────────────────────────────────
DEBUG_MODE = os.environ.get("CLOUD_MODE", "").lower() != "true"

DEBUG_STOCKS = [
    # 電子 / 半導體
    "2330", "2317", "2454", "2308", "2382",
    "2301", "3711", "2379", "2357", "2303",
    # 金融
    "2882", "2881", "2884", "2886", "2892",
    "2887", "2883", "2885", "2880", "2891",
    # 傳產 / 塑化
    "1301", "1303", "1326", "2002", "6505",
    # 民生 / 零售
    "2912", "1216", "2207", "2105", "9910",
    # 電信
    "4904", "2412", "3045",
    # 光學 / 面板
    "3008", "2408",
    # IC 設計 / 封裝
    "5274", "3034", "2327", "2395", "2474",
    # 代工 / ODM
    "3231", "4938", "6669",
    # 航運
    "2609", "2603",
    # 其他科技
    "3037", "2352", "2395", "2474", "3673",
]
# 去重（避免萬一有重複代號）
DEBUG_STOCKS = list(dict.fromkeys(DEBUG_STOCKS))[:50]

# FinMind API Token（可選，免費版每日有限額）
# 若想提升上限，至 https://finmindtrade.com 申請後填入
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
