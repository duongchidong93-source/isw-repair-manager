# -*- coding: utf-8 -*-
"""
db.py
------
Lớp truy cập dữ liệu (data access layer) cho ISW Repair Dashboard, dùng SQLite
(thư viện chuẩn `sqlite3` của Python — không cần cài thêm gì).

Schema 3 bảng được giữ đúng theo thiết kế ở giai đoạn 1 (isw_categories,
maintenance_logs, sop_library), chuyển từ cú pháp MySQL sang SQLite.

*** Điều chỉnh có chủ đích so với schema MySQL gốc ***
Ở giai đoạn 1, isw_categories được mô tả là "danh mục linh kiện" và dữ liệu
mẫu dùng tên linh kiện (TypeC2, HDMI2.1...). Tuy nhiên, toàn bộ Dashboard đang
chạy (KPI, biểu đồ Top 5, dropdown trong form) lại lọc/nhóm theo cột
"Hạng mục lỗi" (自然磨損, FW更新, Rework...). Để ứng dụng hoạt động đúng như
đang thiết kế thay vì phải viết lại toàn bộ dashboard, isw_categories.category_name
ở đây được nạp từ các giá trị DUY NHẤT của cột "Hạng mục lỗi" trong CSV.
Nếu bạn muốn category thực sự là "Linh kiện" (TypeC2, HDMI...), chỉ cần đổi
COL_CATEGORY_SOURCE bên dưới và chạy lại (xóa file .db cũ trước khi chạy lại).

Một thay đổi thiết kế khác so với schema gốc: cột `status` trong
maintenance_logs giờ lưu THẲNG 1 trong 3 giá trị chuẩn ('Fixed', 'Pending',
'Scrapped') thay vì mã gốc tiếng Trung (OK/NG/报废...), vì đây là lúc dữ liệu
được đưa vào một hệ quản trị CSDL riêng của ứng dụng — việc quy đổi 1 lần lúc
di trú giúp toàn bộ code Dashboard phía sau đơn giản hơn hẳn (không cần map
đi/map lại giữa 2 hệ quy ước như bản CSV trước).
"""

import os
import sqlite3
from contextlib import contextmanager

import pandas as pd

DB_PATH = "isw_repair.db"

COL_CATEGORY_SOURCE = "Hạng mục lỗi"   # đổi thành "Linh kiện" nếu muốn category = tên linh kiện

# Ánh xạ 結果 (giá trị gốc trong CSV) -> trạng thái chuẩn lưu trong DB.
# *** Giả định nghiệp vụ — chỉnh lại nếu quy ước công ty bạn khác ***
STATUS_MAP = {
    "OK": "Fixed",
    "报废": "Scrapped",
    "NG-报废": "Scrapped",
    "NG": "Pending",
    "FAIL": "Pending",
    "等修复": "Pending",
}
STATUS_ORDER = ["Fixed", "Pending", "Scrapped"]


# ============================================================
# KẾT NỐI
# ============================================================

@contextmanager
def get_connection():
    """Mở 1 kết nối SQLite mới, bật ràng buộc khóa ngoại + chế độ WAL để đọc/ghi
    đồng thời an toàn hơn, và luôn đóng kết nối khi xong (kể cả khi có lỗi)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# KHỞI TẠO SCHEMA + DI TRÚ DỮ LIỆU TỪ CSV (chỉ chạy 1 LẦN DUY NHẤT)
# ============================================================

def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS isw_categories (
            category_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            category_name   TEXT    NOT NULL UNIQUE,
            description     TEXT,
            created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS maintenance_logs (
            log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            repair_date     TEXT    NOT NULL,
            box_serial      TEXT    NOT NULL,
            category_id     INTEGER NOT NULL,
            error_symptom   TEXT,
            action_taken    TEXT,
            engineer_name   TEXT,
            status          TEXT    NOT NULL DEFAULT 'Pending'
                                    CHECK (status IN ('Fixed', 'Pending', 'Scrapped')),
            created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES isw_categories (category_id)
                ON UPDATE CASCADE ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_logs_category_id ON maintenance_logs (category_id);
        CREATE INDEX IF NOT EXISTS idx_logs_repair_date ON maintenance_logs (repair_date);

        CREATE TABLE IF NOT EXISTS sop_library (
            sop_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id     INTEGER,
            title           TEXT    NOT NULL,
            file_path       TEXT,
            video_url       TEXT,
            created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES isw_categories (category_id)
                ON UPDATE CASCADE ON DELETE SET NULL,
            CHECK (file_path IS NOT NULL OR video_url IS NOT NULL)
        );
        """
    )
    conn.commit()


