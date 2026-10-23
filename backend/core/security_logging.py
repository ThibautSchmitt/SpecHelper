"""Content-free logging filter safe to import before Django application setup."""

import logging


class ContentFreeWebLogFilter(logging.Filter):
    """Django errors must not include raw paths, query strings or exception bodies."""

    def filter(self, record):
        if record.name == "django" or record.name.startswith("django."):
            record.msg = "HTTP or framework event (request content and exception details withheld)"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
            record.request = None
        return True
