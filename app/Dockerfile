FROM ubuntu:22.04

WORKDIR /app

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Detect architecture and set environment variables
RUN dpkg --print-architecture > /tmp/arch.txt && \
    echo "Building for architecture: $(cat /tmp/arch.txt)"

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    build-essential \
    libgdal-dev \
    libspatialindex-dev \
    libpq-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set python3.11 as default python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with ARM64 compatibility
# For ARM64, install CPU-only versions of heavy packages to avoid CUDA issues
RUN ARCH=$(dpkg --print-architecture) && \
    pip install --upgrade pip setuptools wheel && \
    if [ "$ARCH" = "arm64" ] || [ "$ARCH" = "aarch64" ]; then \
        echo "Installing ARM64-compatible packages..." && \
        pip install --no-cache-dir --timeout=1000 --retries=5 \
            pymavlink \
            ollama \
            tkintermapview \
            customtkinter \
            osmnx \
            matplotlib \
            sqlalchemy \
            geoalchemy2 \
            opencv-python-headless \
            numpy \
            rtree \
            psycopg2-binary && \
        pip install --no-cache-dir --timeout=1000 --retries=5 ultralytics --extra-index-url https://pypi.org/simple; \
    else \
        echo "Installing x86_64 packages..." && \
        pip install --no-cache-dir --timeout=1000 --retries=5 -r requirements.txt; \
    fi && \
    echo "\n========================================" && \
    echo "Finished Building" && \
    echo "========================================\n"

# Copy the entire app directory
COPY . .

# Print all dependencies when container runs
CMD ["python3", "missionState.py"]
