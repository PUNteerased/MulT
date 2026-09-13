"""
Kernel Density Estimation (KDE) Liquidity Zone Detector.
Runs on CPU using SciPy gaussian_kde.
Extracts institutional liquidity pools by clustering pivot high/low clusters and volume.
"""
from typing import List, Dict, Any, Tuple
import numpy as np
import pandas as pd
from scipy.stats import gaussian_kde
from scipy.signal import find_peaks
from loguru import logger

class KDELiquidityDetector:
    """Finds high-volume institutional liquidity clusters from price pivots."""

    @staticmethod
    def extract_pivots(df: pd.DataFrame, window: int = 3) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Extract swing highs and swing lows along with their respective volumes.
        """
        highs = df['high'].values
        lows = df['low'].values
        volumes = df['tick_volume'].values

        pivot_prices = []
        pivot_weights = []
        pivot_types = []  # 1 for high, -1 for low

        n = len(df)
        for i in range(window, n - window):
            # Swing High check
            if highs[i] == np.max(highs[i - window:i + window + 1]):
                pivot_prices.append(highs[i])
                pivot_weights.append(volumes[i])
                pivot_types.append(1)

            # Swing Low check
            if lows[i] == np.min(lows[i - window:i + window + 1]):
                pivot_prices.append(lows[i])
                pivot_weights.append(volumes[i])
                pivot_types.append(-1)

        return (
            np.array(pivot_prices, dtype=np.float64),
            np.array(pivot_weights, dtype=np.float64),
            np.array(pivot_types, dtype=np.int32)
        )

    @classmethod
    def find_liquidity_zones(
        cls,
        df: pd.DataFrame,
        current_price: float,
        num_grid_points: int = 500,
        bandwidth: float = 0.2
    ) -> List[Dict[str, Any]]:
        """
        Fit KDE over pivot prices and find prominent support & resistance zones.
        """
        if len(df) < 20:
            return []

        pivots, weights, types = cls.extract_pivots(df, window=2)
        if len(pivots) < 2:
            return []

        # Normalize weights
        norm_weights = weights / (np.sum(weights) + 1e-9)

        # Fit Gaussian KDE
        try:
            kde = gaussian_kde(pivots, weights=norm_weights, bw_method=bandwidth)
        except Exception as e:
            logger.warning(f"[KDE] Error fitting gaussian_kde: {e}")
            return []

        price_min = np.min(pivots) * 0.999
        price_max = np.max(pivots) * 1.001
        x_grid = np.linspace(price_min, price_max, num_grid_points)
        density = kde(x_grid)

        # Find local peaks of density
        peaks, properties = find_peaks(density, height=np.mean(density) * 0.5, distance=5)
        if len(peaks) == 0:
            peaks = [np.argmax(density)]
        zones = []

        for p_idx in peaks:
            peak_price = x_grid[p_idx]
            peak_density = density[p_idx]
            # Determine whether zone is below or above current price
            zone_type = "SUPPORT" if peak_price < current_price else "RESISTANCE"
            direction = "BUY" if zone_type == "SUPPORT" else "SELL"

            # Compute estimated zone width (+/- 0.05% of price or grid step)
            zone_width = peak_price * 0.0008

            zones.append({
                "center_price": float(peak_price),
                "lower_bound": float(peak_price - zone_width),
                "upper_bound": float(peak_price + zone_width),
                "type": zone_type,
                "direction": direction,
                "density_score": float(peak_density),
                "dist_to_price": abs(peak_price - current_price)
            })

        # Sort zones by distance to current price (closest first)
        zones.sort(key=lambda z: z["dist_to_price"])
        return zones
