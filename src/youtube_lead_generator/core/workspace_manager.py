import os
import shutil
import threading
from pathlib import Path

class WorkspaceManager:
    _lock = threading.Lock()
    _active_workspace = "default"
    _base_dir = Path(__file__).parent.parent.parent.parent / "workspaces"

    @classmethod
    def init(cls):
        """Initializes the workspaces directory and migrates the old database if needed."""
        with cls._lock:
            cls._base_dir.mkdir(exist_ok=True)
            
            old_db = Path(__file__).parent.parent.parent.parent / "scraper.db"
            default_db = cls._base_dir / "default.db"
            
            if old_db.exists():
                # Migrate the old DB to the new default workspace
                shutil.move(str(old_db), str(default_db))
                
            # If no default db exists at all, we create a blank one just by setting it active 
            # and the system will init it when get_db_path is called.
            
    @classmethod
    def get_db_path(cls, workspace_name=None) -> Path:
        """Returns the Path to the active workspace's SQLite file, or a specific one."""
        name = workspace_name or cls._active_workspace
        # Sanitize to prevent directory traversal
        name = "".join(c for c in name if c.isalnum() or c in ('_', '-'))
        if not name:
            name = "default"
            
        return cls._base_dir / f"{name}.db"

    @classmethod
    def get_active(cls) -> str:
        """Returns the name of the currently active workspace."""
        return cls._active_workspace

    @classmethod
    def set_active(cls, name: str):
        """Sets the currently active workspace."""
        # Sanitize
        name = "".join(c for c in name if c.isalnum() or c in ('_', '-'))
        if not name:
            raise ValueError("Invalid workspace name")
            
        with cls._lock:
            cls._active_workspace = name

    @classmethod
    def list_workspaces(cls) -> list[str]:
        """Returns a list of all workspace names based on .db files in the directory."""
        if not cls._base_dir.exists():
            return []
            
        workspaces = []
        for file in cls._base_dir.glob("*.db"):
            workspaces.append(file.stem)
            
        if "default" not in workspaces:
            workspaces.append("default")
            
        return sorted(list(set(workspaces)))

    @classmethod
    def create_workspace(cls, name: str):
        """Creates a new workspace by just setting it active, DB will be created on connect."""
        name = "".join(c for c in name if c.isalnum() or c in ('_', '-'))
        if not name:
            raise ValueError("Invalid workspace name")
        
        # We don't actually need to do anything but set it active, 
        # since sqlite3.connect creates the file if it doesn't exist.
        cls.set_active(name)
        
        # Let's ensure the DB schema is initialized for it right away
        # To avoid circular imports, we don't import database.py here.
        # The caller (web.py) can call database.init_db() after creating.
        return name

# Auto-initialize on import
WorkspaceManager.init()
