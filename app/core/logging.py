import logging
import re

_SECRET = re.compile(
    r"(?i)(password|passwd|pwd|token|api[-_]?key|x-api-key|authorization|cookie|bearer)([\"'\s:=]+)([^\s\"',;&]+)"
)


class MaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _SECRET.sub(r"\1\2***", record.getMessage())
        record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(MaskingFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
