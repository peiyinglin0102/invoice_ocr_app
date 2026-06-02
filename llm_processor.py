# -*- coding: utf-8 -*-
import json
import logging
from typing import List, Dict, Any

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

2. 空間排版對齊與「非典型單據」推理（特別針對置物櫃、車票、自動販賣機收據）：
   - 同一行文字的 y 座標會非常接近（差值通常小於 18）。
   - 如果品項名稱與金額分處左右兩端，請比對它們的 y 座標。y 座標最接近的文字與金額，即為對應的品項與價格。
   - ⚠️ **欄位與雜訊隔離（極重要）**：單據上常出現大量與金額無關的 3 或 4 位數（例如：置物櫃號碼 Box No.、終端機編號 Terminal No.、條碼編號）。當提取金額（`unit_price` / `total_foreign_amount`）時，必須尋找緊鄰 `¥`、`\`、`$`、`KRW`、`金額`、`領収`、`利用料`、`小計`、`合計`、`TOTAL` 等關鍵字「同一行（y軸相近）」或「正下方（x軸相近）」的數字。
   - **嚴禁**將孤立的、明顯是設備編號或置物櫃號碼的數字（如單獨一行且前後無貨幣標記的 `3819`）誤認為商品價格或總金額！

3. 🧮 數學自我檢算與對帳規範（嚴禁做帳）：
   - 提取完所有品項（items）後，請自行計算 `(unit_price * quantity)` 的加總（包含負數折扣項）是否等於 `total_foreign_amount`（發票上的「合計金額」）。
   - ⚠️ **絕對忠實原則**：您必須高度忠實於發票上的真實數字。**嚴禁為了使加總吻合而擅自憑空修改/竄改其他本來就正確的商品單價或數量來進行「做帳`」或「湊數」！**
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
   - 若發票/收據中出現折扣、優惠、折價、優惠券等相關項目（常見日文關鍵字如：`値引き`、`割引`、`割引額`、`クーポン`、`割引券` 等；英文如：`Discount`、`Coupon`、`Markdown`），**請務必將其作為獨立品項列出**。
   - 折扣項目的數值規範：
     - `original_name` 與 `translated_name` 應如實保留其優惠或折扣名稱（如：`値引き` 譯為 `優惠折扣`）。
     - **`unit_price` 必須為負數**（例如 `-100.0` 或 `-50.0`），代表扣減金額。
     - `quantity` 設為 `1`。
     - `category` 設為 `免稅/折扣`，`tax_flag` 可為空。
   - 這類負數的折抵金額將與其它正商品加總一併計算，藉此完全比對並驗證最終的實付金額（合計金額）邏輯是否正確合理。

5. 雜訊與座標過濾：
   - 存入 `original_name` 時，請務必「乾淨移除空間座標前綴與多餘條碼數字」（例如將 `[y:230, x:40] 3101パペットスンスン` 轉為純淨的原始商品名 `パペットスンスン`）。
   - 忽略電話、宣傳標語、設備編號、找零（お釣り）、實收（お預り）等與消費品項無關的純描述資訊。

6. 繁體化與品牌精準翻譯：
   - 將商品翻譯為台灣習慣的「繁體中文」正式譯名（例如：`パペットスンスン` 譯為 `Sunsun 玩偶/手套偶`；`紙袋小` 譯為 `小紙袋`；`コインロッカー` 或包含 `ロッカー利用料` 譯為 `置物櫃使用費`）。

