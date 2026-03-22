import os
import random
import shutil
from pathlib import Path
from PIL import Image

def main():
    # Set seed for reproducibility
    random.seed(42)

    base_dir = Path(r"src\NorgesGruppen_Data_Object_Detection")
    
    # We use the 'revised' folder as the source
    src_dir = base_dir / "datasets" / "cropped_objects_ground_truth_revised"
    
    # This is the new folder where the capped and augmented dataset will be saved
    dest_dir = base_dir / "datasets" / "cropped_objects_ground_truth_capped"

    if not src_dir.exists():
        print(f"Source directory not found: {src_dir}")
        return

    print(f"Preparing destination directory: {dest_dir}")
    if dest_dir.exists():
        print("Cleaning up existing capped directory...")
        shutil.rmtree(dest_dir, ignore_errors=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    categories = [d for d in src_dir.iterdir() if d.is_dir()]
    print(f"Found {len(categories)} categories to process.")

    total_copied = 0
    total_augmented = 0
    capped_count = 0
    augmented_count = 0

    for cat_dir in categories:
        cat_name = cat_dir.name
        dest_cat_dir = dest_dir / cat_name
        dest_cat_dir.mkdir(parents=True, exist_ok=True)

        images = [p for p in cat_dir.iterdir() if p.is_file() and p.suffix.lower() in ['.jpg', '.jpeg', '.png']]
        count = len(images)

        if count == 0:
            continue

        if count > 100:
            # CAP: Randomly select 100 images
            selected_images = random.sample(images, 100)
            for img_path in selected_images:
                shutil.copy2(img_path, dest_cat_dir / img_path.name)
            total_copied += 100
            capped_count += 1
            
        elif count < 10:
            # AUGMENT: Tilt +45 and -45 degrees
            augmented_count += 1
            for img_path in images:
                # Copy original
                shutil.copy2(img_path, dest_cat_dir / img_path.name)
                total_copied += 1
                
                try:
                    with Image.open(img_path) as img:
                        # Convert to RGB in case of RGBA/P formats to safely save as JPEG
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                            
                        # Rotate 45 degrees left (counter-clockwise)
                        img_45 = img.rotate(45, expand=True, fillcolor=(0, 0, 0))
                        img_45.save(dest_cat_dir / f"rot45_{img_path.name}")
                        total_augmented += 1
                        
                        # Rotate 45 degrees right (clockwise)
                        img_m45 = img.rotate(-45, expand=True, fillcolor=(0, 0, 0))
                        img_m45.save(dest_cat_dir / f"rotm45_{img_path.name}")
                        total_augmented += 1
                except Exception as e:
                    print(f"Error augmenting {img_path.name}: {e}")
                    
        else:
            # NORMAL: Between 10 and 100 images, just copy them all
            for img_path in images:
                shutil.copy2(img_path, dest_cat_dir / img_path.name)
            total_copied += count

    print("\n--- Summary ---")
    print(f"Categories capped (had > 100 images): {capped_count}")
    print(f"Categories augmented (had < 10 images): {augmented_count}")
    print(f"Total original images copied: {total_copied}")
    print(f"Total augmented images created: {total_augmented}")
    print(f"Total images in new dataset: {total_copied + total_augmented}")
    print(f"New dataset successfully saved to: {dest_dir}")

if __name__ == '__main__':
    main()