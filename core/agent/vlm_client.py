import json
import re
import requests
from typing import List, Dict, Any, Generator

class VLMClient:
    """
    Client for interacting with Qwen3-VL (or similar) models via Ollama.
    Handles the specific prompt engineering for 'computer use'.
    """
    def __init__(self, model_name: str = "qwen2.5-vl:3b", base_url: str = "http://localhost:11434"):
        # Default to 3b as "smallest" standard, but allows override
        self.model_name = model_name
        self.base_url = base_url

    def construct_system_prompt(self) -> str:
        """
        Constructs the system prompt based on the Qwen cookbook for computer use.
        """
        return """
You are a helpful assistant.

# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{
    "type": "function", 
    "function": {
        "name": "computer_use", 
        "description": "Use a mouse and keyboard to interact with a computer, and take screenshots.
* This is an interface to a web browser. You do not have access to a terminal or OS menu.
* Some pages may take time to load, so you may need to wait and take successive screenshots.
* The screen's resolution is 1000x1000.
* Whenever you intend to move the cursor to click on an element like an icon, you should consult a screenshot to determine the coordinates of the element before moving the cursor.
* Make sure to click any buttons, links, icons, etc with the cursor tip in the center of the element.", 
        "parameters": {
            "properties": {
                "action": {
                    "description": "The action to perform. The available actions are:
* `key`: Performs key down presses on the arguments passed in order, then performs key releases in reverse order.
* `type`: Type a string of text on the keyboard.
* `mouse_move`: Move the cursor to a specified (x, y) pixel coordinate on the screen.
* `left_click`: Click the left mouse button at a specified (x, y) pixel coordinate on the screen.
* `left_click_drag`: Click and drag the cursor to a specified (x, y) pixel coordinate on the screen.
* `right_click`: Click the right mouse button at a specified (x, y) pixel coordinate on the screen.
* `middle_click`: Click the middle mouse button at a specified (x, y) pixel coordinate on the screen.
* `double_click`: Double-click the left mouse button at a specified (x, y) pixel coordinate on the screen.
* `scroll`: Performs a scroll of the mouse scroll wheel.
* `wait`: Wait specified seconds for the change to happen.
* `terminate`: Terminate the current task and report its completion status.
* `answer`: Answer a question.", 
                    "enum": ["key", "type", "mouse_move", "left_click", "left_click_drag", "right_click", "middle_click", "double_click", "scroll", "wait", "terminate", "answer"], 
                    "type": "string"
                }, 
                "keys": {
                    "description": "Required only by `action=key`.", 
                    "type": "array"
                }, 
                "text": {
                    "description": "Required only by `action=type` and `action=answer`.", 
                    "type": "string"
                }, 
                "coordinate": {
                    "description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to.", 
                    "type": "array"
                }, 
                "pixels": {
                    "description": "The amount of scrolling to perform. Positive values scroll up, negative values scroll down. Required only by `action=scroll`.", 
                    "type": "number"
                }, 
                "time": {
                    "description": "The seconds to wait. Required only by `action=wait`.", 
                    "type": "number"
                }, 
                "status": {
                    "description": "The status of the task. Required only by `action=terminate`.", 
                    "type": "string", 
                    "enum": ["success", "failure"]
                }
            }, 
            "required": ["action"], 
            "type": "object"
        }
    }
}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
"""

    def generate_action(self, messages: List[Dict[str, Any]]) -> Generator[Dict[str, Any], None, None]:
        """
        Sends the messages to the model and yields chunks/result.
        Yields:
            Dict: {"type": "thinking", "content": str} for streaming thought
            Dict: {"type": "action", "content": dict} for final parsed action
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model_name,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.1, # Low temp for precise tool use
                        "num_ctx": 4096
                    }
                },
                stream=True
            )
            
            full_response = ""
            
            for line in response.iter_lines():
                if line:
                    data = json.loads(line.decode('utf-8'))
                    msg = data.get("message", {})
                    
                    # 1. Handle "thinking" field (Qwen/DeepSeek reasoning models)
                    if "thinking" in msg and msg["thinking"]:
                        yield {"type": "thinking", "content": msg["thinking"]}
                    
                    # 2. Handle "content" field
                    chunk = msg.get("content", "")
                    if chunk:
                        full_response += chunk
                        # Yield thinking content if it is NOT in the specific field (fallback)
                        # But if we saw 'thinking' field, we assume content is just content.
                        # For now, we only yield as thinking if we haven't seen tool call yet?
                        # Actually, if we are using "thinking" field, we shouldn't mix.
                        # However, for qwen3-vl:2b, it might NOT use the field if it wasn't quantized/served that way.
                        # But since user says "qwen3 ... seems to load", maybe they are using a model that uses it.
                        pass # We accumulate content for parsing later. 
                        
                        # Note: We should yield content as 'thinking' ONLY if the model outputs thoughts in content stream 
                        # using <think> tags or verify if it's mixed.
                        # But user request says "the thinking model is sent in a seperate token".
                        # So we rely on the logic above. 
                        
                    if data.get("done"):
                        break
            
            # Parse the final complete response
            action = self._parse_action(full_response)
            if action:
                yield {"type": "action", "content": action}
            else:
                # If no tool call found, maybe it just answered?
                # We'll treat plain text as an 'answer' action or just logged text
                # check if there's a tool call at all
                pass

        except Exception as e:
            print(f"VLM Error: {e}")
            yield {"type": "error", "content": str(e)}

    def _parse_action(self, response_text: str) -> Dict[str, Any]:
        """
        Robustly extracts the JSON action from <tool_call> tags.
        """
        # Look for <tool_call>...JSON...</tool_call>
        pattern = r"<tool_call>\s*({.*?})\s*</tool_call>"
        match = re.search(pattern, response_text, re.DOTALL)
        
        if match:
            json_str = match.group(1)
            try:
                data = json.loads(json_str)
                # The prompt usually asks for {"name":..., "arguments":...}
                # Qwen might output just the arguments depending on fine-tuning, 
                # but the system prompt explicitly asks for name+args.
                if "arguments" in data:
                    return data["arguments"]
                return data
            except json.JSONDecodeError:
                print(f"Failed to parse JSON: {json_str}")
                return None
        return None
