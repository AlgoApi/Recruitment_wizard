# logging_setup.py
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
import threading
import traceback
import datetime
import glob
import re
from typing import Optional
import requests
import asyncio
from .config import settings

LOG_DIR = os.getenv("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILENAME = os.path.join(LOG_DIR, "bot.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATETIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")  # timestamp в начале строки


def _parse_line_time(line: str) -> Optional[datetime.datetime]:
    m = DATETIME_RE.match(line)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def get_recent_log_slice(hours: int = 1, max_chars: int = 3500) -> str:
    now = datetime.datetime.now()
    cutoff = now - datetime.timedelta(hours=hours)
    lines_collected = []

    files = [LOG_FILENAME] + sorted(glob.glob(LOG_FILENAME + "*"), reverse=True)
    for fname in files:
        try:
            if not os.path.exists(fname):
                continue
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(fname))
            if fname != LOG_FILENAME and mtime < (cutoff - datetime.timedelta(hours=24)):
                continue
            with open(fname, "r", encoding="utf-8", errors="ignore") as fh:
                for raw_line in fh:
                    lines_collected.append(raw_line.rstrip("\n"))
        except Exception:
            continue

    # по времени
    filtered = []
    for line in reversed(lines_collected):  # идти с конца
        t = _parse_line_time(line)
        if t is None:
            filtered.append(line)
        else:
            if t >= cutoff:
                filtered.append(line)
            else:
                pass
        # ограничение по размерам
        if sum(len(l) for l in filtered) > max_chars:
            break

    # хронологический порядок сдлеать
    filtered = list(reversed(filtered))
    text = "\n".join(filtered)
    if len(text) > max_chars:
        text = text[-max_chars:]
        text = "..." + text

    excerpt_path = os.path.join(LOG_DIR, "last_hour.log")
    with open(excerpt_path, "w+", encoding="utf-8") as f:
        for line in f:
            try:
                f.write(line)
            except Exception:
                pass
    return excerpt_path or "(no recent logs)"


def _send_telegram_message_sync(text: str, file:str, parse_mode: str = "HTML"):
    token = settings.bot_token
    chat = settings.superadmin_chatid
    if not token or not chat:
        logging.getLogger(__name__).warning("Telegram token/chat not configured — cannot send report")
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        data = {
            "chat_id": chat,
            "caption": text,
            "parse_mode": parse_mode
        }
        with open(file, "rb") as f:
            files = {"document": f}
            resp = requests.post(url, data=data, files=files, timeout=15)
        if resp.status_code != 200:
            try:
                logging.getLogger(__name__).error("Telegram send failed: %s %s", resp.status_code, resp.text)
            except Exception:
                try:
                    url = f"https://api.telegram.org/bot{token}/sendMessage"
                    data = {
                        "chat_id": chat,
                        "text": text,
                        "parse_mode": parse_mode
                    }
                    resp = requests.post(url, data=data, timeout=10)
                    if resp.status_code != 200:
                        logging.getLogger(__name__).warning("Telegram send failed: %s %s", resp.status_code, resp.text)
                except Exception as e:
                    logging.getLogger(__name__).exception("Failed to send telegram message: %s", e)
    except Exception as e:
        logging.getLogger(__name__).exception("Failed to send telegram message: %s", e)


class TelegramErrorHandler(logging.Handler):
    """
    Logging handler that sends ERROR/CRITICAL logs to Telegram with traceback + recent logs.
    Has cooldown to avoid spamming.
    """
    def __init__(self, cooldown_seconds: int = 60):
        super().__init__(level=logging.ERROR)
        self._last_sent = datetime.datetime.min
        self._cooldown = datetime.timedelta(seconds=cooldown_seconds)
        self._excluded_loggers = {"urllib3", "requests", __name__}

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if any(record.name.startswith(x) for x in self._excluded_loggers):
                return

            now = datetime.datetime.now()
            if now - self._last_sent < self._cooldown:
                return

            header = f"Ошибка в приложении: {record.levelname}\n"
            header += f"Logger: {record.name}\n"

            tbbb_text = None
            if record.exc_info:
                tbbb_text = "".join(traceback.format_exception(*record.exc_info))
            elif record.stack_info:
                tbbb_text = record.stack_info
            else:
                tbbb_text = record.getMessage()

            # trim traceback to safe size
            tbbb_text = tbbb_text or "(no traceback)"
            if len(tbbb_text) > 3000:
                tbbb_text = tbbb_text[-3000:]
                tbbb_text = "..." + tbbb_text

            recent = get_recent_log_slice(hours=1, max_chars=3500)

            message = (
                f"{header}\n"
                f"Сообщение:\n<pre>{escape_html(tbbb_text)}</pre>\n\n"
                f"Логи за последний час в файле"
            )

            _send_telegram_message_sync(message, recent, parse_mode="HTML")
            self._last_sent = now
        except Exception:
            try:
                logging.getLogger(__name__).exception("Failed inside TelegramErrorHandler.emit")
            except Exception:
                pass


def escape_html(s: str) -> str:
    # экранирование для HTML parse_mode в Telegram
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


def install_global_exception_handlers():
    logger = logging.getLogger()

    def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if exc_value is None:
            return
        try:
            logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        except Exception:
            pass

    sys.excepthook = _handle_unhandled_exception

    # threading.excepthook
    if hasattr(threading, "excepthook"):
        def _thread_excepthook(args):
            try:
                logger.error("Unhandled thread exception", exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
            except Exception:
                pass
        threading.excepthook = _thread_excepthook

    # asyncio loop handler
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop:
        def _asyncio_exc_handler(loop_, context):
            try:
                exc = context.get("exception")
                if exc:
                    logger.error("Unhandled async exception", exc_info=(type(exc), exc, exc.__traceback__))
                else:
                    logger.error("Unhandled async error: %s", context.get("message"), exc_info=context)
            except Exception:
                pass
        try:
            loop.set_exception_handler(_asyncio_exc_handler)
        except Exception:
            logger.debug("Unable to set asyncio exception handler")
    else:
        logger.debug("No running asyncio loop found while installing exception handler.")


def setup_logging(level: str = "INFO") -> None:
    """
      - консоль 1
      - TimedRotatingFileHandler (midnight) 1
      - TelegramErrorHandler для ERROR/CRITICAL 1
      - установка глобальных обработчиков необработанных исключений 1
    """
    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(LOG_FORMAT)

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # File rotating handler
    file_handler = TimedRotatingFileHandler(LOG_FILENAME, when="midnight", backupCount=14, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Telegram handler (ERROR and above)
    telegram_handler = TelegramErrorHandler()
    root.addHandler(telegram_handler)

    # Prevent requests/urllib3 logs from causing Telegram flood:
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    # Install global exception hooks
    install_global_exception_handlers()
