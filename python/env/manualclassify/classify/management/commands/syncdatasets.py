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

        # NOTE: ifcbdb /api/list_datasets should be used here, but its response includes inactive datasets
        #       change to use it if an active filter gets implemented: https://github.com/WHOIGit/ifcbdb/issues/507
        active_datasets = list(set([x.replace('dataset=', '').strip() for x in
                    re.findall(r'dataset=[^\'"\\]*', str(requests.get(f'{dashboard_url}datasets').content))]))
        active_datasets.sort()

        for dataset in active_datasets:
            #NOTE: timeseries_url *must* have a trailing slash
            timeseries_url = f'{dashboard_url}{dataset}/'
            if not Timeseries.objects.filter(url=timeseries_url):
                self.stdout.write(f'Creating timeseries {timeseries_url}')
                timeseries = Timeseries(url=timeseries_url)
                timeseries.save()
