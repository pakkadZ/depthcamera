# --- GUI กล้องเลือก Orbbec หรือ Webcam พร้อม Config บันทึกลง webcam_config.json ---
import cv2
import os
import json
import numpy as np
from datetime import datetime
from tkinter import Tk, Button, Label, Frame, Toplevel, filedialog, IntVar, BooleanVar, StringVar, Radiobutton, Checkbutton, OptionMenu, messagebox
from PIL import Image, ImageTk
# เพิ่มตัวแปร global สำหรับแสดง preview และข้อความ overlay
preview_label = None
overlay_label = None
overlay_timer = None

# ---- CONFIG ----
CONFIG_FILE = "webcam_config.json"
default_config = {
    "SAVE_FOLDER": os.path.expanduser("~/Desktop"),
    "WEBCAM_INDEX": 0,
    "RESOLUTION": "640x480",
    "FLIP_IMAGE": "none",
    "CAMERA_MODE": "webcam"
}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    config = default_config.copy()

SAVE_FOLDER = config.get("SAVE_FOLDER", default_config["SAVE_FOLDER"])
webcam_index = config.get("WEBCAM_INDEX", default_config["WEBCAM_INDEX"])
resolution = (640, 480)  # ✅ บังคับใช้ตรงนี้

flip_mode = config.get("FLIP_IMAGE", default_config["FLIP_IMAGE"])  # 'none', 'horizontal', 'vertical'
camera_mode = config.get("CAMERA_MODE", default_config["CAMERA_MODE"])

capture_flag = False
webcam = None
pipeline = None
camera_label = None
root = None

try:
    from pyorbbecsdk import Config as OBConfig, OBError, OBSensorType, OBFormat, Pipeline, FrameSet
    orbbec_available = True
except ImportError:
    orbbec_available = False

# ---- CAPTURE IMAGE ----
def capture_image():
    global capture_flag
    capture_flag = True

# ---- DISPLAY FRAME ----
def update_webcam_frame():
    global capture_flag, webcam
    if webcam is None:
        return  # ✅ ออกจากฟังก์ชันทันทีหาก webcam ยังไม่ได้เปิด

    ret, frame = webcam.read()
    if not ret:
        root.after(10, update_webcam_frame)
        return
    frame = apply_flip(frame)
    handle_frame_output(frame)
    root.after(10, update_webcam_frame)


def update_orbbec_frame():
    global capture_flag, pipeline
    if not pipeline:
        return

    try:
        frames = pipeline.wait_for_frames(1)
    except Exception as e:
        print("Frame wait error:", e)
        root.after(10, update_orbbec_frame)
        return
    if frames is None:
        root.after(10, update_orbbec_frame)
        return
    color_frame = frames.get_color_frame()
    if color_frame is None:
        root.after(10, update_orbbec_frame)
        return
    data = color_frame.get_data()
    width = color_frame.get_width()
    height = color_frame.get_height()
    frame = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 3))[:, :, ::-1]
    frame = apply_flip(frame)
    handle_frame_output(frame)
    root.after(10, update_orbbec_frame)

def apply_flip(frame):
    if flip_mode == "horizontal":
        return cv2.flip(frame, 1)
    elif flip_mode == "vertical":
        return cv2.flip(frame, 0)
    elif flip_mode == "both":
        return cv2.flip(frame, -1)
    return frame


# ---- SHOW OVERLAY TEXT ----
def show_overlay(text):
    global overlay_label, overlay_timer
    if overlay_label:
        overlay_label.config(text=text)
        if overlay_timer:
            root.after_cancel(overlay_timer)
        overlay_timer = root.after(1500, lambda: overlay_label.config(text=""))


# ---- SHOW PREVIEW ----
def show_preview(frame):
    preview_resized = cv2.resize(frame, (160, 120))
    rgb_image = cv2.cvtColor(preview_resized, cv2.COLOR_BGR2RGB)
    imgtk = ImageTk.PhotoImage(image=Image.fromarray(rgb_image))
    preview_label.imgtk = imgtk
    preview_label.config(image=imgtk)



