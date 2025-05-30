"""
Strategy module for Coinbase International Exchange HFT Bot.
Implements channel breakout strategy with order book imbalance ML factor.
"""
import logging
import time
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler
import joblib
import os

import config
from data_handler import DataHandler

logger = logging.getLogger("coinbase_hft.strategy")

class ChannelBreakoutStrategy:
    """
    Channel breakout strategy with order book imbalance ML factor.
    Uses Donchian channels to detect breakouts and ML to filter signals.
    """
    def __init__(self, symbol: str, data_handler: DataHandler):
        """
        Initialize the strategy.
        
        Args:
            symbol: Trading symbol (e.g., 'BTC-USD')
            data_handler: Data handler instance
        """
        self.symbol = symbol
        self.data_handler = data_handler
        
        self.channel_window = config.CHANNEL_WINDOW  # seconds
        self.obi_threshold = config.OBI_THRESHOLD
        
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = [
            "obi", "volatility", "trade_imbalance", 
            "vwap_distance", "hawkes_intensity", "channel_position"
        ]
        
        self.X_train = []
        self.y_train = []
        
        self.last_signal_time = 0
        self.signal_cooldown = 10  # seconds
        self.position = 0  # -1 (short), 0 (flat), 1 (long)
        
        self._initialize_model()
    
    def _initialize_model(self) -> None:
        """Initialize the ML model."""
        try:
            model_path = f"models/{self.symbol.replace('-', '_')}_model.joblib"
            if os.path.exists(model_path):
                self.model = joblib.load(model_path)
                logger.info(f"Loaded existing model from {model_path}")
            else:
                self.model = SGDClassifier(
                    loss="log_loss",
                    penalty="l2",
                    alpha=0.0001,
                    max_iter=1000,
                    tol=1e-3,
                    random_state=42,
                    warm_start=True,
                )
                logger.info("Created new model")
                
        except Exception as e:
            logger.error(f"Error initializing model: {e}")
            self.model = SGDClassifier(
                loss="log_loss",
                penalty="l2",
                alpha=0.0001,
                max_iter=1000,
                tol=1e-3,
                random_state=42,
                warm_start=True,
            )
    
    def save_model(self) -> None:
        """Save the ML model to disk."""
        try:
            os.makedirs("models", exist_ok=True)
            
            model_path = f"models/{self.symbol.replace('-', '_')}_model.joblib"
            joblib.dump(self.model, model_path)
            logger.info(f"Saved model to {model_path}")
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    def update_model(self, features: Dict[str, float], label: int) -> None:
        """
        Update the ML model with new training data.
        
        Args:
            features: Feature dictionary
            label: Target label (1 for up, -1 for down, 0 for no movement)
        """
        try:
            X = [features[name] for name in self.feature_names]
            
            self.X_train.append(X)
            self.y_train.append(label)
            
            max_samples = 10000
            if len(self.X_train) > max_samples:
                self.X_train = self.X_train[-max_samples:]
                self.y_train = self.y_train[-max_samples:]
            
            if len(self.X_train) >= 100:
                X_scaled = self.scaler.fit_transform(self.X_train)
                
                self.model.fit(X_scaled, self.y_train)
                
                if len(self.X_train) % 1000 == 0:
                    self.save_model()
                
                logger.debug(f"Updated model with {len(self.X_train)} samples")
                
        except Exception as e:
            logger.error(f"Error updating model: {e}")
    
    def predict_direction(self, features: Dict[str, float]) -> Tuple[int, float]:
        """
        Predict price movement direction using ML model.
        
        Args:
            features: Feature dictionary
            
        Returns:
            Tuple[int, float]: (direction, probability)
                direction: 1 for up, -1 for down, 0 for no movement
                probability: Confidence in prediction
        """
        try:
            if self.model is None or len(self.X_train) < 100:
                obi = features.get("obi", 0)
                if abs(obi) > self.obi_threshold:
                    direction = 1 if obi > 0 else -1
                    return direction, abs(obi)
                return 0, 0.0
            
            X = [features[name] for name in self.feature_names]
            
            X_scaled = self.scaler.transform([X])
            
            direction = self.model.predict(X_scaled)[0]
            
            proba = self.model.predict_proba(X_scaled)[0]
            probability = proba[1] if direction == 1 else proba[0]
            
            return direction, probability
            
        except Exception as e:
            logger.error(f"Error predicting direction: {e}")
            return 0, 0.0
    
    def generate_signal(self) -> Tuple[str, float, Dict[str, Any]]:
        """
        Generate trading signal.
        
        Returns:
            Tuple[str, float, Dict[str, Any]]: (signal, price, metadata)
                signal: 'BUY', 'SELL', or 'NONE'
                price: Price to trade at
                metadata: Additional signal information
        """
        try:
            current_time = time.time()
            if current_time - self.last_signal_time < self.signal_cooldown:
                return "NONE", 0.0, {}
            
            features = self.data_handler.get_features(self.symbol)
            if not features:
                return "NONE", 0.0, {}
            
            current_price = features.get("mid_price", 0)
            if current_price <= 0:
                return "NONE", 0.0, {}
            
            is_breakout, breakout_direction = self.data_handler.is_breakout(self.symbol)
            
            if not is_breakout:
                return "NONE", 0.0, {"reason": "no_breakout"}
            
            ml_direction, ml_probability = self.predict_direction(features)
            
            if breakout_direction == "up" and ml_direction > 0:
                if self.position <= 0:  # Not already long
                    self.last_signal_time = current_time
                    self.position = 1
                    return "BUY", current_price, {
                        "reason": "breakout_up_ml_confirmed",
                        "probability": ml_probability,
                        "features": features
                    }
            
            elif breakout_direction == "down" and ml_direction < 0:
                if self.position >= 0:  # Not already short
                    self.last_signal_time = current_time
                    self.position = -1
                    return "SELL", current_price, {
                        "reason": "breakout_down_ml_confirmed",
                        "probability": ml_probability,
                        "features": features
                    }
            
            return "NONE", 0.0, {
                "reason": "signals_conflict",
                "breakout_direction": breakout_direction,
                "ml_direction": ml_direction,
                "ml_probability": ml_probability
            }
            
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return "NONE", 0.0, {"error": str(e)}
    
    def update_position(self, position: int) -> None:
        """
        Update current position.
        
        Args:
            position: Current position (-1 for short, 0 for flat, 1 for long)
        """
        self.position = position
    
    def should_close_position(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if current position should be closed.
        
        Returns:
            Tuple[bool, Dict[str, Any]]: (should_close, metadata)
                should_close: True if position should be closed
                metadata: Additional information
        """
        try:
            if self.position == 0:
                return False, {"reason": "no_position"}
            
            features = self.data_handler.get_features(self.symbol)
            if not features:
                return False, {"reason": "no_features"}
            
            ml_direction, ml_probability = self.predict_direction(features)
            
            if self.position > 0 and ml_direction < 0 and ml_probability > 0.7:
                return True, {
                    "reason": "reversal_signal",
                    "position": "long",
                    "ml_direction": ml_direction,
                    "ml_probability": ml_probability
                }
            
            if self.position < 0 and ml_direction > 0 and ml_probability > 0.7:
                return True, {
                    "reason": "reversal_signal",
                    "position": "short",
                    "ml_direction": ml_direction,
                    "ml_probability": ml_probability
                }
            
            channel_position = features.get("channel_position", 0.5)
            
            if self.position > 0 and channel_position < 0.4:
                return True, {
                    "reason": "channel_exit",
                    "position": "long",
                    "channel_position": channel_position
                }
            
            if self.position < 0 and channel_position > 0.6:
                return True, {
                    "reason": "channel_exit",
                    "position": "short",
                    "channel_position": channel_position
                }
            
            return False, {"reason": "hold_position"}
            
        except Exception as e:
            logger.error(f"Error checking position close: {e}")
            return False, {"error": str(e)}
