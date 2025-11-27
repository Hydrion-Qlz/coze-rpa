import json
import shutil
from pathlib import Path
from datetime import datetime
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
        
        task_config = self.task_mapping[task_id]
        template_file = task_config.get("file")
        
        if not template_file:
            print(f"Error: No template file specified for task '{task_id}'")
            self.current_task = None
            self.status = TaskStatus.IDLE
            return False
        
        # Get template file path (assume templates are in app directory)
        template_path = self.app_dir / template_file
        
        if not template_path.exists():
            print(f"Warning: Template file '{template_file}' not found, creating empty task file")
            # Create empty task file if template doesn't exist
            task_file_content = json.dumps({"task_id": task_id, "timestamp": datetime.now().isoformat()}, ensure_ascii=False, indent=2)
        else:
            # Read template content
            with open(template_path, 'r', encoding='utf-8') as f:
                task_file_content = f.read()
        
        # Create task file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_filename = f"task_{task_id}_{timestamp}.json"
        task_file_path = self.task_files_dir / task_filename
        
        # Write task file
        with open(task_file_path, 'w', encoding='utf-8') as f:
            f.write(task_file_content)
        
        # Create marker file for RPA to read
        marker_filename = f"task_{task_id}_{timestamp}.ready"
        marker_file_path = self.task_files_dir / marker_filename
        marker_file_path.touch()
        
        print(f"Started task '{task_id}', created files: {task_filename}, {marker_filename}")
        return True
    
    def check_if_current_task_done(self) -> bool:
        """
        Check if current task is done by looking for .done file
        
        Returns:
            True if task is done, False otherwise
        """
        if not self.current_task:
            return False
        
        # Look for .done file in task_files directory
        done_files = list(self.task_files_dir.glob(f"task_{self.current_task}_*.done"))
        return len(done_files) > 0
    
    def get_status(self) -> Dict:
        """
        Get current task status
        
        Returns:
            Dictionary with current_task, status, and log content
        """
        result = {
            "current_task": self.current_task,
            "status": self.status.value
        }
        
        # Read log file if exists
        log_content = ""
        if self.current_task:
            # Look for log file in logs directory
            log_files = list(self.logs_dir.glob(f"{self.current_task}.log"))
            if log_files:
                log_file = log_files[0]
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                except Exception as e:
                    log_content = f"Error reading log file: {str(e)}"
            else:
                # Also check for timestamped log files
                log_files = list(self.logs_dir.glob(f"task_{self.current_task}_*.log"))
                if log_files:
                    # Get the most recent one
                    log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                    log_file = log_files[0]
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            log_content = f.read()
                    except Exception as e:
                        log_content = f"Error reading log file: {str(e)}"
        
        result["log"] = log_content
        return result
    
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

