# Image riêng cho thí nghiệm so sánh phương pháp đọc BCTC (eval/methods.py): Tesseract 5 tiếng Việt và Docling chạy
# CPU. Không đụng image soi-app. Build từ thư mục Code/:
#   docker build -t soi-methods -f eval/methods/Dockerfile eval/methods
# Chạy (Code/ và Data/raw gắn vào như dịch vụ app; không cần CSDL):
#   docker run --rm -v "$PWD:/app/Code" -v "$PWD/../Data/raw:/app/Data/raw" -w /app/Code soi-methods \
#       python eval/methods.py run --method M2 --level goc
# Phiên bản đã ghim (đo 22/10/2026: Tesseract 5.5.0, gói tiếng Việt tesseract-ocr-vie 4.1.0 của Debian, tức bộ
# tessdata chuẩn, không phải tessdata_best; docling 2.140.0, docling-ibm-models 4.0.4, torch 2.14.1+cpu). Danh sách đầy
# đủ sau khi cài nằm ở /opt/versions.txt trong image.
FROM python:3.12.14-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

# Tesseract ghim đúng bản đã đo (Debian 13); thư viện hệ thống cho OpenCV của Docling không ảnh hưởng kết quả, để mới nhất
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr=5.5.0-1+b1 libtesseract5=5.5.0-1+b1 \
        tesseract-ocr-vie=1:4.1.0-2 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# PyTorch bản CPU (không kéo CUDA), rồi Docling
RUN pip install --no-cache-dir torch==2.14.1+cpu torchvision==0.29.1+cpu \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir docling==2.140.0

# Tải sẵn mô hình bố cục và cấu trúc bảng vào image: mọi lần chạy dùng đúng một bộ trọng số
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models
RUN docling-tools models download layout tableformer -o /opt/docling-models

RUN (pip freeze; echo; tesseract --version 2>&1; echo; tesseract --list-langs 2>&1; \
     echo; dpkg -s tesseract-ocr-vie | grep -E '^(Package|Version)') > /opt/versions.txt

ENV PYTHONIOENCODING=utf-8 RAW_DATA_DIR=/app/Data/raw
WORKDIR /app/Code
