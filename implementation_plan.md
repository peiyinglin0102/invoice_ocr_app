# 多國發票辨識與自動理財系統開發計畫

本計畫旨在根據提供的系統開發規格書 (SDS)，開發一個基於 Streamlit 的 Web 應用程式。此系統能透過 PaddleOCR 擷取多國語言發票上的文字，透過大語言模型 (LLM) 進行智能清洗、翻譯並結構化為 JSON 格式，最後使用 yfinance 自動獲取歷史匯率並換算為台幣，實現自動記帳與消費分類。

## User Review Required

> [!IMPORTANT]
> - **環境依賴安裝**：本專案需要安裝 `paddlepaddle==2.6.2` 與 `paddleocr==2.8.1`。這些套件較大，且首次運行會自動下載語言辨識模型檔案。
> - **API 密鑰 (API Key)**：系統將依賴 LLM (如 OpenAI GPT 或 Google Gemini) 進行資料清理與翻譯。我們預計在 Web 介面中加入一個讓使用者輸入自己 API Key 的欄位，確保資料安全與使用彈性。

## Proposed Changes

我們將在目錄 `C:\Users\winnie.lin\.gemini\antigravity\scratch\invoice_ocr_app` 中建立此專案。

### Application UI & Core

#### [NEW] `app.py`
作為 Streamlit 的主程式入口，包含：
- 側邊欄：讓使用者輸入 LLM API Key (支援 OpenAI 或 Gemini) 與選擇模型。
- 主畫面：圖片上傳元件 (支援 JPG/PNG)。
- 進度顯示：顯示 OCR 提取、LLM 分析、匯率換算等階段狀態。
- 結果展示：將分析出的 JSON 結果轉換為表格，並顯示總台幣金額。

### Backend Modules

#### [NEW] `ocr_engine.py`
封裝 PaddleOCR，負責讀取上傳圖片並返回未整理的原始文字清單 (List of strings)。包含處理語系 (`ch`, `japan`, `korean`) 的動態設定。

#### [NEW] `llm_processor.py`
設計 System Prompt，接收 OCR 提取出的雜訊文字陣列，呼叫 LLM 進行除錯、提取（日期、金額）、翻譯與分類。最後強制輸出為定義好的 JSON Schema 格式。

#### [NEW] `finance_utils.py`
封裝匯率換算模組，使用 `yfinance` (例如 `JPYTWD=X`)，根據 LLM 解析出的發票日期抓取該日的收盤價進行外幣到台幣的轉換計算。

### Project Configuration

#### [NEW] `requirements.txt`
包含系統所需之特定版本套件：
```text
streamlit
paddleocr==2.8.1
numpy==1.26.4
paddlepaddle==2.6.2
openai
google-generativeai
yfinance
pillow
pandas
```

## Open Questions

> [!WARNING]
> - **LLM 選擇**：在 Web 畫面上，您是否希望同時支援 OpenAI 與 Google Gemini，還是以其中一種為主？
> - **專案路徑**：將專案建立在 `C:\Users\winnie.lin\.gemini\antigravity\scratch\invoice_ocr_app` 是否符合您的需求？

## Verification Plan

### Manual Verification
1. 提供依賴安裝腳本 (例如 `pip install -r requirements.txt`)。
2. 啟動 `streamlit run app.py` 伺服器。
3. 準備一張含有外文 (如日文) 及數字的發票基準圖進行上傳測試。
4. 驗證 OCR 是否成功提取文字、LLM 是否能返回格式標準的 JSON、以及台幣匯率換算是否正確運作。
