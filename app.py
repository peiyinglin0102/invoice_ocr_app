# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import json
import time
from datetime import datetime
import tempfile
import os
from dotenv import load_dotenv

load_dotenv()

from ocr_engine import InvoiceOCREngine
from llm_processor import LLMProcessor
from finance_utils import FinanceUtils

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
    st.session_state.api_key = os.getenv("GEMINI_API_KEY", "")
if 'result_json' not in st.session_state:
    st.session_state.result_json = None
if 'df_items' not in st.session_state:
    st.session_state.df_items = None
if 'metrics' not in st.session_state:
    st.session_state.metrics = None
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'error_msg' not in st.session_state:
    st.session_state.error_msg = None
if 'error_type' not in st.session_state:
    st.session_state.error_type = None

# ─────────────────────────────────────────────
# Sidebar – Settings Panel
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ 系統設定")

    st.markdown("#### 🔑 Gemini API Key")
    # 取得當前有效的金鑰（優先使用手動輸入的，手動輸入空白則嘗試載入環境變數）
    current_key = st.session_state.api_key.strip()
    if not current_key:
        current_key = os.getenv("GEMINI_API_KEY", "").strip()

    api_key_input = st.text_input(
        "Gemini API Key",
        type="password",
        value=current_key,
        help="請輸入您的 Google Gemini API Key（若留空將自動讀取 .env 的金鑰）",
        label_visibility="collapsed",
    )
    if api_key_input.strip() != st.session_state.api_key.strip():
        st.session_state.api_key = api_key_input.strip()

    # 顯示狀態
    display_key = st.session_state.api_key.strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if display_key:
        st.success("✅ API Key 已設定")
    else:
        st.warning("⚠️ 尚未設定 API Key")

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

    st.markdown("---")
    st.markdown("#### 📋 使用說明")
    st.markdown("""
1. 輸入 Gemini API Key
2. 選擇發票語系
3. 上傳發票圖片
4. 點擊「開始辨識」
5. 查看分析結果並匯出
""")

# ─────────────────────────────────────────────
# Main Content Area
# ─────────────────────────────────────────────
st.title("🧾 AI 智能外幣發票理財系統")
st.markdown("拍照上傳發票，AI 自動辨識、翻譯、分類，並換算台幣消費金額。")
st.markdown("---")

# ── Upload Section ──
st.markdown("### 📤 上傳發票圖片")
uploaded_file = st.file_uploader(
    "支援格式：JPG / PNG / WebP　｜　最大 10 MB",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=False,
    help="可點擊選擇，或直接拖曳圖片至此區域。行動裝置可直接開啟相機拍照上傳。",
)

if uploaded_file is not None:
    if uploaded_file.size > 10 * 1024 * 1024:
        st.warning("⚠️ ERR-001：檔案大小超過 10MB 上限，請壓縮後重新上傳。")
        uploaded_file = None
    else:
        st.image(
            uploaded_file,
            caption=f"📎 已上傳發票預覽 ｜ {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)",
            use_container_width=True,
        )

# ─────────────────────────────────────────────
# Button State Machine
# ─────────────────────────────────────────────
has_api_key = bool(st.session_state.api_key.strip() or os.getenv("GEMINI_API_KEY", "").strip())
is_disabled = (not has_api_key) or (uploaded_file is None) or st.session_state.processing
start_btn = st.button(
    "🔍 開始辨識" if not st.session_state.processing else "⏳ 辨識中，請稍候...",
    disabled=is_disabled,
    type="primary",
    use_container_width=True,
)

# Show persisted error (after rerun)
if st.session_state.error_msg:
    st.error(st.session_state.error_msg)
    st.session_state.error_msg = None

if start_btn:
    st.session_state.processing = True
    st.session_state.result_json = None
    st.session_state.df_items = None
    st.session_state.metrics = None
    st.session_state.error_msg = None
    st.rerun()

