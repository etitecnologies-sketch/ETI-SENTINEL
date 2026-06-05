import PyInstaller.__main__
import os
import shutil
from pathlib import Path

def build_edge_agent():
    here = Path(__file__).parent
    agent_dir = here / "edge-agent"
    dist_dir = here / "dist"
    build_dir = here / "build"

    print(f"Iniciando build do ETI SENTINEL Edge Agent...")

    # Limpa pastas de build anteriores
    for d in [dist_dir, build_dir]:
        if d.exists():
            shutil.rmtree(d)

    # Configuração do PyInstaller
    icon_flag = "--icon=" + str(here / "frontend/public/favicon.ico") if (here / "frontend/public/favicon.ico").exists() else ""
    params = [
        str(agent_dir / "edge_agent.py"),
        "--name=ETI_SENTINEL_Edge",
        "--onefile",
        "--noconsole",
        icon_flag,

        # Módulos Python incluídos como dados (importados dinamicamente)
        f"--add-data={agent_dir / 'workers'};workers",
        f"--add-data={agent_dir / 'services'};services",
        f"--add-data={agent_dir / 'core'};core",
        f"--add-data={agent_dir / 'utils'};utils",
        f"--add-data={agent_dir / 'agent_api.py'};.",
        f"--add-data={agent_dir / 'device_monitor.py'};.",
        f"--add-data={agent_dir / 'config.py'};.",
        f"--add-data={agent_dir / 'camera_collector.py'};.",
        f"--add-data={agent_dir / 'edge_rules.py'};.",
        f"--add-data={agent_dir / 'edge_alert_format.py'};.",
        f"--add-data={agent_dir / 'edge_notify.py'};.",

        # Imports que o PyInstaller não detecta automaticamente
        "--hidden-import=psutil",
        "--hidden-import=psutil._pswindows",
        "--hidden-import=requests",
        "--hidden-import=dotenv",
        "--hidden-import=python_dotenv",
        "--hidden-import=onnxruntime",
        "--hidden-import=onnxruntime.capi._pybind_state",
        "--hidden-import=numpy",
        "--hidden-import=cv2",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",

        # Exclui módulos pesados desnecessários no EXE de campo
        "--exclude-module=ultralytics",
        "--exclude-module=torch",
        "--exclude-module=torchvision",
        "--exclude-module=flask",
        "--exclude-module=flask_cors",
        "--exclude-module=matplotlib",
        "--exclude-module=scipy",
        "--exclude-module=sklearn",
        "--exclude-module=onvif",
        "--exclude-module=zeep",
        "--exclude-module=pystray",
    ]

    # Remove parâmetros vazios (como ícone se não existir)
    params = [p for p in params if p]

    PyInstaller.__main__.run(params)

    print(f"\nBuild concluído com sucesso!")
    print(f"O executável está em: {dist_dir / 'ETI_SENTINEL_Edge.exe'}")
    
    # Criar pasta de distribuição pronta para o cliente
    client_dist = here / "ETI_SENTINEL_CLIENT_READY"
    if client_dist.exists():
        shutil.rmtree(client_dist)
    client_dist.mkdir()
    
    # Copia o executável
    shutil.copy2(dist_dir / "ETI_SENTINEL_Edge.exe", client_dist)
    
    # Copia os binários essenciais (MediaMTX e FFmpeg)
    bin_dir = client_dist / "bin"
    bin_dir.mkdir()
    
    source_bin = here / "bin"
    if source_bin.exists():
        for item in os.listdir(source_bin):
            s = source_bin / item
            d = bin_dir / item
            if s.is_file():
                shutil.copy2(s, d)
                print(f"  Incluido: bin/{item} ({s.stat().st_size // 1024} KB)")
    else:
        print("[AVISO] pasta bin/ nao encontrada. Execute: python exportar_modelo.py")

    # Cria um .env de exemplo para o cliente (preenchido pelo INSTALAR.bat)
    with open(client_dist / ".env", "w", encoding="utf-8") as f:
        f.write("# Configuracoes ETI SENTINEL Edge\n")
        f.write("INGEST_API_URL=https://eti-sentinel-production.up.railway.app\n")
        f.write("COLLECTOR_KEY=SUA_CHAVE_AQUI\n")
        f.write("CLIENT_ID=ID_DO_CLIENTE\n")
        f.write("AGENT_API_PORT=8808\n")
        f.write("ENABLE_STREAMING=1\n")
        f.write("ENABLE_AI_ANALYTICS=1\n")
        f.write("ENABLE_FIRE_DETECTION=1\n")
        f.write("ENABLE_TAMPER_DETECTION=1\n")

    # Copia os scripts de instalacao/desinstalacao da pasta scripts/
    scripts_dir = here / "scripts"
    for script in ["INSTALAR.bat", "DESINSTALAR.bat", "VERIFICAR.bat"]:
        src = scripts_dir / script
        if src.exists():
            shutil.copy2(src, client_dist / script)
        else:
            print(f"[AVISO] {script} nao encontrado em scripts/ — pulando.")

    print(f"Pasta de instalacao profissional criada em: {client_dist}")

if __name__ == "__main__":
    build_edge_agent()
