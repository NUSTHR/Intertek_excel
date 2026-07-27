from app.domain.models import (
    PdfUploadBatch,
    PdfUploadBatchStatus,
    PdfUploadTask,
    PdfUploadTaskStatus,
)


def upload_batch_rollup(
    batch: PdfUploadBatch,
    tasks: list[PdfUploadTask],
) -> tuple[PdfUploadBatchStatus, int, str, str | None, dict[str, object]]:
    if not tasks:
        return (
            PdfUploadBatchStatus.FAILED,
            100,
            "Upload batch contains no accepted tasks.",
            "No accepted PDF knowledge files were found.",
            {"total": 0, "ready": 0, "failed": 0, "cancelled": 0, "active": 0},
        )
    total = len(tasks)
    ready = sum(1 for task in tasks if task.status == PdfUploadTaskStatus.READY)
    failed = sum(1 for task in tasks if task.status == PdfUploadTaskStatus.FAILED)
    cancelled = sum(1 for task in tasks if task.status == PdfUploadTaskStatus.CANCELLED)
    processing = sum(1 for task in tasks if task.status == PdfUploadTaskStatus.PROCESSING)
    queued = sum(1 for task in tasks if task.status == PdfUploadTaskStatus.QUEUED)
    terminal = ready + failed + cancelled
    active = processing + queued
    progress = round(sum(max(0, min(100, task.progress)) for task in tasks) / total)
    result = {
        "total": total,
        "ready": ready,
        "failed": failed,
        "cancelled": cancelled,
        "processing": processing,
        "queued": queued,
        "active": active,
        "accepted_files": batch.accepted_files,
        "skipped_files": batch.skipped_files,
    }
    if terminal == total:
        if ready == total:
            return (
                PdfUploadBatchStatus.READY,
                100,
                f"All {total} documents parsed.",
                None,
                result,
            )
        if cancelled == total:
            return (
                PdfUploadBatchStatus.CANCELLED,
                100,
                f"All {total} documents were cancelled.",
                None,
                result,
            )
        if ready > 0:
            return (
                PdfUploadBatchStatus.PARTIAL,
                100,
                f"{ready} of {total} documents parsed; {failed + cancelled} need review.",
                _first_task_error(tasks),
                result,
            )
        return (
            PdfUploadBatchStatus.FAILED,
            100,
            f"{failed + cancelled} of {total} documents did not parse.",
            _first_task_error(tasks),
            result,
        )
    if processing > 0 or (active > 0 and terminal > 0):
        return (
            PdfUploadBatchStatus.PROCESSING,
            progress,
            f"{ready} of {total} documents parsed; {active} still active.",
            None,
            result,
        )
    return (
        PdfUploadBatchStatus.QUEUED,
        max(progress, batch.progress),
        f"{queued} of {total} documents are queued.",
        None,
        result,
    )


def is_terminal_batch_status(status: PdfUploadBatchStatus) -> bool:
    return status in {
        PdfUploadBatchStatus.READY,
        PdfUploadBatchStatus.PARTIAL,
        PdfUploadBatchStatus.FAILED,
        PdfUploadBatchStatus.CANCELLED,
    }


def _first_task_error(tasks: list[PdfUploadTask]) -> str | None:
    for task in tasks:
        if task.error_message:
            return task.error_message
    return None
