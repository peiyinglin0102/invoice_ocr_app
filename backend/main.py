# -*- coding: utf-8 -*-
"""
FastAPI Backend — AI 智能外幣發票理財系統
路由：POST /api/process_invoice
"""
import sys, os
# ensure root-level modules (ocr_engine, llm_processor, finance_utils) are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import logging
import tempfile
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ocr_engine import InvoiceOCREngine
from llm_processor import LLMProcessor
from finance_utils import FinanceUtils

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
app = FastAPI(title="AI Invoice API", version="1.0.0")

# Allow Vite dev server (port 3000 / 5173) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Response Models
# ─────────────────────────────────────────────
class ItemResult(BaseModel):
    original_name: str
    translated_name: str
    unit_price: float
    quantity: float
    tax_flag: str
    category: str
    twd_subtotal: int

class InvoiceResult(BaseModel):
    invoice_date: str
    currency: str
    exchange_rate: float
    is_fallback_rate: bool
    total_foreign_amount: float
    total_twd: int
    items: list[ItemResult]

class ProcessResponse(BaseModel):
    success: bool
    data: Optional[InvoiceResult] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

# ─────────────────────────────────────────────
# Endpoint
# ─────────────────────────────────────────────
@app.post("/api/process_invoice", response_model=ProcessResponse)
async def process_invoice(
    file: UploadFile = File(...),
    api_key: Optional[str] = Form(None),
    ocr_lang: str = Form("japan"),
):
    """
    一條龍發票處理管線：
    1. 影像預處理 + PaddleOCR 文字擷取
    2. Gemini LLM 清洗/翻譯/分類
    3. yfinance 匯率取得 + 台幣換算
    """
    t0 = time.time()

    # 讀取傳入金鑰
    resolved_api_key = (api_key or "").strip()
    
    # ── 安全性：不接受 API key 為空 ──
    if not resolved_api_key or resolved_api_key == "undefined":
        raise HTTPException(status_code=400, detail="ERR-004: API Key 未提供")

    # ── ERR-001：格式驗證 ──
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=422,
            detail=f"ERR-001: 不支援的檔案格式 ({file.content_type})，請上傳 JPG/PNG/WebP。",
        )

    raw_bytes = await file.read()

    # ERR-001：大小驗證
    if len(raw_bytes) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="ERR-001: 檔案大小超過 10MB 上限。",
        )

    # ── Stage 1：OCR ──
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        ocr = InvoiceOCREngine(lang=ocr_lang)
        raw_texts = ocr.extract_text(tmp_path)
        logger.info(f"[OCR] {len(raw_texts)} blocks in {time.time()-t0:.2f}s")
    finally:
        # 立即從磁碟刪除（安全性要求）
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        # 釋放記憶體 buffer
        del raw_bytes

    if not raw_texts:
        raise HTTPException(
            status_code=422,
            detail="ERR-002: OCR 無法提取任何文字，圖片可能過於模糊，請重新拍攝。",
        )

    # ── Stage 2：LLM ──
    t1 = time.time()
    llm = LLMProcessor(api_key=resolved_api_key)
    try:
        result_dict = llm.process_ocr_texts(raw_texts)
    except ValueError as e:
        err_str = str(e)
        if "ERR-003" in err_str:
            # Retry once
            import asyncio
            await asyncio.sleep(1)
            result_dict = llm.process_ocr_texts(raw_texts)
        elif "ERR-004" in err_str:
            raise HTTPException(status_code=401, detail=err_str)
        else:
            raise HTTPException(status_code=500, detail=err_str)

    logger.info(f"[LLM] done in {time.time()-t1:.2f}s")

    # ── Stage 3：匯率 ──
    t2 = time.time()
    raw_date = (result_dict.get("invoice_date") or "").strip()
    date_str = ""
    if raw_date:
        try:
            datetime.strptime(raw_date, "%Y-%m-%d")
            date_str = raw_date
        except ValueError:
            date_str = ""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    currency = (result_dict.get("currency") or "JPY").strip().upper()
    rate_val, is_fallback = FinanceUtils.get_historical_exchange_rate(currency, "TWD", date_str)
    logger.info(f"[Rate] 1 {currency} = {rate_val:.4f} TWD  fallback={is_fallback}  ({time.time()-t2:.2f}s)")

    # ── Assemble Items ──
    items_raw = result_dict.get("items", [])
    items_out: list[ItemResult] = []
    total_twd = 0
    for item in items_raw:
        unit_price = float(item.get("unit_price") or 0)
        quantity   = float(item.get("quantity") or 1)
        subtotal   = int(round(unit_price * quantity * rate_val))
        total_twd += subtotal
        items_out.append(ItemResult(
            original_name=item.get("original_name", ""),
            translated_name=item.get("translated_name", ""),
            unit_price=unit_price,
            quantity=quantity,
            tax_flag=item.get("tax_flag", "") or "",
            category=item.get("category", "其他"),
            twd_subtotal=subtotal,
        ))

    result = InvoiceResult(
        invoice_date=date_str,
        currency=currency,
        exchange_rate=round(rate_val, 6),
        is_fallback_rate=is_fallback,
        total_foreign_amount=float(result_dict.get("total_foreign_amount") or 0),
        total_twd=total_twd,
        items=items_out,
    )

    logger.info(f"[E2E] Total time: {time.time()-t0:.2f}s")
    return ProcessResponse(success=True, data=result)


@app.get("/api/health")
def health():
    return {"status": "ok"}
