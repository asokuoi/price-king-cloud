# ==========================================
# 📦 Price King 全能搬家機器人 V3.0 (寬容版 - 解決欄位缺失)
# ==========================================
import sqlite3
import psycopg2
import os

# 1. 設定：請填入 Render 的 External Database URL (記得用 postgresql://)
# 範例: "postgresql://user:pass@host/dbname"
RENDER_DB_URL = "postgresql://price_king_user:Xt9yvF6vU1sbWjv1DJEaJpwkX6KwPIQa@dpg-d5tgfs8gjchc73f9fa00-a.singapore-postgres.render.com/price_king"

# 2. 定義要搬運資料的表
TABLES_TO_MIGRATE = [
    'admin_users',      # 管理員
    'chains',           # 通路
    'product_options',  # 選項
    'products',         # 商品
    'staff',            # 員工
    'prices'            # 價格
]

def create_schema(pg_cur):
    print("🏗️  正在建立資料表結構 (包含所有歷史欄位)...")
    
    # 1. Admin Users (補上 line_id, is_active)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id SERIAL PRIMARY KEY,
            username TEXT,
            password TEXT,
            level INTEGER DEFAULT 1,
            audit_code TEXT DEFAULT '8888',
            line_id TEXT,
            is_active INTEGER DEFAULT 1
        );
    """)

    # 2. Users (會員)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            line_id TEXT PRIMARY KEY,
            display_name TEXT,
            picture_url TEXT,
            status INTEGER DEFAULT 1,
            tags TEXT DEFAULT '',
            points INTEGER DEFAULT 0,
            platform_os TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 3. Chains (通路)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS chains (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            logo_url TEXT,
            status INTEGER DEFAULT 1
        );
    """)

    # 4. Product Options (選項)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS product_options (
            id SERIAL PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL
        );
    """)

    # 5. Products (商品 - 補上 volume, is_common, description...)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            spec TEXT,
            material TEXT,
            category TEXT,
            keywords TEXT,
            image_url TEXT,
            priority INTEGER DEFAULT 0,
            status INTEGER DEFAULT 1,
            capacity REAL DEFAULT 0,
            unit TEXT DEFAULT '',
            cp_score REAL DEFAULT 0,
            local_score REAL DEFAULT 0,
            volume INTEGER DEFAULT 0,        -- 舊欄位補齊
            is_common INTEGER DEFAULT 1,     -- 舊欄位補齊
            description TEXT DEFAULT ''      -- 舊欄位補齊
        );
    """)

    # 6. Prices (價格 - 補上 promo_tag, promo_mode)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id SERIAL PRIMARY KEY,
            product_id INTEGER,
            chain_id INTEGER,
            price REAL,
            base_price REAL,
            promo_type INTEGER DEFAULT 1,
            promo_qty INTEGER DEFAULT 1,
            promo_val REAL DEFAULT 0,
            promo_label TEXT,
            promo_tag TEXT,                  -- 舊欄位補齊
            promo_mode TEXT,                 -- 舊欄位補齊
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by_line_id TEXT
        );
    """)

    # 7. Staff (員工 - 補上 username, password, role)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            line_id TEXT PRIMARY KEY,
            name TEXT,
            wallet INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            chain_id INTEGER DEFAULT -1,
            status INTEGER DEFAULT 1,
            username TEXT,                   -- 舊欄位補齊
            password TEXT,                   -- 舊欄位補齊
            role TEXT,                       -- 舊欄位補齊
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 8. Logs (日誌類)
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS price_logs (
            id SERIAL PRIMARY KEY,
            staff_line_id TEXT,
            chain_id INTEGER,
            product_id INTEGER,
            new_price INTEGER,
            base_price INTEGER,
            promo_type INTEGER,
            promo_qty INTEGER,
            promo_val REAL,
            promo_label TEXT,
            promo_tag TEXT,
            promo_mode TEXT,
            gps_lat REAL,
            gps_lng REAL,
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_paid INTEGER DEFAULT 0,
            status INTEGER DEFAULT 1
        );
    """)

    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS search_logs (
            id SERIAL PRIMARY KEY,
            line_id TEXT,
            keyword TEXT,
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS payouts (
            id SERIAL PRIMARY KEY,
            staff_line_id TEXT,
            amount INTEGER,
            admin_username TEXT,
            payout_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    print("✅ 資料表結構建立完成！(V3.0 寬容版)")

def migrate():
    print("🚀 開始全能搬家程序 (V3.0)...")
    
    try:
        local_conn = sqlite3.connect('database.db')
        local_conn.row_factory = sqlite3.Row
        local_cur = local_conn.cursor()
    except Exception as e:
        print(f"❌ 本機資料庫讀取失敗: {e}")
        return

    # 移除 postgres:// 檢查，避免誤判
    try:
        pg_conn = psycopg2.connect(RENDER_DB_URL)
        pg_cur = pg_conn.cursor()
    except Exception as e:
        print(f"❌ Render 連線失敗: {e}")
        return

    # 1. 重建表格
    try:
        # 先刪除舊表以確保結構更新 (Cascade 會連同資料一起刪)
        print("🗑️  正在清除舊資料表以確保結構正確...")
        tables_to_drop = ['price_logs', 'search_logs', 'payouts', 'prices', 'products', 'staff', 'admin_users', 'users', 'chains', 'product_options']
        for t in tables_to_drop:
            pg_cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")
        
        create_schema(pg_cur)
        pg_conn.commit()
    except Exception as e:
        pg_conn.rollback()
        print(f"❌ 建表失敗: {e}")
        return

    # 2. 搬運資料
    for table in TABLES_TO_MIGRATE:
        print(f"   正在搬運資料表: {table} ...", end="")
        
        try:
            local_cur.execute(f"SELECT * FROM {table}")
            rows = local_cur.fetchall()
            
            if not rows:
                print(" (空資料，跳過)")
                continue

            # 取得本機欄位名稱
            columns = rows[0].keys()
            col_names = ",".join(columns)
            placeholders = ",".join(["%s"] * len(columns))
            
            # 使用最單純的 INSERT，因為表結構現在已經完全對齊了
            sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"
            
            data_to_insert = [tuple(row) for row in rows]
            pg_cur.executemany(sql, data_to_insert)
            pg_conn.commit() 
            print(f" ✅ 成功寫入 {len(rows)} 筆")

        except Exception as e:
            pg_conn.rollback()
            print(f" ❌ 失敗: {e}")

    local_conn.close()
    pg_conn.close()
    print("\n🎉 搬家大成功！Render 資料庫已就緒。")

if __name__ == "__main__":
    create_confirm = input("⚠️  這將會覆蓋 Render 資料庫，確定嗎？ (yes/no): ")
    if create_confirm.lower() == "yes":
        migrate()
    else:
        print("已取消")
