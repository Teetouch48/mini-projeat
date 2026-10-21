"""ฐานข้อมูล SQLite ของ FaceCheck (ไฟล์ data/facecheck.db)"""
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/facecheck.db")
OLD_CSV = Path("data/attendance.csv")


def connect():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name       TEXT NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date       TEXT NOT NULL,
            time       TEXT NOT NULL,
            UNIQUE (student_id, date)
        )""")
    conn.commit()
    return conn


def upsert_student(conn, student_id, name):
    conn.execute(
        "INSERT INTO students (student_id, name) VALUES (?, ?) "
        "ON CONFLICT(student_id) DO UPDATE SET name = excluded.name",
        (student_id, name),
    )
    conn.commit()


def log_attendance(conn, student_id):
    """บันทึกการเข้าเรียน คืนค่า True ถ้าบันทึกใหม่, False ถ้าวันนี้เช็คไปแล้ว"""
    now = datetime.now()
    cur = conn.execute(
        "INSERT OR IGNORE INTO attendance (student_id, date, time) VALUES (?, ?, ?)",
        (student_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")),
    )
    conn.commit()
    return cur.rowcount == 1


def import_old_csv(conn):
    """นำเข้าข้อมูลจาก attendance.csv เดิม (ทำครั้งเดียว แล้วเปลี่ยนชื่อไฟล์เป็น .imported)"""
    if not OLD_CSV.exists():
        return 0
    n = 0
    with open(OLD_CSV, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 3:
                continue
            label, date, time = row[0], row[1], row[2]
            sid = label.split("_", 1)[0]
            name = label.split("_", 1)[1] if "_" in label else label
            upsert_student(conn, sid, name)
            cur = conn.execute(
                "INSERT OR IGNORE INTO attendance (student_id, date, time) "
                "VALUES (?, ?, ?)", (sid, date, time))
            n += cur.rowcount
    conn.commit()
    OLD_CSV.rename(OLD_CSV.with_suffix(".csv.imported"))
    return n
