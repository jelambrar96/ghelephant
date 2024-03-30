FROM python:3.10
WORKDIR /ghelephant

COPY . /ghelephant
RUN pip install -r requirements.txt

ENTRYPOINT ["./ghelephant.py"] 
