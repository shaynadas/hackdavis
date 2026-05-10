"""
export_ncnn.py — one-time conversion of YOLOv8n to NCNN format

NCNN is roughly 3-5x faster than PyTorch on Pi 4B ARM, which is the
difference between 1.5 FPS and 6 FPS at imgsz=320.

This produces a folder ./yolov8n_ncnn_model/ that cv_pipeline_pi.py
auto-detects and loads. Run this once after `pip install ultralytics`.

If it OOMs on a 4GB Pi, increase swap to 2GB first (see setup.sh).
"""

from ultralytics import YOLO

IMGSZ = 320  # MUST match INFERENCE_IMGSZ in cv_pipeline_pi.py


def main():
    print(f'[export] loading yolov8n.pt (downloads ~6 MB on first run)')
    m = YOLO('yolov8n.pt')

    print(f'[export] exporting to NCNN at imgsz={IMGSZ}')
    print(f'[export] this takes 5-10 minutes and uses ~2 GB RAM')
    m.export(format='ncnn', imgsz=IMGSZ)

    print(f'[export] done. created ./yolov8n_ncnn_model/')
    print(f'[export] cv_pipeline_pi.py will pick it up automatically')


if __name__ == '__main__':
    main()
