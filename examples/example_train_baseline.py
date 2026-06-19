#!/usr/bin/env python3
"""Minimal baseline patch classifier for the breast FNAC patch dataset.

This is intentionally simple and meant as an example, not a state-of-the-art benchmark.
It expects a patch index CSV produced by scripts/create_patch_index.py and a split CSV
produced by scripts/create_patient_level_splits.py or a patch index that already has a
'split' column.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import torch
import torch.nn as nn
from PIL import Image
from sklearn.metrics import accuracy_score, classification_report, f1_score
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms
from tqdm import tqdm

LABELS = ["C1", "C2", "C3", "C4", "C5"]
LABEL_TO_IDX = {label: idx for idx, label in enumerate(LABELS)}


class PatchDataset(Dataset):
    def __init__(self, df: pd.DataFrame, patches_dir: Path, transform=None):
        self.df = df.reset_index(drop=True)
        self.patches_dir = patches_dir
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        path = self.patches_dir / row["patch_relative_path"]
        image = Image.open(path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        label = LABEL_TO_IDX[row["yokohama_category"]]
        return image, label


def build_model(num_classes: int = 5) -> nn.Module:
    model = models.resnet18(weights=models.ResNet18_Weights.DEFAULT)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model


def run_epoch(model, loader, criterion, optimizer, device, train: bool):
    model.train(train)
    losses = []
    all_y = []
    all_pred = []
    for images, labels in tqdm(loader, leave=False):
        images = images.to(device)
        labels = labels.to(device)
        with torch.set_grad_enabled(train):
            logits = model(images)
            loss = criterion(logits, labels)
            if train:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
        losses.append(float(loss.detach().cpu()))
        pred = logits.argmax(dim=1).detach().cpu().numpy().tolist()
        all_pred.extend(pred)
        all_y.extend(labels.detach().cpu().numpy().tolist())
    acc = accuracy_score(all_y, all_pred) if all_y else 0.0
    f1 = f1_score(all_y, all_pred, average="macro", zero_division=0) if all_y else 0.0
    return sum(losses) / max(len(losses), 1), acc, f1, all_y, all_pred


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a simple ResNet-18 patch classifier baseline.")
    parser.add_argument("--patch-index", type=Path, required=True, help="Patch index CSV with patch_relative_path, yokohama_category, split.")
    parser.add_argument("--patches-dir", type=Path, required=True, help="Path to patches/ directory.")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/baseline_resnet18"))
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--image-size", type=int, default=224)
    args = parser.parse_args()

    df = pd.read_csv(args.patch_index)
    required_cols = {"patch_relative_path", "yokohama_category", "split"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Patch index missing required columns: {sorted(missing)}")
    df = df[df["yokohama_category"].isin(LABELS)].copy()

    train_tf = transforms.Compose([
        transforms.Resize((args.image_size, args.image_size)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    eval_tf = transforms.Compose([
        transforms.Resize((args.image_size, args.image_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    train_df = df[df["split"] == "train"]
    val_df = df[df["split"].isin(["val", "validation"])]
    test_df = df[df["split"] == "test"]

    train_loader = DataLoader(PatchDataset(train_df, args.patches_dir, train_tf), batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers)
    val_loader = DataLoader(PatchDataset(val_df, args.patches_dir, eval_tf), batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)
    test_loader = DataLoader(PatchDataset(test_df, args.patches_dir, eval_tf), batch_size=args.batch_size, shuffle=False, num_workers=args.num_workers)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(num_classes=len(LABELS)).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    best_val_f1 = -1.0
    for epoch in range(1, args.epochs + 1):
        train_loss, train_acc, train_f1, _, _ = run_epoch(model, train_loader, criterion, optimizer, device, train=True)
        val_loss, val_acc, val_f1, _, _ = run_epoch(model, val_loader, criterion, optimizer, device, train=False)
        print(f"Epoch {epoch:03d}: train_loss={train_loss:.4f} train_acc={train_acc:.3f} train_f1={train_f1:.3f} val_loss={val_loss:.4f} val_acc={val_acc:.3f} val_f1={val_f1:.3f}")
        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            torch.save({"model_state_dict": model.state_dict(), "labels": LABELS}, args.output_dir / "best_model.pt")

    checkpoint = torch.load(args.output_dir / "best_model.pt", map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    _, test_acc, test_f1, y_true, y_pred = run_epoch(model, test_loader, criterion, optimizer, device, train=False)
    report = classification_report(y_true, y_pred, target_names=LABELS, zero_division=0)
    print(f"Test accuracy: {test_acc:.3f}")
    print(f"Test macro F1: {test_f1:.3f}")
    print(report)
    (args.output_dir / "test_classification_report.txt").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
