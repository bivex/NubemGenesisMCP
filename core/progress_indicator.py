#!/usr/bin/env python3
"""
Progress Indicator - Animated progress indicators for long operations
"""

import sys
import time
import threading
from typing import Optional, Callable
import itertools

class ProgressIndicator:
    """Animated progress indicator for CLI operations"""
    
    def __init__(self, message: str = "Processing", style: str = "spinner"):
        self.message = message
        self.style = style
        self.running = False
        self.thread = None
        
        # Different animation styles
        self.animations = {
            'spinner': ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'],
            'dots': ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'],
            'arrows': ['←', '↖', '↑', '↗', '→', '↘', '↓', '↙'],
            'bar': ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█', '▇', '▆', '▅', '▄', '▃', '▂'],
            'clock': ['🕐', '🕑', '🕒', '🕓', '🕔', '🕕', '🕖', '🕗', '🕘', '🕙', '🕚', '🕛'],
            'progress': ['[    ]', '[=   ]', '[==  ]', '[=== ]', '[====]', '[ ===]', '[  ==]', '[   =]'],
            'github': ['🔄', '🔃', '🔁', '🔂'],
        }
        
        # Colors
        self.colors = {
            'blue': '\033[0;34m',
            'green': '\033[0;32m',
            'yellow': '\033[1;33m',
            'cyan': '\033[0;36m',
            'reset': '\033[0m'
        }
    
    def _animate(self):
        """Animation loop"""
        animation = self.animations.get(self.style, self.animations['spinner'])
        color = self.colors['cyan']
        reset = self.colors['reset']
        
        for frame in itertools.cycle(animation):
            if not self.running:
                break
            
            # Clear line and print new frame
            sys.stdout.write(f'\r{color}{frame} {self.message}...{reset}')
            sys.stdout.flush()
            
            time.sleep(0.1)
        
        # Clear the line when done
        sys.stdout.write('\r' + ' ' * (len(self.message) + 10) + '\r')
        sys.stdout.flush()
    
    def start(self):
        """Start the progress indicator"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._animate, daemon=True)
            self.thread.start()
    
    def stop(self, success: bool = True, message: Optional[str] = None):
        """Stop the progress indicator"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        
        # Show completion message
        if message:
            if success:
                print(f"{self.colors['green']}✅ {message}{self.colors['reset']}")
            else:
                print(f"{self.colors['yellow']}⚠️  {message}{self.colors['reset']}")
    
    def __enter__(self):
        """Context manager entry"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop(success=(exc_type is None))


class MultiStepProgress:
    """Progress indicator for multi-step operations"""
    
    def __init__(self, steps: list, title: str = "Processing"):
        self.steps = steps
        self.title = title
        self.current_step = 0
        self.total_steps = len(steps)
        self.indicator = None
        
    def start(self):
        """Start multi-step progress"""
        print(f"\n{self.title}")
        print("=" * 50)
    
    def next_step(self):
        """Move to next step"""
        if self.indicator:
            self.indicator.stop(success=True)
        
        if self.current_step < self.total_steps:
            step_name = self.steps[self.current_step]
            print(f"\n[{self.current_step + 1}/{self.total_steps}] {step_name}")
            
            self.indicator = ProgressIndicator(
                message=step_name,
                style='spinner'
            )
            self.indicator.start()
            self.current_step += 1
            
            return True
        return False
    
    def complete(self, success: bool = True):
        """Complete all steps"""
        if self.indicator:
            self.indicator.stop(success=success)
        
        if success:
            print(f"\n✅ {self.title} completado exitosamente!")
        else:
            print(f"\n❌ {self.title} falló")
        print("=" * 50)


def with_progress(message: str = "Processing", style: str = "spinner"):
    """Decorator to add progress indicator to functions"""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            with ProgressIndicator(message, style) as progress:
                result = func(*args, **kwargs)
                return result
        return wrapper
    return decorator


# Example usage
if __name__ == "__main__":
    # Test different styles
    styles = ['spinner', 'dots', 'arrows', 'bar', 'clock', 'progress', 'github']
    
    for style in styles:
        print(f"\nTesting {style} style:")
        with ProgressIndicator(f"Testing {style}", style) as progress:
            time.sleep(2)
    
    # Test multi-step
    print("\n\nTesting multi-step progress:")
    steps = [
        "Conectando a GitHub",
        "Obteniendo lista de repositorios",
        "Filtrando repositorios públicos",
        "Cambiando visibilidad",
        "Verificando cambios"
    ]
    
    progress = MultiStepProgress(steps, "Cambio de visibilidad de repositorios")
    progress.start()
    
    while progress.next_step():
        time.sleep(1.5)  # Simulate work
    
    progress.complete(success=True)