# ─────────────────────────────────────────────
# Processing Pipeline
# ─────────────────────────────────────────────
if st.session_state.processing and uploaded_file is not None:
    progress_bar = st.progress(0, text="準備開始...")
    status_container = st.status("⏳ 正在處理發票...", expanded=True)

    try:
        # ── Stage 1: Image Preprocessing + OCR ──
        status_container.update(label="🔍 正在預處理影像與辨識發票文字...", state="running")
        progress_bar.progress(10, text="🔍 正在預處理影像與辨識發票文字...")

        # Write temp file (will be deleted immediately after OCR)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        ocr_engine = InvoiceOCREngine(lang=lang_code)
        raw_texts = ocr_engine.extract_text(tmp_path)

        # Immediately remove temp file from disk (security requirement)
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        progress_bar.progress(33, text="🔍 OCR 文字擷取完成")

        if not raw_texts:
            raise ValueError("ERR-002: OCR 未擷取到任何文字")

        # ── Stage 2: LLM Cleaning + Translation ──
        status_container.update(label="🤖 AI 正在清洗雜訊、分析品項並翻譯...", state="running")
        progress_bar.progress(40, text="🤖 AI 正在清洗雜訊、分析品項並翻譯...")

        # 解析有效金鑰：優先使用 UI 手動輸入，若無則讀取 .env
        effective_key = st.session_state.api_key.strip()
        if not effective_key:
            effective_key = os.getenv("GEMINI_API_KEY", "").strip()

        llm = LLMProcessor(api_key=effective_key)

        try:
            result_dict = llm.process_ocr_texts(raw_texts)
        except ValueError as e:
            if "ERR-003" in str(e):
                # Retry once per spec
                status_container.write("⚠️ JSON 解析失敗，正在重試...")
                time.sleep(1)
                result_dict = llm.process_ocr_texts(raw_texts)
            else:
                raise

        progress_bar.progress(66, text="🤖 LLM 分析完成")

        # ── Stage 3: Exchange Rate + Calculation ──
        status_container.update(label="💱 正在查詢歷史匯率並換算台幣...", state="running")
        progress_bar.progress(70, text="💱 正在查詢歷史匯率並換算台幣...")

        raw_date = result_dict.get("invoice_date", "")
        # Validate and normalise date string
        date_str = ""
        if raw_date and raw_date.strip():
            try:
                datetime.strptime(raw_date.strip(), "%Y-%m-%d")
                date_str = raw_date.strip()
            except ValueError:
                date_str = ""
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        currency = (result_dict.get("currency") or "JPY").strip().upper()

        rate_result = FinanceUtils.get_historical_exchange_rate(currency, "TWD", date_str)
        is_fallback = False
        if isinstance(rate_result, tuple):
            rate_val, is_fallback = rate_result
        else:
            rate_val = float(rate_result)

        if is_fallback:
            st.warning(
                f"⚠️ ERR-005：yfinance 匯率查詢失敗，目前使用估算匯率 "
                f"（1 {currency} ≈ {rate_val} TWD），數據僅供參考。"
            )

        # ── Build DataFrame ──
        items = result_dict.get("items", [])
        df = pd.DataFrame(items)

        if not df.empty:
            df["unit_price"] = pd.to_numeric(df.get("unit_price", 0), errors="coerce").fillna(0)
            df["quantity"] = pd.to_numeric(df.get("quantity", 1), errors="coerce").fillna(1)
            df["twd_subtotal"] = (df["unit_price"] * df["quantity"] * rate_val).round().astype(int)
            # Ensure required columns exist
            for col in ["original_name", "translated_name", "tax_flag", "category"]:
                if col not in df.columns:
                    df[col] = ""
            total_twd = int(df["twd_subtotal"].sum())
        else:
            total_twd = 0
            df = pd.DataFrame(
                columns=["original_name", "translated_name", "unit_price", "quantity", "tax_flag", "category", "twd_subtotal"]
            )

        progress_bar.progress(100, text="✅ 處理完成！")

        # Store results in session (no disk write)
        st.session_state.result_json = result_dict
        st.session_state.df_items = df
        st.session_state.metrics = {
            "date": date_str,
            "foreign_total": result_dict.get("total_foreign_amount", 0),
            "currency": currency,
            "rate": rate_val,
            "total_twd": total_twd,
        }

        status_container.update(label="✅ 辨識成功！結果如下。", state="complete")
        st.success("✅ 發票辨識與分析已完成！請查看下方結果。")
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
        elif "ERR-004" in err_msg or "API_KEY_INVALID" in err_msg or "invalid" in err_msg.lower():
            st.session_state.error_msg = (
                "❌ ERR-004：Gemini API 驗證失敗。請確認側欄中的 API Key 是否正確填寫。"
            )
        else:
            st.session_state.error_msg = f"❌ 系統發生未預期錯誤：{err_msg}"
        st.rerun()

# ─────────────────────────────────────────────
# Results Rendering
# ─────────────────────────────────────────────
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

