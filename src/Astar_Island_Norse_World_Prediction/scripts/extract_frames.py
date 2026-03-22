import cv2
import os

video_path = "/Users/herstad/Downloads/tui.mp4"
output_dir = "data/temp_frames"
os.makedirs(output_dir, exist_ok=True)

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
if fps <= 0: fps = 30

print(f"FPS: {fps}")
count = 0
frame_idx = 0
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break
    
    # Save one frame every second
    if count % int(fps) == 0:
        out_path = f"{output_dir}/frame_{frame_idx:03d}.jpg"
        cv2.imwrite(out_path, frame)
        frame_idx += 1
        if frame_idx >= 60: # Limit to first minute to avoid too much data
            break
    count += 1

cap.release()
print(f"Extracted {frame_idx} frames to {output_dir}")
