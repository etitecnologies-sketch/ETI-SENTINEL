#!/usr/bin/env python3
"""
Monitoring System - Installation Script (Cross-platform)
Funciona em Windows, macOS e Linux
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

# Colors for terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(message):
    """Print a nice header"""
    width = 52
    print()
    print(f"{Colors.CYAN}╔{'═' * (width - 2)}╗{Colors.ENDC}")
    print(f"{Colors.CYAN}║  {message:<{width - 6}}║{Colors.ENDC}")
    print(f"{Colors.CYAN}╚{'═' * (width - 2)}╝{Colors.ENDC}")
    print()

def print_info(message):
    """Print info message"""
    print(f"{Colors.BLUE}[INFO]{Colors.ENDC} {message}")

def print_success(message):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.ENDC} {message}")

def print_warning(message):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.ENDC} {message}")

def print_error(message):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.ENDC} {message}")

def run_command(cmd, cwd=None, description=None):
    """Run a shell command"""
    try:
        if description:
            print_info(description)

        kwargs = {"cwd": cwd, "capture_output": True, "text": True}
        if os.name == "nt":
            kwargs["stdin"] = subprocess.DEVNULL
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
                kwargs["startupinfo"] = si
            except Exception:
                pass

        if isinstance(cmd, str):
            result = subprocess.run(cmd, shell=True, **kwargs)
        else:
            result = subprocess.run(cmd, **kwargs)
        
        if result.returncode != 0:
            print_error(f"Erro ao executar: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
            print(result.stderr)
            return False
        
        return True
    except Exception as e:
        print_error(f"Excepção: {e}")
        return False

def check_command(command, name):
    """Check if a command is available"""
    print_info(f"Verificando {name}...")
    return shutil.which(command) is not None

def main():
    """Main installation function"""
    print_header("Monitoring System - Setup Automático")
    
    # Check Node.js
    if not check_command("node", "Node.js"):
        print_error("Node.js não encontrado")
        print_warning("Por favor, instale Node.js 18+")
        print("Download: https://nodejs.org/")
        sys.exit(1)
    
    # Get Node version
    result = subprocess.run(["node", "--version"], capture_output=True, text=True)
    print_success(f"Node.js {result.stdout.strip()} encontrado")
    
    # Check Python (optional)
    python_available = check_command("python", "Python") or check_command("python3", "Python")
    if python_available:
        result = subprocess.run(["python3" if check_command("python3", "") else "python", "--version"], 
                              capture_output=True, text=True)
        print_success(f"Python {result.stdout.strip()} encontrado")
    else:
        print_warning("Python não encontrado - Processor não funcionará")
    
    # Install dependencies
    print()
    print_info("Instalando dependências da raiz...")
    if not run_command("npm install"):
        sys.exit(1)
    print_success("Raiz instalada")
    
    # Install ingest-api
    print()
    print_info("Instalando ingest-api...")
    if not run_command("npm install", cwd="ingest-api"):
        sys.exit(1)
    print_success("Ingest-API instalada")
    
    # Install websocket-server
    print()
    print_info("Instalando websocket-server...")
    if not run_command("npm install", cwd="websocket-server"):
        sys.exit(1)
    print_success("WebSocket Server instalado")
    
    # Install frontend
    print()
    print_info("Instalando frontend...")
    if not run_command("npm install", cwd="frontend"):
        sys.exit(1)
    print_success("Frontend instalado")
    
    # Install processor Python
    if python_available:
        print()
        print_info("Instalando dependências Python...")
        python_cmd = "python3" if check_command("python3", "") else "python"
        if run_command([python_cmd, "-m", "pip", "install", "-r", "requirements.txt"], 
                      cwd="processor"):
            print_success("Processor Python instalado")
        else:
            print_warning("Erro ao instalar dependências Python")
    
    # Create .env
    print()
    print_info("Configurando variáveis de ambiente...")
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    
    if not env_path.exists():
        if env_example_path.exists():
            shutil.copy(env_example_path, env_path)
            print_warning(".env criado de .env.example - CONFIGURE AS SENHAS!")
        else:
            print_warning(".env.example não encontrado")
    else:
        print_success(".env já existe")
    
    # Summary
    print_header("✓ Setup Completo!")
    
    print(f"{Colors.BLUE}Próximos passos:{Colors.ENDC}")
    print("1. Configure as variáveis no arquivo .env")
    print()
    
    print(f"{Colors.BLUE}Para iniciar em desenvolvimento:{Colors.ENDC}")
    print(f"{Colors.CYAN}   make dev{Colors.ENDC}")
    print()
    
    print(f"{Colors.BLUE}Ou com Docker:{Colors.ENDC}")
    print(f"{Colors.CYAN}   docker-compose up -d{Colors.ENDC}")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print_warning("Instalação cancelada pelo usuário")
        sys.exit(1)
    except Exception as e:
        print_error(f"Erro inesperado: {e}")
        sys.exit(1)
