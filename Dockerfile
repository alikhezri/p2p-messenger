FROM python:3.8-slim-buster
COPY ./requirements.txt ./
RUN pip install -r requirements.txt
COPY ./src/ /code/
WORKDIR /code/
CMD [ "python", "main.py"]