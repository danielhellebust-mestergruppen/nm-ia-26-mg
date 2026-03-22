import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

try:
    from ultralytics import YOLO
except ImportError:
    print(Fore.RED + "ultralytics not installed. Please run: pip install ultralytics")
    sys.exit(1)

# Global variables
WORKSPACE_DIR = Path(__file__).parent.absolute()
NG_DIR = WORKSPACE_DIR / "src" / "NorgesGruppen_Data_Object_Detection"
TRIPLETEX_DIR = WORKSPACE_DIR / "src" / "Tripletex_AI_Accounting_Agent"
ASTAR_DIR = WORKSPACE_DIR / "src" / "Astar_Island_Norse_World_Prediction"
DATASETS_DIR = NG_DIR / "datasets"
CLS_DATASET = DATASETS_DIR / "classifier_dataset_capped_split"
MERGED_YOLO_DIR = WORKSPACE_DIR / "merged_yolo_dataset"
YOLO_CONFIG = MERGED_YOLO_DIR / "config.yaml"

def print_header(title):
    print("\n" + "="*60)
    print(Fore.CYAN + Style.BRIGHT + f" {title}".center(58))
    print("="*60 + "\n")

def prompt_choice(options, default=None):
    while True:
        for idx, opt in enumerate(options, 1):
            print(f"  {Fore.GREEN}{idx}{Style.RESET_ALL}. {opt}")
        
        prompt_text = f"\nEnter choice (1-{len(options)})"
        if default:
            prompt_text += f" [{default}]"
        prompt_text += ": "
        
        choice = input(prompt_text)
        if default and choice.strip() == "":
            return default - 1
            
        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(options):
                return choice_idx
        except ValueError:
            pass
        print(Fore.RED + "Invalid choice. Please try again.")

def step_download_datasets():
    print_header("Step 1: Download & Prepare Datasets")
    if MERGED_YOLO_DIR.exists():
        print(Fore.YELLOW + f"Directory '{MERGED_YOLO_DIR.name}' already exists.")
        ans = input("Do you want to re-download and merge? (y/N): ").lower()
        if ans != 'y':
            print("Skipping download.")
            return

    script_path = WORKSPACE_DIR / "setup_reproduction_data.py"
    if not script_path.exists():
        print(Fore.RED + f"Error: Could not find {script_path.name} in {WORKSPACE_DIR}")
        return

    print("Running setup_reproduction_data.py...")
    subprocess.run([sys.executable, str(script_path)], check=True)

def step_download_pretrained():
    print_header("Step 2: Download Pre-trained Models (submission_v9)")
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(Fore.RED + "huggingface_hub not installed. Please run: pip install huggingface_hub")
        return

    repo_id = "DanielHellebust/NorgesGruppen_submission_v9_models"
    sub_v9_dir = NG_DIR / "submission_v9"
    
    print(Fore.CYAN + f"Downloading models from {repo_id}...")
    try:
        snapshot_download(repo_id=repo_id, repo_type="model", local_dir=str(sub_v9_dir))
        print(Fore.GREEN + f"\nSuccessfully downloaded models to {sub_v9_dir}")
    except Exception as e:
        print(Fore.RED + f"\nFailed to download models: {e}")

def step_choose_yolo_version(current_version):
    print_header(f"Step 3: Choose YOLOv8 Version (Current: {current_version})")
    versions = [
        "n (Nano - Fast, Lowest Accuracy)", 
        "s (Small)", 
        "m (Medium)", 
        "l (Large)", 
        "x (Extra Large - Slowest, Highest Accuracy)"
    ]
    choice = prompt_choice(versions, default=1)
    
    mapping = {0: 'n', 1: 's', 2: 'm', 3: 'l', 4: 'x'}
    version = mapping[choice]
    
    print(Fore.CYAN + f"\nSelected YOLOv8{version} for subsequent training.")
    return version

