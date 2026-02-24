# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Set the working directory in the container
WORKDIR /app

# Install curl (required for downloading uv)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy pyproject.toml and README.md (required by hatchling metadata) to install dependencies first (caching layer)
COPY pyproject.toml README.md ./
# COPY uv.lock . # Uncomment if you use uv.lock to freeze versions

# Copy the source code because hatchling needs it to build the package during install
COPY src ./src

# Install dependencies using uv
RUN uv pip install -e .

# Copy the rest of the application code
COPY . .

# Run the Telegram bot by default
CMD ["uv", "run", "sj-trading", "bot", "--no-sim"]
