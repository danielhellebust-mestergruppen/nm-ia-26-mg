import json
from pathlib import Path

def main():
    # Define paths
    base_dir = Path(r"src\NorgesGruppen_Data_Object_Detection")
    map_path = base_dir / "submission_v6" / "category_map.json"
    images_dir = base_dir / "datasets" / "cropped_objects_ground_truth_revised"

    # 1. Load category mapping
    try:
        with open(map_path, 'r', encoding='utf-8') as f:
            category_map = json.load(f)
        print(f"Loaded {len(category_map)} categories from category_map.json.")
    except Exception as e:
        print(f"Failed to load category_map.json: {e}")
        return

    # 2. Count images per category in the directory
    category_counts = {}
    total_images = 0

    if not images_dir.exists():
        print(f"Directory not found: {images_dir}")
        return

    for folder in images_dir.iterdir():
        if folder.is_dir():
            count = len([f for f in folder.iterdir() if f.is_file()])
            category_counts[folder.name] = count
            total_images += count

    print(f"\n--- Images per Category ---")
    sorted_counts = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    # Print top 10 and bottom 10 for brevity, or we can just print the missing ones.
    print(f"Showing top 5 populated categories:")
    for cat_name, count in sorted_counts:
        print(f"{cat_name}: {count}")

    print(f"\nTotal images found: {total_images}")

    # 3. Find categories without images
    categories_without_images = []
    
    # Check all categories defined in category_map
    for safe_cat_name, cat_id in category_map.items():
        if safe_cat_name not in category_counts or category_counts[safe_cat_name] == 0:
            categories_without_images.append((cat_id, safe_cat_name))

    print(f"\n--- Categories WITHOUT Images ({len(categories_without_images)}) ---")
    categories_without_images.sort(key=lambda x: x[0])
    for cat_id, safe_cat_name in categories_without_images:
        print(f"ID {cat_id:3d}: {safe_cat_name}")

if __name__ == '__main__':
    main()