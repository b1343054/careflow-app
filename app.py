import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="CareFlow 慢性病居家量測與衛教審核系統",
    page_icon="🩺",
    layout="wide"
)

DB_FILE = "careflow_v3.db"

def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            age INTEGER,
            condition_type TEXT
        )
    ''')
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

    c.execute("SELECT COUNT(*) FROM measurements")
    if c.fetchone()[0] == 0:
        today = datetime.now().date()
        sample_records = [
            ("陳伯伯", str(today - timedelta(days=4)), 135, 85, 72, 110, 138, 68.5, "已按時服藥", "無明顯不適", "08:30:00"),
            ("陳伯伯", str(today - timedelta(days=3)), 138, 88, 75, 115, 142, 68.4, "已按時服藥", "無明顯不適", "08:40:00"),
            ("陳伯伯", str(today - timedelta(days=2)), 146, 92, 78, 122, 150, 68.6, "已按時服藥", "輕微頭暈", "08:15:00"),
            ("陳伯伯", str(today - timedelta(days=1)), 152, 95, 80, 128, 158, 68.8, "忘記服藥", "頭暈、肩頸緊繃", "08:20:00"),
            ("林奶奶", str(today - timedelta(days=3)), 128, 80, 70, 136, 185, 56.2, "已按時服藥", "容易口渴", "08:10:00"),
            ("林奶奶", str(today - timedelta(days=2)), 130, 82, 72, 142, 196, 56.0, "已按時服藥", "疲倦", "08:05:00"),
            ("林奶奶", str(today - timedelta(days=1)), 126, 78, 68, 148, 210, 55.9, "已按時服藥", "口渴、頻尿", "08:25:00"),
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

EDU_TEMPLATES = {
    "請選擇衛教範本...": "",
    "【高血壓飲食】得舒飲食與減鈉提醒": "建議每日鈉攝取量低於 2,400 毫克（約 6 克鹽），減少加工食品、醃漬物與湯汁攝取，多吃深綠色蔬菜與高鉀蔬果。",
    "【高血糖控制】低 GI 飲食與餐後散步": "請減少精緻澱粉（白飯、白麵包）與含糖飲料，改以糙米、燕麥取代，並於餐後 30 分鐘進行 15~20 分鐘溫和散步。",
    "【規律量測】居家血壓 722 原則衛教": "請持續保持連續 7 天、每天 2 回（起床後與睡前）、每回量 2 遍取平均值，確保數值準確供醫師評估。",
    "【用藥與回診】異常數值回診評估建議": "近期數值持續偏高，請確認是否按時服用慢性病處方藥，若伴隨持續頭暈、胸悶請提前回診評估。"
}

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
                c.execute(
                    "INSERT INTO alerts (patient_name, trigger_date, reason, status) VALUES (?, ?, ?, '待審核')",
                    (patient_name, today_str, reason_str)
                )
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
        patients_df = get_all_patients_df()
        patient_names = patients_df['name'].tolist()
        selected_patient = st.selectbox("選擇病患姓名", patient_names)
        
        p_info = patients_df[patients_df['name'] == selected_patient].iloc[0]
        st.caption(f"👤 病患檔案：{p_info['age']} 歲 ｜ 追蹤項目：{p_info['condition_type']}")

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

        with st.form("upload_form", clear_on_submit=False):
            record_date = st.date_input("量測日期", value=datetime.now().date())
            st.markdown("**1. 基礎生理數值**")
            c1, c2 = st.columns(2)
            with c1:
                systolic = st.number_input("收縮壓 (mmHg)", min_value=0, max_value=350, value=135, step=1)
                pulse = st.number_input("脈搏 (次/分)", min_value=0, max_value=250, value=74, step=1)
                post_meal_sugar = st.number_input("餐後2小時血糖 (mg/dL)", min_value=0, max_value=600, value=135, step=1)
            with c2:
                diastolic = st.number_input("舒張壓 (mmHg)", min_value=0, max_value=250, value=85, step=1)
                blood_sugar = st.number_input("空腹血糖 (mg/dL)", min_value=0, max_value=600, value=105, step=1)
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
                    st.error("⚠️ 數值超出正常生理範圍，請重新確認後再送出！")
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
                    if systolic > 140 or diastolic > 90 or blood_sugar > 130:
                        st.info("💡 溫馨提醒：本次血壓或血糖略高於標準值，建議先休息 10 分鐘後再量一次。")
                    triggered, reason = check_and_trigger_br01(selected_patient)
                    if triggered:
                        st.warning(f"🚨 系統已自動觸發高風險關注警訊並推入護理師待審清單：{reason}")

        st.divider()
        st.subheader("💌 護理師衛教關懷紀錄")
        conn = get_conn()
        care_df = pd.read_sql_query(
            "SELECT reviewed_at, nurse_name, edu_template, nurse_note FROM alerts WHERE patient_name = ? AND status = '已審核' ORDER BY id DESC",
            conn, params=(selected_patient,)
        )
        conn.close()
        if care_df.empty:
            st.info("目前尚無護理師衛教回覆紀錄。")
        else:
            for _, row in care_df.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['edu_template']}** (`{row['reviewed_at']}` · {row['nurse_name']})")
                    st.write(row['nurse_note'])

    with col_right:
        st.subheader(f"📈 {selected_patient} 的歷史健康趨勢圖表 (FR-02)")
        period = st.radio("檢視區間切換", ["近 7 天 (週)", "近 30 天 (月)"], horizontal=True)
        days_limit = 7 if "7" in period else 30
        
        conn = get_conn()
        hist_df = pd.read_sql_query(
            "SELECT * FROM measurements WHERE patient_name = ? ORDER BY record_date ASC, id ASC",
            conn, params=(selected_patient,)
        )
        conn.close()
        
        if not hist_df.empty:
            cutoff_date = str((datetime.now() - timedelta(days=days_limit)).date())
            hist_df = hist_df[hist_df['record_date'] >= cutoff_date]
            
            fig_bp = go.Figure()
            fig_bp.add_trace(go.Scatter(
                x=hist_df['record_date'], y=hist_df['systolic'],
                mode='lines+markers', name='收縮壓 (mmHg)',
                line=dict(color='#2563EB', width=2),
                marker=dict(size=10, color=['#EF4444' if v > 140 else '#2563EB' for v in hist_df['systolic']])
            ))
            fig_bp.add_trace(go.Scatter(
                x=hist_df['record_date'], y=hist_df['diastolic'],
                mode='lines+markers', name='舒張壓 (mmHg)',
                line=dict(color='#10B981', width=2)
            ))
            fig_bp.add_hline(y=140, line_dash="dash", line_color="red", annotation_text="收縮壓警戒線 (140)")
            fig_bp.update_layout(title="血壓變化趨勢（紅點表示收縮壓 > 140 mmHg 超標）", height=300, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_bp, use_container_width=True)
            
            fig_bs = go.Figure()
            fig_bs.add_trace(go.Scatter(
                x=hist_df['record_date'], y=hist_df['blood_sugar'],
                mode='lines+markers', name='空腹血糖 (mg/dL)',
                line=dict(color='#F59E0B', width=2),
                marker=dict(size=10, color=['#EF4444' if v > 130 else '#F59E0B' for v in hist_df['blood_sugar']])
            ))
            fig_bs.add_trace(go.Scatter(
                x=hist_df['record_date'], y=hist_df['post_meal_sugar'],
                mode='lines+markers', name='餐後2小時血糖 (mg/dL)',
                line=dict(color='#8B5CF6', width=2, dash='dot')
            ))
            fig_bs.add_hline(y=130, line_dash="dash", line_color="red", annotation_text="空腹血糖警戒線 (130)")
            fig_bs.update_layout(title="血糖變化趨勢（紅點表示空腹血糖 > 130 mg/dL 超標）", height=290, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_bs, use_container_width=True)
            
            with st.expander("📋 查看完整歷史量測與症狀明細表", expanded=True):
                display_df = hist_df[['record_date', 'systolic', 'diastolic', 'pulse', 'blood_sugar', 'post_meal_sugar', 'weight', 'medication_status', 'symptoms']].copy()
                display_df.columns = ['量測日期', '收縮壓', '舒張壓', '脈搏', '空腹血糖', '餐後血糖', '體重(kg)', '用藥狀況', '自述症狀']
                st.dataframe(display_df.sort_values(by=['量測日期'], ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("該病患在此區間內尚無量測紀錄，請由左側表單輸入第一筆數據！")

# ==========================================
# 分頁 B：診所衛教護理師端
# ==========================================
with tab_nurse:
    nurse_name = st.text_input("👩‍⚕️ 當前值班護理師姓名（用於併發審核鎖定紀錄）", value="李護理師")
    col_alert, col_missing = st.columns([3, 2], gap="large")
    
    with col_alert:
        st.subheader("🚨 高風險待審核警訊清單 (UC-03 / BR-01 置頂)")
        conn = get_conn()
        pending_alerts = pd.read_sql_query("SELECT * FROM alerts WHERE status = '待審核' ORDER BY id DESC", conn)
        conn.close()
        
        if pending_alerts.empty:
            st.success("🎉 目前所有高風險警訊皆已審核完畢，無待辦卡片！")
        else:
            for _, alert in pending_alerts.iterrows():
                with st.container(border=True):
                    st.markdown(f"### 🔴 高風險關注：{alert['patient_name']} （觸發日：{alert['trigger_date']}）")
                    st.error(f"**異常原因：** {alert['reason']}")
                    
                    conn = get_conn()
                    p_14d = pd.read_sql_query(
                        "SELECT record_date, systolic, diastolic, blood_sugar, post_meal_sugar, medication_status, symptoms FROM measurements WHERE patient_name = ? ORDER BY record_date DESC LIMIT 14",
                        conn, params=(alert['patient_name'],)
                    )
                    conn.close()
                    p_14d.columns = ['日期', '收縮壓', '舒張壓', '空腹血糖', '餐後血糖', '用藥', '症狀']
                    with st.expander(f"📊 展開 {alert['patient_name']} 近 14 天量測與症狀明細"):
                        st.dataframe(p_14d, use_container_width=True, hide_index=True)
                    
                    tpl_choice = st.selectbox("選擇衛教範本 (FR-05)", list(EDU_TEMPLATES.keys()), key=f"tpl_{alert['id']}")
                    note_input = st.text_area("衛教處置紀錄與備註（BR-03 規定：必填才可關閉警訊）", value=EDU_TEMPLATES[tpl_choice], key=f"note_{alert['id']}", height=90)
                    
                    if st.button("✅ 儲存衛教紀錄並完成審核", key=f"btn_{alert['id']}", type="primary"):
                        if not note_input.strip():
                            st.warning("⚠️ 依據業務規則 BR-03：請先填寫處置紀錄或選擇衛教範本，未填寫前不允許直接關閉警訊！")
                        else:
                            conn = get_conn()
                            c = conn.cursor()
                            c.execute("SELECT status, nurse_name FROM alerts WHERE id = ?", (alert['id'],))
                            row_status = c.fetchone()
                            if row_status and row_status[0] != '待審核':
                                st.error(f"⚠️ 此警訊已由其他同仁（{row_status[1]}）處置完畢！系統已自動取消本次寫入。")
                            else:
                                now_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
                                final_tpl = tpl_choice if tpl_choice != "請選擇衛教範本..." else "自訂衛教處置"
                                c.execute(
                                    "UPDATE alerts SET status = '已審核', nurse_name = ?, edu_template = ?, nurse_note = ?, reviewed_at = ? WHERE id = ?",
                                    (nurse_name, final_tpl, note_input.strip(), now_dt, alert['id'])
                                )
                                conn.commit()
                                st.success(f"已儲存衛教紀錄並解除 {alert['patient_name']} 的高風險警訊！")
                                st.rerun()
                            conn.close()

        st.divider()
        st.subheader("📁 已審核與衛教處置歷史紀錄")
        conn = get_conn()
        done_alerts = pd.read_sql_query(
            "SELECT reviewed_at, patient_name, nurse_name, edu_template, nurse_note FROM alerts WHERE status = '已審核' ORDER BY id DESC",
            conn
        )
        conn.close()
        if done_alerts.empty:
            st.info("尚無已審核紀錄。")
        else:
            done_alerts.columns = ['審核時間', '病患', '審核護理師', '衛教範本', '處置備註']
            st.dataframe(done_alerts, use_container_width=True, hide_index=True)

    with col_missing:
        st.subheader("⏰ 當日逾時未上傳數據清單 (FR-06 / BR-02)")
        st.caption("業務規則 BR-02：每日 09:00 應上傳，逾 12:00 未有紀錄自動列入未完成清單。")
        all_patients = get_all_patients_df()['name'].tolist()
        today_str = str(datetime.now().date())
        conn = get_conn()
        uploaded_today_df = pd.read_sql_query("SELECT DISTINCT patient_name FROM measurements WHERE record_date = ?", conn, params=(today_str,))
        conn.close()
        uploaded_set = set(uploaded_today_df['patient_name'].tolist())
        missing_patients = [p for p in all_patients if p not in uploaded_set]
        
        st.metric(label=f"今日 ({today_str}) 應上傳總人數", value=f"{len(all_patients)} 人", delta=f"尚未上傳：{len(missing_patients)} 人", delta_color="inverse")
        if missing_patients:
            for mp in missing_patients:
                st.warning(f"⚠️ **{mp}** — 狀態：`逾時未上傳`（今日尚未建立量測紀錄）")
        else:
            st.success("✅ 今日所有病患皆已完成數據上傳！")
            
        st.divider()
        st.markdown("**✔️ 今日已完成上傳病患：**")
        for up in uploaded_set:
            st.write(f"- {up} （已完成）")

# ==========================================
# 分頁 C：衛教小百科
# ==========================================
with tab_edu:
    st.subheader("📚 慢性病居家照護與衛教小百科")
    st.markdown("看不懂血壓機與血糖機上的數字嗎？透過下方的**紅黃綠燈對照表**與**日常飲食原則**，輕鬆掌握自己與家人的健康狀態！")

    col_e1, col_e2 = st.columns(2, gap="large")
    with col_e1:
        st.markdown("### 1️⃣ 血壓數值怎麼看？（單位：mmHg）")
        bp_guide = pd.DataFrame({
            "健康燈號": ["🟢 正常血壓", "🟡 血壓偏高（注意期）", "🔴 高血壓警戒（需介入）", "🚨 危險高血壓"],
            "收縮壓（上壓）": ["小於 120", "120 ～ 139", "140 ～ 179", "180 以上"],
            "舒張壓（下壓）": ["小於 80", "80 ～ 89", "90 ～ 109", "110 以上"],
            "建議行動": [
                "非常標準！請維持目前作息與清淡飲食。",
                "開始注意減鹽、規律運動，每天早晚量測。",
                "系統將自動標記關注，請遵照護理師衛教並定期回診。",
                "若伴隨劇烈頭痛、胸痛或手腳無力，請立即就醫！"
            ]
        })
        st.table(bp_guide)
        st.info("💡 **什麼是「居家血壓 722 原則」？**\n- **7**：連續量測 **7** 天。\n- **2**：每天量 **2** 回（早上起床 1 小時內、晚上睡前各一次）。\n- **2**：每回量 **2** 遍（兩次間隔 1 分鐘，取平均值記錄最準確）。")

    with col_e2:
        st.markdown("### 2️⃣ 血糖數值怎麼看？（單位：mg/dL）")
        bs_guide = pd.DataFrame({
            "健康燈號": ["🟢 理想標準", "🟡 偏高注意（糖尿病前期）", "🔴 高血糖警戒", "⚠️ 低血糖危險"],
            "空腹血糖（未進食8小時）": ["70 ～ 99", "100 ～ 125", "130 以上（連續3天觸發警訊）", "低於 70"],
            "餐後 2 小時血糖": ["小於 140", "140 ～ 199", "200 以上", "—"],
            "建議行動": [
                "血糖控制良好，繼續保持均衡飲食。",
                "減少精緻糖分與宵夜，飯後散步 15 分鐘。",
                "系統將通知護理師關懷，請檢視近期澱粉與甜食攝取。",
                "若出現冒冷汗、手抖、心悸，請立即補充 15 克糖分（如半杯果汁或 3 顆方糖）！"
            ]
        })
        st.table(bs_guide)
        st.warning("💡 **量測前小提醒**：量血壓前請先靜坐休息 5 分鐘，不要憋尿，測量前 30 分鐘避免喝咖啡、濃茶或抽菸。")

    st.divider()
    st.markdown("### 3️⃣ 三高日常飲食紅綠燈指南")
    c_diet1, c_diet2, c_diet3 = st.columns(3)
    with c_diet1:
        with st.container(border=True):
            st.markdown("#### 🥗 高血壓「得舒飲食」原則")
            st.markdown("- **多吃高鉀蔬果**：菠菜、空心菜、地瓜葉、香蕉、奇異果（幫助排出多餘鈉離子）。\n- **選擇全穀雜糧**：以糙米、五穀米、燕麥取代白米飯。\n- **白肉取代紅肉**：優先選擇魚肉、去皮雞肉與豆製品，減少豬五花、牛腩。\n- **每日鹽分限制**：一天總鈉量不超過 2,400 毫克（約 **1 茶匙鹽**）。")
    with c_diet2:
        with st.container(border=True):
            st.markdown("#### 🍚 控糖「進食順序」技巧")
            st.markdown("- **改變吃飯順序**：掌握 **「水 ➔ 菜 ➔ 肉 ➔ 飯」**，先吃蔬菜與蛋白質墊胃，最後再吃澱粉。\n- **挑選低 GI 食物**：選擇地瓜、南瓜、全麥麵包，避免白吐司、糕點與含糖手搖飲。\n- **水果份量控制**：每天最多 2 份（約 2 個拳頭大），切忌打成果汁喝。")
    with c_diet3:
        with st.container(border=True):
            st.markdown("#### 🚫 慢性病患應避開的「地雷食物」")
            st.markdown("- **高鈉加工品**：香腸、火腿、臘肉、肉鬆、泡麵、罐頭醬菜。\n- **隱形高鹽湯汁**：火鍋湯底、牛肉麵湯、勾芡濃湯（建議吃料不喝湯）。\n- **精緻糖與反式脂肪**：珍珠奶茶、蛋糕、酥皮麵包、油炸物。\n- **藥物交互作用**：服用降血壓或降血脂藥期間，**不可食用葡萄柚與柚子**。")
