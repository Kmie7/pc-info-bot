#!/usr/bin/env python3
"""
PC Info & Tech Assistant — Telegram Bot
Run: python telegram_bot.py
Requires: pip install -r requirements.txt
Token: set TELEGRAM_TOKEN in .env file (never paste in chat!)
"""

import os
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — can set env var manually

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
except ImportError:
    raise SystemExit("Missing dependency. Run: pip install -r requirements.txt")

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise SystemExit("TELEGRAM_TOKEN not set. Add it to your .env file:\nTELEGRAM_TOKEN=your_token_here")

# ─── Knowledge Base ───────────────────────────────────────────────────────────

COMPONENTS = {
    "motherboard": {
        "name": "Motherboard (Papan Induk)",
        "what": "The main circuit board — CPU, RAM, GPU, storage, and ports all connect here.",
        "types": ["ATX", "Micro-ATX", "Mini-ITX", "E-ATX"],
        "brands": ["ASUS", "MSI", "Gigabyte", "ASRock"],
        "check": {
            "windows": "Win+R → msinfo32 → BaseBoard Manufacturer / Product",
            "mac": "Apple menu → About This Mac → System Report → Hardware",
            "linux": "sudo dmidecode -t baseboard"
        }
    },
    "cpu": {
        "name": "CPU (Processor)",
        "what": "The brain of the PC. Processes all instructions. Speed in GHz, more cores = better multitasking.",
        "types": ["Intel Core i3/i5/i7/i9", "AMD Ryzen 3/5/7/9", "Apple M1/M2/M3/M4", "Qualcomm Snapdragon X"],
        "brands": ["Intel", "AMD", "Apple", "Qualcomm"],
        "check": {
            "windows": "Ctrl+Shift+Esc → Performance → CPU  OR  Win+R → msinfo32",
            "mac": "Apple menu → About This Mac → Chip/Processor",
            "linux": "lscpu  OR  cat /proc/cpuinfo | grep 'model name'"
        }
    },
    "ram": {
        "name": "RAM (Memory)",
        "what": "Temporary memory for active tasks. More GB = smoother multitasking.",
        "types": ["DDR4", "DDR5", "LPDDR5 (laptops)", "SO-DIMM (laptop)", "ECC (servers)"],
        "brands": ["Kingston", "Corsair", "G.Skill", "Crucial", "Samsung"],
        "check": {
            "windows": "Ctrl+Shift+Esc → Performance → Memory (shows speed & slots used)",
            "mac": "Apple menu → About This Mac → Memory",
            "linux": "free -h  OR  sudo dmidecode -t memory"
        }
    },
    "gpu": {
        "name": "GPU (Graphics Card)",
        "what": "Handles visuals, gaming, video & AI. Has its own VRAM. Can be dedicated or integrated.",
        "types": ["NVIDIA GeForce RTX/GTX", "AMD Radeon RX", "Intel Arc", "Integrated (Intel UHD / AMD / Apple)"],
        "brands": ["NVIDIA", "AMD", "Intel", "Apple"],
        "check": {
            "windows": "Win+X → Device Manager → Display adapters  OR  Win+R → dxdiag → Display",
            "mac": "Apple menu → About This Mac → Graphics",
            "linux": "lspci | grep -i vga  OR  nvidia-smi (NVIDIA)"
        }
    },
    "storage": {
        "name": "Storage (SSD / HDD / NVMe)",
        "what": "Where your OS, files and programs live permanently. SSD is fast, HDD is cheaper per GB.",
        "types": ["NVMe SSD (M.2, fastest)", "SATA SSD (2.5\")", "HDD (mechanical)", "eMMC (budget laptops)"],
        "brands": ["Samsung", "WD", "Seagate", "Crucial", "Kingston"],
        "check": {
            "windows": "File Explorer → This PC  OR  Win+R → diskmgmt.msc  OR  Settings → Storage",
            "mac": "Apple menu → About This Mac → Storage",
            "linux": "df -h  OR  lsblk"
        }
    },
    "psu": {
        "name": "PSU (Power Supply)",
        "what": "Converts wall power to DC for components. Wattage and 80+ efficiency rating matter.",
        "types": ["ATX", "SFX (small form factor)", "Modular / Semi / Non-modular", "80+ Bronze/Gold/Platinum/Titanium"],
        "brands": ["Corsair", "Seasonic", "be quiet!", "Cooler Master"],
        "check": {
            "windows": "Check the label on PSU physically — no software reads PSU details",
            "mac": "N/A — internal, not user-serviceable",
            "linux": "Check physically or: sudo dmidecode -t 39"
        }
    },
    "cooling": {
        "name": "Cooling System",
        "what": "Keeps CPU/GPU temps in check. Overheating = throttling or shutdown.",
        "types": ["Stock cooler", "Air cooler (tower heatsink)", "AIO liquid cooler (240/360mm)", "Custom water loop"],
        "brands": ["Noctua", "be quiet!", "Cooler Master", "NZXT", "Arctic"],
        "check": {
            "windows": "Download HWiNFO64 or Core Temp for live temps",
            "mac": "About This Mac → System Report → Power → CPU Temperature",
            "linux": "sensors  (install: sudo apt install lm-sensors)"
        }
    },
    "monitor": {
        "name": "Monitor / Display",
        "what": "Screen output from GPU. Key specs: resolution, refresh rate (Hz), panel type.",
        "types": ["IPS (accurate colours)", "VA (high contrast)", "OLED", "1080p/1440p/4K", "60Hz/144Hz/240Hz"],
        "brands": ["LG", "Samsung", "Dell", "ASUS ROG", "BenQ"],
        "check": {
            "windows": "Right-click desktop → Display settings  OR  Win+R → dxdiag → Display",
            "mac": "Apple menu → System Preferences → Displays",
            "linux": "xrandr"
        }
    },
    "network": {
        "name": "Network Adapter (WiFi / LAN)",
        "what": "Connects to internet. Wired (Ethernet) or wireless (WiFi). Laptops usually have both.",
        "types": ["Ethernet 1Gbps/2.5Gbps", "WiFi 5 (ac)", "WiFi 6 (ax)", "WiFi 6E", "WiFi 7", "Bluetooth 5.x"],
        "brands": ["Intel", "Realtek", "Broadcom", "MediaTek", "TP-Link"],
        "check": {
            "windows": "Win+R → ncpa.cpl  OR  Device Manager → Network Adapters",
            "mac": "About This Mac → System Report → Network",
            "linux": "ip link  OR  lspci | grep -i net"
        }
    },
    "battery": {
        "name": "Battery (Laptop only)",
        "what": "Powers laptop when unplugged. Health degrades over charge cycles. Measured in Wh.",
        "types": ["Li-Ion (most common)", "Li-Po (slim laptops)", "40Wh / 72Wh / 99.9Wh (airline max)"],
        "brands": ["Built-in by Dell, HP, Lenovo, ASUS, Acer, Apple"],
        "check": {
            "windows": "Open Terminal → powercfg /batteryreport → open the HTML report",
            "mac": "Option + click battery icon  OR  System Report → Power",
            "linux": "upower -i /org/freedesktop/UPower/devices/battery_BAT0"
        }
    },
    "keyboard": {
        "name": "Keyboard",
        "what": "Input device. Membrane (quiet), mechanical (clicky/tactile), or scissor-switch (laptops).",
        "types": ["Membrane", "Mechanical (Cherry MX/Gateron/Kailh)", "Scissor-switch", "TKL (no numpad)", "65%/75%/100%"],
        "brands": ["Logitech", "Corsair", "Razer", "Keychron", "Ducky"],
        "check": {
            "windows": "Device Manager → Keyboards",
            "mac": "System Report → USB",
            "linux": "xinput list"
        }
    },
    "mouse": {
        "name": "Mouse",
        "what": "Pointing device. Gaming mice: high DPI, polling rate. Office: ergonomics, battery life.",
        "types": ["Optical", "Laser", "Wireless (2.4GHz/Bluetooth)", "Gaming (up to 8000Hz polling)"],
        "brands": ["Logitech", "Razer", "SteelSeries", "Zowie", "Glorious"],
        "check": {
            "windows": "Device Manager → Mice and other pointing devices",
            "mac": "System Report → USB or Bluetooth",
            "linux": "xinput list"
        }
    },
    "audio": {
        "name": "Sound Card / Audio",
        "what": "Processes audio I/O. Most boards have integrated Realtek. Dedicated cards give better quality.",
        "types": ["Integrated (Realtek ALC)", "PCIe sound card", "USB DAC / audio interface"],
        "brands": ["Realtek", "Creative Sound Blaster", "ASUS Xonar", "Focusrite"],
        "check": {
            "windows": "Device Manager → Sound, video and game controllers",
            "mac": "System Report → Audio",
            "linux": "aplay -l  OR  lspci | grep -i audio"
        }
    },
    "webcam": {
        "name": "Webcam",
        "what": "Camera for video calls and streaming. Key specs: resolution (1080p/4K) and FPS.",
        "types": ["Built-in laptop webcam", "External USB webcam", "4K AI webcam"],
        "brands": ["Logitech", "Razer", "Microsoft", "Elgato"],
        "check": {
            "windows": "Device Manager → Cameras",
            "mac": "System Report → Camera",
            "linux": "ls /dev/video*"
        }
    },
    "case": {
        "name": "PC Case / Chassis",
        "what": "Enclosure for all components. Affects airflow, size of parts supported, and aesthetics.",
        "types": ["Full Tower", "Mid Tower (ATX, most common)", "Mini-ITX", "HTPC"],
        "brands": ["Fractal Design", "Lian Li", "NZXT", "Corsair", "Phanteks"],
        "check": {
            "windows": "Check physically or invoice",
            "mac": "N/A",
            "linux": "sudo dmidecode -t chassis"
        }
    },
    "ports": {
        "name": "Ports & Connectivity",
        "what": "Physical connectors on PC/laptop for display, storage, peripherals, and power.",
        "types": ["USB-A 3.0/3.2", "USB-C / Thunderbolt 4/5", "HDMI 2.1", "DisplayPort 2.1", "SD card", "RJ-45"],
        "brands": ["Built into motherboard / laptop"],
        "check": {
            "windows": "Device Manager → Universal Serial Bus controllers",
            "mac": "System Report → USB / Thunderbolt",
            "linux": "lsusb  OR  lspci | grep -i thunderbolt"
        }
    },
}

