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
        self.setWindowTitle("Anki Media Deduplicator")
        self.resize(1000, 650)
        self.plan: DeduplicationPlan | None = None
        self.token: CancellationToken | None = None
        self.progress_state: ProgressState | None = None
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(100)
        qconnect(self.progress_timer.timeout, self._poll_progress)

        self.summary = QLabel("Click Scan Media to perform a read-only dry run.")
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Keep", "Duplicates", "Size Each", "Copies", "Space Saved", "References"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        self.scan_button = QPushButton("Scan Media")
        self.apply_button = QPushButton("Apply Deduplication")
        self.apply_button.setEnabled(False)
        self.close_button = QPushButton("Close")
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
        ).failure(self._operation_failed).with_progress("Indexing media...").run_in_background()

    def _scan_succeeded(self, plan: DeduplicationPlan) -> None:
        self.progress_timer.stop()
        self.plan = plan
        self._set_busy(False)
        self._render_plan(plan)

    def _operation_failed(self, error: Exception) -> None:
        self.progress_timer.stop()
        self._set_busy(False)
        if error.__class__.__name__ == "CancelledError":
            self.summary.setText("Scan cancelled. No changes were made.")
            return
        QMessageBox.critical(self, "Anki Media Deduplicator", str(error))

    def _render_plan(self, plan: DeduplicationPlan) -> None:
        self.summary.setText(
            "\n".join(
                (
                    f"Media entries scanned: {plan.media_files_scanned:,}",
                    f"Total media size: {format_bytes(plan.media_size)}",
                    f"Duplicate groups: {len(plan.groups):,}",
                    f"Duplicate files: {plan.duplicate_files:,}",
                    f"Files to trash: {plan.files_to_trash:,}",
                    f"Affected notes: {len(plan.affected_note_ids):,}",
                    f"References to rewrite: {plan.references_to_rewrite:,}",
                    f"Protected files skipped: {plan.protected_skipped:,}",
                    f"Reclaimable space: {format_bytes(plan.reclaimable_bytes)}",
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
        message = (
            f"This will modify {len(self.plan.affected_note_ids):,} notes, trash "
            f"{self.plan.files_to_trash:,} duplicate media files, and may reclaim "
            f"{format_bytes(self.plan.reclaimable_bytes)}.\n\nContinue?"
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
            f"Updated notes: {result.updated_notes:,}\n"
            f"Rewritten references: {result.rewritten_references:,}\n"
            f"Trashed media files: {len(result.trashed_files):,}\n"
            f"Skipped stale/conflicting groups: {result.skipped_groups:,}",
            parent=self,
        )
        self.scan()

    def reject(self) -> None:
        if self.progress_timer.isActive():
            return
        DeduplicatorDialog._instance = None
        super().reject()
