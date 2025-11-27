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
        self.task_start_time: Optional[datetime] = None
    
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
        self.task_start_time = datetime.now()  # Record task start time
        
        # Get task config from mapping
        if task_id not in self.task_mapping:
            print(f"Error: Task ID '{task_id}' not found in task_mapping")
            self.current_task = None
            self.status = TaskStatus.IDLE
            self.task_start_time = None
            return False
        
        task_config = self.task_mapping[task_id]
        template_file = task_config.get("file")
        
        if not template_file:
            print(f"Error: No template file specified for task '{task_id}'")
            self.current_task = None
            self.status = TaskStatus.IDLE
            self.task_start_time = None
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
        
        # Log task start
        self._log_task_start(task_id, timestamp)
        
        print(f"Started task '{task_id}', created files: {task_filename}, {marker_filename}")
        return True
    
    def _log_task_start(self, task_id: str, timestamp: str):
        """
        Log task start information
        
        Args:
            task_id: Task ID
            timestamp: Task timestamp string
        """
        # Create log file path
        log_filename = f"{task_id}.log"
        log_file_path = self.logs_dir / log_filename
        
        # Prepare log entry
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"\n{'='*60}\n"
        log_entry += f"Task Start Log\n"
        log_entry += f"{'='*60}\n"
        log_entry += f"Task ID: {task_id}\n"
        log_entry += f"Start Time: {start_time}\n"
        log_entry += f"Task Timestamp: {timestamp}\n"
        
        # Get task description and timeout if available
        if task_id in self.task_mapping:
            task_config = self.task_mapping[task_id]
            description = task_config.get("description", "")
            timeout_seconds = task_config.get("timeout")
            
            if description:
                log_entry += f"Task Description: {description}\n"
            if timeout_seconds:
                log_entry += f"Timeout Setting: {timeout_seconds} seconds\n"
        
        log_entry += f"Status: Task started and queued for execution\n"
        log_entry += f"{'='*60}\n"
        
        # Append to log file
        try:
            with open(log_file_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"Error writing task start log: {str(e)}")
    
    def check_if_current_task_done(self) -> bool:
        """
        Check if current task is done by looking for .done file or timeout
        
        Returns:
            True if task is done, False otherwise
        """
        if not self.current_task:
            return False
        
        # Check if task is done by .done file
        done_files = list(self.task_files_dir.glob(f"task_{self.current_task}_*.done"))
        if len(done_files) > 0:
            # Task completed normally (RPA created .done file)
            if self.task_start_time:
                elapsed_time = (datetime.now() - self.task_start_time).total_seconds()
                self._log_task_completion("completed", elapsed_time)
            return True
        
        # Check if task has timed out
        if self.task_start_time and self.current_task in self.task_mapping:
            task_config = self.task_mapping[self.current_task]
            timeout_seconds = task_config.get("timeout")
            
            if timeout_seconds is not None:
                elapsed_time = (datetime.now() - self.task_start_time).total_seconds()
                if elapsed_time >= timeout_seconds:
                    # Task timed out, create .done file automatically
                    print(f"Task '{self.current_task}' timed out after {elapsed_time:.1f} seconds (timeout: {timeout_seconds}s)")
                    self._mark_task_as_done()
                    self._log_task_completion("timeout", elapsed_time, timeout_seconds)
                    return True
        
        return False
    
    def _mark_task_as_done(self):
        """
        Mark current task as done by creating a .done file
        """
        if not self.current_task:
            return
        
        # Find the corresponding task file to get timestamp
        task_files = list(self.task_files_dir.glob(f"task_{self.current_task}_*.json"))
        if task_files:
            # Extract timestamp from task file name
            task_file = task_files[0]
            # Format: task_{task_id}_{timestamp}.json
            parts = task_file.stem.split('_')
            if len(parts) >= 3:
                timestamp = '_'.join(parts[2:])  # Get timestamp part
                done_filename = f"task_{self.current_task}_{timestamp}.done"
                done_file_path = self.task_files_dir / done_filename
                done_file_path.touch()
                print(f"Created timeout .done file: {done_filename}")
    
    def _log_task_completion(self, completion_type: str, elapsed_time: float, timeout_seconds: Optional[float] = None):
        """
        Log task completion information
        
        Args:
            completion_type: "completed" or "timeout"
            elapsed_time: Task execution time in seconds
            timeout_seconds: Timeout value if task timed out
        """
        if not self.current_task:
            return
        
        # Create log file path
        log_filename = f"{self.current_task}.log"
        log_file_path = self.logs_dir / log_filename
        
        # Prepare log entry
        completion_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"\n{'='*60}\n"
        log_entry += f"Task Completion Log\n"
        log_entry += f"{'='*60}\n"
        log_entry += f"Task ID: {self.current_task}\n"
        log_entry += f"Completion Time: {completion_time}\n"
        log_entry += f"Completion Type: {completion_type.upper()}\n"
        log_entry += f"Elapsed Time: {elapsed_time:.2f} seconds\n"
        
        if completion_type == "timeout" and timeout_seconds:
            log_entry += f"Timeout Setting: {timeout_seconds} seconds\n"
            log_entry += f"Status: Task timed out (exceeded {timeout_seconds}s limit)\n"
        else:
            log_entry += f"Status: Task completed successfully\n"
        
        # Get task description if available
        if self.current_task in self.task_mapping:
            task_config = self.task_mapping[self.current_task]
            description = task_config.get("description", "")
            if description:
                log_entry += f"Task Description: {description}\n"
        
        log_entry += f"{'='*60}\n"
        
        # Append to log file
        try:
            with open(log_file_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            print(f"Task completion logged to: {log_filename}")
        except Exception as e:
            print(f"Error writing task completion log: {str(e)}")
    
    def get_status(self) -> Dict:
        """
        Get current task status
        
        Returns:
            Dictionary with current_task, status, and log content
        """
        # Check timeout before returning status
        if self.status == TaskStatus.RUNNING:
            self.check_if_current_task_done()
        
        result = {
            "current_task": self.current_task,
            "status": self.status.value
        }
        
        # Add elapsed time if task is running
        if self.current_task and self.task_start_time:
            elapsed_time = (datetime.now() - self.task_start_time).total_seconds()
            result["elapsed_seconds"] = round(elapsed_time, 1)
            
            # Add timeout info if configured
            if self.current_task in self.task_mapping:
                task_config = self.task_mapping[self.current_task]
                timeout_seconds = task_config.get("timeout")
                if timeout_seconds is not None:
                    result["timeout_seconds"] = timeout_seconds
                    result["remaining_seconds"] = max(0, round(timeout_seconds - elapsed_time, 1))
        
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
    
    def finish_current_task(self):
        """
        Finish current task and prepare for next task
        This should be called when task is done
        """
        if not self.current_task:
            return
        
        # Log task transition if needed
        if self.task_start_time:
            elapsed_time = (datetime.now() - self.task_start_time).total_seconds()
            # Log will be written in check_if_current_task_done, but we can add transition log
            log_filename = f"{self.current_task}.log"
            log_file_path = self.logs_dir / log_filename
            transition_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                with open(log_file_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n[{transition_time}] Task finished, preparing for next task in queue...\n")
            except Exception as e:
                print(f"Error writing task transition log: {str(e)}")
        
        # Reset current task state
        self.current_task = None
        self.status = TaskStatus.IDLE
        self.task_start_time = None
    
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

