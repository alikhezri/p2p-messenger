FROM python:3.8-slim-buster
COPY ./requirements.txt /code/
RUN pip install -r /code/requirements.txt
COPY ./src/ /code/src/
WORKDIR /code/src/
CMD [ "python", "main.py"]