def step_train_detection(yolo_version):
    print_header("Step 3: Train Object Detection Model")
    if not YOLO_CONFIG.exists():
        print(Fore.RED + f"Error: Cannot find {YOLO_CONFIG}")
        print("Please run Step 1 to download and prepare the dataset first.")
        return None

    model_name = f'yolov8{yolo_version}.pt'
    print(f"Initializing YOLO Detection Model: {model_name}")
    try:
        model = YOLO(model_name)
    except Exception as e:
        print(Fore.RED + f"Failed to initialize YOLO model: {e}")
        return None
    
    epochs = input("Enter number of epochs for detection [default: 50]: ").strip()
    epochs = int(epochs) if epochs.isdigit() else 50
    
    imgsz = input("Enter image size [default: 640]: ").strip()
    imgsz = int(imgsz) if imgsz.isdigit() else 640

    print(Fore.YELLOW + f"\nStarting Detection Training on {MERGED_YOLO_DIR.name}...")
    try:
        results = model.train(data=str(YOLO_CONFIG), epochs=epochs, imgsz=imgsz, project='runs/detect', name=f'train_det_v8{yolo_version}')
        
        best_model_path = Path(model.trainer.save_dir) / 'weights' / 'best.pt'
        if not best_model_path.exists():
            print(Fore.RED + "Error: Could not locate best.pt after training.")
            return None
            
        print(Fore.GREEN + f"\nDetection training complete! Best model saved to:\n{best_model_path}")
        return best_model_path
    except Exception as e:
        print(Fore.RED + f"\nTraining failed: {e}")
        return None

def step_train_classification(yolo_version):
    print_header("Step 4: Train Classification Model")
    if not CLS_DATASET.exists():
        print(Fore.RED + f"Error: Cannot find {CLS_DATASET}")
        return None

    model_name = f'yolov8{yolo_version}-cls.pt'
    print(f"Initializing YOLO Classification Model: {model_name}")
    try:
        model = YOLO(model_name)
    except Exception as e:
        print(Fore.RED + f"Failed to initialize YOLO model: {e}")
        return None
    
    epochs = input("Enter number of epochs for classification [default: 50]: ").strip()
    epochs = int(epochs) if epochs.isdigit() else 50
    
    imgsz = input("Enter image size [default: 224]: ").strip()
    imgsz = int(imgsz) if imgsz.isdigit() else 224

    print(Fore.YELLOW + f"\nStarting Classification Training on {CLS_DATASET.name}...")
    try:
        results = model.train(data=str(CLS_DATASET), epochs=epochs, imgsz=imgsz, project='runs/classify', name=f'train_cls_v8{yolo_version}')
        
        best_model_path = Path(model.trainer.save_dir) / 'weights' / 'best.pt'
        if not best_model_path.exists():
            print(Fore.RED + "Error: Could not locate best.pt after training.")
            return None
            
        print(Fore.GREEN + f"\nClassification training complete! Best model saved to:\n{best_model_path}")
        return best_model_path
    except Exception as e:
        print(Fore.RED + f"\nTraining failed: {e}")
        return None

def step_validate(det_model_path, cls_model_path):
    print_header("Step 5: Validate Models")
    
    if det_model_path and Path(det_model_path).exists():
        print(Fore.CYAN + f"Validating Detection Model ({Path(det_model_path).name})...")
        try:
            model = YOLO(det_model_path)
            metrics = model.val(data=str(YOLO_CONFIG))
            print(Fore.GREEN + f"Detection mAP50-95: {metrics.box.map:.3f}")
        except Exception as e:
            print(Fore.RED + f"Detection validation failed: {e}")
    else:
        print(Fore.YELLOW + "No valid detection model provided to validate.")

    if cls_model_path and Path(cls_model_path).exists():
        print(Fore.CYAN + f"\nValidating Classification Model ({Path(cls_model_path).name})...")
        try:
            model = YOLO(cls_model_path)
            metrics = model.val(data=str(CLS_DATASET))
            print(Fore.GREEN + f"Classification Top-1 Accuracy: {metrics.top1:.3f}")
        except Exception as e:
            print(Fore.RED + f"Classification validation failed: {e}")
    else:
        print(Fore.YELLOW + "No valid classification model provided to validate.")

