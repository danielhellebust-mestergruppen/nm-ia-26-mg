import os
import random
import shutil
from pathlib import Path
import kagglehub
from huggingface_hub import snapshot_download
import yaml
from tqdm import tqdm

def find_images_and_labels(base_image_dir, base_label_dir):
    """Recursively find all images and their corresponding label files."""
    dataset_items = []
    valid_exts = {'.jpg', '.jpeg', '.png'}
    
    # Ensure directories exist
    if not Path(base_image_dir).exists() or not Path(base_label_dir).exists():
        return dataset_items

    for root, _, files in os.walk(base_image_dir):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in valid_exts:
                img_path = Path(root) / file
                
                # Check directly in the base label dir with the same stem
                label_path = Path(base_label_dir) / f"{img_path.stem}.txt"
                
                # If not found, try maintaining relative directory structure
                if not label_path.exists():
                    try:
                        rel_path = img_path.relative_to(base_image_dir)
                        label_path = Path(base_label_dir) / rel_path.with_suffix('.txt')
                    except ValueError:
                        pass
                
                if label_path.exists():
                    dataset_items.append((img_path, label_path))
                    
    return dataset_items

def main():
    # 1. Download Hugging Face Datasets
    print("Downloading Hugging Face Datasets...")
    hf_repo = "DanielHellebust"
    hf_datasets = [
        "NorgesGruppen_classification_dataset",
        "NorgesGruppen_classifier_dataset_capped_split",
        "NorgesGruppen_detection_dataset"
    ]
    
    hf_paths = {}
    for ds in hf_datasets:
        print(f"  -> Downloading {ds}...")
        path = snapshot_download(repo_id=f"{hf_repo}/{ds}", repo_type="dataset")
        hf_paths[ds] = path
        print(f"  -> Saved to {path}")

    # 2. Download Kaggle Dataset
    print("\nDownloading SKU-110k from Kaggle...")
    try:
        sku_path = kagglehub.dataset_download("thedatasith/sku110k-annotations")
        print(f"  -> Saved to {sku_path}")
    except Exception as e:
        print(f"Error downloading from Kaggle: {e}")
        print("Please ensure you are authenticated with Kaggle (e.g., KAGGLE_USERNAME and KAGGLE_KEY env variables).")
        return

    # 3. Collect Data
    print("\nProcessing and collecting data...")
    
    # Gather SKU-110K Data
    sku_items = []
    sku_base = Path(sku_path)
    
    # The kaggle dataset usually splits into train/val/test inside 'images' and 'labels' folders
    for split in ['train', 'val', 'test']:
        img_d = sku_base / "images" / split
        lbl_d = sku_base / "labels" / split
        
        # Sometimes nested under SKU110K_fixed
        if not img_d.exists():
            img_d = sku_base / "SKU110K_fixed" / "images" / split
            lbl_d = sku_base / "SKU110K_fixed" / "labels" / split

        if img_d.exists() and lbl_d.exists():
            sku_items.extend(find_images_and_labels(img_d, lbl_d))

    # Fallback to flat directory search if splits weren't found
    if not sku_items:
        img_d = sku_base / "images" if (sku_base / "images").exists() else sku_base
        lbl_d = sku_base / "labels" if (sku_base / "labels").exists() else sku_base
        sku_items = find_images_and_labels(img_d, lbl_d)

    print(f"Found {len(sku_items)} items in SKU-110k.")
    
    # Take 50% of SKU-110k
    random.seed(42)
    random.shuffle(sku_items)
    sku_half_count = len(sku_items) // 2
    sku_sampled = sku_items[:sku_half_count]
    print(f"Sampled 50% of SKU-110k: {len(sku_sampled)} items.")

    # Gather NorgesGruppen Detection Data
    ng_det_path = Path(hf_paths["NorgesGruppen_detection_dataset"])
    
    # Structure of your detection dataset: images likely in coco_dataset, labels in labels
    ng_img_dir = ng_det_path / "coco_dataset"
    if not ng_img_dir.exists(): # Fallback if just images
        ng_img_dir = ng_det_path / "images"
    ng_lbl_dir = ng_det_path / "labels"
    
    ng_items = find_images_and_labels(ng_img_dir, ng_lbl_dir)
    # Fallback flat search
    if not ng_items:
        ng_items = find_images_and_labels(ng_det_path, ng_det_path)
        
    print(f"Found {len(ng_items)} items in NorgesGruppen detection dataset.")

    # 4. Merge and Split
    all_items = sku_sampled + ng_items
    random.shuffle(all_items)
    
    # 80% train, 10% val, 10% test
    total = len(all_items)
    train_end = int(total * 0.8)
    val_end = int(total * 0.9)
    
    splits = {
        'train': all_items[:train_end],
        'val': all_items[train_end:val_end],
        'test': all_items[val_end:]
    }
    
    print(f"\nCreated Splits for merged detection dataset:")
    print(f"  Train: {len(splits['train'])}")
    print(f"  Val:   {len(splits['val'])}")
    print(f"  Test:  {len(splits['test'])}")

    # 5. Copy to new structure
    out_dir = Path("merged_yolo_dataset")
    print(f"\nCopying files to {out_dir}...")
    
    for split_name, items in splits.items():
        split_img_dir = out_dir / "images" / split_name
        split_lbl_dir = out_dir / "labels" / split_name
        split_img_dir.mkdir(parents=True, exist_ok=True)
        split_lbl_dir.mkdir(parents=True, exist_ok=True)
        
        for img_path, lbl_path in tqdm(items, desc=f"Copying {split_name}"):
            # Generate unique filenames to avoid collision between the datasets
            unique_name = f"{img_path.parent.name}_{img_path.name}"
            
            shutil.copy(img_path, split_img_dir / unique_name)
            shutil.copy(lbl_path, split_lbl_dir / f"{Path(unique_name).stem}.txt")

    # 6. Create config.yaml for YOLO training
    config_path = out_dir / "config.yaml"
    config = {
        'path': str(out_dir.absolute()),
        'train': 'images/train',
        'val': 'images/val',
        'test': 'images/test',
        'nc': 1,
        'names': {0: 'product'} # Class 0 = generic product/object
    }
    
    with open(config_path, 'w') as f:
        yaml.dump(config, f, sort_keys=False)
        
    print(f"\nDone! Merged YOLO Dataset ready at: {out_dir.absolute()}")
    print(f"YOLO Training config generated at: {config_path.absolute()}")
    print("\nYou can now upload this 'merged_yolo_dataset' folder to a public repo to reproduce the training.")

if __name__ == "__main__":
    main()