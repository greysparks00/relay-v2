from datetime import datetime

class GetTimeTool:
    name = "get_time"
    description = "Get the current time"
    parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False
        } 

    def __call__(self):
        return datetime.now().isoformat()