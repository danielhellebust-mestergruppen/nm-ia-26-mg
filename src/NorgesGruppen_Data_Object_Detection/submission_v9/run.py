import argparse
import json
from pathlib import Path
from ultralytics import YOLO

def main():
    try:
        # Sett opp parser for argumentene som NM-systemet bruker
        parser = argparse.ArgumentParser()
        parser.add_argument('--input', type=str, required=True, help='Path to input images directory')
        parser.add_argument('--output', type=str, required=True, help='Path to output JSON file')
        args = parser.parse_args()

        input_dir = Path(args.input)
        output_file = Path(args.output)
        
        # Sørg for at output-mappen eksisterer
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
    except Exception as e:
        print(f"Klarte ikke starte scriptet eller parse argumenter: {e}")
        return

    predictions = []
    
    try:
        # 1. Hent stier til vekter - Ligger i samme mappe som run.py (i zip-filen)
        base_path = Path(__file__).parent
        det_model_path = base_path / 'best_det.onnx'
        cls_model_path = base_path / 'best_cls.onnx'
        
        # 2. Laster inn Category Map (Navn -> ID for NM)
        category_map_path = base_path / 'category_map.json'
        safe_name_to_id = {}
        if category_map_path.exists():
            with open(category_map_path, 'r', encoding='utf-8') as f:
                safe_name_to_id = json.load(f)
        
        # 3. Last inn modellene
        det_model = YOLO(det_model_path, task='detect')
        cls_model = YOLO(cls_model_path, task='classify')
        
        # Finn alle bilder som matcher formatet img_XXXXX.jpg (f.eks. img_00042.jpg)
        # Bruker rglob i tilfelle --input er /data og bildene ligger i /data/images/
        import re
        image_paths = []
        for p in input_dir.rglob('*'):
            if p.is_file() and re.match(r'^img_\d{5}\.jpe?g$', p.name, re.IGNORECASE):
                image_paths.append(p)
        
        # Gå igjennom hvert enkelt test-bilde
        for img_path in image_paths:
            try:
                # Trekk ut image_id fra filnavnet
                filename = img_path.stem
                import re
                match = re.search(r'img_(\d+)', filename)
                if match:
                    image_id = int(match.group(1))
                else:
                    digits = ''.join(filter(str.isdigit, filename))
                    if digits:
                        image_id = int(digits)
                    else:
                        print(f"Advarsel: Hopper over {img_path.name} da det mangler ID.")
                        continue
                        
                # STEG 1: OBJEKTGJENKJENNING
                det_results = det_model.predict(source=str(img_path), imgsz=1024, device=0, verbose=False)
                result = det_results[0]
                
                boxes = result.boxes
                if boxes is None or len(boxes) == 0:
                    continue
                    
                img = result.orig_img
                if img is None:
                    import cv2
                    img = cv2.imread(str(img_path))
                h, w = img.shape[:2]
                        
                # STEG 2: KLASSIFISERING
                for i in range(len(boxes)):
                    box_xyxy = boxes.xyxy[i].tolist()
                    x1, y1, x2, y2 = map(int, box_xyxy)
                    
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(w, x2), min(h, y2)
                    
                    width = x2 - x1
                    height = y2 - y1
                    
                    if width < 5 or height < 5:
                        continue 
                        
                    coco_bbox = [float(x1), float(y1), float(width), float(height)]
                    det_score = float(boxes.conf[i])
                    
                    cropped_img = img[y1:y2, x1:x2]
                    
                    cls_results = cls_model.predict(source=cropped_img, imgsz=224, device=0, verbose=False)
                    
                    top_idx = cls_results[0].probs.top1
                    pred_class_name = cls_results[0].names[top_idx]
                    
                    category_id = safe_name_to_id.get(pred_class_name, -1)
                    if category_id == -1:
                        category_id = 0

                    prediction = {
                        "image_id": image_id,
                        "category_id": category_id,
                        "bbox": coco_bbox,
                        "score": det_score
                    }
                    predictions.append(prediction)
                    
            except Exception as e:
                print(f"Advarsel: Feilet fullstendig på {img_path.name}: {e}")
                continue
                
    except Exception as e:
        print("Kritisk feil under kjøring:")
        print(e)

    # GARANTERT SKRIVING AV FIL (sikrer exit code 0)
    try:
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(predictions, f, indent=2)
    except Exception as e:
        print(f"Feil ved lagring av output: {e}")

if __name__ == '__main__':
    main()