FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY README.md ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[server,llm]"

# Expose port
EXPOSE 3002

# Set environment variables
ENV PORT=3002
ENV PYTHONUNBUFFERED=1

# Run the API server
CMD ["python", "-m", "thordata_firecrawl.api"]
