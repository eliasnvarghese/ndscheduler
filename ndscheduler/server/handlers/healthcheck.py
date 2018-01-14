"""Simple 200 response."""

from ndscheduler.server.handlers import base


class Handler(base.BaseHandler):
    """Healthcheck handler."""

    def get(self):
        """Returns simple HTTP OK."""
        self.set_status(200)
        self.finish({"Status": "UP"})
