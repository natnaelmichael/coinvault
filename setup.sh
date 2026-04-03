#!/bin/bash
# Setup script for Pump.fun Bot

set -e

echo "🚀 Pump.fun Bot - Installation Script"
echo "======================================"
echo ""

# Check Python version
echo "📋 Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
REQUIRED_VERSION="3.9"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Python $REQUIRED_VERSION or higher is required"
    echo "   Current version: $PYTHON_VERSION"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION detected"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "⚠️  Virtual environment already exists, skipping..."
fi
echo ""

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Setup configuration
echo "⚙️  Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ Created .env file from .env.example"
    echo "⚠️  IMPORTANT: Edit .env file with your settings before running!"
else
    echo "⚠️  .env file already exists, skipping..."
fi
echo ""

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs data config
echo "✅ Directories created"
echo ""

echo "======================================"
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your wallet keys and settings"
echo "2. Activate virtual environment: source venv/bin/activate"
echo "3. Generate wallets (optional): python main.py generate-wallets --count 5"
echo "4. Check configuration: python main.py config-check"
echo "5. Start the bot: python main.py start"
echo ""
echo "⚠️  IMPORTANT: Start with DRY_RUN_MODE=true for testing!"
echo ""
