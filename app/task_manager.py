import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict
from enum import Enum

# Configure logger
logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"


class TaskManager:
    """Task queue manager for RPA tasks"""
    
    _instance: Optional['TaskManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        # Get app directory
        self.app_dir = Path(__file__).parent
        self.task_mapping_file = self.app_dir / "task_mapping.json"
        self.task_files_dir = self.app_dir / "task_files"
        self.logs_dir = self.app_dir / "logs"
        
        # Ensure directories exist
        self.task_files_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        
        # Load task mapping
        self.task_mapping: Dict = {}
        self.load_task_mapping()
        
        # Task queue and current task
        self.queue: List[str] = []
        self.current_task: Optional[str] = None
        self.status: TaskStatus = TaskStatus.IDLE
        
        # Thread lock for thread safety
        self._lock = threading.Lock()
        
        # Start background monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_tasks, daemon=True)
        self._monitor_thread.start()
        logger.info("Background task monitor thread started")
    
    def load_task_mapping(self):
        """Load task mapping from JSON file"""
        if self.task_mapping_file.exists():
            with open(self.task_mapping_file, 'r', encoding='utf-8') as f:
                self.task_mapping = json.load(f)
        else:
            self.task_mapping = {}
    
    def add_tasks(self, task_ids: List[str]) -> int:
        """
        Add tasks to the queue
        
        Args:
            task_ids: List of task IDs to add
            
        Returns:
            Number of tasks added
        """
        valid_tasks = []
        self.load_task_mapping()
        for task_id in task_ids:
            if task_id in self.task_mapping:
                valid_tasks.append(task_id)
            else:
                logger.warning(f"Task ID '{task_id}' not found in task_mapping")
        
        with self._lock:
            self.queue.extend(valid_tasks)
        if valid_tasks:
            logger.info(f"Added {len(valid_tasks)} task(s) to queue: {valid_tasks}")
        return len(valid_tasks)
    
    def start_next_task(self) -> bool:
        """
        Start the next task in the queue
        
        Returns:
            True if a task was started, False if queue is empty or task is already running
        """
        with self._lock:
            # Don't start new task if one is already running
            if self.status == TaskStatus.RUNNING:
                return False
            
            if not self.queue:
                return False
            
            # Pop next task
            task_id = self.queue.pop(0)
            self.current_task = task_id
            self.status = TaskStatus.RUNNING
        
        # Get task config from mapping
        if task_id not in self.task_mapping:
            logger.error(f"Task ID '{task_id}' not found in task_mapping")
            with self._lock:
                self.current_task = None
                self.status = TaskStatus.IDLE
            return False
        
        # Check and delete existing log file if it exists
        log_filename = f"{task_id}.txt"
        log_file_path = self.logs_dir / log_filename
        if log_file_path.exists():
            try:
                log_file_path.unlink()
                logger.info(f"Deleted existing log file for task '{task_id}': {log_filename}")
            except Exception as e:
                logger.error(f"Error deleting existing log file for task '{task_id}': {str(e)}")
        
        # Create trigger file for RPA
        trigger_filename = f"trigger.{task_id}"
        trigger_file_path = self.task_files_dir / trigger_filename
        trigger_file_path.touch()
        
        logger.info(f"Started task '{task_id}', created trigger file: {trigger_filename}")
        return True
    
    def check_if_current_task_done(self) -> bool:
        """
        Check if current task is done by checking log file
        
        Returns:
            True if task is done, False otherwise
        """
        with self._lock:
            current_task = self.current_task
        
        if not current_task:
            return False
        
        # Check if log file last line contains "脚本执行成功"
        log_filename = f"{current_task}.txt"
        log_file_path = self.logs_dir / log_filename
        if log_file_path.exists():
            try:
                with open(log_file_path, 'r', encoding='utf-8') as log_file:
                    lines = log_file.readlines()
                    if lines and "脚本执行成功" in lines[-1]:
                        logger.info(f"Task '{current_task}' completed (found '脚本执行成功' in log)")
                        return True
            except Exception as e:
                logger.error(f"Error reading log file for task '{current_task}': {str(e)}")
        return False
    
    def get_status(self) -> Dict:
        """
        Get current task status
        
        Returns:
            Dictionary with current_task, status, and log content
        """
        with self._lock:
            current_task = self.current_task
            status = self.status.value
        
        result = {
            "current_task": current_task,
            "status": status
        }
        
        # Read log file if exists
        log_content = ""
        if current_task:
            # Read log file from logs/{taskname}.txt
            log_filename = f"{current_task}.txt"
            log_file_path = self.logs_dir / log_filename
            
            if log_file_path.exists():
                try:
                    with open(log_file_path, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                except Exception as e:
                    log_content = f"Error reading log file: {str(e)}"
        
        result["log"] = log_content
        return result
    
    def finish_current_task(self):
        """
        Finish current task and prepare for next task
        This should be called when task is done
        """
        with self._lock:
            if not self.current_task:
                return
            
            # Get current task before resetting
            task_id = self.current_task
            
            # Reset current task state
            self.current_task = None
            self.status = TaskStatus.IDLE
        
        # Delete trigger file for completed task
        trigger_filename = f"trigger.{task_id}"
        trigger_file_path = self.task_files_dir / trigger_filename
        if trigger_file_path.exists():
            try:
                trigger_file_path.unlink()
                logger.info(f"Deleted trigger file for completed task '{task_id}': {trigger_filename}")
            except Exception as e:
                logger.error(f"Error deleting trigger file for task '{task_id}': {str(e)}")
        else:
            logger.warning(f"Trigger file not found for task '{task_id}': {trigger_filename}")
    
    def get_available_tasks(self) -> List[Dict]:
        """
        Get list of available tasks
        
        Returns:
            List of task dictionaries with id and description
        """
        tasks = []
        self.load_task_mapping()
        for task_id, task_config in self.task_mapping.items():
            tasks.append({
                "id": task_id,
                "description": task_config.get("description", "")
            })
        return tasks
    
    def _monitor_tasks(self):
        """
        Background thread to monitor task completion
        Checks every 10 seconds if current task is done
        """
        logger.debug("Task monitor thread started monitoring")
        while True:
            try:
                time.sleep(10)  # Check every 10 seconds
                
                with self._lock:
                    status = self.status
                    current_task = self.current_task
                
                # Only check if there's a running task
                if status == TaskStatus.RUNNING and current_task:
                    logger.debug(f"Checking completion status for task '{current_task}'")
                    if self.check_if_current_task_done():
                        # Task is done, finish current task and start next task
                        logger.info(f"Task '{current_task}' is done, finishing and starting next task")
                        self.finish_current_task()
                        next_started = self.start_next_task()
                        if not next_started:
                            logger.info("No more tasks in queue, waiting for new tasks")
            except Exception as e:
                logger.error(f"Error in monitor thread: {str(e)}", exc_info=True)

