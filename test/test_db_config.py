import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.db_sqlite import sqlite_manager
from loguru import logger

def test_config_storage():
    logger.info("Starting config storage test...")
    
    # Test Data
    test_configs = {
        "llm_env": "cloud",
        "llm_api_key": "test_sk_12345",
        "llm_model": "deepseek-chat"
    }
    
    # 1. Save Configs
    logger.info(f"Saving configs: {test_configs}")
    success = sqlite_manager.save_configs(test_configs)
    assert success, "Failed to save configs to database"
    
    # 2. Get Configs
    logger.info("Fetching saved configs...")
    fetched_configs = sqlite_manager.get_all_configs()
    logger.info(f"Fetched configs: {fetched_configs}")
    
    # 3. Assertions
    assert fetched_configs.get("llm_api_key") == "test_sk_12345", "API key mismatch"
    assert fetched_configs.get("llm_env") == "cloud", "Env mismatch"
    assert fetched_configs.get("llm_model") == "deepseek-chat", "Model mismatch"
    
    logger.info("All tests passed successfully! 🎉")

if __name__ == "__main__":
    test_config_storage()
