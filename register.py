"""ลงทะเบียนใบหน้า: python register.py 6401001 Somchai
กด SPACE เพื่อถ่ายรูป (แนะนำ 5 รูป หลายมุม/แสง), กด q เพื่อออก"""
import sys
import cv2
from pathlib import Path

if len(sys.argv) < 3:
    sys.exit("วิธีใช้: python register.py <รหัส> <ชื่อ>")

student_id, name = sys.argv[1], sys.argv[2]
folder = Path("known_faces") / f"{student_id}_{name}"
folder.mkdir(parents=True, exist_ok=True)

cam = cv2.VideoCapture(0)
count = len(list(folder.glob("*.jpg")))

while True:
    ok, frame = cam.read()
    if not ok:
        sys.exit("เปิดกล้องไม่ได้ ตรวจสิทธิ์กล้องใน System Settings")
    cv2.putText(frame, f"{name}: {count} photos | SPACE=capture q=quit",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.imshow("Register", frame)
    key = cv2.waitKey(1) & 0xFF
    if key == 32:
        count += 1
        cv2.imwrite(str(folder / f"{count}.jpg"), frame)
    elif key == ord("q"):
        break

cam.release()
cv2.destroyAllWindows()
