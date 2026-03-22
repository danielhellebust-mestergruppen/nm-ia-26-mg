import os
import json
import cv2
from pathlib import Path
from ultralytics import YOLO

def crop_and_save_objects():
    # 1. Stier
    dataset_dir = Path('src/NorgesGruppen_Data_Object_Detection/datasets/detection_dataset/coco_dataset')
    json_path = dataset_dir / 'annotations.json'
    
    # Mappen der vi lagrer de utklippede småbildene
    output_dir = Path('src/NorgesGruppen_Data_Object_Detection/datasets/cropped_objects_ground_truth')

    if not json_path.exists():
        print(f"[FEIL] Finner ikke annotations.json på: {json_path}")
        return

    # Klargjør output-mappen
    if output_dir.exists():
        import shutil
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Laster inn COCO annotations.json...")
    with open(json_path, 'r', encoding='utf-8') as f:
        coco = json.load(f)

    # 2. Bygg oppslagstabeller
    # category_id -> category_name
    categories = {c['id']: c['name'] for c in coco.get('categories', [])}
    
    # image_id -> image_info (filnavn)
    images = {img['id']: img for img in coco.get('images', [])}

    # image_id -> liste over annotations (bokser)
    annotations_by_image = {}
    for ann in coco.get('annotations', []):
        img_id = ann['image_id']
        if img_id not in annotations_by_image:
            annotations_by_image[img_id] = []
        annotations_by_image[img_id].append(ann)

    print(f"Fant {len(images)} bilder og {len(coco.get('annotations', []))} annoteringer.")

    total_crops = 0

    # 3. Gå gjennom alle bilder som har annoteringer
    for img_id, anns in annotations_by_image.items():
        if img_id not in images:
            continue
            
        img_info = images[img_id]
        file_name = img_info['file_name']
        
        # Finn bildet på disk (enten i train eller val)
        img_path_train = dataset_dir / 'train' / file_name
        img_path_val = dataset_dir / 'val' / file_name
        
        if img_path_train.exists():
            actual_img_path = img_path_train
        elif img_path_val.exists():
            actual_img_path = img_path_val
        else:
            print(f"Advarsel: Fant ikke bildefilen {file_name}")
            continue

        # Laster inn det originale bildet for å klippe
        img = cv2.imread(str(actual_img_path))
        if img is None:
            print(f"Kunne ikke lese bildet med OpenCV: {actual_img_path}")
            continue

        h, w = img.shape[:2]
        crop_count_for_image = 0

        # 4. Klipp ut hver boks
        for ann in anns:
            bbox = ann.get('bbox')
            if not bbox or len(bbox) != 4:
                continue
                
            # COCO bbox: [x_min, y_min, width, height]
            x_min, y_min, bw, bh = bbox
            
            # Konverter til heltall (x1, y1, x2, y2)
            x1, y1 = int(x_min), int(y_min)
            x2, y2 = int(x_min + bw), int(y_min + bh)
            
            # Klipp slik at vi ikke går utenfor kanten på bildet
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)

            # Sjekk at boksen har en gyldig størrelse
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue

            # Finn klassen (produktnavnet)
            cat_id = ann.get('category_id')
            class_name = categories.get(cat_id, f"Unknown_{cat_id}")

            # Sørg for at filnavnet/mappenavnet er trygt i Windows
            safe_class_name = "".join(c if c.isalnum() else "_" for c in class_name)
            
            # Lag en undermappe for hver produktkategori
            class_dir = output_dir / safe_class_name
            class_dir.mkdir(parents=True, exist_ok=True)
            
            # Klipp ut fra bildet (Numpy array bruker [y, x])
            cropped_img = img[y1:y2, x1:x2]

            # Lagre bildet i undermappen sin
            filename = f"{safe_class_name}_{img_id}_{crop_count_for_image:03d}.jpg"
            save_path = class_dir / filename
            
            cv2.imwrite(str(save_path), cropped_img)
            total_crops += 1
            crop_count_for_image += 1
            
        print(f"Klippet {crop_count_for_image} objekter fra: {file_name}")

    print(f"\n[SUKSESS] Ferdig!")
    print(f"Klippet ut {total_crops} individuelle produkter basert på annotations.json.")
    print(f"Du finner dem sortert i mapper her: {output_dir}")

if __name__ == '__main__':
    crop_and_save_objects()