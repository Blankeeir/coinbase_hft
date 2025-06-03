#!/usr/bin/env python
"""
Patch script for Coinbase International Exchange FIX client.
This script applies the necessary fixes to the fix_client.py file.
"""
import os
import re
import shutil
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("fix_client_patch")

def backup_file(file_path):
    """Create a backup of the file."""
    backup_path = f"{file_path}.bak"
    shutil.copy2(file_path, backup_path)
    logger.info(f"Created backup at {backup_path}")
    return backup_path

def patch_connect_method(file_path):
    """Patch the connect method to pass SSL context."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    connect_pattern = r'async def connect\(self, max_attempts: int = 3\) -> bool:'
    if not re.search(connect_pattern, content):
        logger.error("Could not find connect method in fix_client.py")
        return False
    
    connect_call_pattern = r'await self\.connection\.connect\(\)'
    if not re.search(connect_call_pattern, content):
        logger.error("Could not find connection.connect() call in fix_client.py")
        return False
    
    patched_content = re.sub(
        connect_call_pattern,
        'await self.connection.connect(ssl=self.ssl_context)',
        content
    )
    
    with open(file_path, 'w') as f:
        f.write(patched_content)
    
    logger.info("Patched connect method to pass SSL context")
    return True

def patch_wait_for_network(file_path):
    """Add _wait_for_network_connection method if it doesn't exist."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    if '_wait_for_network_connection' in content:
        logger.info("_wait_for_network_connection method already exists")
        return True
    
    connect_pattern = r'async def connect\(self, max_attempts: int = 3\) -> bool:'
    match = re.search(connect_pattern, content)
    if not match:
        logger.error("Could not find connect method in fix_client.py")
        return False
    
    wait_method = '''
    async def _wait_for_network_connection(self, timeout: int = 10) -> bool:
        """Wait for network connection to be established."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.connection.connection_state == ConnectionState.NETWORK_CONN_ESTABLISHED:
                return True
            await asyncio.sleep(0.1)
        return False
    
'''
    
    insert_pos = match.start()
    patched_content = content[:insert_pos] + wait_method + content[insert_pos:]
    
    with open(file_path, 'w') as f:
        f.write(patched_content)
    
    logger.info("Added _wait_for_network_connection method")
    return True

def patch_connection_state_check(file_path):
    """Update the connection state check after connect."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    state_check_pattern = r'if self\.connection\.connection_state != ConnectionState\.NETWORK_CONN_ESTABLISHED:'
    if not re.search(state_check_pattern, content):
        logger.warning("Could not find connection state check in fix_client.py")
        return True  # Not critical
    
    patched_content = re.sub(
        state_check_pattern,
        'if not await self._wait_for_network_connection():',
        content
    )
    
    with open(file_path, 'w') as f:
        f.write(patched_content)
    
    logger.info("Patched connection state check to use _wait_for_network_connection")
    return True

def patch_imports(file_path):
    """Ensure all necessary imports are present."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    if 'from asyncfix.connection import ConnectionState' not in content:
        import_pattern = r'from asyncfix\.connection import AsyncFIXConnection'
        if not re.search(import_pattern, content):
            logger.error("Could not find AsyncFIXConnection import in fix_client.py")
            return False
        
        patched_content = re.sub(
            import_pattern,
            'from asyncfix.connection import AsyncFIXConnection, ConnectionState',
            content
        )
        
        with open(file_path, 'w') as f:
            f.write(patched_content)
        
        logger.info("Added ConnectionState import")
    
    return True

def main():
    """Apply all patches to fix_client.py."""
    fix_client_path = os.path.join(os.getcwd(), 'fix_client.py')
    
    if not os.path.exists(fix_client_path):
        logger.error(f"fix_client.py not found at {fix_client_path}")
        return False
    
    logger.info(f"Patching {fix_client_path}")
    
    backup_path = backup_file(fix_client_path)
    
    success = True
    success = success and patch_imports(fix_client_path)
    success = success and patch_wait_for_network(fix_client_path)
    success = success and patch_connect_method(fix_client_path)
    success = success and patch_connection_state_check(fix_client_path)
    
    if success:
        logger.info("Successfully patched fix_client.py")
        logger.info(f"Backup saved at {backup_path}")
    else:
        logger.error("Failed to patch fix_client.py")
        logger.info(f"Restoring from backup {backup_path}")
        shutil.copy2(backup_path, fix_client_path)
    
    return success

if __name__ == "__main__":
    main()
