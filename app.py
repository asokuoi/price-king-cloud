# ==========================================
# 🏆 PRICE KING 價格王 - V89.0 雲端 PostgreSQL 專用版
# ------------------------------------------
# 1. 核心邏輯：與 V88 完全一致
# 2. 資料庫層：全面修正為 PostgreSQL 語法 (%s 與 時間函數)
# 3. 修復重點：解決 Internal Server Error 與 Syntax Error
# ==========================================
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import psycopg2
from psycopg2.extras import DictCursor
import os
from dotenv import load_dotenv

# ==========================================
# 🛠️ 環境變數載入設定 (強制讀取版)
# ==========================================
basedir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(basedir, '.env')

if os.path.exists(env_path):
    # 🔥 重點修正：加上 override=True，強制以 .env 檔案內容為準
    load_dotenv(env_path, override=True)
    print(f"✅ [Local Dev] 已強制載入 .env 設定: {env_path}")
else:
    print(f"⚠️ [Production] 未找到 .env，將使用系統環境變數 (Render)")

import json
from datetime import datetime, timedelta
from urllib.parse import quote, unquote
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    FlexSendMessage, FollowEvent, PostbackEvent
)
import config

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', config.SECRET_KEY)

# ==========================================
# 🤖 LINE Bot 設定
# ==========================================
channel_access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', config.LINE_CHANNEL_ACCESS_TOKEN)
channel_secret = os.environ.get('LINE_CHANNEL_SECRET', config.LINE_CHANNEL_SECRET)

line_bot_api = LineBotApi(channel_access_token)
handler = WebhookHandler(channel_secret)
# ==========================================
# 🗄️ 資料庫連線 Helper (補在這裡！)
# ==========================================
def get_db():
    """建立 PostgreSQL 連線 (支援 Render 格式修正)"""
    db_url = os.environ.get('DATABASE_URL')
    
    # Render 的 postgres:// 需要轉為 postgresql:// 才能給 SQLAlchemy/psycopg2 用
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    conn = psycopg2.connect(db_url, cursor_factory=DictCursor)
    return conn

# 輔助：轉型防呆
def to_float(val, default=0.0):
    try: return float(val)
    except: return default

def to_int(val, default=0):
    try: return int(val)
    except: return default

# 👇 這裡會直接告訴你真相
print("---------------- 系統啟動檢查 ----------------")
print(f"🔑 Secret 前5碼: {channel_secret[:5] if channel_secret else 'None'}")
print(f"📱 目前 LIFF ID: {os.environ.get('LIFF_ID', getattr(config, 'LIFF_ID', '⚠️ 未設定'))}")
print("---------------------------------------------")

# ... (後面接 get_db 函式)

# ----------------------------------------------------
# 💓 心跳檢測站 (防止 Render 休眠用)
# ----------------------------------------------------
@app.route('/keep_alive')
def keep_alive():
    # 這個接口不做任何資料庫操作，只回傳一個簡單文字
    # 絕對不會寫入 search_logs，完全無痕！
    return "I am awake!", 200    

# ==========================================
# 🌐 基礎路由
# ==========================================

# 🛡️ 強制允許 GPS 權限
@app.after_request
def add_header(response):
    # 允許 geolocation
    response.headers['Permissions-Policy'] = 'geolocation=(self "https://price-king-cloud.onrender.com")'
    return response

@app.route('/')
def index():
    # 1. 處理 LIFF 登入後的跳轉 (liff.state)
    liff_state = request.args.get('liff.state')
    if liff_state:
        # 解碼目標路徑
        target_path = unquote(liff_state)
        # 防止惡意跳轉，只允許站內路徑
        if target_path.startswith('/'):
            return redirect(target_path)
    
    # 2. 如果沒有指定跳轉，預設去搜尋頁
    # ⚠️ 請確認你的搜尋頁函式名稱！如果是 def search(): 這裡就要寫 'search'
    # ⚠️ 如果是 def consumer_search(): 這裡就寫 'consumer_search'
    try:
        return redirect(url_for('search')) 
    except:
        # 萬一名字打錯，直接硬導向網址 '/search' (保命符)
        return redirect('/search')

@app.route('/admin')
def admin_root(): return redirect(url_for('admin_login'))

# ==========================================
# 🤖 LINE Webhook (含迎賓邏輯)
# ==========================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try: handler.handle(body, signature)
    except InvalidSignatureError: return 'Invalid signature', 400
    return 'OK'

