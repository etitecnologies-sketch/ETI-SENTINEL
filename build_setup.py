"""
Compila o setup_wizard.py em ETI_SENTINEL_Setup.exe
e o copia automaticamente para ETI_SENTINEL_CLIENT_READY/.
"""
import os
import shutil
import sys
from pathlib import Path

import PyInstaller.__main__


def build_setup() -> None:
    here      = Path(__file__).parent
    dist_dir  = here / "dist"
    build_dir = here / "build"
    client    = here / "ETI_SENTINEL_CLIENT_READY"

    print("Compilando ETI_SENTINEL_Setup.exe...")

    # Limpa builds anteriores apenas do wizard
    for d in [dist_dir, build_dir]:
        spec = d / "ETI_SENTINEL_Setup"
        if spec.exists():
            shutil.rmtree(spec)

    icon_flag = ""
    ico = here / "frontend" / "public" / "favicon.ico"
    if ico.exists():
        icon_flag = f"--icon={ico}"

    params = [
        str(here / "setup_wizard.py"),
        "--name=ETI_SENTINEL_Setup",
        "--onefile",
        "--noconsole",
        "--uac-admin",   # solicita elevação automaticamente no Windows
    ]
    if icon_flag:
        params.append(icon_flag)

    params = [p for p in params if p]
    PyInstaller.__main__.run(params)

    setup_exe = dist_dir / "ETI_SENTINEL_Setup.exe"
    if not setup_exe.exists():
        print("[ERRO] ETI_SENTINEL_Setup.exe nao foi gerado.")
        sys.exit(1)

    size_mb = round(setup_exe.stat().st_size / 1_048_576, 1)
    print(f"OK: ETI_SENTINEL_Setup.exe gerado ({size_mb} MB)")

    # Copia para a pasta de distribuicao do cliente
    if client.exists():
        dest = client / "ETI_SENTINEL_Setup.exe"
        shutil.copy2(setup_exe, dest)
        print(f"OK: Copiado para {dest}")
    else:
        print("AVISO: ETI_SENTINEL_CLIENT_READY nao encontrada. Rode build_exe.py primeiro.")

    print("\nPronto! Distribua ETI_SENTINEL_CLIENT_READY/ com o Setup incluido.")
    print("O cliente so precisa dar duplo clique em ETI_SENTINEL_Setup.exe")


if __name__ == "__main__":
    build_setup()
