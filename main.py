import requests
import json
import sys
import os
import re
import wave
import threading
import queue
from pathlib import Path

# ANSI Escape Codes for coloring output
GRAY = "\033[90m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"

# --- Piper TTS Integration ---
class PiperTTS:
    """Lightweight Piper TTS wrapper with streaming sentence support."""
    
    # British female voice model (Alba - Scottish English)
    VOICE_MODEL = "en_GB-alba-medium"
    MODEL_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx"
    CONFIG_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/alba/medium/en_GB-alba-medium.onnx.json"
    
    def __init__(self):
        self.enabled = False
        self.voice = None
        self.speech_queue = queue.Queue()
        self.worker_thread = None
        self.running = False
        self.models_dir = Path.home() / ".local" / "share" / "piper" / "voices"
        
        # Check if piper-tts is installed
        try:
            from piper import PiperVoice
            self.PiperVoice = PiperVoice
            self.available = True
        except ImportError:
            self.available = False
            print(f"{GRAY}[TTS] piper-tts not installed. Run: pip install piper-tts{RESET}")
    
    def download_model(self):
        """Download voice model if not present."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        model_path = self.models_dir / f"{self.VOICE_MODEL}.onnx"
        config_path = self.models_dir / f"{self.VOICE_MODEL}.onnx.json"
        
        if not model_path.exists():
            print(f"{CYAN}[TTS] Downloading voice model ({self.VOICE_MODEL})...{RESET}")
            # Download model
            r = requests.get(self.MODEL_URL, stream=True)
            r.raise_for_status()
            with open(model_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            # Download config
            r = requests.get(self.CONFIG_URL)
            r.raise_for_status()
            with open(config_path, 'wb') as f:
                f.write(r.content)
            print(f"{CYAN}[TTS] Model downloaded!{RESET}")
        
        return str(model_path), str(config_path)
    
    def initialize(self):
        """Load the voice model."""
        if not self.available:
            return False
        
        try:
            model_path, config_path = self.download_model()
            self.voice = self.PiperVoice.load(model_path, config_path)
            self.running = True
            self.worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
            self.worker_thread.start()
            return True
        except Exception as e:
            print(f"{GRAY}[TTS] Failed to initialize: {e}{RESET}")
            return False
    
    def _speech_worker(self):
        """Background thread that plays queued sentences."""
        while self.running:
            try:
                text = self.speech_queue.get(timeout=0.5)
                if text is None:  # Poison pill
                    break
                self._speak_text(text)
                self.speech_queue.task_done()
            except queue.Empty:
                continue
    
    def _speak_text(self, text):
        """Synthesize and play text using the system audio."""
        if not self.voice or not text.strip():
            return
        
        try:
            # Piper synthesize() returns an iterable of AudioChunk objects
            # Each chunk has .audio (bytes) and .sample_rate
            tmp_wav = "/tmp/piper_output.wav"
            audio_bytes = b""
            sample_rate = self.voice.config.sample_rate
            
            for audio_chunk in self.voice.synthesize(text):
                audio_bytes += audio_chunk.audio_int16_bytes
            
            # Write WAV file with proper headers
            with wave.open(tmp_wav, 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_bytes)
            
            # Play using macOS afplay (fast and reliable)
            os.system(f'afplay "{tmp_wav}" 2>/dev/null')
        except Exception as e:
            print(f"{GRAY}[TTS Error]: {e}{RESET}")  # Show errors for debugging
    
    def queue_sentence(self, sentence):
        """Add a sentence to the speech queue."""
        if self.enabled and self.voice and sentence.strip():
            self.speech_queue.put(sentence)
    
    def wait_for_completion(self):
        """Wait for all queued speech to finish."""
        if self.enabled:
            self.speech_queue.join()
    
    def toggle(self, enable):
        """Enable/disable TTS."""
        if enable and not self.voice:
            if self.initialize():
                self.enabled = True
                return True
            return False
        self.enabled = enable
        return True
    
    def shutdown(self):
        """Clean up resources."""
        self.running = False
        self.speech_queue.put(None)


class SentenceBuffer:
    """Buffers streaming text and extracts complete sentences."""
    
    # Sentence-ending patterns
    SENTENCE_ENDINGS = re.compile(r'([.!?])\s+|([.!?])$')
    
    def __init__(self):
        self.buffer = ""
    
    def add(self, text):
        """Add text chunk and return any complete sentences."""
        self.buffer += text
        sentences = []
        
        # Find sentence boundaries
        while True:
            match = self.SENTENCE_ENDINGS.search(self.buffer)
            if match:
                end_pos = match.end()
                sentence = self.buffer[:end_pos].strip()
                if sentence:
                    sentences.append(sentence)
                self.buffer = self.buffer[end_pos:]
            else:
                break
        
        return sentences
    
    def flush(self):
        """Return any remaining text as a final sentence."""
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining if remaining else None


# Global TTS instance
tts = PiperTTS()


def main():
    # Default State
    thinking_mode = False
    tts_mode = tts.toggle(True)  # Enable TTS by default
    
    print(f"{BOLD}Pocket AI (Qwen3-1.7B) - DeepSeek Style{RESET}")
    print("---------------------------------------------")
    print(f"Commands:")
    print(f"  /think on   -> {GRAY}Show internal reasoning{RESET}")
    print(f"  /think off  -> Hide reasoning (Faster/Cleaner)")
    print(f"  /tts on     -> {CYAN}Enable voice output{RESET}")
    print(f"  /tts off    -> Disable voice output")
    print(f"  exit        -> Quit")
    print(f"{CYAN}[TTS enabled by default]{RESET}")
    print("---------------------------------------------\n")
    
    messages = [
        {'role': 'system', 'content': 'You are a helpful assistant. Respond in short, complete sentences. Never use emojis or special characters. Keep responses concise and conversational.'}
    ]
    
    url = "http://localhost:11434/api/chat"
    
    while True:
        try:
            # Visual indicator of current mode
            mode_parts = []
            if thinking_mode:
                mode_parts.append(f"{GRAY}Thinking{RESET}")
            if tts_mode:
                mode_parts.append(f"{CYAN}Voice{RESET}")
            mode_text = f"({', '.join(mode_parts)})" if mode_parts else "(Fast)"
            
            user_input = input(f"You {mode_text}: ")
            
            if not user_input: continue
            
            # --- Command Handling ---
            if user_input.strip().lower() == "/think on":
                thinking_mode = True
                print(f">> System: Thinking {BOLD}ENABLED{RESET}. You will see the reasoning process.")
                continue
                
            if user_input.strip().lower() == "/think off":
                thinking_mode = False
                print(f">> System: Thinking {BOLD}DISABLED{RESET}.")
                continue

            if user_input.strip().lower() == "/tts on":
                if tts.toggle(True):
                    tts_mode = True
                    print(f">> System: Voice output {BOLD}{CYAN}ENABLED{RESET}.")
                else:
                    print(f">> System: {GRAY}TTS unavailable. Install with: pip install piper-tts{RESET}")
                continue
                
            if user_input.strip().lower() == "/tts off":
                tts.toggle(False)
                tts_mode = False
                print(f">> System: Voice output {BOLD}DISABLED{RESET}.")
                continue

            if user_input.lower() in ['exit', 'quit']:
                tts.shutdown()
                print("Goodbye!")
                break
                
            messages.append({'role': 'user', 'content': user_input})
            
            # --- The Request ---
            payload = {
                "model": "qwen3:1.7b",
                "messages": messages,
                "stream": True,
                "think": thinking_mode 
            }
            
            print("AI: ", end='', flush=True)
            
            # Trackers to handle newlines cleanly between Thought and Answer
            full_response = ""
            has_printed_thought = False
            sentence_buffer = SentenceBuffer()
            
            with requests.post(url, json=payload, stream=True) as r:
                r.raise_for_status()
                
                for line in r.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            
                            # Get the message object (if it exists)
                            msg = chunk.get('message', {})
                            
                            # 1. HANDLE THINKING TOKENS
                            # The API puts reasoning here now, not in 'content'
                            if 'thinking' in msg and msg['thinking']:
                                # Print in GRAY so it looks like a "thought bubble"
                                print(f"{GRAY}{msg['thinking']}{RESET}", end='', flush=True)
                                has_printed_thought = True

                            # 2. HANDLE ACTUAL CONTENT
                            if 'content' in msg and msg['content']:
                                # If we just finished thinking, add a newline to separate Thought from Answer
                                if has_printed_thought:
                                    print(f"{RESET}\n\n", end='', flush=True) 
                                    has_printed_thought = False # Reset flag so we don't print newlines forever
                                
                                # Print the answer normally
                                content = msg['content']
                                print(content, end='', flush=True)
                                full_response += content
                                
                                # TTS: Extract and queue complete sentences
                                if tts_mode:
                                    sentences = sentence_buffer.add(content)
                                    for sentence in sentences:
                                        tts.queue_sentence(sentence)
                                
                        except json.JSONDecodeError:
                            continue
            
            # TTS: Handle any remaining buffered text
            if tts_mode:
                remaining = sentence_buffer.flush()
                if remaining:
                    tts.queue_sentence(remaining)
                tts.wait_for_completion()
            
            print() # Final newline
            messages.append({'role': 'assistant', 'content': full_response})

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    main()