def _migrate_csv_into_db(conn: sqlite3.Connection, csv_path: str) -> None:
    df = pd.read_csv(csv_path)

    # --- 1. Nạp danh mục (category) từ các giá trị duy nhất trong CSV ---
    categories = sorted(df[COL_CATEGORY_SOURCE].dropna().unique().tolist())
    conn.executemany(
        "INSERT OR IGNORE INTO isw_categories (category_name) VALUES (?)",
        [(c,) for c in categories],
    )
    conn.commit()

    category_id_map = dict(
        conn.execute("SELECT category_name, category_id FROM isw_categories").fetchall()
    )

    # --- 2. Nạp nhật ký sửa chữa ---
    engineer_col = "Tên Kỹ sư" if "Tên Kỹ sư" in df.columns else None

    rows = []
    for _, r in df.iterrows():
        category_name = r.get(COL_CATEGORY_SOURCE)
        if pd.isna(category_name) or category_name not in category_id_map:
            continue  # bỏ qua dòng thiếu category hợp lệ, tránh vi phạm FOREIGN KEY

        raw_status = r.get("結果")
        status = STATUS_MAP.get(raw_status, "Pending")

        rows.append((
            str(r.get("Ngày tháng")) if pd.notna(r.get("Ngày tháng")) else None,
            str(r.get("SN Number")) if pd.notna(r.get("SN Number")) else "",
            category_id_map[category_name],
            str(r.get("Hiện tượng")) if pd.notna(r.get("Hiện tượng")) else None,
            str(r.get("維修方式")) if pd.notna(r.get("維修方式")) else None,
            (str(r.get(engineer_col)) if engineer_col and pd.notna(r.get(engineer_col)) else None),
            status,
        ))

    conn.executemany(
        """
        INSERT INTO maintenance_logs
            (repair_date, box_serial, category_id, error_symptom, action_taken, engineer_name, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def init_db_if_needed(csv_path: str) -> bool:
    """Nếu file database CHƯA tồn tại: tạo schema + nạp toàn bộ dữ liệu cũ từ CSV.
    Nếu đã tồn tại: không làm gì (coi như đã khởi tạo từ trước).
    Trả về True nếu vừa mới khởi tạo (để hiển thị thông báo lần đầu), False nếu đã có sẵn."""
    if os.path.exists(DB_PATH):
        return False

    with get_connection() as conn:
        _create_schema(conn)
        if os.path.exists(csv_path):
            _migrate_csv_into_db(conn, csv_path)
    return True


# ============================================================
# TRUY VẤN CHO DASHBOARD
# ============================================================

def fetch_logs_df() -> pd.DataFrame:
    """Lấy toàn bộ nhật ký sửa chữa, JOIN sẵn tên category, trả về dạng
    DataFrame với tên cột tiếng Việt để phần giao diện dùng lại được ngay."""
    query = """
        SELECT
            m.log_id            AS "log_id",
            m.repair_date        AS "Ngày tháng",
            m.box_serial         AS "SN Number",
            c.category_name      AS "Hạng mục lỗi",
            m.error_symptom      AS "Hiện tượng",
            m.action_taken       AS "Biện pháp xử lý",
            m.engineer_name      AS "Tên Kỹ sư",
            m.status             AS "Trạng thái xử lý"
        FROM maintenance_logs m
        JOIN isw_categories c ON m.category_id = c.category_id
        ORDER BY m.repair_date DESC, m.log_id DESC
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn)

    df["Ngày tháng"] = pd.to_datetime(df["Ngày tháng"], errors="coerce")
    return df


