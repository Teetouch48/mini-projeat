"""ตรรกะรายงานสรุปการเข้าเรียน ใช้ร่วมกันระหว่าง report.py และ app.py"""
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


def build_report(conn, date, start="09:00", grace=15):
    """คืนค่า (df รายชื่อ+สถานะ, summary จำนวน มา/สาย/ขาด, เวลาที่เริ่มนับว่าสาย)
    ถ้ารูปแบบวันที่/เวลา/นาทีไม่ถูกต้อง จะเกิด ValueError"""
    datetime.strptime(date, "%Y-%m-%d")
    limit = (datetime.strptime(start, "%H:%M") + timedelta(minutes=int(grace))).time()

    students = pd.read_sql_query(
        "SELECT student_id, name FROM students ORDER BY student_id", conn)
    att = pd.read_sql_query(
        "SELECT student_id, time FROM attendance WHERE date = ?", conn, params=(date,))

    def status(t):
        if pd.isna(t):
            return "ขาด"
        return "มา" if datetime.strptime(t, "%H:%M:%S").time() <= limit else "สาย"

    df = students.merge(att, on="student_id", how="left")
    df["status"] = df["time"].apply(status)
    df["time"] = df["time"].fillna("-")
    df.columns = ["รหัส", "ชื่อ", "เวลาเช็คชื่อ", "สถานะ"]

    summary = df["สถานะ"].value_counts().reindex(["มา", "สาย", "ขาด"], fill_value=0)
    summary = summary.rename_axis("สถานะ").reset_index(name="จำนวน")
    return df, summary, limit


def export_excel(df, summary, date):
    Path("reports").mkdir(exist_ok=True)
    out = Path("reports") / f"attendance_{date}.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="รายชื่อ", index=False)
        summary.to_excel(writer, sheet_name="สรุป", index=False)
        for sheet in writer.sheets.values():
            for col in sheet.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                sheet.column_dimensions[col[0].column_letter].width = width + 4
    return out
