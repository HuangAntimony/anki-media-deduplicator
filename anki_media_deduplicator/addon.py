from __future__ import annotations


def register() -> None:
    from aqt import gui_hooks

    def add_menu_item() -> None:
        from aqt import mw as main_window
        from aqt.qt import QAction, qconnect

        from .ui import DeduplicatorDialog

        action = QAction("Anki Media Deduplicator...", main_window)
        qconnect(action.triggered, lambda: DeduplicatorDialog.open(main_window))
        main_window.form.menuTools.addAction(action)

    gui_hooks.main_window_did_init.append(add_menu_item)
