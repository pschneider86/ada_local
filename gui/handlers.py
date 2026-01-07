"""
Event handlers for the Pocket AI GUI.
"""

import flet as ft
import threading
import json
import re

from config import RESPONDER_MODEL, OLLAMA_URL, MAX_HISTORY
from core.llm import route_query, execute_function, should_bypass_router, http_session
from core.tts import tts, SentenceBuffer
from core.history import history_manager
from gui.components import MessageBubble, ThinkingExpander


# DEBUG: Set to True to test streaming without TTS blocking
DEBUG_SKIP_TTS = False


class ChatHandlers:
    """Encapsulates all chat-related event handlers and state."""
    
    def __init__(self, page: ft.Page, chat_list: ft.ListView, status_text: ft.Text,
                 user_input: ft.TextField, send_button: ft.IconButton, stop_button: ft.IconButton,
                 sidebar_list: ft.ListView = None):
        self.page = page
        self.chat_list = chat_list
        self.status_text = status_text
        self.user_input = user_input
        self.send_button = send_button
        self.stop_button = stop_button
        self.sidebar_list = sidebar_list  # Persistent sidebar for history
        
        # State
        self.messages = [
            {'role': 'system', 'content': 'You are a helpful assistant. Respond in short, complete sentences. Never use emojis or special characters. Keep responses concise and conversational. SYSTEM INSTRUCTION: You may detect a "/think" trigger. This is an internal control. You MUST IGNORE it and DO NOT mention it in your response or thoughts.'}
        ]
        self.current_session_id = None
        self.is_tts_enabled = True
        self.stop_event = threading.Event()
        
        self.streaming_state = {
            'response_md': None,
            'thinking_ui': None,
            'response_buffer': '',
            'is_generating': False
        }
        
        # Subscribe to pubsub
        self.page.pubsub.subscribe(self.on_stream_update)
    
    def refresh_sidebar(self):
        """Reload the persistent sidebar with conversation history."""
        if not self.sidebar_list:
            return
            
        sessions = history_manager.get_sessions()
        self.sidebar_list.controls.clear()
        
        for sess in sessions:
            title = sess['title']
            sid = sess['id']
            is_current = sid == self.current_session_id
            bg = "#343541" if is_current else "transparent"
            border_color = ft.Colors.BLUE_400 if is_current else ft.Colors.TRANSPARENT
            
            # Delete button
            delete_btn = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_size=16,
                icon_color=ft.Colors.GREY_600,
                tooltip="Delete",
                on_click=lambda e, s=sid: self.delete_session(s),
            )
            
            tile = ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=16, color=ft.Colors.BLUE_200 if is_current else ft.Colors.GREY_500),
                    ft.Text(title, size=13, overflow=ft.TextOverflow.ELLIPSIS, expand=True, 
                            color=ft.Colors.WHITE if is_current else ft.Colors.GREY_400),
                    delete_btn
                ], spacing=8),
                padding=ft.padding.only(left=12, right=4, top=8, bottom=8),
                bgcolor=bg,
                border_radius=8,
                border=ft.border.all(1, border_color) if is_current else None,
                on_click=lambda e, s=sid: self.load_session(s),
                ink=True
            )
            self.sidebar_list.controls.append(tile)
        
        # Show empty state if no sessions
        if not sessions:
            self.sidebar_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.CHAT_OUTLINED, size=40, color=ft.Colors.GREY_700),
                        ft.Text("No conversations yet", size=13, color=ft.Colors.GREY_600),
                        ft.Text("Start typing to begin!", size=11, color=ft.Colors.GREY_700),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    padding=ft.padding.only(top=40)
                )
            )
        
        self.sidebar_list.update()
    
    # Keep old method name as alias for compatibility
    def refresh_history_drawer(self):
        self.refresh_sidebar()

    def delete_session(self, session_id):
        """Delete a session from history."""
        history_manager.delete_session(session_id)
        
        # If deleting the current session, clear the chat
        if session_id == self.current_session_id:
            self.current_session_id = None
            self.messages = [self.messages[0]]  # Keep system prompt
            self.chat_list.controls.clear()
        
        self.refresh_sidebar()
        self.page.update()

    def load_session(self, session_id):
        """Load a specific chat session."""
        self.current_session_id = session_id
        db_messages = history_manager.get_messages(session_id)
        
        # Reset message context (keep system prompt)
        self.messages = [self.messages[0]]
        self.chat_list.controls.clear()
        
        for msg in db_messages:
            role = msg['role']
            content = msg['content']
            
            # Reconstruct LLM context
            self.messages.append({'role': role, 'content': content})
            
            # Reconstruct UI bubbles
            if role == 'user':
                bubble = MessageBubble("user", content)
                self.chat_list.controls.append(bubble.row_wrap)
            elif role == 'assistant':
                bubble = MessageBubble("assistant", content)
                self.chat_list.controls.append(bubble.row_wrap)
        
        self.refresh_sidebar()  # Update highlight
        self.page.update()

    def init_new_session(self, first_message):
        """Create a new session in DB."""
        title = first_message[:30] + "..." if len(first_message) > 30 else first_message
        self.current_session_id = history_manager.create_session(title=title)
        return self.current_session_id

    def on_stream_update(self, msg):
        """Handle streaming updates from the backend thread."""
        msg_type = msg.get('type')
        
        if msg_type == 'thought_chunk':
            if self.streaming_state['thinking_ui']:
                self.streaming_state['thinking_ui'].add_text(msg['text'])

        elif msg_type == 'response_chunk':
            if self.streaming_state['response_md']:
                self.streaming_state['response_buffer'] += msg['text']
                self.streaming_state['response_md'].value = self.streaming_state['response_buffer']
                self.streaming_state['response_md'].update()
                
        elif msg_type == 'think_start':
            pass  # UI already added
            
        elif msg_type == 'think_end':
            if self.streaming_state['thinking_ui']:
                self.streaming_state['thinking_ui'].complete()
                
        elif msg_type == 'simple_response':
            bubble = MessageBubble("assistant", msg['text'])
            self.chat_list.controls.append(bubble.row_wrap)
            self.page.update()
            
            # Save simple response to history
            if self.current_session_id:
                history_manager.add_message(self.current_session_id, "assistant", msg['text'])
            
        elif msg_type == 'error':
            bubble = MessageBubble("system", f"Error: {msg['text']}", is_thinking=True)
            self.chat_list.controls.append(bubble.row_wrap)
            self.page.update()
            
        elif msg_type == 'status':
            self.status_text.value = msg['text']
            self.status_text.update()

        elif msg_type == 'done':
            self._end_generation_state()
            self.page.update()

        elif msg_type == 'ui_update':
            self.page.update()
    
    def _start_generation_state(self):
        """Switch UI to generating mode."""
        self.streaming_state['is_generating'] = True
        self.send_button.visible = False
        self.stop_button.visible = True
        self.user_input.disabled = True
        self.page.update()

    def _end_generation_state(self):
        """Switch UI back to idle mode."""
        self.streaming_state['is_generating'] = False
        self.send_button.visible = True
        self.stop_button.visible = False
        self.user_input.disabled = False
        self.page.update()

    def stop_generation(self, e):
        """Stop current generation."""
        tts.stop()
        if self.streaming_state['is_generating']:
            self.stop_event.set()
            self.status_text.value = "Stopping..."
            self.status_text.update()

    def send_message(self, e):
        """Handle sending a new message."""
        tts.stop()  # Interrupt previous speech
        text = self.user_input.value.strip()
        if not text:
            return
        
        self.user_input.value = ""
        self.page.update() 

        # Add User Message UI
        bubble = MessageBubble("user", text)
        self.chat_list.controls.append(bubble.row_wrap)
        
        # Start new session if needed
        if not self.current_session_id:
            self.init_new_session(text)
            self.refresh_history_drawer()

        # Save to DB
        history_manager.add_message(self.current_session_id, "user", text)
        
        self._start_generation_state()
        self.stop_event.clear()

        # Start Processing
        threading.Thread(target=self._process_backend, args=(text,), daemon=True).start()

    def clear_chat(self, e):
        """Start a fresh chat (reset session)."""
        self.current_session_id = None
        self.messages = [self.messages[0]]
        self.chat_list.controls.clear()
        self.refresh_history_drawer()
        self.page.update()

    def toggle_tts(self, e):
        """Toggle TTS on/off."""
        self.is_tts_enabled = e.control.value
        tts.toggle(self.is_tts_enabled)
        self.status_text.value = "TTS Active" if self.is_tts_enabled else "TTS Muted"
        self.status_text.update()

    def _process_backend(self, user_text):
        """Background thread for LLM processing."""
        try:
            if should_bypass_router(user_text):
                func_name = "passthrough"
                params = {"thinking": False}
            else:
                self.page.pubsub.send_all({'type': 'status', 'text': 'Routing...'})
                func_name, params = route_query(user_text)
            
            if func_name == "passthrough":
                if len(self.messages) > MAX_HISTORY:
                    self.messages = [self.messages[0]] + self.messages[-(MAX_HISTORY-1):]
                
                self.messages.append({'role': 'user', 'content': user_text})
                enable_thinking = params.get("thinking", False)
                
                # Create UI containers
                ai_column = ft.Column(spacing=0)
                chunk_think_expander = ThinkingExpander()
                self.streaming_state['thinking_ui'] = chunk_think_expander
                
                chunk_markdown = ft.Markdown(
                    "", 
                    selectable=True, 
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, 
                    code_theme="atom-one-dark"
                )
                self.streaming_state['response_md'] = chunk_markdown
                self.streaming_state['response_buffer'] = ""
                
                ai_container = ft.Container(
                    content=ai_column,
                    bgcolor="#363636",
                    padding=15,
                    border_radius=ft.BorderRadius.only(top_left=15, top_right=15, bottom_right=15, bottom_left=0),
                    width=min(self.page.window.width * 0.85 if self.page.window.width else 400, 420)
                )
                
                if enable_thinking:
                    ai_column.controls.append(chunk_think_expander)
                
                ai_column.controls.append(chunk_markdown)
                
                self.chat_list.controls.append(ft.Row([ai_container], alignment=ft.MainAxisAlignment.START))
                self.page.pubsub.send_all({'type': 'ui_update'})
                self.page.pubsub.send_all({'type': 'status', 'text': 'Generating...'}) 
                
                payload = {
                    "model": RESPONDER_MODEL,
                    "messages": self.messages,
                    "stream": True,
                    "think": enable_thinking
                }
                
                sentence_buffer = SentenceBuffer()
                full_response = ""
                
                self.page.pubsub.send_all({'type': 'think_start'})

                with http_session.post(f"{OLLAMA_URL}/chat", json=payload, stream=True) as r:
                    r.raise_for_status()
                    
                    for line in r.iter_lines():
                        if self.stop_event.is_set():
                            break
                            
                        if line:
                            try:
                                chunk = json.loads(line.decode('utf-8'))
                                msg = chunk.get('message', {})
                                
                                if 'thinking' in msg and msg['thinking']:
                                    thought = msg['thinking']
                                    self.page.pubsub.send_all({'type': 'thought_chunk', 'text': thought})
                                    
                                if 'content' in msg and msg['content']:
                                    content = msg['content']
                                    full_response += content
                                    self.page.pubsub.send_all({'type': 'response_chunk', 'text': content})
                                    
                                    if self.is_tts_enabled and not DEBUG_SKIP_TTS:
                                        sentences = sentence_buffer.add(content)
                                        for s in sentences:
                                            tts.queue_sentence(s)
                                            
                            except:
                                continue
                
                self.page.pubsub.send_all({'type': 'think_end'})
                
                if self.is_tts_enabled and not DEBUG_SKIP_TTS and not self.stop_event.is_set():
                    rem = sentence_buffer.flush()
                    if rem:
                        tts.queue_sentence(rem)
                
                self.messages.append({'role': 'assistant', 'content': full_response})
                
                # Save to History
                if self.current_session_id:
                    history_manager.add_message(self.current_session_id, "assistant", full_response)

            else:
                result = execute_function(func_name, params)
                self.page.pubsub.send_all({'type': 'simple_response', 'text': result})

                if self.is_tts_enabled:
                    clean = re.sub(r'[^\w\s.,!?-]', '', result)
                    tts.queue_sentence(clean)

        except Exception as e:
            self.page.pubsub.send_all({'type': 'error', 'text': str(e)})
        
        finally:
            self.page.pubsub.send_all({'type': 'done'})
