import re

file_path = "scripts/train_attention_unet_predictor.py"
with open(file_path, "r") as f:
    content = f.read()

# Add random_split to torch.utils.data import if missing
if "random_split" not in content:
    content = content.replace(
        "from torch.utils.data import Dataset, DataLoader",
        "from torch.utils.data import Dataset, DataLoader, random_split"
    )

# Add val-split to argparse
if "parser.add_argument(\"--val-split\"" not in content:
    content = content.replace(
        'parser.add_argument("--lr", default=1e-3, type=float)',
        'parser.add_argument("--lr", default=1e-3, type=float)\n    parser.add_argument("--val-split", default=0.1, type=float)'
    )

# Replace the training loop with a train/val loop
old_training_loop = """    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    
    model = AttentionUNet()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
    
    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for x, y in dataloader:
            optimizer.zero_grad()
            log_pred = model(x)
            loss = entropy_weighted_kl(log_pred, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * x.size(0)
            
        scheduler.step()
        epoch_loss = total_loss / len(dataset)
        if (epoch+1) % 10 == 0:
            score_approx = max(0, min(100, 100 * np.exp(-3 * epoch_loss)))
            print(f"Epoch {epoch+1:3d}/{args.epochs} | WKL Loss: {epoch_loss:.4f} | Approx Score: {score_approx:.2f}/100")
            
    out_path = Path(args.out_model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_path)"""

new_training_loop = """    val_size = int(len(dataset) * args.val_split)
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
    
    print(f"Train samples: {train_size}, Val samples: {val_size}")
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AttentionUNet().to(device)
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
    
    best_val_loss = float('inf')
    
    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            log_pred = model(x)
            loss = entropy_weighted_kl(log_pred, y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * x.size(0)
            
        scheduler.step()
        train_loss /= train_size
        
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                log_pred = model(x)
                loss = entropy_weighted_kl(log_pred, y)
                val_loss += loss.item() * x.size(0)
                
        if val_size > 0:
            val_loss /= val_size
        else:
            val_loss = 0.0
            
        if (epoch+1) % 10 == 0 or epoch == 0:
            score_approx = max(0, min(100, 100 * np.exp(-3 * val_loss))) if val_size > 0 else 0
            print(f"Epoch {epoch+1:3d}/{args.epochs} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val Score Approx: {score_approx:.2f}")
            
        if val_loss < best_val_loss or val_size == 0:
            best_val_loss = val_loss
            out_path = Path(args.out_model)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), out_path)
            
    print(f"\\nTraining complete. Best Val Loss: {best_val_loss:.4f}")
    print(f"Saved best Attention U-Net to {args.out_model}")"""

content = content.replace(old_training_loop, new_training_loop)

with open(file_path, "w") as f:
    f.write(content)