# Component keywords mapping
KEYWORDS = {
    "motherboard": ["motherboard", "mainboard", "mobo", "papan induk"],
    "cpu": ["cpu", "processor", "pemproses", "ryzen", "core i", "xeon", "m1", "m2", "m3", "m4"],
    "ram": ["ram", "memory", "memori", "ddr4", "ddr5", "lpddr"],
    "gpu": ["gpu", "graphics", "graphic card", "video card", "vram", "rtx", "gtx", "radeon", "geforce", "arc", "kad grafik"],
    "storage": ["ssd", "hdd", "nvme", "storage", "storan", "disk", "drive", "m.2", "emmc"],
    "psu": ["psu", "power supply", "bekalan kuasa", "watt", "80+"],
    "cooling": ["cooling", "cooler", "fan", "heatsink", "aio", "thermal", "temperature", "suhu"],
    "monitor": ["monitor", "display", "screen", "skrin", "refresh rate", "hz", "4k", "1080p", "oled", "ips"],
    "network": ["wifi", "wi-fi", "ethernet", "lan", "network", "rangkaian", "bluetooth"],
    "battery": ["battery", "bateri", "charge cycle", "watt-hour"],
    "keyboard": ["keyboard", "papan kekunci", "mechanical", "membrane"],
    "mouse": ["mouse", "tetikus", "dpi", "polling rate"],
    "audio": ["sound", "audio", "speaker", "headphone", "microphone", "realtek", "bunyi"],
    "webcam": ["webcam", "camera", "kamera"],
    "case": ["case", "casing", "chassis", "tower"],
    "ports": ["port", "usb", "thunderbolt", "hdmi", "displayport"],
}

