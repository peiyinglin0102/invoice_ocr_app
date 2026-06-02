# -*- coding: utf-8 -*-
import os
import tempfile
import cv2
import numpy as np
from paddleocr import PaddleOCR
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InvoiceOCREngine:
    """
    PaddleOCR 2.x 文字擷取引擎（穩定版）。

    使用 paddlepaddle==2.6.2 + paddleocr==2.8.3：
    - 穩定 API：ocr(img_path, cls=True)
    - 無 Windows oneDNN NotImplementedError 問題
    - 回傳格式：[[[bbox, (text, confidence)], ...]]

    策略：
    1. 直接使用原始影像路徑（PaddleOCR 深度學習對自然拍攝照片效果最佳）
    2. 僅在原圖無結果時，做 CLAHE 輕量亮度增強後重試
    """

    # 信心門檻
    CONFIDENCE_THRESHOLD = 0.6

    def __init__(self, lang: str = "japan"):
        logger.info(f"Initializing PaddleOCR with language: {lang}")
        self.ocr = PaddleOCR(use_angle_cls=True, lang=lang)
        logger.info("PaddleOCR initialized successfully.")

    # ─────────────────────────────────────────
    # 影像輕量增強（備用，僅在必要時使用）
    # ─────────────────────────────────────────
    def _enhance_image(self, image_path: str) -> str:
        """
        CLAHE 自適應直方圖均衡化：增強亮度對比，不破壞文字形狀。
        回傳暫存檔路徑（呼叫端負責刪除）。
        """
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read image at path: {image_path}")

        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_ch, a_ch, b_ch = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_ch = clahe.apply(l_ch)
        lab = cv2.merge([l_ch, a_ch, b_ch])
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        cv2.imwrite(tmp.name, enhanced)
        tmp.close()
        logger.info(f"CLAHE-enhanced image saved to: {tmp.name}")
        return tmp.name

    # ─────────────────────────────────────────
    # PaddleOCR 2.x 結果解析
    # ─────────────────────────────────────────
    def _parse_result(self, result) -> list[dict]:
        """
        解析 paddleocr 2.x ocr() 回傳結果。
        格式：[[[bbox, (text, confidence)], ...]]
        回傳 [{'text': text, 'confidence': conf, 'box': bbox}, ...]
        """
        parsed_items = []
        if not result:
            return parsed_items

        pages = result if isinstance(result[0], list) else [result]
        for page in pages:
            if not page:
                continue
            for line in page:
                try:
                    bbox = line[0]
                    text_conf = line[1]
                    if isinstance(text_conf, (list, tuple)) and len(text_conf) == 2:
                        text, confidence = text_conf
                        if text and str(text).strip():
                            parsed_items.append({
                                "text": str(text).strip(),
                                "confidence": float(confidence),
                                "box": bbox
                            })
                except (IndexError, TypeError, ValueError) as e:
                    logger.debug(f"Skipping unparseable line: {line} — {e}")
        return parsed_items

    # ─────────────────────────────────────────
    # OCR 主流程
    # ─────────────────────────────────────────
    def extract_text(self, image_path: str) -> list[str]:
        """
        執行 OCR 文字擷取：
        1. 對原始影像執行 OCR（最佳品質）
        2. 若無結果，做 CLAHE 增強後重試
        回傳高信心度的文字字串列表。
        """
        logger.info(f"Starting OCR extraction on: {image_path}")
        enhanced_path = None
        try:
            # ── Pass 1：原始影像 ──
            logger.info("Pass 1: OCR on original image...")
            result = self.ocr.ocr(image_path, cls=True)
            parsed = self._parse_result(result)

            # 為了讓 LLM 能在排版混亂的收據上（例如置物櫃收據、橫向排版）正確關聯品項名稱與金額，
            # 我們將包含位置座標（Bounding Box 的頂部中點與左側中點）編碼進 OCR 回傳的文字串中，
            # 格式範例：[x:120, y:300] "Total Amount"
            # 這樣既不破壞舊有函式回傳 list[str] 的簽章，也能提供 LLM 強大的 2D 佈局推理能力！
            
            raw_texts = []
            for item in parsed:
                if item["confidence"] > self.CONFIDENCE_THRESHOLD:
                    box = item["box"]
                    # 計算 bounding box 的中心 Y 座標與最左邊的 X 座標以利 LLM 排版對齊
                    ys = [pt[1] for pt in box]
                    xs = [pt[0] for pt in box]
                    y_coord = int(sum(ys) / len(ys))
                    x_coord = int(min(xs))
                    raw_texts.append(f"[y:{y_coord}, x:{x_coord}] {item['text']}")
            
            logger.info(f"Pass 1: {len(parsed)} detected, {len(raw_texts)} above threshold {self.CONFIDENCE_THRESHOLD}.")

            # ── Pass 2：CLAHE 增強（僅在完全無結果時）──
            if not raw_texts:
                logger.info("Pass 1 yielded nothing. Trying CLAHE-enhanced image...")
                enhanced_path = self._enhance_image(image_path)
                result2 = self.ocr.ocr(enhanced_path, cls=True)
                parsed2 = self._parse_result(result2)
                for item in parsed2:
                    if item["confidence"] > self.CONFIDENCE_THRESHOLD:
                        box = item["box"]
                        ys = [pt[1] for pt in box]
                        xs = [pt[0] for pt in box]
                        y_coord = int(sum(ys) / len(ys))
                        x_coord = int(min(xs))
                        raw_texts.append(f"[y:{y_coord}, x:{x_coord}] {item['text']}")

                # 若仍為空，降低門檻保留部分結果
                if not raw_texts and parsed2:
                    logger.warning("Still empty after enhancement. Lowering threshold to 0.3.")
                    for item in parsed2:
                        if item["confidence"] > 0.3:
                            box = item["box"]
                            ys = [pt[1] for pt in box]
                            xs = [pt[0] for pt in box]
                            y_coord = int(sum(ys) / len(ys))
                            x_coord = int(min(xs))
                            raw_texts.append(f"[y:{y_coord}, x:{x_coord}] {item['text']}")

            logger.info(f"OCR complete. Extracted {len(raw_texts)} text blocks.")
            return raw_texts

        except Exception as e:
            logger.error(f"OCR Processing error: {e}", exc_info=True)
            return []
        finally:
            if enhanced_path:
                try:
                    os.remove(enhanced_path)
                except OSError:
                    pass
