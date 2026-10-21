"""FaceCheck - เช็คชื่อ / ลงทะเบียนใบหน้า / รายงาน ในโปรแกรมเดียว
รัน: python app.py  หรือดับเบิลคลิก FaceCheck.command"""
import os
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import face_recognition
import numpy as np
from PIL import Image, ImageTk

os.chdir(Path(__file__).resolve().parent)  # ให้ดับเบิลคลิกจากที่ไหนก็หาโฟลเดอร์ข้อมูลเจอ

import db  # noqa: E402
import report_core  # noqa: E402

KNOWN_DIR = Path("known_faces")
THRESHOLD = 0.5       # ยิ่งน้อยยิ่งเข้มงวด
VIDEO_SIZE = (600, 450)
PROCESS_EVERY = 6     # จดจำใบหน้าทุก N เฟรม เพื่อไม่ให้ภาพกระตุก
REG_TARGET = 5        # จำนวนรูปที่แนะนำต่อคน

# สี
BG = "#f4f6f8"
SIDE = "#12202e"
SIDE_ACTIVE = "#1b3044"
ACCENT = "#1fb5a0"
ACCENT_DARK = "#12806f"
TEXT = "#1b2733"
MUTED = "#6a7179"
CARD = "#ffffff"
LINE = "#e1e5e8"
BANNERS = {
    "ready": ("#e9edf0", TEXT),
    "ok": ("#d9f4ee", "#12806f"),
    "seen": ("#e3eefb", "#1f5a99"),
    "unknown": ("#fdeaea", "#b03a2e"),
}

_family = None


def font(size=14, bold=False):
    global _family
    if _family is None:
        _family = tkfont.nametofont("TkDefaultFont").actual("family")
    return (_family, size, "bold" if bold else "normal")


class Btn(tk.Label):
    """ปุ่มแบบกำหนดสีเองได้ (tk.Button บน macOS ไม่ยอมเปลี่ยนสี)"""

    def __init__(self, parent, text, command, bg=ACCENT, hover=ACCENT_DARK,
                 fg="#ffffff", size=15, padx=22, pady=11):
        super().__init__(parent, text=text, bg=bg, fg=fg, font=font(size, True),
                         padx=padx, pady=pady, cursor="hand2")
        self.bind("<Enter>", lambda e: self.configure(bg=hover))
        self.bind("<Leave>", lambda e: self.configure(bg=bg))
        self.bind("<Button-1>", lambda e: command())


def card(parent, pad=16):
    return tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1,
                    padx=pad, pady=pad)


def entry(parent, var):
    return tk.Entry(parent, textvariable=var, font=font(16), relief="flat", bg=BG, fg=TEXT,
                    insertbackground=TEXT, highlightthickness=1, highlightbackground="#d5dbe0",
                    highlightcolor=ACCENT)


