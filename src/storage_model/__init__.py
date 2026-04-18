"""
Storage Model
=============
An educational gas storage optimization analogy using exchange-traded assets.
Mirrors injection/withdrawal decisions subject to physical constraints.
"""

from src.storage_model.config import StorageConfig, GLD_PRESET, CORN_PRESET
from src.storage_model.data_loader import StorageDataLoader
from src.storage_model.signals import StorageSignalEngine
from src.storage_model.engine import StorageEngine, StorageBacktestResults
