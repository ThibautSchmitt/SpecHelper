from django.core.management.base import BaseCommand

from core.models import Job
from core.worker import perform_job


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)
        parser.add_argument("--attempt-id", default=None)

    def handle(self, job_id, **options):
        job = Job.objects.filter(pk=job_id, status="RUNNING").first()
        if job:
            perform_job(job, options.get("attempt_id"))
