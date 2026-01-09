from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout
)
from PySide6.QtCore import Qt
from qfluentwidgets import (
    ScrollArea, ExpandLayout, SettingCardGroup, SwitchSettingCard,
    OptionsSettingCard, PushSettingCard, FluentIcon as FIF,
    setTheme, Theme, ConfigItem, OptionsValidator, qconfig,
    PrimaryPushSettingCard
)

class SettingsTab(ScrollArea):
    """
    Settings Tab implementation.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsInterface")
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)
        
        # Make background transparent/consistent
        self.setStyleSheet("background-color: transparent;")
        self.scrollWidget.setObjectName("scrollWidget")
        
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        
        self._init_ui()

    def _init_ui(self):
        # Personalization Group
        self.personal_group = SettingCardGroup("Personalization", self.scrollWidget)
        
        self.theme_card = OptionsSettingCard(
            ConfigItem(None, "ThemeMode", "Dark", OptionsValidator(["Light", "Dark", "Auto"])),
            FIF.BRUSH,
            "Application Theme",
            "Change the appearance of the application",
            texts=["Light", "Dark", "Auto"],
            parent=self.personal_group
        )
        # Handle theme change logic if needed, usually qfluentwidgets handles config
        self.theme_card.optionChanged.connect(self._on_theme_changed)
        
        self.personal_group.addSettingCard(self.theme_card)
        self.expandLayout.addWidget(self.personal_group)

        # AI Configuration Group
        self.ai_group = SettingCardGroup("AI Configuration", self.scrollWidget)
        
        self.model_card = PushSettingCard(
            "Configure",
            FIF.ROBOT,
            "Ollama Models",
            "Manage your local LLM and VLM models",
            self.ai_group
        )
        self.ai_group.addSettingCard(self.model_card)
        
        self.expandLayout.addWidget(self.ai_group)

        # About
        self.about_group = SettingCardGroup("About", self.scrollWidget)
        self.about_card = PrimaryPushSettingCard(
            "Check Update",
            FIF.INFO,
            "About Pocket AI",
            "Version 0.2.0 (Alpha)",
            self.about_group
        )
        self.about_group.addSettingCard(self.about_card)
        self.expandLayout.addWidget(self.about_group)

    def _on_theme_changed(self, value):
        t = Theme.DARK if value == "Dark" else Theme.LIGHT
        if value == "Auto":
            t = Theme.AUTO
        setTheme(t)