class App:
    def __init__(self, root):
        self.root = root
        root.title("FaceCheck")
        root.geometry("1280x780")
        root.minsize(1180, 720)
        root.configure(bg=BG)

        KNOWN_DIR.mkdir(exist_ok=True)
        self.conn = db.connect()
        db.import_old_csv(self.conn)
        self.cam = None
        self.frame = None
        self.frame_count = 0
        self.last_results = []
        self.reg_count = 0
        self.reg_folder = None
        self.report_df = None
        self.report_summary = None
        self.known_enc, self.known_lbl = [], []
        self.current = "home"
        self.banner_job = None

        self.setup_style()
        self.build_layout()
        self.show("home")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(300, self.reload_known)
        self.update_frame()

    # ---------- โครงหน้าจอ ----------
    def setup_style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Face.Treeview", font=font(14), rowheight=38, background=CARD,
                    fieldbackground=CARD, foreground=TEXT, borderwidth=0)
        s.configure("Face.Treeview.Heading", font=font(14, True), background="#e9edf0",
                    foreground=TEXT, relief="flat", padding=8)
        s.map("Face.Treeview", background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])
        s.configure("Face.Horizontal.TProgressbar", troughcolor=LINE, background=ACCENT,
                    thickness=14, borderwidth=0)

    def build_layout(self):
        side = tk.Frame(self.root, bg=SIDE, width=230)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="FaceCheck", bg=SIDE, fg="#ffffff",
                 font=font(26, True)).pack(anchor="w", padx=24, pady=(34, 2))
        tk.Label(side, text="ระบบเช็คชื่อด้วยใบหน้า", bg=SIDE, fg="#8aa0b0",
                 font=font(12)).pack(anchor="w", padx=24, pady=(0, 28))

        self.nav = {}
        for key, text in [("home", "🏠   หน้าหลัก"), ("check", "📷   เช็คชื่อ"),
                          ("register", "➕   ลงทะเบียน"), ("report", "📊   รายงาน")]:
            lbl = tk.Label(side, text=text, bg=SIDE, fg="#d5dee5", font=font(16),
                           anchor="w", padx=24, pady=14, cursor="hand2")
            lbl.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, k=key: self.show(k))
            self.nav[key] = lbl
        self.side_status = tk.Label(side, text="", bg=SIDE, fg="#8aa0b0", font=font(12),
                                    wraplength=190, justify="left")
        self.side_status.pack(side="bottom", anchor="w", padx=24, pady=24)

        content = tk.Frame(self.root, bg=BG)
        content.pack(side="left", fill="both", expand=True)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self.pages = {}
        for key in ("home", "check", "register", "report"):
            f = tk.Frame(content, bg=BG, padx=36, pady=28)
            f.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = f
        self.build_home()
        self.build_check()
        self.build_register()
        self.build_report()

    def page_title(self, parent, title, subtitle):
        tk.Label(parent, text=title, bg=BG, fg=TEXT, font=font(28, True)).pack(anchor="w")
        tk.Label(parent, text=subtitle, bg=BG, fg=MUTED, font=font(14)).pack(anchor="w", pady=(2, 0))

    def video_holder(self, parent):
        box = card(parent, pad=10)
        holder = tk.Frame(box, width=VIDEO_SIZE[0], height=VIDEO_SIZE[1], bg="#0e1822")
        holder.pack()
        holder.pack_propagate(False)
        lbl = tk.Label(holder, text="กำลังเปิดกล้อง...", bg="#0e1822", fg="#8aa0b0", font=font(16))
        lbl.pack(fill="both", expand=True)
        return box, lbl

    def show(self, name):
        self.current = name
        self.pages[name].tkraise()
        for k, lbl in self.nav.items():
            on = k == name
            lbl.configure(bg=SIDE_ACTIVE if on else SIDE, fg=ACCENT if on else "#d5dee5")
        if name in ("check", "register"):
            self.start_camera()
        else:
            self.stop_camera()
        if name == "home":
            self.refresh_home()
        elif name == "check":
            self.refresh_today()
        elif name == "report":
            self.show_report(quiet=True)

    # ---------- หน้าหลัก ----------
    def build_home(self):
        p = self.pages["home"]
        tk.Label(p, text="ยินดีต้อนรับสู่ FaceCheck", bg=BG, fg=TEXT,
                 font=font(30, True)).pack(anchor="w")
        self.home_date = tk.Label(p, text="", bg=BG, fg=MUTED, font=font(15))
        self.home_date.pack(anchor="w", pady=(4, 24))

        stats = tk.Frame(p, bg=BG)
        stats.pack(fill="x")
        self.stat_students = tk.StringVar(value="-")
        self.stat_today = tk.StringVar(value="-")
        for title, var, color in [("นักศึกษาที่ลงทะเบียนแล้ว", self.stat_students, ACCENT_DARK),
                                  ("เช็คชื่อแล้ววันนี้", self.stat_today, "#1f5a99")]:
            c = card(stats, pad=20)
            c.pack(side="left", padx=(0, 20))
            tk.Label(c, textvariable=var, bg=CARD, fg=color, font=font(40, True)).pack(anchor="w")
            tk.Label(c, text=title, bg=CARD, fg=MUTED, font=font(14)).pack(anchor="w")

        tk.Label(p, text="เริ่มต้นใช้งาน", bg=BG, fg=TEXT, font=font(20, True)).pack(
            anchor="w", pady=(34, 12))
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x")
        for icon, title, desc, btn, target in [
            ("📷", "เช็คชื่อ", "ให้นักศึกษายืนหน้ากล้อง ระบบจดจำและบันทึกเวลาให้เอง", "เริ่มเช็คชื่อ", "check"),
            ("➕", "ลงทะเบียนใบหน้า", "เพิ่มนักศึกษาใหม่ ถ่ายรูปประมาณ 5 รูป", "ลงทะเบียน", "register"),
            ("📊", "ดูรายงาน", "สรุป มา / สาย / ขาด และส่งออกเป็น Excel", "เปิดรายงาน", "report"),
        ]:
            c = card(row, pad=22)
            c.pack(side="left", fill="both", expand=True, padx=(0, 20))
            tk.Label(c, text=icon, bg=CARD, font=font(40)).pack(anchor="w")
            tk.Label(c, text=title, bg=CARD, fg=TEXT, font=font(20, True)).pack(anchor="w", pady=(6, 4))
            tk.Label(c, text=desc, bg=CARD, fg=MUTED, font=font(14), wraplength=260,
                     justify="left").pack(anchor="w", pady=(0, 18))
            Btn(c, btn, lambda t=target: self.show(t)).pack(anchor="w")

    def refresh_home(self):
        today = datetime.now().strftime("%Y-%m-%d")
        n_students = self.conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        n_today = self.conn.execute(
            "SELECT COUNT(*) FROM attendance WHERE date = ?", (today,)).fetchone()[0]
        self.stat_students.set(str(n_students))
        self.stat_today.set(str(n_today))
        self.home_date.configure(text=datetime.now().strftime("วันที่ %d/%m/%Y"))

    # ---------- หน้าเช็คชื่อ ----------
    def build_check(self):
        p = self.pages["check"]
        self.page_title(p, "เช็คชื่อ", "หันหน้าเข้ากล้อง ระบบจะบันทึกให้อัตโนมัติ (วันละครั้งต่อคน)")
        body = tk.Frame(p, bg=BG)
        body.pack(fill="both", expand=True, pady=(16, 0))
        box, self.check_video = self.video_holder(body)
        box.pack(side="left", anchor="n", padx=(0, 20))

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.banner = tk.Label(right, text="พร้อมเช็คชื่อ", bg=BANNERS["ready"][0],
                               fg=BANNERS["ready"][1], font=font(18, True), wraplength=300,
                               pady=26)
        self.banner.pack(fill="x")
        tk.Label(right, text="เช็คชื่อแล้ววันนี้", bg=BG, fg=TEXT, font=font(16, True)).pack(
            anchor="w", pady=(18, 8))
        lst = card(right, pad=8)
        lst.pack(fill="both", expand=True)
        self.today_list = tk.Listbox(lst, font=font(15), bd=0, highlightthickness=0,
                                     activestyle="none", bg=CARD, fg=TEXT,
                                     selectbackground=CARD, selectforeground=TEXT)
        self.today_list.pack(fill="both", expand=True)

    def set_banner(self, kind, text):
        bg, fg = BANNERS[kind]
        self.banner.configure(text=text, bg=bg, fg=fg)
        if self.banner_job:
            self.root.after_cancel(self.banner_job)
            self.banner_job = None
        if kind != "ready":
            self.banner_job = self.root.after(2500, lambda: self.set_banner("ready", "พร้อมเช็คชื่อ"))

    def refresh_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self.conn.execute(
            "SELECT a.time, s.name FROM attendance a JOIN students s USING (student_id) "
            "WHERE a.date = ? ORDER BY a.time DESC", (today,)).fetchall()
        self.today_list.delete(0, "end")
        for t, name in rows:
            self.today_list.insert("end", f"  {t[:5]}   {name}")

    def process_checkin(self, frame):
        if self.frame_count % PROCESS_EVERY == 0:
            small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            locs = face_recognition.face_locations(rgb)
            encs = face_recognition.face_encodings(rgb, locs)
            results, new_msg, seen_msg, unknown = [], None, None, False
            for loc, enc in zip(locs, encs):
                label = "Unknown"
                if self.known_enc:
                    dist = face_recognition.face_distance(self.known_enc, enc)
                    best = int(np.argmin(dist))
                    if dist[best] < THRESHOLD:
                        label = self.known_lbl[best]
                        sid, _, name = label.partition("_")
                        if db.log_attendance(self.conn, sid):
                            now = datetime.now().strftime("%H:%M")
                            new_msg = f"✓ {name}\nเช็คชื่อแล้ว {now}"
                            self.refresh_today()
                        else:
                            seen_msg = f"{name}\nเช็คชื่อไปแล้ววันนี้"
                if label == "Unknown":
                    unknown = True
                results.append((loc, label))
            self.last_results = results
            if new_msg:
                self.set_banner("ok", new_msg)
            elif seen_msg:
                self.set_banner("seen", seen_msg)
            elif unknown:
                self.set_banner("unknown", "ไม่รู้จักใบหน้านี้")

        display = frame.copy()
        for (top, right, bottom, left), label in self.last_results:
            top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
            cv2.rectangle(display, (left, top), (right, bottom), (31, 181, 160), 3)
            cv2.putText(display, label, (left, max(top - 10, 24)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (31, 181, 160), 2)
        self.show_frame(display, self.check_video)

    # ---------- หน้าลงทะเบียน ----------
    def build_register(self):
        p = self.pages["register"]
        self.page_title(p, "ลงทะเบียนใบหน้า", "กรอกรหัสและชื่อ แล้วถ่ายรูปประมาณ 5 รูป")
        body = tk.Frame(p, bg=BG)
        body.pack(fill="both", expand=True, pady=(16, 0))
        box, self.reg_video = self.video_holder(body)
        box.pack(side="left", anchor="n", padx=(0, 20))

        form = card(body, pad=22)
        form.pack(side="left", fill="both", expand=True, anchor="n")
        self.id_var, self.name_var = tk.StringVar(), tk.StringVar()
        tk.Label(form, text="รหัสนักศึกษา", bg=CARD, fg=MUTED, font=font(13)).pack(anchor="w")
        entry(form, self.id_var).pack(fill="x", ipady=6, pady=(2, 12))
        tk.Label(form, text="ชื่อ (ภาษาอังกฤษ ไม่เว้นวรรค)", bg=CARD, fg=MUTED,
                 font=font(13)).pack(anchor="w")
        entry(form, self.name_var).pack(fill="x", ipady=6, pady=(2, 18))

        self.reg_progress_text = tk.Label(form, text=f"ถ่ายแล้ว 0 / {REG_TARGET} รูป", bg=CARD,
                                          fg=TEXT, font=font(15, True))
        self.reg_progress_text.pack(anchor="w")
        self.reg_bar = ttk.Progressbar(form, maximum=REG_TARGET, style="Face.Horizontal.TProgressbar")
        self.reg_bar.pack(fill="x", pady=(6, 10))
        self.reg_status = tk.Label(form, text="พร้อมถ่ายรูป", bg=CARD, fg=MUTED, font=font(13),
                                   wraplength=280, justify="left")
        self.reg_status.pack(anchor="w", pady=(0, 14))

        Btn(form, "📸  ถ่ายรูป", self.capture).pack(fill="x", pady=(0, 10))
        Btn(form, "✓  เสร็จสิ้น", self.finish_register, bg=ACCENT_DARK, hover="#0d6153").pack(fill="x")
        tk.Label(form, text="เคล็ดลับ: หันหน้าตรง ให้เห็นชัด มีหน้าเดียวในภาพ\nและเปลี่ยนมุมเล็กน้อยในแต่ละรูป",
                 bg=CARD, fg=MUTED, font=font(12), justify="left").pack(anchor="w", pady=(16, 0))

    def _person(self):
        sid, name = self.id_var.get().strip(), self.name_var.get().strip()
        if not sid or not name:
            messagebox.showwarning("ข้อมูลไม่ครบ", "กรุณากรอกรหัสและชื่อก่อน")
            return None
        if " " in name or "/" in name or "_" in sid or "/" in sid:
            messagebox.showwarning("รูปแบบไม่ถูกต้อง", "ชื่อห้ามเว้นวรรค และรหัสห้ามมีเครื่องหมาย _ หรือ /")
            return None
        return sid, name

    def _update_progress(self):
        self.reg_progress_text.configure(text=f"ถ่ายแล้ว {self.reg_count} / {REG_TARGET} รูป")
        self.reg_bar["value"] = min(self.reg_count, REG_TARGET)

    def capture(self):
        person = self._person()
        if person is None or self.frame is None:
            return
        sid, name = person
        rgb = cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB)
        small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
        faces = face_recognition.face_locations(small)
        if len(faces) != 1:
            self.reg_status.configure(text=f"พบใบหน้า {len(faces)} หน้า ต้องมีหน้าเดียวในภาพ ลองใหม่", fg="#b03a2e")
            return
        folder = KNOWN_DIR / f"{sid}_{name}"
        folder.mkdir(parents=True, exist_ok=True)
        if folder != self.reg_folder:
            self.reg_folder = folder
            self.reg_count = len(list(folder.glob("*.jpg")))
        self.reg_count += 1
        cv2.imwrite(str(folder / f"{self.reg_count}.jpg"), self.frame)
        self._update_progress()
        self.reg_status.configure(text="บันทึกรูปแล้ว เปลี่ยนมุมหน้าเล็กน้อยแล้วถ่ายต่อ", fg=ACCENT_DARK)

    def finish_register(self):
        person = self._person()
        if person is None:
            return
        if self.reg_count == 0:
            messagebox.showinfo("ยังไม่มีรูป", "ยังไม่ได้ถ่ายรูปเลย")
            return
        sid, name = person
        db.upsert_student(self.conn, sid, name)
        done = self.reg_count
        self.id_var.set("")
        self.name_var.set("")
        self.reg_count = 0
        self.reg_folder = None
        self._update_progress()
        self.reg_status.configure(text="กำลังโหลดใบหน้าใหม่เข้าระบบ...", fg=MUTED)
        self.root.update_idletasks()
        self.reload_known()
        self.reg_status.configure(text="ลงทะเบียนคนถัดไปได้เลย", fg=MUTED)
        messagebox.showinfo("สำเร็จ", f"ลงทะเบียน {sid}_{name} แล้ว ({done} รูป)")

    # ---------- หน้ารายงาน ----------
    def build_report(self):
        p = self.pages["report"]
        self.page_title(p, "รายงานการเข้าเรียน", "เลือกวันและเกณฑ์เวลา แล้วดูสรุปหรือส่งออก Excel")
        bar = card(p, pad=14)
        bar.pack(fill="x", pady=(16, 14))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        self.start_var = tk.StringVar(value="09:00")
        self.grace_var = tk.StringVar(value="15")
        for text, var, w in [("วันที่ (YYYY-MM-DD)", self.date_var, 12),
                             ("เริ่มเรียน (HH:MM)", self.start_var, 7),
                             ("สายหลัง (นาที)", self.grace_var, 5)]:
            col = tk.Frame(bar, bg=CARD)
            col.pack(side="left", padx=(0, 16))
            tk.Label(col, text=text, bg=CARD, fg=MUTED, font=font(12)).pack(anchor="w")
            e = entry(col, var)
            e.configure(width=w)
            e.pack(ipady=4)
        Btn(bar, "แสดงรายงาน", self.show_report).pack(side="left", padx=(8, 10), pady=(18, 0))
        Btn(bar, "ส่งออก Excel", self.export, bg="#1f5a99", hover="#184a80").pack(side="left", pady=(18, 0))

        stats = tk.Frame(p, bg=BG)
        stats.pack(fill="x", pady=(0, 14))
        self.sum_vars = {k: tk.StringVar(value="0") for k in ("มา", "สาย", "ขาด")}
        for key, color in [("มา", ACCENT_DARK), ("สาย", "#c4891a"), ("ขาด", "#b03a2e")]:
            c = card(stats, pad=14)
            c.pack(side="left", padx=(0, 14))
            tk.Label(c, textvariable=self.sum_vars[key], bg=CARD, fg=color, font=font(30, True),
                     width=4).pack(side="left")
            tk.Label(c, text=key, bg=CARD, fg=MUTED, font=font(16)).pack(side="left", padx=(0, 8))
        self.limit_label = tk.Label(stats, text="", bg=BG, fg=MUTED, font=font(13))
        self.limit_label.pack(side="left", padx=8)

        wrap = card(p, pad=0)
        wrap.pack(fill="both", expand=True)
        cols = ("รหัส", "ชื่อ", "เวลาเช็คชื่อ", "สถานะ")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", style="Face.Treeview")
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=160, anchor="center")
        self.tree.tag_configure("มา", background="#e6f6f1")
        self.tree.tag_configure("สาย", background="#fff3cd")
        self.tree.tag_configure("ขาด", background="#f8d7da")
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def show_report(self, quiet=False):
        try:
            df, summary, limit = report_core.build_report(
                self.conn, self.date_var.get().strip(),
                self.start_var.get().strip(), self.grace_var.get().strip())
        except ValueError:
            if not quiet:
                messagebox.showerror("รูปแบบไม่ถูกต้อง",
                                     "วันที่ใช้ YYYY-MM-DD, เวลาใช้ HH:MM และนาทีเป็นตัวเลข")
            return
        self.report_df, self.report_summary = df, summary
        self.tree.delete(*self.tree.get_children())
        for row in df.itertuples(index=False):
            self.tree.insert("", "end", values=tuple(row), tags=(row[3],))
        counts = {r["สถานะ"]: int(r["จำนวน"]) for _, r in summary.iterrows()}
        for k, var in self.sum_vars.items():
            var.set(str(counts.get(k, 0)))
        self.limit_label.configure(text=f"นับว่าสายหลัง {limit.strftime('%H:%M')}")
        if df.empty and not quiet:
            messagebox.showinfo("ยังไม่มีนักศึกษา", "ลงทะเบียนนักศึกษาก่อนที่แท็บ 'ลงทะเบียน'")

    def export(self):
        self.show_report(quiet=True)
        if self.report_df is None or self.report_df.empty:
            messagebox.showinfo("ยังไม่มีรายงาน", "ยังไม่มีข้อมูลให้ส่งออก")
            return
        out = report_core.export_excel(
            self.report_df, self.report_summary, self.date_var.get().strip())
        messagebox.showinfo("สำเร็จ", f"บันทึก Excel แล้ว:\n{out.resolve()}")

    # ---------- ใบหน้าที่ลงทะเบียนไว้ ----------
    def reload_known(self):
        self.side_status.configure(text="กำลังโหลดใบหน้า...")
        self.root.update_idletasks()
        encodings, labels = [], []
        for folder in sorted(KNOWN_DIR.iterdir()):
            if not folder.is_dir():
                continue
            sid, _, name = folder.name.partition("_")
            db.upsert_student(self.conn, sid, name or sid)
            for img_path in folder.glob("*.jpg"):
                img = face_recognition.load_image_file(str(img_path))
                found = face_recognition.face_encodings(img)
                if found:
                    encodings.append(found[0])
                    labels.append(folder.name)
        self.known_enc, self.known_lbl = encodings, labels
        self.side_status.configure(text=f"โหลดแล้ว {len(set(labels))} คน ({len(labels)} รูป)")
        if self.current == "home":
            self.refresh_home()

    # ---------- กล้อง ----------
    def start_camera(self):
        if self.cam is not None:
            return
        cam = cv2.VideoCapture(0)
        if not cam.isOpened():
            cam.release()
            messagebox.showerror(
                "เปิดกล้องไม่ได้",
                "ตรวจสิทธิ์กล้องที่ System Settings → Privacy & Security → Camera\nแล้วเปิดโปรแกรมใหม่")
            return
        self.cam = cam

    def stop_camera(self):
        if self.cam is not None:
            self.cam.release()
            self.cam = None
        self.last_results = []
        for lbl in (self.check_video, self.reg_video):
            lbl.configure(image="", text="กำลังเปิดกล้อง...")
            lbl.image = None

    def show_frame(self, frame, label, flip=False):
        if flip:
            frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(cv2.resize(frame, VIDEO_SIZE), cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        label.configure(image=img, text="")
        label.image = img

    def update_frame(self):
        if self.cam is not None:
            ok, frame = self.cam.read()
            if ok:
                self.frame = frame
                if self.current == "check":
                    self.process_checkin(frame)
                elif self.current == "register":
                    self.show_frame(frame, self.reg_video, flip=True)
        self.frame_count += 1
        self.root.after(30, self.update_frame)

    def close(self):
        self.stop_camera()
        self.conn.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
