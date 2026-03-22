import os
import shutil
from pathlib import Path

def main():
    base_dir = Path(r"src\NorgesGruppen_Data_Object_Detection")
    unknown_dir = base_dir / "datasets" / "cropped_objects_ground_truth_revised" / "unknown"
    dest_base_dir = base_dir / "datasets" / "cropped_objects_ground_truth_revised"
    
    if not unknown_dir.exists():
        print(f"Directory not found: {unknown_dir}")
        return

    images = [p for p in unknown_dir.iterdir() if p.is_file() and p.suffix.lower() in ['.jpg', '.jpeg', '.png']]
    print(f"Found {len(images)} images to process in the unknown folder.")

    moved_count = 0
    errors_count = 0

    for img_path in images:
        # Example filename: MÜSLI_HASSELNØTT_600G_AXA_main.jpg
        # We need to extract the category name, which is everything before the LAST underscore.
        parts = img_path.stem.split('_')
        
        # Safety check: if there are no underscores, skip
        if len(parts) < 2:
            print(f"Warning: Cannot parse category from {img_path.name}")
            errors_count += 1
            continue
            
        # The image type (main, front, back, left, right, top, bottom) is the last part
        # Everything before the last part is the category name
        category_name = "_".join(parts[:-1])
        
        dest_cat_dir = dest_base_dir / category_name
        dest_cat_dir.mkdir(parents=True, exist_ok=True)
        
        dest_path = dest_cat_dir / img_path.name
        
        try:
            shutil.move(img_path, dest_path)
            moved_count += 1
        except Exception as e:
            print(f"Failed to move {img_path.name}: {e}")
            errors_count += 1

    print("\n--- Summary ---")
    print(f"Successfully moved {moved_count} images to their category folders.")
    if errors_count > 0:
        print(f"Failed to process/move {errors_count} images.")

if __name__ == '__main__':
    main()