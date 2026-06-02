FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 安裝 PaddleOCR 和 OpenCV 需要的系統層級依賴套件
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 複製 requirements.txt 並安裝 Python 依賴
# (請確保你的專案根目錄有 requirements.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案內所有程式碼到容器內
COPY . .

# 暴露 App 運行的 Port (假設你的後端使用 8000 port)
EXPOSE 8000

# 啟動指令 (請依據你實際的啟動指令修改，這裡是 FastAPI 的範例)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]