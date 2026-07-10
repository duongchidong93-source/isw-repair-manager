# -*- coding: utf-8 -*-
"""
isw_dashboard.py
-----------------
ISW Repair Management System — Dashboard + Nhật ký + Thư viện SOP/Video (SQLite).

Cài đặt thư viện:
    pip install streamlit pandas plotly --break-system-packages

Chạy ứng dụng:
    streamlit run isw_dashboard.py

Cấu trúc 3 tab:
    [1] 📊 Dashboard Thống Kê     — KPI + biểu đồ tổng quan
    [2] 📝 Nhật Ký & Nhập Liệu    — tìm kiếm nhanh + bảng chi tiết + form thêm mới
    [3] 📚 Thư Viện SOP/Video     — tải lên & xem tài liệu theo Hạng mục lỗi

Lần chạy đầu tiên: nếu chưa có file isw_repair.db, tự tạo schema + nạp dữ liệu
từ ISW_Repair_Logs_Cleaned.csv. Từ lần sau chỉ đọc/ghi thẳng SQLite.
"""

import os
import re
import time
from datetime import date

import db
import pandas as pd
import plotly.express as px
import streamlit as st

CSV_SEED_PATH = "ISW_Repair_Logs_Cleaned.csv"
ASSETS_DIR = "assets"
os.makedirs(ASSETS_DIR, exist_ok=True)

STATUS_ORDER = db.STATUS_ORDER  # ["Fixed", "Pending", "Scrapped"]
STATUS_COLORS = {"Fixed": "#2ECC71", "Pending": "#F39C12", "Scrapped": "#E74C3C"}

SEARCH_COLUMNS = ["SN Number", "Hạng mục lỗi", "Hiện tượng", "Biện pháp xử lý", "Tên Kỹ sư"]


# ============================================================
# NẠP DỮ LIỆU (đọc từ SQLite, có cache — xóa cache sau mỗi lần ghi mới)
# ============================================================

@st.cache_data
def load_data():
    return db.fetch_logs_df()


@st.cache_data
def load_category_options():
    return db.get_category_options()


def clear_data_cache():
    load_data.clear()
    load_category_options.clear()


def search_filter(data: pd.DataFrame, keyword: str) -> pd.DataFrame:
    """Lọc dữ liệu theo từ khóa tự do, khớp không phân biệt hoa/thường trên nhiều
    cột cùng lúc (số Serial, hạng mục lỗi, hiện tượng, biện pháp xử lý, kỹ sư)."""
    keyword = keyword.strip().lower()
    if not keyword:
        return data

    mask = pd.Series(False, index=data.index)
    for col in SEARCH_COLUMNS:
        if col in data.columns:
            mask |= data[col].astype(str).str.lower().str.contains(re.escape(keyword), na=False)
    return data[mask]


# ============================================================
# GIAO DIỆN — CẤU HÌNH TRANG & CSS
# ============================================================

st.set_page_config(page_title="ISW Repair Management System", page_icon="🔧", layout="wide")

