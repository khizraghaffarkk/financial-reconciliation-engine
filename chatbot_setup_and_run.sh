#!/bin/bash

# ----------------------------------------------------------
# Script: chatbot_setup_and_run.sh
# Purpose: Automate setup and run of Streamlit LLM interface
# ----------------------------------------------------------

# Step 1: Install Python dependencies
echo "Installing Python dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r requirements.txt

# Step 2: Check if Ollama is installed
if ! command -v ollama &> /dev/null
then
    echo "Ollama CLI not found. Please install Ollama manually from https://ollama.com/"
    exit 1
fi

# Step 3: Pull default LLM model (llama3.2:latest)
DEFAULT_MODEL="llama3.2:latest"
echo "Pulling default model: $DEFAULT_MODEL..."
ollama pull $DEFAULT_MODEL

# Step 4: Run Ollama server in background
echo "Starting Ollama server..."
ollama serve &

# Give the server a few seconds to start
sleep 5

# Step 5: Run Streamlit interface
echo "Launching Streamlit interface..."
streamlit run src/llm_inference_app.py

# Optional: Instructions for user
echo "If Streamlit does not launch, make sure your Python virtual environment is active."
