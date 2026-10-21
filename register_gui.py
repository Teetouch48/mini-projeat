"""หน้าจอลงทะเบียนใบหน้า (Tkinter): python register_gui.py
กรอกรหัสและชื่อ → ดูภาพสดจากกล้อง → กด 'ถ่ายรูป' ประมาณ 5 รูป → กด 'เสร็จสิ้น'"""
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import cv2
import face_recognition
from PIL import Image, ImageTk

import db

KNOWN_DIR = Path("known_faces")


class RegisterApp:
    def __init__(self, root):
        self.root = root
        root.title("FaceCheck - ลงทะเบียนใบหน้า")
        self.cam = cv2.VideoCapture(0)
        self.frame = None
        self.count = 0
        self.folder = None

        form = tk.Frame(root)
        form.pack(padx=10, pady=8)
        tk.Label(form, text="รหัสนักศึกษา").grid(row=0, column=0, sticky="e")
        self.id_var = tk.StringVar()
        tk.Entry(form, textvariable=self.id_var, width=18).grid(row=0, column=1, padx=6)
        tk.Label(form, text="ชื่อ (ภาษาอังกฤษ ไม่เว้นวรรค)").grid(row=0, column=2, sticky="e")
        self.name_var = tk.StringVar()
        tk.Entry(form, textvariable=self.name_var, width=18).grid(row=0, column=3, padx=6)

        self.video = tk.Label(root)
        self.video.pack()

        self.status = tk.StringVar(value="กรอกรหัสและชื่อ แล้วกด 'ถ่ายรูป'")
        tk.Label(root, textvariable=self.status).pack(pady=4)

        buttons = tk.Frame(root)
        buttons.pack(pady=8)
        tk.Button(buttons, text="ถ่ายรูป", width=14, command=self.capture).pack(side="left", padx=6)
        tk.Button(buttons, text="เสร็จสิ้น", width=14, command=self.finish).pack(side="left", padx=6)

        root.geometry("700x700")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.update_frame()

    def update_frame(self):
        ok, frame = self.cam.read()
        if ok:
            self.frame = frame
            preview = cv2.resize(cv2.flip(frame, 1), (640, 480))
            rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
            img = ImageTk.PhotoImage(Image.fromarray(rgb))
            self.video.configure(image=img)
            self.video.image = img
        self.root.after(30, self.update_frame)

    def _current_person(self):
        sid, name = self.id_var.get().strip(), self.name_var.get().strip()
        if not sid or not name:
            messagebox.showwarning("ข้อมูลไม่ครบ", "กรุณากรอกรหัสและชื่อก่อน")
            return None
        if " " in name or "/" in name or "_" in sid:
            messagebox.showwarning("รูปแบบไม่ถูกต้อง", "ชื่อห้ามเว้นวรรค และรหัสห้ามมีเครื่องหมาย _")
            return None
        return sid, name

    def capture(self):
        person = self._current_person()
        if person is None or self.frame is None:
            return
        sid, name = person
        rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
        faces = face_recognition.face_locations(small)
        if len(faces) != 1:
            self.status.set(f"พบใบหน้า {len(faces)} หน้า ต้องมีหน้าเดียวในภาพ ลองใหม่")
            return
        folder = KNOWN_DIR / f"{sid}_{name}"
        folder.mkdir(parents=True, exist_ok=True)
        if folder != self.folder:
            self.folder = folder
            self.count = len(list(folder.glob("*.jpg")))
        self.count += 1
        cv2.imwrite(str(folder / f"{self.count}.jpg"), self.frame)
        self.status.set(f"บันทึกแล้ว {self.count} รูป (แนะนำอย่างน้อย 5 รูป เปลี่ยนมุมและแสง)")

    def finish(self):
        person = self._current_person()
        if person is None:
            return
        if self.count == 0:
            messagebox.showinfo("ยังไม่มีรูป", "ยังไม่ได้ถ่ายรูปเลย")
            return
        sid, name = person
        conn = db.connect()
        db.upsert_student(conn, sid, name)
        conn.close()
        messagebox.showinfo("สำเร็จ", f"ลงทะเบียน {sid}_{name} แล้ว ({self.count} รูป)")
        self.id_var.set("")
        self.name_var.set("")
        self.count = 0
        self.folder = None
        self.status.set("ลงทะเบียนคนถัดไปได้เลย")

    def close(self):
        self.cam.release()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    RegisterApp(root)
    root.mainloop()
