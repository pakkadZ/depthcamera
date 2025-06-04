# ✅ Enhanced: Show saved camera points and compute affine transform after all points saved

import tkinter as tk
from tkinter import ttk
from queue import Queue
import cv2
import numpy as np
from pyorbbecsdk import Config, OBSensorType, OBFormat, Pipeline, FrameSet
from ultralytics import YOLO
from PIL import Image, ImageTk
import json
import os
import csv

# --------------------- FIXED SETTINGS ---------------------
model_path = "yoloCode/mark.pt"
FLIP_IMAGE = True
MAIN_LABEL = "dot"
model = YOLO(model_path)

# --------------------- CAMERA INIT ---------------------
queue = Queue()
MAX_QUEUE_SIZE = 5

frame_buffer = []
camera_points = []
robot_points = []
current_index = 0


def on_new_frame_callback(frame: FrameSet):
    if frame is None:
        return
    if queue.qsize() >= MAX_QUEUE_SIZE:
        queue.get()
    queue.put(frame)

config_cam = Config()
pipeline = Pipeline()

color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
color_profile = color_profiles.get_video_stream_profile(640, 0, OBFormat.RGB, 30)
config_cam.enable_stream(color_profile)

pipeline.start(config_cam, lambda frames: on_new_frame_callback(frames))

# --------------------- FUNCTION ---------------------
def frame_to_bgr_image(color_frame):
    img = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
    img = img.reshape((color_frame.get_height(), color_frame.get_width(), 3))
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

def detect_reference_points(img):
    points = []
    results = model(img, verbose=False)
    for result in results:
        if not result.boxes:
            continue
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = model.names.get(cls_id, None)
            if label == MAIN_LABEL:
                x1, y1, x2, y2 = box.xyxy[0]
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                points.append((cx, cy, int(x1), int(y1), int(x2), int(y2)))
    points.sort(key=lambda p: p[1])
    return points

