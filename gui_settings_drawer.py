"""Settings drawer UI backed by the window's shared preferences model."""

import sys

from PySide6.QtCore import QEvent, QEasingCurve, QPoint, QPropertyAnimation, Property, QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
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


SETTING_HELP = {
    "proxy": ("Proxy Mode",
        "Routes one supported download through an external SOCKS5 proxy. "
        "AiDM does not start or manage the proxy.\n\nAdvanced features and ordinary download "
        "controls are unavailable while active. Only the saved endpoint is used. "
        "Changes apply to new jobs; Retry keeps the original job's endpoint."),
    "profile": ("Performance profile",
        "Quick presets for the three performance controls below. Custom appears when those "
        "settings do not match a preset.\n\nBandwidth and retry settings are not changed by profiles."),
    "connections_per_file": ("Connections per file",
        "Controls connections aria2c may use for one file. More can improve speed, but some servers "
        "restrict multiple connections.\n\nAuto keeps AiDM's tested defaults: 1 for direct downloads "
        "and 8 for normal YouTube downloads using aria2c.\n\nApplies to aria2c primary transfers, "
        "not yt-dlp-native HLS/DASH fragments. Subtitle sidecars use AiDM's internal defaults."),
    "parallel_files": ("Parallel files",
        "Controls how many files aria2c downloads at once in Direct Bulk → Parallel mode only. "
        "Waiting files start as active ones finish.\n\nDoes not affect single downloads or sequential bulk downloads."),
    "fragment_concurrency": ("Concurrent stream fragments",
        "Controls how many HLS/DASH fragments yt-dlp downloads at once. Higher values may improve "
        "speed, but some servers restrict them.\n\nApplies only to native HLS/DASH stream downloads, "
        "such as browser-assisted streams. Does not affect normal aria2c-backed YouTube downloads."),
    "speed_limit": ("Download speed limit",
        "Limits total download speed for aria2c transfers and native yt-dlp HLS/DASH streams. "
        "Unlimited removes AiDM's artificial cap.\n\nIn Direct Bulk → Parallel mode, the limit "
        "applies to the whole aria2c process, not separately to each file."),
    "retry_attempts": ("Retry attempts",
        "Controls general retries after a failed download or connection attempt by the primary "
        "transfer engine: aria2c, or yt-dlp for native HLS/DASH streams. Auto keeps the engine's "
        "normal behavior.\n\nMore retries may help unstable connections but take longer to give up. "
        "Separate from Stream fragment retries."),
    "fragment_retries": ("Stream fragment retries",
        "Controls retries for individual HLS/DASH fragments when yt-dlp downloads a stream "
        "natively. Auto keeps yt-dlp's normal behavior.\n\nUseful on unstable connections; higher "
        "values take longer to give up on unavailable fragments. Separate from general Retry attempts."),
}


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

    def __init__(self, parent, settings: DownloadSettings, proxy_settings=None):
        super().__init__(parent)
        self.settings = settings
        self.proxy_settings = proxy_settings
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
        self.info_buttons = {}
        self.profile_label = QLabel("Profile")
        self.profile_choice = QComboBox()
        self.profile_choice.setAccessibleName("Performance profile")
        self.profile_label.setBuddy(self.profile_choice)
        for profile in PerformanceProfile:
            self.profile_choice.addItem(profile.value, profile)
        custom_index = self.profile_choice.findData(PerformanceProfile.CUSTOM)
        self.profile_choice.model().item(custom_index).setEnabled(False)
        self._add_help_label(layout, self.profile_label, "profile")
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
                self._add_help_label(layout, label, name)
                layout.addWidget(combo)
                self.setting_choices[name] = combo
                combo.currentIndexChanged.connect(lambda index, name=name: self._update_setting(name, index))
        layout.addSpacing(8)
        self.restore_button = QPushButton("Restore Defaults")
        self.restore_button.setAccessibleName("Restore default download settings")
        self.restore_button.clicked.connect(self._restore_defaults)
        layout.addWidget(self.restore_button)
        if proxy_settings is not None:
            self._add_proxy_section(layout, font)
        layout.addStretch()
        # Reserve one quiet footer line so notifications do not move the form.
        self.saved_notice = QLabel("Settings saved")
        self.saved_notice.setAccessibleName("Settings saved")
        self.saved_notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.saved_notice.setContentsMargins(0, 4, 0, 4)
        policy = self.saved_notice.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.saved_notice.setSizePolicy(policy)
        panel_layout.addWidget(self.saved_notice)
        self.saved_notice.hide()
        self.saved_timer = QTimer(self)
        self.saved_timer.setSingleShot(True)
        self.saved_timer.setInterval(2000)
        self.saved_timer.timeout.connect(self.saved_notice.hide)
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
        self.focus_order = tuple(widget for combo, info in zip(self.combos, self.info_buttons.values())
                                 for widget in (combo, info)) + (self.restore_button, self.button)
        if proxy_settings is not None:
            self.focus_order = self.focus_order[:-1] + (
                self.proxy_toggle, self.info_buttons["proxy"], self.proxy_host,
                self.proxy_port, self.proxy_save, self.button,
            )
            self.refresh_proxy_state()

        # A child bubble stays inside the application and leaves keyboard focus
        # on its trigger. It does not compete with native combo popup windows.
        self.help_popup = QFrame(self)
        self.help_popup.setFrameShape(QFrame.Shape.StyledPanel)
        self.help_popup.setAutoFillBackground(True)
        help_layout = QVBoxLayout(self.help_popup)
        help_layout.setContentsMargins(12, 10, 12, 10)
        self.help_title = QLabel()
        self.help_title.setFont(font)
        self.help_title.setWordWrap(True)
        self.help_text = QLabel()
        self.help_text.setWordWrap(True)
        self.help_text.setTextFormat(Qt.TextFormat.PlainText)
        help_layout.addWidget(self.help_title)
        help_layout.addWidget(self.help_text)
        self.help_popup.hide()
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.help_popup.hide)

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

    def _add_proxy_section(self, layout, font):
        layout.addSpacing(8)
        heading = QLabel("PROXY-AWARE SPECIAL MODE")
        heading.setFont(font)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        self.proxy_toggle = QCheckBox("Proxy Mode")
        self.proxy_toggle.setAccessibleName("Proxy Mode")
        self._add_help_label(layout, self.proxy_toggle, "proxy")
        self.proxy_toggle.toggled.connect(self._toggle_proxy)
        endpoint = self.proxy_settings.endpoint
        self.proxy_host = QLineEdit(endpoint.host if endpoint else "")
        self.proxy_port = QLineEdit(str(endpoint.port) if endpoint else "")
        for title, widget in (("SOCKS host", self.proxy_host), ("SOCKS port", self.proxy_port)):
            label = QLabel(title)
            label.setBuddy(widget)
            widget.setAccessibleName(title)
            layout.addWidget(label)
            layout.addWidget(widget)
        self.proxy_example = QLabel("(e.g. 127.0.0.1 : 1081)")
        self.proxy_example.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(self.proxy_example)
        self.proxy_save = QPushButton("Save")
        self.proxy_save.setAccessibleName("Save SOCKS endpoint")
        self.proxy_save.clicked.connect(self._save_proxy)
        layout.addWidget(self.proxy_save)
        notice = QLabel("Special mode supports one download at a time. Most advanced AiDM features "
                        "are unavailable. Ordinary download controls are preserved for normal mode.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.proxy_feedback = QLabel()
        self.proxy_feedback.setWordWrap(True)
        self.proxy_feedback.setAccessibleName("Proxy settings feedback")
        self.proxy_feedback.hide()
        layout.addWidget(self.proxy_feedback)

    def refresh_proxy_state(self):
        # Do not overwrite unsaved text when mode or another view changes.
        enabled = self.proxy_settings.enabled
        with QSignalBlocker(self.proxy_toggle):
            self.proxy_toggle.setChecked(enabled)
        for widget in (*self.combos, self.restore_button):
            widget.setEnabled(not enabled)

    def _toggle_proxy(self, enabled):
        self._hide_saved()
        try:
            self.proxy_settings.set_enabled(enabled)
            self.proxy_feedback.hide()
        except ValueError as error:
            self._show_proxy_error(error)
        self.refresh_proxy_state()

    def _save_proxy(self):
        self._hide_saved()
        try:
            self.proxy_settings.save(self.proxy_host.text(), self.proxy_port.text())
        except (ValueError, OSError) as error:
            self._show_proxy_error(error)
            return
        endpoint = self.proxy_settings.endpoint
        self.proxy_host.setText(endpoint.host)
        self.proxy_port.setText(str(endpoint.port))
        self.proxy_feedback.hide()
        self._show_saved()

    def _show_proxy_error(self, error):
        self.proxy_feedback.setText(str(error))
        self.proxy_feedback.show()
        # Let the new label update the scroll range before revealing feedback.
        QTimer.singleShot(0, self, lambda:
                          self.scroll_area.ensureWidgetVisible(self.proxy_feedback, 0, 24))

    def _available_focus_order(self):
        return tuple(widget for widget in self.focus_order if widget.isEnabled() and widget.isVisible())

    def _add_help_label(self, layout, label, name):
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(label, 1)
        info = QToolButton()
        info.setText("ⓘ")
        info.setAutoRaise(True)
        info.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        title, text = SETTING_HELP[name]
        info.setAccessibleName(f"About {title.lower()}")
        info.setAccessibleDescription(text)
        info.clicked.connect(lambda: self._show_help(name))
        row.addWidget(info)
        self.info_buttons[name] = info
        layout.addLayout(row)

    def _show_help(self, name):
        if not self.is_open:
            return
        button = self.info_buttons[name]
        button.setFocus(Qt.FocusReason.OtherFocusReason)
        self.scroll_area.ensureWidgetVisible(button, 0, 24)
        for combo in self.combos:
            combo.hidePopup()
        title, text = SETTING_HELP[name]
        self.help_title.setText(title)
        self.help_text.setText(text)
        self.help_popup.setAccessibleName(title)
        self.help_popup.setAccessibleDescription(text)
        width = min(340, self.width() - 16)
        self.help_popup.setFixedSize(width, self.help_popup.layout().totalHeightForWidth(width))
        self.help_popup.layout().activate()
        anchor = button.mapTo(self, QPoint(0, button.height()))
        x = max(8, min(anchor.x(), self.width() - self.help_popup.width() - 8))
        y = anchor.y() + 4
        if y + self.help_popup.height() > self.height() - 8:
            y = max(8, anchor.y() - button.height() - self.help_popup.height() - 4)
        self.help_popup.move(x, y)
        self.help_popup.show()
        self.help_popup.raise_()

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
                self._show_saved()
        except OSError as error:
            self._hide_saved()
            print(str(error), file=sys.stderr)
        finally:
            self.refresh_from_settings()

    def _apply_profile(self, index):
        profile = self.profile_choice.itemData(index)
        try:
            if profile is not None and profile != PerformanceProfile.CUSTOM:
                self.settings.apply_profile(profile)
                self._show_saved()
        except OSError as error:
            self._hide_saved()
            print(str(error), file=sys.stderr)
        finally:
            self.refresh_from_settings()

    def _show_saved(self):
        if self.is_open:
            self.saved_notice.show()
            self.saved_timer.start()

    def _hide_saved(self):
        self.saved_timer.stop()
        self.saved_notice.hide()

    def _confirm_restore(self):
        dialog = QMessageBox(self.panel)
        dialog.setWindowTitle("Restore Defaults")
        dialog.setText("Restore all download settings to AiDM defaults?")
        dialog.setIcon(QMessageBox.Icon.Question)
        restore = dialog.addButton("Restore", QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(cancel)
        dialog.setEscapeButton(cancel)
        try:
            dialog.exec()
            return dialog.clickedButton() is restore
        finally:
            dialog.deleteLater()

    def _restore_defaults(self):
        if self._confirm_restore():
            try:
                self.settings.reset_to_defaults()
                self._show_saved()
            except OSError as error:
                self._hide_saved()
                print(str(error), file=sys.stderr)
            finally:
                self.refresh_from_settings()
        self.restore_button.setFocus(Qt.FocusReason.OtherFocusReason)

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
            self._available_focus_order()[0].setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.help_popup.hide()
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
        self.help_popup.hide()
        self._hide_saved()
        QApplication.instance().removeEventFilter(self)
        self.is_open = False
        self.button.setChecked(False)
        self.button.setAccessibleName("Open settings")
        self.overlay.hide()
        self.panel.hide()
        self._set_reveal(0.0)
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if (watched in (self.window(), self.parentWidget())
                and event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.WindowDeactivate)):
            self.help_popup.hide()
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
            # Qt defers resizeEvent for hidden widgets; position the visible
            # sibling toggle immediately even while the drawer is closed.
            self._position_widgets()
        if not self.blocks_input or not isinstance(watched, QWidget):
            return False
        in_help = watched is self.help_popup or self.help_popup.isAncestorOf(watched)
        if (self.help_popup.isVisible() and event.type() == QEvent.Type.MouseButtonPress
                and not in_help):
            self.help_popup.hide()
        # QWidget.isAncestorOf does not cross the combo's popup window boundary.
        popup_combo = next((combo for combo in self.combos
                            if watched.window() is combo.view().window()), None)
        in_popup = popup_combo is not None
        inside = (watched is self.button or watched is self.panel or self.panel.isAncestorOf(watched)
                  or in_popup or in_help)
        if not inside and watched.window() is not self.window():
            return False
        if event.type() == QEvent.Type.ShortcutOverride:
            if in_popup:
                return False  # Qt's combo popup handles its own selection shortcuts.
            event.accept()  # Prevent window-wide Download shortcuts reaching the main UI.
            return True
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape and self.help_popup.isVisible():
                self.help_popup.hide()
                return True
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                self.help_popup.hide()
                current = popup_combo or QApplication.focusWidget()
                if popup_combo is not None:
                    popup_combo.hidePopup()
                backwards = (event.key() == Qt.Key.Key_Backtab
                             or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                order = self._available_focus_order()
                index = order.index(current) if current in order else 0
                target = order[(index + (-1 if backwards else 1)) % len(order)]
                target.setFocus(Qt.FocusReason.BacktabFocusReason if backwards else Qt.FocusReason.TabFocusReason)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if inside and isinstance(watched, QAbstractButton):
                    watched.click()
                    return True
                return not inside or watched is self.panel
            if not inside:
                return True
        if event.type() == QEvent.Type.FocusIn:
            if not inside:
                self._available_focus_order()[0].setFocus(Qt.FocusReason.OtherFocusReason)
            elif watched in self.focus_order and watched is not self.button:
                self.help_popup.hide()
                self.scroll_area.ensureWidgetVisible(watched, 0, 24)
        return False
