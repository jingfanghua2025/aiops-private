FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmariadb-dev \
    pkg-config \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.org/simple
# Install extra cloud SDKs
RUN pip install --no-cache-dir tencentcloud-sdk-python aliyun-python-sdk-core aliyun-python-sdk-ecs jdcloud_sdk -i https://pypi.org/simple
# Huawei cloud causing issues, skipping for now or try later
# RUN pip install --no-cache-dir huaweicloud-sdk-core huaweicloud-sdk-ecs

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
