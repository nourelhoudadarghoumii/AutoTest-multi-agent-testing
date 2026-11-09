import numpy as np
import pandas as pd
from collections import defaultdict as dd
import math

class DataProcessor:
    """Base data processor."""
    def __init__(self, data: list):
        self.data = data
        
    def clean(self):
        """Clean the data."""
        pass
        
    def filter(self):
        """Filter the data."""
        pass

class AdvancedProcessor(DataProcessor):
    """Advanced data processor."""
    def normalize(self):
        """Normalize data."""
        pass
        
    def summarize(self):
        """Summarize data."""
        pass

def process_dataset(data: list, config: dict) -> dict:
    """Process dataset with nested control flow."""
    result = {}
    if data:
        for item in data:
            if isinstance(item, dict):
                for k, v in item.items():
                    if k in config:
                        if config[k] == "active":
                            result[k] = v * 2
                        elif config[k] == "inactive":
                            continue
                        else:
                            result[k] = v
            elif isinstance(item, list):
                for i in item:
                    if i > 0:
                        result["pos"] = result.get("pos", 0) + i
    return result

def aggregate_metrics(records: list) -> dict:
    """Aggregate metrics with branching."""
    summary = {"total": 0, "avg": 0, "max": 0, "min": 0}
    if not records:
        return summary
        
    for r in records:
        if r > summary["max"]:
            summary["max"] = r
        if r < summary["min"] or summary["min"] == 0:
            summary["min"] = r
        if r > 0:
            summary["total"] += r
            
    if len(records) > 0:
        summary["avg"] = summary["total"] / len(records)
        if summary["avg"] > 100:
            summary["status"] = "high"
        elif summary["avg"] > 50:
            summary["status"] = "medium"
        else:
            summary["status"] = "low"
            
    return summary
