from ultralytics import YOLO
model = YOLO("yolo11n.pt")

# เทรนโมเดลเท่านั้น
model.train(
    data="coco8.yaml",   # path ไปยังไฟล์ dataset.yaml
    epochs=100,          # จำนวนรอบ epoch
    imgsz=640,           # ขนาดภาพ
    device="cpu"         # ใช้ CPU หรือ GPU (เช่น 0, 1, ...)
)
