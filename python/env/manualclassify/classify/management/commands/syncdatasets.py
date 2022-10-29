from django.core.management.base import BaseCommand, CommandError
from classify.models import Timeseries
import requests

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('dashboard', type=str, help='dashboard url (example https://ifcb-data.whoi.edu)')

    def handle(self, *args, **options):
        dashboard_url = options['dashboard']

        if not dashboard_url.endswith('/'):
            dashboard_url += '/'

        active_datasets = [x[0] for x in
                    requests.get(f'{dashboard_url}secure/api/dt/datasets').json()['data'] if x[2]]
        active_datasets.sort()

        for dataset in active_datasets:
            #NOTE: timeseries_url *must* have a trailing slash
            timeseries_url = f'{dashboard_url}{dataset}/'
            if not Timeseries.objects.filter(url=timeseries_url):
                self.stdout.write(f'Creating timeseries {timeseries_url}')
                timeseries = Timeseries(url=timeseries_url)
                timeseries.save()
