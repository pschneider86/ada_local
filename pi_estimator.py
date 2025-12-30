#!/usr/bin/env python3
"""
Raspberry Pi 5 TTFT Estimator
Measures Time to First Token with streaming.
"""

import requests
import time
import sys
import json

PI_THREAD_COUNT = 4
PI_BANDWIDTH_FACTOR = 3  # Memory bandwidth slowdown

MODELS = [
    {"model": "qwen3:0.6b", "name": "qwen3:0.6b"},
    {"model": "gemma3:1b", "name": "gemma3:1b"},
    {"model": "qwen3:1.7b", "name": "qwen3:1.7b"},
]

TEST_PROMPTS = [
    "Turn on the lights",
    "What's the weather?",
    "Set a timer for 5 minutes",
]

URL = "http://localhost:11434/api/chat"


def measure_ttft(model, prompt, num_thread=None):
    """Stream response and measure time to first token."""
    options = {"temperature": 0.0, "seed": 42}
    if num_thread:
        options["num_thread"] = num_thread
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "options": options
    }
    
    start = time.time()
    ttft = None
    
    try:
        with requests.post(URL, json=payload, stream=True, timeout=60) as r:
            for line in r.iter_lines():
                if line:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content and ttft is None:
                        ttft = time.time() - start
                    if chunk.get("done"):
                        break
        return ttft or 0
    except Exception as e:
        print(f"Error: {e}")
        return 0


def main():
    print("=" * 70)
    print("Raspberry Pi 5 TTFT Estimator (Streaming)")
    print(f"Simulated threads: {PI_THREAD_COUNT}")
    print("=" * 70)
    
    results = []
    
    for config in MODELS:
        model = config["model"]
        name = config["name"]
        
        print(f"\n🔄 Testing {name}...")
        
        # Warmup
        measure_ttft(model, "hi", PI_THREAD_COUNT)
        
        mac_ttft_list = []
        throttled_ttft_list = []
        
        for i, prompt in enumerate(TEST_PROMPTS):
            sys.stdout.write(f"\r  Prompt {i+1}/{len(TEST_PROMPTS)}...")
            sys.stdout.flush()
            
            # Full Mac TTFT
            mac_ttft = measure_ttft(model, prompt)
            
            # Throttled TTFT
            throttled_ttft = measure_ttft(model, prompt, PI_THREAD_COUNT)
            
            if mac_ttft > 0:
                mac_ttft_list.append(mac_ttft)
            if throttled_ttft > 0:
                throttled_ttft_list.append(throttled_ttft)
        
        print("\r" + " " * 30)
        
        if mac_ttft_list and throttled_ttft_list:
            avg_mac = sum(mac_ttft_list) / len(mac_ttft_list)
            avg_throttled = sum(throttled_ttft_list) / len(throttled_ttft_list)
            
            # Pi estimate: throttled + bandwidth slowdown
            estimated_pi = avg_throttled * PI_BANDWIDTH_FACTOR
            
            results.append({
                "name": name,
                "mac_ttft": avg_mac * 1000,  # Convert to ms
                "throttled_ttft": avg_throttled * 1000,
                "pi_est_ttft": estimated_pi * 1000,
            })
    
    # Print results
    print("\n" + "=" * 70)
    print("TIME TO FIRST TOKEN (TTFT)")
    print("=" * 70)
    print(f"\n{'MODEL':<20} | {'MAC TTFT':<12} | {'THROTTLED':<12} | {'PI 5 EST.':<12}")
    print("-" * 65)
    
    for r in results:
        print(f"{r['name']:<20} | {r['mac_ttft']:<10.0f}ms | {r['throttled_ttft']:<10.0f}ms | {r['pi_est_ttft']:<10.0f}ms")
    
    print("-" * 65)
    
    # Best for Pi
    best = min(results, key=lambda x: x["pi_est_ttft"])
    print(f"\n🏆 Fastest TTFT on Pi: {best['name']} (~{best['pi_est_ttft']:.0f}ms)")
    
    # Usability assessment
    print("\n📊 USABILITY:")
    for r in results:
        ttft_sec = r["pi_est_ttft"] / 1000
        if ttft_sec < 0.5:
            feel = "⚡ Instant"
        elif ttft_sec < 1:
            feel = "✅ Responsive"
        elif ttft_sec < 2:
            feel = "⚠️ Noticeable delay"
        else:
            feel = "❌ Slow"
        print(f"   {r['name']:<16} {ttft_sec:.1f}s → {feel}")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