7. 分類歸納（擴充精準旅遊分類）：
   - 必須將品項嚴格歸類到以下 18 個分類之一。請參考後方列出的各國常見購買品項與關鍵字進行歸類：
     * **餐飲**：餐廳正餐、拉麵、燒肉、居酒屋、咖啡廳、下午茶、點餐（Dine-in / Takeout）。
     * **超商/超市**：7-11、FamilyMart、GS25、CU、大國藥妝零食部、E-MART、樂天超市、Trader Joe's、Whole Foods、基本生鮮食品、三明治等。
     * **伴手禮/土特產**：東京芭娜娜、白色戀人、韓國海苔、人蔘雞禮盒、各國機場免稅店伴手禮盒、名產。
     * **零食/飲料**：軟糖、洋芋片、巧克力、餅乾、午後紅茶、香蕉牛奶、各類包裝零嘴與罐裝飲品。
     * **藥妝/美妝**：臉部保養品、化妝品、面膜、防曬乳、護唇膏、Olive Young 戰利品、絲芙蘭 (Sephora) 專櫃彩妝、洗面乳。
     * **醫療保健**：合利他命、EVE止痛藥、Wakamoto、大正感冒藥、南大門貼布、各類維他命、保健食品、感冒藥、OK蹦。
     * **服飾/鞋包**：服裝、外套、球鞋、包包、帽子、Gentle Monster 墨鏡、Porter包、Outlet戰利品、T-shirt。
     * **精品/奢侈品**：Louis Vuitton、Chanel、Gucci、Hermès、Rolex、各國名牌專櫃與高價皮件精品。
     * **動漫/玩具/周邊**：Sunsun玩偶、吉伊卡哇 (Chiikawa) 周邊、動漫周邊、寶可夢中心、模型、一番賞、盲盒、樂高。
     * **居家/生活用品**：保溫瓶、餐具、香氛、蠟燭、大創 (Daiso) 小物、吹風機、保養儀器、生活雜貨。
     * **電子產品/3C**：iPhone、iPad、AirPods、相機鏡頭、行動電源、Bic Camera 買的3C配件、記憶卡、充電線。
     * **交通**：地鐵票、新幹線、KTX、火車票、計程車費（Uber / Grab / Kakao T）、機票、租車、加油費、儲值IC卡（Suica / T-money）。
     * **住宿**：飯店、高級渡假村、Airbnb、青年旅館、溫泉旅館、商務旅館、Lodge。
     * **門票/娛樂**：環球影城門票、迪士尼門票、景觀台景點門票、演唱會、滑雪場纜車票、一日遊體驗行程。
     * **稅金/服務費**：飯店住宿稅 (Accommodation Tax)、城市稅 (City Tax)、出境稅、置物櫃使用費 (Locker fee / ロッカー利用料)、行李寄放費、外送平台服務費。
     * **免稅/折扣**：退稅退款 (Tax Refund)、退稅手續費扣減、店內折價券（値引き/割引額/Coupon/Discount/Markdown）。
     * **文具/書籍**：Loft文具、紙膠帶、各國旅遊雜誌、手帳、筆記本、原子筆、御朱印帳、動漫設定集、明信片。
     * **其他**：無法歸類的雜項、國際郵資、ATM提領手續費等。

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
    Gemini 3.5 Flash LLM 處理器 (純 REST API 版，對應 2026 年最新 API)
    """

    def __init__(self, api_key: str = None, model_name: str = "gemini-3.5-flash"):
        """
        初始化 Gemini LLM。
        """
        resolved_key = (api_key or "").strip()
        
        if not resolved_key:
            raise ValueError("ERR-004: Gemini API Key 未提供")

        self.model_name = model_name
        self.api_key = resolved_key
        logger.info(f"LLMProcessor initialized using pure REST API for {self.model_name}")

    def process_ocr_texts(self, ocr_texts: List[str]) -> Dict[str, Any]:
        """
        將 OCR 擷取的文字陣列送入 Gemini LLM 進行清洗、翻譯與結構化。
        """
        import requests
        
        ocr_block = "\n".join(ocr_texts)
        user_prompt = "以下是由 PaddleOCR 傳入的發票原始文字陣列，請依上述規則進行結構化：\n" + ocr_block

        logger.info(
            f"Sending {len(ocr_texts)} OCR text blocks to {self.model_name} via REST API..."
        )
        
        # 使用最新的 v1beta 搭配 gemini-3.5-flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {"parts": [{"text": user_prompt}]}
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json"
            }
        }
        
        response_text = ""
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                resp_json = response.json()
                
                if "candidates" not in resp_json or not resp_json["candidates"]:
                    raise ValueError("API 沒有回傳有效的 candidates 內容")
                
                # 提取文字
                try:
                    response_text = resp_json["candidates"][0]["content"]["parts"][0]["text"]
                except (KeyError, IndexError, TypeError):
                    try:
                        response_text = resp_json["candidates"][0].get("output", "")
                    except:
                        raise ValueError("無法從 API 回應中提取文字")

                # 清除可能殘留的 Markdown 標記
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

                logger.info(f"✅ Successfully used REST API: {self.model_name}")
                return result_dict
            else:
                err_msg = f"HTTP {response.status_code}"
                try:
                    err_json = response.json()
                    if "error" in err_json:
                        err_msg = err_json["error"].get("message", err_msg)
                except:
                    err_msg = response.text[:300]
                raise ValueError(f"{err_msg}")
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error. Raw response: {response_text[:500]}")
            logger.error(f"JSONDecodeError: {e}")
            raise ValueError("ERR-003: Gemini JSON 輸出格式損毀") from e

        except Exception as e:
            err_str = str(e)
            logger.error(f"LLM API error: {err_str}")
            if "ERR-003" in err_str:
                raise ValueError("ERR-003: Gemini JSON 輸出格式損毀") from e
            raise ValueError(f"ERR-004: Gemini API 呼叫失敗 — {err_str}") from e