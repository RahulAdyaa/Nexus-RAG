FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads chroma_db

# Expose port
EXPOSE 8000

# Copy startup script and make it executable
COPY start.sh .
RUN chmod +x start.sh

# Command to run the application (starts Celery + Uvicorn)
CMD ["./start.sh"]
