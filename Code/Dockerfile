# Image dùng chung cho web, bộ canh và các lệnh chạy một lần (đọc BCTC, kiểm tra lại...).
# Chạy trên Linux nên không phụ thuộc chính sách chặn DLL của Windows (Smart App Control chặn libpq của psycopg).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 PIP_NO_CACHE_DIR=1
WORKDIR /app/Code

# Phông có đủ dấu tiếng Việt cho ảnh thẻ chia sẻ và PDF báo cáo; pango cho WeasyPrint
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 && rm -rf /var/lib/apt/lists/*

# Cài thư viện trước (đọc từ pyproject.toml) để lớp này được cache khi chỉ sửa code
COPY pyproject.toml .
RUN python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb'))['project']; \
open('/tmp/req.txt', 'w').write('\n'.join(d['dependencies'] + d['optional-dependencies']['dev']))" \
    && pip install -r /tmp/req.txt

COPY . .
ENV PYTHONPATH=/app/Code

EXPOSE 8765
CMD ["python", "-m", "services.api", "--host", "0.0.0.0", "--port", "8765"]
