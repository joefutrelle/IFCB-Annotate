from django.core.management.base import BaseCommand, CommandError
from classify.models import ClassLabel
import requests

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('autoclass_csv_url', type=str, help='url for autoclass csv from which to import classes')

    def handle(self, *args, **options):
        autoclass_csv_url = options['autoclass_csv_url']

        r = requests.get(autoclass_csv_url)
        r.raise_for_status()

        class_labels = r.text.partition('\n')[0].split(',')

        if 'pid' in class_labels:
            class_labels.remove('pid')

        class_labels = [c.replace('_', ' ') for c in class_labels]

        for class_label in class_labels:
            if not ClassLabel.objects.filter(name=class_label):
                self.stdout.write(f'Creating class label {class_label}')
                class_label_record = ClassLabel(name=class_label)
                class_label_record.save()
