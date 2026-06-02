# -*- coding: utf-8 -*-
import os
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_use_mkldnn_cache"] = "0"

import cv2
import numpy as np
import tempfile
from paddleocr import PaddleOCR

print("=== Initializing PaddleOCR 3.x ===")
ocr = PaddleOCR(use_textline_orientation=True, lang="japan")
print("=== Ready ===\n")

# 建立一張有文字的測試圖
test_img = np.ones((400, 800, 3), dtype=np.uint8) * 255
cv2.putText(test_img, "Invoice Test 1234", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, (0,0,0), 3)
cv2.putText(test_img, "Total: 1,000 yen", (30, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,0), 2)
cv2.putText(test_img, "Date: 2026-05-23", (30, 320), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0,0,0), 2)

tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
cv2.imwrite(tmp.name, test_img)
tmp.close()

print(f"Test image: {tmp.name}")
print("Running ocr.ocr()...")
result = ocr.ocr(tmp.name, cls=True)

print(f"\nResult type: {type(result)}")
if result:
    for i, item in enumerate(result):
        print(f"Content: {item}")
else:
    print("Result is empty/None!")

os.unlink(tmp.name)
print("\n=== Test Done ===")
