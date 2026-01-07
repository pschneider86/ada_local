"""
Main Flet application setup and layout.
"""

import flet as ft
import threading

from core.llm import preload_models
from core.tts import tts
from gui.handlers import ChatHandlers


def main(page: ft.Page):
    """Main application entry point."""
    
    # --- Page Configuration ---
    page.title = "Pocket AI"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.window.width = 1000
    page.window.height = 700
    page.bgcolor = "#1a1c1e"
    
    page.fonts = {
        "Roboto Mono": "https://github.com/google/fonts/raw/main/apache/robotomono/RobotoMono%5Bwght%5D.ttf"
    }

    # --- UI Components ---
    chat_list = ft.ListView(
        expand=True,
        spacing=15,
        auto_scroll=True,
        padding=20
    )

    status_text = ft.Text("Initializing...", size=12, color=ft.Colors.GREY_500)
    
    user_input = ft.TextField(
        hint_text="Ask something...",
        border_radius=25,
        filled=True,
        bgcolor="#2b2d31",
        border_color=ft.Colors.TRANSPARENT,
        expand=True,
        autofocus=True,
        content_padding=ft.Padding.symmetric(horizontal=20, vertical=10),
    )

    send_button = ft.IconButton(
        icon=ft.Icons.SEND_ROUNDED, 
        icon_color=ft.Colors.BLUE_200,
        bgcolor="#2b2d31",
        tooltip="Send"
    )
    
    stop_button = ft.IconButton(
        icon=ft.Icons.STOP_CIRCLE_OUTLINED,
        icon_color=ft.Colors.RED_400,
        bgcolor="#2b2d31",
        visible=False,
        tooltip="Stop Generation"
    )

    # --- Sidebar for Conversation History ---
    sidebar_list = ft.ListView(
        expand=True,
        spacing=4,
        padding=ft.padding.symmetric(horizontal=10, vertical=5)
    )
    
    new_chat_btn = ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.ADD, size=18, color=ft.Colors.WHITE),
            ft.Text("New Chat", size=14, weight=ft.FontWeight.W_500),
        ], spacing=10),
        padding=ft.padding.symmetric(horizontal=15, vertical=12),
        bgcolor="#3d3d3d",
        border_radius=8,
        ink=True,
        margin=ft.margin.only(bottom=10),
    )
    
    sidebar = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Text("Pocket AI", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_200),
                padding=ft.padding.only(left=15, top=15, bottom=5)
            ),
            ft.Divider(color=ft.Colors.GREY_800, height=1),
            ft.Container(
                content=new_chat_btn,
                padding=ft.padding.only(left=10, right=10, top=10)
            ),
            sidebar_list,
        ], spacing=0, expand=True),
        width=260,
        bgcolor="#202123",
        border=ft.border.only(right=ft.BorderSide(1, ft.Colors.GREY_800)),
    )

    # --- Initialize Handlers ---
    handlers = ChatHandlers(
        page=page,
        chat_list=chat_list,
        status_text=status_text,
        user_input=user_input,
        send_button=send_button,
        stop_button=stop_button,
        sidebar_list=sidebar_list  # Pass sidebar reference
    )
    
    # Wire up new chat button
    new_chat_btn.on_click = handlers.clear_chat

    # Wire up events
    user_input.on_submit = handlers.send_message
    send_button.on_click = handlers.send_message
    stop_button.on_click = handlers.stop_generation

    # --- Chat Panel Layout ---
    chat_header = ft.Container(
        content=ft.Row([
            ft.Text("Chat", size=16, weight=ft.FontWeight.W_500),
            ft.Container(expand=True),
            ft.Text("Voice", size=12, color=ft.Colors.GREY_400),
            ft.Switch(value=True, on_change=handlers.toggle_tts, scale=0.8),
        ]),
        padding=ft.padding.symmetric(horizontal=20, vertical=10),
        bgcolor="#1a1c1e",
    )

    input_bar = ft.Container(
        content=ft.Row([
            user_input,
            stop_button,
            send_button
        ], spacing=8),
        padding=ft.padding.all(15),
        bgcolor="#1a1c1e",
    )

    chat_panel = ft.Column([
        chat_header,
        status_text,
        ft.Divider(color=ft.Colors.GREY_800, height=1),
        chat_list,
        input_bar
    ], expand=True, spacing=0)

    # --- Main Layout: Sidebar + Chat ---
    page.add(
        ft.Row([
            sidebar,
            ft.Container(content=chat_panel, expand=True, padding=0)
        ], expand=True, spacing=0)
    )
    
    # Refresh sidebar with history
    handlers.refresh_sidebar()

    # --- Initial Preload ---
    def preload_background():
        status_text.value = "Warming up models..."
        page.update()
        preload_models()
        if tts.toggle(True):
            status_text.value = "Ready | TTS Active"
        else:
            status_text.value = "Ready | TTS Failed"
        page.update()

    threading.Thread(target=preload_background, daemon=True).start()
