import json
import logging
from typing import List, Dict, Any
import google.generativeai as genai
from openai import OpenAI

logger = logging.getLogger(__name__)

class LLMProcessor:
    def __init__(self, api_key: str, provider: str = "gemini", model_name: str = "gemini-1.5-pro-latest"):
        """
        初始化 LLM Processor
        :param api_key: 您的 API 金鑰
        :param provider: 'gemini' 或 'openai'
        :param model_name: 使用的模型名稱
        """
        self.provider = provider.lower()
        self.api_key = api_key
        self.model_name = model_name
        
        if self.provider == "gemini":
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_name)
        elif self.provider == "openai":
            self.client = OpenAI(api_key=self.api_key)
        else:
            raise ValueError("Unsupported provider. Please choose 'gemini' or 'openai'.")

    def _get_system_prompt(self):
        return """你是一個專業的財務會計與多國語言翻譯專家。
任務指示：根據以下 OCR 掃描出來的發票文字，請執行以下動作：
1. 提取出發票的購買「日期」(格式為 YYYY-MM-DD，如果沒有年份請用今年代替) 與「總金額」(數字)。
2. 從雜亂的文字中辨識出真實購買的「商品品項」。
3. 自動修正可能的 OCR 拼寫錯誤（例如 アリナミンミメプラス 應該是 アリナミンEXプラス）。
4. 將品項精準翻譯為「繁體中文」。
5. 根據常識判斷品項並歸類 (如：醫療保健/藥妝、餐飲、交通、服飾、日常用品等)。
6. 判斷幣別 (如 JPY, KRW, USD, TWD)。若無法判斷，預設依據常識猜測或使用 "Unknown"。

格式約束：嚴格禁止輸出任何結尾或開頭的解釋性文字 (也不要有 Markdown ```json 標籤)，僅回傳一個完全符合以下格式的合法 JSON 字串：
{
  "receipt_info": {
    "date": "2023-06-24",
    "store_name": "商店名稱 (若有)",
    "currency": "JPY",
    "total_amount_foreign": 30813
  },
  "items": [
    {
      "original_name": "原文品名",
      "translated_name": "繁體中譯",
      "quantity": 1,
      "unit_price": 500,
      "category": "醫療保健/藥妝"
    }
  ]
}
"""

    def process_ocr_texts(self, ocr_texts: List[str]) -> Dict[str, Any]:
        """
        將 OCR 文字送進 LLM 進行重構與清理
        """
        prompt = self._get_system_prompt() + "\n\n以下是 OCR 雜訊文字陣列：\n" + "\n".join(ocr_texts)
        
        logger.info(f"Sending OCR text to {self.provider} ({self.model_name}) for processing...")
        response_text = ""
        try:
            if self.provider == "gemini":
                # Gemini
                response = self.model.generate_content(prompt)
                response_text = response.text
            elif self.provider == "openai":
                # OpenAI
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": "以下是 OCR 雜訊文字陣列：\n" + "\n".join(ocr_texts)}
                    ],
                    temperature=0.0
                )
                response_text = response.choices[0].message.content

            # 清理 Markdown 代碼塊
            response_text = response_text.replace("```json", "").replace("```", "").strip()
            
            # 解析為 Dict
            result_dict = json.loads(response_text)
            logger.info("Successfully parsed LLM response to JSON.")
            return result_dict
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON. Raw response: {response_text}")
            logger.error(f"JSON Error: {str(e)}")
            raise e
        except Exception as e:
            logger.error(f"LLM Processing Error: {str(e)}")
            raise e
