from django.core.management.base import BaseCommand

from core.models import Job
from core.worker import perform_job


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("job_id", type=int)

    def handle(self, job_id, **options):
        perform_job(Job.objects.get(pk=job_id, status="RUNNING"))
