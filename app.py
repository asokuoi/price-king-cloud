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
import json
from datetime import datetime, timedelta
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, FollowEvent
from urllib.parse import quote, unquote
# 注意：這裡雖然 import 了 database 和 sqlite3，但在雲端主要依賴 psycopg2
import config

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', config.SECRET_KEY) # 優先讀取環境變數

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', config.LINE_CHANNEL_ACCESS_TOKEN))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET', config.LINE_CHANNEL_SECRET))

def get_db():
    # ✅ FIX: 確保使用 PostgreSQL 連線，並使用 DictCursor 讓操作像 SQLite 一樣方便
    db_url = os.environ.get('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    conn = psycopg2.connect(db_url, cursor_factory=DictCursor)
    return conn

def is_admin_logged_in(): return session.get('admin_logged_in')

# 輔助：轉型防呆
def to_float(val, default=0.0):
    try: return float(val)
    except: return default

def to_int(val, default=0):
    try: return int(val)
    except: return default

# ==========================================
# 🌐 基礎路由
# ==========================================
@app.route('/')
def index():
    liff_state = request.args.get('liff.state')
    if liff_state:
        target_path = unquote(liff_state)
        if target_path.startswith('/'):
            return redirect(target_path)
    return redirect(url_for('consumer_search'))

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
        search_url = f"https://liff.line.me/{config.LIFF_ID}/search?keyword={quote(msg)}"
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
    cur.execute("SELECT id, name, category, spec FROM products WHERE status = 1 ORDER BY category, id")
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

@app.route('/api/price/update', methods=['POST'])
def api_price_update():
    d = request.json
    if not all([d.get('product_id'), d.get('chain_id'), d.get('line_id')]): 
        return jsonify({'status':'error', 'msg': '資料不全'}), 400
    
    conn = get_db(); cur = conn.cursor()
    try:
        # ✅ FIX: ? -> %s
        cur.execute("SELECT status, name, wallet, level FROM staff WHERE line_id = %s", (d['line_id'],))
        staff_res = cur.fetchone()
        if not staff_res: return jsonify({'status': 'error', 'msg': '未授權用戶'})
        staff = dict(staff_res)
        if staff.get('status', 1) == 0: return jsonify({'status': 'error', 'msg': '帳號已停權'})
        current_level = staff.get('level', 1)

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

        # ✅ FIX: ? -> %s, date() -> DATE(.. AT TIME ZONE)
        # PostgreSQL 的 date() 比較嚴格，這裡用日期比對
        cur.execute("""
            SELECT id, staff_line_id FROM price_logs 
            WHERE product_id=%s AND chain_id=%s AND status=1 
            AND DATE(log_time + interval '8 hours') = DATE(CURRENT_TIMESTAMP + interval '8 hours')
        """, (d['product_id'], d['chain_id']))
        prev_log = cur.fetchone()

        if prev_log:
            prev_log_id = prev_log['id']
            prev_staff_id = prev_log['staff_line_id']
            # ✅ FIX: ? -> %s
            cur.execute("SELECT level FROM staff WHERE line_id=%s", (prev_staff_id,))
            prev_staff_res = cur.fetchone()
            prev_level = prev_staff_res['level'] if prev_staff_res else 0

            if current_level >= prev_level:
                # ✅ FIX: ? -> %s
                cur.execute("UPDATE price_logs SET status=0 WHERE id=%s", (prev_log_id,))
                cur.execute("UPDATE staff SET wallet = wallet - 5 WHERE line_id=%s AND wallet >= 5", (prev_staff_id,))
                
        # ✅ FIX: ? -> %s
        cur.execute("SELECT id FROM prices WHERE product_id=%s AND chain_id=%s", (d['product_id'], d['chain_id']))
        row = cur.fetchone()
        
        if row:
            # ✅ FIX: ? -> %s, datetime -> CURRENT_TIMESTAMP
            sql = """UPDATE prices SET 
                     price=%s, base_price=%s, promo_type=%s, promo_qty=%s, promo_val=%s, promo_label=%s, 
                     update_time=CURRENT_TIMESTAMP + interval '8 hours', updated_by_line_id=%s 
                     WHERE id=%s"""
            cur.execute(sql, (final_price, base_price, pt, pq, pv, promo_label, d['line_id'], row['id']))
        else:
            # ✅ FIX: ? -> %s, datetime -> CURRENT_TIMESTAMP
            sql = """INSERT INTO prices 
                     (product_id, chain_id, price, base_price, promo_type, promo_qty, promo_val, promo_label, update_time, updated_by_line_id) 
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP + interval '8 hours',%s)"""
            cur.execute(sql, (d['product_id'], d['chain_id'], final_price, base_price, pt, pq, pv, promo_label, d['line_id']))
        
        # ✅ FIX: ? -> %s, datetime -> CURRENT_TIMESTAMP
        cur.execute("""INSERT INTO price_logs 
                       (staff_line_id, product_id, chain_id, new_price, base_price, promo_type, promo_qty, promo_val, promo_label, log_time, is_paid, status) 
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP + interval '8 hours',0, 1)""", 
                       (d['line_id'], d['product_id'], d['chain_id'], final_price, base_price, pt, pq, pv, promo_label))
        
        # ✅ FIX: ? -> %s
        cur.execute("UPDATE staff SET wallet = wallet + 5 WHERE line_id = %s", (d['line_id'],))
        conn.commit()
        return jsonify({'status':'success', 'label': promo_label})
    except Exception as e: return jsonify({'status':'error', 'msg':str(e)}), 500
    finally: conn.close()
# ----------------------------------------------------
# 🛒 消費者搜尋 (V89.2: 恢復 GPS 與 ID 紀錄)
# ----------------------------------------------------
@app.route('/search')
def consumer_search():
    keyword = request.args.get('keyword', '').strip()
    mode = request.args.get('mode', '') 
    target_chain_id = request.args.get('chain_id')
    target_category = request.args.get('category')
    pin_product_id = request.args.get('pin_id')
    
    # 🆕 新增：接收經緯度與 User ID
    lat = request.args.get('lat', '')
    lng = request.args.get('lng', '')
    user_line_id = request.args.get('line_id', '')

    conn = get_db(); cur = conn.cursor()
    products_list = []
    
    # 流量清洗與紀錄 (V89.2: 完整記錄人事時地物)
    if keyword and len(keyword) > 0:
        try: 
            # ✅ FIX: 寫入 keyword, lat, lng, line_id
            # 注意：這裡假設資料庫已有 lat, lng 欄位 (您剛確認過有了)
            cur.execute("""
                INSERT INTO search_logs (keyword, line_id, lat, lng, log_time) 
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP + interval '8 hours')
            """, (keyword, user_line_id, lat, lng))
            conn.commit()
        except Exception as e: 
            print(f"Log Error: {e}") # 偷印錯誤避免當機

    # 1. 智慧分類鎖定
    if pin_product_id and not target_category:
        try:
            cur.execute("SELECT category FROM products WHERE id = %s", (pin_product_id,))
            res = cur.fetchone()
            if res: target_category = dict(res)['category']
        except: pass

    # 2. 大廳資料
    lobby_data = {'categories': [], 'chains': []}
    if not keyword and not mode:
        try:
            cur.execute("SELECT DISTINCT category FROM products WHERE status = 1 ORDER BY category")
            for r in cur.fetchall(): lobby_data['categories'].append({"name": dict(r)['category'], "icon": "📦"})
            cur.execute("SELECT id, name, logo_url FROM chains WHERE status = 1 ORDER BY id")
            for r in cur.fetchall(): lobby_data['chains'].append({"id": dict(r)['id'], "name": dict(r)['name'], "logo_url": dict(r)['logo_url'], "icon": "🏪"})
        except: pass
        conn.close()
        return render_template('search.html', products_data="[]", lobby_data=lobby_data, search_keyword="", search_mode="", liff_id=config.LIFF_ID, pin_id="")

    # 3. 撈產品
    cols = "id, name, spec, material, category, keywords, priority, image_url, capacity, unit"
    if mode == 'store_shelf' and target_chain_id:
        if target_category: cur.execute(f"SELECT {cols} FROM products WHERE status = 1 AND category = %s ORDER BY priority DESC, id", (target_category,))
        else: cur.execute(f"SELECT {cols} FROM products WHERE status = 1 ORDER BY category, priority DESC, id")
    else:
        cur.execute(f"SELECT {cols} FROM products WHERE status = 1 ORDER BY priority DESC, category, id")
    products_rows = cur.fetchall()
    
    # 4. 撈價格
    sql_prices = """
        SELECT p.product_id, p.price, p.base_price, p.promo_label, p.update_time, 
               c.name as chain_name, c.id as chain_id, c.logo_url as chain_logo 
        FROM prices p 
        LEFT JOIN chains c ON p.chain_id = c.id 
        LEFT JOIN products prod ON p.product_id = prod.id 
        WHERE c.status = 1 AND prod.status = 1
    """
    cur.execute(sql_prices + " ORDER BY p.price ASC")
    prices_rows = cur.fetchall()
    
    # 5. 資料組裝
    products_map = {p['id']: dict(p) for p in products_rows}
    for pid in products_map:
        products_map[pid].update({'prices': [], 'cp_score': 999999.0, 'local_score': 999999.0, 'selling_at': []})

    for row in prices_rows:
        d = dict(row)
        pid = d['product_id']
        if pid in products_map:
            p = products_map[pid]
            price = float(d['price'])
            cap = to_float(p.get('capacity'), 0)
            
            score = (price / cap) if cap > 0 and price > 0 else price
            if score < p['cp_score']: p['cp_score'] = score
            
            is_target_store = (str(d['chain_id']) == str(target_chain_id)) if target_chain_id else False
            if is_target_store:
                if score < p['local_score']: p['local_score'] = score

            unit = p.get('unit', '')
            cp_str = ""
            if cap > 0 and price > 0:
                high_vol = ['ml', 'g', 'cc', 'cm']
                val = (price/cap)*100 if unit in high_vol else (price/cap)
                suffix = f"100{unit}" if unit in high_vol else unit
                cp_str = f"(${round(val, 1)}/{suffix})"
            
            time_str = ""
            if d['update_time']:
                try:
                    dt = datetime.strptime(str(d['update_time']).split('.')[0], "%Y-%m-%d %H:%M:%S")
                    diff = datetime.now() - dt
                    if diff.days == 0: time_str = "剛剛" if diff.seconds < 3600 else f"{diff.seconds // 3600}小時前"
                    elif diff.days == 1: time_str = "昨天"
                    else: time_str = dt.strftime("%m/%d")
                except: pass

            p['prices'].append({
                'chain_id': d['chain_id'],
                'chain_name': d['chain_name'],
                'chain_logo': d.get('chain_logo'),
                'price': int(price),
                'base_price': int(d.get('base_price', 0)),
                'promo_label': d.get('promo_label', ''),
                'cp_val': cp_str,
                'time_ago': time_str,
                'is_target_store': is_target_store
            })
            p['selling_at'].append(d['chain_name'])

    # 6. 排序與過濾
    raw_list = list(products_map.values())
    if keyword:
        kws = keyword.lower().split()
        raw_list = [p for p in raw_list if all(k in (p['name'] + str(p['material']) + str(p['category']) + str(p.get('keywords','')) + ' '.join(p['selling_at'])).lower() for k in kws)]
    
    def get_sort_key(p):
        is_pinned = (str(p['id']) == str(pin_product_id)) if pin_product_id else False
        return (0 if is_pinned else 1, p['cp_score'])

    if mode == 'store_shelf' and target_chain_id:
        final_list = []
        for p in raw_list:
            if any(pr['is_target_store'] for pr in p['prices']):
                final_list.append(p)
        products_list = sorted(final_list, key=lambda x: (
            0 if str(x['id']) == str(pin_product_id) else 1, 
            x['category'], 
            x['local_score']
        ))
    else:
        products_list = sorted([p for p in raw_list if len(p['prices']) > 0], key=get_sort_key)
    
    for p in products_list:
        p['prices'].sort(key=lambda x: x['price'])

    conn.close()
    return render_template('search.html', products_data=json.dumps(products_list), lobby_data=lobby_data, search_keyword=keyword, search_mode=mode, liff_id=config.LIFF_ID, pin_id=pin_product_id)

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

@app.route('/admin/audit')
def admin_audit_review():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    query_date = request.args.get('query_date', datetime.now().strftime('%Y-%m-%d'))
    conn = get_db(); cur = conn.cursor()
    # ✅ FIX: ? -> %s, date() -> DATE(...)
    query = """
        SELECT l.id, l.staff_line_id, l.new_price, l.log_time, l.status, l.is_paid, l.promo_label,
               s.name as staff_name, c.name as chain_name, p.name as product_name
        FROM price_logs l
        LEFT JOIN staff s ON l.staff_line_id = s.line_id
        LEFT JOIN chains c ON l.chain_id = c.id
        LEFT JOIN products p ON l.product_id = p.id
        WHERE DATE(l.log_time + interval '8 hours') = %s
        ORDER BY l.log_time DESC
    """
    try:
        cur.execute(query, (query_date,))
        # 修改開始
        logs = []
        for r in cur.fetchall():
            d = dict(r)
            d['log_time'] = str(d['log_time']) # 關鍵這行！
            logs.append(d)
        # 修改結束
    except: logs = []
    conn.close()
    return render_template('admin/audit_review.html', logs=logs, current_date=query_date)

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

@app.route('/admin/products/add', methods=['POST'])
def admin_products_add():
    if not is_admin_logged_in(): return redirect(url_for('admin_login'))
    conn = get_db(); cur = conn.cursor(); 
    # ✅ FIX: ? -> %s
    cur.execute("INSERT INTO products (name, spec, material, category, keywords, capacity, unit) VALUES (%s,%s,%s,%s,%s,%s,%s)", 
                (request.form.get('name'), request.form.get('spec'), request.form.get('material'), request.form.get('category'), request.form.get('keywords'), request.form.get('capacity'), request.form.get('unit')))
    conn.commit(); conn.close(); return redirect(url_for('admin_products'))

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
