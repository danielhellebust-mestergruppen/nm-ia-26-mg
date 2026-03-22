import os
import json
import shutil
import re
from pathlib import Path
from PIL import Image

def safe_filename(name):
    # Make product_name safe for filenames (replace spaces and invalid chars)
    return "".join(c if c.isalnum() or c in [' ', '-', '_'] else '_' for c in name).replace(' ', '_')

def resize_image(src_path, dest_path, max_size=320):
    try:
        with Image.open(src_path) as img:
            # Convert RGBA to RGB for JPEG
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Calculate resize ratio maintaining aspect ratio
            width, height = img.size
            if width > max_size or height > max_size:
                if width > height:
                    new_width = max_size
                    new_height = int(max_size * height / width)
                else:
                    new_height = max_size
                    new_width = int(max_size * width / height)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            img.save(dest_path, "JPEG", quality=90)
            return True
    except Exception as e:
        print(f"Failed to process {src_path}: {e}")
        return False

def main():
    base_dir = Path(r"src\NorgesGruppen_Data_Object_Detection")
    
    metadata_path = base_dir / "datasets" / "classification_dataset" / "product_images" / "metadata.json"
    source_images_dir = base_dir / "datasets" / "classification_dataset" / "product_images" / "images"
    
    # The user specifically requested storing under the original images directory
    dest_images_dir = base_dir / "datasets" / "classification_dataset" / "product_images" / "images"
    unknown_dir = base_dir / "datasets" / "cropped_objects_ground_truth_revised" / "unknown"
    
    cat_map_path = base_dir / "submission_v7" / "category_map.json"

    # Load category map
    with open(cat_map_path, 'r', encoding='utf-8') as f:
        category_map = json.load(f)
    
    known_categories = set(category_map.keys())

    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    products = metadata.get('products', [])
    print(f"Found {len(products)} products in metadata.")

    processed = 0
    unknown_count = 0
    unknown_names = []
    
    dest_images_dir.mkdir(parents=True, exist_ok=True)
    unknown_dir.mkdir(parents=True, exist_ok=True)
    
    # Load manual mappings if the log file was updated by the user
    manual_map = {}
    unknown_log_path = unknown_dir / "unknown_categories_log.txt"
    if unknown_log_path.exists():
        with open(unknown_log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' in line:
                    parts = line.split('=')
                    if len(parts) == 2:
                        old_cat = parts[0].strip()
                        new_cat = parts[1].strip()
                        manual_map[old_cat] = new_cat

    for p in products:
        product_code = p.get('product_code')
        product_name = p.get('product_name', 'Unnamed_Product')
        
        if not p.get('has_images'):
            continue
            
        # Replace any character that is NOT alphanumeric or Norwegian letters with an underscore
        category_candidate = re.sub(r'[^a-zA-Z0-9æøåÆØÅ]', '_', product_name)
        
        # Apply manual mapping if user provided one
        if category_candidate in manual_map:
            category_candidate = manual_map[category_candidate]
        
        if category_candidate in known_categories:
            output_folder = dest_images_dir / category_candidate
        else:
            output_folder = unknown_dir
            unknown_count += 1
            if category_candidate not in unknown_names:
                unknown_names.append(category_candidate)
            
        output_folder.mkdir(parents=True, exist_ok=True)
        
        prod_img_folder = source_images_dir / product_code
        if not prod_img_folder.exists():
            continue
            
        safe_prod_name = safe_filename(product_name)
        
        for img_file in prod_img_folder.iterdir():
            if img_file.is_file() and img_file.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                img_type = img_file.stem
                new_filename = f"{safe_prod_name}_{img_type}.jpg"
                dest_path = output_folder / new_filename
                
                # Resize and save
                success = resize_image(img_file, dest_path, max_size=320)
                if success:
                    processed += 1

    # Save the names of unknown categories to a text file
    unknown_log_path = unknown_dir / "unknown_categories_log.txt"
    with open(unknown_log_path, 'w', encoding='utf-8') as f:
        for name in unknown_names:
            f.write(f"{name}\n")

    print("\n--- Summary ---")
    print(f"Successfully processed and resized {processed} images.")
    print(f"Images for {unknown_count} products were sent to the 'unknown' folder.")
    print(f"Names of unknown categories saved to: {unknown_log_path}")
    print(f"Categorized images are saved in: {dest_images_dir}")

if __name__ == '__main__':
    main()