from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import logging
import uvicorn
from task_manager import TaskManager

# Configure logging with timestamp and location information
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="RPA Task Manager API")

# Initialize TaskManager singleton
task_manager = TaskManager()


class TaskCreateRequest(BaseModel):
    task_ids: List[str]


@app.get("/tasks/available")
async def get_available_tasks():
    """
    Get list of available tasks from task_mapping.json
    """
    logger.info("GET /tasks/available - Requesting available tasks")
    tasks = task_manager.get_available_tasks()
    logger.info(f"Returning {len(tasks)} available task(s)")
    return {"tasks": tasks}


@app.post("/tasks/create")
async def create_tasks(request: TaskCreateRequest):
    """
    Create tasks and add them to the queue
    
    - Validates task_ids exist in task_mapping
    - Adds valid tasks to queue
    - Automatically starts next task if no task is currently running
    """
    logger.info(f"POST /tasks/create - Request to create tasks: {request.task_ids}")
    
    if not request.task_ids:
        logger.warning("POST /tasks/create - Empty task_ids provided")
        raise HTTPException(status_code=400, detail="task_ids cannot be empty")
    
    # Add tasks to queue
    count = task_manager.add_tasks(request.task_ids)
    
    if count == 0:
        logger.warning(f"POST /tasks/create - No valid task_ids provided: {request.task_ids}")
        raise HTTPException(status_code=400, detail="No valid task_ids provided")
    
    # Start next task if no task is currently running
    # start_next_task will check if task is already running, so we can call it directly
    task_manager.start_next_task()
    
    logger.info(f"POST /tasks/create - Successfully queued {count} task(s)")
    return {
        "queued": True,
        "count": count
    }


@app.get("/tasks/status")
async def get_task_status():
    """
    Get current task status including task ID, status, and log content
    Background thread handles task completion checking and automatic task switching
    """
    logger.debug("GET /tasks/status - Requesting task status")
    status = task_manager.get_status()
    logger.debug(f"GET /tasks/status - Current task: {status.get('current_task')}, Status: {status.get('status')}")
    return status


@app.get("/tasks/errors")
async def get_task_errors():
    """
    Get all error records from tasks that terminated with errors
    
    Returns:
        Dictionary with list of error records, each containing:
        - task_id: Task ID
        - description: Task description
        - log: Full execution log content
    """
    logger.info("GET /tasks/errors - Requesting error records")
    errors = task_manager.get_error_records()
    logger.info(f"Returning {len(errors)} error record(s)")
    return {"errors": errors}


if __name__ == "__main__":
    logger.info("Starting RPA Task Manager API server on 0.0.0.0:9000")
    uvicorn.run(app, host="0.0.0.0", port=9000)

