import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==========================================
# 1. 頁面基本設定
# ==========================================
st.set_page_config(
    page_title="CareFlow 慢性病居家量測與衛教審核系統",
    page_icon="🩺",
    layout="wide"
)

DB_FILE = "careflow_v2.db"

# ==========================================
# 2. 資料庫初始化與測試資料建立 (SQLite)
# ==========================================
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    # 病患基本資料表 (支援動態新增病患)
    c.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            age INTEGER,
            condition_type TEXT
        )
    ''')

    # 量測紀錄表 (擴充餐後血糖、體重、用藥與症狀紀錄)
    c.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            record_date TEXT NOT NULL,
            systolic INTEGER NOT NULL,
            diastolic INTEGER NOT NULL,
            pulse INTEGER NOT NULL,
            blood_sugar INTEGER NOT NULL,
            post_meal_sugar INTEGER DEFAULT 0,
            weight REAL DEFAULT 0.0,
            medication_status TEXT DEFAULT '已按時服藥',
            symptoms TEXT DEFAULT '無明顯不適',
            created_at TEXT NOT NULL
        )
    ''')
    
    # 異常警訊與衛教處置表
    c.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            trigger_date TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '待審核',
            nurse_name TEXT,
            edu_template TEXT,
            nurse_note TEXT,
            reviewed_at TEXT
        )
    ''')
    conn.commit()

    # 預設病患名單
    c.execute("SELECT COUNT(*) FROM patients")
    if c.fetchone()[0] == 0:
        default_patients = [
            ("陳伯伯", 68, "高血壓"),
            ("林奶奶", 72, "第二型糖尿病"),
            ("王叔叔", 61, "高血壓與高血脂"),
            ("張阿姨", 65, "糖尿病前期")
        ]
        c.executemany("INSERT INTO patients (name, age, condition_type) VALUES (?, ?, ?)", default_patients)
        conn.commit()

    # 若量測資料庫為空，自動灌入展示用假資料
    c.execute("SELECT COUNT(*) FROM measurements")
    if c.fetchone()[0] == 0:
        today = datetime.now().date()
        sample_records = [
            # 陳伯伯：前兩天收縮壓都 > 140
            ("陳伯伯", str(today - timedelta(days=4)), 135, 85, 72, 110, 138, 68.5, "已按時服藥", "無明顯不適", "08:30:00"),
            ("陳伯伯", str(today - timedelta(days=3)), 138, 88, 75, 115, 142, 68.4, "已按時服藥", "無明顯不適", "08:40:00"),
            ("陳伯伯", str(today - timedelta(days=2)), 146, 92, 78, 122, 150, 68.6, "已按時服藥", "輕微頭暈", "08:15:00"),
            ("陳伯伯", str(today - timedelta(days=1)), 152, 95, 80, 128, 158, 68.8, "忘記服藥", "頭暈、肩頸緊繃", "08:20:00"),
            
            # 林奶奶：已連續 3 天空腹血糖 > 130
            ("林奶奶", str(today - timedelta(days=3)), 128, 80, 70, 136, 185, 56.2, "已按時服藥", "容易口渴", "08:10:00"),
            ("林奶奶", str(today - timedelta(days=2)), 130, 82, 72, 142, 196, 56.0, "已按時服藥", "疲倦", "08:05:00"),
            ("林奶奶", str(today - timedelta(days=1)), 126, 78, 68, 148, 210, 55.9, "已按時服藥", "口渴、頻尿", "08:25:00"),
            
            # 王叔叔：數據正常，且今日已上傳
            ("王叔叔", str(today - timedelta(days=2)), 122, 78, 66, 98, 125, 74.0, "已按時服藥", "無明顯不適", "08:50:00"),
            ("王叔叔", str(today - timedelta(days=1)), 118, 76, 65, 102, 130, 73.8, "已按時服藥", "無明顯不適", "08:45:00"),
            ("王叔叔", str(today), 120, 79, 67, 99, 128, 73.9, "已按時服藥", "無明顯不適", "08:30:00"),
        ]
        c.executemany('''
            INSERT INTO measurements (patient_name, record_date, systolic, diastolic, pulse, blood_sugar, post_meal_sugar, weight, medication_status, symptoms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_records)

        c.execute('''
            INSERT INTO alerts (patient_name, trigger_date, reason, status)
            VALUES (?, ?, ?, ?)
        ''', ("林奶奶", str(today - timedelta(days=1)), "連續 3 天空腹血糖 > 130 mg/dL (136 / 142 / 148)", "待審核"))
        
        conn.commit()
    conn.close()

