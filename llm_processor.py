# -*- coding: utf-8 -*-
import json
import logging
from typing import List, Dict, Any

import google.genai as genai

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# System Prompt (直接實作於程式碼中，符合規格書要求)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """妳是一個極致精準的財務發票與收據數據結構化專家。
請分析由 PaddleOCR 傳入的發票原始字串。
傳入字串已加上空間座標前綴（格式為：`[y:縱向座標, x:橫向座標] 文字`），代表該文字在圖片上的物理位置（y 越小代表越上方，x 越小代表越左方）。

請極度嚴格執行以下任務：

1. ⚠️ 多行排版品項關聯（極重要）：
   許多日韓發票的單一商品明細會拆成多行展示，例如：
   - 第一行：國際條碼/序號或分類代號（如 `4548626224661`、`3101`）
   - 第二行：商品名稱文字（如 `パペットスンスン`）
   - 第三行：單價與數量與金額（如 `単1,518 x 2個 內 ¥3,036`）
   請利用 y 座標的連續性，將這些屬於同一個商品的「國際條碼/序號、商品名稱、單價數量金額」行合併為單一品項。切勿將條碼或隨後的文字當成獨立品項！
   商品名稱在上一行（y 較小），而單價、數量、總價在下一行（y 較大，但差值極小），請確保它們被完美合併。

2. 空間排版對齊推理：
   - 同一行文字的 y 座標會非常接近（差值通常小於 18）。
   - 如果品項名稱與金額分處左右兩端，請比對它們的 y 座標。y 座標最接近的文字與金額，即為對應的品項與價格。