def step_create_submission(det_model_path, cls_model_path):
    print_header("Step 6: Export & Create Submission Zip")
    
    if not det_model_path or not Path(det_model_path).exists():
        print(Fore.RED + "Error: Detection model not found. Cannot create submission.")
        return
    if not cls_model_path or not Path(cls_model_path).exists():
        print(Fore.RED + "Error: Classification model not found. Cannot create submission.")
        return

    det_model_path = Path(det_model_path)
    cls_model_path = Path(cls_model_path)

    print(Fore.CYAN + "Exporting Detection model to ONNX...")
    try:
        det_model = YOLO(str(det_model_path))
        det_onnx_path = det_model.export(format='onnx', imgsz=640)
    except Exception as e:
        print(Fore.RED + f"Detection export failed: {e}")
        return
        
    print(Fore.CYAN + "Exporting Classification model to ONNX...")
    try:
        cls_model = YOLO(str(cls_model_path))
        cls_onnx_path = cls_model.export(format='onnx', imgsz=224)
    except Exception as e:
        print(Fore.RED + f"Classification export failed: {e}")
        return

    print(Fore.CYAN + "\nGathering required files for submission.zip...")
    sub_v9_dir = NG_DIR / "submission_v9"
    run_py = sub_v9_dir / "run.py"
    cat_map = sub_v9_dir / "category_map.json"
    
    if not run_py.exists():
        print(Fore.RED + f"Error: Could not find template {run_py}")
        return
    if not cat_map.exists():
        print(Fore.RED + f"Error: Could not find {cat_map}")
        return

    zip_path = WORKSPACE_DIR / "submission.zip"
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            print(f"  Adding {Path(det_onnx_path).name} as best_det.onnx")
            zipf.write(det_onnx_path, "best_det.onnx")
            
            print(f"  Adding {Path(cls_onnx_path).name} as best_cls.onnx")
            zipf.write(cls_onnx_path, "best_cls.onnx")
            
            print(f"  Adding {run_py.name}")
            zipf.write(run_py, run_py.name)
            
            print(f"  Adding {cat_map.name}")
            zipf.write(cat_map, cat_map.name)

        print(Fore.GREEN + f"\nSuccess! Submission created at: {zip_path}")
    except Exception as e:
        print(Fore.RED + f"Failed to create ZIP: {e}")

def step_run_tripletex_agent():
    print_header("Tripletex AI Accounting Agent")
    
    if not TRIPLETEX_DIR.exists():
        print(Fore.RED + f"Error: Cannot find {TRIPLETEX_DIR}")
        return

    main_script = TRIPLETEX_DIR / "main.py"
    if not main_script.exists():
        print(Fore.RED + f"Error: Cannot find {main_script}")
        return
        
    req_file = WORKSPACE_DIR / "requirements.txt"
    if req_file.exists():
        print(Fore.YELLOW + "Checking workspace dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"])

    print(Fore.CYAN + "Starting Tripletex Agent (Uvicorn Server)...")
    try:
        # Assuming the agent uses Uvicorn to run a FastAPI app as seen in requirements
        subprocess.run(["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"], cwd=str(TRIPLETEX_DIR))
    except KeyboardInterrupt:
        print(Fore.YELLOW + "\nTripletex Agent stopped.")
    except Exception as e:
        print(Fore.RED + f"Failed to start Tripletex Agent: {e}")