init_db()

# 衛教範本庫 (對應 FR-05)
EDU_TEMPLATES = {
    "請選擇衛教範本...": "",
    "【高血壓飲食】得舒飲食與減鈉提醒": "建議每日鈉攝取量低於 2,400 毫克（約 6 克鹽），減少加工食品、醃漬物與湯汁攝取，多吃深綠色蔬菜與高鉀蔬果。",
    "【高血糖控制】低 GI 飲食與餐後散步": "請減少精緻澱粉（白飯、白麵包）與含糖飲料，改以糙米、燕麥取代，並於餐後 30 分鐘進行 15~20 分鐘溫和散步。",
    "【規律量測】居家血壓 722 原則衛教": "請持續保持連續 7 天、每天 2 回（起床後與睡前）、每回量 2 遍取平均值，確保數值準確供醫師評估。",
    "【用藥與回診】異常數值回診評估建議": "近期數值持續偏高，請確認是否按時服用慢性病處方藥，若伴隨持續頭暈、胸悶請提前回診評估。"
}

# ==========================================
# 3. 核心業務邏輯 (BR-01 連續3天高風險判定)
# ==========================================
def check_and_trigger_br01(patient_name):
    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM measurements WHERE patient_name = ? ORDER BY record_date DESC, id DESC LIMIT 3",
        conn, params=(patient_name,)
    )
    
    if len(df) >= 3:
        high_bp = all(df['systolic'] > 140)
        high_bs = all(df['blood_sugar'] > 130)
        
        if high_bp or high_bs:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM alerts WHERE patient_name = ? AND status = '待審核'", (patient_name,))
            if c.fetchone()[0] == 0:
                reasons = []
                if high_bp:
                    vals = " / ".join(map(str, df['systolic'].tolist()[::-1]))
                    reasons.append(f"連續 3 天收縮壓 > 140 mmHg ({vals})")
                if high_bs:
                    vals = " / ".join(map(str, df['blood_sugar'].tolist()[::-1]))
                    reasons.append(f"連續 3 天空腹血糖 > 130 mg/dL ({vals})")
                
                reason_str = " 且 ".join(reasons)
                today_str = str(datetime.now().date())
                c.execute('''
                    INSERT INTO alerts (patient_name, trigger_date, reason, status)
                    VALUES (?, ?, ?, '待審核')
                ''', (patient_name, today_str, reason_str))
                conn.commit()
                conn.close()
                return True, reason_str
    conn.close()
    return False, ""

def get_all_patients_df():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM patients ORDER BY id ASC", conn)
    conn.close()
    return df

# ==========================================
# 4. 網頁主介面與分頁導覽
# ==========================================
st.title("🩺 CareFlow 慢性病衛教與居家量測數據追蹤系統")
st.caption("第 8 組 系統分析與設計實作原型 | 整合病患居家上傳、歷史趨勢圖表、護理師審核與大眾衛教指南")

tab_patient, tab_nurse, tab_edu = st.tabs([
    "📱 病患／家屬端（數據上傳與趨勢）",
    "👩‍⚕️ 診所衛教護理師端（警訊審核與逾期清單）",
    "📚 衛教小百科（數值判讀與飲食指南）"
])

