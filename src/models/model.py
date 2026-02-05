"""Mean Reversion ML Model"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
import joblib
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
import lightgbm as lgb
try:
    import xgboost as xgb
    HAS_XGB = True
except (ImportError, Exception):
    HAS_XGB = False
    xgb = None
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MeanReversionModel:
    """Machine learning model for mean reversion trading"""

    def __init__(self, config):
        """Initialize model with configuration"""
        self.config = config
        self.model = None
        self.feature_names = None
        self.feature_importance = None
        self.cv_scores = []
        self.training_history = []

    def create_model(self):
        """Create the ML model based on configuration"""
        if self.config.model_type == "lightgbm":
            self.model = lgb.LGBMClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                min_child_samples=self.config.min_child_samples,
                subsample=self.config.subsample,
                colsample_bytree=self.config.colsample_bytree,
                random_state=42,
                n_jobs=-1,
                verbosity=-1
            )
        elif self.config.model_type == "xgboost":
            if not HAS_XGB:
                raise ImportError("XGBoost is not available. Install it with: pip install xgboost, or use lightgbm instead.")
            self.model = xgb.XGBClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                subsample=self.config.subsample,
                colsample_bytree=self.config.colsample_bytree,
                random_state=42,
                n_jobs=-1,
                verbosity=0
            )
        else:
            raise ValueError(f"Unknown model type: {self.config.model_type}")

        logger.info(f"Created {self.config.model_type} model")

    def train(self, X: pd.DataFrame, y: pd.Series, dates: pd.Series = None) -> Dict:
        """Train model with time series cross-validation"""
        logger.info(f"Training model on {len(X)} samples")

        # Store feature names
        self.feature_names = X.columns.tolist()

        # Time series cross-validation
        tscv = TimeSeriesSplit(
            n_splits=self.config.n_splits,
            gap=self.config.gap_days,
            test_size=self.config.test_days
        )

        cv_results = {
            'train_scores': [],
            'val_scores': [],
            'train_precision': [],
            'val_precision': [],
            'train_recall': [],
            'val_recall': []
        }

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            logger.info(f"Training fold {fold + 1}/{self.config.n_splits}")

            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            # Create and train model for this fold
            self.create_model()
            self.model.fit(X_train, y_train)

            # Predictions
            train_pred_proba = self.model.predict_proba(X_train)[:, 1]
            val_pred_proba = self.model.predict_proba(X_val)[:, 1]

            train_pred = (train_pred_proba >= self.config.confidence_threshold).astype(int)
            val_pred = (val_pred_proba >= self.config.confidence_threshold).astype(int)

            # Calculate metrics
            cv_results['train_scores'].append(roc_auc_score(y_train, train_pred_proba))
            cv_results['val_scores'].append(roc_auc_score(y_val, val_pred_proba))
            cv_results['train_precision'].append(precision_score(y_train, train_pred, zero_division=0))
            cv_results['val_precision'].append(precision_score(y_val, val_pred, zero_division=0))
            cv_results['train_recall'].append(recall_score(y_train, train_pred, zero_division=0))
            cv_results['val_recall'].append(recall_score(y_val, val_pred, zero_division=0))

            logger.info(f"Fold {fold + 1} - Val AUC: {cv_results['val_scores'][-1]:.4f}, "
                       f"Val Precision: {cv_results['val_precision'][-1]:.4f}")

        # Train final model on all data
        logger.info("Training final model on all data")
        self.create_model()
        self.model.fit(X, y)

        # Get feature importance
        if self.config.model_type == "lightgbm":
            self.feature_importance = pd.DataFrame({
                'feature': self.feature_names,
                'importance': self.model.feature_importances_
            }).sort_values('importance', ascending=False)
        elif self.config.model_type == "xgboost":
            self.feature_importance = pd.DataFrame({
                'feature': self.feature_names,
                'importance': self.model.feature_importances_
            }).sort_values('importance', ascending=False)

        # Store CV scores
        self.cv_scores = cv_results

        # Calculate summary statistics
        summary = {
            'mean_train_auc': np.mean(cv_results['train_scores']),
            'mean_val_auc': np.mean(cv_results['val_scores']),
            'std_val_auc': np.std(cv_results['val_scores']),
            'mean_val_precision': np.mean(cv_results['val_precision']),
            'mean_val_recall': np.mean(cv_results['val_recall']),
            'total_samples': len(X),
            'positive_samples': y.sum(),
            'positive_rate': y.mean()
        }

        logger.info(f"Training complete - Mean Val AUC: {summary['mean_val_auc']:.4f} "
                   f"(+/- {summary['std_val_auc']:.4f})")

        return summary

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict probability of successful trade"""
        if self.model is None:
            raise ValueError("Model not trained yet")

        # Ensure features match training
        X = X[self.feature_names]

        return self.model.predict_proba(X)[:, 1]

    def predict(self, X: pd.DataFrame, threshold: float = None) -> np.ndarray:
        """Predict binary outcome"""
        if threshold is None:
            threshold = self.config.confidence_threshold

        proba = self.predict_proba(X)
        return (proba >= threshold).astype(int)

    def save_model(self, path: str = None):
        """Save trained model to disk"""
        if path is None:
            path = self.config.model_save_path

        model_data = {
            'model': self.model,
            'feature_names': self.feature_names,
            'feature_importance': self.feature_importance,
            'cv_scores': self.cv_scores,
            'config': self.config
        }

        joblib.dump(model_data, path)
        logger.info(f"Model saved to {path}")

    def load_model(self, path: str = None):
        """Load trained model from disk"""
        if path is None:
            path = self.config.model_save_path

        model_data = joblib.load(path)
        self.model = model_data['model']
        self.feature_names = model_data['feature_names']
        self.feature_importance = model_data['feature_importance']
        self.cv_scores = model_data['cv_scores']
        self.config = model_data['config']

        logger.info(f"Model loaded from {path}")

    def get_top_features(self, n: int = 20) -> pd.DataFrame:
        """Get top n most important features"""
        if self.feature_importance is None:
            raise ValueError("Model not trained yet")

        return self.feature_importance.head(n)