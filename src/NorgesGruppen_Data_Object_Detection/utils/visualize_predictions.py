import os
import json
import cv2
from pathlib import Path
from collections import defaultdict
import random

def visualize_predictions():
    # Stier
    images_dir = Path('src/NorgesGruppen_Data_Object_Detection/datasets/detection_dataset/coco_dataset/val')
    preds_path = Path('src/NorgesGruppen_Data_Object_Detection/test_output_v10/predictions.json')
    gt_path = Path('src/NorgesGruppen_Data_Object_Detection/datasets/detection_dataset/coco_dataset/annotations.json')
    output_dir = Path('src/NorgesGruppen_Data_Object_Detection/test_output_v10/visualized')
    
    if not output_dir.exists():
        output_dir.mkdir(parents=True)
        
    print("Laster inn prediksjoner og fasit for navneoppslag...")
    with open(preds_path, 'r', encoding='utf-8') as f:
        predictions = json.load(f)
        
    with open(gt_path, 'r', encoding='utf-8') as f:
        coco = json.load(f)
        
    # Oppslag for å finne mappenavn / filnavn basert på image_id
    id_to_filename = {img['id']: img['file_name'] for img in coco.get('images', [])}
    
    # Oppslag for kategori ID -> Navn
    id_to_catname = {cat['id']: cat['name'] for cat in coco.get('categories', [])}
    
    # Grupper prediksjoner pr bilde
    preds_by_image = defaultdict(list)
    for p in predictions:
        preds_by_image[p['image_id']].append(p)
        
    # Velg 10 tilfeldige bilder fra prediksjonene som faktisk ligger i val-mappen
    available_image_ids = [img_id for img_id in preds_by_image.keys() if (images_dir / id_to_filename.get(img_id, "")).exists()]
    
    if not available_image_ids:
        print("[FEIL] Fant ingen bilder fra prediksjonene i val-mappen.")
        return
        
    random.seed(42) # For å få de samme 10 bildene hver gang, kan fjernes
    sample_ids = random.sample(available_image_ids, min(10, len(available_image_ids)))
    
    print(f"Tegner bounding boxes på {len(sample_ids)} bilder...\n")
    
    for img_id in sample_ids:
        filename = id_to_filename[img_id]
        img_path = images_dir / filename
        
        # Les bildet
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"Kunne ikke lese {filename}")
            continue
            
        preds = preds_by_image[img_id]
        
        # Tegn hver boks
        for p in preds:
            # bbox i prediksjoner er COCO: [x, y, w, h]
            x, y, w, h = p['bbox']
            x1, y1 = int(x), int(y)
            x2, y2 = int(x + w), int(y + h)
            
            score = p['score']
            cat_id = p['category_id']
            cat_name = id_to_catname.get(cat_id, "Unknown")
            
            # Velg en farge (grønn)
            color = (0, 255, 0)
            
            # Tegn rektangel
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
            
            # Legg på tekst (Klasse + Score)
            label = f"{cat_name[:15]} {score:.2f}" # Korter ned lange navn litt
            
            # For å få teksten lesbar, tegner vi en fylt bakgrunnsboks
            (text_width, text_height), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(img, (x1, y1 - text_height - 10), (x1 + text_width, y1), color, -1)
            cv2.putText(img, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            
        # Lagre bildet
        save_path = output_dir / f"pred_{filename}"
        cv2.imwrite(str(save_path), img)
        print(f"Lagret: {save_path.name} (Fant {len(preds)} objekter)")

    print(f"\n[SUKSESS] Ferdig! Du kan se de 10 bildene i mappen: {output_dir}")

if __name__ == '__main__':
    visualize_predictions()