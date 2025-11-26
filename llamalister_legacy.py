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
from dataclasses import dataclass, asdict
try:
    import pyautogui  # for simulated paste hotkey
    PYAUTOGUI_AVAILABLE = True
except Exception:
    PYAUTOGUI_AVAILABLE = False
try:
    import pyperclip  # for reliable clipboard set
    PYPERCLIP_AVAILABLE = True
except Exception:
    PYPERCLIP_AVAILABLE = False
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
        self.root.title("LlamaLister - AI Product Listing Assistant")
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
        scroll_container.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
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
        self.notebook.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        builder_tab = ttk.Frame(self.notebook)
        overlay_tab = ttk.Frame(self.notebook)
        self.notebook.add(builder_tab, text="Listing Builder")
        self.notebook.add(overlay_tab, text="Overlay Assist")

        # === BUILDER TAB CONTENT ===
        builder_tab.columnconfigure(0, weight=1)
        header = ttk.Label(builder_tab, text="🚀 AI Product Listing Assistant", style='Title.TLabel')
        header.grid(row=0, column=0, pady=(0, 10), sticky=tk.W)

        # Upload section
        upload_frame = ttk.LabelFrame(builder_tab, text="Step 1: Upload Product Images", padding="15")
        upload_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        upload_frame.columnconfigure(0, weight=1)

        ttk.Label(upload_frame, text="Select one or more clear photos of your product:").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        btn_frame = ttk.Frame(upload_frame)
        btn_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        ttk.Button(btn_frame, text="📁 Choose Images", command=self.upload_images, style='Accent.TButton').pack(side=tk.LEFT, padx=(0, 10))
        self.upload_label = ttk.Label(upload_frame, text="No images selected", foreground=self.colors['text_secondary'])
        self.upload_label.grid(row=2, column=0, sticky=tk.W, pady=(10, 0))

        # Image preview area
        self.preview_text = scrolledtext.ScrolledText(upload_frame, height=5, width=80, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 9), wrap=tk.WORD)
        self.preview_text.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        self.preview_text.insert('1.0', "Image previews will appear here after upload...")
        self.preview_text.config(state='disabled')

        # Multi-stage analysis & enterprise listing generation section
        gen_frame = ttk.LabelFrame(builder_tab, text="Step 2: Vision Analysis & Enterprise Listing", padding="15")
        gen_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        gen_frame.columnconfigure(0, weight=1)

        ttk.Label(gen_frame, text="Run Scout & Maverick passes separately, then synthesize a high-conversion commercial listing.").grid(row=0, column=0, sticky=tk.W, pady=(0, 10))
        gen_btn_frame = ttk.Frame(gen_frame)
        gen_btn_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
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
        progress_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(progress_frame, mode='indeterminate', length=400)
        self.progress_label = ttk.Label(progress_frame, text="", foreground=self.colors['accent'], font=('Segoe UI', 10, 'italic'))

        # Listing editor section
        editor_frame = ttk.LabelFrame(builder_tab, text="Step 3: Review & Edit Listing", padding="15")
        editor_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        editor_frame.columnconfigure(1, weight=1)
        row = 0
        ttk.Label(editor_frame, text="Product Title:", style='Subtitle.TLabel').grid(row=row, column=0, sticky=tk.W, pady=(0, 5), padx=(0, 10))
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(editor_frame, textvariable=self.title_var, width=60)
        self.title_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=(0, 10))
        row += 1
        ttk.Label(editor_frame, text="Description:", style='Subtitle.TLabel').grid(row=row, column=0, sticky=(tk.W, tk.N), pady=(0, 5), padx=(0, 10))
        self.desc_text = scrolledtext.ScrolledText(editor_frame, width=60, height=8, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 10), insertbackground=self.colors['accent'], wrap=tk.WORD)
        self.desc_text.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=(0, 10))
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
        ttk.Label(editor_frame, text="Target Platforms:", style='Subtitle.TLabel').grid(row=row, column=0, sticky=(tk.W, tk.N), pady=(0, 5), padx=(0, 10))
        platforms_frame = ttk.Frame(editor_frame)
        platforms_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=(0, 10))
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
        chat_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        chat_frame.columnconfigure(0, weight=1)
        self.chat_display = scrolledtext.ScrolledText(chat_frame, width=80, height=6, bg=self.colors['input_bg'], fg=self.colors['text'], font=('Segoe UI', 10), wrap=tk.WORD, insertbackground=self.colors['accent'], state='disabled')
        self.chat_display.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame = ttk.Frame(chat_frame)
        input_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        input_frame.columnconfigure(0, weight=1)
        self.chat_input = ttk.Entry(input_frame, width=80, font=('Segoe UI', 10))
        self.chat_input.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 10))
        self.chat_input.bind('<Return>', lambda e: self.send_chat())
        ttk.Button(input_frame, text="Send", command=self.send_chat, style='Accent.TButton').grid(row=0, column=1)
        self._add_chat_message("System", "👋 Welcome! Upload images and generate a listing, then ask me questions!")

        # Status bar (uses status_var initialized in __init__)
        status_bar = tk.Label(self.root, textvariable=self.status_var, bg=self.colors['bg_tertiary'], fg=self.colors['text'], anchor=tk.W, font=('Segoe UI', 9), padx=10, pady=5)
        status_bar.grid(row=1, column=0, sticky=(tk.W, tk.E))

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
        index_frame.grid(row=2, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(0,10))
        index_frame.columnconfigure(0, weight=1)
        self.overlay_listbox = tk.Listbox(index_frame, height=12, bg=self.colors['input_bg'], fg=self.colors['text'])
        self.overlay_listbox.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        overlay_scroll = ttk.Scrollbar(index_frame, orient='vertical', command=self.overlay_listbox.yview)
        overlay_scroll.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.overlay_listbox.configure(yscrollcommand=overlay_scroll.set)
        self.overlay_listbox.bind('<<ListboxSelect>>', self._on_overlay_select)
        ttk.Button(index_frame, text="🔄 Refresh", command=self._reload_overlay_listing_index).grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        ttk.Button(index_frame, text="🪟 Launch Transparent Overlay", command=self._launch_overlay_window).grid(row=1, column=0, sticky=tk.E, pady=(5,0))

        # Field pack panel
        field_frame = ttk.LabelFrame(overlay_tab, text="Field Pack & Paste Controls", padding="10")
        field_frame.grid(row=2, column=1, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(0,10))
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
        ttk.Label(field_frame, text="Title:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_title_var).grid(row=row_ov, column=1, sticky=(tk.W, tk.E)); ttk.Button(field_frame, text="Paste", command=lambda: self._paste_text(self.ov_title_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Tagline:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_tagline_var).grid(row=row_ov, column=1, sticky=(tk.W, tk.E)); ttk.Button(field_frame, text="Paste", command=lambda: self._paste_text(self.ov_tagline_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Bullets (one per line):").grid(row=row_ov, column=0, sticky=tk.W); self.ov_bullets_text.grid(row=row_ov, column=1, columnspan=2, sticky=(tk.W, tk.E)); row_ov+=1
        ttk.Button(field_frame, text="Paste Bullets", command=lambda: self._paste_text('\n'.join([l for l in self.ov_bullets_text.get('1.0','end').splitlines() if l.strip()]))) .grid(row=row_ov, column=1, sticky=tk.W, pady=(0,5)); row_ov+=1
        ttk.Label(field_frame, text="Materials:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_materials_var).grid(row=row_ov, column=1, sticky=(tk.W, tk.E)); ttk.Button(field_frame, text="Paste", command=lambda: self._paste_text(self.ov_materials_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Dimensions:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_dimensions_var).grid(row=row_ov, column=1, sticky=(tk.W, tk.E)); ttk.Button(field_frame, text="Paste", command=lambda: self._paste_text(self.ov_dimensions_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Condition:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_condition_var).grid(row=row_ov, column=1, sticky=(tk.W, tk.E)); ttk.Button(field_frame, text="Paste", command=lambda: self._paste_text(self.ov_condition_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="Price Range:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_price_var).grid(row=row_ov, column=1, sticky=(tk.W, tk.E)); ttk.Button(field_frame, text="Paste", command=lambda: self._paste_text(self.ov_price_var.get())).grid(row=row_ov, column=2); row_ov+=1
        ttk.Label(field_frame, text="SEO Keywords:").grid(row=row_ov, column=0, sticky=tk.W); ttk.Entry(field_frame, textvariable=self.ov_keywords_var).grid(row=row_ov, column=1, sticky=(tk.W, tk.E)); ttk.Button(field_frame, text="Paste", command=lambda: self._paste_text(self.ov_keywords_var.get())).grid(row=row_ov, column=2); row_ov+=1
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
        """Copy text to clipboard and attempt Ctrl+V paste into currently focused window."""
        if not text:
            return
        try:
            if PYPERCLIP_AVAILABLE:
                pyperclip.copy(text)
            else:
                self.root.clipboard_clear(); self.root.clipboard_append(text)
            time.sleep(0.05)
            if PYAUTOGUI_AVAILABLE:
                pyautogui.hotkey('ctrl','v')
            else:
                self._add_chat_message('System', '⚠️ pyautogui not available - text copied to clipboard, press Ctrl+V manually.')
        except Exception as e:
            self._add_chat_message('System', f'⚠️ Paste failed: {e}')

    def _launch_overlay_window(self):
        """Create a semi-transparent click-through overlay window (best-effort)."""
        try:
            overlay = tk.Toplevel(self.root)
            overlay.title('Listing Field Pack Overlay')
            overlay.attributes('-topmost', True)
            overlay.geometry('400x500+50+50')
            overlay.attributes('-alpha', 0.55)
            frame = ttk.Frame(overlay, padding='6')
            frame.pack(fill='both', expand=True)
            ttk.Label(frame, text='Overlay Field Pack (click Paste buttons then focus target field)').pack(anchor='w', pady=(0,4))
            # Reuse current overlay vars for quick access
            ttk.Button(frame, text='Paste Title', command=lambda: self._paste_text(self.ov_title_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Tagline', command=lambda: self._paste_text(self.ov_tagline_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Bullets', command=lambda: self._paste_text('\n'.join([l for l in self.ov_bullets_text.get('1.0','end').splitlines() if l.strip()]))).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Materials', command=lambda: self._paste_text(self.ov_materials_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Dimensions', command=lambda: self._paste_text(self.ov_dimensions_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Condition', command=lambda: self._paste_text(self.ov_condition_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste Price Range', command=lambda: self._paste_text(self.ov_price_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Paste SEO Keywords', command=lambda: self._paste_text(self.ov_keywords_var.get())).pack(fill='x', pady=2)
            ttk.Button(frame, text='Close', command=overlay.destroy).pack(fill='x', pady=(10,2))
            # Attempt click-through (Windows only) using ctypes extended styles
            try:
                if sys.platform.startswith('win'):
                    import ctypes
                    GWL_EXSTYLE = -20
                    WS_EX_LAYERED = 0x80000
                    WS_EX_TRANSPARENT = 0x20
                    hwnd = ctypes.windll.user32.GetParent(overlay.winfo_id())
                    current = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current | WS_EX_LAYERED | WS_EX_TRANSPARENT)
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
        self.progress.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
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
