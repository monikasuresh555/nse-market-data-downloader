"""Configuration package for NSE Market Data Downloader."""

from config.datasets import DATASET_REGISTRY, DatasetConfig, get_all_dataset_names, get_dataset_config

__all__ = [
    "DatasetConfig",
    "DATASET_REGISTRY",
    "get_dataset_config",
    "get_all_dataset_names",
]
