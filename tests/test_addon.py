import sys
from types import ModuleType, SimpleNamespace

from anki_media_deduplicator.addon import register


def test_main_window_hook_accepts_no_arguments(monkeypatch) -> None:
    callbacks = []
    actions = []
    fake_aqt = ModuleType("aqt")
    fake_aqt.gui_hooks = SimpleNamespace(main_window_did_init=callbacks)
    fake_aqt.mw = SimpleNamespace(
        form=SimpleNamespace(menuTools=SimpleNamespace(addAction=actions.append))
    )
    fake_qt = ModuleType("aqt.qt")
    fake_qt.QAction = lambda label, parent: SimpleNamespace(
        label=label, parent=parent, triggered=object()
    )
    fake_qt.qconnect = lambda signal, callback: None
    fake_ui = ModuleType("anki_media_deduplicator.ui")
    fake_ui.DeduplicatorDialog = SimpleNamespace(open=lambda parent: None)
    monkeypatch.setitem(sys.modules, "aqt", fake_aqt)
    monkeypatch.setitem(sys.modules, "aqt.qt", fake_qt)
    monkeypatch.setitem(sys.modules, "anki_media_deduplicator.ui", fake_ui)

    register()
    callbacks[0]()

    assert len(actions) == 1
    assert actions[0].label == "Anki Media Deduplicator..."
