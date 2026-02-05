"""Train mean reversion model on historical data"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import logging
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from src.models.config import ModelConfig, BacktestConfig
from src.models.data_loader import DataLoader
from src.models.features import FeatureEngineer
from src.models.model import MeanReversionModel
from src.models.backtest import Backtester

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def prepare_data_for_symbol(symbol: str, df: pd.DataFrame, feature_engineer: FeatureEngineer, config: ModelConfig):
    """Prepare features and labels for a single symbol"""
    if len(df) < config.lookback_days * 2:
        return None, None

    # Create features
    features = feature_engineer.create_features(df)

    # Generate labels using ATR-based targets
    labels = feature_engineer.generate_labels(df, use_atr=config.use_atr_targets)

    # Remove rows with insufficient history
    valid_idx = ~features.iloc[:, :20].isnull().any(axis=1)
    features = features[valid_idx]
    labels = labels[valid_idx]

    # Add metadata
    features['Symbol'] = symbol
    features['Date'] = df.loc[valid_idx, 'Date'].values

    return features, labels['label']


def main():
    """Main training pipeline"""
    logger.info("="*80)
    logger.info("MEAN REVERSION MODEL TRAINING PIPELINE")
    logger.info("="*80)

    # Initialize configuration
    config = ModelConfig()
    backtest_config = BacktestConfig()

    # Initialize components
    data_loader = DataLoader()
    feature_engineer = FeatureEngineer(config)
    model = MeanReversionModel(config)
    backtester = Backtester(config)

    # Phase 1: Data Preparation
    logger.info("\n" + "="*60)
    logger.info("PHASE 1: DATA PREPARATION")
    logger.info("="*60)

    # Select high-quality symbols for training (EXCLUDED: HD, XOM, DIS, CSCO, COST, V, WMT, PG)
    # Based on historical analysis, these stocks have <30% mean reversion success rate
    training_symbols = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
        'JPM', 'BAC', 'JNJ', 'MA', 'UNH',
        'NFLX', 'ADBE', 'CRM', 'PYPL', 'INTC', 'AMD',
        'PEP', 'KO', 'NKE', 'MCD', 'CVX'
    ]

    # Filter to available symbols
    available_training_symbols = [s for s in training_symbols if s in data_loader.available_symbols]
    logger.info(f"Using {len(available_training_symbols)} symbols for training")

    # Load and prepare training data
    all_features = []
    all_labels = []
    symbol_data = {}

    for symbol in available_training_symbols:
        logger.info(f"Processing {symbol}...")
        df = data_loader.load_symbol(symbol, start_date="2015-01-01", end_date="2024-01-01")

        if df.empty:
            continue

        features, labels = prepare_data_for_symbol(symbol, df, feature_engineer, config)

        if features is not None and len(features) > 100:
            all_features.append(features)
            all_labels.append(labels)
            symbol_data[symbol] = df
            logger.info(f"  - Added {len(features)} samples, success rate: {labels.mean():.2%}")

    # Combine all data
    X = pd.concat(all_features, ignore_index=True)
    y = pd.concat(all_labels, ignore_index=True)

    # Extract metadata before dropping
    dates = X['Date'].copy()
    symbols = X['Symbol'].copy()
    X = X.drop(['Date', 'Symbol'], axis=1)

    logger.info(f"\nTotal training samples: {len(X)}")
    logger.info(f"Total features: {len(X.columns)}")
    logger.info(f"Overall success rate: {y.mean():.2%}")

    # Phase 2: Model Training
    logger.info("\n" + "="*60)
    logger.info("PHASE 2: MODEL TRAINING")
    logger.info("="*60)

    # Train model with cross-validation
    training_results = model.train(X, y, dates)

    logger.info("\nCross-Validation Results:")
    logger.info(f"  Mean AUC: {training_results['mean_val_auc']:.4f} (+/- {training_results['std_val_auc']:.4f})")
    logger.info(f"  Mean Precision: {training_results['mean_val_precision']:.4f}")
    logger.info(f"  Mean Recall: {training_results['mean_val_recall']:.4f}")

    # Display top features
    top_features = model.get_top_features(15)
    logger.info("\nTop 15 Most Important Features:")
    for idx, row in top_features.iterrows():
        logger.info(f"  {row['feature']:30s}: {row['importance']:.4f}")

    # Save model
    os.makedirs("models", exist_ok=True)
    model.save_model("models/mean_reversion_model.pkl")

    # Phase 3: Backtesting
    logger.info("\n" + "="*60)
    logger.info("PHASE 3: BACKTESTING")
    logger.info("="*60)

    # Prepare backtest data (out-of-sample period)
    backtest_features = []
    backtest_symbols = []
    backtest_dates = []

    logger.info("Preparing backtest data...")
    for symbol in available_training_symbols[:20]:  # Use subset for faster backtesting
        df = data_loader.load_symbol(symbol, start_date="2024-01-01", end_date="2024-12-31")

        if df.empty or len(df) < config.lookback_days * 2:
            continue

        # Create features for backtesting period
        features = feature_engineer.create_features(df)

        # Remove rows with insufficient history
        valid_idx = ~features.iloc[:, :20].isnull().any(axis=1)
        features = features[valid_idx]

        if len(features) > 0:
            backtest_features.append(features)
            backtest_symbols.extend([symbol] * len(features))
            backtest_dates.extend(df.loc[valid_idx, 'Date'].values)

    if backtest_features:
        # Combine backtest data
        X_backtest = pd.concat(backtest_features, ignore_index=True)

        # Create predictions DataFrame
        predictions = pd.DataFrame({
            'date': backtest_dates,
            'symbol': backtest_symbols,
            'confidence': model.predict_proba(X_backtest)
        })

        # Run backtest
        logger.info(f"Running backtest on {len(predictions)} signals...")

        # Reload full data for backtesting
        backtest_market_data = {}
        for symbol in set(backtest_symbols):
            df = data_loader.load_symbol(symbol, start_date="2023-12-01", end_date="2024-12-31")
            if not df.empty:
                backtest_market_data[symbol] = df

        results = backtester.run_backtest(
            predictions=predictions,
            market_data=backtest_market_data,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )

        # Calculate performance metrics
        metrics = results.calculate_metrics(config.initial_capital)

        logger.info("\nBacktest Results (2024):")
        logger.info(f"  Total Trades: {metrics['total_trades']}")
        logger.info(f"  Win Rate: {metrics['win_rate']:.2%}")
        logger.info(f"  Average Return: {metrics['avg_return']:.2%}")
        logger.info(f"  Total Return: {metrics['total_return']:.2%}")
        logger.info(f"  Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
        logger.info(f"  Max Drawdown: {metrics['max_drawdown']:.2%}")
        logger.info(f"  Calmar Ratio: {metrics['calmar_ratio']:.2f}")

        if metrics['total_trades'] > 0:
            logger.info(f"  Avg Winner: {metrics.get('avg_winner', 0):.2%}")
            logger.info(f"  Avg Loser: {metrics.get('avg_loser', 0):.2%}")
            logger.info(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}")

    # Phase 4: Production Integration
    logger.info("\n" + "="*60)
    logger.info("PHASE 4: PRODUCTION INTEGRATION")
    logger.info("="*60)

    # Create production scanner script
    scanner_code = '''"""Production scanner using trained mean reversion model"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

