import socket
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, Toplevel, StringVar
from tkinter.ttk import Combobox
from queue import Queue
import cv2
import numpy as np
from pyorbbecsdk import Config, OBSensorType, OBFormat, Pipeline, FrameSet
from ultralytics import YOLO
from PIL import Image, ImageTk
import json
import os
import time
from threading import Lock

# --------------------- CONFIG LOAD/SAVE json ---------------------
CONFIG_FILE = "config.json"
default_config = {
    "IP_ROBOT": "192.168.201.1",
    "PORT": 6601,
    "YOLO_MODEL": "Ai_pt_place/grey.pt",
    "FLIP_IMAGE": True,
    "SHOW_DEPTH": True
}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = default_config.copy()

for key in default_config:
    if key not in config:
        config[key] = default_config[key]

with open(CONFIG_FILE, "w") as f:
    json.dump(config, f, indent=4)

IP_ROBOT = config.get("IP_ROBOT", default_config["IP_ROBOT"])
PORT = config.get("PORT", default_config["PORT"])
model_path = config.get("YOLO_MODEL", default_config["YOLO_MODEL"])
FLIP_IMAGE = config.get("FLIP_IMAGE", True)
SHOW_DEPTH = config.get("SHOW_DEPTH", True)
MAIN_LABEL = config.get("MAIN_LABEL", "grey")
HEAD_LABEL = config.get("HEAD_LABEL", "head")
model = YOLO(model_path)


# --------------------- SETUP ---------------------
window = tk.Tk()
window.title("Robot Control Panel")
window.geometry("1400x900")
window.config(bg="white")

sock = None
queue = Queue()
MAX_QUEUE_SIZE = 5
is_adjusting_ry = False
adjust_position = True
has_aligned_once = False 
stop_rendering = False
is_connected = False
send_lock = Lock()

# --------------------- START STREAM ---------------------
config_cam = Config()
pipeline = Pipeline()
try:
    color_profiles = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
    color_profile = color_profiles.get_video_stream_profile(640, 0, OBFormat.RGB, 30)
    config_cam.enable_stream(color_profile)
    depth_profiles = pipeline.get_stream_profile_list(OBSensorType.DEPTH_SENSOR)
    depth_profile = depth_profiles.get_default_video_stream_profile()
    config_cam.enable_stream(depth_profile)
    pipeline.start(config_cam, lambda frames: on_new_frame_callback(frames))
except Exception as e:
    print("Error configuring streams:", e)
    exit(1)


# --------------------- FUNCTIONคำนวณ  ตำแหน่ง ------------------------------

