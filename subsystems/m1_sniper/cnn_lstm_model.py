"""
PyTorch 1D-CNN + LSTM Neural Network for M1 Sniper Pattern Classification.
Combines 1D temporal convolutions (candlestick shape extractor) with LSTM
(sequence momentum) to classify high-probability reversal sweeps.
"""
import os
import torch
import torch.nn as nn
from typing import Optional
import numpy as np
from loguru import logger
from config.settings import MODELS_DIR, TORCH_DEVICE

class SniperCNNLSTM(nn.Module):
    """Hybrid 1D-CNN + LSTM classifier."""
    def __init__(self, in_features: int = 5, seq_len: int = 60):
        super().__init__()
        # 1D-CNN blocks over time series (features as channels)
        self.conv_block = nn.Sequential(
            nn.Conv1d(in_channels=in_features, out_channels=32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Conv1d(in_channels=32, out_channels=64, kernel_size=3, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU()
        )
        # LSTM layer
        self.lstm = nn.LSTM(
            input_size=64,
            hidden_size=64,
            num_layers=1,
            batch_first=True
        )
        # Dense classification head
        self.classifier = nn.Sequential(
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x shape: (batch_size, seq_len, in_features)
        # Transpose for Conv1d: (batch_size, in_features, seq_len)
        x_conv = x.transpose(1, 2)
        feat = self.conv_block(x_conv)
        # Transpose back for LSTM: (batch_size, seq_len, 64)
        feat = feat.transpose(1, 2)
        lstm_out, _ = self.lstm(feat)
        # Take the output of the final time step
        last_step = lstm_out[:, -1, :]
        prob = self.classifier(last_step)
        return prob

class SniperModelEngine:
    """Manages inference, weights loading, and VRAM containment for SniperCNNLSTM."""
    def __init__(self, device: str = TORCH_DEVICE):
        self.device = device
        self.model = SniperCNNLSTM().to(self.device)
        self.weights_path = MODELS_DIR / "m1_sniper_cnn_lstm.pt"
        self._load_or_initialize_weights()

    def _load_or_initialize_weights(self):
        if self.weights_path.exists():
            try:
                self.model.load_state_dict(torch.load(self.weights_path, map_location=self.device))
                logger.info(f"[SniperModelEngine] Loaded weights from {self.weights_path}")
            except Exception as e:
                logger.warning(f"[SniperModelEngine] Could not load weights: {e}, using fresh weights.")
        else:
            # Save initialized weights
            try:
                torch.save(self.model.state_dict(), self.weights_path)
                logger.info(f"[SniperModelEngine] Initialized and saved default weights to {self.weights_path}")
            except Exception as e:
                logger.warning(f"[SniperModelEngine] Could not save default weights: {e}")
        self.model.eval()

    def predict_reversal_confidence(self, ohlcv_60: np.ndarray) -> float:
        """
        Input: numpy array of shape (60, 5) with columns [open, high, low, close, volume]
        Output: confidence score 0.0 - 1.0
        """
        if ohlcv_60.shape[0] < 60:
            return 0.50

        # Normalize relative to latest bar
        data = ohlcv_60.copy()
        base_price = data[-1, 3]  # close
        mean_vol = np.mean(data[:, 4]) + 1e-6

        data[:, :4] = (data[:, :4] - base_price) / (np.std(data[:, :4]) + 1e-6)
        data[:, 4] = data[:, 4] / mean_vol

        tensor_in = torch.tensor(data, dtype=torch.float32, device=self.device).unsqueeze(0)

        with torch.no_grad():
            score = self.model(tensor_in).item()

        return float(score)
