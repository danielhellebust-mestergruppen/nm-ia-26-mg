import shutil
from pathlib import Path
from ultralytics import YOLO

def main():
    base_dir = Path(r"src\NorgesGruppen_Data_Object_Detection")
    src_dir = base_dir / "datasets" / "cropped_objects_ground_truth_revised" / "unknown_product"
    dest_dir = base_dir / "datasets" / "classified_unknowns"
    model_path = base_dir / "runs" / "classify" / "runs" / "classify" / "product_classifier_v3m2" / "weights" / "best.pt"

    if not src_dir.exists():
        print(f"Source directory not found: {src_dir}")
        return

    if not model_path.exists():
        print(f"Model not found: {model_path}")
        return

    print("Loading model...")
    model = YOLO(model_path)

    print(f"Preparing destination directory: {dest_dir}")
    # Clear dest_dir if it exists to avoid mixing old runs
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    images = [p for p in src_dir.iterdir() if p.is_file() and p.suffix.lower() in ['.jpg', '.jpeg', '.png']]
    print(f"Found {len(images)} images to classify.")

    class_counts = {}
    
    print("Classifying and copying images...")
    # Process images and copy them to folders named after their predicted category
    for i, img_path in enumerate(images):
        if i % 50 == 0:
            print(f"Processing image {i}/{len(images)}...")
            
        # Predict using YOLO
        results = model.predict(source=str(img_path), verbose=False, device=0)
        
        # Extract top prediction
        top_idx = results[0].probs.top1
        pred_class_name = results[0].names[top_idx]
        conf = float(results[0].probs.top1conf)
        
        # Create folder for the predicted class
        class_folder = dest_dir / pred_class_name
        class_folder.mkdir(parents=True, exist_ok=True)
        
        # Copy file, prefixing with confidence score to easily find high/low confidence predictions
        dest_file = class_folder / f"{conf:.2f}_{img_path.name}"
        shutil.copy2(img_path, dest_file)
        
        # Update counts
        class_counts[pred_class_name] = class_counts.get(pred_class_name, 0) + 1

    print("\n--- Classification Summary ---")
    sorted_counts = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)
    for cls_name, count in sorted_counts[:20]: # Show top 20
        print(f"{cls_name}: {count} images")
        
    if len(sorted_counts) > 20:
        print(f"... and {len(sorted_counts) - 20} more categories.")
        
    print(f"\nAll categorized images have been saved to:\n{dest_dir}")

if __name__ == '__main__':
    main()