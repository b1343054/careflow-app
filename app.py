import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date, datetime
from database import init_db, get_connection

st.set_page_config(page_title="CareFlow 慢性病衛教追蹤系統", page_icon="🩺", layout="wide")

# 初始化資料庫與預設病人資料
init_db()

st.title("🩺 CareFlow 慢性病衛教與居家量測追蹤審核系統")
st.caption("第 8 組｜支援 SQLite 永久資料庫儲存、病人基本資料與歷史數據讀取、BR-01 連續 3 天異常警訊與 BR-03 審核防呆")

tab_patient, tab_nurse, tab_db = st.tabs(["👤 病患／家屬端（讀取資料與上傳量測）", "👩‍⚕️ 診所衛教護理師端（異常審核）", "🗄️ 資料庫總覽（Demo 檢視用）"])

# ==========================================
# 1. 病患／家屬端
# ==========================================
with tab_patient:
    conn = get_connection()
    patients_df = pd.read_sql_query("SELECT * FROM patients ORDER BY patient_id", conn)

    col_left, col_right = st.columns([1, 2.2], gap="large")

    with col_left:
        st.subheader("1. 選擇病患檔案")
        patient_options = {f"{row['patient_id']} - {row['name']} ({row['condition_type']})": row['patient_id'] for _, row in patients_df.iterrows()}
        selected_label = st.selectbox("請選擇目前登入的病患", list(patient_options.keys()))
        selected_pid = patient_options[selected_label]

        # 讀取該病患基本資料
        p_info = patients_df[patients_df["patient_id"] == selected_pid].iloc[0]
        with st.container(border=True):
            st.markdown(f"**姓名：** {p_info['name']}（{p_info['gender']}，{p_info['age']} 歲）")
            st.markdown(f"**追蹤慢性病別：** `{p_info['condition_type']}`")
            st.markdown(f"**聯絡電話：** {p_info['phone']}")

        st.subheader("2. 上傳今日居家量測")
        with st.form("measurement_form", clear_on_submit=False):
            rec_date = st.date_input("量測日期", value=date.today())
            c1, c2 = st.columns(2)
            systolic = c1.number_input("收縮壓 (mmHg)", min_value=50, max_value=260, value=128)
            diastolic = c2.number_input("舒張壓 (mmHg)", min_value=30, max_value=160, value=82)
            c3, c4 = st.columns(2)
            pulse = c3.number_input("脈搏 (次/分)", min_value=30, max_value=220, value=74)
            blood_sugar = c4.number_input("空腹血糖 (mg/dL)", min_value=30, max_value=500, value=108)
            symptoms = st.text_input("身體不適症狀（選填）", placeholder="例如：無不適、微頭暈、口渴...")
            submitted = st.form_submit_button("送出量測紀錄", type="primary", use_container_width=True)

            if submitted:
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO measurements (patient_id, record_date, systolic, diastolic, pulse, blood_sugar, symptoms)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (selected_pid, rec_date.isoformat(), int(systolic), int(diastolic), int(pulse), int(blood_sugar), symptoms or "無不適")
                )
                conn.commit()

                # 檢查 BR-01：最近 3 筆量測是否連續超標（收縮壓 > 140 或 空腹血糖 > 130）
                recent_3 = pd.read_sql_query(
                    "SELECT * FROM measurements WHERE patient_id = ? ORDER BY record_date DESC, record_id DESC LIMIT 3",
                    conn, params=(selected_pid,)
                )
                if len(recent_3) == 3:
                    all_abnormal = all((r["systolic"] > 140) or (r["blood_sugar"] > 130) for _, r in recent_3.iterrows())
                    if all_abnormal:
                        # 避免重複產生同日待審警訊
                        existing = cur.execute(
                            "SELECT COUNT(*) FROM health_alerts WHERE patient_id = ? AND alert_status = '待審核'",
                            (selected_pid,)
                        ).fetchone()[0]
                        if existing == 0:
                            bp_list = " / ".join(str(x) for x in recent_3["systolic"][::-1])
                            bs_list = " / ".join(str(x) for x in recent_3["blood_sugar"][::-1])
                            reason_txt = f"連續 3 次量測超標（收縮壓: {bp_list}；空腹血糖: {bs_list}）"
                            cur.execute(
                                "INSERT INTO health_alerts (patient_id, trigger_date, reason, alert_status) VALUES (?, ?, ?, '待審核')",
                                (selected_pid, rec_date.isoformat(), reason_txt)
                            )
                            conn.commit()
                            st.warning("⚠️ 系統偵測連續 3 次數值超標（BR-01），已自動產生高風險警訊並置頂通知護理師！")
                st.success("✅ 量測數據已成功寫入資料庫！")
                st.rerun()

    with col_right:
        st.subheader(f"📊 {p_info['name']} 的歷史健康趨勢與最新醫護回饋")

        # 讀取護理師最新已審核衛教關懷紀錄
        care_df = pd.read_sql_query(
            """SELECT trigger_date, edu_template_title, nurse_note, reviewed_by, reviewed_at
               FROM health_alerts
               WHERE patient_id = ? AND alert_status = '已審核'
               ORDER BY reviewed_at DESC LIMIT 3""",
            conn, params=(selected_pid,)
        )
        if not care_df.empty:
            for _, crow in care_df.iterrows():
                st.info(f"💬 **護理師衛教關懷（{crow['reviewed_at']}｜{crow['reviewed_by']}）**

"
                        f"**衛教主題：** {crow['edu_template_title'] or '個別化照護建議'}

"
                        f"**處置建議：** {crow['nurse_note']}")

        # 讀取該病患歷史量測數據
        m_df = pd.read_sql_query(
            """SELECT record_id, record_date AS 量測日期, systolic AS 收縮壓, diastolic AS 舒張壓,
                      pulse AS 脈搏, blood_sugar AS 空腹血糖, symptoms AS 症狀
               FROM measurements WHERE patient_id = ? ORDER BY record_date ASC, record_id ASC""",
            conn, params=(selected_pid,)
        )

        if not m_df.empty:
            fig = px.line(
                m_df, x="量測日期", y=["收縮壓", "舒張壓", "空腹血糖"],
                markers=True, title=f"{p_info['name']} 血壓與空腹血糖變化趨勢"
            )
            fig.add_hline(y=140, line_dash="dash", line_color="red", annotation_text="收縮壓警戒線 (140)")
            fig.add_hline(y=130, line_dash="dot", line_color="orange", annotation_text="空腹血糖警戒線 (130)")
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### 📋 個人歷史量測明細（可即時讀取）")
            st.dataframe(m_df.iloc[::-1].drop(columns=["record_id"]), use_container_width=True, hide_index=True)
        else:
            st.info("目前尚無歷史量測紀錄，請從左側表單新增第一筆數據。")

    conn.close()

