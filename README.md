# Ollama Dashboard

![Backend Coverage](https://img.shields.io/badge/Backend_Coverage-Unknown-lightgrey)
![Frontend Coverage](https://img.shields.io/badge/Frontend_Coverage-Unknown-lightgrey)
A robust, full-stack administration panel and playground for managing local [Ollama](https://ollama.com/) AI models. Built with a focus on real-time streaming, asynchronous communication, and elegant error handling (SOLID).

## 🚀 Key Features

* **Model Hub:** Browse, install, update, and delete local AI models (Llama 3, Qwen, Phi, etc.) with real-time download progress tracking.
* **Smart Categorization:** Automatically detects and tags model capabilities (Chat, Embedding, Vision, Code).
* **Dual-Mode Playground:**
  * *Agent Chat:* A modern, Markdown-supported conversational UI.
  * *Raw Console:* A terminal-like interface for direct prompt testing.
* **Real-time Streaming (SSE over POST):** Custom implementation of Server-Sent Events consuming `ReadableStream` via `fetch`.
* **Resilient Architecture:** Graceful handling of client disconnections, `asyncio.CancelledError`, and strict interception of Ollama API exceptions to prevent frontend crashes.

## 🚦 Getting Started

### Prerequisites
1. Install [Python 3.10+](https://www.python.org/downloads/) and [Node.js 18+](https://nodejs.org/).
2. Install [Ollama](https://ollama.com/) and ensure it is running on your machine.

### Run the Dashboard

The project includes an intelligent bootstrap script that automatically installs dependencies on its first run and launches both the backend and frontend simultaneously.

Simply open your terminal in the project's root folder and run:

```bash
python run.py
```

The script will automatically set up the environment, start the services, and open the dashboard in your default web browser (`http://localhost:5173`). To stop the servers, just press `CTRL+C` in the terminal.

## 🛠️ Testing (TDD)

The backend is fully covered by unit tests using `pytest` and `httpx` mocking to ensure the core routing and local API wrapper are fail-safe. 

To run the test suite:
```bash
cd backend
python -m pytest tests/ -v
```