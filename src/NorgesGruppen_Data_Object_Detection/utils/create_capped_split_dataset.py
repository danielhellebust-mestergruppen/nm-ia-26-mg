import os
import shutil
import random
from pathlib import Path
from PIL import Image

def main():
    # Set seed for reproducibility so the train/val/test split is identical if rerun
    random.seed(42)

    base_dir = Path(r"src\NorgesGruppen_Data_Object_Detection")
    src_dir = base_dir / "datasets" / "cropped_objects_ground_truth_revised"
    dest_dir = base_dir / "datasets" / "classifier_dataset_capped_split"

    if not src_dir.exists():
        print(f"Source directory not found: {src_dir}")
        return

    print(f"Preparing destination directory: {dest_dir}")
    if dest_dir.exists():
        print("Cleaning up existing dataset directory...")
        shutil.rmtree(dest_dir, ignore_errors=True)
    
    # Create split directories
    train_dir = dest_dir / "train"
    val_dir = dest_dir / "val"
    test_dir = dest_dir / "test"
    
    train_dir.mkdir(parents=True, exist_ok=True)
    val_dir.mkdir(parents=True, exist_ok=True)
    test_dir.mkdir(parents=True, exist_ok=True)

    categories = [d for d in src_dir.iterdir() if d.is_dir()]
    print(f"Found {len(categories)} categories to process.")

    total_train = 0
    total_val = 0
    total_test = 0
    total_augmented = 0

    def process_and_copy(img_list, split_dir, cat_name, augment):
        nonlocal total_augmented
        
        cat_split_dir = split_dir / cat_name
        cat_split_dir.mkdir(parents=True, exist_ok=True)
        
        copied_count = 0
        for img_path in img_list:
            dest_path = cat_split_dir / img_path.name
            shutil.copy2(img_path, dest_path)
            copied_count += 1
            
            if augment:
                try:
                    with Image.open(img_path) as img:
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        
                        # Rotate +45 degrees
                        img_45 = img.rotate(45, expand=True, fillcolor=(0, 0, 0))
                        img_45.save(cat_split_dir / f"rot45_{img_path.name}", "JPEG", quality=90)
                        copied_count += 1
                        total_augmented += 1
                        
                        # Rotate -45 degrees
                        img_m45 = img.rotate(-45, expand=True, fillcolor=(0, 0, 0))
                        img_m45.save(cat_split_dir / f"rotm45_{img_path.name}", "JPEG", quality=90)
                        copied_count += 1
                        total_augmented += 1
                except Exception as e:
                    print(f"Error augmenting {img_path.name}: {e}")
                    
        return copied_count

    for cat_dir in categories:
        cat_name = cat_dir.name
        images = [p for p in cat_dir.iterdir() if p.is_file() and p.suffix.lower() in ['.jpg', '.jpeg', '.png']]
        
        count = len(images)
        if count == 0:
            continue

        # 1. CAP at 100
        if count > 100:
            images = random.sample(images, 100)
            count = 100
        else:
            random.shuffle(images)
            
        # 2. Determine if augmentation is needed
        needs_augmentation = (count < 20)

        # 3. Calculate 80% / 15% / 5% splits
        n_train = int(count * 0.80)
        n_val = int(count * 0.15)
        
        # Failsafe for tiny classes to ensure train and val get at least something
        if n_train == 0: 
            n_train = 1
        if count > 1 and n_val == 0: 
            n_val = 1
            
        n_test = count - n_train - n_val
        if n_test < 0:
            n_val += n_test
            n_test = 0

        train_imgs = images[:n_train]
        val_imgs = images[n_train:n_train+n_val]
        test_imgs = images[n_train+n_val:]

        # 4. Process and distribute
        # Note: We group the augmented images into the same split as the original image
        # This completely prevents "Data Leakage" where an original is in Train and its rotation is in Val/Test!
        total_train += process_and_copy(train_imgs, train_dir, cat_name, augment=needs_augmentation)
        total_val += process_and_copy(val_imgs, val_dir, cat_name, augment=needs_augmentation)
        total_test += process_and_copy(test_imgs, test_dir, cat_name, augment=needs_augmentation)

    print("\n--- Summary ---")
    print(f"Total Base Images Processed (after capping): {total_train + total_val + total_test - total_augmented}")
    print(f"Total Augmented Images Created: {total_augmented}")
    print(f"-----------------------------------")
    print(f"Train Set (80%): {total_train} images")
    print(f"Val Set   (15%): {total_val} images")
    print(f"Test Set  (5%):  {total_test} images")
    print(f"-----------------------------------")
    print(f"Total final dataset size: {total_train + total_val + total_test} images")
    print(f"Dataset successfully saved and split at:\n{dest_dir}")

if __name__ == '__main__':
    main()