# 🔥 新增：監聽「加入好友」事件
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    profile = None
    try:
        profile = line_bot_api.get_profile(user_id)
    except: pass

    display_name = profile.display_name if profile else "新朋友"
    picture_url = profile.picture_url if profile else ""

    # 1. 會員建檔 (Insert or Update)
    conn = get_db(); cur = conn.cursor()
    try:
        # ✅ FIX: SQLite 'datetime' -> Postgres 'CURRENT_TIMESTAMP'
        # ✅ FIX: ? -> %s
        cur.execute("""
            INSERT INTO users (line_id, display_name, picture_url, status, join_date, last_active)
            VALUES (%s, %s, %s, 1, CURRENT_TIMESTAMP + interval '8 hours', CURRENT_TIMESTAMP + interval '8 hours')
            ON CONFLICT(line_id) DO UPDATE SET
            display_name = excluded.display_name,
            picture_url = excluded.picture_url,
            status = 1,
            last_active = CURRENT_TIMESTAMP + interval '8 hours'
        """, (user_id, display_name, picture_url))
        conn.commit()
    except Exception as e:
        print(f"User Save Error: {e}")
    finally:
        conn.close()

    # 2. 發送方案 A 迎賓卡片
    search_url = f"https://liff.line.me/{config.LIFF_ID}/search"
    
    welcome_flex = {
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png",
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "歡迎來到 Price King 👑", "weight": "bold", "size": "xl", "color": "#1DB446"},
                {"type": "text", "text": f"嗨！{display_name}", "size": "lg", "weight": "bold", "margin": "md"},
                {"type": "text", "text": "我是您的全網比價助手。\n輸入商品名稱，我將為您搜尋 7-11、全聯、好市多等通路的即時價格，幫您找出最划算的選擇！", "wrap": True, "color": "#666666", "margin": "md", "size": "sm"}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "action": {"type": "uri", "label": "🛒 進入比價大廳", "uri": search_url},
                    "color": "#0d6efd"
                },
                {
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {"type": "message", "label": "📖 使用教學", "text": "教學"}
                }
            ],
            "flex": 0
        }
    }
    line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="歡迎加入價格王", contents=welcome_flex))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_line_id = event.source.user_id 
    
    conn = get_db(); cur = conn.cursor()
    # 更新使用者最後活躍時間
    try: 
        # ✅ FIX: ? -> %s, datetime -> CURRENT_TIMESTAMP
        cur.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP + interval '8 hours' WHERE line_id = %s", (user_line_id,))
        conn.commit()
    except: pass
    
    try:
        cur.execute("SELECT audit_code FROM admin_users WHERE username = 'admin'")
        res = cur.fetchone()
        # DictCursor 讓這裡可以用 dict(res) 或者直接 res['audit_code']
        global_audit_code = str(res['audit_code']).strip() if res else "8888"
    except: global_audit_code = "8888"
    conn.close()

    if msg == global_audit_code:
        liff_url = f"https://liff.line.me/{config.LIFF_ID}/audit"
        flex_msg = {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": "🔐 驗證通過", "weight": "bold", "size": "xl", "color": "#1DB446"},
                {"type": "text", "text": f"ID: {user_line_id}", "size": "xs", "color": "#aaaaaa", "wrap": True, "margin": "md"},
                {"type": "text", "text": "請截圖 ID 供店長開通權限", "size": "xxs", "color": "#ff5555"}
            ]},
            "footer": {"type": "box", "layout": "vertical", "contents": [
                {"type": "button", "action": {"type": "uri", "label": "🚀 進入盤點系統", "uri": liff_url}, "style": "primary", "color": "#1DB446"}
            ]}
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text="驗證通過", contents=flex_msg))
    elif msg in ["查", "盤點", "系統"]:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🔒 請輸入盤點通關密碼"))
    elif msg == "教學":
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📝 【使用教學】\n\n1. 直接輸入商品名稱 (例如：百威) 即可搜尋全網價格。\n2. 點擊「進入比價大廳」可瀏覽各通路分類。\n3. 在單店頁面中，點擊「導航」可前往最近店家。"))
    else:
        # ✅ FIX: 在網址後方補上 &line_id=...，讓後端能抓到是誰搜尋的
        search_url = f"https://liff.line.me/{config.LIFF_ID}/search?keyword={quote(msg)}&line_id={user_line_id}"
        
        flex_msg = {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"🔍 搜尋：{msg}", "weight": "bold", "size": "lg"},
                {"type": "text", "text": "點擊下方按鈕比價", "size": "xs", "color": "#aaaaaa"}
            ]},
            "footer": {"type": "box", "layout": "vertical", "contents": [
                {"type": "button", "action": {"type": "uri", "label": "🛒 全網比價", "uri": search_url}, "style": "primary"}
            ]}
        }
        line_bot_api.reply_message(event.reply_token, FlexSendMessage(alt_text=f"搜尋 {msg}", contents=flex_msg))

# ==========================================
# ⚡ 前端盤點 API
# ==========================================
@app.route('/audit')
def audit_page():
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM chains WHERE status = 1")
    chains = [dict(r) for r in cur.fetchall()]
# 🔥 修改重點：加入 material，且排序改為：分類 -> 檔名(品牌) -> ID
    cur.execute("SELECT id, name, category, spec, material FROM products WHERE status = 1 ORDER BY category, name, id")
    products = [dict(r) for r in cur.fetchall()]
    
    cur.execute("SELECT chain_id, product_id, price, base_price, promo_label FROM prices")
    price_map = {}
    for r in cur.fetchall():
        key = f"{r['chain_id']}-{r['product_id']}"
        price_map[key] = {
            'price': int(r['price']),
            'base_price': int(r['base_price']),
            'label': r['promo_label']
        }
    conn.close()
    return render_template('audit.html', chains=chains, products=products, price_map=price_map, liff_id=config.LIFF_ID)

@app.route('/api/staff/check', methods=['POST'])
def api_staff_check():
    line_id = request.json.get('line_id')
    if not line_id: return jsonify({'status': 'error'})
    conn = get_db(); cur = conn.cursor()
    # ✅ FIX: ? -> %s
    cur.execute("SELECT level, chain_id, name, status, wallet FROM staff WHERE line_id = %s", (line_id,))
    res = cur.fetchone()
    conn.close()
    
    if res:
        r = dict(res)
        if r.get('status', 1) == 0: return jsonify({'status': 'banned', 'name': r['name']})
        return jsonify({'status': 'success', 'level': r['level'], 'chain_id': r['chain_id'], 'name': r['name'], 'wallet': r['wallet']})
    else: return jsonify({'status': 'unregistered'})
from datetime import datetime, timedelta  # 務必確認檔頭有引入這兩個

