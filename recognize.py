"""จดจำใบหน้าผ่านกล้อง แล้วบันทึกลงฐานข้อมูล SQLite (data/facecheck.db)
เช็คชื่อได้วันละครั้งต่อคน กด q เพื่อออก"""
from pathlib import Path

import cv2
import face_recognition
import numpy as np

import db

KNOWN_DIR = Path("known_faces")
THRESHOLD = 0.5  # ยิ่งน้อยยิ่งเข้มงวด


def load_known(conn):
    """โหลดใบหน้าจาก known_faces และลงทะเบียนนักศึกษาเข้าตาราง students"""
    encodings, ids = [], []
    for folder in KNOWN_DIR.iterdir():
        if not folder.is_dir():
            continue
        student_id, _, name = folder.name.partition("_")
        db.upsert_student(conn, student_id, name or student_id)
        for img_path in folder.glob("*.jpg"):
            img = face_recognition.load_image_file(str(img_path))
            found = face_recognition.face_encodings(img)
            if found:
                encodings.append(found[0])
                ids.append(folder.name)
    return encodings, ids


conn = db.connect()
imported = db.import_old_csv(conn)
if imported:
    print(f"นำเข้าข้อมูลเก่าจาก CSV {imported} รายการ")

known_enc, known_lbl = load_known(conn)
print(f"โหลดใบหน้า {len(known_enc)} รูป")

cam = cv2.VideoCapture(0)
while True:
    ok, frame = cam.read()
    if not ok:
        break
    small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
    locs = face_recognition.face_locations(rgb)
    encs = face_recognition.face_encodings(rgb, locs)

    for (top, right, bottom, left), enc in zip(locs, encs):
        label = "Unknown"
        if known_enc:
            dist = face_recognition.face_distance(known_enc, enc)
            best = int(np.argmin(dist))
            if dist[best] < THRESHOLD:
                label = known_lbl[best]
                if db.log_attendance(conn, label.split("_", 1)[0]):
                    print(f"บันทึกเช็คชื่อ: {label}")
        top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(frame, label, (left, top - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("FaceCheck", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cam.release()
cv2.destroyAllWindows()
conn.close()
