from pathlib import Path
from typing import Dict
from loguru import logger

class MemoryManager:
    """Manages the 3-layer Markdown memory files."""
    
    def __init__(self, data_dir: str = "/app/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.files = {
            "SYSTEM": self.data_dir / "SYSTEM.md",
            "FAMILY": self.data_dir / "FAMILY.md",
            "SNAPSHOT": self.data_dir / "SNAPSHOT.md"
        }
        
        # Ensure files exist, although they should be created by the init script
        for name, path in self.files.items():
            if not path.exists():
                logger.warning(f"Memory file missing {name}. It should have been pre-initialized.")
                path.write_text(f"# {name} Memory\n", encoding="utf-8")

    def read_memory(self, layer: str) -> str:
        """Reads a specific memory layer."""
        if layer not in self.files:
            raise ValueError(f"Unknown memory layer: {layer}")
        try:
            return self.files[layer].read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read {layer}: {e}")
            return ""

    def update_memory(self, layer: str, content: str) -> bool:
        """Overwrites a specific memory layer."""
        if layer not in self.files:
            raise ValueError(f"Unknown memory layer: {layer}")
        try:
            self.files[layer].write_text(content, encoding="utf-8")
            logger.info(f"Updated memory layer: {layer}")
            return True
        except Exception as e:
            logger.error(f"Failed to update {layer}: {e}")
            return False

    def append_to_snapshot(self, snapshot_content: str) -> bool:
        """Appends a new conversation snapshot to the SNAPSHOT.md file."""
        try:
            current_content = self.read_memory("SNAPSHOT")
            new_content = current_content + f"\n\n---\n{snapshot_content}\n"
            return self.update_memory("SNAPSHOT", new_content)
        except Exception as e:
            logger.error(f"Failed to append to SNAPSHOT: {e}")
            return False

    def get_all_context(self) -> Dict[str, str]:
        """Returns the full context to be injected into the LLM system prompt."""
        return {
            "system": self.read_memory("SYSTEM"),
            "family": self.read_memory("FAMILY"),
            "snapshot": self.read_memory("SNAPSHOT")
        }