from src.models.config import ModelConfig
from src.models.data_loader import DataLoader
from src.models.features import FeatureEngineer
from src.models.model import MeanReversionModel


def scan_for_opportunities():
    """Scan all symbols for mean reversion opportunities"""

    # Load configuration and model
    config = ModelConfig()
    model = MeanReversionModel(config)
    model.load_model("models/mean_reversion_model.pkl")

    # Initialize components
    data_loader = DataLoader()
    feature_engineer = FeatureEngineer(config)

    # Scan all available symbols
    opportunities = []

    for symbol in data_loader.available_symbols:
        df = data_loader.load_symbol(symbol)

        if df.empty or len(df) < config.lookback_days * 2:
            continue

        # Get latest features
        features = feature_engineer.create_features(df)

        if features.empty:
            continue

        # Get prediction for latest day
        latest_features = features.iloc[[-1]]
        latest_features = latest_features.drop(['Symbol', 'Date'], axis=1, errors='ignore')

        confidence = model.predict_proba(latest_features)[0]

        if confidence >= config.confidence_threshold:
            opportunities.append({
                'Symbol': symbol,
                'Confidence': confidence,
                'Price': df.iloc[-1]['Close'],
                'Volume': df.iloc[-1]['Volume'],
                'RSI_14': latest_features.iloc[0].get('rsi_14', np.nan),
                'Distance_from_20d_low': latest_features.iloc[0].get('dist_from_low_20d', np.nan)
            })

    # Sort by confidence
    opportunities = sorted(opportunities, key=lambda x: x['Confidence'], reverse=True)

    # Display results
    print("\\n" + "="*80)
    print("MEAN REVERSION OPPORTUNITIES")
    print("="*80)
    print(f"\\nFound {len(opportunities)} opportunities above {config.confidence_threshold:.0%} confidence\\n")

    if opportunities:
        df_opps = pd.DataFrame(opportunities)
        print(df_opps.to_string(index=False))

    return opportunities


if __name__ == "__main__":
    opportunities = scan_for_opportunities()
'''

    with open("scripts/scan_mean_reversion.py", "w") as f:
        f.write(scanner_code)

    logger.info("Created production scanner: scripts/scan_mean_reversion.py")

    # Summary
    logger.info("\n" + "="*80)
    logger.info("TRAINING PIPELINE COMPLETE")
    logger.info("="*80)
    logger.info("\nModel Performance Summary:")
    logger.info(f"  - Validation AUC: {training_results['mean_val_auc']:.4f}")
    logger.info(f"  - Backtest Win Rate: {metrics.get('win_rate', 0):.2%}")
    logger.info(f"  - Backtest Sharpe: {metrics.get('sharpe_ratio', 0):.2f}")
    logger.info("\nKey Files Created:")
    logger.info("  - models/mean_reversion_model.pkl (trained model)")
    logger.info("  - scripts/scan_mean_reversion.py (production scanner)")
    logger.info("\nNext Steps:")
    logger.info("  1. Run 'python scripts/scan_mean_reversion.py' to find current opportunities")
    logger.info("  2. Review top features for insights into what drives mean reversion")
    logger.info("  3. Consider adjusting confidence threshold based on risk tolerance")
    logger.info("  4. Monitor live performance and retrain periodically")


if __name__ == "__main__":
    main()