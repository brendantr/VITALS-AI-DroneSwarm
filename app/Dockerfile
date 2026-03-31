FROM python:3.11

# 1. Install system dependencies required by OpenCV, PyQt6, and QtWebEngine
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
    libxcb-shape0 libxcb-xinerama0 libegl1 libdbus-1-3 \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2 libxshmfence1 \
    libxfixes3 libxtst6 libxkbfile1 \
    libx11-xcb1 libxcb-dri3-0 libxcb-present0 libxss1 libxi6 libxrender1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. Detect architecture and set environment variables
RUN dpkg --print-architecture > /tmp/arch.txt && \
    echo "Building for architecture: $(cat /tmp/arch.txt)"

# 3. Copy requirements first for better caching
COPY requirements.txt .

# 4. Install Python dependencies with ARM64 / x86_64 compatibility
RUN ARCH=$(dpkg --print-architecture) && \
    pip install --upgrade pip setuptools wheel && \
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then \
        echo "Installing ARM64-compatible packages..." && \
        pip install --no-cache-dir --timeout=1000 --retries=5 \
            pymavlink mcp pyserial mavproxy PyQt6 PyQt6-WebEngine \
            pyproj shapely geopandas ollama tkintermapview customtkinter \
            Pillow osmnx matplotlib sqlalchemy geoalchemy2 numpy rtree \
            psycopg2-binary==2.9.11 && \
        pip install --no-cache-dir --timeout=1000 --retries=5 ultralytics --extra-index-url https://pypi.org/simple; \
    else \
        echo "Installing x86_64 packages..." && \
        pip install --no-cache-dir --timeout=1000 --retries=5 -r requirements.txt; \
    fi

# 5. Copy the entire app directory
COPY . .

# 6. Run the application
CMD ["python3", "missionState.py"]
