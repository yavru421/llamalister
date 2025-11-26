"""
LlamaLister - Tabbed Interface with Persistent Memory
Uses Llama API for AI assistance with full memory service integration
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import json
import csv
import requests
import re
import time
from dataclasses import dataclass
try:
    import pyautogui as _pyautogui  # for simulated paste hotkey
except Exception:
    _pyautogui = None
PYAUTOGUI_AVAILABLE = _pyautogui is not None
try:
    import pyperclip as _pyperclip  # for reliable clipboard set
except Exception:
    _pyperclip = None
PYPERCLIP_AVAILABLE = _pyperclip is not None
try:
    import pynput.mouse
except Exception:
    pynput = None
PYNPUT_AVAILABLE = pynput is not None
import base64
from datetime import datetime
from pathlib import Path
import threading
import sys

# Add parent directory to path for imports (src + root for strict_mode)
core_src_path = Path(__file__).parent.parent / "Core_AUA_System" / "src"
core_root_path = Path(__file__).parent.parent / "Core_AUA_System"
sys.path.insert(0, str(core_src_path))
sys.path.insert(0, str(core_root_path))
try:
    import strict_mode  # noqa: F401
except Exception:
    print("⚠️ strict_mode not available - fatal enforcement disabled for GUI")

try:
    from memory_service import get_memory_service
    MEMORY_AVAILABLE = True
except ImportError:
    MEMORY_AVAILABLE = False
    print("⚠️ Memory service not available - running without persistent memory")

# Configuration
LLAMA_API_URL = os.environ.get("LLAMA_API_URL", "https://api.llama.com/v1/chat/completions")
LLAMA_API_KEY = os.environ.get("LLAMA_API_KEY", "")
LLAMA_MODEL = os.environ.get("LLAMA_MODEL", "Llama-3.3-70B-Instruct")
VISION_MODEL_SCOUT = "Llama-4-Scout-17B-16E-Instruct-FP8"
VISION_MODEL_MAVERICK = "Llama-4-Maverick-17B-128E-Instruct-FP8"

# Persistent storage paths (always saved relative to this script directory for consistency)
LISTINGS_DIR = Path(__file__).parent
LISTINGS_FILE = LISTINGS_DIR / "listings.csv"
LISTINGS_JSON_FILE = LISTINGS_DIR / "listings.json"

# === Performance / Reuse Optimizations ===
# Pre-compile regex patterns used for auto-population to avoid recompilation cost each listing
TITLE_PATTERN = re.compile(r'^TITLE:\s*(.+)', re.MULTILINE)
PRICE_RANGE_PATTERN = re.compile(r'PRICE_RANGE_USD:\s*([$]?\d[\d-]*)')
ALT_PRICE_RANGE_PATTERN = re.compile(r'Likely retail range:?\s*\$?(\d+)[-–](\d+)')
CONDITION_PATTERN = re.compile(r'CONDITION:\s*(.+)')

# Required keys for simple field pack validation (best-effort)
SIMPLE_FIELD_PACK_REQUIRED = [
    'TITLE', 'TAGLINE', 'MATERIALS', 'DIMENSIONS', 'CONDITION', 'PRICE_RANGE_USD', 'SEO_KEYWORDS'
]


def _sanitize_description_for_save(desc: str) -> str:
    """Remove or clean common placeholder tokens from generated descriptions before saving.

    This removes lines that contain only placeholders (e.g. UNKNOWN_MATERIAL, UNKNOWN_SIZE,
    or tokens like ##EXACT_DIMENSIONS##) and strips those tokens from mixed lines.
    """
    if not desc:
        return ""

    tokens = [
        'UNKNOWN_MATERIAL', 'UNKNOWN_SIZE', '##EXACT_DIMENSIONS##', '##BRAND_OR_MAKER##',
        '##MATERIALS_DETAILS##', '##PURCHASE_INFO##', '##USAGE_HISTORY##', '##CARE_INSTRUCTIONS##',
        '##INCLUDED_ITEMS##', '##SHIPPING_DETAILS##', 'TBD', 'UNKNOWN', 'N/A'
    ]
    # case-insensitive pattern
    token_pattern = re.compile(r'(' + '|'.join(re.escape(t) for t in tokens) + r')', re.IGNORECASE)

    cleaned_lines = []
    for line in desc.splitlines():
        if token_pattern.search(line):
            # Remove tokens from the line
            reduced = token_pattern.sub('', line)
            # Remove punctuation left behind
            reduced_stripped = re.sub(r'[\-_:#*\[\]]+', '', reduced).strip()
            # If nothing useful remains, skip the line entirely
            if not re.search(r'[A-Za-z0-9]', reduced_stripped):
                continue
            cleaned_lines.append(reduced_stripped)
        else:
            cleaned_lines.append(line)

    # Collapse multiple blank lines
    cleaned = '\n'.join(cleaned_lines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

@dataclass
class Listing:
    """Structured representation of a listing used internally for persistence.
    Introduced for clearer data handling; external CSV/JSON formats preserved.
    """
    timestamp: str
    title: str
    description: str
    price: str
    category: str
    condition: str
    platforms: list[str]
    images: list[str]

    @classmethod
    def from_form(cls, app: 'ListingApp'):
        # Sanitize description to remove placeholder tokens before saving
        raw_desc = app.desc_text.get("1.0", tk.END).strip()
        try:
            from html import unescape as _unescape  # local import to avoid top-level side effects
        except Exception:
            _unescape = lambda x: x
        desc = _sanitize_description_for_save(raw_desc)
        return cls(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            title=app.title_var.get(),
            description=desc,
            price=app.price_var.get(),
            category=app.category_var.get(),
            condition=app.condition_var.get(),
            platforms=[p for p, v in app.platform_vars.items() if v.get()],
            images=app.uploaded_images.copy()
        )

    def to_csv_row(self):
        row = {
            "Timestamp": self.timestamp,
            "Title": self.title,
            "Description": self.description,
            "Price": self.price,
            "Category": self.category,
            "Condition": self.condition,
            "Platforms": ", ".join(self.platforms),
            "Images": " | ".join(self.images)
        }
        # Remove fields with 'UNKNOWN', 'N/A', or empty values
        return {k: v for k, v in row.items() if v and v.upper() not in ["UNKNOWN", "N/A", "UNKNOWN_SIZE", "UNKNOWN_MATERIAL", "TBD"]}

    def to_json_entry(self):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "title": self.title,
            "description": self.description,
            "price": self.price,
            "category": self.category,
            "condition": self.condition,
            "images": self.images,
            "platforms": self.platforms
        }
        # Remove fields with 'UNKNOWN', 'N/A', or empty values
        return {k: v for k, v in entry.items() if v and (not isinstance(v, str) or v.upper() not in ["UNKNOWN", "N/A", "UNKNOWN_SIZE", "UNKNOWN_MATERIAL", "TBD"])}


class ListingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("LlamaLister")
        self.root.geometry("1000x700")
        self.status_var = tk.StringVar(value="Ready")

        # High-contrast, non-blue color scheme for readability
        self.colors = {
            'bg_primary': '#222222',      # Very dark gray background
            'bg_secondary': '#2c2c2c',   # Slightly lighter dark gray
            'bg_tertiary': '#444444',    # Accent panel color (neutral)
            'accent': '#00BCD4',         # Teal/cyan accent (more readable than yellow)
            'accent_hover': '#0097A7',   # Darker teal hover
            'text': '#E6E6E6',           # Slightly off-white for less glare
            'text_secondary': '#BDBDBD', # Dimmed text
            'success': '#4caf50',        # Green
            'warning': '#ff9800',        # Orange
            'error': '#f44336',          # Red
            'input_bg': '#333333',       # Input field background
            'button_bg': '#007ACC',      # Button background (blue)
        }

        self.root.configure(bg=self.colors['bg_primary'])

        # Initialize memory service
        self.memory_service = None
        self.session_id = None
        if MEMORY_AVAILABLE:
            try:
                self.memory_service = get_memory_service()
                self.session_id = self.memory_service.start_session(user_agent="ListingGUI_v2")
                print(f"✅ Memory service initialized - Session: {self.session_id}")
            except Exception as e:
                print(f"⚠️ Memory service init failed: {e}")

        # Configure ttk styles
        self._configure_styles()

        # Track state
        self.uploaded_images = []
        self.current_listing_data = {}
        # Whether to request a detailed price explanation from Llama
        self.detailed_price_var = tk.BooleanVar(value=False)
        # Multi-stage vision analysis intermediate storage
        self.scout_raw = None
        self.scout_json = None
        self.maverick_raw = None
        self.maverick_json = None

        # Create main UI
        self._create_ui()
        # Keyboard shortcuts for speed
        self.root.bind('<Control-s>', lambda e: self.save_listing())
        self.root.bind('<Control-g>', lambda e: self.generate_enterprise_listing())

        # Log startup
        self._log_interaction("gui", "startup", "LlamaLister started")

    def _configure_styles(self):
        """Configure ttk styles for modern look"""
        style = ttk.Style()
        style.theme_use('clam')

        # Frame styles
        style.configure('TFrame', background=self.colors['bg_primary'])
        style.configure('Card.TFrame', background=self.colors['bg_secondary'], relief='flat')

        # Label styles
        style.configure('TLabel', background=self.colors['bg_primary'],
                       foreground=self.colors['text'], font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 16, 'bold'),
                       foreground=self.colors['accent'])
        style.configure('Subtitle.TLabel', font=('Segoe UI', 12, 'bold'))

        # Button styles
        style.configure('TButton',
                       background=self.colors['button_bg'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Segoe UI', 10))
        style.map('TButton',
                 background=[('active', self.colors['accent_hover'])],
                 foreground=[('active', 'white')])

        style.configure('Accent.TButton',
                       background=self.colors['accent'],
                       font=('Segoe UI', 10, 'bold'))

        # Entry styles
        style.configure('TEntry',
                       fieldbackground=self.colors['input_bg'],
                       foreground=self.colors['text'],
                       borderwidth=1,
                       insertcolor=self.colors['accent'])

        # Notebook (tabs) styles
        style.configure('TNotebook', background=self.colors['bg_primary'], borderwidth=0)
        style.configure('TNotebook.Tab',
                       background=self.colors['bg_tertiary'],
                       foreground=self.colors['text'],
                       padding=[20, 10],
                       font=('Segoe UI', 10, 'bold'))
        style.map('TNotebook.Tab',
                 background=[('selected', self.colors['accent'])],
                 foreground=[('selected', 'white')])

        # LabelFrame styles
        style.configure('TLabelframe',
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['accent'],
                       borderwidth=1,
                       relief='solid')
        style.configure('TLabelframe.Label',
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['accent'],
                       font=('Segoe UI', 11, 'bold'))

        # Radiobutton and Checkbutton
        style.configure('TRadiobutton', background=self.colors['bg_secondary'],
                       foreground=self.colors['text'])
        style.configure('TCheckbutton', background=self.colors['bg_secondary'],
                       foreground=self.colors['text'])

    def _create_ui(self):
        """Create single-window, single-pipeline UI"""
        # === GLOBAL SCROLLABLE CONTAINER ===
        # Wrap all content (except status bar) in a canvas with vertical scrollbar so the
        # entire window becomes scrollable when the content height exceeds the viewport.
        scroll_container = ttk.Frame(self.root)
        scroll_container.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            scroll_container,
            background=self.colors['bg_primary'],
            highlightthickness=0
        )
        v_scrollbar = ttk.Scrollbar(scroll_container, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=v_scrollbar.set)
        v_scrollbar.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)

        # Inner frame that holds all UI widgets
        main_frame = ttk.Frame(self.canvas, padding="15")
        self.canvas.create_window((0, 0), window=main_frame, anchor='nw')

        # Update scroll region whenever size changes
        def _configure_scroll_region(event):
            self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        main_frame.bind('<Configure>', _configure_scroll_region)

        main_frame.columnconfigure(0, weight=1)

        # Bind global mouse wheel for areas that are not individual ScrolledText widgets
        self._bind_canvas_scroll()

        # NOTEBOOK (Tabs)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        builder_tab = ttk.Frame(self.notebook)
        overlay_tab = ttk.Frame(self.notebook)
        settings_tab = ttk.Frame(self.notebook)
        self.notebook.add(builder_tab, text="Listing Builder")
        self.notebook.add(overlay_tab, text="Overlay Assist")
        self.notebook.add(settings_tab, text="Settings & License")

        # === SETTINGS TAB CONTENT ===
        settings_tab.columnconfigure(0, weight=1)
        settings_tab.rowconfigure(0, weight=1)

        # Create scrollable settings container
        settings_canvas = tk.Canvas(settings_tab, background=self.colors['bg_primary'], highlightthickness=0)
        settings_scrollbar = ttk.Scrollbar(settings_tab, orient='vertical', command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=settings_scrollbar.set)

        settings_frame = ttk.Frame(settings_canvas, padding="20")
        settings_canvas.create_window((0, 0), window=settings_frame, anchor='nw')

        # Update scroll region when content changes
        def _configure_settings_scroll(event):
            settings_canvas.configure(scrollregion=settings_canvas.bbox('all'))
        settings_frame.bind('<Configure>', _configure_settings_scroll)

        # Pack canvas and scrollbar
        settings_canvas.pack(side='left', fill='both', expand=True)
        settings_scrollbar.pack(side='right', fill='y')

        # Bind mouse wheel to settings canvas
        def _on_settings_mousewheel(event):
            if event.widget not in (self.preview_text, self.desc_text, self.chat_display):
                delta_units = 0
                if event.delta:
                    delta_units = int(-1 * (event.delta / 120))
                elif getattr(event, 'num', None) in (4, 5):
                    delta_units = -1 if event.num == 4 else 1
                if delta_units:
                    settings_canvas.yview_scroll(delta_units, 'units')
                    return 'break'
        settings_canvas.bind_all('<MouseWheel>', _on_settings_mousewheel)
        settings_canvas.bind_all('<Button-4>', _on_settings_mousewheel)
        settings_canvas.bind_all('<Button-5>', _on_settings_mousewheel)

        # Initialize settings variables
        self._init_settings_vars()

        # Load saved settings
        self._load_settings()

        # Create settings sections
        self._create_api_settings_section(settings_frame)
        self._create_ui_settings_section(settings_frame)
        self._create_app_settings_section(settings_frame)
        self._create_performance_settings_section(settings_frame)
        self._create_storage_settings_section(settings_frame)
        self._create_privacy_settings_section(settings_frame)
        self._create_system_info_section(settings_frame)
        self._create_import_export_section(settings_frame)

        # License section at bottom
        self._create_license_section(settings_frame)

        # === BUILDER TAB CONTENT ===
        builder_tab.columnconfigure(0, weight=1)
        header = ttk.Label(builder_tab, text="🚀 LlamaLister", style='Title.TLabel')
        header.grid(row=0, column=0, pady=(0, 10), sticky=tk.W)

        # Upload section
        upload_frame = ttk.LabelFrame(builder_tab, text="Step 1: Upload Product Images", padding="15")
        upload_frame.grid(row=1, column=0, sticky="we", pady=(0, 10))
        upload_frame.columnconfigure(0, weight=1)

        ttk.Label(upload_frame, text="Select one or more clear photos of your product:").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        btn_frame = ttk.Frame(upload_frame)
        btn_frame.grid(row=1, column=0, sticky="we")
        ttk.Button(btn_frame, text="📁 Choose Images", command=self.upload_images, style='Accent.TButton').pack(side=tk.LEFT, padx=(0, 10))
        self.upload_label = ttk.Label(upload_frame, text="No images selected", foreground=self.colors['text_secondary'])
        self.upload_label.grid(row=2, column=0, sticky=tk.W, pady=(10, 0))

        # Image preview area
        self.preview_text = scrolledtext.ScrolledText(upload_frame, height=5, width=80, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 9), wrap=tk.WORD)
        self.preview_text.grid(row=3, column=0, sticky="we", pady=(10, 0))
        self.preview_text.insert('1.0', "Image previews will appear here after upload...")
        self.preview_text.config(state='disabled')

        # Multi-stage analysis & enterprise listing generation section
        gen_frame = ttk.LabelFrame(builder_tab, text="Step 2: Vision Analysis & Enterprise Listing", padding="15")
        gen_frame.grid(row=2, column=0, sticky="we", pady=(0, 10))
        gen_frame.columnconfigure(0, weight=1)

        ttk.Label(gen_frame, text="Run Scout & Maverick passes separately, then synthesize a high-conversion commercial listing.").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        gen_btn_frame = ttk.Frame(gen_frame)
        gen_btn_frame.grid(row=1, column=0, sticky="we")
        self.btn_scout = ttk.Button(gen_btn_frame, text="🔍 Scout Analysis", command=self.run_scout_analysis, style='Accent.TButton', state='disabled')
        self.btn_scout.pack(side=tk.LEFT, padx=(0, 10))
        self.btn_maverick = ttk.Button(gen_btn_frame, text="🧠 Maverick Analysis", command=self.run_maverick_analysis, state='disabled')
        self.btn_maverick.pack(side=tk.LEFT, padx=(0, 10))
        self.btn_generate_listing = ttk.Button(gen_btn_frame, text="📝 Generate Enterprise Listing", command=self.generate_enterprise_listing, state='disabled')
        self.btn_generate_listing.pack(side=tk.LEFT, padx=(0, 10))
        # Simple mode toggle: when enabled, generator will output a compact field pack only
        self.simple_mode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(gen_frame, text="Simple Output Only", variable=self.simple_mode_var).grid(row=2, column=0, sticky=tk.W, pady=(5, 0))

        # Progress section
        progress_frame = ttk.Frame(gen_frame)
        progress_frame.grid(row=2, column=0, sticky="we", pady=(10, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_frame, mode='indeterminate', length=400)
        self.progress_label = ttk.Label(progress_frame, text="", foreground=self.colors['accent'], font=('Segoe UI', 10, 'italic'))

        # Listing editor section
        editor_frame = ttk.LabelFrame(builder_tab, text="Step 3: Review & Edit Listing", padding="15")
        editor_frame.grid(row=3, column=0, sticky="we", pady=(0, 10))
        editor_frame.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(editor_frame, text="Product Title:", style='Subtitle.TLabel').grid(row=row, column=0, sticky=tk.W, pady=(0, 5), padx=(0, 10))
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(editor_frame, textvariable=self.title_var, width=60)
        self.title_entry.grid(row=row, column=1, sticky="we", pady=(0, 10))
        row += 1
        ttk.Label(editor_frame, text="Description:", style='Subtitle.TLabel').grid(row=row, column=0, sticky="wn", pady=(0, 5), padx=(0, 10))
        self.desc_text = scrolledtext.ScrolledText(editor_frame, width=60, height=8, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 10), insertbackground=self.colors['accent'], wrap=tk.WORD)
        self.desc_text.grid(row=row, column=1, sticky="we", pady=(0, 10))
        row += 1
        ttk.Label(editor_frame, text="Price ($):", style='Subtitle.TLabel').grid(row=row, column=0, sticky=tk.W, pady=(0, 5), padx=(0, 10))
        self.price_var = tk.StringVar()
        self.price_entry = ttk.Entry(editor_frame, textvariable=self.price_var, width=20)
        self.price_entry.grid(row=row, column=1, sticky=tk.W, pady=(0, 10))
        row += 1
        ttk.Label(editor_frame, text="Category:", style='Subtitle.TLabel').grid(row=row, column=0, sticky=tk.W, pady=(0, 5), padx=(0, 10))
        self.category_var = tk.StringVar()
        self.category_entry = ttk.Entry(editor_frame, textvariable=self.category_var, width=40)
        self.category_entry.grid(row=row, column=1, sticky=tk.W, pady=(0, 10))
        row += 1
        ttk.Label(editor_frame, text="Condition:", style='Subtitle.TLabel').grid(row=row, column=0, sticky=tk.W, pady=(0, 5), padx=(0, 10))
        self.condition_var = tk.StringVar(value="used")
        cond_frame = ttk.Frame(editor_frame)
        cond_frame.grid(row=row, column=1, sticky=tk.W, pady=(0, 10))
        ttk.Radiobutton(cond_frame, text="New", variable=self.condition_var, value="new").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(cond_frame, text="Used", variable=self.condition_var, value="used").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(cond_frame, text="Refurbished", variable=self.condition_var, value="refurbished").pack(side=tk.LEFT)
        row += 1
        ttk.Label(editor_frame, text="Target Platforms:", style='Subtitle.TLabel').grid(row=row, column=0, sticky="wn", pady=(0, 5), padx=(0, 10))
        platforms_frame = ttk.Frame(editor_frame)
        platforms_frame.grid(row=row, column=1, sticky="we", pady=(0, 10))
        self.platform_vars = {}
        platforms = ["eBay", "Etsy", "Amazon", "Facebook Marketplace", "Craigslist", "Mercari"]
        for i, platform in enumerate(platforms):
            var = tk.BooleanVar()
            self.platform_vars[platform] = var
            ttk.Checkbutton(platforms_frame, text=platform, variable=var).grid(row=i//3, column=i%3, sticky=tk.W, padx=(0, 10), pady=2)
        row += 1
        action_frame = ttk.Frame(editor_frame)
        action_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(action_frame, text="💾 Save Listing", command=self.save_listing, style='Accent.TButton').pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(action_frame, text="🗑️ Clear Form", command=self.clear_form).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="🔎 Market Research & Price Suggestion", command=self.market_price_suggestion, style='Accent.TButton').pack(side=tk.LEFT, padx=(0, 10))
        # Option to request a more detailed price explanation from Llama
        ttk.Checkbutton(action_frame, text="Detailed", variable=self.detailed_price_var).pack(side=tk.LEFT, padx=(6, 0))

        # Chat section (AI Assistant)
        chat_frame = ttk.LabelFrame(builder_tab, text="AI Assistant Chat", padding="15")
        chat_frame.grid(row=4, column=0, sticky="we", pady=(0, 10))
        chat_frame.columnconfigure(0, weight=1)
        self.chat_display = scrolledtext.ScrolledText(chat_frame, width=80, height=6, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 10), wrap=tk.WORD, insertbackground=self.colors['accent'], state='disabled')
        self.chat_display.grid(row=0, column=0, sticky="we", pady=(0, 10))
        input_frame = ttk.Frame(chat_frame)
        input_frame.grid(row=1, column=0, sticky="we")
        input_frame.columnconfigure(0, weight=1)
        self.chat_input = ttk.Entry(input_frame, width=80, font=('Segoe UI', 10))
        self.chat_input.grid(row=0, column=0, sticky="we", padx=(0, 10))
        self.chat_input.bind('<Return>', lambda e: self.send_chat())
        ttk.Button(input_frame, text="Send", command=self.send_chat, style='Accent.TButton').grid(row=0, column=1)
        self._add_chat_message("System", "👋 Welcome! Upload images and generate a listing, then ask me questions!")

        # Status bar (uses status_var initialized in __init__)
        status_bar = tk.Label(self.root, textvariable=self.status_var, bg=self.colors['bg_tertiary'], fg=self.colors['text'], anchor=tk.W, font=('Segoe UI', 9), padx=10, pady=5)
        status_bar.grid(row=1, column=0, sticky="we")

        # Attach robust scroll bindings (mouse wheel / trackpad)
        self._attach_scroll_bindings([self.preview_text, self.desc_text, self.chat_display])

        # === OVERLAY TAB CONTENT ===
        overlay_tab.columnconfigure(0, weight=1)
        overlay_tab.columnconfigure(1, weight=1)
        ov_header = ttk.Label(overlay_tab, text="🪟 Overlay Assist – Fast External Site Filling", style='Title.TLabel')
        ov_header.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))
        ttk.Label(overlay_tab, text="Select a saved listing and use Paste buttons while your cursor is focused in a browser field.").grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0,5))

        # Listing index panel
        index_frame = ttk.LabelFrame(overlay_tab, text="Saved Listings", padding="10")
        index_frame.grid(row=2, column=0, sticky="nsew", pady=(0,10))
        index_frame.columnconfigure(0, weight=1)
        self.overlay_listbox = tk.Listbox(index_frame, height=12, bg=self.colors['input_bg'], fg=self.colors['text'])
        self.overlay_listbox.grid(row=0, column=0, sticky="nsew")
        overlay_scroll = ttk.Scrollbar(index_frame, orient='vertical', command=self.overlay_listbox.yview)
        overlay_scroll.grid(row=0, column=1, sticky="ns")
        self.overlay_listbox.configure(yscrollcommand=overlay_scroll.set)
        self.overlay_listbox.bind('<<ListboxSelect>>', self._on_overlay_select)
        ttk.Button(index_frame, text="🔄 Refresh", command=self._reload_overlay_listing_index).grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        ttk.Button(index_frame, text="🪟 Launch Transparent Overlay", command=self._launch_overlay_window).grid(row=1, column=0, sticky=tk.E, pady=(5,0))

        # Field pack panel
        field_frame = ttk.LabelFrame(overlay_tab, text="Field Pack & Paste Controls", padding="10")
        field_frame.grid(row=2, column=1, sticky="nsew", pady=(0,10))
        field_frame.columnconfigure(1, weight=1)
        self.ov_title_var = tk.StringVar()
        self.ov_tagline_var = tk.StringVar()
        self.ov_materials_var = tk.StringVar()
        self.ov_dimensions_var = tk.StringVar()
        self.ov_condition_var = tk.StringVar()
        self.ov_price_var = tk.StringVar()
        self.ov_keywords_var = tk.StringVar()
        self.ov_bullets_text = scrolledtext.ScrolledText(field_frame, height=6, bg=self.colors['input_bg'], fg=self.colors['text'], wrap=tk.WORD)

        row_ov = 0
        ttk.Label(field_frame, text="Title:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_title_var).grid(row=row_ov, column=1, sticky="we"); ttk.Button(field_frame, text="Paste", command=lambda: self._start_targeted_paste(self.ov_title_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Tagline:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_tagline_var).grid(row=row_ov, column=1, sticky="we"); ttk.Button(field_frame, text="Paste", command=lambda: self._start_targeted_paste(self.ov_tagline_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Bullets (one per line):").grid(row=row_ov, column=0, sticky=tk.W); self.ov_bullets_text.grid(row=row_ov, column=1, columnspan=2, sticky="we"); row_ov+=1
        ttk.Button(field_frame, text="Paste Bullets", command=lambda: self._start_targeted_paste('\n'.join([l for l in self.ov_bullets_text.get('1.0','end').splitlines() if l.strip()]))) .grid(row=row_ov, column=1, sticky=tk.W, pady=(0,5)); row_ov+=1
        ttk.Label(field_frame, text="Materials:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_materials_var).grid(row=row_ov, column=1, sticky="we"); ttk.Button(field_frame, text="Paste", command=lambda: self._start_targeted_paste(self.ov_materials_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Dimensions:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_dimensions_var).grid(row=row_ov, column=1, sticky="we"); ttk.Button(field_frame, text="Paste", command=lambda: self._start_targeted_paste(self.ov_dimensions_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Condition:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_condition_var).grid(row=row_ov, column=1, sticky="we"); ttk.Button(field_frame, text="Paste", command=lambda: self._start_targeted_paste(self.ov_condition_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Price Range:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_price_var).grid(row=row_ov, column=1, sticky="we"); ttk.Button(field_frame, text="Paste", command=lambda: self._start_targeted_paste(self.ov_price_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="SEO Keywords:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_keywords_var).grid(row=row_ov, column=1, sticky="we"); ttk.Button(field_frame, text="Paste", command=lambda: self._start_targeted_paste(self.ov_keywords_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Button(field_frame, text="Clear Fields", command=self._overlay_clear_fields).grid(row=row_ov, column=1, sticky=tk.E, pady=(5,0))

        # Initial load of listing index
        self.overlay_listings = []
        self._overlay_json_mtime = None  # caching mtime for overlay reload efficiency
        self._reload_overlay_listing_index(force=True)
    def market_price_suggestion(self):
        from market_price_helper import get_market_data_and_price
        title = self.title_var.get().strip()
        desc = self.desc_text.get("1.0", tk.END).strip()
        if not title:
            self._show_error("Please enter a product title before market research.")
            return
        self._show_progress("Fetching market data and price suggestion...")
        def worker():
            try:
                res = get_market_data_and_price(title, desc, detailed=self.detailed_price_var.get())
                # Support both (results, price) and (results, price, detailed_text)
                if isinstance(res, tuple) and len(res) == 3:
                    results, price_suggestion, detailed_text = res
                else:
                    results, price_suggestion = res
                    detailed_text = None

                self._hide_progress()
                # Format results for display
                out = "Market Data Results:\n\n"
                for r in results:
                    out += f"- {r.get('title','(no title)')}\n  {r.get('snippet','')}\n  {r.get('url','')}\n\n"
                out += f"\nSuggested Price Range:\n{price_suggestion}\n"
                if detailed_text:
                    out += "\nDetailed Analysis:\n" + detailed_text
                self._show_market_popup(out)
            except Exception as e:
                self._hide_progress()
                self._show_error(f"Market research failed: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _show_market_popup(self, text):
        win = tk.Toplevel(self.root)
        win.title("Market Research & Price Suggestion")
        win.geometry("700x500")
        win.configure(bg=self.colors['bg_secondary'])
        txt = tk.Text(win, wrap=tk.WORD, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 11), padx=10, pady=10)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert(tk.END, text)
        txt.config(state=tk.DISABLED)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=10)

        # Popup only - chat and overlay UI are created during main UI setup

    def _bind_canvas_scroll(self):
        """Bind mouse wheel events to the canvas for scrolling the whole UI when
        the pointer is NOT over a dedicated text widget (those have their own scroll)."""
        def _on_canvas_mousewheel(event):
            # Ignore if focused widget is a text area with its own scrolling
            if event.widget in (getattr(self, 'preview_text', None),
                                getattr(self, 'desc_text', None),
                                getattr(self, 'chat_display', None)):
                return
            delta_units = 0
            if event.delta:
                # Windows & macOS: event.delta is typically +/-120 multiples
                delta_units = int(-1 * (event.delta / 120))
            elif getattr(event, 'num', None) in (4, 5):  # X11 systems
                delta_units = -1 if event.num == 4 else 1
            if delta_units:
                self.canvas.yview_scroll(delta_units, 'units')
                return 'break'

        # Bind across the application
        self.canvas.bind_all('<MouseWheel>', _on_canvas_mousewheel)
        self.canvas.bind_all('<Button-4>', _on_canvas_mousewheel)
        self.canvas.bind_all('<Button-5>', _on_canvas_mousewheel)


    # === EVENT HANDLERS ===

    def upload_images(self):
        """Handle image upload"""
        filenames = filedialog.askopenfilenames(
            title="Select Product Images",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.gif *.bmp")]
        )
        if filenames:
            self.uploaded_images = list(filenames)
            count = len(self.uploaded_images)

            self.upload_label.config(
                text=f"✅ {count} image{'s' if count != 1 else ''} selected: " +
                     ", ".join([Path(f).name for f in self.uploaded_images]),
                foreground=self.colors['success'])

            # Update preview
            self.preview_text.config(state='normal')
            self.preview_text.delete('1.0', tk.END)
            for i, img_path in enumerate(self.uploaded_images, 1):
                self.preview_text.insert(tk.END, f"{i}. {img_path}\n")
            self.preview_text.config(state='disabled')

            self.btn_scout.config(state='normal')
            self.status_var.set(f"{count} image(s) ready - Run Scout Analysis")

            self._log_interaction("gui", "upload_images",
                                f"Uploaded {count} images")

    # === MULTI-STAGE BUTTON HANDLERS ===
    def run_scout_analysis(self):
        if not self.uploaded_images:
            messagebox.showerror("Error", "Upload images first")
            return
        self._show_progress("Scout vision analysis running...")
        self.btn_scout.config(state='disabled')
        threading.Thread(target=self._scout_analysis_worker, daemon=True).start()

    def run_maverick_analysis(self):
        if not self.uploaded_images:
            messagebox.showerror("Error", "Upload images first")
            return
        self._show_progress("Maverick vision analysis running...")
        self.btn_maverick.config(state='disabled')
        threading.Thread(target=self._maverick_analysis_worker, daemon=True).start()

    def generate_enterprise_listing(self):
        if not (self.scout_json or self.maverick_json):
            messagebox.showerror("Error", "Run at least one vision analysis first")
            return
        self._show_progress("Generating enterprise-grade listing...")
        self.btn_generate_listing.config(state='disabled')
        threading.Thread(target=self._generate_listing_worker, daemon=True).start()

    # === IMAGE ENCODING ===
    def _encode_images(self):
        encoded = []
        for img_path in self.uploaded_images:
            with open(img_path, 'rb') as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode('utf-8')
            ext = Path(img_path).suffix.lower().lstrip('.') or 'jpeg'
            mime_map = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png', 'gif': 'gif', 'bmp': 'bmp', 'webp': 'webp'}
            mime = mime_map.get(ext, 'jpeg')
            encoded.append({"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}})
        return encoded

    # === WORKERS ===
    def _scout_analysis_worker(self):
        try:
            if not self.uploaded_images:
                self._add_chat_message("System", "❌ No images uploaded for Scout analysis")
                return
            self._update_progress("Encoding images (Scout)...")
            image_contents = self._encode_images()
            self._add_chat_message("Debug", f"Scout encoded {len(image_contents)} image(s)")
            scout_prompt = (
                "You are performing a technical product vision audit for high-volume eCommerce listings.\n\n"
                "TASK: Analyze the provided product image(s) and return STRICT JSON ONLY (no prose) with this schema:\n"
                "{\n  \"product_core\": {\n    \"primary_product_type\": \"\",\n    \"variant_keywords\": [],\n    \"dominant_colors\": [],\n    \"materials\": [],\n    \"dimensions_estimate\": \"\",\n    \"style_tags\": []\n  },\n  \"visual_assets\": {\n    \"notable_graphic_elements\": [],\n    \"pattern_summary\": \"\",\n    \"foreground_subjects\": []\n  },\n  \"market_positioning\": {\n    \"suggested_consumer_segments\": [],\n    \"potential_uses\": [],\n    \"seasonality\": []\n  },\n  \"quality_indicators\": {\n    \"craftsmanship_notes\": [],\n    \"wear_observations\": [],\n    \"condition_rating\": \"\"\n  },\n  \"risk_checks\": {\n    \"prohibited_content\": [],\n    \"copyright_or_brand_flags\": []\n  }\n}\n\n"
                "Rules:\n- If size or material cannot be determined visually, use 'UNKNOWN_SIZE', 'UNKNOWN_MATERIAL'.\n"
                "- Never invent licensing or brand info.\n- dominant_colors: basic color terms only.\n"
                "- condition_rating: one of ['new','like_new','gently_used','used','needs_repair'].\n"
                "Return ONLY the JSON."
            )
            content_list = [{"type": "text", "text": scout_prompt}] + image_contents
            payload = {"model": VISION_MODEL_SCOUT, "messages": [{"role": "user", "content": content_list}], "max_completion_tokens": 650, "temperature": 0.2}
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LLAMA_API_KEY}"}
            import requests
            response = requests.post(LLAMA_API_URL, json=payload, headers=headers, timeout=90)
            self._add_chat_message("Debug", f"Scout raw response:\n{response.text}")
            if response.status_code == 200:
                result = response.json()
                raw = result.get("completion_message", {}).get("content", "")
                raw_text = raw.get("text", str(raw)) if isinstance(raw, dict) else str(raw)
                self.scout_raw = raw_text
                self.scout_json = self._parse_json_response(raw_text, {})
                self._add_chat_message("Scout", raw_text)
                self.status_var.set("✅ Scout analysis complete")
                # Enable subsequent steps
                self.btn_maverick.config(state='normal')
                self.btn_generate_listing.config(state='normal')
                self._log_interaction("vision", "scout_analysis", agent_response=raw_text, metadata=self.scout_json)
            else:
                self._add_chat_message("System", f"❌ Scout API error {response.status_code}")
                self.status_var.set("Scout API error")
        except Exception as e:
            self._add_chat_message("System", f"❌ Scout fatal: {e}")
            self.status_var.set(f"Scout fatal error: {e}")
        finally:
            self._hide_progress()
            if self.scout_raw is None:
                self.btn_scout.config(state='normal')

    def _maverick_analysis_worker(self):
        try:
            if not self.uploaded_images:
                self._add_chat_message("System", "❌ No images uploaded for Maverick analysis")
                return
            self._update_progress("Encoding images (Maverick)...")
            image_contents = self._encode_images()
            self._add_chat_message("Debug", f"Maverick encoded {len(image_contents)} image(s)")
            mav_prompt = (
                "You are a product marketing vision strategist. Provide PREMIUM LISTING ENHANCEMENT JSON ONLY.\n"
                "Schema STRICT: {\n  \"title_options\": [],\n  \"feature_bullets\": [],\n  \"long_description_paragraphs\": [],\n  \"seo_keywords\": [],\n  \"target_audiences\": [],\n  \"pricing_insights\": {\n    \"likely_price_band_usd\": \"\",\n    \"value_justification\": \"\"\n  }\n}\n"
                "Guidelines:\n"
                "- Analyze the product type from images and tailor content accordingly (e.g., clothing, electronics, home goods, musical instruments, art, etc.).\n"
                "- Only describe qualities that are visually evident in the image(s).\n"
                "- Do NOT assume the item is handcrafted, handmade, or artisan unless there is clear visual evidence (such as visible hand-stitching, tool marks, or a maker's signature).\n"
                "- For items like guitars, do NOT describe as handcrafted unless you see explicit signs of handcrafting.\n"
                "- Emphasize features, design, and functionality that can be directly observed.\n"
                "- Do NOT infer or invent qualities such as craftsmanship, handmade, or art unless visually confirmed.\n"
                "- Include durability, comfort, style, gift appeal only if these are visually supported.\n"
                "- Realistic price band based on product type and visible quality; if unknown use 'TBD'.\n"
                "- Avoid hallucinating materials, brands, or features not visually evident.\n"
                "- Handle edge cases: vintage items (emphasize history only if visible), collectibles (rarity only if indicated), mass-produced (reliability), custom (uniqueness only if marked).\n"
                "- For ambiguous products, describe only what is visually clear and provide versatile descriptions.\n"
                "- Return ONLY JSON."
            )
            content_list = [{"type": "text", "text": mav_prompt}] + image_contents
            payload = {"model": VISION_MODEL_MAVERICK, "messages": [{"role": "user", "content": content_list}], "max_completion_tokens": 650, "temperature": 0.35}
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LLAMA_API_KEY}"}
            import requests
            response = requests.post(LLAMA_API_URL, json=payload, headers=headers, timeout=90)
            self._add_chat_message("Debug", f"Maverick raw response:\n{response.text}")
            if response.status_code == 200:
                result = response.json()
                raw = result.get("completion_message", {}).get("content", "")
                raw_text = raw.get("text", str(raw)) if isinstance(raw, dict) else str(raw)
                self.maverick_raw = raw_text
                self.maverick_json = self._parse_json_response(raw_text, {})
                self._add_chat_message("Maverick", raw_text)
                self.status_var.set("✅ Maverick analysis complete")
                self.btn_generate_listing.config(state='normal')
                self._log_interaction("vision", "maverick_analysis", agent_response=raw_text, metadata=self.maverick_json)
            else:
                self._add_chat_message("System", f"❌ Maverick API error {response.status_code}")
                self.status_var.set("Maverick API error")
        except Exception as e:
            self._add_chat_message("System", f"❌ Maverick fatal: {e}")
            self.status_var.set(f"Maverick fatal error: {e}")
        finally:
            self._hide_progress()
            if self.maverick_raw is None:
                self.btn_maverick.config(state='normal')

    def _generate_listing_worker(self):
        try:
            self._update_progress("Synthesizing enterprise listing copy...")
            scout_json_str = json.dumps(self.scout_json or {}, indent=2)
            maverick_json_str = json.dumps(self.maverick_json or {}, indent=2)
            if self.simple_mode_var.get():
                aggregator_prompt = (
                    "You are an enterprise marketplace listing generator. Merge the analysis JSON objects below for the product and OUTPUT ONLY a SIMPLE FIELD PACK.\n\n"
                    f"SCOUT_ANALYSIS_JSON:\n{scout_json_str}\n\nMAVERICK_ANALYSIS_JSON:\n{maverick_json_str}\n\n"
                    "Return ONLY the following template filled in (no extra prose, no explanations, no blank lines before/after):\n"
                    "TITLE: <optimized title>\n"
                    "TAGLINE: <short emotional hook>\n"
                    "BULLETS: <pipe-separated 6-8 short feature bullets, no emojis, no trailing periods>\n"
                    "DESCRIPTION: <concise 2 paragraph sales description with explicit UNKNOWN placeholders>\n"
                    "MATERIALS: <materials or UNKNOWN_MATERIAL>\n"
                    "DIMENSIONS: <dimensions or UNKNOWN_SIZE>\n"
                    "PATTERN_STYLE: <style/pattern summary>\n"
                    "CONDITION: <condition statement>\n"
                    "PRICE_RANGE_USD: <e.g. 200-350 or TBD>\n"
                    "SEO_KEYWORDS: <comma-separated lowercase keywords>\n"
                    "PLACEHOLDERS_TO_FILL: <comma-separated list of remaining UNKNOWN_* tokens>"
                )
            else:
                aggregator_prompt = (
                    "You are a master storyteller and eCommerce copywriter specializing in products. Create a compelling, conversion-optimized listing for any product that evokes emotion and desire.\n\n"
                    f"SCOUT_ANALYSIS_JSON:\n{scout_json_str}\n\nMAVERICK_ANALYSIS_JSON:\n{maverick_json_str}\n\n"
                    "DETAILED OUTPUT FORMAT (plain text):\n"
                    "TITLE: <SEO-optimized title emphasizing the unique theme and craftsmanship>\n"
                    "SHORT_TAGLINE: <emotional hook that captures the item's spirit>\n\n"
                    "[FEATURE BULLETS]\n(max 8, start with relevant emojis, focus on emotional benefits and craftsmanship)\n\n"
                    "[DETAILED DESCRIPTION]\n"
                    "Write 2-3 vivid, storytelling paragraphs that transport the reader:\n"
                    "• First paragraph: Paint a picture of the design elements, craftsmanship details, and emotional connection\n"
                    "• Second paragraph: Describe comfort, durability, and how it enhances the space\n"
                    "• Third paragraph (if needed): Personal stories, gift appeal, and timeless value\n"
                    "Use sensory language: textures, colors, the feeling of quality. Make it poetic yet professional.\n\n"
                    "[MATERIALS & CONSTRUCTION]\n"
                    "- Materials: ... (be specific about fabric quality and natural feel)\n"
                    "- Dimensions: ... (use 'To be confirmed' if unknown)\n"
                    "- Pattern Style: ... (describe the motif vividly)\n"
                    "- Technique / Craft Notes: ... (emphasize handmade quality and attention to detail)\n\n"
                    "[CARE & MAINTENANCE]\n"
                    "Gentle care instructions that preserve the beauty and longevity.\n\n"
                    "[IDEAL USE CASES]\n"
                    "Comma-separated scenarios where this item enhances life.\n\n"
                    "[SEO KEYWORDS]\n"
                    "Comma-separated, lower-case, include theme terms, item types, emotional benefits.\n\n"
                    "[CONDITION]\n"
                    "Statement based on condition_rating or placeholder.\n\n"
                    "[PRICING GUIDANCE]\n"
                    "Likely retail range (USD) + value justification emphasizing craftsmanship and emotional value.\n\n"
                    "WRITING STYLE RULES:\n"
                    "• Use vivid, sensory language that evokes the item's unique appeal\n"
                    "• Focus on emotional benefits: comfort, connection, warmth, storytelling\n"
                    "• Highlight craftsmanship as art, not just manufacturing\n"
                    "• Make it aspirational - something people want to own and cherish\n"
                    "• Avoid generic phrases; be specific to the item's theme from the analysis\n"
                    "• Professional tone with poetic flair\n"
                    "• Explicitly state unknowns as 'To be confirmed' or 'UNKNOWN_MATERIAL'\n"
                    "• Do NOT invent materials, brands, or unverified details\n\n"
                    "Then APPEND the following exactly once:\n"
                    "=== SIMPLE FIELD PACK ===\n"
                    "TITLE: <title>\n"
                    "TAGLINE: <hook>\n"
                    "BULLETS: <pipe-separated plain bullets (no emoji)>\n"
                    "MATERIALS: <materials or UNKNOWN_MATERIAL>\n"
                    "DIMENSIONS: <dimensions or UNKNOWN_SIZE>\n"
                    "CONDITION: <condition statement>\n"
                    "PRICE_RANGE_USD: <range or TBD>\n"
                    "SEO_KEYWORDS: <comma-separated keywords>\n"
                    "PLACEHOLDERS_TO_FILL: <comma-separated remaining UNKNOWN_* tokens>"
                )
            payload = {
                "model": LLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": "You generate high-converting professional eCommerce listings."},
                    {"role": "user", "content": aggregator_prompt}
                ],
                "max_completion_tokens": 900,
                "temperature": 0.55
            }
            headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LLAMA_API_KEY}"}
            import requests
            response = requests.post(LLAMA_API_URL, json=payload, headers=headers, timeout=120)
            self._add_chat_message("Debug", f"Listing aggregator raw response:\n{response.text}")
            if response.status_code == 200:
                result = response.json()
                raw = result.get("completion_message", {}).get("content", "")
                listing_text = raw.get("text", str(raw)) if isinstance(raw, dict) else str(raw)
                self.desc_text.delete('1.0', tk.END)
                self.desc_text.insert('1.0', listing_text)
                self._auto_populate_from_listing(listing_text)
                self._maybe_add_generated_to_overlay(listing_text)
                self._add_chat_message("Listing", listing_text)
                self.status_var.set("✅ Enterprise listing generated")
                self._log_interaction("listing", "generate_enterprise", agent_response=listing_text)
            else:
                self._add_chat_message("System", f"❌ Listing API error {response.status_code}")
                self.status_var.set("Listing API error")
        except Exception as e:
            self._add_chat_message("System", f"❌ Listing fatal: {e}")
            self.status_var.set(f"Listing fatal error: {e}")
        finally:
            self._hide_progress()
            self.btn_generate_listing.config(state='normal')

    # === OVERLAY SUPPORT METHODS ===
    def _reload_overlay_listing_index(self, force: bool = False):
        """Reload saved listings from JSON file into listbox with simple mtime caching to
        avoid unnecessary disk reads if file unchanged."""
        try:
            if not LISTINGS_JSON_FILE.exists():
                self.overlay_listings.clear()
                self.overlay_listbox.delete(0, tk.END)
                return
            mtime = LISTINGS_JSON_FILE.stat().st_mtime
            if not force and self._overlay_json_mtime == mtime:
                return  # no changes
            self._overlay_json_mtime = mtime
            raw = LISTINGS_JSON_FILE.read_text(encoding='utf-8').strip()
            data = json.loads(raw) if raw else {}
            self.overlay_listings.clear()
            self.overlay_listbox.delete(0, tk.END)
            if isinstance(data, dict):
                # New format: dictionary keyed by title
                self.overlay_listings = list(data.values())
                for i, entry in enumerate(self.overlay_listings):
                    title = entry.get('title', '(untitled)')[:60]
                    self.overlay_listbox.insert(tk.END, f"{i+1}. {title}")
            elif isinstance(data, list):
                # Old format: array of listings
                self.overlay_listings.extend(data)
                for i, entry in enumerate(self.overlay_listings):
                    title = entry.get('title', '(untitled)')[:60]
                    self.overlay_listbox.insert(tk.END, f"{i+1}. {title}")
        except Exception as e:
            self._add_chat_message('System', f'⚠️ Overlay load failed: {e}')

    def _auto_populate_from_listing(self, listing_text: str):
        """Instantly populate all form fields from listing text, skipping placeholders."""
        try:
            title_match = TITLE_PATTERN.search(listing_text)
            title = title_match.group(1).strip() if title_match else ""
            if title and title.upper() not in ["UNKNOWN", "N/A", "TBD"]:
                self.title_var.set(title[:120])
            else:
                self.title_var.set("")

            price_match = PRICE_RANGE_PATTERN.search(listing_text)
            price = ""
            if price_match:
                raw_range = price_match.group(1)
                if '-' in raw_range or '–' in raw_range:
                    parts = re.findall(r'\d+', raw_range)
                    if len(parts) == 2:
                        try:
                            midpoint = (float(parts[0]) + float(parts[1])) / 2
                            price = f"{midpoint:.2f}"
                        except Exception:
                            pass
                else:
                    digits = re.findall(r'\d+', raw_range)
                    if digits:
                        price = digits[0]
            if price and price.upper() not in ["UNKNOWN", "N/A", "TBD"]:
                self.price_var.set(price)
            else:
                self.price_var.set("")

            condition_match = CONDITION_PATTERN.search(listing_text)
            condition = condition_match.group(1).strip().lower() if condition_match else ""
            valid_conditions = ['new', 'like new', 'gently used', 'used', 'refurbished']
            if condition and condition not in ["unknown", "n/a", "tbd"]:
                for token in valid_conditions:
                    if token in condition:
                        self.condition_var.set(token.replace(' ', '_'))
                        break
                else:
                    self.condition_var.set("")
            else:
                self.condition_var.set("")
        except Exception as e:
            self._add_chat_message('System', f'⚠️ Auto-populate parse issue: {e}')

    def _overlay_clear_fields(self):
        self.ov_title_var.set("")
        self.ov_tagline_var.set("")
        self.ov_materials_var.set("")
        self.ov_dimensions_var.set("")
        self.ov_condition_var.set("")
        self.ov_price_var.set("")
        self.ov_keywords_var.set("")
        self.ov_bullets_text.delete('1.0','end')

    def _on_overlay_select(self, event):
        sel = event.widget.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.overlay_listings):
            return
        entry = self.overlay_listings[idx]
        # prefer description parsing for field pack
        text_blob = entry.get('description','')
        parsed = self._extract_field_pack(text_blob)
        # Fill overlay vars
        self.ov_title_var.set(parsed.get('TITLE', entry.get('title','')))
        self.ov_tagline_var.set(parsed.get('TAGLINE',''))
        bullets = parsed.get('BULLETS', [])
        self.ov_bullets_text.delete('1.0','end')
        for b in bullets:
            self.ov_bullets_text.insert(tk.END, b + '\n')
        self.ov_materials_var.set(parsed.get('MATERIALS',''))
        self.ov_dimensions_var.set(parsed.get('DIMENSIONS',''))
        self.ov_condition_var.set(parsed.get('CONDITION', entry.get('condition','')))
        self.ov_price_var.set(parsed.get('PRICE_RANGE_USD', entry.get('price','')))
        self.ov_keywords_var.set(parsed.get('SEO_KEYWORDS',''))

    def _extract_field_pack(self, text: str):
        """Parse simple field pack if present; return dict."""
        result = {}
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        bullets = []
        for line in lines:
            if ':' in line:
                key, val = line.split(':',1)
                k = key.strip().upper()
                v = val.strip()
                if k in ['TITLE','TAGLINE','MATERIALS','DIMENSIONS','PATTERN_STYLE','CONDITION','PRICE_RANGE_USD','SEO_KEYWORDS','PLACEHOLDERS_TO_FILL']:
                    result[k] = v
            elif '|' in line and not bullets:
                # Possibly bullet pipe line from simple pack
                bullets = [b.strip() for b in line.split('|') if b.strip()]
        if not bullets and 'BULLETS' in result:
            bullets = [b.strip() for b in result['BULLETS'].split('|') if b.strip()]
        if bullets:
            result['BULLETS'] = bullets
        return result

    def _maybe_add_generated_to_overlay(self, listing_text: str):
        """If simple field pack present in generated listing, update overlay fields immediately."""
        parsed = self._extract_field_pack(listing_text)
        if not self._validate_simple_field_pack(parsed):
            return  # do not populate partial / invalid pack to avoid confusion
        if parsed.get('TITLE'):
            self.ov_title_var.set(parsed['TITLE'])
        if parsed.get('TAGLINE'):
            self.ov_tagline_var.set(parsed['TAGLINE'])
        if parsed.get('BULLETS'):
            self.ov_bullets_text.delete('1.0','end')
            for b in parsed['BULLETS']:
                self.ov_bullets_text.insert(tk.END, b+'\n')
        self.ov_materials_var.set(parsed.get('MATERIALS',''))
        self.ov_dimensions_var.set(parsed.get('DIMENSIONS',''))
        self.ov_condition_var.set(parsed.get('CONDITION',''))
        self.ov_price_var.set(parsed.get('PRICE_RANGE_USD',''))
        self.ov_keywords_var.set(parsed.get('SEO_KEYWORDS',''))

    def _validate_simple_field_pack(self, parsed: dict) -> bool:
        """Validate that a parsed simple field pack contains the minimum required keys.
        Returns True if valid enough to use for overlay population."""
        if not parsed:
            return False
        missing = [k for k in SIMPLE_FIELD_PACK_REQUIRED if k not in parsed]
        if len(missing) > len(SIMPLE_FIELD_PACK_REQUIRED) // 2:
            # too many missing fields; treat as invalid
            return False
        return True

    def _paste_text(self, text: str):
        """
        Paste text directly into the currently focused UI element using UI Automation.
        Falls back to clipboard + Ctrl+V simulation if direct insertion fails.
        Provides user feedback in the status bar.
        """
        if not text:
            self.status_var.set("Nothing to paste.")
            return

        # Try direct UI Automation insertion first
        try:
            from pywinauto import Desktop
            desktop = Desktop(backend='uia')
            focused_element = desktop.get_focused_element()
            if focused_element:
                # Try direct text setting first
                if hasattr(focused_element, 'set_text'):
                    focused_element.set_text(text)
                    self.status_var.set("✅ Text pasted directly into focused element.")
                    return
                # Fallback to typing keys
                elif hasattr(focused_element, 'type_keys'):
                    focused_element.type_keys(text)
                    self.status_var.set("✅ Text typed into focused element.")
                    return
        except ImportError:
            pass  # pywinauto not available
        except Exception as e:
            self._add_chat_message("System", f"⚠️ Direct paste failed: {e}. Falling back to clipboard.")

        # Fallback to clipboard + Ctrl+V
        try:
            if PYPERCLIP_AVAILABLE and _pyperclip:
                _pyperclip.copy(text)
            else:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
            time.sleep(0.08)
            if PYAUTOGUI_AVAILABLE and _pyautogui:
                time.sleep(0.12)
                _pyautogui.hotkey('ctrl', 'v')
                self.status_var.set("✅ Pasted via clipboard (fallback).")
            else:
                self.status_var.set("⚠️ pyautogui not available. Text copied to clipboard only.")
        except Exception as e:
            self.status_var.set(f"⚠️ Paste failed: {e}. Text copied to clipboard.")

    def _start_targeted_paste(self, text: str):
        """Start targeted paste mode: change cursor to crosshair, wait for user click."""
        if not text:
            self.status_var.set("Nothing to paste.")
            return

        if not PYNPUT_AVAILABLE:
            self._add_chat_message("System", "⚠️ pynput not available. Using standard paste.")
            self._paste_text(text)
            return

        # Change cursor to crosshair globally
        try:
            import ctypes
            # IDC_CROSS = 32515, OCR_NORMAL = 32512
            ctypes.windll.user32.SetSystemCursor(ctypes.windll.user32.LoadCursorW(None, 32515), 32512)
        except Exception as e:
            self._add_chat_message("System", f"⚠️ Could not change cursor: {e}")

        self.targeting_text = text
        self.status_var.set("Click on target location to paste text...")

        # Start mouse listener
        self.listener = pynput.mouse.Listener(on_click=self._on_target_click)
        self.listener.start()

    def _on_target_click(self, x, y, button, pressed):
        """Handle mouse click in targeted paste mode."""
        if pressed and button == pynput.mouse.Button.left:
            self.listener.stop()

            # Restore cursor
            try:
                import ctypes
                ctypes.windll.user32.SetSystemCursor(ctypes.windll.user32.LoadCursorW(None, 32512), 32512)  # Restore normal
            except Exception:
                pass

            self._do_targeted_paste(x, y, self.targeting_text)
            self.status_var.set("Text pasted to target location")

    def _do_targeted_paste(self, x: int, y: int, text: str):
        """Paste text into element at screen coordinates (x, y)."""
        try:
            from pywinauto import Desktop
            desktop = Desktop(backend='uia')
            element = desktop.from_point(x, y)
            if element:
                if hasattr(element, 'set_text'):
                    element.set_text(text)
                    self.status_var.set("✅ Text pasted directly into target element.")
                elif hasattr(element, 'type_keys'):
                    element.type_keys(text)
                    self.status_var.set("✅ Text typed into target element.")
                else:
                    self._add_chat_message("System", "⚠️ Target element does not support text input.")
                    self._paste_text(text)  # Fallback
            else:
                self._add_chat_message("System", "⚠️ No element found at click location.")
                self._paste_text(text)  # Fallback
        except ImportError:
            self._add_chat_message("System", "⚠️ pywinauto not available for targeted paste.")
            self._paste_text(text)
        except Exception as e:
            self._add_chat_message("System", f"⚠️ Targeted paste failed: {e}")
            self._paste_text(text)  # Fallback

    def _launch_overlay_window(self):
        """Create a semi-transparent, non-focus-stealing, click-through overlay window (Windows only)."""
        try:
            overlay = tk.Toplevel(self.root)
            overlay.title('Listing Field Pack Overlay')
            overlay.geometry('400x500+50+50')
            overlay.attributes('-topmost', True)
            overlay.attributes('-alpha', 0.55)
            frame = ttk.Frame(overlay, padding='6')
            frame.pack(fill='both', expand=True)
            ttk.Label(frame, text='Overlay Field Pack (focus your target field, then click Paste)').pack(anchor='w', pady=(0,4))
            # Paste buttons warn if overlay is focused
            def safe_paste(val):
                # If overlay is focused, warn user
                if overlay.focus_displayof() == overlay:
                    self.status_var.set("⚠️ Overlay window is focused. Click your target field first, then click Paste.")
                self._paste_text(val)
            ttk.Button(frame, text='Paste Title', command=lambda: safe_paste(self.ov_title_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Tagline', command=lambda: safe_paste(self.ov_tagline_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Bullets', command=lambda: safe_paste('\n'.join([l for l in self.ov_bullets_text.get('1.0','end').splitlines() if l.strip()]))).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Materials', command=lambda: safe_paste(self.ov_materials_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Dimensions', command=lambda: safe_paste(self.ov_dimensions_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Condition', command=lambda: safe_paste(self.ov_condition_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Price Range', command=lambda: safe_paste(self.ov_price_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste SEO Keywords', command=lambda: safe_paste(self.ov_keywords_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Close', command=overlay.destroy).pack(fill='x', pady=(10,2))
            # Make overlay non-activating and click-through (Windows only)
            try:
                if sys.platform.startswith('win'):
                    import ctypes
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED = 0x80000
                    WS_EX_TRANSPARENT = 0x20
                    WS_EX_NOACTIVATE = 0x8000000
                    WS_EX_TOOLWINDOW = 0x80
                    hwnd = ctypes.windll.user32.GetParent(overlay.winfo_id())
                    current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    new_style = current | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
            except Exception as e:
                self._add_chat_message('System', f'⚠️ Click-through not fully applied: {e}')
        except Exception as e:
            self._add_chat_message('System', f'❌ Overlay launch failed: {e}')

    def _attach_scroll_bindings(self, widgets):
        """Attach mouse wheel / trackpad scroll bindings to text widgets for cross-platform reliability"""
        def _on_mousewheel(event, widget):
            # Windows / Mac delta handling
            delta = 0
            if event.delta:
                # On Windows event.delta is multiples of 120; on Mac may vary
                delta = int(-1 * (event.delta / 120))
            elif event.num in (4, 5):  # X11 systems
                delta = -1 if event.num == 4 else 1
            if delta:
                widget.yview_scroll(delta, "units")
                return "break"

        for w in widgets:
            w.bind("<MouseWheel>", lambda e, widget=w: _on_mousewheel(e, widget))  # Windows / Mac
            w.bind("<Button-4>", lambda e, widget=w: _on_mousewheel(e, widget))     # Linux scroll up
            w.bind("<Button-5>", lambda e, widget=w: _on_mousewheel(e, widget))     # Linux scroll down
    def _simulate_scroll_test(self):
        """Simulate large content in all scrollable areas to verify scrollability"""
        big_text = "\n".join([f"Line {i}: Lorem ipsum dolor sit amet, consectetur adipiscing elit." for i in range(1, 201)])
        self.preview_text.config(state='normal')
        self.preview_text.delete('1.0', tk.END)
        self.preview_text.insert('1.0', big_text)
        self.preview_text.config(state='disabled')
        self.desc_text.delete('1.0', tk.END)
        self.desc_text.insert('1.0', big_text)
        self.chat_display.insert(tk.END, big_text)
        self.chat_display.see(tk.END)

    def send_chat(self):
        """Send chat message to AI"""
        message = self.chat_input.get().strip()
        if not message:
            return

        self.chat_input.delete(0, tk.END)
        self._add_chat_message("You", message)

        # Get context
        context = {
            "title": self.title_var.get(),
            "description": self.desc_text.get("1.0", tk.END).strip(),
            "price": self.price_var.get(),
            "category": self.category_var.get(),
            "condition": self.condition_var.get()
        }

        threading.Thread(target=self._chat_worker,
                        args=(message, context), daemon=True).start()

    def save_listing(self):
        """Save listing to CSV and memory, with custom filename option"""
        if not self.title_var.get().strip():
            messagebox.showerror("Error", "Please enter a title")
            return

        platforms = [p for p, var in self.platform_vars.items() if var.get()]
        if not platforms:
            messagebox.showerror("Error", "Select at least one platform")
            return

        # Prompt for custom filename (CSV/JSON)
        filetypes = [("CSV file", "*.csv"), ("JSON file", "*.json")]
        save_path = filedialog.asksaveasfilename(
            title="Save Listing As...",
            initialdir=str(LISTINGS_DIR),
            initialfile=f"{self.title_var.get().strip().replace(' ', '_')}",
            filetypes=filetypes,
            defaultextension=".csv"
        )
        if not save_path:
            return  # User cancelled

        # Build listing data using dataclass (clearer semantics)
        listing_obj = Listing.from_form(self)
        listing_row = listing_obj.to_csv_row()

        # Ensure storage directory exists
        try:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Storage Error", f"Could not create storage directory {Path(save_path).parent}: {e}")
            return

        # Save to CSV or JSON based on extension
        ext = Path(save_path).suffix.lower()
        success = False
        if ext == ".csv":
            fieldnames = list(listing_row.keys())
            file_exists = Path(save_path).exists()
            try:
                with open(save_path, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(listing_row)
                success = True
            except Exception as e:
                messagebox.showerror("CSV Error", f"Failed saving CSV: {e}")
                return
        elif ext == ".json":
            json_entry = listing_obj.to_json_entry()
            try:
                existing = {}
                if Path(save_path).exists():
                    with open(save_path, 'r', encoding='utf-8') as jf:
                        raw = jf.read().strip()
                        if raw:
                            existing = json.loads(raw)
                            if not isinstance(existing, dict):
                                # Convert old array format to dict format
                                existing = {entry.get('title', f'listing_{i}'): entry for i, entry in enumerate(existing) if isinstance(entry, dict)}
                existing[listing_obj.title] = json_entry
                with open(save_path, 'w', encoding='utf-8') as jf:
                    json.dump(existing, jf, indent=4)
                success = True
            except Exception as e:
                self._add_chat_message("System", f"⚠️ JSON persistence failed: {e}")
                messagebox.showerror("JSON Error", f"Failed saving JSON: {e}")
                return
        else:
            messagebox.showerror("Error", f"Unsupported file extension: {ext}")
            return

        # Save interaction to memory (if available)
        self._log_interaction(
            "gui", "save_listing",
            user_input=self.title_var.get(),
            agent_response=f"Saved {ext.upper()} file",
            metadata={"path": str(save_path), **listing_row}
        )

        if success:
            messagebox.showinfo(
                "Success",
                f"Listing saved!\n{ext.upper()} file: {save_path}"
            )
            self.status_var.set(f"✅ Saved: {self.title_var.get()} ({ext.upper()} file)")

    def clear_form(self):
        """Clear all form fields"""
        self.uploaded_images = []
        self.current_listing_data = {}

        self.upload_label.config(text="No images selected",
                                foreground=self.colors['text_secondary'])
        self.title_var.set("")
        self.desc_text.delete("1.0", tk.END)
        self.price_var.set("")
        self.category_var.set("")
        self.condition_var.set("used")

        for var in self.platform_vars.values():
            var.set(False)

        self.preview_text.config(state='normal')
        self.preview_text.delete('1.0', tk.END)
        self.preview_text.insert('1.0', "Image previews will appear here after upload...")
        self.preview_text.config(state='disabled')

        # Disable multi-stage buttons on clear
        if hasattr(self, 'btn_scout'):
            self.btn_scout.config(state='disabled')
        if hasattr(self, 'btn_maverick'):
            self.btn_maverick.config(state='disabled')
        if hasattr(self, 'btn_generate_listing'):
            self.btn_generate_listing.config(state='disabled')
        # Removed btn_polish reference (no longer exists)

        self.status_var.set("Form cleared - Upload new images to start")

        self._log_interaction("gui", "clear_form", "Form cleared")

    # === AI WORKERS ===

    # Removed _analyze_images (dead code, not used in single-pipeline version)

    # Removed _final_polish_worker (dead code, not used in single-pipeline version)

    def _chat_worker(self, message, context):
        """Background worker for AI chat"""
        try:
            self.status_var.set("🤖 AI thinking...")

            # Build prompt with context
            if any(context.values()):
                full_prompt = (
                    f"You are an AI marketplace listing assistant.\n\n"
                    f"Current listing draft:\n{json.dumps(context, indent=2)}\n\n"
                    f"User question: {message}"
                )
            else:
                full_prompt = message

            # Call Llama API
            payload = {
                "model": LLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a helpful AI marketplace listing assistant."},
                    {"role": "user", "content": full_prompt}
                ],
                "max_completion_tokens": 500,
                "temperature": 0.7
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {LLAMA_API_KEY}"
            }

            response = requests.post(LLAMA_API_URL, json=payload,
                                    headers=headers, timeout=30)
            response.raise_for_status()

            result = response.json()

            # Parse response
            if "completion_message" in result:
                content = result["completion_message"].get("content", "")
                if isinstance(content, dict):
                    ai_response = content.get("text", str(content))
                else:
                    ai_response = str(content)
            else:
                ai_response = str(result)

            self._add_chat_message("AI", ai_response)
            self.status_var.set("Ready")

            self._log_interaction("chat", "ai_assistant",
                                user_input=message,
                                agent_response=ai_response)

        except Exception as e:
            self._add_chat_message("System", f"❌ Chat error: {str(e)}")
            self.status_var.set("Ready")

    # === HELPER METHODS ===

    def _call_vision_api(self, prompt_text, image_contents, model):
        """Call Llama Vision API"""
        content = [{"type": "text", "text": prompt_text}] + image_contents

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_completion_tokens": 1000,
            "temperature": 0.3
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLAMA_API_KEY}"
        }

        response = requests.post(LLAMA_API_URL, json=payload,
                                headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()

        # Parse Llama response
        if "completion_message" in result:
            content = result["completion_message"].get("content", "")
            if isinstance(content, dict):
                return content.get("text", str(content))
            return str(content)
        return str(result)

    def _parse_json_response(self, response_text, default):
        """Parse JSON from AI response with fallback"""
        try:
            # Try to extract JSON from markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            return json.loads(response_text)
        except:
            return default

    def _populate_form(self):
        """Populate form with generated data"""
        data = self.current_listing_data

        self.title_var.set(data.get("title", ""))

        # Build description
        desc_parts = []
        if data.get("description"):
            desc_parts.append(data["description"])
        if data.get("key_features"):
            desc_parts.append("\n\nKey Features:")
            for feature in data["key_features"]:
                desc_parts.append(f"• {feature}")

        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", "\n".join(desc_parts))

        self.price_var.set(str(data.get("price_suggestion", "")))
        self.category_var.set(data.get("category", ""))
        self.condition_var.set(data.get("condition", "used"))

    def _show_progress(self, message):
        """Show progress indicator"""
        self.progress_label.config(text=f"🔄 {message}")
        self.progress_label.grid(row=0, column=0, sticky=tk.W, pady=(10, 5))
        self.progress.grid(row=1, column=0, sticky="we", pady=(0, 10))
        self.progress.start(10)
        self.status_var.set(message)

    def _update_progress(self, message):
        """Update progress message"""
        self.progress_label.config(text=f"🔄 {message}")
        self.status_var.set(message)

    def _hide_progress(self):
        """Hide progress indicator"""
        self.progress.stop()
        self.progress.grid_forget()
        self.progress_label.grid_forget()

    def _add_chat_message(self, sender, message):
        """Add message to chat display"""
        # Ensure the widget is writable while updating
        try:
            self.chat_display.config(state='normal', wrap=tk.WORD)
            self.chat_display.insert(tk.END, f"[{sender}]\n{message}\n\n")
            self.chat_display.see(tk.END)
        finally:
            try:
                self.chat_display.config(state='disabled')
            except Exception:
                pass
    def _format_listing_preview(self, listing: Listing) -> str:
        """Render a human-readable preview of a saved listing."""
        parts = [
            f"Title: {listing.title}",
            f"Price: {listing.price}",
            f"Category: {listing.category}",
            f"Condition: {listing.condition}"
        ]
        if listing.platforms:
            parts.append(f"Platforms: {', '.join(listing.platforms)}")
        if listing.images:
            parts.append("Images:")
            parts.extend(f"- {Path(img).name}" for img in listing.images)
        if listing.description:
            parts.append("\nDescription:")
            parts.append(listing.description.strip())
        return "\n".join(parts)

    def _show_listing_preview(self, listing: Listing):
        preview_win = tk.Toplevel(self.root)
        preview_win.title("Listing Preview")
        preview_win.geometry("600x500")
        preview_win.configure(bg=self.colors['bg_secondary'])
        text = tk.Text(preview_win, wrap=tk.WORD, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 11), padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True)
        text.insert(tk.END, self._format_listing_preview(listing))
        text.config(state=tk.DISABLED)
        ttk.Button(preview_win, text="Close", command=preview_win.destroy).pack(pady=10)

    def _show_error(self, msg):
        err_win = tk.Toplevel(self.root)
        err_win.title("Error")
        err_win.geometry("500x220")
        err_win.configure(bg=self.colors['bg_secondary'])

        # Use a compact message with optional details to avoid huge red dumps
        frame = ttk.Frame(err_win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        short_msg = msg
        show_details_needed = False
        try:
            if isinstance(msg, str) and len(msg) > 300:
                short_msg = msg[:300] + "\n\n(Truncated) Click Details to view more"
                show_details_needed = True
        except Exception:
            short_msg = str(msg)

        label = tk.Label(frame, text=short_msg, wraplength=460, justify=tk.LEFT, bg=self.colors['bg_secondary'], fg=self.colors['error'], font=('Segoe UI', 11), padx=10, pady=10)
        label.pack(fill=tk.BOTH, expand=False)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(8, 0))

        def _show_details():
            detail_win = tk.Toplevel(err_win)
            detail_win.title("Error Details")
            detail_win.geometry("700x500")
            detail_win.configure(bg=self.colors['bg_secondary'])
            txt = scrolledtext.ScrolledText(detail_win, wrap=tk.WORD, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 10))
            txt.pack(fill=tk.BOTH, expand=True)
            try:
                txt.insert(tk.END, msg)
            except Exception:
                txt.insert(tk.END, str(msg))
            txt.config(state=tk.DISABLED)
            ttk.Button(detail_win, text="Close", command=detail_win.destroy).pack(pady=6)

        if show_details_needed:
            ttk.Button(btn_frame, text="Details", command=_show_details).pack(side=tk.RIGHT, padx=(0, 8))

        ttk.Button(btn_frame, text="Close", command=err_win.destroy).pack(side=tk.RIGHT)

    def _log_interaction(self, interaction_type, method, user_input=None,
                        agent_response=None, success=True, metadata=None):
        """Log interaction to memory service"""
        if self.memory_service:
            try:
                self.memory_service.log_interaction(
                    interaction_type=interaction_type,
                    method=method,
                    user_input=user_input,
                    agent_response=agent_response,
                    success=success,
                    session_id=self.session_id,
                    metadata=metadata
                )
            except Exception as e:
                print(f"⚠️ Memory log failed: {e}")

    def _on_data_change(self, *args):
        """Track data changes"""
        # Could implement auto-save or change tracking here
        pass

    def _refresh_stats(self):
        """Refresh memory statistics"""
        if self.memory_service:
            stats = self.memory_service.get_stats()
            stats_text = f"""Total Interactions: {stats['total_interactions']}
Active Sessions: {stats['active_sessions']}
Knowledge Entries: {stats['knowledge_entries']}
Recent Activity (24h): {stats['recent_interactions']}
Session ID: {self.session_id}"""
            self.stats_label.config(text=stats_text)

    def _load_history(self):
        """Load recent history from memory"""
        if not self.memory_service:
            self.history_display.insert(tk.END, "Memory service not available\n")
            return

        try:
            interactions = self.memory_service.get_recent_interactions(limit=20)

            self.history_display.delete("1.0", tk.END)

            for interaction in interactions:
                timestamp = interaction.get('timestamp', '')
                method = interaction.get('method', '')
                user_input = interaction.get('user_input', '')
                response = interaction.get('agent_response', '')

                self.history_display.insert(tk.END,
                    f"[{timestamp}] {method}\n"
                    f"Input: {user_input[:100]}...\n"
                    f"Response: {response[:100]}...\n\n")

        except Exception as e:
            self.history_display.insert(tk.END, f"Error loading history: {e}\n")

    # === SETTINGS MANAGEMENT METHODS ===

    def _init_settings_vars(self):
        """Initialize all settings variables"""
        # API Settings
        self.api_key_var = tk.StringVar(value=LLAMA_API_KEY)
        self.api_url_var = tk.StringVar(value=LLAMA_API_URL)
        self.vision_model_scout_var = tk.StringVar(value=VISION_MODEL_SCOUT)
        self.vision_model_maverick_var = tk.StringVar(value=VISION_MODEL_MAVERICK)
        self.chat_model_var = tk.StringVar(value=LLAMA_MODEL)
        self.api_timeout_var = tk.IntVar(value=120)

        # UI Settings
        self.theme_var = tk.StringVar(value="dark")
        self.font_size_var = tk.IntVar(value=10)
        self.show_preview_var = tk.BooleanVar(value=True)
        self.auto_scroll_var = tk.BooleanVar(value=True)
        self.compact_mode_var = tk.BooleanVar(value=False)

        # Application Settings
        self.auto_save_var = tk.BooleanVar(value=True)
        self.memory_enabled_var = tk.BooleanVar(value=MEMORY_AVAILABLE)
        self.log_level_var = tk.StringVar(value="INFO")
        self.max_history_var = tk.IntVar(value=100)
        self.backup_frequency_var = tk.StringVar(value="weekly")

        # Performance Settings
        self.max_concurrent_var = tk.IntVar(value=3)
        self.cache_enabled_var = tk.BooleanVar(value=True)
        self.image_compression_var = tk.BooleanVar(value=True)
        self.batch_processing_var = tk.BooleanVar(value=False)

        # Storage Settings
        self.storage_format_var = tk.StringVar(value="json")
        self.storage_dir_var = tk.StringVar(value=str(LISTINGS_DIR))
        self.auto_backup_var = tk.BooleanVar(value=True)
        self.compression_enabled_var = tk.BooleanVar(value=False)

        # Privacy Settings
        self.data_retention_days_var = tk.IntVar(value=365)
        self.analytics_enabled_var = tk.BooleanVar(value=False)
        self.error_reporting_var = tk.BooleanVar(value=True)
        self.usage_stats_var = tk.BooleanVar(value=False)

        # Settings file path
        self.settings_file = LISTINGS_DIR / "settings.json"

    def _load_settings(self):
        """Load settings from JSON file"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                # Load API settings
                self.api_key_var.set(settings.get('api_key', LLAMA_API_KEY))
                self.api_url_var.set(settings.get('api_url', LLAMA_API_URL))
                self.vision_model_scout_var.set(settings.get('vision_model_scout', VISION_MODEL_SCOUT))
                self.vision_model_maverick_var.set(settings.get('vision_model_maverick', VISION_MODEL_MAVERICK))
                self.chat_model_var.set(settings.get('chat_model', LLAMA_MODEL))
                self.api_timeout_var.set(settings.get('api_timeout', 120))

                # Load UI settings
                self.theme_var.set(settings.get('theme', 'dark'))
                self.font_size_var.set(settings.get('font_size', 10))
                self.show_preview_var.set(settings.get('show_preview', True))
                self.auto_scroll_var.set(settings.get('auto_scroll', True))
                self.compact_mode_var.set(settings.get('compact_mode', False))

                # Load app settings
                self.auto_save_var.set(settings.get('auto_save', True))
                self.memory_enabled_var.set(settings.get('memory_enabled', MEMORY_AVAILABLE))
                self.log_level_var.set(settings.get('log_level', 'INFO'))
                self.max_history_var.set(settings.get('max_history', 100))
                self.backup_frequency_var.set(settings.get('backup_frequency', 'weekly'))

                # Load performance settings
                self.max_concurrent_var.set(settings.get('max_concurrent', 3))
                self.cache_enabled_var.set(settings.get('cache_enabled', True))
                self.image_compression_var.set(settings.get('image_compression', True))
                self.batch_processing_var.set(settings.get('batch_processing', False))

                # Load storage settings
                self.storage_format_var.set(settings.get('storage_format', 'json'))
                self.storage_dir_var.set(settings.get('storage_dir', str(LISTINGS_DIR)))
                self.auto_backup_var.set(settings.get('auto_backup', True))
                self.compression_enabled_var.set(settings.get('compression_enabled', False))

                # Load privacy settings
                self.data_retention_days_var.set(settings.get('data_retention_days', 365))
                self.analytics_enabled_var.set(settings.get('analytics_enabled', False))
                self.error_reporting_var.set(settings.get('error_reporting', True))
                self.usage_stats_var.set(settings.get('usage_stats', False))

        except Exception as e:
            print(f"⚠️ Failed to load settings: {e}")

    def _save_settings(self):
        """Save current settings to JSON file"""
        try:
            settings = {
                # API Settings
                'api_key': self.api_key_var.get(),
                'api_url': self.api_url_var.get(),
                'vision_model_scout': self.vision_model_scout_var.get(),
                'vision_model_maverick': self.vision_model_maverick_var.get(),
                'chat_model': self.chat_model_var.get(),
                'api_timeout': self.api_timeout_var.get(),

                # UI Settings
                'theme': self.theme_var.get(),
                'font_size': self.font_size_var.get(),
                'show_preview': self.show_preview_var.get(),
                'auto_scroll': self.auto_scroll_var.get(),
                'compact_mode': self.compact_mode_var.get(),

                # Application Settings
                'auto_save': self.auto_save_var.get(),
                'memory_enabled': self.memory_enabled_var.get(),
                'log_level': self.log_level_var.get(),
                'max_history': self.max_history_var.get(),
                'backup_frequency': self.backup_frequency_var.get(),

                # Performance Settings
                'max_concurrent': self.max_concurrent_var.get(),
                'cache_enabled': self.cache_enabled_var.get(),
                'image_compression': self.image_compression_var.get(),
                'batch_processing': self.batch_processing_var.get(),

                # Storage Settings
                'storage_format': self.storage_format_var.get(),
                'storage_dir': self.storage_dir_var.get(),
                'auto_backup': self.auto_backup_var.get(),
                'compression_enabled': self.compression_enabled_var.get(),

                # Privacy Settings
                'data_retention_days': self.data_retention_days_var.get(),
                'analytics_enabled': self.analytics_enabled_var.get(),
                'error_reporting': self.error_reporting_var.get(),
                'usage_stats': self.usage_stats_var.get(),

                # Metadata
                'last_saved': datetime.now().isoformat(),
                'version': '1.0.0'
            }

            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2)

            self.status_var.set("✅ Settings saved successfully")

        except Exception as e:
            self.status_var.set(f"❌ Failed to save settings: {e}")

    def _reset_settings_to_defaults(self):
        """Reset all settings to defaults"""
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset all settings to defaults? This cannot be undone."):
            try:
                # Reset API settings
                self.api_key_var.set(LLAMA_API_KEY)
                self.api_url_var.set(LLAMA_API_URL)
                self.vision_model_scout_var.set(VISION_MODEL_SCOUT)
                self.vision_model_maverick_var.set(VISION_MODEL_MAVERICK)
                self.chat_model_var.set(LLAMA_MODEL)
                self.api_timeout_var.set(120)

                # Reset UI settings
                self.theme_var.set("dark")
                self.font_size_var.set(10)
                self.show_preview_var.set(True)
                self.auto_scroll_var.set(True)
                self.compact_mode_var.set(False)

                # Reset app settings
                self.auto_save_var.set(True)
                self.memory_enabled_var.set(MEMORY_AVAILABLE)
                self.log_level_var.set("INFO")
                self.max_history_var.set(100)
                self.backup_frequency_var.set("weekly")

                # Reset performance settings
                self.max_concurrent_var.set(3)
                self.cache_enabled_var.set(True)
                self.image_compression_var.set(True)
                self.batch_processing_var.set(False)

                # Reset storage settings
                self.storage_format_var.set("json")
                self.storage_dir_var.set(str(LISTINGS_DIR))
                self.auto_backup_var.set(True)
                self.compression_enabled_var.set(False)

                # Reset privacy settings
                self.data_retention_days_var.set(365)
                self.analytics_enabled_var.set(False)
                self.error_reporting_var.set(True)
                self.usage_stats_var.set(False)

                self._save_settings()
                messagebox.showinfo("Reset Complete", "All settings have been reset to defaults.")

            except Exception as e:
                messagebox.showerror("Reset Failed", f"Failed to reset settings: {e}")

    def _export_settings(self):
        """Export settings to a file"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="Export Settings",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            if file_path:
                # Load current settings
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(settings, f, indent=2)

                messagebox.showinfo("Export Complete", f"Settings exported to {file_path}")

        except Exception as e:
            messagebox.showerror("Export Failed", f"Failed to export settings: {e}")

    def _import_settings(self):
        """Import settings from a file"""
        try:
            file_path = filedialog.askopenfilename(
                title="Import Settings",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
            )
            if file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    imported_settings = json.load(f)

                # Validate imported settings
                required_keys = ['api_key', 'api_url', 'theme']
                if not all(key in imported_settings for key in required_keys):
                    messagebox.showerror("Import Failed", "Invalid settings file format.")
                    return

                # Apply imported settings
                for key, value in imported_settings.items():
                    if hasattr(self, f'{key}_var'):
                        var = getattr(self, f'{key}_var')
                        if isinstance(var, tk.BooleanVar):
                            var.set(bool(value))
                        elif isinstance(var, tk.IntVar):
                            var.set(int(value))
                        elif isinstance(var, tk.StringVar):
                            var.set(str(value))

                self._save_settings()
                messagebox.showinfo("Import Complete", "Settings imported successfully. Restart may be required for some changes.")

        except Exception as e:
            messagebox.showerror("Import Failed", f"Failed to import settings: {e}")

    # === SETTINGS UI CREATION METHODS ===

    def _create_api_settings_section(self, parent):
        """Create API configuration section"""
        api_frame = ttk.LabelFrame(parent, text="🔑 API Configuration", padding="15")
        api_frame.pack(fill='x', pady=(0, 15))

        row = 0
        # API Key
        ttk.Label(api_frame, text="Llama API Key:").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Entry(api_frame, textvariable=self.api_key_var, width=50, show="*").grid(row=row, column=1, sticky='we', pady=2, padx=(10, 0))
        ttk.Button(api_frame, text="👁️", width=3, command=self._toggle_api_key_visibility).grid(row=row, column=2, pady=2)
        row += 1

        # API URL
        ttk.Label(api_frame, text="API Endpoint:").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Entry(api_frame, textvariable=self.api_url_var, width=50).grid(row=row, column=1, columnspan=2, sticky='we', pady=2, padx=(10, 0))
        row += 1

        # Models
        ttk.Label(api_frame, text="Vision Model (Scout):").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Entry(api_frame, textvariable=self.vision_model_scout_var, width=50).grid(row=row, column=1, columnspan=2, sticky='we', pady=2, padx=(10, 0))
        row += 1

        ttk.Label(api_frame, text="Vision Model (Maverick):").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Entry(api_frame, textvariable=self.vision_model_maverick_var, width=50).grid(row=row, column=1, columnspan=2, sticky='we', pady=2, padx=(10, 0))
        row += 1

        ttk.Label(api_frame, text="Chat Model:").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Entry(api_frame, textvariable=self.chat_model_var, width=50).grid(row=row, column=1, columnspan=2, sticky='we', pady=2, padx=(10, 0))
        row += 1

        # Timeout
        ttk.Label(api_frame, text="API Timeout (seconds):").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Spinbox(api_frame, from_=10, to=300, textvariable=self.api_timeout_var, width=10).grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))

        # Configure grid weights
        api_frame.columnconfigure(1, weight=1)

    def _create_ui_settings_section(self, parent):
        """Create UI preferences section"""
        ui_frame = ttk.LabelFrame(parent, text="🎨 UI Preferences", padding="15")
        ui_frame.pack(fill='x', pady=(0, 15))

        row = 0
        # Theme
        ttk.Label(ui_frame, text="Theme:").grid(row=row, column=0, sticky='w', pady=2)
        theme_combo = ttk.Combobox(ui_frame, textvariable=self.theme_var, values=["dark", "light", "auto"], state="readonly", width=15)
        theme_combo.grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))
        row += 1

        # Font Size
        ttk.Label(ui_frame, text="Font Size:").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Spinbox(ui_frame, from_=8, to=16, textvariable=self.font_size_var, width=10).grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))
        row += 1

        # Checkboxes
        ttk.Checkbutton(ui_frame, text="Show image previews", variable=self.show_preview_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1
        ttk.Checkbutton(ui_frame, text="Auto-scroll to new content", variable=self.auto_scroll_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1
        ttk.Checkbutton(ui_frame, text="Compact mode (reduced spacing)", variable=self.compact_mode_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)

    def _create_app_settings_section(self, parent):
        """Create application settings section"""
        app_frame = ttk.LabelFrame(parent, text="⚙️ Application Settings", padding="15")
        app_frame.pack(fill='x', pady=(0, 15))

        row = 0
        # Auto-save
        ttk.Checkbutton(app_frame, text="Auto-save listings", variable=self.auto_save_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1

        # Memory service
        memory_check = ttk.Checkbutton(app_frame, text="Enable memory service", variable=self.memory_enabled_var)
        memory_check.grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        if not MEMORY_AVAILABLE:
            memory_check.config(state='disabled')
        row += 1

        # Log level
        ttk.Label(app_frame, text="Log Level:").grid(row=row, column=0, sticky='w', pady=2)
        log_combo = ttk.Combobox(app_frame, textvariable=self.log_level_var, values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly", width=15)
        log_combo.grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))
        row += 1

        # Max history
        ttk.Label(app_frame, text="Max History Items:").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Spinbox(app_frame, from_=10, to=1000, textvariable=self.max_history_var, width=10).grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))
        row += 1

        # Backup frequency
        ttk.Label(app_frame, text="Backup Frequency:").grid(row=row, column=0, sticky='w', pady=2)
        backup_combo = ttk.Combobox(app_frame, textvariable=self.backup_frequency_var, values=["daily", "weekly", "monthly", "never"], state="readonly", width=15)
        backup_combo.grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))

    def _create_performance_settings_section(self, parent):
        """Create performance settings section"""
        perf_frame = ttk.LabelFrame(parent, text="🚀 Performance Settings", padding="15")
        perf_frame.pack(fill='x', pady=(0, 15))

        row = 0
        # Max concurrent operations
        ttk.Label(perf_frame, text="Max Concurrent Operations:").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Spinbox(perf_frame, from_=1, to=10, textvariable=self.max_concurrent_var, width=10).grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))
        row += 1

        # Checkboxes
        ttk.Checkbutton(perf_frame, text="Enable caching", variable=self.cache_enabled_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1
        ttk.Checkbutton(perf_frame, text="Compress images before upload", variable=self.image_compression_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1
        ttk.Checkbutton(perf_frame, text="Enable batch processing", variable=self.batch_processing_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)

    def _create_storage_settings_section(self, parent):
        """Create storage settings section"""
        storage_frame = ttk.LabelFrame(parent, text="💾 Storage Settings", padding="15")
        storage_frame.pack(fill='x', pady=(0, 15))

        row = 0
        # Storage format
        ttk.Label(storage_frame, text="Default Storage Format:").grid(row=row, column=0, sticky='w', pady=2)
        format_combo = ttk.Combobox(storage_frame, textvariable=self.storage_format_var, values=["json", "csv"], state="readonly", width=15)
        format_combo.grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))
        row += 1

        # Storage directory
        ttk.Label(storage_frame, text="Storage Directory:").grid(row=row, column=0, sticky='w', pady=2)
        dir_frame = ttk.Frame(storage_frame)
        dir_frame.grid(row=row, column=1, sticky='we', pady=2, padx=(10, 0))
        ttk.Entry(dir_frame, textvariable=self.storage_dir_var, width=30).pack(side='left', fill='x', expand=True)
        ttk.Button(dir_frame, text="📁", width=3, command=self._browse_storage_dir).pack(side='right')
        row += 1

        # Checkboxes
        ttk.Checkbutton(storage_frame, text="Auto-backup listings", variable=self.auto_backup_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1
        ttk.Checkbutton(storage_frame, text="Compress stored files", variable=self.compression_enabled_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)

    def _create_privacy_settings_section(self, parent):
        """Create privacy settings section"""
        privacy_frame = ttk.LabelFrame(parent, text="🔒 Privacy & Security", padding="15")
        privacy_frame.pack(fill='x', pady=(0, 15))

        row = 0
        # Data retention
        ttk.Label(privacy_frame, text="Data Retention (days):").grid(row=row, column=0, sticky='w', pady=2)
        ttk.Spinbox(privacy_frame, from_=30, to=3650, textvariable=self.data_retention_days_var, width=10).grid(row=row, column=1, sticky='w', pady=2, padx=(10, 0))
        row += 1

        # Checkboxes
        ttk.Checkbutton(privacy_frame, text="Enable analytics", variable=self.analytics_enabled_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1
        ttk.Checkbutton(privacy_frame, text="Send error reports", variable=self.error_reporting_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)
        row += 1
        ttk.Checkbutton(privacy_frame, text="Share usage statistics", variable=self.usage_stats_var).grid(row=row, column=0, columnspan=2, sticky='w', pady=2)

    def _create_system_info_section(self, parent):
        """Create system information section"""
        info_frame = ttk.LabelFrame(parent, text="ℹ️ System Information", padding="15")
        info_frame.pack(fill='x', pady=(0, 15))

        # System stats
        stats_text = f"""Python Version: {sys.version.split()[0]}
Platform: {sys.platform}
Tkinter Version: {tk.TkVersion}
Memory Service: {'Available' if MEMORY_AVAILABLE else 'Not Available'}
PyAutoGUI: {'Available' if PYAUTOGUI_AVAILABLE else 'Not Available'}
Pyperclip: {'Available' if PYPERCLIP_AVAILABLE else 'Not Available'}
Pynput: {'Available' if PYNPUT_AVAILABLE else 'Not Available'}
Working Directory: {Path.cwd()}
Settings File: {self.settings_file}"""

        stats_label = tk.Label(info_frame, text=stats_text, justify='left', anchor='w', bg=self.colors['bg_secondary'], fg=self.colors['text'], font=('Segoe UI', 9), padx=10, pady=10)
        stats_label.pack(fill='x')

        # Action buttons
        btn_frame = ttk.Frame(info_frame)
        btn_frame.pack(fill='x', pady=(10, 0))
        ttk.Button(btn_frame, text="🔄 Refresh Stats", command=self._refresh_system_info).pack(side='left', padx=(0, 10))
        ttk.Button(btn_frame, text="🗂️ Open Logs Directory", command=self._open_logs_dir).pack(side='left', padx=(0, 10))
        ttk.Button(btn_frame, text="🧹 Clear Cache", command=self._clear_cache).pack(side='left')

    def _create_import_export_section(self, parent):
        """Create import/export section"""
        ie_frame = ttk.LabelFrame(parent, text="📥 Import/Export", padding="15")
        ie_frame.pack(fill='x', pady=(0, 15))

        # Import/Export buttons
        ie_btn_frame = ttk.Frame(ie_frame)
        ie_btn_frame.pack(fill='x', pady=(0, 10))
        ttk.Button(ie_btn_frame, text="📤 Export Settings", command=self._export_settings).pack(side='left', padx=(0, 10))
        ttk.Button(ie_btn_frame, text="📥 Import Settings", command=self._import_settings).pack(side='left', padx=(0, 10))
        ttk.Button(ie_btn_frame, text="💾 Save Settings", command=self._save_settings, style='Accent.TButton').pack(side='right')

        # Reset button
        reset_frame = ttk.Frame(ie_frame)
        reset_frame.pack(fill='x')
        ttk.Button(reset_frame, text="🔄 Reset to Defaults", command=self._reset_settings_to_defaults).pack(side='left')

    def _create_license_section(self, parent):
        """Create license section at bottom"""
        license_frame = ttk.LabelFrame(parent, text="📄 License", padding="15")
        license_frame.pack(fill='x', pady=(0, 15))

        # App acknowledgement
        ack_label = ttk.Label(license_frame, text="LlamaLister\nCreated by John Daniel Dondlinger", style='Title.TLabel')
        ack_label.pack(pady=(0, 10))

        # License text
        license_text = (
            "MIT License\n\n"
            "Copyright (c) 2025 John Daniel Dondlinger\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            "of this software and associated documentation files (the \"Software\"), to deal\n"
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
            "SOFTWARE."
        )

        license_box = scrolledtext.ScrolledText(license_frame, width=80, height=12, wrap=tk.WORD, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 9))
        license_box.pack(fill='x')
        license_box.insert('1.0', license_text)
        license_box.config(state='disabled')

    # === SETTINGS HELPER METHODS ===

    def _toggle_api_key_visibility(self):
        """Toggle API key visibility"""
        # This would need to be implemented with a proper toggle mechanism
        # For now, just show a message
        current = self.api_key_var.get()
        if current and not current.startswith('*'):
            masked = '*' * len(current)
            messagebox.showinfo("API Key", f"Current key ends with: ...{current[-4:] if len(current) > 4 else current}")
        else:
            messagebox.showinfo("API Key", "Key is already masked for security.")

    def _browse_storage_dir(self):
        """Browse for storage directory"""
        dir_path = filedialog.askdirectory(title="Select Storage Directory", initialdir=self.storage_dir_var.get())
        if dir_path:
            self.storage_dir_var.set(dir_path)

    def _refresh_system_info(self):
        """Refresh system information display"""
        # This would refresh the stats display - for now just show a message
        messagebox.showinfo("System Info", "System information refreshed.")

    def _open_logs_dir(self):
        """Open logs directory"""
        logs_dir = Path("logs")
        if not logs_dir.exists():
            logs_dir.mkdir(parents=True)
        try:
            import subprocess
            if sys.platform == "win32":
                subprocess.run(["explorer", str(logs_dir)])
            elif sys.platform == "darwin":
                subprocess.run(["open", str(logs_dir)])
            else:
                subprocess.run(["xdg-open", str(logs_dir)])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open logs directory: {e}")

    def _clear_cache(self):
        """Clear application cache"""
        try:
            # Clear any cached data
            cache_dir = Path("__pycache__")
            if cache_dir.exists():
                import shutil
                shutil.rmtree(cache_dir)
                messagebox.showinfo("Cache Cleared", "Application cache has been cleared.")
            else:
                messagebox.showinfo("Cache", "No cache files found to clear.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear cache: {e}")


def main():
    root = tk.Tk()
    app = ListingApp(root)
    root.mainloop()

    # Cleanup on exit
    if app.memory_service and app.session_id:
        try:
            app.memory_service.end_session(app.session_id)
            print(f"✅ Session ended: {app.session_id}")
        except:
            pass


if __name__ == "__main__":
    main()