@app.route('/api/price/update', methods=['POST'])
def api_price_update():
    d = request.json
    # 0. 基礎檢查
    if not all([d.get('product_id'), d.get('chain_id'), d.get('line_id')]): 
        return jsonify({'status':'error', 'msg': '資料不全'}), 400
    
    conn = get_db(); cur = conn.cursor()
    try:
        # 1. 驗證員工
        cur.execute("SELECT status, name, wallet, level FROM staff WHERE line_id = %s", (d['line_id'],))
        staff_res = cur.fetchone()
        if not staff_res: return jsonify({'status': 'error', 'msg': '未授權用戶'})
        staff = dict(staff_res)
        if staff.get('status', 1) == 0: return jsonify({'status': 'error', 'msg': '帳號已停權'})
        
        # 2. 處理數值
        final_price = to_float(d.get('price'))
        base_price = to_float(d.get('base_price'))
        pt = to_int(d.get('promo_type'), 1)
        pq = to_int(d.get('promo_qty'), 1)
        if pq < 1: pq = 1
        pv = to_float(d.get('promo_val'), 0)
        
        if base_price <= 0: base_price = final_price 
        if final_price <= 0: final_price = base_price 

        promo_label = ""
        if pt == 2: promo_label = f"{pq}件${int(pv)}"
        elif pt == 3: promo_label = f"{pq}件{int(pv)}折"
        elif pt == 4: promo_label = f"買{pq}送{int(pv)}"
        elif pt == 5: promo_label = f"第{pq}件${int(pv)}"
        elif pt == 6: promo_label = f"第{pq}件{int(pv/10) if pv%10==0 else int(pv)}折"

        # ==============================================================================
        # 3. 🔥 邏輯升級：自動作廢今日舊紀錄 + 獎金判斷
        # ==============================================================================
        
        # A. 算出今天起始時間 (UTC)
        now_utc = datetime.utcnow()
        now_tw = now_utc + timedelta(hours=8)
        today_start_tw = now_tw.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_tw - timedelta(hours=8)
        
        # B. 搜尋「今天」已存在的紀錄
        check_sql = """
            SELECT id FROM price_logs 
            WHERE staff_line_id = %s AND product_id = %s AND chain_id = %s
            AND log_time >= %s AND status = 1
        """
        cur.execute(check_sql, (d['line_id'], d['product_id'], d['chain_id'], today_start_utc))
        prev_logs = cur.fetchall()
        
        should_pay = False
        if not prev_logs:
            # 沒查到 -> 今天第一筆 -> 發錢
            should_pay = True
            is_paid_val = 1
        else:
            # 查到了 -> 今天已經有紀錄
            should_pay = False
            is_paid_val = 0
            
            # 🔥 關鍵動作：把今天之前的幾筆 (就算是剛剛打的) 全部作廢 (status=0)
            # 這樣戰情室就只會看到最新的一筆是「有效」的，不會有一堆 $0 的待核銷
            for log in prev_logs:
                cur.execute("UPDATE price_logs SET status = 0 WHERE id = %s", (log['id'],))

        # 4. 更新 prices 主表 (UTC)
        cur.execute("SELECT id FROM prices WHERE product_id=%s AND chain_id=%s", (d['product_id'], d['chain_id']))
        row = cur.fetchone()
        
        if row:
            sql = """UPDATE prices SET 
                     price=%s, base_price=%s, promo_type=%s, promo_qty=%s, promo_val=%s, promo_label=%s, 
                     update_time=CURRENT_TIMESTAMP, updated_by_line_id=%s 
                     WHERE id=%s"""
            cur.execute(sql, (final_price, base_price, pt, pq, pv, promo_label, d['line_id'], row['id']))
        else:
            sql = """INSERT INTO prices 
                     (product_id, chain_id, price, base_price, promo_type, promo_qty, promo_val, promo_label, update_time, updated_by_line_id) 
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s)"""
            cur.execute(sql, (d['product_id'], d['chain_id'], final_price, base_price, pt, pq, pv, promo_label, d['line_id']))
        
        # 5. 寫入 Log (UTC) - 這筆新的 status 預設是 1 (有效)
        cur.execute("""INSERT INTO price_logs 
                       (staff_line_id, product_id, chain_id, new_price, base_price, promo_type, promo_qty, promo_val, promo_label, log_time, is_paid, status) 
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP,%s, 1)""", 
                       (d['line_id'], d['product_id'], d['chain_id'], final_price, base_price, pt, pq, pv, promo_label, is_paid_val))
        
        # 6. 發放獎金
        if should_pay:
            cur.execute("UPDATE staff SET wallet = wallet + 5 WHERE line_id = %s", (d['line_id'],))
        
        conn.commit()
        return jsonify({'status':'success', 'label': promo_label, 'bonus': 5 if should_pay else 0})
        
    except Exception as e: 
        conn.rollback()
        return jsonify({'status':'error', 'msg':str(e)}), 500
    finally: conn.close()


