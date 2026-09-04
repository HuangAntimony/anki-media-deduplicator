from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aqt import mw
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QVBoxLayout,
    qconnect,
)
from aqt.utils import askUser, showInfo

from .apply import ApplyExecutor
from .compatibility import AnkiCollectionPort
from .i18n import tr
from .models import ApplyResult, CancellationToken, DeduplicationPlan
from .progress import ProgressState
from .service import scan_collection


def format_bytes(value: int) -> str:
    amount = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or unit == "TiB":
            return f"{amount:.2f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.2f} TiB"


@dataclass(slots=True)
class AnkiApplyOutcome:
    result: ApplyResult
    changes: object


class DeduplicatorDialog(QDialog):
    _instance = None

    @classmethod
    def open(cls, parent) -> None:
        if cls._instance is None:
            cls._instance = cls(parent)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("window_title"))
        self.resize(1000, 650)
        self.plan: DeduplicationPlan | None = None
        self.token: CancellationToken | None = None
        self.progress_state: ProgressState | None = None
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(100)
        qconnect(self.progress_timer.timeout, self._poll_progress)

        self.summary = QLabel(tr("initial_summary"))
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                tr("keep"),
                tr("duplicates"),
                tr("size_each"),
                tr("copies"),
                tr("space_saved"),
                tr("references"),
            ]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.scan_button = QPushButton(tr("scan_media"))
        self.apply_button = QPushButton(tr("apply_deduplication"))
        self.apply_button.setEnabled(False)
        self.close_button = QPushButton(tr("close"))
        qconnect(self.scan_button.clicked, self.scan)
        qconnect(self.apply_button.clicked, self.apply)
        qconnect(self.close_button.clicked, self.close)
        buttons = QHBoxLayout()
        buttons.addWidget(self.scan_button)
        buttons.addWidget(self.apply_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.table)
        layout.addLayout(buttons)

    def _cache_path(self) -> Path:
        root = Path(__file__).resolve().parent.parent
        return root / "user_files" / "hash_cache.sqlite3"

    def _set_busy(self, busy: bool) -> None:
        self.scan_button.setEnabled(not busy)
        self.apply_button.setEnabled(not busy and self.plan is not None and bool(self.plan.groups))
        self.close_button.setEnabled(not busy)

    def _poll_progress(self) -> None:
        if self.token and mw.progress.want_cancel():
            self.token.cancel()
        if self.progress_state:
            snapshot = self.progress_state.snapshot()
            mw.progress.update(
                label=snapshot.label,
                value=snapshot.value,
                max=snapshot.maximum,
                process=False,
            )

    def scan(self) -> None:
        self.plan = None
        self.token = CancellationToken()
        self.progress_state = ProgressState()
        self._set_busy(True)
        self.progress_timer.start()
        QueryOp(
            parent=self,
            op=lambda col: scan_collection(
                col,
                self._cache_path(),
                self.token,
                self.progress_state.update,
            ),
            success=self._scan_succeeded,
        ).failure(self._operation_failed).with_progress(tr("indexing_media")).run_in_background()

    def _scan_succeeded(self, plan: DeduplicationPlan) -> None:
        self.progress_timer.stop()
        self.plan = plan
        self._set_busy(False)
        self._render_plan(plan)

    def _operation_failed(self, error: Exception) -> None:
        self.progress_timer.stop()
        self._set_busy(False)
        if error.__class__.__name__ == "CancelledError":
            self.summary.setText(tr("scan_cancelled"))
            return
        QMessageBox.critical(self, tr("window_title"), str(error))

    def _render_plan(self, plan: DeduplicationPlan) -> None:
        self.summary.setText(
            "\n".join(
                (
                    tr("media_entries_scanned", count=plan.media_files_scanned),
                    tr("total_media_size", size=format_bytes(plan.media_size)),
                    tr("duplicate_groups", count=len(plan.groups)),
                    tr("duplicate_files", count=plan.duplicate_files),
                    tr("files_to_trash", count=plan.files_to_trash),
                    tr("affected_notes", count=len(plan.affected_note_ids)),
                    tr("references_to_rewrite", count=plan.references_to_rewrite),
                    tr("protected_files_skipped", count=plan.protected_skipped),
                    tr("reclaimable_space", size=format_bytes(plan.reclaimable_bytes)),
                )
            )
        )
        self.table.setRowCount(len(plan.groups))
        for row, group_plan in enumerate(plan.groups):
            group = group_plan.group
            references = sum(group.reference_counts.values())
            values = (
                group_plan.choice.filename,
                "\n".join(group_plan.old_filenames),
                format_bytes(group.size),
                str(len(group.files)),
                format_bytes(group.reclaimable_bytes),
                str(references),
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def apply(self) -> None:
        if not self.plan:
            return
        message = tr(
            "apply_confirmation",
            notes=len(self.plan.affected_note_ids),
            files=self.plan.files_to_trash,
            space=format_bytes(self.plan.reclaimable_bytes),
        )
        if not askUser(message, parent=self):
            return
        self.token = None
        self.progress_state = ProgressState()
        self._set_busy(True)
        self.progress_timer.start()

        def operation(col):
            port = AnkiCollectionPort(col)
            result = ApplyExecutor(
                batch_size=500, progress=self.progress_state.update
            ).execute(self.plan, port)
            if port.last_changes is None:
                from anki.collection import OpChanges

                port.last_changes = OpChanges()
            return AnkiApplyOutcome(result, port.last_changes)

        CollectionOp(self, operation).success(self._apply_succeeded).failure(
            self._operation_failed
        ).run_in_background()

    def _apply_succeeded(self, outcome: AnkiApplyOutcome) -> None:
        self.progress_timer.stop()
        self._set_busy(False)
        result = outcome.result
        showInfo(
            tr(
                "apply_result",
                updated=result.updated_notes,
                rewritten=result.rewritten_references,
                trashed=len(result.trashed_files),
                skipped=result.skipped_groups,
            ),
            parent=self,
        )
        self.scan()

    def reject(self) -> None:
        if self.progress_timer.isActive():
            return
        DeduplicatorDialog._instance = None
        super().reject()
