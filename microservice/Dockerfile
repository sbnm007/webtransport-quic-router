FROM python:3.12-slim

# Install necessary system dependencies for Python packages and runtime
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    wget \
    # Clean up apt cache to keep the image small
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .