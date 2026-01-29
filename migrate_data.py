# ==========================================
# 📦 Price King 資料庫搬家機器人 (SQLite -> PostgreSQL)
# ==========================================
# 用途：將本機的精華資料 (商品/通路/設定) 搬到 Render，並過濾掉測試日誌。
# ==========================================

import sqlite3
import psycopg2
import os
from urllib.parse import urlparse

# 1. 設定：請填入 Render 給您的 External Database URL
# (之後我們會從 Render 後台取得這串網址)
RENDER_DB_URL = "postgres://..."  # 暫時留空，等一下填

# 2. 定義要搬運的「精華資料表」 (不包含 logs)
TABLES_TO_MIGRATE = [
    'admin_users',      # 管理員
    'chains',           # 通路
    'product_options',  # 選項設定
    'products',         # 商品資料
    'staff',            # 員工資料
    'prices'            # 當前價格
]

def migrate():
    if "postgres://" not in RENDER_DB_URL:
        print("❌ 錯誤：請先設定 RENDER_DB_URL (PostgreSQL 連線網址)")
        return

    print("🚀 開始資料搬運...")
    
    # 連線本機 SQLite
    local_conn = sqlite3.connect('database.db')
    local_conn.row_factory = sqlite3.Row
    local_cur = local_conn.cursor()

    # 連線雲端 PostgreSQL
    try:
        pg_conn = psycopg2.connect(RENDER_DB_URL)
        pg_cur = pg_conn.cursor()
    except Exception as e:
        print(f"❌ 無法連線到 Render 資料庫: {e}")
        return

    for table in TABLES_TO_MIGRATE:
        print(f"   正在處理資料表: {table} ...", end="")
        
        # 1. 讀取本機資料
        try:
            local_cur.execute(f"SELECT * FROM {table}")
            rows = local_cur.fetchall()
            
            if not rows:
                print(" (空資料表，跳過)")
                continue

            # 2. 清空雲端資料表 (確保不會重複)
            # 注意：這裡會先清空雲端對應的表，確保是乾淨的覆蓋
            pg_cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
            
            # 3. 準備插入語法
            columns = rows[0].keys()
            col_names = ",".join(columns)
            placeholders = ",".join(["%s"] * len(columns)) # Postgres 用 %s
            
            sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
            
            # 4. 批次寫入
            data_to_insert = [tuple(row) for row in rows]
            pg_cur.executemany(sql, data_to_insert)
            
            print(f" ✅ 成功搬運 {len(rows)} 筆資料")

        except Exception as e:
            print(f" ❌ 失敗: {e}")

    # 提交變更
    pg_conn.commit()
    
    # 關閉連線
    local_conn.close()
    pg_conn.close()
    print("\n🎉 搬家完成！現在 Render 上的資料庫已經準備好了。")

if __name__ == "__main__":
    # 防呆確認
    confirm = input("⚠️  這將會覆蓋 Render 資料庫的現有資料，確定要執行嗎？ (yes/no): ")
    if confirm.lower() == "yes":
        migrate()
    else:
        print("已取消")
