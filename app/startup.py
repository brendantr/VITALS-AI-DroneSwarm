#!/usr/bin/env python3
import subprocess
import sys

print("Hello world")
print("\n" + "="*50)
print("INSTALLED PYTHON PACKAGES:")
print("="*50)
result = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
print(result.stdout)
