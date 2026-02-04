# config.py - 專門存放設定與密鑰
import os

# ==========================================
# ⚠️ 請在此填入您的 4 組 LINE 密鑰 & LIFF ID
# ==========================================
STAFF_ACCESS_TOKEN = '8LdQ3zFggLWa26+NNuLQQxjoiuASEemW/uHtJ9tfP0aDDD4w+NyezV3y4+HTn37P1NBLB2W/dxXJ4uoU3oOsZDSlx31/NJIF6Ql5bESu5R3I0GrXlplW9TNWJP1tnbqL0MRTn9+3TytfTESusr+xUgdB04t89/1O/w1cDnyilFU='
STAFF_SECRET = 'd066f03908b9786f1f9f85eaf918dffd'

USER_ACCESS_TOKEN = '8V8RgT1ww0BtDEkAdIkRUm3CqDPahofze5/5I378+vh2/uGeYQgTyCrDKinfnH+qPrOhRce9d0+XxfR/UxVBKRw3bK5UYcacRsMVjxBVi1PRDJ9U07v8lNYtfEn0dDJ+jzUwX7zA33z2UKT1BYFqFQdB04t89/1O/w1cDnyilFU='
USER_SECRET = '403d119e2d4ee07d3ad5f55c8575cc6a'

LIFF_ID = "2008961957-FxEVP4Fu" 
# ==========================================

# 資料庫設定 (優先讀取 Render 環境變數，沒有則用本機 SQLite)
DATABASE_URL = os.environ.get('DATABASE_URL')

# Flask Session 密鑰
SECRET_KEY = 'SUPER_SECRET_KEY_FOR_SESSION'

#---------------------------
# config.py

# Flask 加密金鑰 (隨便打一串亂碼即可)
SECRET_KEY = 'your_super_secret_random_key_here'

# LINE Bot 設定 (請填入您 LINE Developers 的真實資料)
LINE_CHANNEL_ACCESS_TOKEN = '8LdQ3zFggLWa26+NNuLQQxjoiuASEemW/uHtJ9tfP0aDDD4w+NyezV3y4+HTn37P1NBLB2W/dxXJ4uoU3oOsZDSlx31/NJIF6Ql5bESu5R3I0GrXlplW9TNWJP1tnbqL0MRTn9+3TytfTESusr+xUgdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = 'd066f03908b9786f1f9f85eaf918dffd'

