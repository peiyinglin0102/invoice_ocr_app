import numpy as np
from paddleocr import PaddleOCR
import logging
from PIL import Image

# 設置 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class InvoiceOCREngine:
    def __init__(self, lang='ch'):
        """
        初始化 PaddleOCR 引擎
        :param lang: 支援 'ch' (繁中), 'japan', 'korean', 'en'
        """
        logger.info(f"Initializing PaddleOCR with language: {lang}...")
        # use_angle_cls=True 可以自動分類文字方向
        self.ocr = PaddleOCR(use_angle_cls=True, lang=lang, show_log=False)
        logger.info("PaddleOCR initialized successfully.")

    def extract_text(self, image_path: str):
        """
        從圖片中提取文字
        :param image_path: 圖片的絕對路徑
        :return: 包含所有識別出的文字列表 (List of strings)
        """
        logger.info(f"Starting OCR extraction on {image_path}...")
        
        try:
            # result 是一個列表，裡面每個元素代表一行識別結果
            # 格式大致為: [[[[x,y],[x,y],[x,y],[x,y]], ('text', confidence)], ...]
            result = self.ocr.ocr(image_path, cls=True)
            
            raw_texts = []
            if result and result[0]:
                for line in result[0]:
                    text, confidence = line[1]
                    raw_texts.append(text)
                    
            logger.info(f"Extraction complete. Found {len(raw_texts)} text blocks.")
            return raw_texts
        except Exception as e:
            logger.error(f"OCR Processing error: {str(e)}")
            return []

if __name__ == "__main__":
    # Test script if run locally
    pass
