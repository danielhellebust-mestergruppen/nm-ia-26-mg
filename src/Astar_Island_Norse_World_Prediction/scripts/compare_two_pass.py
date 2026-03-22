import subprocess
import re

models = ["attn_unet", "socio_unet", "time_socio_deep_unet", "ensemble"]
print(f"{'Model':<18} | {'Uniform Mean':<15} | {'Two-Pass Mean'}")
print("-" * 55)

for model in models:
    try:
        cmd = [
            "python", "scripts/eval_two_pass.py",
            "--predictor-mode", model
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{model:<18} | {'ERROR':<15} | {'ERROR'}")
            continue
            
        uniform = re.search(r"Uniform 8-queries Mean Score: ([\d.]+)", result.stdout)
        twopass = re.search(r"Two-Pass Smart Alloc Mean Score: ([\d.]+)", result.stdout)
        
        if uniform and twopass:
            print(f"{model:<18} | {float(uniform.group(1)):<15.2f} | {float(twopass.group(1)):.2f}")
        else:
            print(f"{model:<18} | {'PARSE ERROR':<15} | {'PARSE ERROR'}")
    except Exception as e:
        print(f"{model:<18} | {'EXCEPTION':<15} | {'EXCEPTION'}")