3. 🧮 數學自我檢算與對帳規範（嚴禁做帳）：
   - 提取完所有品項（items）後，請自行計算 `(unit_price * quantity)` 的加總（包含負數折扣項）是否等於 `total_foreign_amount`（發票上的「合計金額」）。
   - ⚠️ **絕對忠實原則**：您必須高度忠實於發票上的真實數字。**嚴禁為了使加總吻合而擅自憑空修改/竄改其他本來就正確的商品單價或數量來進行「做帳」或「湊數」！**
   - **檢查形近字錯誤與排版**：如果加總不符，請高度警惕是否發生了 OCR 形近字誤判，特別是排版與貨幣標記干擾：
     * **日圓符號「¥」或「\」被誤判為「1」**：OCR 經常將日圓符號 `¥` 或反斜線 `\` 誤辨識為數字 `1` 或首位數前導符號。當提取金額時，若發現數字不合理地大，請務必透過『單價 × 數量』的數學邏輯，以及與總價/其它品項之和的差額互補關係，去合理推導、思考並驗證，以還原最真實合理的真實單價（例如將誤判的 `133` 或 `1429` 還原為 `33` 或 `429`）。
     * **「内」與「1」的混淆**：日文發票常有「內稅」標記（如 `内 ¥33`、`内 ¥3,036`），OCR 常將日文的 `内` (inside/tax-included) 誤辨識為數字 `1`、`l` 或貨幣符號 `¥`。請根據前後文與常理邏輯，剔除這種因「内」字產生的虛假價格數字！
     * **「内 \」或「内 ¥」與首位數的混淆（一般化規則）**：
       - 當品項單價或金額前包含 `内` 或貨幣符號 `\`、`¥` 時，OCR 經常將這些符號與價格的第一個數字黏在一起，辨識成多了一位數（例如將 `¥33` 識為 `133` 或 `733`，將 `¥88` 識為 `188`）。
       - 請結合其他品項已知的單價以及總金額來比對。若某個品項（例如小袋子、低價值耗材）顯然不合理地多了一位數，且該品項前方存在 `内` 或貨幣符號，請主動修正該誤判數字（例如將誤判的 `133` 恢復為 `33`）。
       - **絕對禁止**為了讓這類多出的金額被吸收，而反向去更改其他原本正確辨識的大額品項價格（例如將正確的 `880` 竄改為 `780` 來湊數）。
     * **常識與合理性判斷**：
       - 結合品項的中文翻譯與其品類常識進行合理性檢驗。例如，在日本「塑膠袋/紙袋/購物袋」等包裝材料的價格一般極低（通常在 3 到 30 日圓之間），如果辨識出高達上百或數千日圓，且前方帶有稅務標記，顯然是前導符號與數字混淆的 OCR 誤判，應主動將其修正為較低位數的正確金額。
     * **條碼誤判為金額**：檢查是否有將國際條碼中的部分數字誤當成商品價格。
   - 請優先透過「修正 OCR 辨識錯誤」或「檢查是否漏抓品項」來讓數學加總吻合，絕對不要改動其他正常的金額！

4. 🏷️ 折扣與優惠項目提取規範（極重要）：
   - 若發票/收據中出現折扣、優惠、折價、優惠券等相關項目（常見日文關鍵字如：`値引き`、`割引`、`割引額`、`クーポン`、`割引券` 等），**請務必將其作為獨立品項列出**。
   - 折扣項目的數值規範：
     - `original_name` 與 `translated_name` 應如實保留其優惠或折扣名稱（如：`値引き` 譯為 `優惠折扣`）。
     - **`unit_price` 必須為負數**（例如 `-100.0` 或 `-50.0`），代表扣減金額。
     - `quantity` 設為 `1`。
     - `category` 設為 `其他`，`tax_flag` 可為空。
   - 這類負數的折抵金額將與其它正商品加總一併計算，藉此完全比對並驗證最終的實付金額（合計金額）邏輯是否正確合理。

5. 雜訊與座標過濾：
   - 存入 `original_name` 時，請務必「乾淨移除空間座標前綴與多餘條碼數字」（例如將 `[y:230, x:40] 3101パペットスンスン` 轉為純淨的原始商品名 `パペットスンスン`）。
   - 忽略電話、宣傳標語、找零（お釣り）、實收（お預り）等無關資訊。

6. 繁體化與品牌精準翻譯：
   - 將商品翻譯為台灣習慣的「繁體中文」正式譯名（例如：`パペットスンスン` 譯為 `Sunsun 玩偶/手套偶`；`紙袋小` 譯為 `小紙袋`；`コインロッカー` 譯為 `置物櫃使用費`）。

7. 分類歸納：
   - 品項分類必須為以下之一：[醫療保健, 藥妝, 零食/點心, 冷凍食品/冰品, 食品/飲料, 交通, 餐飲, 其他]。

請僅輸出符合以下 JSON Schema 的資料，絕不包含 any Markdown 外殼或對話文字：
{
  "invoice_date": "YYYY-MM-DD (若無則留空)",
  "currency": "ISO 三碼幣別（例如 JPY）",
  "items": [
    {
      "original_name": "原始發票純淨商品名稱 (需移除空間座標前綴及多餘條碼/序號)",
      "translated_name": "繁體中文精準譯名",
      "unit_price": 數字(外幣單價，常規商品為正數，折抵/折扣/優惠項目為負數，絕不能為 0。如：1518.0 或 -100.0)",
      "quantity": 數字,
      "tax_flag": "字串(如 #、★，無則留空)",
      "category": "分類枚舉值"
    }
  ],
  "total_foreign_amount": 數字(發票合計消費總金額，即 total_foreign_amount，如 4719.0)
}"""

class LLMProcessor:
    """
    Gemini 1.5 Flash LLM 處理器。
    負責：雜訊過濾、語境修正、繁體中文翻譯、分類歸納、結構化 JSON 輸出。
    """

    def __init__(self, api_key: str = None, model_name: str = "gemini-1.5-flash"):
        """
        初始化 Gemini LLM。
        """
        resolved_key = (api_key or "").strip()
        
        if not resolved_key:
            raise ValueError("ERR-004: Gemini API Key 未提供")

        self.model_name = model_name
        self.api_key = resolved_key

        try:
            # 確保使用最新版 google-genai 的正確導入方式
            from google import genai
            from google.genai import types
            self.client = genai.Client(api_key=self.api_key)
            self.types = types
            logger.info("LLMProcessor initialized with Gemini 1.5 Flash model successfully")
        except ImportError as e:
            logger.error(f"ImportError: {e}")
            raise RuntimeError("找不到 google-genai 套件，請確認 requirements.txt 中已包含 google-genai")

    def process_ocr_texts(self, ocr_texts: List[str]) -> Dict[str, Any]:
        """
        將 OCR 擷取的文字陣列送入 Gemini LLM 進行清洗、翻譯與結構化。
        """
        ocr_block = "\n".join(ocr_texts)
        user_prompt = "以下是由 PaddleOCR 傳入的發票原始文字陣列，請依上述規則進行結構化：\n" + ocr_block

        logger.info(
            f"Sending {len(ocr_texts)} OCR text blocks to Gemini 1.5 Flash..."
        )
        
        response_text = ""
        try:
            # 新版 SDK 的標準呼叫方式，直接將系統提示詞放入 config 中
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=self.types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                    response_mime_type="application/json"
                )
            )
            
            response_text = response.text

            # 清除可能殘留的 Markdown 標記（防禦性處理）
            response_text = (
                response_text
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

            result_dict = json.loads(response_text)

            # 驗證必要欄位
            required_keys = {"invoice_date", "currency", "items", "total_foreign_amount"}
            missing = required_keys - set(result_dict.keys())
            if missing:
                logger.warning(f"LLM response missing keys: {missing}")
                raise json.JSONDecodeError(f"Missing keys: {missing}", response_text, 0)

            logger.info("Successfully parsed LLM response to structured JSON.")
            return result_dict

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error. Raw response: {response_text[:500]}")
            logger.error(f"JSONDecodeError: {e}")
            raise ValueError("ERR-003: Gemini JSON 輸出格式損毀") from e

        except Exception as e:
            err_str = str(e)
            logger.error(f"LLM API error: {err_str}")
            # ERR-003 re-raise from retry logic
            if "ERR-003" in err_str:
                raise ValueError("ERR-003: Gemini JSON 輸出格式損毀") from e
            # ERR-004: API key / quota issues
            raise ValueError(f"ERR-004: Gemini API 呼叫失敗 — {err_str}") from e