OUT_OF_SCOPE = [
    "repair", "fix", "broke", "broken", "cracked", "solder", "water damage",
    "won't turn on", "not booting", "bsod", "blue screen", "crash", "freeze",
    "virus", "malware", "reinstall windows", "format"
]

# ─── Intent helpers ───────────────────────────────────────────────────────────

def detect_component(text):
    t = text.lower()
    for comp, keys in KEYWORDS.items():
        for k in keys:
            if k in t:
                return comp
    return None

def is_out_of_scope(text):
    t = text.lower()
    return any(k in t for k in OUT_OF_SCOPE)

def is_greeting(text):
    t = text.strip().lower()
    return bool(re.match(r"^(hi|hello|hey|helo|hai|selamat|good\s+(morning|afternoon|evening))[\s!?.]*$", t))

def detect_os(text):
    t = text.lower()
    if any(k in t for k in ["windows", "win10", "win11", "laptop", "pc"]):
        return "windows"
    if any(k in t for k in ["mac", "macos", "macbook", "apple"]):
        return "mac"
    if any(k in t for k in ["linux", "ubuntu", "debian", "fedora", "arch"]):
        return "linux"
    return None

# ─── Message builders ─────────────────────────────────────────────────────────

def build_component_msg(key):
    c = COMPONENTS.get(key)
    if not c:
        return None
    types_str = "\n".join(f"  • {t}" for t in c["types"])
    brands_str = ", ".join(c["brands"])
    check_str = "\n".join(f"  *{os.upper()}:* `{cmd}`" for os, cmd in c["check"].items())
    return (
        f"🖥 *{c['name']}*\n\n"
        f"_{c['what']}_\n\n"
        f"*Types / Variants:*\n{types_str}\n\n"
        f"*Popular Brands:* {brands_str}\n\n"
        f"*How to check:*\n{check_str}"
    )

