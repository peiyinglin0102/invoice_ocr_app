# -*- coding: utf-8 -*-
# Force reload: 3
import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time
from datetime import datetime
import tempfile
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

import importlib
import ocr_engine
import llm_processor
import finance_utils
import db_manager

# Force reload custom modules to completely bypass Streamlit's sticky in-memory cache!
importlib.reload(ocr_engine)
importlib.reload(llm_processor)
importlib.reload(finance_utils)
importlib.reload(db_manager)

from ocr_engine import InvoiceOCREngine
from llm_processor import LLMProcessor
from finance_utils import FinanceUtils
from db_manager import DatabaseManager

# ─────────────────────────────────────────────
# Initialize Database Manager
# ─────────────────────────────────────────────
db = DatabaseManager()

# ─────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="AI 智能外幣發票理財系統",
    layout="wide",
    page_icon="🧾",
)

# ─────────────────────────────────────────────
# Global CSS + Mobile/Touch Injections
# ─────────────────────────────────────────────
st.markdown("""
<style>
/* ── Google Font ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* ── All buttons ≥ 48px tall (WCAG 2.5.5 AA) ── */
button[kind="primary"], button[kind="secondary"] {
    min-height: 48px !important;
    font-size: 1rem !important;
    transition: background-color 0.1s ease, transform 0.1s ease !important;
}
button[kind="primary"]:active {
    transform: scale(0.97);
}

/* ── Dataframe horizontal scroll on mobile ── */
[data-testid="stDataFrame"] > div {
    overflow-x: auto !important;
    touch-action: pan-x !important;
}
[data-testid="stDataFrame"] table {
    min-width: 600px;
}
[data-testid="stDataFrame"] tbody tr {
    min-height: 44px !important;
}

/* ── Upload zone: ensure entire area is clickable ── */
[data-testid="stFileUploader"] > label {
    min-height: 48px !important;
    width: 100% !important;
    cursor: pointer;
}
[data-testid="stFileUploader"] {
    touch-action: manipulation;
}
[data-testid="stFileUploader"]:contextmenu {
    display: none;
}

/* ── Error messages ≥ 14px ── */
[data-testid="stAlert"] p {
    font-size: 14px !important;
}

/* ── Uploaded image responsive ── */
[data-testid="stImage"] img {
    max-width: 100% !important;
    height: auto !important;
}

/* ── Metric card TWD highlight ── */
.twd-highlight {
    font-size: 1.6rem;
    font-weight: 700;
    color: #E53E3E;
    margin-top: 4px;
}
.twd-label {
    font-size: 0.85rem;
    color: #718096;
    font-weight: 500;
}
</style>

<script>
// Inject accept + capture on file inputs for iOS Safari camera support
function patchFileInputs() {
    const inputs = document.querySelectorAll('input[type="file"]');
    inputs.forEach(function(input) {
        input.setAttribute('accept', 'image/*');
        // capture='environment' opens rear camera on mobile
        input.setAttribute('capture', 'environment');
    });
}
// Run on load and whenever DOM updates
document.addEventListener('DOMContentLoaded', function() {
    patchFileInputs();
    const observer = new MutationObserver(patchFileInputs);
    observer.observe(document.body, { childList: true, subtree: true });
});
</script>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# Session State Initialization
# ─────────────────────────────────────────────
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'active_trip_id' not in st.session_state:
    st.session_state.active_trip_id = None
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'error_msg' not in st.session_state:
    st.session_state.error_msg = None
if 'warning_msg' not in st.session_state:
    st.session_state.warning_msg = None
if 'info_msg' not in st.session_state:
    st.session_state.info_msg = None

# ─────────────────────────────────────────────
# Sidebar – Settings Panel & Trip Management
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 系統設定")

    # 1. Database indicator
    if db.use_mongodb:
        st.success("☁️ 雲端資料庫：MongoDB Atlas 已連線")
    else:
        st.info("📂 本地資料庫：使用 `local_db.json` 持久化儲存")

    st.markdown("---")
    st.markdown("#### ✈️ 旅遊專案切換")
    
    trips = db.get_trips()
    trip_options = {t["trip_id"]: f"{t['trip_name']} ({t['base_currency']})" for t in trips}
    
    if trips:
        if st.session_state.active_trip_id not in trip_options:
            st.session_state.active_trip_id = trips[0]["trip_id"]
            
        selected_trip_id = st.selectbox(
            "選擇現有的旅遊專案",
            options=list(trip_options.keys()),
            format_func=lambda x: trip_options[x],
            index=list(trip_options.keys()).index(st.session_state.active_trip_id),
            label_visibility="collapsed",
            key="active_trip_selectbox"
        )
        if selected_trip_id != st.session_state.active_trip_id:
            st.session_state.active_trip_id = selected_trip_id
            st.session_state.warning_msg = None
            st.session_state.info_msg = None
            st.rerun()
    else:
        st.warning("⚠️ 尚未建立任何專案，請在下方建立第一個專案")
        st.session_state.active_trip_id = None

    # Expander to create a new trip project
    with st.expander("➕ 建立新旅遊專案"):
        with st.form("new_trip_form", clear_on_submit=True):
            new_name = st.text_input("旅遊專案名稱", placeholder="例如：2026東京大縱走")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                new_start = st.date_input("開始日期")
            with col_d2:
                new_end = st.date_input("結束日期")
            new_currency = st.selectbox("主要外幣幣別", ["JPY", "KRW", "USD", "EUR", "GBP", "HKD", "SGD", "CNY"], index=0)
            new_budget = st.number_input("專案預算 (台幣 TWD)", min_value=100, value=50000, step=1000)
            
            submit_trip = st.form_submit_button("建立專案", use_container_width=True)
            if submit_trip:
                if not new_name.strip():
                    st.error("請輸入專案名稱！")
                elif new_start > new_end:
                    st.error("開始日期不能晚於結束日期！")
                else:
                    new_trip = db.create_trip(
                        name=new_name,
                        start_date=new_start.strftime("%Y-%m-%d"),
                        end_date=new_end.strftime("%Y-%m-%d"),
                        base_currency=new_currency,
                        budget_twd=new_budget
                    )
                    st.session_state.active_trip_id = new_trip["trip_id"]
                    st.success(f"✅ 專案 {new_name} 建立成功！")
                    time.sleep(0.5)
                    st.rerun()

    st.markdown("---")
    st.markdown("#### 🔑 Gemini API 金鑰")
    
    # 從 Streamlit Secrets 讀取 API Key
    env_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            env_key = st.secrets["GEMINI_API_KEY"].strip()
    except Exception:
        pass

    if env_key:
        st.success("🔑 API Key 已由 Secrets/環境變數自動載入")
        st.session_state.api_key = env_key
    else:
        api_key_input = st.text_input(
            "輸入 Gemini API Key",
            type="password",
            value=st.session_state.api_key.strip(),
            help="請輸入您的 Google Gemini API Key",
            label_visibility="collapsed",
        )
        if api_key_input.strip() != st.session_state.api_key.strip():
            st.session_state.api_key = api_key_input.strip()
            st.rerun()

    st.markdown("---")
    st.markdown("#### 🌐 發票語系")
    lang_options = {
        "🇯🇵 日文 (Japanese)": "japan",
        "🇰🇷 韓文 (Korean)": "korean",
        "🇬🇧 英文 (English)": "en",
        "🇨🇳 中文 (Chinese)": "ch",
    }
    lang_choice = st.selectbox(
        "選擇發票主要語系",
        options=list(lang_options.keys()),
        index=0,
        label_visibility="collapsed",
    )
    lang_code = lang_options[lang_choice]

# ─────────────────────────────────────────────
# Main Content Area
# ─────────────────────────────────────────────
st.title("🧾 AI 智能外幣發票理財系統")

# Get active trip doc
active_trip = None
if st.session_state.active_trip_id:
    active_trip = next((t for t in db.get_trips() if t["trip_id"] == st.session_state.active_trip_id), None)

if active_trip:
    st.markdown(f"📍 目前旅遊專案：**{active_trip['trip_name']}** (主要外幣: {active_trip['base_currency']} | 預算: NT$ {int(active_trip['budget_twd']):,})")
else:
    st.markdown("📸 拍照上傳發票，AI 自動辨識、翻譯、分類，並換算台幣消費金額。")
st.markdown("---")

if not active_trip:
    st.warning("👈 請先在側邊欄建立或選擇旅遊專案，即可開始記帳與辨識發票！")
    st.stop()

# ─────────────────────────────────────────────
# Load Cumulative Trip Data (Always loaded first to populate UI)
# ─────────────────────────────────────────────
invoices = db.get_invoices(st.session_state.active_trip_id)

# Recalculate stats
total_foreign_accumulated = 0.0
total_twd_accumulated = 0.0

for inv in invoices:
    if inv["currency"] == active_trip["base_currency"]:
        total_foreign_accumulated += inv["total_foreign_amount"]
    total_twd_accumulated += inv["total_twd"]

remaining_budget = float(active_trip["budget_twd"]) - total_twd_accumulated

# Flatten items for st.data_editor & Plotly Chart
flat_items = []
for inv in invoices:
    inv_id = inv["invoice_id"]
    rate = inv["exchange_rate"]
    inv_date = inv["invoice_date"]
    for idx, item in enumerate(inv.get("purchase_details", [])):
        flat_items.append({
            "invoice_id": inv_id,
            "item_index": idx,
            "original_name": item.get("original_name", ""),
            "translated_name": item.get("translated_name", ""),
            "unit_price": float(item.get("unit_price", 0)),
            "quantity": int(item.get("quantity", 1)),
            "tax_flag": item.get("tax_flag", ""),
            "category": item.get("category", "其他"),
            "twd_subtotal": int(round(float(item.get("unit_price", 0)) * int(item.get("quantity", 1)) * rate)),
            "invoice_date": inv_date,
            "rate": rate
        })

df_items_accumulated = pd.DataFrame(flat_items)

# ─────────────────────────────────────────────
# Metrics Cards (Unified at the Top)
# ─────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(
        label="📅 專案起訖日期",
        value=f"{active_trip['start_date']} ~ {active_trip['end_date']}",
    )
with col2:
    foreign_str = f"{total_foreign_accumulated:,.2f} {active_trip['base_currency']}"
    st.metric(label="💴 累積外幣消費", value=foreign_str)
with col3:
    st.metric(
        label="🏦 累積台幣消費",
        value=f"NT$ {int(total_twd_accumulated):,}"
    )
with col4:
    st.markdown('<p class="twd-label">🎯 預算剩餘額度</p>', unsafe_allow_html=True)
    color = "#E53E3E" if remaining_budget < 0 else "#38A169"
    st.markdown(
        f'<p class="twd-highlight" style="color: {color}">NT$ {int(remaining_budget):,}</p>',
        unsafe_allow_html=True,
    )

st.markdown("---")

# Show pipeline messages
if st.session_state.error_msg:
    st.error(st.session_state.error_msg)
    st.session_state.error_msg = None
if st.session_state.warning_msg:
    st.warning(st.session_state.warning_msg)
if st.session_state.info_msg:
    st.info(st.session_state.info_msg)

# ─────────────────────────────────────────────
# Main Panel Layout: Split Pie Chart & Upload Box Side-by-Side (UI/UX Optimization)
# ─────────────────────────────────────────────
col_left, col_right = st.columns([11, 9])

with col_left:
    st.markdown("### 🥧 旅程消費分類比例加總")
    if not df_items_accumulated.empty:
        CATEGORY_COLORS = {
            "醫療保健": "#68D391",
            "藥妝":     "#63B3ED",
            "零食/點心": "#F6AD55",
            "冷凍食品/冰品": "#76E4F7",
            "食品/飲料": "#FC8181",
            "交通":     "#B794F4",
            "餐飲":     "#F687B3",
            "其他":     "#CBD5E0",
        }

        # Aggregate by category
        pie_df = df_items_accumulated.groupby("category", as_index=False)["twd_subtotal"].sum()
        pie_df.columns = ["分類", "台幣金額"]

        color_sequence = [CATEGORY_COLORS.get(cat, "#CBD5E0") for cat in pie_df["分類"]]

        fig = px.pie(
            pie_df,
            values="台幣金額",
            names="分類",
            color="分類",
            color_discrete_sequence=color_sequence,
            height=360,
            hover_data=["台幣金額"],
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>累積金額：NT$ %{value:,}<br>佔比：%{percent}<extra></extra>",
        )
        fig.update_layout(
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
            margin=dict(l=0, r=0, t=10, b=40),
        )
        st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": False})
    else:
        st.info("ℹ️ 此專案目前尚無發票記錄，請在上傳區新增以產生圓餅圖！")

with col_right:
    st.markdown("### 📤 上傳發票圖片")
    uploaded_file = st.file_uploader(
        "支援格式：JPG / PNG / WebP ｜ 最大 10 MB",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False,
        label_visibility="collapsed",
        help="可點擊選擇，或直接拖曳圖片至此區域。行動裝置可直接開啟相機拍照上傳。",
    )

    if uploaded_file is not None:
        st.image(
            uploaded_file,
            caption=f"📎 已選擇發票 ｜ {uploaded_file.name}",
            width=200
        )

    has_api_key = bool(st.session_state.api_key.strip())
    is_disabled = (not has_api_key) or (uploaded_file is None) or st.session_state.processing
    start_btn = st.button(
        "🔍 開始辨識" if not st.session_state.processing else "⏳ 辨識中，請稍候...",
        disabled=is_disabled,
        type="primary",
        use_container_width=True,
    )

    if start_btn:
        st.session_state.processing = True
        st.session_state.error_msg = None
        st.session_state.warning_msg = None
        st.session_state.info_msg = None
        st.rerun()

# ─────────────────────────────────────────────
# Processing Pipeline Execution
# ─────────────────────────────────────────────
if st.session_state.processing and uploaded_file is not None:
    st.session_state.processing = False
    progress_bar = st.progress(0, text="準備開始...")
    status_container = st.status("⏳ 正在處理發票...", expanded=True)

    try:
        status_container.update(label="🔍 正在預處理影像與辨識發票文字...", state="running")
        progress_bar.progress(10, text="🔍 正在預處理影像與辨識發票文字...")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        ocr_engine = InvoiceOCREngine(lang=lang_code)
        raw_texts = ocr_engine.extract_text(tmp_path)

        try:
            os.remove(tmp_path)
        except OSError:
            pass

        progress_bar.progress(33, text="🔍 OCR 文字擷取完成")

        if not raw_texts:
            raise ValueError("ERR-002: OCR 未擷取到任何文字")

        status_container.update(label="🤖 AI 正在清洗雜訊、分析品項並翻譯...", state="running")
        progress_bar.progress(40, text="🤖 AI 正在清洗雜訊、分析品項並翻譯...")

        llm = LLMProcessor(api_key=st.session_state.api_key.strip())

        try:
            result_dict = llm.process_ocr_texts(raw_texts)
        except ValueError as e:
            if "ERR-003" in str(e):
                status_container.write("⚠️ JSON 解析失敗，正在重試...")
                time.sleep(1)
                result_dict = llm.process_ocr_texts(raw_texts)
            else:
                raise

        progress_bar.progress(66, text="🤖 LLM 分析完成")

        status_container.update(label="💱 正在查詢歷史匯率並換算台幣...", state="running")
        progress_bar.progress(70, text="💱 正在查詢歷史匯率並換算台幣...")

        raw_date = result_dict.get("invoice_date", "")
        date_str = ""
        is_fallback_date = False
        if raw_date and raw_date.strip():
            try:
                datetime.strptime(raw_date.strip(), "%Y-%m-%d")
                date_str = raw_date.strip()
            except ValueError:
                date_str = ""
        
        # Date backtracking logic
        if not date_str:
            date_str = active_trip["start_date"]
            is_fallback_date = True
            st.session_state.info_msg = "ℹ️ 無法識別發票日期，已採用旅遊首日匯率計算"

        currency = (result_dict.get("currency") or active_trip["base_currency"]).strip().upper()

        rate_result = FinanceUtils.get_historical_exchange_rate(currency, "TWD", date_str)
        is_fallback_rate = False
        if isinstance(rate_result, tuple):
            rate_val, is_fallback_rate = rate_result
        else:
            rate_val = float(rate_result)

        if is_fallback_rate:
            st.session_state.warning_msg = (
                f"⚠️ ERR-005：yfinance 匯率查詢失敗，目前使用估算匯率 "
                f"（1 {currency} ≈ {rate_val} TWD），數據僅供參考。"
            )

        items = result_dict.get("items", [])
        df = pd.DataFrame(items)

        if not df.empty:
            df["unit_price"] = pd.to_numeric(df.get("unit_price", 0), errors="coerce").fillna(0)
            df["quantity"] = pd.to_numeric(df.get("quantity", 1), errors="coerce").fillna(1)
            df["twd_subtotal"] = (df["unit_price"] * df["quantity"] * rate_val).round().astype(int)
            for col in ["original_name", "translated_name", "tax_flag", "category"]:
                if col not in df.columns:
                    df[col] = ""
            total_twd = int(df["twd_subtotal"].sum())
        else:
            total_twd = 0

        progress_bar.progress(100, text="✅ 處理完成！")

        # Save to database
        items_list = df.to_dict(orient="records") if not df.empty else []
        invoice_doc = {
            "invoice_id": str(uuid.uuid4()),
            "trip_id": st.session_state.active_trip_id,
            "invoice_date": date_str,
            "currency": currency,
            "exchange_rate": rate_val,
            "total_foreign_amount": float(result_dict.get("total_foreign_amount", 0)),
            "total_twd": float(total_twd),
            "purchase_details": items_list,
            "uploaded_at": datetime.utcnow().isoformat() + "Z"
        }
        db.save_invoice(invoice_doc)

        status_container.update(label="✅ 發票上傳並持久化保存成功！", state="complete")
        st.session_state.processing = False
        st.rerun()

    except Exception as e:
        err_msg = str(e)
        st.session_state.processing = False
        status_container.update(label="❌ 處理失敗", state="error")

        if "ERR-002" in err_msg:
            st.session_state.error_msg = (
                "❌ ERR-002：OCR 無法提取任何文字。圖片可能過於模糊或角度不佳，請重新拍攝。"
            )
        elif "ERR-003" in err_msg:
            st.session_state.error_msg = (
                "❌ ERR-003：AI 回傳的 JSON 格式損毀，已重試仍失敗。請稍後再試。"
            )
        elif "ERR-004" in err_msg:
            st.session_state.error_msg = f"❌ {err_msg}"
        else:
            st.session_state.error_msg = f"❌ 系統發生未預期錯誤：{err_msg}"
        st.rerun()

# ─────────────────────────────────────────────
# Cumulative Details Table & Save Section (Moved Neatly to the Bottom)
# ─────────────────────────────────────────────
if not df_items_accumulated.empty:
    st.markdown("---")
    st.markdown("### 🛒 專案累積購買明細表格")
    st.info("💡 雙擊任一欄位即可直接編輯修正，支援在底部直接點擊 ➕ 新增項目，或點擊左側 🗑️ 刪除。完成後請務必點擊下方 **💾 儲存變更** 按鈕！")

    # Use st.data_editor to edit items in place
    edited_df = st.data_editor(
        df_items_accumulated,
        width="stretch",
        column_config={
            "invoice_id": None,      # Hide invoice UUID
            "item_index": None,      # Hide index
            "rate": None,            # Hide conversion rate
            "original_name": st.column_config.TextColumn("原始文字", width="medium"),
            "translated_name": st.column_config.TextColumn("品項翻譯", width="large"),
            "unit_price": st.column_config.NumberColumn("單價(外幣)", format="%.2f"),
            "quantity": st.column_config.NumberColumn("數量", format="%d"),
            "tax_flag": st.column_config.TextColumn("稅務標記", width="small"),
            "category": st.column_config.SelectboxColumn(
                "分類",
                options=["醫療保健", "藥妝", "零食/點心", "冷凍食品/冰品", "食品/飲料", "交通", "餐飲", "其他"],
                width="medium"
            ),
            "invoice_date": st.column_config.TextColumn("發票日期", width="medium"),
            "twd_subtotal": st.column_config.NumberColumn("台幣小計 (NT$)", format="%d", disabled=True),
        },
        num_rows="dynamic",
        key="cumulative_items_editor"
    )

    # Database synchronization save button
    col_save, _ = st.columns([1, 4])
    with col_save:
        save_btn = st.button("💾 儲存變更並更新資料庫", type="primary", use_container_width=True)

    if save_btn:
        with st.spinner("正在將變更儲存至資料庫..."):
            edited_invoices = {}
            new_rows = []

            for idx, row in edited_df.iterrows():
                row_dict = row.to_dict()
                inv_id = row_dict.get("invoice_id")
                
                if pd.isna(inv_id) or not inv_id:
                    new_rows.append(row_dict)
                    continue

                if inv_id not in edited_invoices:
                    edited_invoices[inv_id] = []
                
                edited_invoices[inv_id].append(row_dict)

            # Read all current invoices
            for inv in invoices:
                inv_id = inv["invoice_id"]
                rate = inv["exchange_rate"]
                
                if inv_id not in edited_invoices:
                    db.delete_invoice(inv_id)
                else:
                    raw_items = edited_invoices[inv_id]
                    updated_items = []
                    new_foreign_total = 0.0
                    new_twd_total = 0.0

                    for item in raw_items:
                        u_price = float(item["unit_price"])
                        qty = int(item["quantity"])
                        sub_twd = int(round(u_price * qty * rate))
                        
                        updated_items.append({
                            "original_name": str(item["original_name"]),
                            "translated_name": str(item["translated_name"]),
                            "unit_price": u_price,
                            "quantity": qty,
                            "tax_flag": str(item["tax_flag"]),
                            "category": str(item["category"]),
                            "twd_subtotal": sub_twd
                        })
                        new_foreign_total += (u_price * qty)
                        new_twd_total += sub_twd

                    db.update_invoice_items(inv_id, updated_items, new_foreign_total, new_twd_total)

            # Manual additions
            if new_rows:
                new_items_list = []
                total_new_foreign = 0.0
                total_new_twd = 0.0
                default_rate, _ = FinanceUtils.get_historical_exchange_rate(active_trip["base_currency"], "TWD", active_trip["start_date"])

                for row in new_rows:
                    u_price = float(row.get("unit_price") or 0.0)
                    qty = int(row.get("quantity") or 1)
                    sub_twd = int(round(u_price * qty * default_rate))

                    new_items_list.append({
                        "original_name": str(row.get("original_name") or "手動新增品項"),
                        "translated_name": str(row.get("translated_name") or "手動新增品項"),
                        "unit_price": u_price,
                        "quantity": qty,
                        "tax_flag": str(row.get("tax_flag") or ""),
                        "category": str(row.get("category") or "其他"),
                        "twd_subtotal": sub_twd
                    })
                    total_new_foreign += (u_price * qty)
                    total_new_twd += sub_twd

                manual_invoice_doc = {
                    "invoice_id": str(uuid.uuid4()),
                    "trip_id": st.session_state.active_trip_id,
                    "invoice_date": active_trip["start_date"],
                    "currency": active_trip["base_currency"],
                    "exchange_rate": default_rate,
                    "total_foreign_amount": total_new_foreign,
                    "total_twd": total_new_twd,
                    "purchase_details": new_items_list,
                    "uploaded_at": datetime.utcnow().isoformat() + "Z"
                }
                db.save_invoice(manual_invoice_doc)

            st.success("✅ 雲端資料庫更新成功，所有變更已順利儲存！")
            time.sleep(0.5)
            st.rerun()

    # ── Export Section ──
    st.markdown("---")
    st.markdown("### 💾 匯出專案帳目報告")

    export_df = df_items_accumulated.rename(columns={
        "original_name":  "原始文字",
        "translated_name": "品項翻譯",
        "unit_price":     "單價(外幣)",
        "quantity":       "數量",
        "tax_flag":       "稅務標記",
        "category":       "分類",
        "twd_subtotal":   "台幣小計(NT$)",
        "invoice_date":   "消費日期",
    })

    csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            label="⬇️ 下載專案累積 CSV（Excel 相容）",
            data=csv_bytes,
            file_name=f"trip_report_{active_trip['trip_name']}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_dl2:
        export_json = {
            "trip_info": active_trip,
            "invoices": invoices,
            "total_twd_accumulated": total_twd_accumulated,
            "remaining_budget_twd": remaining_budget
        }
        json_str = json.dumps(export_json, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ 下載專案完整 JSON 資料",
            data=json_str,
            file_name=f"trip_report_{active_trip['trip_name']}.json",
            mime="application/json",
            use_container_width=True,
        )
