#!/bin/bash
# Start the React frontend

cd "$(dirname "$0")"

# Install dependencies if node_modules doesn't exist
if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

# Start development server
echo "Starting React frontend on http://localhost:3000"
npm run dev
