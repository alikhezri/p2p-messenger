FROM python:3.8-slim-buster
COPY ./src/ /code/
WORKDIR /code/
CMD [ "python", "main.py"]