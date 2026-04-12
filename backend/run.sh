#!/bin/bash
# Start the FastAPI backend

cd "$(dirname "$0")"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the server
echo "Starting FastAPI backend on http://localhost:8000"
python main.py
