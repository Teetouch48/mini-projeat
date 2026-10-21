"""ทดสอบส่วนฐานข้อมูลและรายงาน (ไม่ต้องใช้กล้อง): python test_core.py"""
import os
import tempfile
import unittest
from pathlib import Path

import db
import report_core


class CoreTests(unittest.TestCase):
    def setUp(self):
        self._old = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        self.conn = db.connect()
        db.upsert_student(self.conn, "001", "Aom")
        db.upsert_student(self.conn, "002", "Beam")
        db.upsert_student(self.conn, "003", "Chai")

    def tearDown(self):
        self.conn.close()
        os.chdir(self._old)
        self._tmp.cleanup()

    def _put(self, sid, date, time):
        self.conn.execute(
            "INSERT INTO attendance (student_id, date, time) VALUES (?, ?, ?)",
            (sid, date, time))
        self.conn.commit()

    def test_no_duplicate_checkin_same_day(self):
        self.assertTrue(db.log_attendance(self.conn, "001"))
        self.assertFalse(db.log_attendance(self.conn, "001"))
        n = self.conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
        self.assertEqual(n, 1)

    def test_upsert_updates_name(self):
        db.upsert_student(self.conn, "001", "AomNew")
        name = self.conn.execute(
            "SELECT name FROM students WHERE student_id='001'").fetchone()[0]
        self.assertEqual(name, "AomNew")

    def test_status_present_late_absent(self):
        self._put("001", "2026-10-21", "09:10:00")   # มา
        self._put("002", "2026-10-21", "09:30:00")   # สาย
        df, summary, _ = report_core.build_report(self.conn, "2026-10-21", "09:00", 15)
        status = dict(zip(df["รหัส"], df["สถานะ"]))
        self.assertEqual(status, {"001": "มา", "002": "สาย", "003": "ขาด"})
        counts = dict(zip(summary["สถานะ"], summary["จำนวน"]))
        self.assertEqual(counts, {"มา": 1, "สาย": 1, "ขาด": 1})

    def test_exactly_on_limit_is_present(self):
        self._put("001", "2026-10-21", "09:15:00")
        df, _, _ = report_core.build_report(self.conn, "2026-10-21", "09:00", 15)
        self.assertEqual(df.loc[df["รหัส"] == "001", "สถานะ"].iloc[0], "มา")

    def test_other_day_not_counted(self):
        self._put("001", "2026-10-20", "09:00:00")
        df, _, _ = report_core.build_report(self.conn, "2026-10-21", "09:00", 15)
        self.assertTrue((df["สถานะ"] == "ขาด").all())

    def test_bad_input_raises_value_error(self):
        for args in [("21-10-2026", "09:00", 15), ("2026-10-21", "9am", 15),
                     ("2026-10-21", "09:00", "abc")]:
            with self.assertRaises(ValueError):
                report_core.build_report(self.conn, *args)

    def test_export_excel(self):
        self._put("001", "2026-10-21", "09:00:00")
        df, summary, _ = report_core.build_report(self.conn, "2026-10-21")
        out = report_core.export_excel(df, summary, "2026-10-21")
        self.assertTrue(Path(out).exists())

    def test_import_old_csv(self):
        Path("data").mkdir(exist_ok=True)
        Path("data/attendance.csv").write_text(
            "004_Dao,2026-10-21,08:55:00\n", encoding="utf-8")
        self.assertEqual(db.import_old_csv(self.conn), 1)
        self.assertTrue(Path("data/attendance.csv.imported").exists())
        name = self.conn.execute(
            "SELECT name FROM students WHERE student_id='004'").fetchone()[0]
        self.assertEqual(name, "Dao")


if __name__ == "__main__":
    unittest.main(verbosity=2)
