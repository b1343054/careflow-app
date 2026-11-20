import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime
from database import init_db, get_connection

st.set_page_config(page_title="CareFlow 慢性病衛教追蹤系統", page_icon="🩺", layout="wide")

# 初始化資料庫
init_db()

# 初始化登入狀態
if "patient_auth" not in st.session_state:
    st.session_state.patient_auth = {}
if "nurse_auth" not in st.session_state:
    st.session_state.nurse_auth = False
if "pending_submit" not in st.session_state:
    st.session_state.pending_submit = None

st.title("🩺 CareFlow 慢性病衛教與居家量測追蹤審核系統")
st.caption("第 8 組｜支援雙端密碼驗證（Enter快速登入）、新增病患建檔、資料編輯、送出前最終確認防呆與全病患量表檢視")

tab_patient, tab_nurse, tab_edu = st.tabs([
    "👤 病患／家屬端（密碼登入與量測上傳）",
    "👩‍⚕️ 診所衛教護理師端（密碼登入與全病患追蹤）",
    "📚 衛教小百科（視覺化圖卡指南）"
])

NL = chr(10)

# ==========================================
# 1. 病患／家屬端
# ==========================================
with tab_patient:
    conn = get_connection()
    patients_df = pd.read_sql_query("SELECT * FROM patients ORDER BY patient_id", conn)

    # 新增自己的病患建檔區塊
    with st.expander("➕ 找不到名字？點此註冊新增病患檔案", expanded=False):
        with st.form("register_patient_form", clear_on_submit=True):
            st.markdown("填寫基本資料後，即可使用您設定的「出生年月日（8碼）」作為登入密碼：")
            r1, r2, r3 = st.columns(3)
            reg_name = r1.text_input("病患姓名 *", placeholder="例如：黃爺爺")
            reg_birth = r2.text_input("出生年月日（8碼登入密碼）*", placeholder="例如：19600315")
            reg_age = r3.number_input("年齡 *", min_value=1, max_value=120, value=65)

            r4, r5, r6 = st.columns(3)
            reg_gender = r4.selectbox("性別", ["男", "女", "其他"])
            reg_cond = r5.selectbox("主要慢性病追蹤項目 *", ["高血壓", "第二型糖尿病", "高血壓＋高血脂", "高血壓＋糖尿病", "糖尿病前期", "一般慢性病追蹤"])
            reg_phone = r6.text_input("聯絡電話", placeholder="例如：0911-222-333")

            reg_submit = st.form_submit_button("✅ 完成建檔並加入選單", type="primary", use_container_width=True)
            if reg_submit:
                if not reg_name.strip():
                    st.error("❌ 請輸入病患姓名！")
                elif len(reg_birth.strip()) != 8 or not reg_birth.strip().isdigit():
                    st.error("❌ 出生年月日密碼必須為 8 碼純數字（例如 19600315）！")
                else:
                    cur = conn.cursor()
                    # 自動產生下一個病患編號 (例如 P005, P006...)
                    max_row = cur.execute("SELECT patient_id FROM patients ORDER BY patient_id DESC LIMIT 1").fetchone()
                    if max_row and max_row[0].startswith("P"):
                        next_num = int(max_row[0][1:]) + 1
                    else:
                        next_num = len(patients_df) + 1
                    new_pid = f"P{next_num:03d}"

                    cur.execute(
                        "INSERT INTO patients (patient_id, name, birth_date, age, gender, condition_type, phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (new_pid, reg_name.strip(), reg_birth.strip(), int(reg_age), reg_gender, reg_cond, reg_phone.strip() or "未填寫")
                    )
                    conn.commit()
                    st.success(f"🎉 已成功新增病患「{new_pid} - {reg_name.strip()}」！請直接從下方選單選擇並輸入密碼進入。")
                    st.rerun()

    # 重新讀取最新病患清單
    patients_df = pd.read_sql_query("SELECT * FROM patients ORDER BY patient_id", conn)
    patient_options = {
        f"{row['patient_id']} - {row['name']} ({row['condition_type']})": row['patient_id']
        for _, row in patients_df.iterrows()
    }
    selected_label = st.selectbox("請選擇病患身分", list(patient_options.keys()), key="pat_select")
    selected_pid = patient_options[selected_label]
    p_info = patients_df[patients_df["patient_id"] == selected_pid].iloc[0]

    # 檢查該病患是否已通過出生年月日密碼驗證
    is_pat_logged_in = st.session_state.patient_auth.get(selected_pid, False)

    if not is_pat_logged_in:
        st.warning(f"🔒 為保護個人健康隱私，進入「{p_info['name']}」的資料與量測介面前，請先輸入出生年月日進行驗證。")
        col_login, _ = st.columns([1, 1.5])
        with col_login:
            # 使用 st.form 讓使用者輸入完直接按鍵盤 Enter 即可送出驗證
            with st.form(f"pat_login_form_{selected_pid}"):
                st.markdown(f"**測試提示（Demo 用）：** `{p_info['name']}` 的出生年月日密碼為 **`{p_info['birth_date']}`**")
                pwd_input = st.text_input("請輸入出生年月日（8碼，輸入後可直接按 Enter）", type="password")
                login_btn = st.form_submit_button("驗證並進入系統", type="primary", use_container_width=True)
                if login_btn:
                    if pwd_input.strip() == str(p_info["birth_date"]):
                        st.session_state.patient_auth[selected_pid] = True
                        st.rerun()
                    else:
                        st.error("❌ 出生年月日密碼錯誤，請重新確認！")
    else:
        top_bar1, top_bar2 = st.columns([4, 1])
        with top_bar1:
            st.success(f"✅ 已驗證身分：**{p_info['name']}**（{p_info['gender']}，{p_info['age']} 歲｜追蹤項目：{p_info['condition_type']}）")
        with top_bar2:
            if st.button("🚪 登出鎖定", key="pat_logout", use_container_width=True):
                st.session_state.patient_auth[selected_pid] = False
                st.session_state.pending_submit = None
                st.rerun()

        col_left, col_right = st.columns([1.05, 2.15], gap="large")

        with col_left:
            # 1. 可編輯病人基本狀況與聯絡資訊
            with st.expander("✏️ 編輯病人基本資料與健康狀況", expanded=False):
                with st.form("edit_patient_form"):
                    new_age = st.number_input("年齡", min_value=1, max_value=120, value=int(p_info["age"]))
                    cond_list = ["高血壓", "第二型糖尿病", "高血壓＋高血脂", "高血壓＋糖尿病", "糖尿病前期", "一般慢性病追蹤"]
                    default_idx = cond_list.index(p_info["condition_type"]) if p_info["condition_type"] in cond_list else 0
                    new_cond = st.selectbox("主要慢性病追蹤狀況", cond_list, index=default_idx)
                    new_phone = st.text_input("聯絡電話", value=str(p_info["phone"]))
                    new_birth = st.text_input("出生年月日密碼（8碼）", value=str(p_info["birth_date"]))
                    if st.form_submit_button("💾 儲存基本資料修改", use_container_width=True):
                        if len(new_birth.strip()) != 8 or not new_birth.strip().isdigit():
                            st.error("出生年月日密碼必須為 8 碼數字（例如 19580512）！")
                        else:
                            cur = conn.cursor()
                            cur.execute(
                                "UPDATE patients SET age = ?, condition_type = ?, phone = ?, birth_date = ? WHERE patient_id = ?",
                                (int(new_age), new_cond, new_phone.strip(), new_birth.strip(), selected_pid)
                            )
                            conn.commit()
                            st.success("已成功更新病人基本狀況！")
                            st.rerun()

            # 2. 上傳今日居家量測（含送出前最終確認防呆）
            st.subheader("📝 上傳今日居家量測")
            with st.form("measurement_form", clear_on_submit=False):
                rec_date = st.date_input("量測日期", value=date.today())
                c1, c2 = st.columns(2)
                systolic = c1.number_input("收縮壓 (mmHg)", min_value=50, max_value=260, value=128)
                diastolic = c2.number_input("舒張壓 (mmHg)", min_value=30, max_value=160, value=82)
                c3, c4 = st.columns(2)
                pulse = c3.number_input("脈搏 (次/分)", min_value=30, max_value=220, value=74)
                blood_sugar = c4.number_input("空腹血糖 (mg/dL)", min_value=30, max_value=500, value=108)
                symptoms = st.text_input("身體不適症狀（選填）", placeholder="例如：無不適、微頭暈、口渴...")
                pre_submit = st.form_submit_button("下一步：核對量測數據", type="primary", use_container_width=True)

                if pre_submit:
                    st.session_state.pending_submit = {
                        "patient_id": selected_pid,
                        "patient_name": p_info["name"],
                        "record_date": rec_date.isoformat(),
                        "systolic": int(systolic),
                        "diastolic": int(diastolic),
                        "pulse": int(pulse),
                        "blood_sugar": int(blood_sugar),
                        "symptoms": symptoms.strip() if symptoms.strip() else "無不適"
                    }

            # 跳出最終確認介面（送出後無法修改）
            if st.session_state.pending_submit and st.session_state.pending_submit["patient_id"] == selected_pid:
                data = st.session_state.pending_submit
                with st.container(border=True):
                    st.error("⚠️ **最終確認：請確認資料是否正確，送出後無法修改！**")
                    confirm_lines = [
                        f"- **病患姓名：** {data['patient_name']}",
                        f"- **量測日期：** `{data['record_date']}`",
                        f"- **血壓數值：** 收縮壓 **{data['systolic']}** / 舒張壓 **{data['diastolic']}** mmHg",
                        f"- **脈搏心跳：** **{data['pulse']}** 次/分",
                        f"- **空腹血糖：** **{data['blood_sugar']}** mg/dL",
                        f"- **自述症狀：** {data['symptoms']}"
                    ]
                    st.markdown(NL.join(confirm_lines))
                    b_ok, b_cancel = st.columns(2)
                    with b_ok:
                        if st.button("✅ 確認無誤，正式送出", type="primary", use_container_width=True):
                            cur = conn.cursor()
                            cur.execute(
                                """INSERT INTO measurements (patient_id, record_date, systolic, diastolic, pulse, blood_sugar, symptoms)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (data["patient_id"], data["record_date"], data["systolic"], data["diastolic"],
                                 data["pulse"], data["blood_sugar"], data["symptoms"])
                            )
                            conn.commit()

                            # BR-01 連續 3 次超標判定
                            recent_3 = pd.read_sql_query(
                                "SELECT * FROM measurements WHERE patient_id = ? ORDER BY record_date DESC, record_id DESC LIMIT 3",
                                conn, params=(selected_pid,)
                            )
                            if len(recent_3) == 3:
                                all_abn = all((r["systolic"] > 140) or (r["blood_sugar"] > 130) for _, r in recent_3.iterrows())
                                if all_abn:
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
                                            (selected_pid, data["record_date"], reason_txt)
                                        )
                                        conn.commit()
                            st.session_state.pending_submit = None
                            st.success("🎉 數據已正式寫入資料庫（已鎖定不可修改）！")
                            st.rerun()
                    with b_cancel:
                        if st.button("↩️ 返回修改", use_container_width=True):
                            st.session_state.pending_submit = None
                            st.rerun()

        with col_right:
            st.subheader(f"📊 {p_info['name']} 的歷史健康趨勢與醫護衛教回饋")

            care_df = pd.read_sql_query(
                """SELECT trigger_date, edu_template_title, nurse_note, reviewed_by, reviewed_at
                   FROM health_alerts
                   WHERE patient_id = ? AND alert_status = '已審核'
                   ORDER BY reviewed_at DESC LIMIT 3""",
                conn, params=(selected_pid,)
            )
            if not care_df.empty:
                for _, crow in care_df.iterrows():
                    tpl_name = crow['edu_template_title'] or '個別化照護建議'
                    care_lines = [
                        f"💬 **護理師衛教關懷（{crow['reviewed_at']}｜{crow['reviewed_by']}）**",
                        "",
                        f"**衛教主題：** {tpl_name}",
                        "",
                        f"**處置建議：** {crow['nurse_note']}"
                    ]
                    st.info(NL.join(care_lines))

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

                st.markdown("#### 📋 個人歷史量測明細（已送出鎖定唯讀）")
                st.dataframe(m_df.iloc[::-1].drop(columns=["record_id"]), use_container_width=True, hide_index=True)
            else:
                st.info("目前尚無歷史量測紀錄，請從左側表單新增第一筆數據。")

    conn.close()

# ==========================================
# 2. 診所衛教護理師端（含密碼鎖定 + Enter登入 + 全病患量表觀測）
# ==========================================
with tab_nurse:
    if not st.session_state.nurse_auth:
        st.warning("🔒 診所衛教護理師後台受醫護權限保護，請先輸入護理師端登入密碼。")
        col_n1, _ = st.columns([1, 1.5])
        with col_n1:
            # 使用 st.form 讓護理師輸入完直接按鍵盤 Enter 即可登入
            with st.form("nurse_login_form"):
                st.markdown("**測試提示（Demo 用）：** 護理師端預設密碼為 **`care2026`**")
                nurse_pwd = st.text_input("請輸入護理師後台密碼（輸入後可直接按 Enter）", type="password")
                n_login_btn = st.form_submit_button("登入護理師後台", type="primary", use_container_width=True)
                if n_login_btn:
                    if nurse_pwd.strip() == "care2026":
                        st.session_state.nurse_auth = True
                        st.rerun()
                    else:
                        st.error("❌ 護理師密碼錯誤，請重新輸入！")
    else:
        n_top1, n_top2 = st.columns([4, 1])
        with n_top1:
            st.success("👩‍⚕️ 歡迎登入診所衛教護理師工作台（目前值班：李護理師）")
        with n_top2:
            if st.button("🚪 登出後台", key="nurse_logout", use_container_width=True):
                st.session_state.nurse_auth = False
                st.rerun()

        conn = get_connection()

        # 上半部：高風險待審核警訊
        st.subheader("🚨 一、待審核高風險異常警訊（依 BR-01 自動置頂）")
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
            st.info("🎉 目前所有高風險異常警訊皆已審核完畢！")
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
                            height=100,
                            key=f"note_{arow['alert_id']}"
                        )
                        if st.button("✅ 完成審核並同步至病患端", key=f"btn_{arow['alert_id']}", type="primary"):
                            if not nurse_note.strip():
                                st.error("⛔ 違反業務規則 BR-03：請先填寫處置紀錄，不允許直接關閉警訊！")
                            else:
                                cur = conn.cursor()
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

        st.divider()

        # 下半部：選擇並觀測所有病患的量表數據
        st.subheader("🔍 二、全病患健康量表觀測與主動關懷（可選擇任一病患）")
        all_p_df = pd.read_sql_query("SELECT * FROM patients ORDER BY patient_id", conn)
        obs_options = {
            f"{r['patient_id']} - {r['name']}（{r['age']}歲｜{r['condition_type']}）": r['patient_id']
            for _, r in all_p_df.iterrows()
        }
        obs_label = st.selectbox("請選擇要觀測的病患", list(obs_options.keys()), key="nurse_obs_select")
        obs_pid = obs_options[obs_label]
        obs_info = all_p_df[all_p_df["patient_id"] == obs_pid].iloc[0]

        obs_m_df = pd.read_sql_query(
            """SELECT record_date AS 量測日期, systolic AS 收縮壓, diastolic AS 舒張壓,
                      pulse AS 脈搏, blood_sugar AS 空腹血糖, symptoms AS 症狀
               FROM measurements WHERE patient_id = ? ORDER BY record_date ASC, record_id ASC""",
            conn, params=(obs_pid,)
        )

        col_obs_chart, col_obs_tbl = st.columns([1.2, 1])
        with col_obs_chart:
            if not obs_m_df.empty:
                fig_obs = px.line(
                    obs_m_df, x="量測日期", y=["收縮壓", "舒張壓", "空腹血糖"],
                    markers=True, title=f"{obs_info['name']} 近期量測趨勢圖"
                )
                fig_obs.add_hline(y=140, line_dash="dash", line_color="red")
                fig_obs.add_hline(y=130, line_dash="dot", line_color="orange")
                st.plotly_chart(fig_obs, use_container_width=True)
            else:
                st.info("該病患尚無量測紀錄。")

        with col_obs_tbl:
            st.markdown(f"**📋 {obs_info['name']} 完整量表數據明細：**")
            if not obs_m_df.empty:
                st.dataframe(obs_m_df.iloc[::-1], use_container_width=True, hide_index=True)
            with st.form("proactive_care_form"):
                st.markdown("**主動發送衛教關懷訊息（即使未觸發警訊也可關懷）：**")
                p_note = st.text_area("輸入給病患的照護提醒", placeholder="例如：近期血壓控制得很穩定，請繼續保持規律運動與清淡飲食！", height=80)
                if st.form_submit_button("📤 發送關懷建議至病患端", use_container_width=True):
                    if not p_note.strip():
                        st.warning("請輸入關懷內容後再送出。")
                    else:
                        cur = conn.cursor()
                        cur.execute(
                            """INSERT INTO health_alerts (patient_id, trigger_date, reason, alert_status, edu_template_title, nurse_note, reviewed_by, reviewed_at)
                               VALUES (?, ?, '護理師主動定期關懷', '已審核', '定期追蹤關懷建議', ?, '李護理師', ?)""",
                            (obs_pid, date.today().isoformat(), p_note.strip(), datetime.now().strftime("%Y-%m-%d %H:%M"))
                        )
                        conn.commit()
                        st.success(f"已發送關懷建議給 {obs_info['name']}！")
                        st.rerun()

        conn.close()

# ==========================================
# 3. 衛教小百科（視覺化圖卡代替純文字）
# ==========================================
with tab_edu:
    st.subheader("📚 慢性病居家照護視覺化圖卡指南")
    st.markdown("透過直覺的**視覺化標準圖表**與**彩色燈號圖卡**，讓長輩與家屬一眼看懂血壓與血糖控制目標！")

    c_v1, c_v2 = st.columns(2, gap="large")

    with c_v1:
        st.markdown("### 🫀 居家血壓標準值視覺量尺 (mmHg)")
        fig_bp_bar = go.Figure()
        fig_bp_bar.add_trace(go.Bar(y=["收縮壓"], x=[120], name="🟢 正常 (<120)", orientation="h", marker_color="#10B981", text="正常 <120", textposition="inside"))
        fig_bp_bar.add_trace(go.Bar(y=["收縮壓"], x=[20], name="🟡 偏高 (120~139)", orientation="h", marker_color="#F59E0B", text="120~139", textposition="inside"))
        fig_bp_bar.add_trace(go.Bar(y=["收縮壓"], x=[40], name="🔴 警戒 (>140)", orientation="h", marker_color="#EF4444", text="警戒 >140", textposition="inside"))
        fig_bp_bar.add_trace(go.Bar(y=["舒張壓"], x=[80], name="🟢 正常 (<80)", orientation="h", marker_color="#10B981", text="正常 <80", textposition="inside", showlegend=False))
        fig_bp_bar.add_trace(go.Bar(y=["舒張壓"], x=[10], name="🟡 偏高 (80~89)", orientation="h", marker_color="#F59E0B", text="80~89", textposition="inside", showlegend=False))
        fig_bp_bar.add_trace(go.Bar(y=["舒張壓"], x=[30], name="🔴 警戒 (>90)", orientation="h", marker_color="#EF4444", text="警戒 >90", textposition="inside", showlegend=False))
        fig_bp_bar.update_layout(barmode="stack", height=220, margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h", y=1.18))
        st.plotly_chart(fig_bp_bar, use_container_width=True)

        with st.container(border=True):
            st.markdown("#### ⏱️ 居家量血壓「722 黃金口訣」圖卡")
            k1, k2, k3 = st.columns(3)
            k1.metric("📅 連續天數", "7 天", "每天記錄")
            k2.metric("🌅 每日次數", "2 回", "早起＆睡前")
            k3.metric("🔁 每次遍數", "2 遍", "間隔1分鐘取平均")

    with c_v2:
        st.markdown("### 🩸 空腹血糖標準值視覺量尺 (mg/dL)")
        fig_bs_bar = go.Figure()
        fig_bs_bar.add_trace(go.Bar(y=["空腹血糖"], x=[100], name="🟢 理想 (70~99)", orientation="h", marker_color="#10B981", text="理想 70~99", textposition="inside"))
        fig_bs_bar.add_trace(go.Bar(y=["空腹血糖"], x=[30], name="🟡 注意 (100~129)", orientation="h", marker_color="#F59E0B", text="100~129", textposition="inside"))
        fig_bs_bar.add_trace(go.Bar(y=["空腹血糖"], x=[50], name="🔴 警戒 (>130)", orientation="h", marker_color="#EF4444", text="警戒 >130", textposition="inside"))
        fig_bs_bar.update_layout(barmode="stack", height=220, margin=dict(l=10, r=10, t=20, b=10), legend=dict(orientation="h", y=1.18))
        st.plotly_chart(fig_bs_bar, use_container_width=True)

        with st.container(border=True):
            st.markdown("#### 🍽️ 控糖穩壓「進食順序」圖卡")
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("第 1 步", "💧 喝水", "先喝清湯或水")
            s2.metric("第 2 步", "🥬 吃菜", "膳食纖維墊胃")
            s3.metric("第 3 步", "🐟 吃肉", "優質蛋白質")
            s4.metric("第 4 步", "🍚 吃飯", "最後吃全穀澱粉")