def draw_result(img, point):
    img_height, img_width = img.shape[:2]
    cv2.line(img, (img_width // 2, 0), (img_width // 2, img_height), (255, 255, 255), 1)
    cv2.line(img, (0, img_height // 2), (img_width, img_height // 2), (255, 255, 255), 1)

    if point:
        cx, cy, x1, y1, x2, y2 = point
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(img, (cx, cy), 5, (0, 0, 255), -1)
        cx_centered = cx - img_width // 2
        cy_centered = cy - img_height // 2  # 🔁 เปลี่ยนเป็นค่าตรงเพื่อให้ตรงกับทิศหุ่น
        coord_label.config(text=f"{current_index+1}. ({cx_centered}, {cy_centered})")
    else:
        coord_label.config(text=f"{current_index+1}. (-, -)")

    image = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    imgtk = ImageTk.PhotoImage(image=image)
    video_label.imgtk = imgtk
    video_label.configure(image=imgtk)

def average_current_point():
    if len(frame_buffer) < 10:
        status_label.config(text="⏳ Need at least 10 frames")
        return None

    xs = [frame[current_index][0] for frame in frame_buffer if len(frame) > current_index]
    ys = [frame[current_index][1] for frame in frame_buffer if len(frame) > current_index]
    if not xs or not ys:
        return None
    cx_avg = int(np.mean(xs))
    cy_avg = int(np.mean(ys))
    return cx_avg, cy_avg

# --------------------- SAVE CAMERA ONLY ---------------------
def save_camera_point():
    result = average_current_point()
    if not result:
        status_label.config(text="⚠️ Unable to average this point")
        return
    cx, cy = result
    cx_centered = cx - 640 // 2
    cy_centered = cy - 480 // 2  # ✅ ปรับให้ตรงกับค่าที่แสดงใน draw_result

    if len(camera_points) > current_index:
        camera_points[current_index] = [cy_centered, cx_centered]  # 🔁 สลับแกน x,y เพื่อให้ตรงกับพิกัดหุ่น
        saved_points_list.delete(current_index)
        saved_points_list.insert(current_index, f"Point {current_index+1}: ({cx_centered}, {cy_centered})")
    else:
        camera_points.append([cy_centered, cx_centered])  # 🔁 สลับแกน x,y เพื่อให้ตรงกับพิกัดหุ่น
        saved_points_list.insert(tk.END, f"Point {current_index+1}: ({cx_centered}, {cy_centered})")

    status_label.config(text=f"📷 Saved camera point {current_index+1}: ({cx_centered}, {cy_centered})")

    if len(camera_points) == 5:
        open_robot_input_window()

# --------------------- Confirm Robot Input for All ---------------------
def open_robot_input_window():
    def on_confirm_all():
        try:
            for i in range(5):
                xr = float(robot_entries[i][0].get())
                yr = float(robot_entries[i][1].get())
                if len(robot_points) > i:
                    robot_points[i] = [xr, yr]
                else:
                    robot_points.append([xr, yr])
            robot_win.destroy()

            # ✅ Compute affine transform
            A = np.hstack([np.array(camera_points), np.ones((len(camera_points), 1))])
            Bx = np.array([p[0] for p in robot_points])
            By = np.array([p[1] for p in robot_points])
            params_x, _, _, _ = np.linalg.lstsq(A, Bx, rcond=None)
            params_y, _, _, _ = np.linalg.lstsq(A, By, rcond=None)
            result = (
                f"x_robot = {params_x[0]:.4f} * x + {params_x[1]:.4f} * y + {params_x[2]:.4f}\n"
                f"y_robot = {params_y[0]:.4f} * x + {params_y[1]:.4f} * y + {params_y[2]:.4f}"
            )
            tk.messagebox.showinfo("Affine Transform Result", result)
        except:
            tk.messagebox.showerror("Input Error", "Please enter valid numbers.")

    robot_win = tk.Toplevel(window)
    robot_win.title("Enter All Robot Coordinates")
    robot_entries.clear()

    for i in range(5):
        frame = ttk.Frame(robot_win)
        frame.pack(pady=3)
        ttk.Label(frame, text=f"Point {i+1}:").pack(side="left")
        ttk.Label(frame, text="X:").pack(side="left")
        x_entry = ttk.Entry(frame, width=10)
        x_entry.pack(side="left")
        ttk.Label(frame, text="Y:").pack(side="left")
        y_entry = ttk.Entry(frame, width=10)
        y_entry.pack(side="left")
        robot_entries.append((x_entry, y_entry))

    ttk.Button(robot_win, text="Confirm All", command=on_confirm_all).pack(pady=10)

# --------------------- MAIN LOOP ---------------------
def rendering_loop():
    if not queue.empty():
        frames = queue.get()
        color_frame = frames.get_color_frame()
        if color_frame is None:
            window.after(10, rendering_loop)
            return

        color_img = frame_to_bgr_image(color_frame)
        if FLIP_IMAGE:
            color_img = cv2.flip(color_img, -1)

        points = detect_reference_points(color_img)
        if len(points) > current_index:
            if len(frame_buffer) >= 10:
                frame_buffer.pop(0)
            frame_buffer.append(points)
            draw_result(color_img, points[current_index])
        else:
            draw_result(color_img, None)

    window.after(10, rendering_loop)

def next_point():
    global current_index, frame_buffer
    current_index += 1
    frame_buffer.clear()
    if not queue.empty():
        frames = queue.queue[-1]
        color_frame = frames.get_color_frame()
        if color_frame:
            color_img = frame_to_bgr_image(color_frame)
            if FLIP_IMAGE:
                color_img = cv2.flip(color_img, -1)
            points = detect_reference_points(color_img)
            if current_index >= len(points):
                current_index = 0
    coord_label.config(text=f"{current_index+1}. (-, -)")
    status_label.config(text="➡️ Switched to next point")

# --------------------- UI SETUP ---------------------
window = tk.Tk()
window.title("Single Point Calibrator")
window.geometry("720x800")

video_label = ttk.Label(window)
video_label.pack(pady=10)

coord_label = ttk.Label(window, text="1. (-, -)", font=("Arial", 12))
coord_label.pack()

save_button = ttk.Button(window, text="💾 Save Camera Point", command=save_camera_point)
save_button.pack(pady=10)

next_button = ttk.Button(window, text="➡️ Next Point", command=next_point)
save_button.pack(pady=5)

saved_points_list = tk.Listbox(window, height=8, font=("Courier", 10))
saved_points_list.pack(pady=10, fill=tk.X, padx=20)

status_label = ttk.Label(window, text="", font=("Arial", 11), foreground="blue")
status_label.pack(pady=10)

robot_entries = []

window.after(100, rendering_loop)
window.mainloop()