def get_category_options() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT category_name FROM isw_categories ORDER BY category_name"
        ).fetchall()
    return [r[0] for r in rows]


def insert_new_log(
    repair_date: str,
    box_serial: str,
    category_name: str,
    error_symptom: str,
    action_taken: str,
    engineer_name: str,
    status: str,
) -> int:
    """Ghi 1 dòng nhật ký sửa chữa mới bằng câu lệnh INSERT INTO tham số hóa
    (tránh SQL injection). Trả về log_id vừa được tạo."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT category_id FROM isw_categories WHERE category_name = ?",
            (category_name,),
        ).fetchone()
        if row is None:
            # Phòng hờ: category chưa tồn tại (vd. được thêm ngoài dropdown) -> tạo mới
            conn.execute(
                "INSERT INTO isw_categories (category_name) VALUES (?)", (category_name,)
            )
            category_id = conn.execute(
                "SELECT category_id FROM isw_categories WHERE category_name = ?",
                (category_name,),
            ).fetchone()[0]
        else:
            category_id = row[0]

        cursor = conn.execute(
            """
            INSERT INTO maintenance_logs
                (repair_date, box_serial, category_id, error_symptom, action_taken, engineer_name, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (repair_date, box_serial, category_id, error_symptom, action_taken, engineer_name, status),
        )
        conn.commit()
        return cursor.lastrowid


def count_logs() -> int:
    with get_connection() as conn:
        return conn.execute("SELECT COUNT(*) FROM maintenance_logs").fetchone()[0]


# ============================================================
# THƯ VIỆN SOP / VIDEO (sop_library)
# ============================================================

def insert_sop(category_name: str, title: str, file_path: str = None, video_url: str = None) -> int:
    """Ghi 1 tài liệu SOP/Video mới vào sop_library bằng INSERT INTO tham số hóa.
    file_path dùng cho PDF, video_url dùng cho đường dẫn file .mp4 cục bộ
    (ở đây "video_url" đơn giản là đường dẫn file trên đĩa, không phải link ngoài)."""
    if not file_path and not video_url:
        raise ValueError("Phải cung cấp ít nhất file_path hoặc video_url.")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT category_id FROM isw_categories WHERE category_name = ?",
            (category_name,),
        ).fetchone()
        if row is None:
            conn.execute("INSERT INTO isw_categories (category_name) VALUES (?)", (category_name,))
            category_id = conn.execute(
                "SELECT category_id FROM isw_categories WHERE category_name = ?",
                (category_name,),
            ).fetchone()[0]
        else:
            category_id = row[0]

        cursor = conn.execute(
            """
            INSERT INTO sop_library (category_id, title, file_path, video_url)
            VALUES (?, ?, ?, ?)
            """,
            (category_id, title, file_path, video_url),
        )
        conn.commit()
        return cursor.lastrowid


def fetch_sop_by_category(category_name: str) -> pd.DataFrame:
    """Lấy danh sách SOP/Video thuộc đúng 1 'Hạng mục lỗi', mới nhất trước."""
    query = """
        SELECT
            s.sop_id      AS "sop_id",
            s.title       AS "title",
            s.file_path   AS "file_path",
            s.video_url   AS "video_url",
            s.created_at  AS "created_at"
        FROM sop_library s
        JOIN isw_categories c ON s.category_id = c.category_id
        WHERE c.category_name = ?
        ORDER BY s.created_at DESC
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=(category_name,))


def count_sop_by_category() -> pd.DataFrame:
    """Đếm số tài liệu SOP/Video theo từng Hạng mục lỗi (dùng để hiển thị badge số lượng)."""
    query = """
        SELECT c.category_name AS "Hạng mục lỗi", COUNT(s.sop_id) AS "Số tài liệu"
        FROM isw_categories c
        LEFT JOIN sop_library s ON s.category_id = c.category_id
        GROUP BY c.category_name
    """
    with get_connection() as conn:
        return pd.read_sql_query(query, conn)
