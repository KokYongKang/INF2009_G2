"""
webcam_sensor.py
Stub for webcam integration (person detection).
"""

import cv2
import os
import time

def webcam_detect(num_images=10, interval=1, width=640, height=480):
    """
    Captures and saves individual images from the webcam to data/images for YOLO object detection.
    """
    print(f"[Webcam] Capturing {num_images} images from webcam...")
    images_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'images')
    os.makedirs(images_dir, exist_ok=True)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    captured = 0
    while captured < num_images:
        ret, frame = cap.read()
        if not ret:
            print("[Webcam] Failed to grab frame.")
            break
        img_path = os.path.join(images_dir, f'webcam_image_{captured+1}.jpg')
        cv2.imwrite(img_path, frame)
        print(f"[Webcam] Saved {img_path}")
        captured += 1
        time.sleep(interval)
    cap.release()
    print(f"[Webcam] {captured} images saved to {images_dir}")
    return images_dir


if __name__ == "__main__":
    webcam_detect()