# ---- HANDLE FRAME OUTPUT ----
def handle_frame_output(frame):
    global capture_flag, overlay_timer
    
    if capture_flag:
        capture_flag = False
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(SAVE_FOLDER, f"image_{timestamp}.jpg")
        cv2.imwrite(filename, frame)
        print(f"✅ Captured: {filename}")
        show_overlay("✅ Saved!")
        show_preview(frame)

    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    imgtk = ImageTk.PhotoImage(image=Image.fromarray(rgb_image))
    camera_label.imgtk = imgtk
    camera_label.config(image=imgtk)

# ---- CONFIG GUI ----
def open_config_window():
    global webcam, pipeline,selected_folder_label
   
    if webcam:
        webcam.release()
        webcam = None

    if pipeline:
        try:
            pipeline.stop()
            pipeline = None
        except:
            pass
    def apply_config():
        global SAVE_FOLDER, webcam_index, flip_mode, camera_mode
        SAVE_FOLDER = save_path_var.get()
        webcam_index = int(camera_index_var.get())
        flip_mode = flip_var.get()
        camera_mode = "orbbec" if camera_mode_var.get() == 1 else "webcam"

        config = {
            "SAVE_FOLDER": SAVE_FOLDER,
            "WEBCAM_INDEX": webcam_index,
            "FLIP_IMAGE": flip_mode,
            "CAMERA_MODE": camera_mode
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)

        # ✅ อัปเดต label แสดงโฟลเดอร์ด้านล่างปุ่ม Open Folder
        if folder_path_label:
            folder_path_label.config(text=f"📂 {SAVE_FOLDER}")

        config_win.destroy()
        restart_camera()
        

    def browse_folder():
        global pipeline, selected_folder_label

        if camera_mode == "orbbec" and pipeline:
            try:
                pipeline.stop()
                pipeline = None
            except:
                pass

        path = filedialog.askdirectory()

        if camera_mode == "orbbec" and orbbec_available:
            try:
                config = OBConfig()
                pipeline = Pipeline()
                profile_list = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
                color_profile = profile_list.get_video_stream_profile(640, 0, OBFormat.RGB, 30)
                config.enable_stream(color_profile)
                pipeline.start(config)
                update_orbbec_frame()
            except Exception as e:
                messagebox.showerror("Orbbec Error", str(e))

        if path:
            save_path_var.set(path)
            selected_folder_label.config(text=path)
            config_win.lift()
            config_win.focus_force()



    config_win = Toplevel(root)
    config_win.title("Configuration")
    config_win.geometry("400x300")
    config_win.configure(bg="white")

    main_frame = Frame(config_win, padx=20, pady=20, bg="white")
    main_frame.pack(expand=True)

    Label(main_frame, text="Camera Mode:", bg="white", anchor="w").grid(row=0, column=0, sticky="w")
    camera_mode_var = IntVar(value=1 if camera_mode == "orbbec" else 2)
    Radiobutton(main_frame, text="Orbbec", variable=camera_mode_var, value=1, bg="white").grid(row=0, column=1, sticky="w")
    Radiobutton(main_frame, text="Webcam", variable=camera_mode_var, value=2, bg="white").grid(row=0, column=2, sticky="w")

    Label(main_frame, text="Webcam Index:", bg="white").grid(row=1, column=0, sticky="w", pady=5)
    camera_index_var = StringVar(value=str(webcam_index))
    OptionMenu(main_frame, camera_index_var, *[str(i) for i in range(5)]).grid(row=1, column=1, columnspan=2, sticky="ew")

    Label(main_frame, text="Flip Mode:", bg="white").grid(row=2, column=0, sticky="w", pady=5)
    flip_var = StringVar(value=flip_mode)
    OptionMenu(main_frame, flip_var, "none", "horizontal", "vertical", "both").grid(row=2, column=1, columnspan=2, sticky="ew")

    Label(main_frame, text="Save Folder:", bg="white").grid(row=3, column=0, sticky="w", pady=5)
    save_path_var = StringVar(value=SAVE_FOLDER)
    Button(main_frame, text="Browse...", command=browse_folder).grid(row=3, column=1, columnspan=2, sticky="ew")
    selected_folder_label = Label(main_frame, text=SAVE_FOLDER, bg="white", fg="gray", wraplength=350, anchor="w", justify="left")

    selected_folder_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(5, 10))

    Button(main_frame, text="Apply", command=apply_config).grid(row=4, column=0, columnspan=3, pady=15)
    config_win.protocol("WM_DELETE_WINDOW", lambda: (config_win.destroy(), restart_camera()))


