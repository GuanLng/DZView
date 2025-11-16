print("Hello World from Anaconda!")

# 测试numpy库是否可用
import numpy as np
print("NumPy version:", np.__version__)

# 测试matplotlib库是否可用
try:
    import matplotlib
    print("Matplotlib version:", matplotlib.__version__)
except ImportError:
    print("Matplotlib not installed")
