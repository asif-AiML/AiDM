"""Settings drawer UI backed by the window's shared preferences model."""

import sys

from PySide6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, Property, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from download_settings import (
    ConnectionsPerFile, DownloadSettings, FragmentConcurrency, FragmentRetries,
    ParallelFiles, PerformanceProfile, RetryAttempts, SpeedLimit,
)


# Presentation only: validation, defaults and profile matching belong to the model.
SETTING_SECTIONS = (
    ("PERFORMANCE", (
        ("connections_per_file", "Connections per file", (
            ("Auto — Recommended", ConnectionsPerFile.AUTO),
            ("1 — Maximum compatibility", ConnectionsPerFile.ONE),
            ("4 — Balanced", ConnectionsPerFile.FOUR),
            ("8 — Best performance", ConnectionsPerFile.EIGHT),
        )),
        ("parallel_files", "Parallel files", (
            ("2 — Conservative", ParallelFiles.TWO),
            ("4 — Recommended", ParallelFiles.FOUR),
        )),
        ("fragment_concurrency", "Concurrent stream fragments", (
            ("1 — Maximum compatibility", FragmentConcurrency.ONE),
            ("4 — Recommended", FragmentConcurrency.FOUR),
            ("8 — Best performance", FragmentConcurrency.EIGHT),
        )),
    )),
    ("BANDWIDTH", (
        ("speed_limit", "Download speed limit", (
            ("Unlimited — Recommended", SpeedLimit.UNLIMITED),
            ("1 MB/s", SpeedLimit.ONE_MBPS),
            ("2 MB/s", SpeedLimit.TWO_MBPS),
            ("5 MB/s", SpeedLimit.FIVE_MBPS),
            ("10 MB/s", SpeedLimit.TEN_MBPS),
        )),
    )),
    ("RELIABILITY", (
        ("retry_attempts", "Retry attempts", (
            ("Auto — Recommended", RetryAttempts.AUTO),
            ("3 — Quick failure", RetryAttempts.THREE),
            ("5 — Balanced", RetryAttempts.FIVE),
            ("10 — Persistent", RetryAttempts.TEN),
        )),
        ("fragment_retries", "Stream fragment retries", (
            ("Auto — Recommended", FragmentRetries.AUTO),
            ("5 — Balanced", FragmentRetries.FIVE),
            ("10 — Persistent", FragmentRetries.TEN),
            ("20 — Very persistent", FragmentRetries.TWENTY),
        )),
    )),
)


class DimOverlay(QWidget):
    clicked = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.opacity = 0.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, round(90 * self.opacity)))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()


