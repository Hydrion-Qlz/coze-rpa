import json
from pathlib import Path
from typing import Optional, List, Dict
from enum import Enum


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
        for task_id in task_ids:
            if task_id in self.task_mapping:
                valid_tasks.append(task_id)
            else:
                # Log warning for invalid task_id
                print(f"Warning: Task ID '{task_id}' not found in task_mapping")
        
        self.queue.extend(valid_tasks)
        return len(valid_tasks)
    
    def start_next_task(self) -> bool:
        """
        Start the next task in the queue
        
        Returns:
            True if a task was started, False if queue is empty
        """
        if not self.queue:
            return False
        
        # Pop next task
        task_id = self.queue.pop(0)
        self.current_task = task_id
        self.status = TaskStatus.RUNNING
        
        # Get task config from mapping
        if task_id not in self.task_mapping:
            print(f"Error: Task ID '{task_id}' not found in task_mapping")
            self.current_task = None
            self.status = TaskStatus.IDLE
            return False
        
        # Create trigger file for RPA
        trigger_filename = f"trigger.{task_id}"
        trigger_file_path = self.task_files_dir / trigger_filename
        trigger_file_path.touch()
        
        print(f"Started task '{task_id}', created trigger file: {trigger_filename}")
        return True
    
    def check_if_current_task_done(self) -> bool:
        """
        Check if current task is done by checking if trigger file is removed
        
        Returns:
            True if task is done, False otherwise
        """
        if not self.current_task:
            return False
        
        # Check if trigger file still exists
        trigger_filename = f"trigger.{self.current_task}"
        trigger_file_path = self.task_files_dir / trigger_filename
        
        # 如果日志文件最后一行包含“结束”，则认为任务结束
        log_filename = f"{self.current_task}.txt"
        log_file_path = self.logs_dir / log_filename
        if log_file_path.exists():
            try:
                with open(log_file_path, 'r', encoding='utf-8') as log_file:
                    lines = log_file.readlines()
                    if lines and "结束执行脚本" in lines[-1]:
                        return True
            except Exception as e:
                print(f"Error reading log file: {str(e)}")
        return False
    
    def get_status(self) -> Dict:
        """
        Get current task status
        
        Returns:
            Dictionary with current_task, status, and log content
        """
        # Check if task is done
        if self.status == TaskStatus.RUNNING:
            self.check_if_current_task_done()
        
        result = {
            "current_task": self.current_task,
            "status": self.status.value
        }
        
        # Read log file if exists
        log_content = ""
        if self.current_task:
            # Read log file from logs/{taskname}.txt
            log_filename = f"{self.current_task}.txt"
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
        if not self.current_task:
            return
        
        # Reset current task state
        self.current_task = None
        self.status = TaskStatus.IDLE
    
    def get_available_tasks(self) -> List[Dict]:
        """
        Get list of available tasks
        
        Returns:
            List of task dictionaries with id and description
        """
        tasks = []
        for task_id, task_config in self.task_mapping.items():
            tasks.append({
                "id": task_id,
                "description": task_config.get("description", "")
            })
        return tasks

