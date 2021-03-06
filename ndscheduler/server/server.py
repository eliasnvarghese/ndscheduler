"""Runs a tornado process to run scheduler daemon and provides REST API & web ui.

How to use:

    SchedulerServer.run()
"""

import base64
import logging
import signal
import sys

import tornado

from ndscheduler import settings
from ndscheduler.core import scheduler_manager
from ndscheduler.server.handlers import audit_logs
from ndscheduler.server.handlers import executions
from ndscheduler.server.handlers import index
from ndscheduler.server.handlers import jobs
from ndscheduler.server.handlers import healthcheck

logger = logging.getLogger(__name__)


def require_basic_auth(handler_class, config=None):
    config = config or dict()
    config.setdefault('user', '')
    config.setdefault('pass', '')
    config.setdefault('realm', 'Next Scheduler')

    if config['user'] and config['pass']:
        def wrap_execute(handler_execute):
            def check_auth(handler):
                auth_header = handler.request.headers.get('Authorization')
                if auth_header and auth_header.startswith('Basic '):
                    if sys.version_info >= (3, 0):
                        auth_decoded = str(base64.b64decode(auth_header[6:]), 'utf-8')
                    else:
                        auth_decoded = str(base64.b64decode(auth_header[6:]))
                    if '%s:%s' % (config['user'], config['pass']) == auth_decoded:
                        return True
                handler.set_status(401)
                handler.set_header('WWW-Authenticate', 'Basic realm=%s' % config['realm'])
                handler._transforms = []
                handler.finish()
                return False

            def _execute(self, transforms, *args, **kwargs):
                if not check_auth(self):
                    return False
                return handler_execute(self, transforms, *args, **kwargs)
            return _execute

        handler_class._execute = wrap_execute(handler_class._execute)
    return handler_class


class SchedulerServer:

    VERSION = 'v1'

    singleton = None

    def __init__(self, scheduler_instance):
        self.pre_scheduler_init()

        # Start scheduler
        self.scheduler_manager = scheduler_instance

        self.tornado_settings = dict(
            debug=settings.DEBUG,
            static_path=settings.STATIC_DIR_PATH,
            template_path=settings.TEMPLATE_DIR_PATH,
            scheduler_manager=self.scheduler_manager
        )

        # Setup server
        URLS = [
            # Index page
            (r'/', index.Handler),

            # APIs
            (r'/api/%s/jobs' % self.VERSION, jobs.Handler),
            (r'/api/%s/jobs/(.*)' % self.VERSION, jobs.Handler),
            (r'/api/%s/executions' % self.VERSION, executions.Handler),
            (r'/api/%s/executions/(.*)' % self.VERSION, executions.Handler),
            (r'/api/%s/logs' % self.VERSION, audit_logs.Handler),

            # Healthcheck
            (r'/healthcheck', healthcheck.Handler)
        ]
        self.application = tornado.web.Application(URLS, **self.tornado_settings)

    def start_scheduler(self):
        self.scheduler_manager.start()
        self.post_scheduler_start()

    def pre_scheduler_init(self):
        pass

    def post_scheduler_start(self):
        """Implement this function to do things once scheduler starts"""
        pass

    def stop_scheduler(self):
        self.scheduler_manager.stop()
        self.post_scheduler_stop()

    def post_scheduler_stop(self):
        """Implement this function to do things once scheduler stops"""
        pass

    @classmethod
    def signal_handler(cls, signal, frame):
        logger.info('Stopping scheduler ...')
        cls.singleton.stop_scheduler()
        logger.info('Done. Bye ~')
        sys.exit(0)

    @classmethod
    def run(cls):
        if not cls.singleton:
            signal.signal(signal.SIGINT, cls.signal_handler)

            cls.singleton = cls(scheduler_manager.SchedulerManager.get_instance())
            cls.singleton.start_scheduler()
            cls.singleton.application.listen(settings.HTTP_PORT, settings.HTTP_ADDRESS)
            logger.info('Running server at %s:%d ...' % (settings.HTTP_ADDRESS, settings.HTTP_PORT))
            logger.info('*** You can access scheduler web ui at http://localhost:%d'
                        ' ***' % settings.HTTP_PORT)
            tornado.ioloop.IOLoop.instance().start()
