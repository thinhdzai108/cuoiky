@echo off
title Cài đặt môi trường Đồ Án AI - Mask & Distance
color 0a

echo ---------------------------------------------------------
echo [1/3] Dang cap nhat Pip...
python -m pip install --upgrade pip

echo [2/3] Dang cai dat cac thu vien lien quan (OpenCV, YOLO, Requests)...
pip install -r requirements.txt

echo [3/3] Dang kiem tra model...
if exist "yolov8.pt" (
    echo Model yolov8.pt da san sang.
) else (
    echo Model yolov8.pt chua co, YOLO se tu dong tai ve khi chay main.py.
)

echo ---------------------------------------------------------
echo [HOAN TAT] Moi truong da san sang để chay do an!
echo Nhan phim bat ky de thoat.
pause
