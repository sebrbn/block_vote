import webview
import tkinter as tk
from tkinter import simpledialog
import sys

# 1. Create a tiny popup to ask the admin for the Server's IP address
root = tk.Tk()
root.withdraw() # Hides the ugly background window

# 2. Prompt for the IP
server_ip = simpledialog.askstring(
    "Secure Network Connection", 
    "Enter the Main Server LAN IP (e.g., 192.168.1.15):"
)

# 3. If they typed an IP, launch the Desktop Application
if server_ip:
    url = f"http://{server_ip}:5000/admin"
    
    # Creates a dedicated, native software window
    webview.create_window(
        title='Election Commission - Secure Admin Console', 
        url=url, 
        width=800, 
        height=700,
        confirm_close=True # Asks "Are you sure you want to quit?"
    )
    
    webview.start()
else:
    sys.exit()