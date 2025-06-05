# ✅ 1. โคลนโปรเจกต์จาก GitHub
```bash
git clone https://github.com/pakkadZ/pyorbbecsdk.git
```
# ✅ 2. ตรวจสอบ Python เวอร์ชัน (ต้องเป็น Python 3.10.4)
```bash
python --version
```
## 2.1 python 3.10.4
```bash
https://www.python.org/downloads/release/python-3104/
```



# ✅ 3. สร้าง Virtual Environment

```bash
cd pyorbbecsdk
python -m venv venv
```
# ✅ 4. เปิดใช้งาน Virtual Environment (ทำในcmdเท่านั้น)
```bash
venv\Scripts\activate
```
# ✅ 5. ติดตั้งไลบรารีทั้งหมด
```bash
pip install -r requirements.txt
```
# ✅ 6. รันโปรแกรม
```bash
set PYTHONPATH=%cd%\install\lib
venv\Scripts\activate
python yoloCode\codever2\Main.py
```


# ✅ สำหรับการก๊อปผ่านflashdrive 
```bash
cd pyorbbecsdk
python -m venv .venv
venv\Scripts\activate
pip install -r requirements.txt
```
รันโปรแกรม
```bash
.venv\Scripts\activate
python src/Main_robot.py
```