class SettingsDrawer(QWidget):
    """Central-widget overlay with a separate, always reachable toggle button.

    Animate a reveal fraction instead of stale pixel endpoints, so resizing at
    any animation frame keeps the panel anchored to the current right edge.
    """

    transition_finished = Signal(bool)

    def __init__(self, parent, settings: DownloadSettings):
        super().__init__(parent)
        self.settings = settings
        self.is_open = False
        self._reveal = 0.0
        self.overlay = DimOverlay(self)
        self.overlay.clicked.connect(lambda: self.set_open(False))
        self.panel = QFrame(self)
        self.panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.panel.setAutoFillBackground(True)
        self.panel.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.panel.setAccessibleName("Download Settings")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(1, 1, 1, 1)
        self.heading = QLabel("Download Settings")
        self.heading.setContentsMargins(20, 23, 56, 8)
        self.heading.setWordWrap(True)
        font = self.heading.font()
        font.setBold(True)
        self.heading.setFont(font)
        panel_layout.addWidget(self.heading)
        self.scroll_area = QScrollArea(self.panel)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.content = QWidget()
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(20, 8, 20, 20)
        self.scroll_area.setWidget(self.content)
        panel_layout.addWidget(self.scroll_area)
        self.profile_label = QLabel("Profile")
        self.profile_choice = QComboBox()
        self.profile_choice.setAccessibleName("Performance profile")
        self.profile_label.setBuddy(self.profile_choice)
        for profile in PerformanceProfile:
            self.profile_choice.addItem(profile.value, profile)
        custom_index = self.profile_choice.findData(PerformanceProfile.CUSTOM)
        self.profile_choice.model().item(custom_index).setEnabled(False)
        layout.addWidget(self.profile_label)
        layout.addWidget(self.profile_choice)
        self.setting_choices = {}
        for section, controls in SETTING_SECTIONS:
            layout.addSpacing(8)
            section_label = QLabel(section)
            section_label.setFont(font)
            layout.addWidget(section_label)
            for name, title, choices in controls:
                label = QLabel(title)
                label.setWordWrap(True)
                combo = QComboBox()
                combo.setAccessibleName(title)
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                label.setBuddy(combo)
                for text, value in choices:
                    combo.addItem(text, value)
                layout.addWidget(label)
                layout.addWidget(combo)
                self.setting_choices[name] = combo
                combo.currentIndexChanged.connect(lambda index, name=name: self._update_setting(name, index))
        layout.addStretch()
        self.combos = (self.profile_choice, *self.setting_choices.values())
        self.profile_choice.currentIndexChanged.connect(self._apply_profile)
        self.refresh_from_settings()

        # A sibling of the overlay layer, so it remains clickable above it.
        self.button = QToolButton(parent)
        self.button.setText("☰")
        self.button.setAutoRaise(True)
        self.button.setCheckable(True)
        self.button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.button.setAccessibleName("Open settings")
        self.button.clicked.connect(lambda: self.set_open(not self.is_open))
        self.button.resize(self.button.sizeHint().expandedTo(self.button.minimumSizeHint()))
        self.focus_order = (*self.combos, self.button)

        self.animation = QPropertyAnimation(self, b"reveal", self)
        self.animation.setDuration(210)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.finished.connect(self._finish_transition)
        self.setGeometry(parent.rect())
        self._position_widgets()
        self.hide()
        self.overlay.hide()
        self.panel.hide()
        # Scope keyboard interception to this window, without disabling or
        # changing the focus policies of dynamically rendered main controls.
        parent.installEventFilter(self)

    def refresh_from_settings(self):
        """Reflect derived values without applying a preset or writing settings."""
        with QSignalBlocker(self.profile_choice):
            self.profile_choice.setCurrentIndex(self.profile_choice.findData(self.settings.profile))
        for name, combo in self.setting_choices.items():
            with QSignalBlocker(combo):
                combo.setCurrentIndex(combo.findData(getattr(self.settings.values, name)))

    def _update_setting(self, name, index):
        value = self.setting_choices[name].itemData(index)
        try:
            if value is not None:
                self.settings.update(**{name: value})
        except OSError as error:
            print(str(error), file=sys.stderr)
        finally:
            self.refresh_from_settings()

    def _apply_profile(self, index):
        profile = self.profile_choice.itemData(index)
        try:
            if profile is not None and profile != PerformanceProfile.CUSTOM:
                self.settings.apply_profile(profile)
        except OSError as error:
            print(str(error), file=sys.stderr)
        finally:
            self.refresh_from_settings()

    @property
    def blocks_input(self):
        return self.isVisible()  # Includes the entire closing animation.

    def _get_reveal(self):
        return self._reveal

    def _set_reveal(self, value):
        self._reveal = float(value)
        self._position_widgets()
        self.overlay.opacity = self._reveal
        self.overlay.update()

    reveal = Property(float, _get_reveal, _set_reveal)

    def _position_widgets(self):
        self.overlay.setGeometry(self.rect())
        width = min(320, round(self.width() * 0.7))
        self.panel.setGeometry(self.width() - round(width * self._reveal), 0, width, self.height())
        self.button.move(max(0, self.width() - self.button.width() - 16), 16)
        self.button.raise_()

    def resizeEvent(self, event):
        self._position_widgets()
        super().resizeEvent(event)

    def set_open(self, opened):
        if self.is_open == opened:
            return
        self.is_open = opened
        self.button.setChecked(opened)
        self.button.setAccessibleName("Close settings" if opened else "Open settings")
        self.animation.stop()
        if opened:
            self.refresh_from_settings()
            QApplication.instance().installEventFilter(self)
            self.show()
            self.overlay.show()
            self.panel.show()
            self.raise_()
            self.button.raise_()
            self.profile_choice.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            for combo in self.combos:
                combo.hidePopup()
        self.animation.setStartValue(self._reveal)
        self.animation.setEndValue(1.0 if opened else 0.0)
        self.animation.start()

    def _finish_transition(self):
        if not self.is_open:
            self.hide()
            self.button.setFocus(Qt.FocusReason.OtherFocusReason)
        self.transition_finished.emit(self.is_open)

    def hideEvent(self, event):
        # Also handles the containing window closing during an animation.
        self.animation.stop()
        QApplication.instance().removeEventFilter(self)
        self.is_open = False
        self.button.setChecked(False)
        self.button.setAccessibleName("Open settings")
        self.overlay.hide()
        self.panel.hide()
        self._set_reveal(0.0)
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
            # Qt defers resizeEvent for hidden widgets; position the visible
            # sibling toggle immediately even while the drawer is closed.
            self._position_widgets()
        if not self.blocks_input or not isinstance(watched, QWidget):
            return False
        # QWidget.isAncestorOf does not cross the combo's popup window boundary.
        popup_combo = next((combo for combo in self.combos
                            if watched.window() is combo.view().window()), None)
        in_popup = popup_combo is not None
        inside = (watched is self.button or watched is self.panel or self.panel.isAncestorOf(watched)
                  or in_popup)
        if not inside and watched.window() is not self.window():
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            if in_popup:
                return False  # Qt's combo popup handles its own selection shortcuts.
            event.accept()  # Prevent window-wide Download shortcuts reaching the main UI.
            return True
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                current = popup_combo or QApplication.focusWidget()
                if popup_combo is not None:
                    popup_combo.hidePopup()
                backwards = (event.key() == Qt.Key.Key_Backtab
                             or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                index = self.focus_order.index(current) if current in self.focus_order else 0
                target = self.focus_order[(index + (-1 if backwards else 1)) % len(self.focus_order)]
                target.setFocus(Qt.FocusReason.BacktabFocusReason if backwards else Qt.FocusReason.TabFocusReason)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if watched is self.button:
                    self.set_open(not self.is_open)
                    return True
                return not inside or watched is self.panel
            if not inside:
                return True
        if event.type() == QEvent.Type.FocusIn:
            if not inside:
                self.profile_choice.setFocus(Qt.FocusReason.OtherFocusReason)
            elif watched in self.combos:
                self.scroll_area.ensureWidgetVisible(watched, 0, 24)
        return False
