# database.py - 專門處理資料庫連線與查詢
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import config # 匯入設定檔

# 🔥 新增：讓 SQLite 也能聽懂 %s 的魔法工具
class SQLiteCursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params=None):
        # 把 %s 換成 ?，這樣 SQLite 就看得懂了
        if params is not None:
            sql = sql.replace('%s', '?')
            return self.cursor.execute(sql, params)
        return self.cursor.execute(sql)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()
    
    def close(self):
        self.cursor.close()

    @property
    def rowcount(self):
        return self.cursor.rowcount
    
    @property
    def lastrowid(self):
        return self.cursor.lastrowid

class SQLiteConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn
        self.row_factory = conn.row_factory

    def cursor(self):
        return SQLiteCursorWrapper(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db_connection():
    if config.DATABASE_URL:
        # Render 環境 (PostgreSQL) - 原生支援 %s，不用動
        conn = psycopg2.connect(config.DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    else:
        # 本機測試環境 (SQLite)
        import sqlite3
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        DB_PATH = os.path.join(BASE_DIR, "database.db")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        
        # 🔥 回傳我們加工過的「翻譯機」連線
        return SQLiteConnectionWrapper(conn)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 基礎人員與商品表
    cur.execute("CREATE TABLE IF NOT EXISTS staff (line_id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT, name TEXT, role TEXT DEFAULT 'staff', chain_id INTEGER DEFAULT -1, wallet INTEGER DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT, spec TEXT, image_url TEXT, volume INTEGER DEFAULT 330, material TEXT DEFAULT 'can', is_common INTEGER DEFAULT 1)")
    cur.execute("CREATE TABLE IF NOT EXISTS chains (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    
    # 2. 最新價格表 (Snapshot)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT, chain_id INTEGER, product_id INTEGER, price INTEGER, 
            promo_tag TEXT, promo_qty INTEGER DEFAULT 1, promo_mode TEXT DEFAULT 'none', promo_val INTEGER DEFAULT 0,
            updated_by_line_id TEXT, update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            UNIQUE(chain_id, product_id)
        )
    """)

    # 3. 交易紀錄表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS price_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            staff_line_id TEXT, 
            chain_id INTEGER, 
            product_id INTEGER, 
            new_price INTEGER, 
            gps_lat REAL, 
            gps_lng REAL,
            promo_tag TEXT,
            promo_qty INTEGER,
            promo_mode TEXT,
            promo_val INTEGER,
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("CREATE TABLE IF NOT EXISTS payouts (id INTEGER PRIMARY KEY AUTOINCREMENT, staff_line_id TEXT, amount INTEGER, admin_username TEXT, payout_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    # 預設資料檢查
    # 注意：在 SQLite Wrapper 下，SELECT COUNT(*) 回傳的是 Row 物件，需要用 index [0] 或 key ['count']
    # 為了簡化，我們直接 fetchone() 然後判斷
    
    # 檢查 chains
    cur.execute("SELECT COUNT(*) as c FROM chains")
    row = cur.fetchone()
    c_val = row['c'] if row else 0
    
    if c_val == 0:
        cur.execute("INSERT INTO chains (name) VALUES ('全聯'), ('7-11'), ('家樂福'), ('美廉社');")

    # 檢查 staff
    cur.execute("SELECT COUNT(*) as c FROM staff WHERE username = 'admin'")
    row = cur.fetchone()
    s_val = row['c'] if row else 0

    if s_val == 0:
         # ⚠️ 請記得確認這裡的 ID
         cur.execute("INSERT INTO staff (line_id, username, password, name, role, chain_id, wallet) VALUES ('U_YOUR_REAL_ID_HERE', 'admin', '888', '超級管理員', 'admin', -1, 1000)")

    conn.commit()
    cur.close()
    conn.close()
    print("✅ 資料庫初始化完成 (database.py)")

if __name__ == "__main__":
    init_db()
