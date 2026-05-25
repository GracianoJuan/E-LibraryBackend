"""
Alembic Migration Helper Script
This script simplifies running Alembic migrations for the E-Library project.

Usage:
    python migration_runner.py upgrade     # Apply all pending migrations
    python migration_runner.py downgrade -1 # Rollback last migration
    python migration_runner.py current      # Show current revision
    python migration_runner.py history      # Show migration history
    python migration_runner.py revision -m "message" # Create new migration
"""

import os
import sys
import asyncio
from pathlib import Path

# Fix for Windows async event loop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent))

from alembic.config import Config
from alembic import command

def get_alembic_config():
    """Get Alembic configuration"""
    backend_root = Path(__file__).resolve().parent
    config = Config(str(backend_root / "alembic.ini"))
    config.set_main_option("script_location", str(backend_root / "migrations"))
    config.set_main_option("prepend_sys_path", str(backend_root))
    return config

def upgrade(revision="head"):
    """Upgrade to a specific revision (default: head)"""
    print(f"Upgrading to {revision}...")
    config = get_alembic_config()
    try:
        command.upgrade(config, revision)
        print("✓ Upgrade completed successfully!")
    except Exception as e:
        print(f"✗ Upgrade failed: {e}")
        sys.exit(1)

def downgrade(revision="-1"):
    """Downgrade by N revisions (default: -1)"""
    print(f"Downgrading by {revision}...")
    config = get_alembic_config()
    try:
        command.downgrade(config, revision)
        print("✓ Downgrade completed successfully!")
    except Exception as e:
        print(f"✗ Downgrade failed: {e}")
        sys.exit(1)

def current():
    """Show current database revision"""
    config = get_alembic_config()
    try:
        command.current(config)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

def history():
    """Show migration history"""
    config = get_alembic_config()
    try:
        command.history(config)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)

def revision(message, autogenerate=False):
    """Create a new migration"""
    print(f"Creating new migration: {message}...")
    config = get_alembic_config()
    try:
        command.revision(config, message=message, autogenerate=autogenerate)
        print("✓ Migration created successfully!")
    except Exception as e:
        print(f"✗ Migration creation failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command_name = sys.argv[1].lower()
    
    if command_name == "upgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        upgrade(revision)
    elif command_name == "downgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "-1"
        downgrade(revision)
    elif command_name == "current":
        current()
    elif command_name == "history":
        history()
    elif command_name == "revision":
        if len(sys.argv) < 4 or sys.argv[2] != "-m":
            print("Usage: python migration_runner.py revision -m 'migration message'")
            sys.exit(1)
        message = " ".join(sys.argv[3:])
        autogenerate = "--autogenerate" in sys.argv
        revision(message, autogenerate=autogenerate)
    else:
        print(f"Unknown command: {command_name}")
        print(__doc__)
        sys.exit(1)