def step_run_astar_island():
    print_header("Astar Island Norse World Prediction")
    
    if not ASTAR_DIR.exists():
        print(Fore.RED + f"Error: Cannot find {ASTAR_DIR}")
        return

    req_file = WORKSPACE_DIR / "requirements.txt"
    if req_file.exists():
        print(Fore.YELLOW + "Checking workspace dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"])

    options = [
        "Backfill Completed Rounds",
        "Backfill Replays",
        "Train Socio-UNet Predictor",
        "Simulate Queries (TUI)",
        "Run Active Round (Two Stage Workflow)",
        "Back to Main Menu"
    ]
    
    choice = prompt_choice(options)
    
    script_to_run = None
    args = []
    
    if choice == 0:
        script_to_run = "backfill_completed_rounds.py"
    elif choice == 1:
        script_to_run = "backfill_replays.py"
    elif choice == 2:
        script_to_run = "train_socio_unet_predictor.py"
        args = ["--epochs", "250"]
    elif choice == 3:
        script_to_run = "simulate_queries_tui.py"
        args = ["--loop-all", "--queries", "8", "--predictor", "socio_unet"]
    elif choice == 4:
        script_to_run = "two_stage_round_workflow.py"
    elif choice == 5:
        return

    if script_to_run:
        script_path = ASTAR_DIR / "scripts" / script_to_run
        if not script_path.exists():
            print(Fore.RED + f"Error: Cannot find script {script_path}")
            return
            
        print(Fore.CYAN + f"\nRunning {script_to_run}...")
        cmd = [sys.executable, str(script_path)] + args
        try:
            subprocess.run(cmd, cwd=str(ASTAR_DIR))
        except KeyboardInterrupt:
            print(Fore.YELLOW + f"\n{script_to_run} stopped by user.")
        except Exception as e:
            print(Fore.RED + f"Error running {script_to_run}: {e}")

def main():
    yolo_version = 'n'
    det_model_path = None
    cls_model_path = None

    while True:
        print_header("Main Menu - NorgesGruppen, Tripletex & Astar Island")
        options = [
            "Download Datasets & Prepare Data (NG)",
            "Download Pre-trained Models (NG)",
            f"Select YOLOv8 Version (NG) (Current: {yolo_version})",
            "Train Detection Model (NG)",
            "Train Classification Model (NG)",
            "Validate Models (NG)",
            "Create Submission Zip (NG)",
            "Run Tripletex AI Accounting Agent (FastAPI)",
            "Run Astar Island Prediction Lab",
            "Exit"
        ]
        choice = prompt_choice(options)
        
        if choice == 0:
            step_download_datasets()
        elif choice == 1:
            step_download_pretrained()
        elif choice == 2:
            yolo_version = step_choose_yolo_version(yolo_version)
        elif choice == 3:
            path = step_train_detection(yolo_version)
            if path: det_model_path = path
        elif choice == 4:
            path = step_train_classification(yolo_version)
            if path: cls_model_path = path
        elif choice == 5:
            if not det_model_path:
                p = input("Enter path to detection best.pt (or press Enter to skip): ").strip()
                if p and Path(p).exists(): det_model_path = Path(p)
            if not cls_model_path:
                p = input("Enter path to classification best.pt (or press Enter to skip): ").strip()
                if p and Path(p).exists(): cls_model_path = Path(p)
            step_validate(det_model_path, cls_model_path)
        elif choice == 6:
            if not det_model_path:
                p = input("Enter path to detection best.pt: ").strip()
                if p and Path(p).exists(): det_model_path = Path(p)
            if not cls_model_path:
                p = input("Enter path to classification best.pt: ").strip()
                if p and Path(p).exists(): cls_model_path = Path(p)
            step_create_submission(det_model_path, cls_model_path)
        elif choice == 7:
            step_run_tripletex_agent()
        elif choice == 8:
            step_run_astar_island()
        elif choice == 9:
            print(Fore.GREEN + "Exiting. Goodbye!")
            break

if __name__ == "__main__":
    main()