if st.session_state.df_items is not None and st.session_state.metrics is not None:
    st.markdown("---")
    st.subheader("📊 財務分析報告")

    m = st.session_state.metrics

    # ── Edit Base Info Expander ──
    with st.expander("📝 修正基本資訊 (發票日期、幣別、匯率)"):
        col_e1, col_e2, col_e3 = st.columns(3)
        with col_e1:
            try:
                current_date = datetime.strptime(m["date"], "%Y-%m-%d").date()
            except Exception:
                current_date = datetime.today().date()
            new_date = st.date_input("消費日期", value=current_date, key="edit_date_input")
            new_date_str = new_date.strftime("%Y-%m-%d")
        with col_e2:
            new_currency = st.text_input("外幣幣別", value=m["currency"], key="edit_currency_input").strip().upper()
        with col_e3:
            new_rate = st.number_input("適用匯率", value=float(m["rate"]), format="%.6f", min_value=0.000001, key="edit_rate_input")
            
        if new_date_str != m["date"] or new_currency != m["currency"] or new_rate != m["rate"]:
            st.session_state.metrics["date"] = new_date_str
            st.session_state.metrics["currency"] = new_currency
            st.session_state.metrics["rate"] = new_rate
            if st.session_state.result_json:
                st.session_state.result_json["invoice_date"] = new_date_str
                st.session_state.result_json["currency"] = new_currency
            
            # Recalculate TWD subtotals and TWD total
            st.session_state.df_items["twd_subtotal"] = (st.session_state.df_items["unit_price"] * st.session_state.df_items["quantity"] * new_rate).round().astype(int)
            st.session_state.metrics["total_twd"] = int(st.session_state.df_items["twd_subtotal"].sum())
            st.rerun()

    # ── Metrics Cards ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="📅 消費日期",
            value=m["date"] if m["date"] else "—",
        )
    with col2:
        foreign_str = f"{m['foreign_total']:,} {m['currency']}"
        st.metric(label="💴 外幣總額", value=foreign_str)
    with col3:
        st.metric(label="📈 適用匯率", value=f"{m['rate']:.4f}")
    with col4:
        st.markdown('<p class="twd-label">🏦 台幣總花費</p>', unsafe_allow_html=True)
        st.markdown(
            f'<p class="twd-highlight">NT$ {m["total_twd"]:,}</p>',
            unsafe_allow_html=True,
        )

    # ── Purchase Details Table ──
    st.markdown("### 🛒 購買明細表格")
    st.info("💡 雙擊任一欄位即可直接編輯修正。若辨識結果有微小誤差，您可在此手動調整！")

    # Use st.data_editor to edit st.session_state.df_items in place
    edited_df = st.data_editor(
        st.session_state.df_items,
        use_container_width=True,
        column_config={
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
            "twd_subtotal": st.column_config.NumberColumn("台幣小計 (NT$)", format="%d", disabled=True),
        },
        num_rows="dynamic",
        key="invoice_items_editor"
    )

    # Detect changes and recalculate subtotals/totals
    if not edited_df.equals(st.session_state.df_items):
        edited_df["unit_price"] = pd.to_numeric(edited_df["unit_price"], errors="coerce").fillna(0)
        edited_df["quantity"] = pd.to_numeric(edited_df["quantity"], errors="coerce").fillna(1)
        edited_df["twd_subtotal"] = (edited_df["unit_price"] * edited_df["quantity"] * m["rate"]).round().astype(int)
        
        st.session_state.df_items = edited_df.copy()
        
        # Recalculate totals
        new_foreign_total = float((st.session_state.df_items["unit_price"] * st.session_state.df_items["quantity"]).sum())
        new_twd_total = int(st.session_state.df_items["twd_subtotal"].sum())
        
        st.session_state.metrics["foreign_total"] = new_foreign_total
        st.session_state.metrics["total_twd"] = new_twd_total
        
        if st.session_state.result_json:
            st.session_state.result_json["items"] = st.session_state.df_items.to_dict(orient="records")
            st.session_state.result_json["total_foreign_amount"] = new_foreign_total
            
        st.rerun()

    # ── Pie Chart ──
    if not st.session_state.df_items.empty:
        st.markdown("### 🥧 本次消費分類比例")

        # Aggregate by category → sum of twd_subtotal
        pie_df = (
            st.session_state.df_items
            .groupby("category", as_index=False)["twd_subtotal"]
            .sum()
        )
        pie_df.columns = ["分類", "台幣金額"]

        # Assign consistent colours from palette
        color_sequence = [CATEGORY_COLORS.get(cat, "#CBD5E0") for cat in pie_df["分類"]]

        fig = px.pie(
            pie_df,
            values="台幣金額",
            names="分類",
            title="本次消費分類比例",
            color="分類",
            color_discrete_sequence=color_sequence,
            height=400,
            hover_data=["台幣金額"],
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>金額：NT$ %{value:,}<br>佔比：%{percent}<extra></extra>",
        )
        fig.update_layout(
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02,
            ),
            margin=dict(l=0, r=160, t=40, b=0),
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"scrollZoom": False},
        )

    # ── Export Section ──
    st.markdown("### 💾 匯出報告")

    # Build export dataframe (all columns including original_name)
    export_df = st.session_state.df_items.rename(columns={
        "original_name":  "原始文字",
        "translated_name": "品項翻譯",
        "unit_price":     f"單價({m['currency']})",
        "quantity":       "數量",
        "tax_flag":       "稅務標記",
        "category":       "分類",
        "twd_subtotal":   "台幣小計(NT$)",
    })

    # UTF-8 BOM for Excel compatibility
    csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")

    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        st.download_button(
            label="⬇️ 下載 CSV（Excel 相容）",
            data=csv_bytes,
            file_name=f"invoice_{m['date']}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_dl2:
        # Attach exchange rate and TWD total to JSON export
        export_json = dict(st.session_state.result_json)
        export_json["exchange_rate"] = m["rate"]
        export_json["total_twd"] = m["total_twd"]
        json_str = json.dumps(export_json, ensure_ascii=False, indent=2)
        st.download_button(
            label="⬇️ 下載 JSON",
            data=json_str,
            file_name=f"invoice_{m['date']}.json",
            mime="application/json",
            use_container_width=True,
        )
