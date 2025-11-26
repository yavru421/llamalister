import tkinter as tk
from tkinter import scrolledtext
import threading
from typing import Any
from . import BaseOperations, OperationResult

class GuiOperations(BaseOperations):
    """Handles GUI operations"""

    def show_chat_interface(self, aua_instance: Any) -> OperationResult:
        """Shows a Tkinter chat interface for interacting with the AUA."""
        try:
            self._log_operation("show_chat_interface", "Launching chat interface")

            def chat_window():
                window = tk.Tk()
                window.title("AUA Chat")

                chat_history = scrolledtext.ScrolledText(window, wrap=tk.WORD, width=60, height=20)
                chat_history.pack(padx=10, pady=10)
                chat_history.insert(tk.END, "AUA: Hello! How can I help you?\n")
                chat_history.config(state=tk.DISABLED)

                input_frame = tk.Frame(window)
                input_frame.pack(padx=10, pady=(0, 10), fill=tk.X)

                user_input = tk.Entry(input_frame, width=50)
                user_input.pack(side=tk.LEFT, fill=tk.X, expand=True)

                def send_message(event: Any = None):
                    message = user_input.get()
                    if not message:
                        return

                    chat_history.config(state=tk.NORMAL)
                    chat_history.insert(tk.END, f"You: {message}\n")
                    user_input.delete(0, tk.END)
                    chat_history.config(state=tk.DISABLED)
                    chat_history.see(tk.END)

                    def get_aua_response():
                        response: str = aua_instance.run(message)
                        chat_history.config(state=tk.NORMAL)
                        chat_history.insert(tk.END, f"AUA: {response}\n\n")
                        chat_history.config(state=tk.DISABLED)
                        chat_history.see(tk.END)

                    threading.Thread(target=get_aua_response, daemon=True).start()

                send_button = tk.Button(input_frame, text="Send", command=send_message)
                send_button.pack(side=tk.RIGHT, padx=(5, 0))

                user_input.bind("<Return>", send_message)

                window.mainloop()

            chat_thread = threading.Thread(target=chat_window, daemon=True)
            chat_thread.start()

            return OperationResult(True, "Chat interface launched in a separate thread.")
        except Exception as e:
            return OperationResult(False, f"Error launching chat interface: {e}")