def display_info(img, main_obj, head_obj, depth_data):
    global is_adjusting_ry, adjust_position, has_aligned_once

    if main_obj:
        cx, cy, x1, y1, x2, y2 = main_obj
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.circle(img, (cx, cy), 5, (0, 255, 0), -1)

        centered_cx = cx - img.shape[1] // 2
        centered_cy = -(cy - img.shape[0] // 2)
        center_distance = depth_data[cy, cx] if 0 <= cy < depth_data.shape[0] and 0 <= cx < depth_data.shape[1] else 0

        centered_hcx = 0
        centered_hcy = 0
        if is_adjusting_ry and mode_var.get() == 1 and head_obj:
            hcx, hcy, *_ = head_obj
            centered_hcx = hcx - img.shape[1] // 2
            centered_hcy = -(hcy - img.shape[0] // 2)
            handle_head_alignment(centered_cy, centered_hcy)

        label_all.config(text=f"X: {centered_cx}   Y: {centered_cy}   Z: {int(center_distance)}   rx: {centered_hcx if mode_var.get() == 1 else '-'}   ry: {centered_hcy if mode_var.get() == 1 else '-'}")

        if is_adjusting_ry and mode_var.get() != 1:
            is_adjusting_ry = False
            adjust_position = False

        if not adjust_position and not has_aligned_once and sock:
            send_alignment_commands(centered_cx, centered_cy, int(center_distance))

    else:
        label_all.config(text="X: -   Y: -   Z: -   rx: -   ry: -")

def calculate_distance(x, y):
    return np.sqrt(x**2 + y**2)

def detect_closest_object(color_img, target_label):
    results = model(color_img, verbose=False)
    min_distance = float('inf')
    closest_object = None
    if not results:
        return None
    for result in results:
        if not result.boxes:
            continue
        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = model.names.get(cls_id, None)
            if label == target_label:
                x1, y1, x2, y2 = box.xyxy[0]
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                distance = calculate_distance(cx - color_img.shape[1] // 2, cy - color_img.shape[0] // 2)
                if distance < min_distance:
                    min_distance = distance
                    closest_object = (cx, cy, int(x1), int(y1), int(x2), int(y2))
    return closest_object

def detect_objects(img):
    main_obj = detect_closest_object(img, MAIN_LABEL)
    head_obj = detect_closest_object(img, HEAD_LABEL)
    return main_obj, head_obj

# --------------------- FUNCTION เตรียมภาพ ------------------------------

def frame_to_bgr_image(color_frame):
    img = np.frombuffer(color_frame.get_data(), dtype=np.uint8)
    img = img.reshape((color_frame.get_height(), color_frame.get_width(), 3))
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

def on_new_frame_callback(frame: FrameSet):
    if frame is None:
        return
    if queue.qsize() >= MAX_QUEUE_SIZE:
        queue.get()
    queue.put(frame)

def extract_images(frames):
    depth_frame = frames.get_depth_frame()
    color_frame = frames.get_color_frame()
    if depth_frame is None or color_frame is None:
        return None, None

    height = depth_frame.get_height()
    width = depth_frame.get_width()
    depth_data = np.frombuffer(depth_frame.get_data(), dtype=np.uint16).reshape((height, width))
    depth_data = depth_data.astype(np.float32) * depth_frame.get_depth_scale()
    color_img = frame_to_bgr_image(color_frame)
    return color_img, depth_data

def update_depth_view(depth_data, target_shape):
    depth_vis = cv2.normalize(depth_data, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    depth_colormap = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
    depth_colormap = cv2.resize(depth_colormap, (target_shape[1], target_shape[0]))
    if FLIP_IMAGE:
        depth_colormap = cv2.flip(depth_colormap, -1)
    depth_image = Image.fromarray(depth_colormap)
    depth_imgtk = ImageTk.PhotoImage(image=depth_image)
    depth_video_label.imgtk = depth_imgtk
    depth_video_label.configure(image=depth_imgtk)

def draw_image_to_gui(img):
    image = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    imgtk = ImageTk.PhotoImage(image=image)
    video_label.imgtk = imgtk
    video_label.configure(image=imgtk)


########################## loop logic หลัก ##################################

def rendering_loop(): # Loop เรียกใช้คำสั่งย่อย
    if stop_rendering:
        return

    if not queue.empty():
        frames = queue.get()
        color_img, depth_data = extract_images(frames)
        if color_img is None or depth_data is None:
            window.after(10, rendering_loop)
            return

        if FLIP_IMAGE:
            color_img = cv2.flip(color_img, -1)

        if SHOW_DEPTH:
            update_depth_view(depth_data, color_img.shape)

        main_obj, head_obj = detect_objects(color_img)
        display_info(color_img, main_obj, head_obj, depth_data)
        draw_image_to_gui(color_img)

    window.after(10, rendering_loop)

x_rules = [
    ((-float('inf'), -100), "lright"),  # ซ้ายสุด
    ((-100, -20), "mright"),
    ((-20, -1), "right"),
    ((1, 20), "left"),
    ((20, 100), "mleft"),
    ((100, float('inf')), "lleft")     # ขวาสุด
]

y_rules = [
    ((-float('inf'), -100), "llow"),    # บนสุด
    ((-100, -20), "mlow"),
    ((-20, -1), "low"),
    ((1, 20), "top"),
    ((20, 100), "mtop"),
    ((100, float('inf')), "ltop")       # ล่างสุด
]

z_rules = [
    ((300, float('inf')), "ldown"),
    ((280, 300), "mdown"),
    ((251, 280), "down"),
    ((0, 249), "up")]

def get_direction_command(value, rules): #  เงื่อนไขข้อความx, y, z 
    for (low, high), command in rules:
        if low <= value < high:
            return command
    return None

def send_alignment_commands(x, y, z): #  ลำดับการส่ง x, y, z 
    message = get_direction_command(x, x_rules) or "stopx"
    if message != "stopx":
        send_command(message)
        return

    message = get_direction_command(y, y_rules) or "stopy"
    if message != "stopy":
        send_command(message)
        return

    message = get_direction_command(z, z_rules) or "stopz"
    if message != "stopz":
        send_command(message)
    elif message == "stopz":
        command_repeat()

def handle_head_alignment(main_cy, head_cy): # เงื่อนไขข้อความ หมุน rz 
    global is_adjusting_ry, adjust_position
    if sock:
        if head_cy < main_cy - 1:
            send_command("rzP")
        elif head_cy > main_cy + 1:
            send_command("rzM")
        else:
            send_command("stopc")
            is_adjusting_ry = False
            adjust_position = False



# --------------------- FUNCTION คำสั่งใช้ในปุ่ม และการเชื่อมต่อ  ------------------------------
def command_repeat():
    global stop_rendering, adjust_position, is_adjusting_ry, has_aligned_once
    if mode_repeat.get() == 1:
        print("wait")
        is_adjusting_ry = False
        adjust_position = True
        send_command("stopz")

    elif mode_repeat.get() != 1:
        is_adjusting_ry = True
        adjust_position = True
        time.sleep(1)
        send_command("stopz")
        time.sleep(3)
                       
def connect_socket():
    global sock, is_connected
    if sock:
        try:
            sock.close()
        except:
            pass
        sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((IP_ROBOT, PORT))
        is_connected = True
        print("✅ Reconnected to robot.")
        return True
    except socket.error as e:
        is_connected = False
        print(f"❌ Reconnection failed: {e}")
        return False

def send_command(message):
    global sock, is_connected
    with send_lock:
        if not is_connected:
            print("❌ Not connected. Skipping command.")
            return
        try:
            sock.sendall(message.encode())
            print(f"✅ Sent: {message}")
        except socket.error as e:
            print(f"⚠️ Socket error: {e}. Attempting to reconnect...")
            if connect_socket():
                try:
                    sock.sendall(message.encode())
                    print(f"✅ Resent after reconnect: {message}")
                except socket.error as e2:
                    print(f"❌ Failed to resend after reconnect: {e2}")
                    sock = None
                    is_connected = False
            else:
                print("❌ Reconnection failed.")
                sock = None
                is_connected = False

def on_connect():
    if connect_socket():
        btn_connect.config(state="disabled")

def stop_connection():
    global sock, is_adjusting_ry, adjust_position, is_connected, has_aligned_once
    if sock:
        send_command("disconnected")
        is_connected = False
        adjust_position = False
        is_adjusting_ry = False
        has_aligned_once = False
        try:
            sock.close()
        except:
            pass
        sock = None
        messagebox.showinfo("Connection Closed", "The connection has been closed.")
        btn_connect.config(state="enabled")
        time.sleep(3)
        
def on_again_pressed():
    global adjust_position, is_adjusting_ry, has_aligned_once
    if not is_connected:
        messagebox.showwarning("Not Connected", "⚠️ กรุณาเชื่อมต่อหุ่นยนต์ก่อนกด 'Again'")
        return
    adjust_position = True
    is_adjusting_ry = True
    has_aligned_once = False
    print("Starting over from centered_cx...")

def on_closing():
    global stop_rendering
    stop_rendering = True

    try:
        send_command("disconnected")  # แจ้ง DoBot ว่าจะปิดโปรแกรม
        time.sleep(3)                # รอให้ DoBot ดำเนินการปิด socket
    except Exception as e:
        print(f"⚠️ Failed to notify robot: {e}")

    try:
        pipeline.stop()              # หยุดกล้อง Orbbec
    except Exception:
        pass

    window.destroy()  

def open_config_window():
    flip_var = tk.BooleanVar(value=config.get("FLIP_IMAGE", True))
    show_depth_var = tk.BooleanVar(value=config.get("SHOW_DEPTH", True))

    config_win = Toplevel(window)
    config_win.title("Configuration")
    config_win.geometry("600x400")

    ip_var = tk.StringVar(value=IP_ROBOT)
    port_var = tk.StringVar(value=str(PORT))
    model_path_var = tk.StringVar(value=model_path)

    # ดึง class names จาก YOLO model
    label_options = list(model.names.values()) if hasattr(model, "names") else []
    main_label_var = tk.StringVar(value=config.get("MAIN_LABEL", "grey"))
    head_label_var = tk.StringVar(value=config.get("HEAD_LABEL", "head"))

    ttk.Label(config_win, text="Robot IP:").grid(row=0, column=0, sticky="e", padx=5, pady=2)
    ttk.Entry(config_win, textvariable=ip_var, width=20).grid(row=0, column=1, columnspan=2, sticky="we", padx=5, pady=2)

    ttk.Label(config_win, text="Port:").grid(row=1, column=0, sticky="e", padx=5, pady=2)
    ttk.Entry(config_win, textvariable=port_var, width=20).grid(row=1, column=1, columnspan=2, sticky="we", padx=5, pady=2)

    ttk.Label(config_win, text="YOLO Model Path:").grid(row=2, column=0, sticky="e")
    ttk.Entry(config_win, textvariable=model_path_var, width=40).grid(row=2, column=1, padx=5, columnspan=1, sticky="w")
    ttk.Button(config_win, text="📁 Browse", command=lambda: model_path_var.set(
        filedialog.askopenfilename(filetypes=[("YOLO Model", "*.pt")])
    )).grid(row=2, column=2, padx=5)

    ttk.Label(config_win, text="Main Object Label:").grid(row=3, column=0, sticky="e", padx=5, pady=2)
    main_combo = Combobox(config_win, textvariable=main_label_var, values=label_options, state="readonly")
    main_combo.grid(row=3, column=1, sticky="w", padx=5, pady=2)

    ttk.Label(config_win, text="Head Object Label:").grid(row=4, column=0, sticky="e", padx=5, pady=2)
    head_combo = Combobox(config_win, textvariable=head_label_var, values=label_options, state="readonly")
    head_combo.grid(row=4, column=1, sticky="w", padx=5, pady=2)

    ttk.Checkbutton(config_win, text="Flip Image", variable=flip_var).grid(row=5, column=1, sticky="w", pady=5)
    ttk.Checkbutton(config_win, text="Show Depth View", variable=show_depth_var).grid(row=6, column=1, sticky="w", pady=5)

    def on_apply_settings():
        global IP_ROBOT, PORT, model, FLIP_IMAGE, SHOW_DEPTH, MAIN_LABEL, HEAD_LABEL
        IP_ROBOT = ip_var.get()
        PORT = int(port_var.get())
        model_path = model_path_var.get()
        FLIP_IMAGE = flip_var.get()
        SHOW_DEPTH = show_depth_var.get()
        MAIN_LABEL = main_label_var.get()
        HEAD_LABEL = head_label_var.get()

        model = YOLO(model_path)

        new_config = {
            "IP_ROBOT": IP_ROBOT,
            "PORT": PORT,
            "YOLO_MODEL": model_path,
            "FLIP_IMAGE": FLIP_IMAGE,
            "SHOW_DEPTH": SHOW_DEPTH,
            "MAIN_LABEL": MAIN_LABEL,
            "HEAD_LABEL": HEAD_LABEL
        }

        with open(CONFIG_FILE, "w") as f:
            json.dump(new_config, f, indent=4)

        messagebox.showinfo("Settings Applied", "✅ Settings saved and applied.")
        config_win.destroy()

    def on_reset_to_default():
        global IP_ROBOT, PORT, model, FLIP_IMAGE, SHOW_DEPTH, MAIN_LABEL, HEAD_LABEL
        default_config = {
            "IP_ROBOT": "192.168.201.1",
            "PORT": 6601,
            "YOLO_MODEL": "Ai_pt_place/grey.pt",
            "FLIP_IMAGE": True,
            "SHOW_DEPTH": True,
            "MAIN_LABEL": "grey",
            "HEAD_LABEL": "head"
        }
        IP_ROBOT = default_config["IP_ROBOT"]
        PORT = default_config["PORT"]
        model = YOLO(default_config["YOLO_MODEL"])
        FLIP_IMAGE = default_config["FLIP_IMAGE"]
        SHOW_DEPTH = default_config["SHOW_DEPTH"]
        MAIN_LABEL = default_config["MAIN_LABEL"]
        HEAD_LABEL = default_config["HEAD_LABEL"]

        with open(CONFIG_FILE, "w") as f:
            json.dump(default_config, f, indent=4)

        messagebox.showinfo("Reset Done", "🌀 Config reset to default.")
        config_win.destroy()

    ttk.Button(config_win, text="✅ Apply Settings", command=on_apply_settings).grid(row=7, column=0, columnspan=1, padx=5, pady=10)
    ttk.Button(config_win, text="🔄 Reset to Default", command=on_reset_to_default).grid(row=7, column=1, columnspan=1, padx=5, pady=10)
    ttk.Label(config_win, text="🔁 กรุณารีสตาร์ทโปรแกรมหลังจากเปลี่ยนค่า Config", foreground="red").grid(row=8, column=0, columnspan=3, pady=(0, 10))

# --------------------- UI SETUP ---------------------
def setup_ui(window):

    global video_label, depth_video_label, label_all
    global mode_var, mode_z, mode_repeat
    global btn_connect

    style = ttk.Style()
    style.configure("TLabel", font=("Arial", 12), background="white")
    style.configure("TButton", font=("Arial", 11), padding=6)
    style.configure("TFrame", background="white")

    main_frame = ttk.Frame(window, padding=10)
    main_frame.pack(fill=tk.BOTH, expand=True)
    main_frame.columnconfigure((0, 1, 2), weight=1)
    main_frame.rowconfigure((0, 1, 2, 3), weight=1)

    video_frame = ttk.LabelFrame(main_frame, text="Camera Feed", padding=10)
    video_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
    video_frame.columnconfigure((0, 1), weight=1)

    video_label = ttk.Label(video_frame)
    video_label.grid(row=0, column=0, padx=5, sticky="nsew")

    depth_video_label = ttk.Label(video_frame)
    depth_video_label.grid(row=0, column=1, padx=5, sticky="nsew")

    position_frame = ttk.LabelFrame(main_frame, text="Object Coordinates", padding=10)
    position_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
    label_all = ttk.Label(position_frame, text="X: 0   Y: 0   Z: 0   rx: 0   ry: 0", width=40)
    label_all.pack(anchor="w")

    button_frame = ttk.LabelFrame(main_frame, text="Controls", padding=10)
    button_frame.grid(row=1, column=1, columnspan=2, sticky="nsew", padx=5, pady=5)
    button_frame.columnconfigure((0, 1, 2), weight=1)

    btn_connect = ttk.Button(button_frame, text="🔌 Connect Robot", command=on_connect)
    btn_connect.grid(row=0, column=0, padx=5, pady=5)

    btn_disconnect = ttk.Button(button_frame, text="❌ Disconnect", command=stop_connection)
    btn_disconnect.grid(row=0, column=1, padx=5, pady=5)

    btn_again = ttk.Button(button_frame, text="↩️ Again", command=on_again_pressed)
    btn_again.grid(row=0, column=2, padx=5, pady=5)

    mode_frame = ttk.LabelFrame(main_frame, text="Operation Mode", padding=10)
    mode_frame.grid(row=2, column=0, columnspan=1, sticky="ew", padx=5, pady=5)
    mode_var = tk.IntVar(value=1)
    tk.Radiobutton(mode_frame, text="จัด rz", variable=mode_var, value=1, background="white").pack(anchor="w")
    tk.Radiobutton(mode_frame, text="ไม่จัด rz", variable=mode_var, value=2, background="white").pack(anchor="w")

    mode_frame = ttk.LabelFrame(main_frame, text="Operation Mode", padding=10)
    mode_frame.grid(row=2, column=1, columnspan=1, sticky="ew", padx=5, pady=5)
    mode_z = tk.IntVar(value=1)
    tk.Radiobutton(mode_frame, text="จัด Z", variable=mode_z, value=1, background="white").pack(anchor="w")
    tk.Radiobutton(mode_frame, text="ไม่จัด Z", variable=mode_z, value=2, background="white").pack(anchor="w")

    mode_frame = ttk.LabelFrame(main_frame, text="Operation Mode", padding=10)
    mode_frame.grid(row=2, column=2, columnspan=1, sticky="ew", padx=5, pady=5)
    mode_repeat = tk.IntVar(value=1)
    tk.Radiobutton(mode_frame, text="ทีละชิ้น", variable=mode_repeat, value=1, background="white").pack(anchor="w")
    tk.Radiobutton(mode_frame, text="ทุกชิ้น", variable=mode_repeat, value=2, background="white").pack(anchor="w")

    ttk.Button(main_frame, text="⚙️ Advanced Config", command=open_config_window).grid(row=3, column=0, columnspan=3, pady=10)

# --------------------- WINDOW ---------------------
setup_ui(window)
window.protocol("WM_DELETE_WINDOW", on_closing)
rendering_loop()
window.mainloop()
