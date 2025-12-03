from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import uvicorn
from task_manager import TaskManager

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
    tasks = task_manager.get_available_tasks()
    return {"tasks": tasks}


@app.post("/tasks/create")
async def create_tasks(request: TaskCreateRequest):
    """
    Create tasks and add them to the queue
    
    - Validates task_ids exist in task_mapping
    - Adds valid tasks to queue
    - Automatically starts next task if no task is currently running
    """
    if not request.task_ids:
        raise HTTPException(status_code=400, detail="task_ids cannot be empty")
    
    # Add tasks to queue
    count = task_manager.add_tasks(request.task_ids)
    
    if count == 0:
        raise HTTPException(status_code=400, detail="No valid task_ids provided")
    
    # Start next task if no task is currently running
    # start_next_task will check if task is already running, so we can call it directly
    task_manager.start_next_task()
    
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
    return task_manager.get_status()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)