# ==========================================
# 分頁 A：病患 / 家屬端
# ==========================================
with tab_patient:
    col_left, col_right = st.columns([1.1, 1.9], gap="large")
    
    with col_left:
        st.subheader("📝 每日健康量測上傳 (UC-01)")
        
        # 讀取動態病患清單
        patients_df = get_all_patients_df()
        patient_names = patients_df['name'].tolist()
        selected_patient = st.selectbox("選擇病患姓名", patient_names)
        
        # 顯示該病患基本標籤
        p_info = patients_df[patients_df['name'] == selected_patient].iloc[0]
        st.caption(f"👤 病患檔案：{p_info['age']} 歲 ｜ 追蹤項目：{p_info['condition_type']}")

        # 新增病患功能區塊
        with st.expander("➕ 找不到名字？點此新增病患資料"):
            with st.form("add_patient_form", clear_on_submit=True):
                new_p_name = st.text_input("新病患姓名（例：黃爺爺）")
                c_age, c_cond = st.columns(2)
                with c_age:
                    new_p_age = st.number_input("年齡", min_value=1, max_value=120, value=65)
                with c_cond:
                    new_p_cond = st.selectbox("主要追蹤項目", ["高血壓", "第二型糖尿病", "三高慢性病", "一般健康追蹤"])
                add_p_btn = st.form_submit_button("確認新增病患", use_container_width=True)
                
                if add_p_btn:
                    if not new_p_name.strip():
                        st.warning("請輸入病患姓名！")
                    elif new_p_name.strip() in patient_names:
                        st.error("此病患姓名已存在，請直接從上方選單選擇！")
                    else:
                        conn = get_conn()
                        c = conn.cursor()
                        c.execute("INSERT INTO patients (name, age, condition_type) VALUES (?, ?, ?)",
                                  (new_p_name.strip(), new_p_age, new_p_cond))
                        conn.commit()
                        conn.close()
                        st.success(f"已成功新增「{new_p_name.strip()}」！請從上方選單切換使用。")
                        st.rerun()

        # 量測數據輸入表單 (擴充完整欄位)
        with st.form("upload_form", clear_on_submit=False):
            record_date = st.date_input("量測日期", value=datetime.now().date())
            
            st.markdown("**1. 基礎生理數值**")
            c1, c2 = st.columns(2)
            with c1:
                systolic = st.number_input("收縮壓 (mmHg)", min_value=0, max_value=350, value=135, step=1, help="正常值應低於 120，超過 140 為高血壓警戒")
                pulse = st.number_input("脈搏 (次/分)", min_value=0, max_value=250, value=74, step=1, help="成人正常靜止心跳約 60~100 次/分")
                post_meal_sugar = st.number_input("餐後2小時血糖 (mg/dL)", min_value=0, max_value=600, value=135, step=1, help="正常值應低於 140 mg/dL")
            with c2:
                diastolic = st.number_input("舒張壓 (mmHg)", min_value=0, max_value=250, value=85, step=1, help="正常值應低於 80，超過 90 為高血壓警戒")
                blood_sugar = st.number_input("空腹血糖 (mg/dL)", min_value=0, max_value=600, value=105, step=1, help="正常值為 70~99，超過 130 為高風險警戒")
                weight = st.number_input("今日體重 (kg)", min_value=20.0, max_value=200.0, value=65.0, step=0.1)

            st.markdown("**2. 用藥與今日身體狀況**")
            med_status = st.radio("今日慢性病藥物服用情形", ["已按時服藥", "忘記服藥", "今日無需服藥"], horizontal=True)
            symptom_list = st.multiselect(
                "今日是否有以下不適症狀？（可複選）",
                ["無明顯不適", "頭暈／頭痛", "肩頸僵硬", "心悸／胸悶", "異常口渴／頻尿", "容易疲倦", "下肢水腫"],
                default=["無明顯不適"]
            )
            
            submitted = st.form_submit_button("✅ 送出今日量測數據", use_container_width=True, type="primary")
            
            if submitted:
                if not (50 <= systolic <= 300) or not (30 <= diastolic <= 200) or not (30 <= pulse <= 220) or not (30 <= blood_sugar <= 500):
                    st.error("⚠️ 數值超出正常生理範圍（收縮壓 50~300、舒張壓 30~200、脈搏 30~220、空腹血糖 30~500），請重新確認後再送出！")
                else:
                    symptoms_str = "、".join(symptom_list) if symptom_list else "未填寫"
                    conn = get_conn()
                    c = conn.cursor()
                    now_time = datetime.now().strftime("%H:%M:%S")
                    c.execute('''
                        INSERT INTO measurements (patient_name, record_date, systolic, diastolic, pulse, blood_sugar, post_meal_sugar, weight, medication_status, symptoms, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (selected_patient, str(record_date), systolic, diastolic, pulse, blood_sugar, post_meal_sugar, weight, med_status, symptoms_str, now_time))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"🎉 {selected_patient} 的量測數據已成功上傳並更新當日完成狀態！")
                    
                    # 即時給予當次量測簡易判讀提示
                    if systolic > 140 or diastolic > 90 or blood_sugar > 130:
                        st.info("💡 溫馨提醒：您本次輸入的血壓或血糖略高於標準值，建議先休息 10 分鐘後再量一次，並可至「📚 衛教小百科」查看飲食注意事項。")

                    # 執行 BR-01 高風險判定
                    triggered, reason = check_and_trigger_br01(selected_patient)
                    if triggered:
                        st.warning(f"🚨 系統已自動觸發高風險關注警訊並推入護理師待審清單：{reason}")

        # 顯示護理師最新發送給該病患的衛教關懷紀錄
        st.divider()
        st.subheader("💌 護理師衛教關懷紀錄")
        conn = get_conn()
        care_df = pd.read_sql_query(
            "SELECT reviewed_at AS 時間
