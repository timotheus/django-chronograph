import sys
import os
import logging
import traceback
import tempfile
import time
from StringIO import StringIO
from datetime import datetime
from multiprocessing import Process
from threading import Thread

from django.core.management import call_command
from django.template import loader, Context
from django.db import transaction
from django import db
from django.db.utils import DatabaseError

from chronograph.models import Job, Log
from chronograph.compatibility import dates

logger = logging.getLogger('chronograph.job.management')


class JobHeartbeatThread(Thread):
    """
    A very simple thread that updates a temporary "lock" file every second.
    If the ``Job`` that we are associated with gets killed off, then the file
    will no longer be updated and after ``CHRONOGRAPH_LOCK_TIMEOUT`` seconds,
    we assume the ``Job`` has terminated.

    The heartbeat should be started with the ``start`` method and once the
    ``Job`` is completed it should be stopped by calling the ``stop`` method.
    """
    daemon = True
    halt = False

    def __init__(self, *args, **kwargs):
        self.lock_file = tempfile.NamedTemporaryFile()
        Thread.__init__(self, *args, **kwargs)

    def run(self):
        """
        Do not call this directly; call ``start()`` instead.
        """
        while not self.halt:
            self.lock_file.seek(0)
            self.lock_file.write(str(time.time()))
            self.lock_file.flush()
            time.sleep(1)

    def stop(self):
        """
        Call this to stop the heartbeat.
        """
        self.halt = True
        while self.is_alive():
            time.sleep(.1)
        self.lock_file.close()
        try:
            os.remove(self.lock_file.name)
        except:
            # Ignore errors trying to remove the lockfile.
            pass


class JobRunner(object):
    """
    Class that handles the actual running of a job.
    """
    def __init__(self, job):
        self.job_id = job.id

    def run(self):
        """
        This method implements the code to actually run a ``Job``.
        """
        args = None
        options = None
        job = None
        last_run_successful = None
        heartbeat = None
        job_is_running = False
        run_date = dates.now()

        # Update job with running data.
        with transaction.commit_on_success():
            job = Job.objects.lock_job(self.job_id)

            if not job.check_is_running():
                args, options = job.get_args()
                heartbeat = JobHeartbeatThread()
                job.is_running = True
                job.lock_file = heartbeat.lock_file.name
                job.save()
            else:
                job_is_running = True

        # Only proceed if the job is not already running.
        if not job_is_running:
            # Redirect output so that we can log it if there is any
            stdout = StringIO()
            stderr = StringIO()
            ostdout = sys.stdout
            ostderr = sys.stderr
            sys.stdout = stdout
            sys.stderr = stderr
            stdout_str, stderr_str = "", ""

            # Start job heartbeat.
            heartbeat.start()

            try:
                logger.debug("Calling command '%s'" % job.command)
                call_command(job.command, *args, **options)
                logger.debug("Command '%s' completed" % job.command)
                last_run_successful = True
            except Exception, e:
                try:
                    # The command failed to run; log the exception
                    t = loader.get_template('chronograph/error_message.txt')
                    c = Context({
                        'exception': unicode(e),
                        'traceback': ['\n'.join(traceback.format_exception(*sys.exc_info()))]
                    })
                    stderr_str += t.render(c)
                except Exception, e2:
                    sys.stderr.write('Caught exception (%s) while handling job exception (%s)' % (e2, e))
                last_run_successful = False

            # Stop the heartbeat
            logger.debug("Stopping heartbeat")
            heartbeat.stop()
            heartbeat.join()

            # Get stdout/stderr.
            stdout_str += stdout.getvalue()
            stderr_str += stderr.getvalue()

            duration = dates.total_seconds((dates.now()-run_date))

            with transaction.commit_on_success():
                job = Job.objects.lock_job(self.job_id)

                # If anything was printed to stderr, consider the run
                # unsuccessful
                if stderr_str:
                    job.last_run_successful = False
                else:
                    job.last_run_successful = last_run_successful
                job.is_running = False
                job.lock_file = ""

                # Only care about minute-level resolution
                job.last_run = dates.make_aware(datetime(
                    run_date.year, run_date.month, run_date.day,
                    run_date.hour, run_date.minute))

                # If this was a forced run, then don't update the
                # next_run date
                if job.force_run:
                    logger.debug("Resetting 'force_run'")
                    job.force_run = False
                else:
                    logger.debug("Determining 'next_run'")
                    while job.next_run < dates.now():
                        job.next_run = dates.make_aware(job.rrule.after(job.next_run))
                    logger.debug("'next_run = ' %s" % job.next_run)
                job.save()

            # Redirect output back to default
            sys.stdout = ostdout
            sys.stderr = ostderr

            if stdout_str or stderr_str:
                log = Log.objects.create(
                    job=job,
                    run_date=run_date,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    success=job.last_run_successful,
                    duration=duration
                )

                # Send emails
                log.email_subscribers()


class JobProcess(Process):
    """
    Each ``Job`` gets run in it's own ``Process``.
    """
    daemon = True

    def __init__(self, job, *args, **kwargs):
        self.job = job
        Process.__init__(self, *args, **kwargs)

    def run(self):
        # Close database connection so it's not shared with the parent.
        # django will reconnect automatically.
        db.close_connection()

        logger.info("Running Job: '%s'" % self.job)
        job_runner = JobRunner(self.job)
        job_runner.run()
