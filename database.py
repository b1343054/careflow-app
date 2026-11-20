import sqlite3
from datetime import date, datetime, timedelta

DB_PATH = "careflow.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # 1. 病患資料表 (Patient)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        patient_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        gender TEXT,
        condition_type TEXT NOT NULL,
        phone TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. 量測紀錄資料表 (Measurement)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS measurements (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        record_date TEXT NOT NULL,
        systolic INTEGER NOT NULL,
        diastolic INTEGER NOT NULL,
        pulse INTEGER NOT NULL,
        blood_sugar INTEGER NOT NULL,
        symptoms TEXT,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    )
    """)

    # 3. 異常警訊資料表 (HealthAlert)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS health_alerts (
        alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        trigger_date TEXT NOT NULL,
        reason TEXT NOT NULL,
        alert_status TEXT NOT NULL DEFAULT '待審核',
        edu_template_title TEXT,
        nurse_note TEXT,
        reviewed_by TEXT,
        reviewed_at TEXT,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
    )
    """)

    # 4. 衛教範本資料表 (EduTemplate)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS edu_templates (
        template_id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL
    )
    """)

    # 5. 衛教護理師資料表 (Nurse)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS nurses (
        nurse_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        department TEXT NOT NULL
    )
    """)

    conn.commit()
    seed_initial_data(conn)
    conn.close()

def seed_initial_data(conn):
    cur = conn.cursor()
    # 檢查是否已有病患資料，避免重複塞入
    cur.execute("SELECT COUNT(*) FROM patients")
    if cur.fetchone()[0] > 0:
        return

    # 預設病患名單（含不同慢性病類型供病人端選擇讀取）
    patients = [
        ("P001", "陳伯伯", 68, "男", "高血壓", "0912-345-678"),
        ("P002", "林阿姨", 62, "女", "第二型糖尿病", "0923-456-789"),
        ("P003", "王先生", 55, "男", "高血壓＋高血脂", "0934-567-890"),
        ("P004", "張奶奶", 74, "女", "高血壓＋糖尿病", "0945-678-901"),
    ]
    cur.executemany(
        "INSERT INTO patients (patient_id, name, age, gender, condition_type, phone) VALUES (?, ?, ?, ?, ?, ?)",
        patients
    )

    # 預設衛教護理師
    nurses = [
        ("N001", "李護理師", "慢性病衛教中心"),
        ("N002", "周個管師", "代謝症候群照護門診"),
    ]
    cur.executemany("INSERT INTO nurses (nurse_id, name, department) VALUES (?, ?, ?)", nurses)

    # 預設標準衛教範本 (FR-05)
    templates = [
        ("T01", "高血壓飲食", "低鈉得舒飲食衛教", "建議每日鈉攝取低於 2400mg（約 6 克鹽），減少湯汁、醃漬物與加工食品，多攝取深綠色蔬菜與高鉀水果。"),
        ("T02", "血糖控制", "空腹血糖偏高照護指引", "建議調整晚餐精緻澱粉比例，飯後 30 分鐘進行 15~20 分鐘溫和散步，並留意是否有頭暈或口渴症狀。"),
        ("T03", "用藥提醒", "規律服藥與居家量測衛教", "請勿自行停藥或減藥，建議每日固定起床後 1 小時內（服藥前、早餐前）完成血壓與空腹血糖量測。")
    ]
    cur.executemany("INSERT INTO edu_templates (template_id, category, title, content) VALUES (?, ?, ?, ?)", templates)

    # 預設歷史量測紀錄（讓病人端一打開就有 7 天趨勢圖與測試數據可讀）
    today = date.today()
    sample_measurements = [
        # 陳伯伯：連續 3 天收縮壓 > 140（供演示 BR-01 高風險警訊）
        ("P001", (today - timedelta(days=4)).isoformat(), 132, 84, 72, 102, "無不適"),
        ("P001", (today - timedelta(days=3)).isoformat(), 136, 86, 74, 105, "無不適"),
        ("P001", (today - timedelta(days=2)).isoformat(), 145, 91, 78, 108, "偶爾肩頸緊繃"),
        ("P001", (today - timedelta(days=1)).isoformat(), 149, 94, 80, 110, "輕微頭脹"),
        ("P001", today.isoformat(), 152, 95, 79, 112, "早上起床微頭暈"),
        # 林阿姨：平穩控制中
        ("P002", (today - timedelta(days=2)).isoformat(), 124, 78, 70, 118, "無不適"),
        ("P002", (today - timedelta(days=1)).isoformat(), 122, 76, 68, 121, "無不適"),
        ("P002", today.isoformat(), 126, 79, 71, 116, "精神良好"),
        # 王先生：昨日數據
        ("P003", (today - timedelta(days=1)).isoformat(), 138, 88, 75, 114, "熬夜加班"),
        # 張奶奶：空腹血糖偏高
        ("P004", (today - timedelta(days=2)).isoformat(), 135, 82, 73, 138, "口渴"),
        ("P004", (today - timedelta(days=1)).isoformat(), 139, 85, 74, 142, "疲倦"),
    ]
    cur.executemany(
        "INSERT INTO measurements (patient_id, record_date, systolic, diastolic, pulse, blood_sugar, symptoms) VALUES (?, ?, ?, ?, ?, ?, ?)",
        sample_measurements
    )

    # 預設一筆陳伯伯的待審核警訊
    cur.execute(
        """INSERT INTO health_alerts (patient_id, trigger_date, reason, alert_status)
           VALUES (?, ?, ?, ?)""",
        ("P001", today.isoformat(), "連續 3 天收縮壓 > 140 mmHg（145 / 149 / 152）", "待審核")
    )

    conn.commit()

if __name__ == "__main__":
    init_db()
    print("CareFlow 資料庫初始化完成！")
