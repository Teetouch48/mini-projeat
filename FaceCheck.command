#!/bin/bash
# ดับเบิลคลิกไฟล์นี้เพื่อเปิด FaceCheck
cd "$(dirname "$0")"
source venv/bin/activate
python app.py
