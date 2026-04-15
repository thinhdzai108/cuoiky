import cv2
from ultralytics import YOLO

def test_mask_model():
    model_path = "YOLOv8m_FMD.pt"
    
    print(f"--- Đang tải model: {model_path} ---")
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"❌ Lỗi: Không tìm thấy file model tại {model_path}. Hãy kiểm tra lại đường dẫn.")
        return

    # In ra các class mà model này hỗ trợ
    print("\n✅ Danh sách các nhãn (Classes) trong model:")
    for id, name in model.names.items():
        print(f"   ID {id}: {name}")
    print("-" * 40)

    # Mở camera để test thực tế
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Không thể mở camera.")
        return

    print("🚀 Đang mở camera để test... Nhấn 'Q' để thoát.")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # Chạy dự đoán
        results = model(frame, conf=0.5, verbose=False)
        
        # Vẽ kết quả mặc định của YOLO lên frame
        annotated_frame = results[0].plot()
        
        # Hiển thị
        cv2.imshow("Test YOLOv8m_FMD Model", annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("\n--- Hoàn tất test ---")

if __name__ == "__main__":
    test_mask_model()