# ==========================================
# 2. 診所衛教護理師端
# ==========================================
with tab_nurse:
    conn = get_connection()
    st.subheader("🚨 待審核高風險異常警訊（依 BR-01 自動置頂）")

    alerts_df = pd.read_sql_query(
        """SELECT a.alert_id, a.patient_id, p.name AS patient_name, p.age, p.condition_type,
                  a.trigger_date, a.reason, a.alert_status
           FROM health_alerts a
           JOIN patients p ON a.patient_id = p.patient_id
           WHERE a.alert_status = '待審核'
           ORDER BY a.alert_id DESC""",
        conn
    )

    templates_df = pd.read_sql_query("SELECT * FROM edu_templates", conn)
    template_map = {f"[{r['category']}] {r['title']}": r['content'] for _, r in templates_df.iterrows()}

    if alerts_df.empty:
        st.success("🎉 目前所有異常警訊皆已審核完畢！")
    else:
        for _, arow in alerts_df.iterrows():
            with st.expander(f"🔴 【高風險置頂】{arow['patient_name']}（{arow['age']}歲｜{arow['condition_type']}）— {arow['reason']}", expanded=True):
                c_hist, c_act = st.columns([1.3, 1])
                with c_hist:
                    st.markdown("**近期量測數據明細：**")
                    sub_m = pd.read_sql_query(
                        """SELECT record_date AS 日期, systolic AS 收縮壓, diastolic AS 舒張壓,
                                  pulse AS 脈搏, blood_sugar AS 空腹血糖, symptoms AS 症狀
                           FROM measurements WHERE patient_id = ? ORDER BY record_date DESC, record_id DESC LIMIT 7""",
                        conn, params=(arow["patient_id"],)
                    )
                    st.dataframe(sub_m, use_container_width=True, hide_index=True)

                with c_act:
                    st.markdown("**衛教處置與結案審核（BR-03 必填防呆）：**")
                    chosen_tpl = st.selectbox(
                        "快速套用標準衛教範本 (FR-05)",
                        ["（自行輸入衛教建議）"] + list(template_map.keys()),
                        key=f"tpl_{arow['alert_id']}"
                    )
                    default_note = template_map.get(chosen_tpl, "")
                    nurse_note = st.text_area(
                        "處置紀錄與衛教建議（必填）*",
                        value=default_note,
                        height=110,
                        key=f"note_{arow['alert_id']}"
                    )
                    if st.button("✅ 完成審核並同步至病患端", key=f"btn_{arow['alert_id']}", type="primary"):
                        if not nurse_note.strip():
                            st.error("⛔ 違反業務規則 BR-03：請先填寫處置紀錄，不允許直接關閉警訊！")
                        else:
                            cur = conn.cursor()
                            # 併發防呆檢查 (UC-03 E1)
                            curr_status = cur.execute(
                                "SELECT alert_status FROM health_alerts WHERE alert_id = ?",
                                (int(arow["alert_id"]),)
                            ).fetchone()[0]
                            if curr_status != "待審核":
                                st.warning("⚠️ 此警訊已由其他護理師搶先審核結案！")
                            else:
                                tpl_title = chosen_tpl if chosen_tpl != "（自行輸入衛教建議）" else "個別化衛教建議"
                                cur.execute(
                                    """UPDATE health_alerts
                                       SET alert_status = '已審核', edu_template_title = ?, nurse_note = ?,
                                           reviewed_by = '李護理師', reviewed_at = ?
                                       WHERE alert_id = ?""",
                                    (tpl_title, nurse_note.strip(), datetime.now().strftime("%Y-%m-%d %H:%M"), int(arow["alert_id"]))
                                )
                                conn.commit()
                                st.success("已結案並同步顯示於病患端網頁！")
                                st.rerun()
    conn.close()

# ==========================================
# 3. 資料庫總覽（Demo 檢視用）
# ==========================================
with tab_db:
    conn = get_connection()
    st.markdown("### 1. 病患基本資料表 (`patients`)")
    st.dataframe(pd.read_sql_query("SELECT * FROM patients", conn), use_container_width=True, hide_index=True)

    st.markdown("### 2. 居家量測紀錄表 (`measurements`)")
    st.dataframe(pd.read_sql_query("SELECT * FROM measurements ORDER BY record_id DESC", conn), use_container_width=True, hide_index=True)

    st.markdown("### 3. 異常警訊與審核紀錄表 (`health_alerts`)")
    st.dataframe(pd.read_sql_query("SELECT * FROM health_alerts ORDER BY alert_id DESC", conn), use_container_width=True, hide_index=True)
    conn.close()