def build_list_msg():
    lines = "\n".join(f"• {c['name']}" for c in COMPONENTS.values())
    return f"📋 *PC/Laptop Components I Know:*\n\n{lines}\n\nAsk me about any one of them!"

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ CPU", callback_data="cpu"),
         InlineKeyboardButton("🧠 RAM", callback_data="ram"),
         InlineKeyboardButton("🎮 GPU", callback_data="gpu")],
        [InlineKeyboardButton("💾 Storage", callback_data="storage"),
         InlineKeyboardButton("🔌 PSU", callback_data="psu"),
         InlineKeyboardButton("❄️ Cooling", callback_data="cooling")],
        [InlineKeyboardButton("🖥 Monitor", callback_data="monitor"),
         InlineKeyboardButton("🌐 WiFi/LAN", callback_data="network"),
         InlineKeyboardButton("🔋 Battery", callback_data="battery")],
        [InlineKeyboardButton("⌨️ Keyboard", callback_data="keyboard"),
         InlineKeyboardButton("🖱️ Mouse", callback_data="mouse"),
         InlineKeyboardButton("🔊 Audio", callback_data="audio")],
        [InlineKeyboardButton("📷 Webcam", callback_data="webcam"),
         InlineKeyboardButton("🗃️ Case", callback_data="case"),
         InlineKeyboardButton("🔌 Ports", callback_data="ports")],
        [InlineKeyboardButton("📋 List All Components", callback_data="list_all")],
    ])

# ─── Handlers ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I'm your *PC Info & Tech Assistant Bot*.\n\n"
        "I can explain PC/laptop components — CPU, RAM, GPU, SSD, Motherboard, PSU, Cooling, Battery, and more.\n\n"
        "Ask me about any component, or pick one below:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*What I can help with:*\n\n"
        "• Explain any PC/laptop component\n"
        "• Tell you how to check specs on Windows, macOS, or Linux\n"
        "• List all components I know\n\n"
        "*I cannot help with:*\n"
        "• Physical hardware repairs\n"
        "• Complex troubleshooting (BSOD, crashes, virus removal)\n\n"
        "Just ask about a component — e.g. _'What is a GPU?'_ or _'How do I check my RAM?'_",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""

    # Out of scope
    if is_out_of_scope(text):
        await update.message.reply_text(
            "⚠️ That sounds like physical repair or complex troubleshooting — "
            "which is outside my scope.\n\n"
            "Please consult a *human technician* or your nearest service centre. 🛠️",
            parse_mode="Markdown"
        )
        return

    # Greeting
    if is_greeting(text):
        await start(update, context)
        return

    # List all
    if any(k in text.lower() for k in ["list all", "semua komponen", "all component", "what components"]):
        await update.message.reply_text(
            build_list_msg(), parse_mode="Markdown", reply_markup=main_keyboard()
        )
        return

    # Component detected
    comp = detect_component(text)
    if comp:
        msg = build_component_msg(comp)
        if msg:
            await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())
            return

    # Unknown
    await update.message.reply_text(
        "🤔 I didn't quite understand that.\n\n"
        "Try asking about a specific component — e.g. *'What is a GPU?'* or *'Tell me about RAM'*\n\n"
        "Or pick from the menu below:",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "list_all":
        await query.message.reply_text(
            build_list_msg(), parse_mode="Markdown", reply_markup=main_keyboard()
        )
        return

    msg = build_component_msg(data)
    if msg:
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=main_keyboard())

# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("✅ PC Info Telegram Bot starting...")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🤖 Bot is running. Press Ctrl+C to stop.")
    app.run_polling()
