import psycopg2
import os
import platform
import logging
import traceback
import pandas as pd
from csv_writers import CSVWriters
from psycopg2.errors import CharacterNotInRepertoire


class DatabaseLink:
    """
    Class to link to the database and perform operations on it.
    """
    def __init__(self, username, password, 
                database, host, port,
                sed_name=None, data_path="."):
        self.conn = psycopg2.connect(database=database, user=username,
            password=password, host=host, port=port)
        self.cursor = self.conn.cursor()
        self.username = username
        self.password = password
        self.database = database
        self.host = host
        self.port = port
        self.data_path = data_path
        self.sed_name = sed_name

    def __enter__(self):
        self.__init__(username=self.username, password=self.password, 
                          database=self.database, host=self.host, port=self.port, 
                          sed_name=self.sed_name, data_path=self.data_path)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.conn.commit()
        self.cursor.close()
        self.conn.close()

    def create_tables(self):
        """
        Create tables in the database.
        :return: None
        """
        with open('sql/create_tables.sql', 'r') as f:
            self.cursor.execute(f.read())
        self.conn.commit()

    def create_indices(self):
        """
        Create indices in the database.
        :return: None
        """
        logging.info('Creating indices')
        with open('sql/create_indices.sql', 'r') as f:
            self.cursor.execute(f.read())
        self.conn.commit()
        logging.info('Finished creating indices')

    def insert_csvs_into_db(self, date, use_pandas=False):
        """
        Insert CSV files into the database.
        :param date: the date of the files to be inserted, corresponds to file name
        :return: None
        """
        if not use_pandas:
            for table in CSVWriters.file_names:
                query = f"COPY {table} FROM '{self.data_path}/{table}-{date}.csv' WITH (FORMAT csv)"
                try:
                    self.cursor.execute(query)
                except CharacterNotInRepertoire:
                    self.conn.rollback()
                    logging.warn(f'Illegal character in table {table} for {date}, removing null bytes and retrying')
                    if self.sed_name is None:
                        DatabaseLink.__remove_null_chars(f"{self.data_path}/{table}-{date}.csv")
                    else:
                        os.system(f"{self.sed_name} -i 's/\\x00//g' {self.data_path}/{table}-{date}.csv")
                    logging.info(f'Removed null bytes from {table}')
                    self.cursor.execute(query)
                except Exception:
                    self.conn.rollback()
                    logging.error(f'Error copying table {table} for {date} into database')
                    logging.error(traceback.format_exc())
                self.conn.commit()
        else:
            for table in CSVWriters.file_names:
                csv_filepath = f'{self.data_path}/{table}-{date}.csv'
                try:
                    df = pd.read_csv(csv_filepath)
                    df.to_sql(table, self.conn, if_exists='append')
                except Exception:
                    self.conn.rollback()
                    logging.error(f'Error copying table {table} for {date} into database')
                    logging.error(traceback.format_exc())                
        logging.info(f'Finished copying {date} into database')

    @staticmethod
    def __remove_null_chars( filepath):
        with open(filepath, 'r', encoding='utf-8') as archivo_entrada:
            contenido = archivo_entrada.read()
        contenido_sin_nulos = contenido.replace('\x00', '')
        with open(filepath, 'w', encoding='utf-8') as archivo_salida:
            archivo_salida.write(contenido_sin_nulos)