# ---- TOGGLE FLIP MODE ----
def toggle_flip():
    global flip_mode
    if flip_mode == "none":
        flip_mode = "horizontal"
    elif flip_mode == "horizontal":
        flip_mode = "vertical"
    elif flip_mode == "vertical":
        flip_mode = "both"
    else:
        flip_mode = "none"
    flip_label.config(text=f"Flip: {flip_mode}")
    print("Flip mode set to:", flip_mode)



# ---- RESTART CAMERA ----
def restart_camera():
    global webcam, pipeline

    # ปิด webcam ทันทีถ้ามีการเปิดอยู่
    if webcam:
        webcam.release()
        webcam = None

    # ปิด pipeline ของ Orbbec ถ้าเปิดอยู่
    if pipeline:
        try:
            pipeline.stop()
            pipeline = None
        except:
            pass

    if camera_mode == "webcam":
        webcam = cv2.VideoCapture(webcam_index)
        webcam.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
        webcam.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
        update_webcam_frame()

    elif camera_mode == "orbbec" and orbbec_available:
        try:
            config = OBConfig()
            pipeline = Pipeline()
            profile_list = pipeline.get_stream_profile_list(OBSensorType.COLOR_SENSOR)
            color_profile = profile_list.get_video_stream_profile(640, 0, OBFormat.RGB, 30)
            config.enable_stream(color_profile)
            
            pipeline.start(config)
            update_orbbec_frame()
        except Exception as e:
            messagebox.showerror("Orbbec Error", str(e))
    else:
        messagebox.showwarning("Unavailable", "Orbbec SDK is not available.")


# ---- GUI ----
def open_save_folder():
    os.startfile(SAVE_FOLDER)

# ---- GUI ----
def start_main_gui():
    global root, camera_label, preview_label, overlay_label
    root = Tk()
    root.title("Camera Capture GUI")
    root.geometry("1000x800")
    root.configure(bg="#e6e6e6")  # สีพื้นหลังอ่อนๆ

    # ----------- กล้อง Live View -----------
    Label(root, text="📷 Live Camera Feed", font=("Arial", 16, "bold"), bg="#e6e6e6").pack(pady=10)

    camera_frame = Frame(root, bg="black", width=640, height=480)
    camera_frame.pack(pady=5)
    camera_label = Label(camera_frame, bg="black")
    camera_label.pack()

    # ----------- Overlay Saved Text -----------
    overlay_label = Label(root, text="", fg="green", font=("Arial", 12), bg="#e6e6e6")
    overlay_label.pack()

    # ----------- ปุ่มกดต่างๆ -----------
    button_frame = Frame(root, bg="#e6e6e6")
    button_frame.pack(pady=10)

    btn_style = {"font": ("Arial", 11), "width": 15, "padx": 5, "pady": 5}

    Button(button_frame, text="📸 Capture", command=capture_image, **btn_style).grid(row=0, column=0, padx=5)
    Button(button_frame, text="🔁 Flip Mode", command=toggle_flip, **btn_style).grid(row=0, column=1, padx=5)
    Button(button_frame, text="⚙️ Config", command=open_config_window, **btn_style).grid(row=0, column=2, padx=5)
    Button(button_frame, text="📁 Open Folder", command=open_save_folder, **btn_style).grid(row=0, column=3, padx=5)
    global flip_label,folder_path_label
    flip_label = Label(button_frame, text=f"Flip: {flip_mode}", bg="#e6e6e6")
    flip_label.grid(row=1, column=1)
    folder_path_label = Label(button_frame, text=f"📂 {SAVE_FOLDER}", bg="#e6e6e6")
    folder_path_label.grid(row=1, column=3)
    

    # ----------- Preview ล่าสุด -----------
    #Label(root, text="📷 Last Captured Image", font=("Arial", 5), bg="#e6e6e6").pack(pady=(20, 5))
    preview_label = Label(root, bg="gray", width=160, height=120)
    preview_label.pack(pady=5)

    restart_camera()
    root.mainloop()

# ---- MAIN ----
if __name__ == "__main__":
    start_main_gui()