st.markdown(
    """
    <style>
    html, body, [class*="css"] { font-family: 'Consolas', 'Roboto Mono', monospace; }

    /* Header */
    .isw-header-title { font-size: 1.9rem; font-weight: 700; margin-bottom: 0; }
    .isw-header-sub    { color: #6B7280; font-size: 0.92rem; margin-top: 2px; }

    /* KPI cards */
    div[data-testid="stMetric"] {
        background-color: #F5F6F8;
        border: 1px solid #D9DCE1;
        border-radius: 8px;
        padding: 16px 18px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    div[data-testid="stMetricLabel"] { font-size: 0.85rem; color: #555; }

    /* Tabs — chữ to hơn, rõ ràng hơn */
    button[data-baseweb="tab"] { font-size: 1rem; font-weight: 600; padding: 10px 18px; }

    /* Section headers */
    h1, h2, h3 { font-weight: 650; }

    hr { margin: 0.6rem 0 1.2rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

header_col1, header_col2 = st.columns([3, 1])
with header_col1:
    st.markdown('<p class="isw-header-title">🔧 ISW Repair Management System</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="isw-header-sub">Quản lý nhật ký sửa chữa hộp thử nghiệm ISW — dữ liệu SQLite (isw_repair.db)</p>',
        unsafe_allow_html=True,
    )

# --- Khởi tạo DB lần đầu (idempotent) ---
just_initialized = db.init_db_if_needed(CSV_SEED_PATH)
if just_initialized:
    st.toast(f"Đã khởi tạo isw_repair.db và nạp {db.count_logs():,} dòng dữ liệu từ CSV.", icon="✅")

with header_col2:
    st.metric("Tổng số bản ghi", f"{db.count_logs():,}")

st.divider()

df = load_data()
category_options = load_category_options()

# ------------------------------------------------------------
# Sidebar: bộ lọc dùng chung cho cả Dashboard & Nhật ký
# ------------------------------------------------------------
st.sidebar.header("⚙️ Bộ lọc chung")

selected_categories = st.sidebar.multiselect(
    "Hạng mục lỗi", options=category_options, default=[], help="Để trống = hiển thị tất cả",
)

has_engineer_data = df["Tên Kỹ sư"].notna().any()
if has_engineer_data:
    selected_engineers = st.sidebar.multiselect(
        "Tên Kỹ sư",
        options=sorted(df["Tên Kỹ sư"].dropna().unique().tolist()),
        default=[],
        help="Để trống = hiển thị tất cả",
    )
else:
    selected_engineers = []
    st.sidebar.info("Chưa có dữ liệu 'Tên Kỹ sư'. Bộ lọc tự xuất hiện khi có nhật ký ghi tên kỹ sư.")

st.sidebar.caption("Bộ lọc này áp dụng cho cả tab Dashboard và tab Nhật Ký.")

filtered_df = df.copy()
if selected_categories:
    filtered_df = filtered_df[filtered_df["Hạng mục lỗi"].isin(selected_categories)]
if selected_engineers:
    filtered_df = filtered_df[filtered_df["Tên Kỹ sư"].isin(selected_engineers)]


# ============================================================
# 3 TAB CHÍNH
# ============================================================
tab_dashboard, tab_logs, tab_sop = st.tabs(
    ["📊 Dashboard Thống Kê", "📝 Nhật Ký & Nhập Liệu", "📚 Thư Viện SOP/Video"]
)

# ============================================================
# [1] DASHBOARD THỐNG KÊ
# ============================================================
with tab_dashboard:
    total_cases = len(filtered_df)
    fixed_cases = int((filtered_df["Trạng thái xử lý"] == "Fixed").sum())
    success_rate = (fixed_cases / total_cases * 100) if total_cases > 0 else 0.0

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Tổng số ca sửa chữa", f"{total_cases:,}")
    kpi2.metric("Số ca đã xử lý xong (Fixed)", f"{fixed_cases:,}")
    kpi3.metric("Tỷ lệ sửa thành công", f"{success_rate:.1f}%")

    st.divider()

    chart_col1, chart_col2 = st.columns([1.2, 1])

    with chart_col1:
        st.subheader("Top 5 Hạng mục lỗi xuất hiện nhiều nhất")
        top5 = (
            filtered_df["Hạng mục lỗi"].value_counts().head(5)
            .sort_values(ascending=True).reset_index()
        )
        top5.columns = ["Hạng mục lỗi", "Số ca"]

        if top5.empty:
            st.info("Không có dữ liệu để hiển thị với bộ lọc hiện tại.")
        else:
            fig_bar = px.bar(
                top5, x="Số ca", y="Hạng mục lỗi", orientation="h", text="Số ca",
                template="simple_white", color_discrete_sequence=["#2E86C1"],
            )
            fig_bar.update_traces(textposition="outside")
            fig_bar.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=340,
                                   yaxis_title=None, xaxis_title="Số ca")
            st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col2:
        st.subheader("Tỷ lệ trạng thái sửa chữa")
        status_counts = (
            filtered_df["Trạng thái xử lý"].value_counts()
            .reindex(STATUS_ORDER).fillna(0).reset_index()
        )
        status_counts.columns = ["Trạng thái", "Số ca"]

        if filtered_df.empty:
            st.info("Không có dữ liệu để hiển thị với bộ lọc hiện tại.")
        else:
            fig_pie = px.pie(
                status_counts, names="Trạng thái", values="Số ca", color="Trạng thái",
                color_discrete_map=STATUS_COLORS, hole=0.45, template="simple_white",
            )
            fig_pie.update_traces(textinfo="label+percent")
            fig_pie.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=340)
            st.plotly_chart(fig_pie, use_container_width=True)


# ============================================================
# [2] NHẬT KÝ & NHẬP LIỆU
# ============================================================
with tab_logs:
    st.subheader("🔎 Tìm kiếm nhanh")
    search_keyword = st.text_input(
        "Tìm theo mã chip, số Serial, hiện tượng lỗi, biện pháp xử lý hoặc tên kỹ sư...",
        placeholder="VD: BL7901, TPE-2026..., 接口損壞, ...",
        label_visibility="collapsed",
    )
    st.caption(
        "💡 Gõ từ khóa rồi nhấn **Enter** (hoặc click ra ngoài ô) để bảng bên dưới lọc "
        "ngay lập tức — tìm cùng lúc trên các cột: " + ", ".join(SEARCH_COLUMNS) + "."
    )

    search_result_df = search_filter(filtered_df, search_keyword)

    st.caption(
        f"Hiển thị {len(search_result_df):,} / {len(filtered_df):,} dòng "
        f"(sau bộ lọc sidebar) — tổng toàn bộ dữ liệu: {len(df):,} dòng"
    )

    display_cols = ["Ngày tháng", "SN Number", "Hạng mục lỗi", "Hiện tượng",
                     "Biện pháp xử lý", "Tên Kỹ sư", "Trạng thái xử lý"]
    display_cols = [c for c in display_cols if c in search_result_df.columns]

    st.dataframe(
        search_result_df[display_cols].sort_values(by="Ngày tháng", ascending=False),
        use_container_width=True,
        hide_index=True,
        height=380,
    )

    st.divider()

    st.subheader("➕ Thêm nhật ký sửa chữa mới")

    with st.form("form_update_log", clear_on_submit=True):
        col_a, col_b = st.columns(2)

        with col_a:
            repair_date = st.date_input("Ngày sửa", value=date.today())
            serial_no = st.text_input("Số Serial hộp ISW", placeholder="VD: TPE-20260709-001")
            category = st.selectbox("Hạng mục lỗi", options=category_options)
            engineer_name = st.text_input("Kỹ sư thực hiện", placeholder="VD: Nguyễn Văn A")

        with col_b:
            symptom = st.text_area("Hiện tượng lỗi", placeholder="Mô tả hiện tượng quan sát được...")
            action_taken = st.text_area("Biện pháp xử lý", placeholder="Mô tả cách xử lý đã thực hiện...")
            status = st.selectbox("Trạng thái", options=STATUS_ORDER)

        submitted = st.form_submit_button("💾 Lưu và Đồng Bộ", use_container_width=True)

    if submitted:
        missing_fields = []
        if not serial_no.strip():
            missing_fields.append("Số Serial hộp ISW")
        if not category:
            missing_fields.append("Hạng mục lỗi")
        if not symptom.strip():
            missing_fields.append("Hiện tượng lỗi")
        if not action_taken.strip():
            missing_fields.append("Biện pháp xử lý")
        if not engineer_name.strip():
            missing_fields.append("Kỹ sư thực hiện")

        if missing_fields:
            st.error("⚠️ Vui lòng điền đầy đủ thông tin. Các trường còn thiếu: " + ", ".join(missing_fields))
        else:
            try:
                new_log_id = db.insert_new_log(
                    repair_date=repair_date.strftime("%Y-%m-%d"),
                    box_serial=serial_no.strip(),
                    category_name=category,
                    error_symptom=symptom.strip(),
                    action_taken=action_taken.strip(),
                    engineer_name=engineer_name.strip(),
                    status=status,
                )
            except Exception as e:
                st.error(f"❌ Không thể ghi dữ liệu vào cơ sở dữ liệu: {e}")
            else:
                st.success(f"✅ Đã lưu và đồng bộ thành công! (log_id = {new_log_id})")
                clear_data_cache()
                st.rerun()


# ============================================================
# [3] THƯ VIỆN SOP & VIDEO
# ============================================================
with tab_sop:
    st.subheader("Thư Viện SOP & Video")
    st.caption("Tải lên quy trình chuẩn (PDF) hoặc video thao tác thực tế (.mp4), gắn với "
               "1 'Hạng mục lỗi'. File được lưu trong thư mục assets/, đường dẫn ghi vào bảng sop_library.")

    upload_col, view_col = st.columns([1, 1.3], gap="large")

    with upload_col:
        st.markdown("##### ⬆️ Tải lên tài liệu mới")

        with st.form("form_upload_sop", clear_on_submit=True):
            sop_category = st.selectbox(
                "Hạng mục lỗi liên quan", options=category_options,
                help="VD: chọn hạng mục liên quan đến lỗi bạn muốn gắn tài liệu (vd: Chip BL7901).",
            )
            sop_title = st.text_input("Tiêu đề tài liệu", placeholder="VD: Quy trình thay Chip BL7901")
            uploaded_file = st.file_uploader(
                "Chọn file (PDF quy trình hoặc video .mp4 thao tác thực tế)",
                type=["pdf", "mp4"],
            )
            sop_submitted = st.form_submit_button("⬆️ Tải lên", use_container_width=True)

        if sop_submitted:
            sop_errors = []
            if not sop_category:
                sop_errors.append("Hạng mục lỗi liên quan")
            if not sop_title.strip():
                sop_errors.append("Tiêu đề tài liệu")
            if uploaded_file is None:
                sop_errors.append("File PDF/Video")

            if sop_errors:
                st.error("⚠️ Vui lòng điền đầy đủ thông tin. Còn thiếu: " + ", ".join(sop_errors))
            else:
                ext = os.path.splitext(uploaded_file.name)[1].lower()
                safe_title = re.sub(r"[^\w\-]+", "_", sop_title.strip())[:60]
                filename = f"{int(time.time())}_{safe_title}{ext}"
                save_path = os.path.join(ASSETS_DIR, filename)

                try:
                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    if ext == ".pdf":
                        new_sop_id = db.insert_sop(
                            category_name=sop_category, title=sop_title.strip(),
                            file_path=save_path, video_url=None,
                        )
                    else:  # .mp4
                        new_sop_id = db.insert_sop(
                            category_name=sop_category, title=sop_title.strip(),
                            file_path=None, video_url=save_path,
                        )
                except Exception as e:
                    st.error(f"❌ Không thể lưu tài liệu: {e}")
                else:
                    st.success(f"✅ Đã tải lên và lưu vào thư viện! (sop_id = {new_sop_id})")
                    clear_data_cache()
                    st.rerun()

    with view_col:
        st.markdown("##### 📂 Xem tài liệu theo Hạng mục lỗi")

        view_category = st.selectbox(
            "Chọn Hạng mục lỗi cần xem", options=category_options, key="sop_view_category",
        )

        sop_df = db.fetch_sop_by_category(view_category)

        if sop_df.empty:
            st.info(f"Chưa có tài liệu SOP/Video nào cho hạng mục '{view_category}'.")
        else:
            st.caption(f"Tìm thấy {len(sop_df)} tài liệu cho hạng mục '{view_category}':")
            for _, row in sop_df.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['title']}**")

                    if pd.notna(row["video_url"]) and os.path.exists(str(row["video_url"])):
                        st.video(row["video_url"])
                    elif pd.notna(row["file_path"]) and os.path.exists(str(row["file_path"])):
                        with open(row["file_path"], "rb") as f:
                            st.download_button(
                                "⬇️ Tải file SOP (PDF)",
                                data=f.read(),
                                file_name=os.path.basename(row["file_path"]),
                                mime="application/pdf",
                                key=f"download_{row['sop_id']}",
                            )
                    else:
                        st.warning("File gốc không còn tồn tại trên đĩa (đã bị xóa/di chuyển).")
