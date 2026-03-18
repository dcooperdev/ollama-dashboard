import os
import subprocess
import sys
import platform
import time
import webbrowser
import importlib.util

def check_python_deps():
    """Checks if the core backend dependencies are installed."""
    for pkg in ["fastapi", "uvicorn", "httpx"]:
        if importlib.util.find_spec(pkg) is None:
            return True # Missing dependencies
    return False

def setup_environment(is_windows: bool, npm_cmd: str):
    """Installs dependencies only if they are missing."""
    # 1. Setup Backend
    if check_python_deps():
        print("📦 First run detected! Installing backend dependencies...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
            cwd="backend", 
            check=True
        )
        print("✅ Backend dependencies installed.\n")

    # 2. Setup Frontend
    if not os.path.exists(os.path.join("frontend", "node_modules")):
        print("📦 First run detected! Installing frontend dependencies (this might take a minute)...")
        subprocess.run(
            [npm_cmd, "install"], 
            cwd="frontend", 
            check=True
        )
        print("✅ Frontend dependencies installed.\n")

def main():
    """
    Bootstraps the environment, starts both servers, and opens the browser.
    Ensures graceful shutdown of child processes on exit.
    """
    is_windows = platform.system() == "Windows"
    npm_cmd = "npm.cmd" if is_windows else "npm"

    # Step 1: Auto-install dependencies if needed
    setup_environment(is_windows, npm_cmd)

    # Step 2: Define commands for servers
    backend_cmd = [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"]
    frontend_cmd = [npm_cmd, "run", "dev"]

    print("🚀 Starting Ollama Dashboard...")
    print("Press CTRL+C to stop both servers gracefully.\n")

    backend_process = None
    frontend_process = None

    try:
        # Start backend
        backend_process = subprocess.Popen(backend_cmd, cwd="backend")
        time.sleep(1.5) # Wait a moment for the backend port to bind

        # Start frontend
        frontend_process = subprocess.Popen(frontend_cmd, cwd="frontend")
        time.sleep(2) # Wait for Vite to start

        # Auto-open the browser
        print("\n🌐 Opening browser at http://localhost:5173 ...\n")
        webbrowser.open("http://localhost:5173")

        # Keep the main thread alive waiting for child processes
        backend_process.wait()
        frontend_process.wait()

    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down servers...")
        if backend_process:
            backend_process.terminate()
        if frontend_process:
            frontend_process.terminate()
            
        if backend_process:
            backend_process.wait()
        if frontend_process:
            frontend_process.wait()
            
        print("✅ Shutdown complete. Ports are now free.")

if __name__ == "__main__":
    main()