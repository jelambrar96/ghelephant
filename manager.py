import requests
import gzip
import os
import logging
import datetime
from variables import data_path
from queue import Queue  
from json_to_csv_converter import JSONToCSVConverter
from csv_writers import CSVWriters
from database_link import DatabaseLink


class Manager:
    def __init__(self, start_year, start_month, start_day, end_year, end_month, end_day):
        self.start_year = start_year
        self.start_month = start_month
        self.start_day = start_day
        self.end_year = end_year
        self.end_month = end_month
        self.end_day = end_day
        dates_to_download = self.__dates_to_download()
        self.dates_to_download = iter(dates_to_download)
        self.last_hour = dates_to_download[-1]
        self.last_day = self.last_hour[:-2]
        self.downloadedQueue = Queue(maxsize=10)
        self.decompressedQueue = Queue(maxsize=10)
        self.written_queue = Queue(maxsize=3)

    def run_download(self):
        while date := next(self.dates_to_download, None):
            self.download_json(date)
            self.downloadedQueue.put(date)

    def run_decompress(self):
        while date := self.downloadedQueue.get():
            self.decompress_json(date)
            self.decompressedQueue.put(date)
            if date == self.last_hour:
                break

    def run_write_csvs(self):
        with DatabaseLink() as db:
            db.create_tables()

        converter = JSONToCSVConverter(writers=None)
        while date := self.decompressedQueue.get():
            day, hour = date[:10], date[11:]
            if hour == '23':
                converter.writers = CSVWriters(day)  # type: ignore
                if day[-2:] == '01':
                    converter.reset_added_sets()
            file_name = f'{data_path}/{date}.json'
            logging.info(f'Writing csv for {date}')
            with open(file_name, 'rb') as f:
                converter.write_events(f)
            self.remove_json(date)
            if hour == '0':
                converter.writers.close()  # type: ignore
                self.written_queue.put(day)
                if date == self.last_hour:
                    break

        with DatabaseLink() as db:
            db.add_primary_keys()

    def run_copy_into_database(self):
        while day := self.written_queue.get():
            logging.info('Inserting csvs into database')
            with DatabaseLink() as db:
                db.insert_csvs_into_db(day)
            self.remove_inserted_csvs(day)
            if day == self.last_day:
                break

    def __dates_to_download(self) -> list:
        dates_to_download = []
        start_date = datetime.date(self.start_year, self.start_month, self.start_day)
        end_date = datetime.date(self.end_year, self.end_month, self.end_day)
        delta = end_date - start_date
        for i in range(delta.days + 1):
            day = start_date + datetime.timedelta(days=i)
            for h in range(0, 24):
                dates_to_download.append(f'{day.year}-{str(day.month).zfill(2)}-{str(day.day).zfill(2)}-{h}')
        dates_to_download.reverse()
        return dates_to_download

    @staticmethod
    def download_json(date_to_download):
        path = f'{data_path}/{date_to_download}'
        if os.path.isfile(f'{path}.json'):
            return
        # download compressed file
        logging.info(f'Downloading {date_to_download}')
        response = requests.get(f'https://data.gharchive.org/{date_to_download}.json.gz')
        with open(f'{path}.json.gz', 'wb') as f:
            f.write(response.content)

    @staticmethod
    def decompress_json(date_to_download):
        path = f'{data_path}/{date_to_download}'
        if os.path.isfile(f'{path}.json'):
            return
        # decompress file, delete compressed file
        logging.info(f'Decompressing {date_to_download}')
        with gzip.open(f'{path}.json.gz', 'rb') as compressed, open(f'{path}.json', 'wb') as uncompressed:
            uncompressed.write(compressed.read())
        os.remove(f'{path}.json.gz')

    @staticmethod
    def remove_json(date_to_download):
        path = f'{data_path}/{date_to_download}'
        os.remove(f'{path}.json')

    @staticmethod
    def remove_inserted_csvs(day):
        os.system(f'rm {data_path}/*-{day}.csv')
