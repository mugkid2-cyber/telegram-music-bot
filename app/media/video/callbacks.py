from aiogram.filters.callback_data import CallbackData


class DownloadTypeCallback(CallbackData, prefix="vd_type"):
    req_id: str
    kind: str  # "audio" | "video"


class QualityCallback(CallbackData, prefix="vd_q"):
    req_id: str
    format_id: str  # id формата yt-dlp, либо "auto"


class CancelCallback(CallbackData, prefix="vd_cancel"):
    req_id: str
