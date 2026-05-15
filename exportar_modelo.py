"""
ETI SENTINEL - Exportador de Modelo para ONNX
==============================================
Execute este script UMA VEZ na maquina do desenvolvedor
para converter o modelo YOLOv8 para o formato ONNX leve.

O arquivo gerado vai para bin/ e e distribuido junto no pendrive.

Uso:
    python exportar_modelo.py
    python exportar_modelo.py --model yolov8s  (mais preciso, 28MB)
    python exportar_modelo.py --model yolov8n  (mais rapido, 12MB) [padrao]
"""

import argparse
import json
import os
import sys
import shutil
from pathlib import Path


# Nomes das 80 classes do COCO (dataset padrao do YOLOv8)
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
    "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana",
    "apple", "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza",
    "donut", "cake", "chair", "couch", "potted plant", "bed", "dining table",
    "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]


def check_deps():
    try:
        import ultralytics  # noqa
        print("  [OK] ultralytics encontrado.")
    except ImportError:
        print("  [!] ultralytics nao encontrado. Instalando...")
        os.system(f"{sys.executable} -m pip install ultralytics --quiet")
        try:
            import ultralytics  # noqa
            print("  [OK] ultralytics instalado.")
        except ImportError:
            print("  [ERRO] Nao foi possivel instalar ultralytics.")
            print("  Execute manualmente: pip install ultralytics")
            sys.exit(1)

    try:
        import onnxruntime  # noqa
        print("  [OK] onnxruntime encontrado.")
    except ImportError:
        print("  [!] onnxruntime nao encontrado. Instalando versao com GPU Windows (DirectML)...")
        os.system(f"{sys.executable} -m pip install onnxruntime-directml --quiet")
        try:
            import onnxruntime  # noqa
            print("  [OK] onnxruntime instalado.")
        except ImportError:
            print("  [AVISO] onnxruntime nao instalado. Tente: pip install onnxruntime")


def export_model(model_name: str, output_dir: Path, img_size: int = 640) -> Path:
    from ultralytics import YOLO

    print(f"\n  Carregando modelo {model_name}.pt...")
    model = YOLO(f"{model_name}.pt")

    print(f"  Exportando para ONNX (imgsz={img_size}, simplify=True)...")
    exported = model.export(
        format="onnx",
        imgsz=img_size,
        simplify=True,
        opset=12,
        dynamic=False,
    )

    onnx_src = Path(exported)
    if not onnx_src.exists():
        onnx_src = Path(f"{model_name}.onnx")

    if not onnx_src.exists():
        raise FileNotFoundError(f"Arquivo ONNX nao encontrado: {onnx_src}")

    output_dir.mkdir(parents=True, exist_ok=True)
    onnx_dest = output_dir / "modelo_ia.onnx"
    shutil.copy2(onnx_src, onnx_dest)

    size_mb = onnx_dest.stat().st_size / (1024 * 1024)
    print(f"  [OK] Modelo exportado: {onnx_dest} ({size_mb:.1f} MB)")

    return onnx_dest


def save_classes(output_dir: Path, classes: list) -> Path:
    classes_file = output_dir / "onnx_classes.json"
    with open(classes_file, "w", encoding="utf-8") as f:
        json.dump({"classes": classes}, f, ensure_ascii=False, indent=2)
    print(f"  [OK] Classes salvas: {classes_file}")
    return classes_file


def validate_model(onnx_path: Path) -> bool:
    print("\n  Validando modelo exportado...")
    try:
        import onnxruntime as ort
        import numpy as np

        providers = []
        try:
            if "DmlExecutionProvider" in ort.get_available_providers():
                providers.append("DmlExecutionProvider")
        except Exception:
            pass
        providers.append("CPUExecutionProvider")

        sess = ort.InferenceSession(str(onnx_path), providers=providers)
        inp = sess.get_inputs()[0]
        dummy = np.zeros(inp.shape, dtype=np.float32)
        out = sess.run(None, {inp.name: dummy})
        print(f"  [OK] Modelo validado. Saida: {[o.shape for o in out]}")
        return True
    except Exception as e:
        print(f"  [AVISO] Validacao falhou: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Exporta modelo YOLOv8 para ONNX")
    parser.add_argument("--model", default="yolov8n", help="Modelo: yolov8n (rapido) ou yolov8s (preciso)")
    parser.add_argument("--imgsz", type=int, default=640, help="Tamanho de entrada (padrao: 640)")
    parser.add_argument("--output", default=None, help="Pasta de saida (padrao: bin/)")
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    output_dir = Path(args.output) if args.output else here / "bin"

    print()
    print("  ============================================================")
    print("    ETI SENTINEL - Exportador de Modelo IA para ONNX")
    print("  ============================================================")
    print()
    print("  [1/4] Verificando dependencias...")
    check_deps()

    print(f"\n  [2/4] Exportando {args.model} para ONNX...")
    try:
        onnx_path = export_model(args.model, output_dir, args.imgsz)
    except Exception as e:
        print(f"  [ERRO] Falha na exportacao: {e}")
        sys.exit(1)

    print("\n  [3/4] Salvando nomes das classes...")
    save_classes(output_dir, COCO_CLASSES)

    print("\n  [4/4] Validando modelo...")
    validate_model(onnx_path)

    print()
    print("  ============================================================")
    print("    EXPORTACAO CONCLUIDA!")
    print()
    print(f"    Modelo:  {output_dir / 'modelo_ia.onnx'}")
    print(f"    Classes: {output_dir / 'onnx_classes.json'}")
    print()
    print("    Proximo passo:")
    print("      python build_exe.py")
    print("  ============================================================")
    print()


if __name__ == "__main__":
    main()
