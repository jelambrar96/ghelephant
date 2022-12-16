import psycopg2
from variables import database_name, database_user
import logging
from variables import data_path, sed_name
import os
from psycopg2.errors import CharacterNotInRepertoire


class DatabaseLink:
    def __init__(self):
        self.conn = psycopg2.connect(database=database_name, user=database_user)
        self.cursor = self.conn.cursor()

    def __enter__(self):
        self.__init__()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.conn.commit()
        self.cursor.close()
        self.conn.close()

    def create_tables(self):
        with open('sql/create_tables.sql', 'r') as f:
            self.cursor.execute(f.read())
        self.conn.commit()

    def add_primary_keys(self):
        with open('sql/primary_keys.sql', 'r') as f:
            self.cursor.execute(f.read())
        self.conn.commit()

    def get_csv_files(self, suffix=''):
        files = os.listdir(data_path)
        return [f.removesuffix(f'.csv{suffix}') for f in files if f.endswith(f'.csv{suffix}')]

    def insert_csvs_into_db(self, suffix=''):
        for table in self.get_csv_files(suffix=suffix):
            logging.info(f'Inserting {table} into database')
            query = f"COPY {table} FROM '{data_path}/{table}.csv{suffix}' WITH (FORMAT csv)"
            try:
                self.cursor.execute(query)
            except CharacterNotInRepertoire:
                self.conn.rollback()
                logging.error(f'Illegal character in {table}, removing null bytes and retrying')
                os.system(f"{sed_name} -i 's/\\x00//g' {data_path}/{table}.csv{suffix}")
                logging.info(f'Removed null bytes from {table}')
                self.cursor.execute(query)
            self.conn.commit()
