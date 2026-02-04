#---------------------------------------------------------------------------
# config.py - 設定與密鑰管理
import os

# ==========================================
# 1. 判斷環境：Render 會有一個特殊的環境變數 'RENDER'
# ==========================================
IS_ON_RENDER = os.environ.get('RENDER')

# ==========================================
# 2. 設定 LINE Bot 密鑰 (雙胞胎機制)
# ==========================================
if IS_ON_RENDER:
    # --- 【環境 A：Render 正式站】(填入正式機器人的 ID) ---
    print("🚀 偵測到 Render 環境：載入 [正式] 機器人設定")
    # 這些數值請去 Render 後台 Environment Variables 設定，或者直接填在這裡(不建議)
    # 建議在 Render 後台設定 LINE_CHANNEL_ACCESS_TOKEN 與 LINE_CHANNEL_SECRET
    LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '8LdQ3zFggLWa26+NNuLQQxjoiuASEemW/uHtJ9tfP0aDDD4w+NyezV3y4+HTn37P1NBLB2W/dxXJ4uoU3oOsZDSlx31/NJIF6Ql5bESu5R3I0GrXlplW9TNWJP1tnbqL0MRTn9+3TytfTESusr+xUgdB04t89/1O/w1cDnyilFU=')
    LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', 'd066f03908b9786f1f9f85eaf918dffd')
    LIFF_ID = "2008961957-FxEVP4Fu"  # 正式站用的 LIFF (對應 Render 網址)

else:
    # --- 【環境 B：Local Ngrok 測試站】(填入測試機器人的 ID) ---
    print("💻 偵測到 Local 環境：載入 [測試] 機器人設定")
    # 這裡填入你申請給 Ngrok 測試用的那個機器人
    LINE_CHANNEL_ACCESS_TOKEN = '1UGy9WCsIAxMGS7tdLOLWzaZzS4Fi6B/rISbLo2cRWbm7Wxe62JhvOGk3+xBsCDqML7plKo5UEvCiciVGiHwj2aDgA7CbYWluhbHKm9ADiP2G4Zo3+kQVlYoNsLRGZiO21DJQiAJVaPv43EZWCoguQdB04t89/1O/w1cDnyilFU='
    LINE_CHANNEL_SECRET = 'cbe7c02fa8c61af0ad0d2d305d9ce130'
    LIFF_ID = "2009052171-mo62XjK0" # 測試用的 LIFF (對應 Ngrok 網址)

# ==========================================
# 3. 資料庫連線 (核心：共用 Render 資料庫)
# ==========================================
# 本機端：請在你的電腦設定環境變數 DATABASE_URL，值為 Render 的 "External Database URL"
# Render端：它會自動帶入 Internal Database URL
DATABASE_URL = os.environ.get('postgresql://price_king_user:Xt9yvF6vU1sbWjv1DJEaJpwkX6KwPIQa@dpg-d5tgfs8gjchc73f9fa00-a/price_king')

# Flask Session 密鑰
SECRET_KEY = os.environ.get('SECRET_KEY', 'PriceKing_Secret_Key_888')
