import logging
import time

from django.core.management.base import BaseCommand

from chronograph.job_management import JobProcess

logger = logging.getLogger('chronograph.commands.cron')


class Command(BaseCommand):
    help = 'Runs all jobs that are due.'

    def handle(self, *args, **options):
        from chronograph.models import Job

        procs = []
        for job in Job.objects.due():
            proc = JobProcess(job)
            proc.start()
            procs.append(proc)

        logger.info("%d Jobs are due" % len(procs))

        # Keep looping until all jobs are done
        while procs:
            for i in range(len(procs)):
                if not procs[i].is_alive():
                    procs.pop(i)
                    break
                time.sleep(.1)
