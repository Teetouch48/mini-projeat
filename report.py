"""รายงานสรุปการเข้าเรียน (มา/สาย/ขาด) และส่งออกเป็น Excel (แบบคำสั่ง)

ตัวอย่าง:
  python report.py                              # วันนี้ เริ่มเรียน 09:00 สายหลัง 15 นาที
  python report.py --date 2026-10-21            # เลือกวัน
  python report.py --start 13:00 --grace 10     # เปลี่ยนเวลาเริ่มเรียน/เวลาผ่อนผัน
ไฟล์จะถูกบันทึกที่ reports/attendance_<วันที่>.xlsx
"""
import argparse
from datetime import datetime

import db
import report_core

parser = argparse.ArgumentParser()
parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
parser.add_argument("--start", default="09:00", help="เวลาเริ่มเรียน HH:MM")
parser.add_argument("--grace", type=int, default=15, help="นาทีที่ผ่อนผันก่อนนับว่าสาย")
args = parser.parse_args()

conn = db.connect()
df, summary, limit = report_core.build_report(conn, args.date, args.start, args.grace)
conn.close()

if df.empty:
    raise SystemExit("ยังไม่มีนักศึกษาในระบบ ลงทะเบียนก่อน (python app.py)")

print(f"\nรายงานวันที่ {args.date} (เริ่มเรียน {args.start}, สายหลัง {limit.strftime('%H:%M')})\n")
print(df.to_string(index=False))
print("\nสรุป:", ", ".join(f"{r['สถานะ']} {r['จำนวน']}" for _, r in summary.iterrows()))
print(f"\nบันทึก Excel แล้ว: {report_core.export_excel(df, summary, args.date)}")