# ==========================================
# 🛒 消費者搜尋 V3.5 (分組冠軍 + 液態單位修正)
# ==========================================
@app.route('/search')
def consumer_search():
    keyword = request.args.get('keyword', '').strip()
    mode = request.args.get('mode', '') 
    target_chain_id = request.args.get('chain_id')
    target_category = request.args.get('category')
    pin_product_id = request.args.get('pin_id')
    
    # V89.7: 接收定位與身分
    lat = request.args.get('lat', '')
    lng = request.args.get('lng', '')
    user_line_id = request.args.get('line_id', '')

    conn = get_db(); cur = conn.cursor()
    products_list = []
    
    # 1. 流量紀錄 (寫入台灣時間)
    if keyword:
        try: 
            cur.execute("""
                INSERT INTO search_logs (keyword, line_id, lat, lng, log_time) 
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP + interval '8 hours')
            """, (keyword, user_line_id, lat, lng))
            conn.commit()
        except: pass

    # 2. 準備大廳資料 (沒搜尋時顯示)
    lobby_data = {'categories': [], 'chains': []}
    if not keyword and not mode:
        try:
            cur.execute("SELECT DISTINCT category FROM products WHERE status = 1 ORDER BY category")
            for r in cur.fetchall(): lobby_data['categories'].append({"name": dict(r)['category'], "icon": "📦"})
            cur.execute("SELECT id, name, logo_url FROM chains WHERE status = 1 ORDER BY id")
            for r in cur.fetchall(): lobby_data['chains'].append({"id": dict(r)['id'], "name": dict(r)['name'], "logo_url": dict(r)['logo_url'], "icon": "🏪"})
        except: pass
        conn.close()
        return render_template('search.html', products_data="[]", lobby_data=lobby_data, search_keyword="", search_mode="", liff_id=os.environ.get('LIFF_ID', config.LIFF_ID), pin_id="")

    # 3. 撈產品基礎資料
    cols = "id, name, spec, material, category, keywords, priority, image_url, capacity, unit"
    if mode == 'store_shelf' and target_chain_id:
        if target_category: cur.execute(f"SELECT {cols} FROM products WHERE status = 1 AND category = %s ORDER BY priority DESC, id", (target_category,))
        else: cur.execute(f"SELECT {cols} FROM products WHERE status = 1 ORDER BY category, priority DESC, id")
    else:
        cur.execute(f"SELECT {cols} FROM products WHERE status = 1 ORDER BY priority DESC, category, id")
    products_rows = cur.fetchall()
    
    # 4. 歷史低價 (30天內最低)
    history_low_map = {}
    try:
        cur.execute("SELECT product_id, MIN(new_price) as min_price FROM price_logs WHERE log_time >= CURRENT_TIMESTAMP - interval '30 days' AND status = 1 GROUP BY product_id")
        for r in cur.fetchall(): history_low_map[r['product_id']] = float(r['min_price'])
    except: pass

    # 5. 撈目前架上價格
    sql_prices = """
        SELECT p.product_id, p.price, p.base_price, p.promo_label, p.update_time, 
               c.name as chain_name, c.id as chain_id, c.logo_url as chain_logo 
        FROM prices p 
        LEFT JOIN chains c ON p.chain_id = c.id 
        LEFT JOIN products prod ON p.product_id = prod.id 
        WHERE c.status = 1 AND prod.status = 1 AND p.price > 0
    """
    cur.execute(sql_prices + " ORDER BY p.price ASC")
    prices_rows = cur.fetchall()
    
    # 6. 資料組裝
    products_map = {p['id']: dict(p) for p in products_rows}
    # 初始化
    for pid in products_map:
        products_map[pid].update({'prices': [], 'cp_score': 999999.0, 'local_score': 999999.0, 'selling_at': [], 'cp_display': ''})

    for row in prices_rows:
        d = dict(row)
        pid = d['product_id']
        if pid in products_map:
            p = products_map[pid]
            price = float(d['price'])
            cap = to_float(p.get('capacity'), 0)
            unit = str(p.get('unit', '')).strip()
            
            # CP值計算 (每1單位價格，用於排序)
            score = (price / cap) if cap > 0 and price > 0 else price
            
            # cp_display (顯示用，自動轉 100ml)
            cp_disp = ""
            if cap > 0 and price > 0:
                # 判斷液體/重量單位 (不分大小寫)
                high_vol_units = ['ml', 'g', 'cc', 'cm']
                if unit.lower() in high_vol_units:
                    val_100 = (price / cap) * 100
                    cp_disp = f"${round(val_100, 1)}/100{unit}"
                else:
                    cp_disp = f"${round(score, 1)}/{unit}"

            # 更新全域 CP 霸主
            if score < p['cp_score']: 
                p['cp_score'] = score
                p['cp_display'] = cp_disp 
            
            # 更新店內 CP 分數
            is_target_store = (str(d['chain_id']) == str(target_chain_id)) if target_chain_id else False
            if is_target_store:
                if score < p['local_score']: p['local_score'] = score

            # 時間
            time_str = ""
            if d['update_time']:
                try:
                    db_time = d['update_time']
                    if isinstance(db_time, str): db_time = datetime.strptime(db_time.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    time_str = db_time.strftime("%m/%d")
                except: pass

            hist_min = history_low_map.get(pid, 999999)
            is_hist_low = (price <= hist_min) and (price > 0)

            p['prices'].append({
                'chain_id': d['chain_id'],
                'chain_name': d['chain_name'],
                'chain_logo': d.get('chain_logo'),
                'price': int(price),
                'base_price': int(d.get('base_price', 0)),
                'promo_label': d.get('promo_label', ''),
                'cp_val': cp_disp, 
                'time_ago': time_str,
                'is_target_store': is_target_store,
                'is_hist_low': is_hist_low
            })
            p['selling_at'].append(d['chain_name'])

    # 7. 排序與關鍵字過濾
    raw_list = list(products_map.values())
    
    # 搜尋邏輯
    if keyword:
        kws = keyword.lower().split()
        filtered_list = []
        for p in raw_list:
            search_text = (
                f"{p['name']} {p['material'] or ''} {p['category']} "
                f"{p.get('keywords') or ''} {' '.join(p['selling_at'])}"
            ).lower()
            if all(k in search_text for k in kws):
                filtered_list.append(p)
        raw_list = filtered_list
    
    # 預設排序
    def get_sort_key(p):
        is_pinned = (str(p['id']) == str(pin_product_id)) if pin_product_id else False
        return (0 if is_pinned else 1, p['cp_score'])

    target_chain_info = {} # 用於傳遞給前端顯示 Store Header
    
    if mode == 'store_shelf' and target_chain_id:
        # 撈出該通路的資訊 (Logo, Name)
        try:
            cur.execute("SELECT id, name, logo_url FROM chains WHERE id = %s", (target_chain_id,))
            chain_res = cur.fetchone()
            if chain_res: target_chain_info = dict(chain_res)
        except: pass

        final_list = []
        for p in raw_list:
            if any(pr['is_target_store'] for pr in p['prices']):
                final_list.append(p)
        
        # 店內模式排序：置頂 -> 分類 -> 本店分數
        products_list = sorted(final_list, key=lambda x: (
            0 if str(x['id']) == str(pin_product_id) else 1, 
            x['category'], 
            x['local_score']
        ))
    else:
        # 一般模式排序：置頂 -> 全域分數
        products_list = sorted([p for p in raw_list if len(p['prices']) > 0], key=get_sort_key)
    
    # 價格內排序
    for p in products_list:
        p['prices'].sort(key=lambda x: x['price'])

    conn.close()
    
    # 🔥 注意：這裡新增傳入 target_chain_info 供前端使用
    return render_template('search.html', 
                           products_data=json.dumps(products_list), 
                           lobby_data=lobby_data, 
                           search_keyword=keyword, 
                           search_mode=mode, 
                           liff_id=os.environ.get('LIFF_ID', config.LIFF_ID), 
                           pin_id=pin_product_id,
                           target_chain_info=json.dumps(target_chain_info))
# ==========================================
# 👑 後台管理
# ==========================================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        conn = get_db(); cur = conn.cursor()
        # ✅ FIX: ? -> %s
        cur.execute("SELECT * FROM admin_users WHERE username = %s", (request.form['username'],))
        acc = cur.fetchone()
        conn.close()
        if acc and dict(acc)['password'] == request.form['password']:
            session['admin_logged_in'] = True; return redirect(url_for('admin_dashboard'))
        flash('❌ 登入失敗')
    return render_template('admin/login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    data = {}
    
    # 1. 基礎數據統計
    try: 
        # ✅ FIX: SQLite date() -> Postgres DATE(...)
        cur.execute("SELECT COUNT(*) FROM search_logs WHERE DATE(log_time + interval '8 hours') = DATE(CURRENT_TIMESTAMP + interval '8 hours')")
        data['today_search'] = cur.fetchone()[0]
    except: data['today_search'] = 0
    
    try: cur.execute("SELECT COUNT(*) FROM products WHERE status = 1"); data['product_count'] = cur.fetchone()[0]
    except: data['product_count'] = 0
    try: cur.execute("SELECT COUNT(*) FROM chains WHERE status = 1"); data['store_count'] = cur.fetchone()[0]
    except: data['store_count'] = 0
    try: cur.execute("SELECT COUNT(*) FROM staff WHERE status = 1"); data['staff_count'] = cur.fetchone()[0]
    except: data['staff_count'] = 0
    
    # 2. 異常抓鬼 (轉換時間格式)
    abnormal_query = """
        SELECT s.name as staff_name, p.name as product_name, c.name as chain_name, COUNT(*) as cnt 
        FROM price_logs l
        JOIN staff s ON l.staff_line_id = s.line_id
        JOIN products p ON l.product_id = p.id
        JOIN chains c ON l.chain_id = c.id
        WHERE DATE(l.log_time + interval '8 hours') = DATE(CURRENT_TIMESTAMP + interval '8 hours')
        GROUP BY l.staff_line_id, l.product_id, s.name, p.name, c.name
        HAVING COUNT(*) >= 2
        ORDER BY cnt DESC LIMIT 10
    """
    try:
        cur.execute(abnormal_query)
        # ✅ FIX: 這裡雖然沒有時間欄位要顯示，但保持習慣轉 dict
        abnormal_list = [dict(r) for r in cur.fetchall()]
    except Exception as e: 
        print(e)
        abnormal_list = []

    # 3. 最近搜尋 (🔴 這裡是關鍵報錯點！)
    try:
        cur.execute("SELECT keyword, log_time FROM search_logs ORDER BY log_time DESC LIMIT 10")
        raw_searches = cur.fetchall()
        recent_searches = []
        for r in raw_searches:
            d = dict(r)
            # ✅ FIX: 強制把 datetime 物件轉成字串，讓 HTML 的 .split() 可以運作
            if d['log_time']:
                d['log_time'] = str(d['log_time']) 
            recent_searches.append(d)
    except: recent_searches = []

    conn.close()
    return render_template('admin/dashboard.html', data=data, abnormal_list=abnormal_list, recent_searches=recent_searches)

#---------戰情勾稽是加強版202621

# ==========================================
# ⚡ 戰情室 API：取得單一商品歷史紀錄 (給 Modal 用)
# ==========================================
@app.route('/admin/api/history')
def admin_api_history():
    if not is_admin_logged_in(): return jsonify({'error': 'Unauthorized'}), 403
    
    chain_id = request.args.get('chain_id')
    product_id = request.args.get('product_id')
    
    if not chain_id or not product_id:
        return jsonify({'error': 'Missing parameters'}), 400
        
    conn = get_db(); cur = conn.cursor()
    try:
        # 🔥 修改點：拿掉 l.status = 1，顯示所有歷史
        sql = """
            SELECT l.new_price, l.log_time, l.promo_label, l.status, s.name as staff_name
            FROM price_logs l
            LEFT JOIN staff s ON l.staff_line_id = s.line_id
            WHERE l.chain_id = %s AND l.product_id = %s 
            ORDER BY l.log_time DESC
            LIMIT 20
        """
        cur.execute(sql, (chain_id, product_id))
        rows = [dict(r) for r in cur.fetchall()]
        
        history = []
        for i, row in enumerate(rows):
            # A. 時間處理 (UTC -> 台灣時間)
            db_time = row['log_time']
            if isinstance(db_time, str):
                try: db_time = datetime.strptime(db_time.split('.')[0], "%Y-%m-%d %H:%M:%S")
                except: db_time = datetime.now()
            
            tw_time = db_time + timedelta(hours=8)
            
            # B. 漲跌幅
            diff_display = "-"
            if i < len(rows) - 1:
                prev_price = rows[i+1]['new_price']
                curr_price = row['new_price']
                # 只有當前後價格真的不同時才算漲跌
                if prev_price > 0 and curr_price != prev_price:
                    diff = curr_price - prev_price
                    pct = round((diff / prev_price) * 100, 1)
                    if diff > 0: diff_display = f"🔺 +{pct}%"
                    else: diff_display = f"🔻 {pct}%"
            
            # C. 狀態標示 (如果是作廢的紀錄，加個標記)
            status_text = ""
            if row['status'] == 0:
                status_text = "(已作廢)"
            
            history.append({
                'date': tw_time.strftime('%Y/%m/%d'),
                'time': tw_time.strftime('%H:%M'),
                'staff': row['staff_name'] or '未知',
                'price': row['new_price'],
                'promo': row['promo_label'] or '',
                'diff': diff_display,
                'status': row['status'],     # 傳回狀態給前端判斷顏色
                'status_text': status_text
            })
            
        return jsonify({'status': 'success', 'data': history})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
    finally:
        conn.close()

# ==========================================
# ⚡ 戰情勾稽室 (V2.1 歷史回朔版)
# ==========================================
@app.route('/admin/audit')
def admin_audit_review():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    
    # query_date 是您選的「台灣日期」
    query_date = request.args.get('query_date', datetime.now().strftime('%Y-%m-%d'))
    filter_chain = request.args.get('chain_id', '')
    filter_staff = request.args.get('staff_id', '')
    
    conn = get_db(); cur = conn.cursor()

    # 下拉選單
    chains = []; staffs = []
    try:
        cur.execute("SELECT id, name FROM chains ORDER BY id"); chains = cur.fetchall()
        cur.execute("SELECT line_id, name FROM staff ORDER BY name"); staffs = cur.fetchall()
    except: pass

    # 🔥 核心查詢：
    # 1. WHERE: 把 UTC 轉成台灣時間來比對日期 (確保查到的是台灣的今天)
    # 2. Subquery: 找上一筆時，直接比對 UTC 時間即可 (log_time < l.log_time)
    sql = """
        SELECT 
            l.id, l.staff_line_id, l.chain_id, l.product_id,
            l.new_price, l.log_time, l.status, l.promo_label,
            s.name as staff_name, 
            c.name as chain_name, 
            p.name as product_name, p.spec, p.material,
            
            -- 子查詢：找上一筆時間 (UTC)
            (SELECT log_time FROM price_logs l2 
             WHERE l2.chain_id = l.chain_id AND l2.product_id = l.product_id AND l2.log_time < l.log_time 
             ORDER BY l2.log_time DESC LIMIT 1) as prev_time_db,
             
            -- 子查詢：找上一筆價格
            (SELECT new_price FROM price_logs l3 
             WHERE l3.chain_id = l.chain_id AND l3.product_id = l.product_id AND l3.log_time < l.log_time 
             ORDER BY l3.log_time DESC LIMIT 1) as prev_price_db

        FROM price_logs l
        LEFT JOIN staff s ON l.staff_line_id = s.line_id
        LEFT JOIN chains c ON l.chain_id = c.id
        LEFT JOIN products p ON l.product_id = p.id
        -- 這裡最關鍵：把 log_time (UTC) 轉成 台灣時間 (+8) 再取 DATE
        WHERE DATE(l.log_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Taipei') = %s
    """
    params = [query_date]

    if filter_chain: sql += " AND l.chain_id = %s"; params.append(filter_chain)
    if filter_staff: sql += " AND l.staff_line_id = %s"; params.append(filter_staff)

    sql += " ORDER BY l.log_time DESC"

    processed_logs = []
    try:
        cur.execute(sql, tuple(params))
        for r in cur.fetchall():
            log = dict(r)
            
            # A. 顯示時間處理：UTC -> 台灣時間 (+8)
            db_time = log['log_time']
            if isinstance(db_time, str):
                try: db_time = datetime.strptime(db_time.split('.')[0], "%Y-%m-%d %H:%M:%S")
                except: db_time = datetime.now()
            
            tw_time = db_time + timedelta(hours=8)
            log['display_time'] = tw_time.strftime('%H:%M') # 介面顯示用
            
            # B. 計算間隔 (全部用原始 UTC 來算秒數差，這樣最準)
            if log['prev_time_db']:
                prev_time = log['prev_time_db']
                if isinstance(prev_time, str):
                    try: prev_time = datetime.strptime(prev_time.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    except: prev_time = db_time
                
                # 直接相減 (UTC - UTC)
                diff_seconds = (db_time - prev_time).total_seconds()
                log['gap_mins'] = int(diff_seconds / 60)
                log['gap_days'] = round(diff_seconds / 86400, 1)
                
                # 價格變動
                prev_price = log['prev_price_db']
                if prev_price and prev_price > 0:
                    diff = log['new_price'] - prev_price
                    log['diff_pct'] = round(((log['new_price'] - prev_price) / prev_price) * 100, 1)
                    log['prev_price_display'] = prev_price
                else:
                    log['diff_pct'] = 0
                    log['prev_price_display'] = log['new_price']
            else:
                log['gap_mins'] = None
                log['gap_days'] = 999
                log['diff_pct'] = 0
                log['prev_price_display'] = None

            processed_logs.append(log)

    except Exception as e:
        print(f"❌ SQL Audit Error: {e}")
        conn.close()
        return f"System Error: {e}"

    conn.close()

    return render_template('admin/audit_review.html', 
                           logs=processed_logs, 
                           current_date=query_date,
                           chains=chains, staffs=staffs,
                           sel_chain=filter_chain, sel_staff=filter_staff)


@app.route('/admin/audit/toggle', methods=['POST'])
def admin_audit_toggle():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    log_id = request.form['log_id']
    date_val = request.form['return_date']
    conn = get_db(); cur = conn.cursor()
    # ✅ FIX: ? -> %s
    cur.execute("SELECT staff_line_id, status FROM price_logs WHERE id = %s", (log_id,))
    log = cur.fetchone()
    if log and log['status'] == 1:
        staff_id = log['staff_line_id']
        # ✅ FIX: ? -> %s
        cur.execute("UPDATE staff SET wallet = wallet - 5 WHERE line_id = %s AND wallet >= 5", (staff_id,))
        cur.execute("UPDATE price_logs SET status = 0 WHERE id = %s", (log_id,))
        conn.commit()
        flash('🚫 紀錄已作廢，獎金已回收')
    conn.close()
    return redirect(url_for('admin_audit_review', query_date=date_val))

# 🔥 員工管理 (V87.1: 三指標 + 核銷邏輯)
@app.route('/admin/staff')
def admin_staff():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT s.*, c.name as chain_name FROM staff s LEFT JOIN chains c ON s.chain_id = c.id ORDER BY s.line_id ASC")
    staff_list = []
    for row in cur.fetchall():
        s = dict(row)
        # ✅ FIX: ? -> %s
        cur.execute("SELECT COUNT(*) FROM price_logs WHERE staff_line_id = %s", (s['line_id'],))
        s['total_logs'] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM price_logs WHERE staff_line_id = %s AND status = 1", (s['line_id'],))
        s['valid_logs'] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM price_logs WHERE staff_line_id = %s AND status = 1 AND COALESCE(is_paid, 0) = 0", (s['line_id'],))
        s['unpaid_logs'] = cur.fetchone()[0]
        s['calc_wallet'] = s.get('wallet', 0)
        if s.get('status') is None: s['status'] = 1
        staff_list.append(s)
    cur.execute("SELECT * FROM chains WHERE status = 1")
    chains = [dict(r) for r in cur.fetchall()]
    conn.close(); return render_template('admin/staff.html', staff_list=staff_list, chains=chains)

@app.route('/admin/staff/add', methods=['POST'])
def admin_staff_add():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    try: 
        # ✅ FIX: ? -> %s
        cur.execute("INSERT INTO staff (line_id, name, wallet, level, chain_id, status) VALUES (%s, %s, 0, %s, %s, 1)", 
                    (request.form['line_id'], request.form['name'], request.form['level'], request.form['chain_id']))
        conn.commit(); flash('✅ 新增成功')
    except: flash('❌ 失敗')
    conn.close(); return redirect(url_for('admin_staff'))

@app.route('/admin/staff/edit', methods=['POST'])
def admin_staff_edit():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    
    conn = get_db()
    cur = conn.cursor()
    
    original_line_id = request.form['original_line_id'] 
    new_line_id = request.form['new_line_id']           
    
    try:
        # 1. 如果 ID 有變更，先檢查新 ID 是否已被使用
        if original_line_id != new_line_id:
            # ✅ FIX: ? -> %s
            cur.execute("SELECT 1 FROM staff WHERE line_id = %s", (new_line_id,))
            if cur.fetchone():
                flash(f'❌ 修改失敗：新 ID {new_line_id} 已經有其他員工使用了')
                return redirect(url_for('admin_staff'))

        # 2. 更新員工資料 (含 ID)
        # ✅ FIX: ? -> %s
        cur.execute("""
            UPDATE staff 
            SET line_id=%s, name=%s, level=%s, chain_id=%s, status=%s 
            WHERE line_id=%s
        """, (
            new_line_id, 
            request.form['name'], 
            request.form['level'], 
            request.form['chain_id'], 
            request.form['status'], 
            original_line_id
        ))
        
        # 3. 🔥 關鍵：連動更新歷史紀錄
        if original_line_id != new_line_id:
            # ✅ FIX: ? -> %s
            cur.execute("UPDATE price_logs SET staff_line_id = %s WHERE staff_line_id = %s", (new_line_id, original_line_id))
            cur.execute("UPDATE search_logs SET line_id = %s WHERE line_id = %s", (new_line_id, original_line_id))

        conn.commit()
        flash(f'✅ 員工 {request.form["name"]} 資料更新成功')
        
    except Exception as e:
        conn.rollback()
        flash(f'❌ 更新失敗: {str(e)}')
    finally:
        conn.close()
        
    return redirect(url_for('admin_staff'))

@app.route('/admin/staff/payout', methods=['POST'])
def admin_staff_payout():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor(); line_id = request.form['line_id']
    # ✅ FIX: ? -> %s
    cur.execute("UPDATE price_logs SET is_paid = 1 WHERE staff_line_id = %s AND status = 1 AND COALESCE(is_paid, 0) = 0", (line_id,))
    cur.execute("UPDATE staff SET wallet = 0 WHERE line_id = %s", (line_id,)); conn.commit(); conn.close(); flash('✅ 核銷完成')
    return redirect(url_for('admin_staff'))

@app.route('/admin/staff/delete', methods=['POST'])
def admin_staff_delete():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor(); 
    # ✅ FIX: ? -> %s
    cur.execute("DELETE FROM staff WHERE line_id = %s", (request.form['line_id'],)); conn.commit(); conn.close(); flash('🗑️ 刪除成功')
    return redirect(url_for('admin_staff'))

# ==========================================
# ⚙️ 設定 (V89.1: 詳細除錯版)
# ==========================================
@app.route('/admin/settings', methods=['GET', 'POST'])
def admin_settings():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    
    if request.method == 'POST':
        try:
            pwd = request.form.get('password')
            code = request.form.get('audit_code')
            
            if pwd: 
                cur.execute("UPDATE admin_users SET password=%s, audit_code=%s WHERE username='admin'", (pwd, code))
            else: 
                cur.execute("UPDATE admin_users SET audit_code=%s WHERE username='admin'", (code,))
            
            conn.commit()
            flash('✅ 設定已更新')
        except Exception as e:
            conn.rollback()
            print(f"❌ Settings Update Error: {e}")
            flash(f'❌ 更新失敗: {str(e)}')
        finally:
            conn.close()
        return redirect(url_for('admin_settings'))

    # GET 請求：讀取資料
    try:
        cur.execute("SELECT * FROM admin_users WHERE username = 'admin'")
        res = cur.fetchone()
        admin_data = dict(res) if res else {'audit_code': '8888'}
        
        cur.execute("SELECT * FROM chains ORDER BY id")
        chains = [dict(r) for r in cur.fetchall()]
        
        cur.execute("SELECT * FROM product_options ORDER BY kind, name")
        options = {'category': [], 'spec': [], 'material': [], 'unit': []}
        for r in cur.fetchall():
            d = dict(r)
            if d['kind'] in options: options[d['kind']].append(d)
            
    except Exception as e:
        print(f"❌ Load Settings Error: {e}")
        flash(f'❌ 資料讀取異常: {str(e)}')
        admin_data = {'audit_code': 'Error'}
        chains = []
        options = {'category': [], 'spec': [], 'material': [], 'unit': []}
    finally:
        if conn: conn.close()

    return render_template('admin/settings.html', admin_data=admin_data, chains=chains, options=options)

@app.route('/admin/settings/toggle_chain', methods=['POST'])
def admin_toggle_chain():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    cid = request.form.get('chain_id')
    curr = request.form.get('current_status')
    new_s = 0 if str(curr) == '1' else 1
    
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("UPDATE chains SET status = %s WHERE id = %s", (new_s, cid))
        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f'❌ 切換失敗: {str(e)}')
    finally:
        conn.close()
    return redirect(url_for('admin_settings'))

@app.route('/admin/settings/add_chain', methods=['POST'])
def admin_add_chain():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    name = request.form.get('name')
    logo = request.form.get('logo_url')
    
    conn = get_db(); cur = conn.cursor()
    try: 
        cur.execute("INSERT INTO chains (name, logo_url, status) VALUES (%s, %s, 1)", (name, logo))
        conn.commit()
        flash(f'✅ 已新增通路: {name}')
    except Exception as e: 
        conn.rollback()
        flash(f'❌ 新增失敗: {str(e)}')
    finally:
        conn.close()
    return redirect(url_for('admin_settings'))

@app.route('/admin/settings/edit_chain', methods=['POST'])
def admin_edit_chain():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    cid = request.form.get('chain_id')
    name = request.form.get('name')
    logo = request.form.get('logo_url')
    
    conn = get_db(); cur = conn.cursor()
    try: 
        cur.execute("UPDATE chains SET name=%s, logo_url=%s WHERE id=%s", (name, logo, cid))
        conn.commit()
        flash(f'✅ 通路更新成功')
    except Exception as e: 
        conn.rollback()
        flash(f'❌ 更新失敗: {str(e)}')
    finally:
        conn.close()
    return redirect(url_for('admin_settings'))

@app.route('/admin/settings/add_option', methods=['POST'])
def admin_settings_add_option():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    kind = request.form.get('kind')
    name = request.form.get('name')
    
    conn = get_db(); cur = conn.cursor()
    try: 
        # Debug 訊息：看看後端到底收到了什麼
        print(f"Attempting to add option: kind={kind}, name={name}")
        
        cur.execute("INSERT INTO product_options (kind, name) VALUES (%s, %s)", (kind, name))
        conn.commit()
        flash(f'✅ 已新增 {name}')
    except Exception as e:
        conn.rollback()
        print(f"❌ Add Option Error: {e}") # 關鍵！這行會把錯誤印在 Logs 裡
        flash(f'❌ 新增失敗: {str(e)}')   # 這行會把錯誤顯示在網頁上
    finally:
        conn.close()
    return redirect(url_for('admin_settings'))

@app.route('/admin/settings/delete_option', methods=['POST'])
def admin_settings_delete_option():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    oid = request.form.get('id')
    kind = request.form.get('kind')
    name = request.form.get('name')
    
    conn = get_db(); cur = conn.cursor()
    try:
        # 先檢查是否被使用
        if kind in ['category', 'spec', 'material', 'unit']:
            # 注意：這裡假設 products 表有這些欄位名稱，如果沒有會報錯
            cur.execute(f"SELECT COUNT(*) FROM products WHERE {kind} = %s", (name,))
            count = cur.fetchone()[0]
            if count > 0: 
                flash(f'🚫 無法刪除：尚有 {count} 個商品使用此選項')
                return redirect(url_for('admin_settings'))
        
        cur.execute("DELETE FROM product_options WHERE id = %s", (oid,))
        conn.commit()
        flash(f'🗑️ 已刪除 {name}')
    except Exception as e:
        conn.rollback()
        flash(f'❌ 刪除失敗: {str(e)}')
    finally:
        conn.close()
    return redirect(url_for('admin_settings'))

@app.route('/admin/products')
def admin_products():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor(); cur.execute("SELECT * FROM products ORDER BY id DESC"); products = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM product_options ORDER BY kind, name"); options = {'category': [], 'spec': [], 'material': [], 'unit': []}
    for r in cur.fetchall():
        d = dict(r)
        if d['kind'] in options: options[d['kind']].append(d)
    conn.close(); return render_template('admin/products.html', products=products, options=options)

# ----------------------------------------------------
# 🛍️ 商品管理：新增商品 (V89.6 修正版：防呆與轉型)
# ----------------------------------------------------
@app.route('/admin/products/add', methods=['POST'])
def admin_products_add():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    
    # 1. 接收並清洗資料
    name = request.form.get('name')
    spec = request.form.get('spec')
    material = request.form.get('material')
    category = request.form.get('category')
    keywords = request.form.get('keywords')
    unit = request.form.get('unit')
    
    # ⚠️ 關鍵修正：處理數字欄位的空白問題
    # 如果 capacity 是空字串，直接塞給 SQL 會導致 "Invalid input syntax" 錯誤
    cap_raw = request.form.get('capacity')
    try:
        # 如果有值就轉成 float，沒值或是怪怪的符號就給 0
        capacity = float(cap_raw) if cap_raw and cap_raw.strip() else 0
    except:
        capacity = 0
        
    conn = get_db(); cur = conn.cursor()
    try:
        # 2. 執行寫入 
        # (補上 status=1 預設上架, priority=0 預設排序，避免資料庫因欄位缺失報錯)
        cur.execute("""
            INSERT INTO products (name, spec, material, category, keywords, capacity, unit, status, priority) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 0)
        """, (name, spec, material, category, keywords, capacity, unit))
        conn.commit()
    except Exception as e:
        print(f"Insert Error: {e}") # 在 Log 印出錯誤，避免完全瞎掉
        conn.rollback()
    finally:
        conn.close()

    return redirect(url_for('admin_products'))

@app.route('/admin/products/edit', methods=['POST'])
def admin_products_edit():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor(); 
    # ✅ FIX: ? -> %s
    cur.execute("UPDATE products SET name=%s, spec=%s, material=%s, category=%s, keywords=%s, capacity=%s, unit=%s WHERE id=%s", 
                (request.form.get('name'), request.form.get('spec'), request.form.get('material'), request.form.get('category'), request.form.get('keywords'), request.form.get('capacity'), request.form.get('unit'), request.form.get('product_id')))
    conn.commit(); conn.close(); return redirect(url_for('admin_products'))

@app.route('/admin/products/delete', methods=['POST'])
def admin_products_delete():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor(); 
    # ✅ FIX: ? -> %s
    cur.execute("DELETE FROM products WHERE id = %s", (request.form.get('product_id'),)); conn.commit(); conn.close(); return redirect(url_for('admin_products'))

@app.route('/admin/products/toggle', methods=['POST'])
def admin_products_toggle():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    curr = request.form.get('current_status'); new_s = 0 if str(curr) == '1' else 1; conn = get_db(); cur = conn.cursor(); 
    # ✅ FIX: ? -> %s
    cur.execute("UPDATE products SET status = %s WHERE id = %s", (new_s, request.form.get('product_id'))); conn.commit(); conn.close(); return redirect(url_for('admin_products'))

@app.route('/admin/analysis/dead_stock')
def admin_dead_stock():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor()
    # ✅ FIX: SQLite date('now', '-30 days') -> Postgres CURRENT_DATE - interval '30 days'
    try: cur.execute("SELECT p.id, p.name, p.category, MAX(pr.update_time) as last_update FROM products p LEFT JOIN prices pr ON p.id = pr.product_id GROUP BY p.id HAVING last_update < CURRENT_DATE - interval '30 days' OR last_update IS NULL ORDER BY last_update ASC"); products = [dict(r) for r in cur.fetchall()]
    except: products = []
    conn.close(); return render_template('admin/analysis.html', products=products, title="滯銷分析")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
