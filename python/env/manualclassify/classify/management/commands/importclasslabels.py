from django.core.management.base import BaseCommand, CommandError
from classify.models import ClassLabel, TagLabel
import requests

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('autoclass_csv_url', type=str, help='url for autoclass csv from which to import classes')

    def handle(self, *args, **options):
        autoclass_csv_url = options['autoclass_csv_url']

        r = requests.get(autoclass_csv_url)
        r.raise_for_status()

        labels = r.text.partition('\n')[0].split(',')

        if 'pid' in labels:
            labels.remove('pid')

        class_labels = list({l.split('_TAG_')[0].replace('_', ' ') for l in labels})
        class_labels.sort()

        tag_labels = list({l.split('_TAG_')[1].replace('_', ' ') for l in labels if '_TAG_' in l})
        tag_labels.sort()

        for class_label in class_labels:
            if not ClassLabel.objects.filter(name=class_label):
                self.stdout.write(f'Creating class label {class_label}')
                class_label_record = ClassLabel(name=class_label)
                class_label_record.save()

        for tag_label in tag_labels:
            if not TagLabel.objects.filter(name=tag_label):
                self.stdout.write(f'Creating tag label {tag_label}')
                tag_label_record = TagLabel(name=tag_label)
                tag_label_record.save()
