import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
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

DB_FILE = "careflow.db"

# ==========================================
# 2. 資料庫初始化與測試資料建立 (SQLite)
# ==========================================
def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    
    # 量測紀錄表 (包含血壓、脈搏、空腹血糖)
    c.execute('''
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            record_date TEXT NOT NULL,
            systolic INTEGER NOT NULL,
            diastolic INTEGER NOT NULL,
            pulse INTEGER NOT NULL,
            blood_sugar INTEGER NOT NULL,
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

    # 若資料庫為空，自動灌入展示用假資料 (方便 Demo)
    c.execute("SELECT COUNT(*) FROM measurements")
    if c.fetchone()[0] == 0:
        today = datetime.now().date()
        sample_records = [
            # 陳伯伯：前兩天收縮壓都 > 140 (Demo時只要再輸入一筆 >140 就會立刻觸發BR-01警訊！)
            ("陳伯伯", str(today - timedelta(days=4)), 135, 85, 72, 110, "08:30:00"),
            ("陳伯伯", str(today - timedelta(days=3)), 138, 88, 75, 115, "08:40:00"),
            ("陳伯伯", str(today - timedelta(days=2)), 146, 92, 78, 122, "08:15:00"),
            ("陳伯伯", str(today - timedelta(days=1)), 152, 95, 80, 128, "08:20:00"),
            
            # 林奶奶：已連續 3 天空腹血糖 > 130，系統已有一筆待審核警訊
            ("林奶奶", str(today - timedelta(days=3)), 128, 80, 70, 136, "08:10:00"),
            ("林奶奶", str(today - timedelta(days=2)), 130, 82, 72, 142, "08:05:00"),
            ("林奶奶", str(today - timedelta(days=1)), 126, 78, 68, 148, "08:25:00"),
            
            # 王叔叔：數據正常，且今日已上傳
            ("王叔叔", str(today - timedelta(days=2)), 122, 78, 66, 98, "08:50:00"),
            ("王叔叔", str(today - timedelta(days=1)), 118, 76, 65, 102, "08:45:00"),
            ("王叔叔", str(today), 120, 79, 67, 99, "08:30:00"),
        ]
        c.executemany('''
            INSERT INTO measurements (patient_name, record_date, systolic, diastolic, pulse, blood_sugar, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_records)

        # 幫林奶奶建立一筆預設的「待審核」警訊卡片
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
    "【高血壓飲食】得舒飲食與減鈉提醒": "建議每日鈉攝取量低於 2,400 毫克（約 6 克鹽），減少加工食品與湯汁攝取，多吃深綠色蔬菜與高鉀蔬果。",
    "【高血糖控制】低 GI 飲食與餐後散步": "請減少精緻澱粉與含糖飲料，改以糙米、燕麥取代白飯，並於餐後 30 分鐘進行 15~20 分鐘溫和散步。",
    "【規律量測】居家血壓 722 原則衛教": "請持續保持連續 7 天、每天 2 回（起床後與睡前）、每回量 2 遍取平均值，確保數值準確供醫師評估。",
    "【用藥與回診】異常數值回診評估建議": "近期數值持續偏高，請確認是否按時服用慢性病處方藥，若伴隨頭暈、胸悶請提前回診評估。"
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
        # 檢查最近 3 筆紀錄是否皆超過門檻 (收縮壓 > 140 或 空腹血糖 > 130)
        high_bp = all(df['systolic'] > 140)
        high_bs = all(df['blood_sugar'] > 130)
        
        if high_bp or high_bs:
            # 檢查是否已經有未處理的相同待審核警訊，避免重複發送
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

# ==========================================
# 4. 網頁主介面與分頁導覽
# ==========================================
st.title("🩺 CareFlow 慢性病衛教與居家量測數據追蹤系統")
st.caption("第 8 組 系統分析與設計實作原型 | 整合病患居家上傳、歷史趨勢圖表與護理師端審核作業")

tab_patient, tab_nurse = st.tabs(["📱 病患／家屬端（數據上傳與歷史趨勢）", "👩‍⚕️ 診所衛教護理師端（警訊審核與逾期清單）"])

# ==========================================
# 分頁 A：病患 / 家屬端
# ==========================================
with tab_patient:
    col_left, col_right = st.columns([1, 2], gap="large")
    
    with col_left:
        st.subheader("📝 每日健康量測上傳 (UC-01)")
        patient_list = ["陳伯伯", "林奶奶", "王叔叔", "張阿姨"]
        selected_patient = st.selectbox("選擇病患姓名", patient_list)
        
        with st.form("upload_form", clear_on_submit=False):
            record_date = st.date_input("量測日期", value=datetime.now().date())
            c1, c2 = st.columns(2)
            with c1:
                systolic = st.number_input("收縮壓 (mmHg)", min_value=0, max_value=350, value=148, step=1)
                pulse = st.number_input("脈搏 (次/分)", min_value=0, max_value=250, value=76, step=1)
            with c2:
                diastolic = st.number_input("舒張壓 (mmHg)", min_value=0, max_value=250, value=92, step=1)
                blood_sugar = st.number_input("空腹血糖 (mg/dL)", min_value=0, max_value=600, value=118, step=1)
            
            submitted = st.form_submit_button("✅ 送出今日量測數據", use_container_width=True, type="primary")
            
            if submitted:
                # UC-01 例外路徑 E1：生理範圍合理性校驗
                if not (50 <= systolic <= 300) or not (30 <= diastolic <= 200) or not (30 <= pulse <= 220) or not (30 <= blood_sugar <= 500):
                    st.error("⚠️ 數值超出正常生理範圍（收縮壓 50~300、舒張壓 30~200、脈搏 30~220、血糖 30~500），請重新確認後再送出！")
                else:
                    conn = get_conn()
                    c = conn.cursor()
                    now_time = datetime.now().strftime("%H:%M:%S")
                    c.execute('''
                        INSERT INTO measurements (patient_name, record_date, systolic, diastolic, pulse, blood_sugar, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (selected_patient, str(record_date), systolic, diastolic, pulse, blood_sugar, now_time))
                    conn.commit()
                    conn.close()
                    
                    st.success(f"🎉 {selected_patient} 的量測數據已成功上傳並更新當日完成狀態！")
                    
                    # 執行 BR-01 高風險判定
                    triggered, reason = check_and_trigger_br01(selected_patient)
                    if triggered:
                        st.warning(f"🚨 系統已自動觸發高風險關注警訊並推入護理師待審清單：{reason}")

        # 顯示護理師最新發送給該病患的衛教關懷紀錄 (FR-05 網頁同步顯示)
        st.divider()
        st.subheader("💌 護理師衛教關懷紀錄")
        conn = get_conn()
        care_df = pd.read_sql_query(
            "SELECT reviewed_at AS 時間, nurse_name AS 護理師, edu_template AS 衛教主題, nurse_note AS 處置與建議 FROM alerts WHERE patient_name = ? AND status = '已審核' ORDER BY id DESC",
            conn, params=(selected_patient,)
        )
        conn.close()
        if care_df.empty:
            st.info("目前尚無護理師衛教回覆紀錄。")
        else:
            for _, row in care_df.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['衛教主題']}** (`{row['時間']}` · {row['護理師']})")
                    st.write(row['處置與建議'])

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
            
            # 1. 血壓趨勢折線圖 (超標紅點高亮)
            fig_bp = go.Figure()
            fig_bp.add_trace(go.Scatter(
                x=hist_df['record_date'], y=hist_df['systolic'],
                mode='lines+markers', name='收縮壓 (mmHg)',
                line=dict(color='#2563EB', width=2),
                marker=dict(
                    size=10,
                    color=['#EF4444' if v > 140 else '#2563EB' for v in hist_df['systolic']]
                )
            ))
            fig_bp.add_trace(go.Scatter(
                x=hist_df['record_date'], y=hist_df['diastolic'],
                mode='lines+markers', name='舒張壓 (mmHg)',
                line=dict(color='#10B981', width=2)
            ))
            fig_bp.add_hline(y=140, line_dash="dash", line_color="red", annotation_text="收縮壓警戒線 (140)")
            fig_bp.update_layout(title="血壓變化趨勢（紅點表示收縮壓 > 140 mmHg 超標）", height=320, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_bp, use_container_width=True)
            
            # 2. 空腹血糖趨勢折線圖 (超標紅點高亮)
            fig_bs = go.Figure()
            fig_bs.add_trace(go.Scatter(
                x=hist_df['record_date'], y=hist_df['blood_sugar'],
                mode='lines+markers', name='空腹血糖 (mg/dL)',
                line=dict(color='#F59E0B', width=2),
                marker=dict(
                    size=10,
                    color=['#EF4444' if v > 130 else '#F59E0B' for v in hist_df['blood_sugar']]
                )
            ))
            fig_bs.add_hline(y=130, line_dash="dash", line_color="red", annotation_text="空腹血糖警戒線 (130)")
            fig_bs.update_layout(title="空腹血糖變化趨勢（紅點表示血糖 > 130 mg/dL 超標）", height=300, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_bs, use_container_width=True)
            
            # 歷史明細表格
            with st.expander("📋 查看完整歷史量測數據明細表", expanded=True):
                display_df = hist_df[['record_date', 'created_at', 'systolic', 'diastolic', 'pulse', 'blood_sugar']].copy()
                display_df.columns = ['量測日期', '上傳時間', '收縮壓', '舒張壓', '脈搏', '空腹血糖']
                st.dataframe(display_df.sort_values(by=['量測日期', '上傳時間'], ascending=False), use_container_width=True, hide_index=True)
        else:
            st.info("該區間內尚無量測紀錄。")

# ==========================================
# 分頁 B：診所衛教護理師端
# ==========================================
with tab_nurse:
    nurse_name = st.text_input("👩‍⚕️ 當前值班護理師姓名（用於併發審核鎖定紀錄）", value="李護理師")
    
    col_alert, col_missing = st.columns([3, 2], gap="large")
    
    # 左側：高風險待審核警訊卡片與處置 (UC-03, FR-03, FR-04, FR-05, BR-03)
    with col_alert:
        st.subheader("🚨 高風險待審核警訊清單 (UC-03 / BR-01 置頂)")
        conn = get_conn()
        pending_alerts = pd.read_sql_query(
            "SELECT * FROM alerts WHERE status = '待審核' ORDER BY id DESC", conn
        )
        conn.close()
        
        if pending_alerts.empty:
            st.success("🎉 目前所有高風險警訊皆已審核完畢，無待辦卡片！")
        else:
            for _, alert in pending_alerts.iterrows():
                with st.container(border=True):
                    st.markdown(f"### 🔴 高風險關注：{alert['patient_name']} （觸發日：{alert['trigger_date']}）")
                    st.error(f"**異常原因：** {alert['reason']}")
                    
                    # 檢視病患近 14 天數據明細 (FR-04)
                    conn = get_conn()
                    p_14d = pd.read_sql_query(
                        "SELECT record_date AS 日期, systolic AS 收縮壓, diastolic AS 舒張壓, pulse AS 脈搏, blood_sugar AS 空腹血糖 FROM measurements WHERE patient_name = ? ORDER BY record_date DESC LIMIT 14",
                        conn, params=(alert['patient_name'],)
                    )
                    conn.close()
                    with st.expander(f"📊 展開 {alert['patient_name']} 近 14 天量測數據明細"):
                        st.dataframe(p_14d, use_container_width=True, hide_index=True)
                    
                    # 選擇衛教範本與填寫處置備註 (FR-05 & BR-03)
                    tpl_choice = st.selectbox(
                        "選擇衛教範本 (FR-05)",
                        list(EDU_TEMPLATES.keys()),
                        key=f"tpl_{alert['id']}"
                    )
                    default_text = EDU_TEMPLATES[tpl_choice]
                    note_input = st.text_area(
                        "衛教處置紀錄與備註（BR-03 規定：必填才可關閉警訊）",
                        value=default_text,
                        key=f"note_{alert['id']}",
                        height=90
                    )
                    
                    if st.button("✅ 儲存衛教紀錄並完成審核", key=f"btn_{alert['id']}", type="primary"):
                        # BR-03 業務規則檢核：未填寫處置紀錄不允許關閉警訊
                        if not note_input.strip():
                            st.warning("⚠️ 依據業務規則 BR-03：請先填寫處置紀錄或選擇衛教範本，未填寫前不允許直接關閉警訊！")
                        else:
                            # UC-03 例外路徑 E1：併發鎖定檢查 (確認該卡片尚未被其他護理師搶先審核)
                            conn = get_conn()
                            c = conn.cursor()
                            c.execute("SELECT status, nurse_name FROM alerts WHERE id = ?", (alert['id'],))
                            row_status = c.fetchone()
                            
                            if row_status and row_status[0] != '待審核':
                                st.error(f"⚠️ 此警訊已由其他同仁（{row_status[1]}）處置完畢！系統已自動取消本次寫入。")
                            else:
                                now_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
                                final_tpl = tpl_choice if tpl_choice != "請選擇衛教範本..." else "自訂衛教處置"
                                c.execute('''
                                    UPDATE alerts
                                    SET status = '已審核', nurse_name = ?, edu_template = ?, nurse_note = ?, reviewed_at = ?
                                    WHERE id = ?
                                ''', (nurse_name, final_tpl, note_input.strip(), now_dt, alert['id']))
                                conn.commit()
                                st.success(f"已儲存衛教紀錄並解除 {alert['patient_name']} 的高風險警訊！")
                                st.rerun()
                            conn.close()

        # 已審核歷史紀錄區
        st.divider()
        st.subheader("📁 已審核與衛教處置歷史紀錄")
        conn = get_conn()
        done_alerts = pd.read_sql_query(
            "SELECT reviewed_at AS 審核時間, patient_name AS 病患, nurse_name AS 審核護理師, edu_template AS 衛教範本, nurse_note AS 處置備註 FROM alerts WHERE status = '已審核' ORDER BY id DESC",
            conn
        )
        conn.close()
        if done_alerts.empty:
            st.info("尚無已審核紀錄。")
        else:
            st.dataframe(done_alerts, use_container_width=True, hide_index=True)

    # 右側：當日未按時上傳數據清單 (FR-06 & BR-02)
    with col_missing:
        st.subheader("⏰ 當日逾時未上傳數據清單 (FR-06 / BR-02)")
        st.caption("業務規則 BR-02：每日 09:00 應上傳，逾 12:00 未有紀錄自動列入未完成清單。")
        
        all_patients = ["陳伯伯", "林奶奶", "王叔叔", "張阿姨"]
        today_str = str(datetime.now().date())
        
        conn = get_conn()
        uploaded_today_df = pd.read_sql_query(
            "SELECT DISTINCT patient_name FROM measurements WHERE record_date = ?",
            conn, params=(today_str,)
        )
        conn.close()
        
        uploaded_set = set(uploaded_today_df['patient_name'].tolist())
        missing_patients = [p for p in all_patients if p not in uploaded_set]
        
        st.metric(label=f"今日 ({today_str}) 應上傳人數", value=f"{len(all_patients)} 人", delta=f"尚未上傳：{len(missing_patients)} 人", delta_color="inverse")
        
        if missing_patients:
            for mp in missing_patients:
                st.warning(f"⚠️ **{mp}** — 狀態：`逾時未上傳`（今日尚未建立量測紀錄）")
        else:
            st.success("✅ 今日所有病患皆已完成數據上傳！")
            
        st.divider()
        st.markdown("**✔️ 今日已完成上傳病患：**")
        for up in uploaded_set:
            st.write(f"- {up} （已完成）")